#!/usr/bin/env bash
# =============================================================================
#  BrewHome — Script d'installation
#  Usage : sudo bash install.sh
#  Distributions supportées : Debian/Ubuntu, Fedora/RHEL, Arch, Alpine Linux
# =============================================================================

set -euo pipefail

# ── Couleurs ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERREUR]${RESET} $*" >&2; exit 1; }
step()    { echo -e "\n${BOLD}━━━  $*  ━━━${RESET}"; }

# ── Vérifications préalables ──────────────────────────────────────────────────
[ "$(id -u)" -eq 0 ] || error "Ce script doit être exécuté en root (sudo bash install.sh)"

DISTRO=""
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO="${ID:-}"
fi

# ── Variables ─────────────────────────────────────────────────────────────────
APP_NAME="brewhome"
INSTALL_DIR="/opt/${APP_NAME}"
APP_USER="brewhome"
APP_PORT=5000

# Répertoire source : dossier contenant ce script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="${SCRIPT_DIR}/brewhome"

[ -d "${SRC_DIR}" ] || error "Répertoire source introuvable : ${SRC_DIR}"

# =============================================================================
step "1/6 — Dépendances système"
# =============================================================================

if command -v apk &>/dev/null; then
    info "Système Alpine Linux détecté"
    apk update --quiet
    # bash requis pour ce script, python3, pip, venv, curl
    apk add --no-cache bash python3 py3-pip curl
    # py3-virtualenv ou le module venv inclus dans python3 selon la version
    python3 -m venv --help &>/dev/null || apk add --no-cache py3-virtualenv
    NOLOGIN_SHELL="/sbin/nologin"

elif command -v apt-get &>/dev/null; then
    info "Système Debian/Ubuntu détecté"
    apt-get update -qq
    apt-get install -y -qq python3 python3-venv python3-pip curl
    NOLOGIN_SHELL="/usr/sbin/nologin"

elif command -v dnf &>/dev/null; then
    info "Système Fedora/RHEL détecté"
    dnf install -y -q python3 python3-pip curl
    NOLOGIN_SHELL="/usr/sbin/nologin"

elif command -v pacman &>/dev/null; then
    info "Système Arch Linux détecté"
    pacman -Sy --noconfirm python python-pip curl
    NOLOGIN_SHELL="/usr/sbin/nologin"

else
    warn "Gestionnaire de paquets non reconnu — vérifiez manuellement que python3, pip et venv sont installés"
    NOLOGIN_SHELL="/usr/sbin/nologin"
fi

python3 --version &>/dev/null || error "python3 introuvable après installation"
success "Python $(python3 --version 2>&1 | awk '{print $2}') disponible"

# ── Détection du gestionnaire de services ─────────────────────────────────────
if command -v rc-service &>/dev/null && [ -d /etc/init.d ]; then
    SERVICE_MANAGER="openrc"
    info "Gestionnaire de services : OpenRC"
else
    SERVICE_MANAGER="systemd"
    info "Gestionnaire de services : systemd"
fi

# =============================================================================
step "2/6 — Création de l'utilisateur système"
# =============================================================================

if id "${APP_USER}" &>/dev/null; then
    info "Utilisateur '${APP_USER}' déjà existant"
else
    if [ "${DISTRO}" = "alpine" ]; then
        # Alpine utilise adduser (busybox), syntaxe différente de useradd
        adduser -S -D -H -s "${NOLOGIN_SHELL}" "${APP_USER}"
    else
        useradd --system --no-create-home --shell "${NOLOGIN_SHELL}" "${APP_USER}"
    fi
    success "Utilisateur système '${APP_USER}' créé"
fi

# =============================================================================
step "3/6 — Copie des fichiers dans ${INSTALL_DIR}"
# =============================================================================

if [ -d "${INSTALL_DIR}" ]; then
    warn "Le répertoire ${INSTALL_DIR} existe déjà — mise à jour des fichiers"
    for db in brewhome.db brewhome_readings.db; do
        if [ -f "${INSTALL_DIR}/${db}" ]; then
            info "Base de données préservée : ${db}"
        fi
    done
fi

mkdir -p "${INSTALL_DIR}"

# Copie en excluant venv et les bases SQLite existantes
rsync -a --exclude='venv/' --exclude='*.db' "${SRC_DIR}/" "${INSTALL_DIR}/" 2>/dev/null \
    || cp -r "${SRC_DIR}/." "${INSTALL_DIR}/"

chown -R "${APP_USER}:${APP_USER}" "${INSTALL_DIR}"
success "Fichiers copiés dans ${INSTALL_DIR}"

# =============================================================================
step "4/6 — Environnement virtuel Python & dépendances"
# =============================================================================

VENV_DIR="${INSTALL_DIR}/venv"

if [ ! -d "${VENV_DIR}" ]; then
    info "Création de l'environnement virtuel…"
    python3 -m venv "${VENV_DIR}"
fi

info "Installation des dépendances Python…"
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt"

chown -R "${APP_USER}:${APP_USER}" "${VENV_DIR}"
success "Dépendances installées ($(${VENV_DIR}/bin/pip show flask | grep ^Version | awk '{print "Flask "$2}'))"

