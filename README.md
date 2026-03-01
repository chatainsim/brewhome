# BrewHome

## Attention, application uniquement codé par Claude Code. Le support sera limité. (_spaghetti_ inside)

Application web de gestion pour brasseurs amateurs.
Hébergée localement (sur un Raspberry Pi, NAS, PC ou serveur Linux), accessible depuis n'importe quel appareil de votre réseau.

---

## Fonctionnalités

### Inventaire des matières premières
- Gestion des stocks de **malts, houblons, levures et autres ingrédients**
- Filtrage par catégorie, affichage archivé/actif
- Alertes visuelles de **stock faible** avec seuils configurables par catégorie et unité
- Prix à l'unité pour le calcul de coût des recettes
- Réorganisation par glisser-déposer
- Déduction automatique du stock lors de la validation d'un brassin

### Recettes
- Créateur de recettes complet : volume, efficacité de brasserie, températures et durées d'empâtage et d'ébullition
- Calculs automatiques : **OG estimée, IBU, EBC, coût matières** (ingrédients + eau + énergie)
- Comparaison avec les styles **BJCP** (OG, FG, ABV, IBU, EBC min/max)
- Recherche par autocomplétion dans le catalogue d'ingrédients
- Gestion des houblons : type (amérisant, aromatique, dual), temps d'addition, ajouts à sec (*dry hop*)
- Gestion des ingrédients "autres" : épices, fruits, adjuvants, sels de correction — avec moment d'ajout : **Empâtage, Eau de rinçage, Ébullition, Flameout, Whirlpool, Dry Hop, Fermentation, Mise en bouteille**
- Paramètre de fermentation (température, durée)
- Note sur 5 étoiles
- Archivage et réorganisation

### Brassins
- Enregistrement des sessions de brassage liées à une recette
- Saisie de la **densité initiale (OG), densité finale (FG), ABV calculé**
- Suivi de l'état du brassin (en cours / terminé)
- Association à un **densimètre connecté** pour le suivi de fermentation (graphique densité + température)
- Association à une **sonde de température** pour le suivi de la température ambiante, y compris sur les brassins terminés (refermentation en bouteilles, garde…)
- Badge en temps réel sur la carte brassin pour le densimètre et la sonde associés (mesure courante + ancienneté)
- Le densimètre est délié automatiquement à la clôture du brassin ; la sonde de température reste attachée pour le suivi post-fermentation
- Archivage et réorganisation

### Cave à bières
- Gestion de votre **stock de bières embouteillées** (formats 33 cl et 75 cl)
- Indicateur de niveau de remplissage avec barre de progression
- Photo de la bière (stockée en base)
- Type de bière avec autocomplétion (base de données de styles intégrée)
- Date de brassin et d'embouteillage
- Modal de détail avec visualisation plein écran de la photo
- Impression d'**étiquettes** (format A4 paysage, 5 par ligne, 51 mm de large)
- Archivage et réorganisation

### Densimètres connectés
Endpoint universel `POST /api/spindle/data?token=TOKEN` supportant plusieurs types d'appareils :

| Appareil | Protocole | Particularité |
|----------|-----------|---------------|
| **iSpindel** | HTTP POST | Format natif |
| **Tilt** (via TiltBridge) | HTTP POST | Température en °F → conversion automatique |
| **GravityMon** | HTTP POST | Compatible iSpindel |
| **Générique** | HTTP POST ou GET | Champs flexibles (`gravity`/`SG`, `temperature`/`temp`…) |

- Tableau de bord par appareil : densité, température, batterie, angle, ancienneté de la mesure
- Badge coloré par type d'appareil
- Graphique de fermentation (densité, ABV estimé, température)
- Association à un brassin en cours — badge live sur la carte brassin
- Purge configurable de la base de mesures

### Sondes de température (Home Assistant)
Surveillance de température en temps réel via **Home Assistant** (frigos, caves, cuves…) :
- Deux types d'entités HA supportés :

