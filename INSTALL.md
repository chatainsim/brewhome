# Installation de BrewHome

## Prérequis

- **Python 3.10 ou supérieur**
- `pip` et `venv` (inclus avec Python 3)
- Accès réseau local pour atteindre l'interface depuis d'autres appareils

---

## Linux / Raspberry Pi / NAS — Installation automatique

Le script `install.sh` prend en charge les distributions suivantes :
Debian · Ubuntu · Raspberry Pi OS · Fedora · RHEL · Arch Linux · Alpine Linux

### 1. Cloner ou copier les fichiers

```bash
# Via git
git clone <url-du-dépôt> brewhome-src
cd brewhome-src

# Ou décompresser l'archive
unzip brewhome.zip
cd brewhome
```

### 2. Lancer l'installation

```bash
sudo bash install.sh
```

Le script effectue automatiquement :
1. Installation de Python 3, pip, venv et curl via le gestionnaire de paquets
2. Création d'un utilisateur système dédié `brewhome`
3. Copie des fichiers dans `/opt/brewhome` (les bases de données existantes sont préservées)
4. Création d'un environnement virtuel Python et installation des dépendances (Flask, APScheduler, Pillow)
5. Enregistrement et activation d'un service **systemd** (ou **OpenRC** sous Alpine)
6. Démarrage du service

### 3. Accéder à l'application

À la fin de l'installation, le script affiche l'URL :

```
http://<IP-du-serveur>:5000
```

---

## Linux — Gestion du service

### systemd (Debian, Ubuntu, Fedora, Arch…)

```bash
# Démarrer
sudo systemctl start brewhome

# Arrêter
sudo systemctl stop brewhome

# Redémarrer
sudo systemctl restart brewhome

# Statut
sudo systemctl status brewhome

# Logs en temps réel
sudo journalctl -u brewhome -f

# Activer au démarrage
sudo systemctl enable brewhome

# Désactiver au démarrage
sudo systemctl disable brewhome
```

### OpenRC (Alpine Linux)

```bash
rc-service brewhome start
rc-service brewhome stop
rc-service brewhome restart
rc-service brewhome status

# Logs
tail -f /var/log/brewhome.log

# Activer au démarrage
rc-update add brewhome default

# Désactiver au démarrage
rc-update del brewhome default
```

---

## Windows — Installation automatique

### Prérequis

Python 3.10+ doit être installé et dans le PATH.
Téléchargement : <https://www.python.org/downloads/>
> Cochez **"Add Python to PATH"** lors de l'installation.

### 1. Lancer `install.bat`

Double-cliquez sur `brewhome\install.bat` ou exécutez-le depuis une invite de commandes.

Le script effectue :
1. Détection de Python
2. Création de l'environnement virtuel `venv\`
3. Installation des dépendances Python (Flask, APScheduler, Pillow)
4. Création d'un raccourci **BrewHome** sur le bureau (lance en arrière-plan)
5. Proposition d'activation du **démarrage automatique** à l'ouverture de session

### 2. Lancer l'application

| Fichier | Description |
|---------|-------------|
| `start.bat` | Lance avec une fenêtre console (logs visibles) |
| `start_silent.vbs` | Lance en **arrière-plan** sans fenêtre (recommandé au quotidien) |
| `stop.bat` | Arrête l'application |

Après le lancement, le navigateur s'ouvre automatiquement sur `http://localhost:5000`.

---

## Lancement manuel (sans installation de service)

Utile pour tester ou développer.

```bash
cd brewhome

# Créer l'environnement virtuel (première fois uniquement)
python3 -m venv venv

# Installer les dépendances (première fois uniquement)
venv/bin/pip install -r requirements.txt   # Linux/macOS
# ou
venv\Scripts\pip install -r requirements.txt   # Windows

# Démarrer
venv/bin/python app.py   # Linux/macOS
# ou
venv\Scripts\python app.py   # Windows
```

L'application est accessible sur `http://localhost:5000`.

---

## Mise à jour

### Linux (service installé)

```bash
# Copier les nouveaux fichiers (les bases de données sont préservées)
sudo bash install.sh
```

Le script détecte l'installation existante, met à jour les fichiers et redémarre le service.

### Windows

