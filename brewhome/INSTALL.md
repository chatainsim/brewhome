# Installation de BrewHome

## Prérequis

- **Python 3.10 ou plus récent** — [python.org/downloads](https://www.python.org/downloads/)
- Connexion Internet (uniquement pour l'installation des dépendances)

---

## Windows

### Installation (première fois)

1. Double-cliquer sur **`install.bat`**
2. Le script va :
   - Vérifier que Python est disponible
   - Créer un environnement virtuel (`venv/`)
   - Installer les dépendances (`Flask`, `APScheduler`, `Pillow`)
   - Créer un raccourci sur le Bureau
   - Proposer le démarrage automatique au login

> Si Python n'est pas trouvé : télécharger depuis [python.org](https://www.python.org/downloads/) en cochant **"Add Python to PATH"** lors de l'installation.

### Démarrage

| Fichier | Action |
|--------|--------|
| `start.bat` | Lance BrewHome avec une fenêtre console (logs visibles) |
| `start_silent.vbs` | Lance en arrière-plan (sans console) — usage quotidien recommandé |
| `stop.bat` | Arrête l'application |

### Démarrage automatique

L'installateur propose d'activer le démarrage automatique via le Planificateur de tâches Windows.
Pour l'activer manuellement plus tard, relancer `install.bat` en tant qu'Administrateur.

---

## Linux / Raspberry Pi

### Installation manuelle

```bash
# Cloner ou copier le projet dans /opt/brewhome
cd /opt/brewhome

# Rendre le script exécutable
chmod +x start.sh

# Premier lancement (crée le venv et installe les dépendances)
./start.sh
```

Le premier lancement crée automatiquement l'environnement virtuel et installe les dépendances.

### Service systemd (démarrage automatique au boot)

1. Adapter `brewhome.service` si nécessaire (chemin, utilisateur) :

```ini
[Service]
User=www-data                          # ou votre utilisateur
WorkingDirectory=/opt/brewhome        # chemin vers le dossier
ExecStart=/opt/brewhome/venv/bin/python app.py
```

2. Installer et activer le service :

```bash
sudo cp brewhome.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable brewhome
sudo systemctl start brewhome
```

3. Vérifier le statut :

```bash
sudo systemctl status brewhome
# Logs en temps réel :
sudo journalctl -u brewhome -f
```

### Installation manuelle des dépendances (sans start.sh)

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python app.py
```

---

## Accès à l'interface

Une fois lancé, ouvrir un navigateur :

| Depuis | URL |
|--------|-----|
| La machine hôte | `http://localhost:5000` |
| Un autre appareil du réseau | `http://<IP_HOTE>:5000` |

L'IP de la machine hôte s'obtient avec :
- Windows : `ipconfig` dans un terminal
- Linux : `ip addr` ou `hostname -I`

---

## Mise à jour

1. Remplacer les fichiers du projet (conserver `brewhome.db`)
2. Réinstaller les dépendances si `requirements.txt` a changé :
   - Windows : relancer `install.bat`
   - Linux : `venv/bin/pip install -r requirements.txt`
3. Relancer l'application

> La base de données `brewhome.db` est créée automatiquement et mise à jour au démarrage — aucune migration manuelle nécessaire.

---

## Dépendances Python

| Paquet | Version minimale | Rôle |
|--------|-----------------|------|
| Flask | 3.0.0 | Serveur web et API REST |
| APScheduler | 3.10.0 | Notifications planifiées (Telegram) |
| Pillow | 10.0.0 | Traitement des photos |

---

## Désinstallation

1. Supprimer le dossier `brewhome/`
2. Windows : supprimer la tâche planifiée si activée :
   ```
   schtasks /delete /tn "BrewHome" /f
   ```
3. Linux : désactiver le service :
   ```bash
   sudo systemctl disable brewhome
   sudo rm /etc/systemd/system/brewhome.service
   ```

La base de données `brewhome.db` contient toutes vos données — la conserver si vous souhaitez migrer vers une autre machine.