# =============================================================================
step "5/6 — Service ${SERVICE_MANAGER}"
# =============================================================================

if [ "${SERVICE_MANAGER}" = "openrc" ]; then
    # ── OpenRC (Alpine Linux) ──────────────────────────────────────────────────
    INIT_SCRIPT="/etc/init.d/${APP_NAME}"
    LOG_FILE="/var/log/${APP_NAME}.log"

    cat > "${INIT_SCRIPT}" <<EOF
#!/sbin/openrc-run
description="BrewHome - Gestion Brasserie"

command="${VENV_DIR}/bin/python"
command_args="app.py"
command_background=true
directory="${INSTALL_DIR}"
command_user="${APP_USER}:${APP_USER}"
pidfile="/run/${APP_NAME}.pid"
output_log="${LOG_FILE}"
error_log="${LOG_FILE}"

depend() {
    need net
}
EOF

    chmod +x "${INIT_SCRIPT}"
    touch "${LOG_FILE}"
    chown "${APP_USER}:${APP_USER}" "${LOG_FILE}"

    rc-update add "${APP_NAME}" default 2>/dev/null || true
    success "Script OpenRC créé et activé au démarrage (runlevel default)"

else
    # ── systemd ───────────────────────────────────────────────────────────────
    SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"

    cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=BrewHome - Gestion Brasserie
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${VENV_DIR}/bin/python app.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${APP_NAME}

# Sécurité
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=${INSTALL_DIR}

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "${APP_NAME}.service"
    success "Service systemd créé et activé au démarrage"
fi

# =============================================================================
step "6/6 — Démarrage du service"
# =============================================================================

if [ "${SERVICE_MANAGER}" = "openrc" ]; then
    rc-service "${APP_NAME}" start
    sleep 2
    if rc-service "${APP_NAME}" status 2>&1 | grep -q "started"; then
        success "Service démarré avec succès"
    else
        warn "Le service n'a pas démarré — consultez les logs :"
        echo "    tail -n 30 /var/log/${APP_NAME}.log"
    fi
else
    systemctl restart "${APP_NAME}.service"
    sleep 2
    if systemctl is-active --quiet "${APP_NAME}.service"; then
        success "Service démarré avec succès"
    else
        warn "Le service n'a pas démarré — consultez les logs :"
        echo "    journalctl -u ${APP_NAME} -n 30 --no-pager"
    fi
fi

# =============================================================================
# Récupération de l'IP locale
# =============================================================================
LOCAL_IP=$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if ($i=="src") print $(i+1)}' | head -1)
[ -z "${LOCAL_IP}" ] && LOCAL_IP="<IP-du-serveur>"

# =============================================================================
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║        BrewHome installé avec succès !               ║${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${BOLD}Accès web${RESET}"
echo -e "    ${CYAN}http://${LOCAL_IP}:${APP_PORT}${RESET}"
echo -e "    ${CYAN}http://localhost:${APP_PORT}${RESET}"
echo ""
echo -e "  ${BOLD}Répertoire d'installation${RESET}"
echo -e "    ${INSTALL_DIR}"
echo ""

if [ "${SERVICE_MANAGER}" = "openrc" ]; then
    echo -e "  ${BOLD}Commandes du service (OpenRC)${RESET}"
    echo -e "    Démarrer   :  ${YELLOW}rc-service ${APP_NAME} start${RESET}"
    echo -e "    Arrêter    :  ${YELLOW}rc-service ${APP_NAME} stop${RESET}"
    echo -e "    Redémarrer :  ${YELLOW}rc-service ${APP_NAME} restart${RESET}"
    echo -e "    Statut     :  ${YELLOW}rc-service ${APP_NAME} status${RESET}"
    echo -e "    Logs live  :  ${YELLOW}tail -f /var/log/${APP_NAME}.log${RESET}"
    echo ""
    echo -e "  ${BOLD}Activer / désactiver au démarrage${RESET}"
    echo -e "    Activer    :  ${YELLOW}rc-update add    ${APP_NAME} default${RESET}"
    echo -e "    Désactiver :  ${YELLOW}rc-update del    ${APP_NAME} default${RESET}"
else
    echo -e "  ${BOLD}Commandes du service (systemd)${RESET}"
    echo -e "    Démarrer   :  ${YELLOW}sudo systemctl start   ${APP_NAME}${RESET}"
    echo -e "    Arrêter    :  ${YELLOW}sudo systemctl stop    ${APP_NAME}${RESET}"
    echo -e "    Redémarrer :  ${YELLOW}sudo systemctl restart ${APP_NAME}${RESET}"
    echo -e "    Statut     :  ${YELLOW}sudo systemctl status  ${APP_NAME}${RESET}"
    echo -e "    Logs live  :  ${YELLOW}sudo journalctl -u ${APP_NAME} -f${RESET}"
    echo ""
    echo -e "  ${BOLD}Activer / désactiver au démarrage${RESET}"
    echo -e "    Activer    :  ${YELLOW}sudo systemctl enable  ${APP_NAME}${RESET}"
    echo -e "    Désactiver :  ${YELLOW}sudo systemctl disable ${APP_NAME}${RESET}"
fi
echo ""