| Type | Entité HA | Données remontées |
|------|-----------|-------------------|
| **Sonde** | `sensor.xxx` | Température + humidité |
| **Thermostat** | `climate.xxx` | Température courante, consigne, mode (chauffe / refroid. / arrêt) |

- Compatible avec tout appareil exposé dans HA : **Inkbird ITC-308 WiFi** (`climate.xxx`), sondes Zigbee/Z-Wave, etc.
- Saisie du nom de l'entité HA directement dans le formulaire de création — le YAML est pré-rempli
- **Association à un brassin** (en cours ou terminé) : badge température en temps réel sur la carte brassin, bouton graphique direct ; la sonde reste attachée après la clôture pour la refermentation ou la garde
- Alertes visuelles si la température sort des seuils min/max configurés
- Carte thermostat : affichage de la **consigne** et du **mode HVAC** avec icône colorée
- Suivi de l'**humidité** pour les sondes de type `sensor`
- Graphique historique avec sélection de plage (24 h → 30 jours → tout → personnalisé) et lignes de seuil
- Le modal "configuration" génère deux blocs YAML distincts prêts à copier-coller séparément dans `configuration.yaml` et `automations.yaml`

---

## Paramètres avancés

### Catalogue d'ingrédients
Catalogue de référence préchargé (malts, houblons, levures) enrichissable :
- Malts : EBC, rendement GU, % max en recette
- Houblons : taux d'alpha, catégorie
- Levures : températures de fermentation, atténuation, tolérance alcool, dosage
- Autres ingrédients personnalisables

### Seuils de stock
Définissez les seuils d'alerte (affichage orange) par catégorie :
- Malts (en g), houblons (en g), levures (en sachets)
- Autres : seuils par unité (g, kg, mL, L, pièce, sachet)

### Eau & Énergie
- Prix de l'eau au litre (inclus dans le coût de la recette)
- Coût gaz et électricité par brassin
- **Profil minéral** : pH, Calcium, Magnésium, Sodium, Sulfates, Chlorures, Bicarbonates (mg/L)
- **Récupération automatique via HubEau** : sélectionnez votre département et commune pour importer les dernières valeurs de qualité de l'eau du robinet (API officielle Eau France, couvre toute la France métropolitaine et les DOM)

### Import / Export
Export et import au format JSON pour chaque module :
- Inventaire, recettes, cave, brassins, densimètres
- **Paramètres avancés** (eau, énergie, seuils, apparence) — les tokens GitHub sont exclus de l'export

### Apparence
- Thème clair / sombre (bascule en nav)
- **Nom de l'application** personnalisable (affiché dans la nav, les étiquettes, la vitrine)
- **Logo** personnalisable (clic pour agrandissement)
- **Couleur d'accent** (amber par défaut)

---

## Vitrine GitHub Pages

Publiez automatiquement un catalogue de vos bières sur **GitHub Pages** en un clic :
- Page HTML statique responsive générée et poussée sur votre dépôt
- Photos des bières, niveaux de stock avec barres de progression
- Logo et nom de l'application, couleur d'accent personnalisée
- Détection intelligente des **fichiers inchangés** (commit uniquement si modification) via l'API Git Data de GitHub (un seul commit pour tous les fichiers)

## Sauvegarde GitHub

Poussez l'intégralité de vos données sur un dépôt GitHub en un clic :
- `inventaire.json`, `recettes.json`, `brassins.json`, `cave.json`, `densimetres.json`, `parametres.json`
- Saut automatique des fichiers inchangés

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Python 3 / Flask |
| Base de données | SQLite (2 fichiers : données + mesures densimètre/température) |
| Frontend | HTML / CSS / JavaScript vanilla (pas de framework) |
| Icônes | Font Awesome 6 |
| Déploiement | Service systemd ou OpenRC, ou lancement direct |

---

## Accès réseau

L'application écoute sur `0.0.0.0:5000`.
Une fois démarrée, elle est accessible depuis tout appareil de votre réseau local :

```
http://<IP-du-serveur>:5000
```

---

## Licence

Usage personnel, pas de licence explicite définie.