1. Arrêtez l'application (`stop.bat` ou fermez la fenêtre)
2. Remplacez les fichiers (sauf `venv\`, `brewhome.db`, `brewhome_readings.db`)
3. Relancez `start.bat` ou `start_silent.vbs`

---

## Structure des fichiers

```
brewhome/
├── app.py                  Application Flask (backend + routes API)
├── requirements.txt        Dépendances Python (Flask, APScheduler, Pillow)
├── brewhome.db             Base de données principale (SQLite, créée au 1er lancement)
├── brewhome_readings.db    Base de données des mesures densimètre/température (SQLite)
├── templates/
│   ├── index.html
│   └── parts/              Fragments HTML de l'interface
├── static/                 Fichiers statiques (CSS, JS éventuels)
├── start.bat               Lancement Windows avec console
├── start_silent.vbs        Lancement Windows silencieux
├── stop.bat                Arrêt Windows
├── install.bat             Installation Windows
├── start.sh                Lancement Linux manuel
└── brewhome.service        Fichier de service systemd (exemple)
```

---

## Densimètres connectés supportés

L'endpoint universel accepte les données en **HTTP POST** (ou GET) :

```
POST http://<IP-du-serveur>:5000/api/spindle/data?token=<TOKEN>
```

Le `<TOKEN>` est généré automatiquement à la création du densimètre. Le type d'appareil se sélectionne dans le modal — les instructions de configuration s'affichent automatiquement.

### iSpindel

Configuration dans l'iSpindel (onglet Configuration) :

| Paramètre | Valeur |
|-----------|--------|
| Service | HTTP |
| Méthode | POST |
| Port | 5000 |
| Chemin | `/api/spindle/data` |
| URL | `http://<IP>:5000/api/spindle/data?token=<TOKEN>` |

Champs envoyés : `gravity`, `temperature` (°C), `battery` (V), `angle`, `RSSI`

### Tilt (via TiltBridge)

Dans TiltBridge, configurer un service **Custom HTTP** :

| Paramètre | Valeur |
|-----------|--------|
| Méthode | POST |
| URL | `http://<IP>:5000/api/spindle/data?token=<TOKEN>` |

La température est envoyée en **Fahrenheit** par TiltBridge (`Temp`) et convertie automatiquement en °C.
Champs envoyés : `SG`, `Temp` (°F), `Color`

### GravityMon

Dans GravityMon, configurer le service **BrewSpy** ou un endpoint HTTP personnalisé pointant vers :

```
POST http://<IP>:5000/api/spindle/data?token=<TOKEN>
```

Champs compatibles : `gravity`, `temperature` (°C), `battery`, `angle`, `rssi`

### Générique / Autre

N'importe quel appareil capable d'envoyer un HTTP POST ou GET. Champs acceptés :

| Champ prioritaire | Alias acceptés |
|-------------------|---------------|
| `gravity` | `SG`, `specific_gravity` |
| `temperature` | `temp`, `celsius` (en °C) — ou `temp_f` / `fahrenheit` (en °F) |
| `battery` | `voltage` (tension en V) |
| `angle` | `tilt` |
| `rssi` | `RSSI`, `signal` |

Le token peut aussi être inclus dans le corps JSON : `{"token":"…","gravity":…}`

---

## Sondes de température (Home Assistant)

BrewHome peut recevoir des données de température depuis **Home Assistant**, ce qui permet de surveiller n'importe quel appareil exposé dans HA : Inkbird ITC-308 WiFi, sondes Zigbee/Z-Wave, thermostats connectés, etc.

Deux types d'entités HA sont supportés :

| Type | Entité HA | Usage |
|------|-----------|-------|
| **Sonde** | `sensor.xxx` | Sondes de température + humidité |
| **Thermostat** | `climate.xxx` | Thermostats connectés (ex : Inkbird ITC-308 WiFi) |

### Principe

1. Créez une sonde dans BrewHome (page **Capteurs** → section "Sondes de température")
2. Choisissez le **type d'entité** (Sonde ou Thermostat) et saisissez le nom de l'entité Home Assistant
3. Cliquez sur l'icône **clé** de la carte pour afficher la configuration HA
4. Copiez-collez les deux blocs YAML dans les fichiers correspondants et rechargez HA
5. *(Optionnel)* Associez la sonde à un brassin via le sélecteur en bas de sa carte — la température apparaît en temps réel sur la carte brassin

Le sélecteur propose deux groupes :
- **En cours** — brassins actifs (fermentation primaire)
- **Terminés** — brassins clos (refermentation en bouteilles, garde, maturation…)

> Contrairement au densimètre (délié automatiquement à la clôture), la sonde de température **reste attachée** au brassin après la complétion, pour assurer le suivi post-fermentation. Elle peut être déliée manuellement à tout moment via le sélecteur.

### Endpoint

```
POST http://<IP-du-serveur>:5000/api/temperature/data?token=<TOKEN>
Content-Type: application/json
```

Le token peut aussi être passé dans le corps JSON.

### Configuration Home Assistant — Sonde (`sensor.xxx`)

BrewHome génère les deux blocs YAML prêts à copier-coller depuis l'interface (icône clé sur la carte).

**Bloc 1 — `configuration.yaml`** :

```yaml
rest_command:
  brewhome_temp_frigo_cave:
    url: "http://<IP>:5000/api/temperature/data?token=<TOKEN>"
    method: POST
    content_type: "application/json"
    payload: >-
      {"temperature":{{ states('sensor.inkbird_itc308_temperature_probe')|float|round(1) }},"humidity":{{ states('sensor.inkbird_itc308_humidity')|float|round(1)|default(none) }}}
```

**Bloc 2 — `automations.yaml`** :

```yaml
- alias: "BrewHome — Frigo Cave"
  trigger:
    - platform: time_pattern
      minutes: "/5"
  action:
    - action: rest_command.brewhome_temp_frigo_cave
```

### Configuration Home Assistant — Thermostat (`climate.xxx`)

Pour les appareils exposés comme entité `climate` (ex : Inkbird ITC-308 WiFi → `climate.itc_308_wifi_thermostat`).
En plus de la température, BrewHome enregistre la **consigne** et le **mode** (chauffe / refroidissement / arrêt).

**Bloc 1 — `configuration.yaml`** :

```yaml
rest_command:
  brewhome_temp_frigo_cave:
    url: "http://<IP>:5000/api/temperature/data?token=<TOKEN>"
    method: POST
    content_type: "application/json"
    payload: >-
      {"temperature":{{ state_attr('climate.itc_308_wifi_thermostat','current_temperature')|float|round(1) }},"target_temp":{{ state_attr('climate.itc_308_wifi_thermostat','temperature')|float|round(1) }},"hvac_mode":"{{ states('climate.itc_308_wifi_thermostat') }}"}
```

**Bloc 2 — `automations.yaml`** :

```yaml
- alias: "BrewHome — Frigo Cave"
  trigger:
    - platform: time_pattern
      minutes: "/5"
  action:
    - action: rest_command.brewhome_temp_frigo_cave
```

> Le YAML exact (avec les noms d'entités renseignés lors de la création) est généré automatiquement par BrewHome — il suffit de copier-coller chaque bloc dans le bon fichier.

### Champs acceptés par l'endpoint

| Champ | Alias acceptés | Unité |
|-------|----------------|-------|
| `temperature` | `temp`, `celsius`, `Temperature` | °C |
| `temperature` | `temp_f`, `fahrenheit` | °F (converti automatiquement) |
| `humidity` | `Humidity`, `hum` | % |
| `target_temp` | `target_temperature`, `setpoint` | °C |
| `hvac_mode` | `mode` | texte (`heat`, `cool`, `off`…) |

### Alertes de seuil

Configurez des seuils **min** et **max** (en °C) sur chaque sonde. Si la température sort de la plage, la carte affiche une alerte visuelle colorée (bleu = sous le seuil, rouge = dépassement).

---

## Génération d'images par IA (optionnel)

BrewHome peut générer automatiquement une étiquette de bière (cave) ou une image illustrant un brouillon de recette, via une IA externe.

### Configuration

1. Ouvrez **Paramètres avancés** → onglet **IA**
2. Saisissez votre **clé Google Gemini** et/ou votre **clé OpenAI** (indépendantes)
3. Dans la section **Génération d'images**, choisissez le fournisseur et le modèle
4. Cliquez sur **Enregistrer la config IA**

Les clés API sont stockées en **base de données** — retrouvées automatiquement sur tous les appareils. Elles sont exclues de l'export JSON.

### Fournisseurs et modèles — Images

**OpenAI**

| Modèle | Notes |
|--------|-------|
| `gpt-image-1` *(recommandé)* | Meilleure qualité, niveaux de qualité configurables |
| `gpt-image-1.5` | |
| `chatgpt-image-latest` | |
| `gpt-image-1-mini` | Plus rapide |

Qualité : `auto` (défaut) · `low` · `medium` · `high`
Clé API : [platform.openai.com](https://platform.openai.com)

**Google Gemini**

| Modèle | ID API | Statut |
|--------|--------|--------|
| Gemini 3.1 Flash Image *(recommandé)* | `gemini-3.1-flash-image-preview` | Preview |
| Gemini 2.5 Flash Image | `gemini-2.5-flash-image` | Stable |
| Gemini 3 Pro Image | `gemini-3-pro-image-preview` | Preview |

> Les modèles Gemini image nécessitent un compte avec facturation activée — le tier gratuit n'inclut pas la génération d'images.

Clé API : [aistudio.google.com](https://aistudio.google.com)

### Format généré

Les images sont générées en **portrait** (1024×1536 pour OpenAI, ratio 3:4 pour Gemini), adapté à une étiquette de bière ou à l'illustration d'un brouillon. Le prompt est construit automatiquement sans ABV, sans contenance et sans logo de brasserie inventé.

### Utilisation — Cave (étiquette de bière)

1. Dans la **Cave**, cliquez sur **Ajouter** ou modifiez une bière existante
2. Le bouton **Générer avec IA** et le champ d'instructions apparaissent sous la zone photo (uniquement si une clé est configurée)
3. Renseignez le nom, le type et/ou la description de la bière
4. *(Optionnel)* Ajoutez des **instructions supplémentaires** : couleurs, style graphique, ingrédients à illustrer, ambiance…
5. Cliquez sur **Générer avec IA** — l'image s'insère directement dans le formulaire
6. Si la bière n'avait pas encore de photo, elle est **enregistrée automatiquement** en base
7. Pour supprimer une photo existante, cliquez sur le bouton ✕ superposé à l'aperçu

### Utilisation — Cahier de brouillons

1. Ouvrez un brouillon existant ou créez-en un nouveau
2. Dans la section **Image**, saisissez des **instructions supplémentaires** si souhaité (style artistique, ambiance, ingrédients à mettre en valeur…)
3. Cliquez sur **Générer avec IA** — l'image est insérée et sauvegardée avec le brouillon
4. Cette image **suit automatiquement** jusqu'à la cave : lors du passage en cave depuis le brassin, l'image du brouillon d'origine est proposée et reprise comme photo de la bière

---

## Suggestion de recette par IA (optionnel)

Depuis le **Cahier de brouillons**, BrewHome peut générer automatiquement une liste d'ingrédients et des notes à partir du titre et du style BJCP du brouillon.

### Configuration

1. Ouvrez **Paramètres avancés** → onglet **IA**
2. Dans la section **Suggestion de recette**, choisissez le fournisseur et le modèle texte
3. Cliquez sur **Enregistrer la config IA**

### Fournisseurs et modèles — Texte

**Google Gemini**

| Modèle | Notes |
|--------|-------|
| `gemini-2.5-flash` *(recommandé)* | Rapide et précis |
| `gemini-2.0-flash-lite` | Allégé |
| `gemini-2.5-pro` | Meilleure qualité |
| `gemini-2.5-flash-preview` | Preview |
| `gemini-2.5-pro-preview` | Preview |

**OpenAI**

| Modèle | Notes |
|--------|-------|
| `gpt-4.1` *(recommandé)* | |
| `gpt-4.1-mini` | |
| `gpt-4.1-nano` | |
| `gpt-4o` | |
| `o4-mini` | |
| `o3-mini` | |
| `gpt-5` | |
| `gpt-5-mini` | |
| `gpt-3.5-turbo` | |

### Utilisation

1. Dans le **Cahier de brouillons**, ouvrez un brouillon en mode édition
2. Renseignez au minimum le **titre** et/ou le **style BJCP**
3. Cliquez sur le bouton de suggestion IA — les ingrédients et les notes sont générés et insérés dans le formulaire
4. Ajustez selon vos préférences puis enregistrez

---

## Notifications Telegram (optionnel)

BrewHome peut envoyer des notifications automatiques dans Telegram : résumé quotidien des brassins en cours, état mensuel de la cave et de l'inventaire, et alertes sur les événements calendrier.

### Contenu des notifications

| Notification | Fréquence | Détail |
|---|---|---|
| 🍺 **Brassins en cours** | Quotidien | Nom, statut, OG/FG, ABV, date de brassage. Si un densimètre est associé au brassin : dernière densité mesurée, température et ancienneté de la mesure |
| 🍾 **État de la cave** | Mensuel | Bières avec stock (bouteilles 33cl / 75cl / fût en litres) puis bières épuisées dans une section séparée |
| 📦 **Inventaire** | Mensuel | Un message par catégorie non vide : 🌾 Malts, 🌿 Houblons, 🧫 Levures, 🔮 Autres — quantités et unités par article |
| 📅 **Événements calendrier** | Jour J (+ rappel configurable si activé) | Titre, notes et rappel de brassage pour chaque événement personnalisé avec Telegram activé |

### 1. Créer un bot Telegram

1. Ouvrez Telegram et cherchez **@BotFather**
2. Envoyez `/newbot` et suivez les instructions
3. Copiez le **token** fourni (format `123456789:AAF…`)

### 2. Obtenir votre Chat ID

1. Démarrez une conversation avec votre bot (envoyez-lui n'importe quel message)
2. Ouvrez dans un navigateur : `https://api.telegram.org/bot<VOTRE_TOKEN>/getUpdates`
3. Repérez le champ `"chat":{"id": XXXXXXXXX}` — c'est votre Chat ID

### 3. Configurer dans BrewHome

1. Ouvrez **Paramètres avancés** → onglet **Notifications**
2. Renseignez le **Token du bot** et le **Chat ID**
3. Définissez le **fuseau horaire** du serveur (ex : `Europe/Paris`)
4. Activez les notifications souhaitées et configurez les horaires :
   - Brassins : heure d'envoi quotidienne (HH:MM)
   - Cave et Inventaire : jour du mois (1–28) + heure d'envoi
5. Cliquez sur **Tester la connexion** pour valider le bot
6. Utilisez **Envoyer maintenant** sur chaque ligne pour un envoi immédiat
7. Enregistrez — les planifications prennent effet immédiatement sans redémarrage

### Fuseau horaire

Le champ fuseau horaire accepte les chaînes IANA standard :

| Zone | Valeur |
|------|--------|
| France métropolitaine | `Europe/Paris` |
| UTC | `UTC` |
| Heure de l'Est (USA) | `America/New_York` |

Pour trouver votre fuseau : [en.wikipedia.org/wiki/List_of_tz_database_time_zones](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)

> **Note** : les notifications nécessitent que le serveur BrewHome soit en fonctionnement au moment de l'envoi planifié. Si l'application est redémarrée, les planifications sont rechargées automatiquement depuis la base de données.

---

## Notes

- Le port par défaut est **5000**. Il est fixé dans `app.py` et dans le service systemd/OpenRC.
- Les deux bases de données SQLite (`brewhome.db` et `brewhome_readings.db`) sont créées automatiquement au premier démarrage. `brewhome_readings.db` contient les mesures des densimètres **et** des sondes de température. Les nouvelles colonnes (`recurrence`, `brew_reminder_days`, etc.) sont ajoutées automatiquement par migration au premier démarrage après mise à jour — aucune intervention manuelle n'est nécessaire.
- Aucune connexion Internet n'est requise pour le fonctionnement de base. La récupération des données d'eau (HubEau), la synchronisation GitHub, la génération d'images par IA, la suggestion de recette par IA et les notifications Telegram nécessitent un accès réseau.
- Tous les paramètres avancés (seuils, eau, énergie, GitHub, IA, Telegram) sont **synchronisés en base de données** et retrouvés automatiquement sur tout appareil accédant à l'instance BrewHome. Les tokens GitHub, les clés IA et le token Telegram sont inclus dans cette synchronisation, visibles en clair dans l'interface de configuration, mais **exclus de l'export JSON** pour éviter toute diffusion accidentelle.
