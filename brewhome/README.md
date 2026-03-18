# BrewHome

Application web de gestion de brasserie amateur — recettes, brassins, cave, inventaire et bien plus.
Fonctionne en local (PC, Raspberry Pi, NAS) et s'ouvre dans n'importe quel navigateur du réseau.

**Version actuelle : 0.0.5**

---

## Fonctionnalités

### Recettes
- Création et édition de recettes (malts, houblons, levures, autres ingrédients)
- Calcul automatique IBU (Tinseth), EBC (Morey), ABV estimé, coût
- Correction de l'eau (acidification, profil minéral)
- Import / Export **BeerXML 1.0** (compatible BeerSmith, Brewfather, BrewFather…)
- Duplication avec numéro de version automatique (`IPA v2` → `IPA v3`)
- Génération de recette par IA (Google Gemini)
- Vérification de stock en un clic
- Impression optimisée (fiche recette complète)

### Guide de brassage
- Chronomètre interactif par phase (concassage, empâtage, ébullition)
- Agenda des houblons en temps réel
- **Mode plein écran** — grande minuterie lisible à 1 mètre, mains occupées
- Checklist ingrédients et eau de brassage

### Brassins
- Suivi du statut (en cours, fermentation, embouteillage, terminé)
- **Cycle de vie** visuel : frise chronologique Brassage → Fermentation → Cave → Consommation
- Notes rapides directement depuis la liste
- Photos de brassin
- Intégration densimètres connectés (Tilt, iSpindel…)

### Cave à bières
- Stock par format (33cl, 75cl, fût)
- Suivi de consommation et courbe de dépletion
- **Étiquettes imprimables** (nom, ABV, style BJCP, IBU/EBC, barre couleur EBC, QR code)
- Impression en lot (toutes les bières filtrées, A4 paysage)
- Notes de dégustation structurées (arômes, flaveurs, amertume, bouche, notes générales, score)
- Assignation à un fût (keg)

### Inventaire
- Gestion des ingrédients par catégorie (malt, houblon, levure, autre)
- Alertes de stock faible
- Export / Import catalogue
- Import catalogue Hopsteiner

### Densimètres (Spindles)
- Réception des mesures en temps réel
- Graphiques gravité / ABV estimé / température
- Configuration et calibration depuis l'interface

### Notifications Telegram
- Rappels de fermentation (J-2, J-1, J0, J+1) avec estimation du nombre de bouteilles
- **Alerte embouteillage** immédiate lors de l'ajout en cave (nombre de bouteilles estimé)
- Rapport cave et brassins planifiable
- Rapport inventaire hebdomadaire
- Événements brassicoles mondiaux (jour J + rappel J-avant)

### Autres
- **Recherche globale** (Ctrl+K) — recettes, bières, inventaire, brassins, notes de dégustation
- Interface bilingue **Français / English**
- Thème clair / sombre
- Calendrier des événements brassicoles
- Brouillons de bières (planification)
- Vitrine publique exportable sur GitHub Pages
- Application Web Progressive (PWA) — installable sur mobile

---

## Technologies

| Composant | Détail |
|-----------|--------|
| Backend | Python 3.10+, Flask 3, SQLite |
| Planificateur | APScheduler |
| Images | Pillow |
| Frontend | HTML/CSS/JS vanilla, Chart.js, Font Awesome |
| Base de données | SQLite (fichier local `brewhome.db`) |

---

## Démarrage rapide

### Windows
Double-cliquer sur `install.bat` puis `start_silent.vbs`.
Voir [INSTALL.md](INSTALL.md) pour le détail.

### Linux / Raspberry Pi
```bash
chmod +x start.sh
./start.sh
```
Voir [INSTALL.md](INSTALL.md) pour l'installation en service systemd.

---

## Accès
Une fois lancé, ouvrir un navigateur sur :
```
http://localhost:5000
```
Ou depuis un autre appareil du réseau (remplacer par l'IP de la machine hôte) :
```
http://192.168.x.x:5000
```

---

## Structure du projet

```
brewhome/
├── app.py                  # Backend Flask + API REST
├── requirements.txt        # Dépendances Python
├── brewhome.db             # Base de données SQLite (créée au premier lancement)
├── install.bat             # Installation Windows
├── start.bat               # Démarrage Windows (avec console)
├── start_silent.vbs        # Démarrage Windows silencieux (arrière-plan)
├── stop.bat                # Arrêt Windows
├── start.sh                # Démarrage Linux
├── brewhome.service        # Service systemd (Linux)
├── static/                 # Fichiers statiques (CSS, JS, images, fonts)
└── templates/
    ├── index.html
    └── parts/
        ├── nav.html
        ├── page_recettes.html
        ├── page_cave.html
        ├── page_brassins.html (et autres pages)
        ├── modals_*.html
        └── scripts.html    # Toute la logique JS + i18n
```

---

## Licence
Usage personnel — homebrewing enthusiasts only.
