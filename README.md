# BrewHome

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
- **Vue lecture** : mode lecture seul avec bouton bascule vers l'édition
- **Miniature du brouillon** : si la recette a été créée depuis un brouillon avec image, la miniature s'affiche en haut à droite de la fiche recette, cliquable pour l'afficher en grand
- **Étiquettes en cave** : section en bas de la fiche recette affichant les photos des bières liées (cave) sous forme de vignettes 90×90 cliquables
- Archivage et réorganisation

### Brassins
- Enregistrement des sessions de brassage liées à une recette
- Saisie de la **densité initiale (OG), densité finale (FG), ABV calculé**
- Suivi de l'état du brassin (en cours / terminé)
- Association à un **densimètre connecté** pour le suivi de fermentation (graphique densité + température)
- Association à une **sonde de température** pour le suivi de la température ambiante, y compris sur les brassins terminés (refermentation en bouteilles, garde…)
- Badge en temps réel sur la carte brassin pour le densimètre et la sonde associés (mesure courante + ancienneté)
- **Association à un soda keg** : liez directement un brassin à un keg depuis la carte brassin (badge keg affiché, volume mis en fermentation)
- Le densimètre est délié automatiquement à la clôture du brassin ; la sonde de température reste attachée pour le suivi post-fermentation
- **Passage en cave** depuis la clôture d'un brassin : saisie du stock bouteilles (33 cl / 75 cl) et/ou du **volume en fût** — l'image du brouillon d'origine est prévisualisée et automatiquement reprise dans la cave
- Archivage et réorganisation

### Cave à bières
- Gestion de votre **stock de bières embouteillées** (formats 33 cl et 75 cl) et **en fût** (volume en litres)
- Indicateur de niveau de remplissage avec barre de progression (bouteilles et fût)
- **Gestion des fûts** : saisie du volume courant et du volume initial, barre de progression colorée (vert / orange / rouge selon le niveau restant)
- **Modal de transfert fût → bouteilles** : saisie de la quantité consommée directement au fût + nombre de bouteilles 33 cl et 75 cl à remplir, récapitulatif en temps réel avec alerte de dépassement
- **Association à un soda keg** : liez une bière cave à un keg directement depuis sa carte (badge keg affiché avec le volume restant)
- Photo de la bière (stockée en base) — importée depuis un fichier, **générée par IA** ou supprimable ; propagée automatiquement depuis l'image du brouillon lors du passage en cave
- Type de bière avec autocomplétion (base de données de styles intégrée)
- Date de brassin et d'embouteillage
- Modal de détail avec visualisation plein écran de la photo
- Impression d'**étiquettes** (format A4 paysage, 5 par ligne, 51 mm de large)
- Archivage et réorganisation

### Soda Kegs
Inventaire et suivi de vos **soda kegs** (Corny Keg / Cornelius keg) pour la fermentation sous pression et le service en pression :

- Types pré-configurés : **Corny Keg / Soda Keg 19 L** et **Corny Keg 6 L** — type libre personnalisable
- Caractéristiques par keg : volume total, volume de fermentation (suggestion automatique à 80%), poids à vide, couleur, photo
- **Suivi du statut** : Vide · En fermentation · En service · Nettoyage
- Barre de progression du volume avec code couleur (vert → orange → rouge selon le niveau)
- **Association bidirectionnelle** :
  - Depuis la page **Kegs** : modal de statut pour lier un brassin (fermentation) ou une bière cave (service)
  - Depuis la page **Brassins** : bouton 🫙 sur chaque carte pour associer/dissocier un keg directement
  - Depuis la page **Cave** : bouton 🫙 sur chaque carte pour associer/dissocier un keg directement
- Badge keg affiché sur les cartes brassin et cave associées (nom + volume)
- Dissociation automatique de l'ancien keg lors d'une réassignation

### Cahier de brouillons
Espace de notes rapides pour vos idées de recettes, séparé du flux de création complet :
- **Formulaire structuré** : titre, style BJCP, volume cible, ingrédients (malts, houblons, levures, autres), notes libres
- **Couleur personnalisable** par brouillon (pastille colorée sur la carte de liste)
- **Image** : importée depuis un fichier ou **générée par IA** avec un champ d'instructions supplémentaires (style graphique, ambiance, ingrédients à illustrer…)
- **Vue lecture / mode édition** : consultation en lecture seule avec bascule vers l'édition, comme les recettes
- **Auto-save** : enregistrement automatique 1 seconde après la dernière frappe
- **Association à un événement calendrier** : objectif de brassage lié à un événement, avec bannière de compte à rebours (date de brassage + date de l'événement cible)
- **Créer la recette** : convertit le brouillon en recette complète (titre, style, notes pré-remplis) en un clic — l'image du brouillon suit automatiquement jusqu'à la cave via la recette et le brassin
- Suggestion de recette par IA : génère les ingrédients et les notes à partir du style et du titre

### Calendrier
Vue mensuelle de toutes les activités de brassage :
- **Événements automatiques** : brassins (date de brassage), fermentations, embouteillages — affichés directement depuis les données
- **Événements personnalisés** : titre, emoji, date, couleur, notes, notification Telegram le jour J
- **Association** : un événement peut être lié à un style BJCP, une recette ou un brouillon
- **Rappel J-45** : affiche un rappel dans le calendrier 45 jours avant l'événement (avec notification Telegram optionnelle)
- Brouillons associés à un événement : affichés dans le calendrier avec leur compte à rebours
- Navigation mois par mois, bouton "Aujourd'hui"

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
- Inventaire, recettes, cave, brassins, densimètres, **brouillons**, **calendrier**
- **Paramètres avancés** (eau, énergie, seuils, apparence) — les tokens GitHub et les clés IA sont exclus de l'export (mais conservés en base de données)

### Apparence
- Thème clair / sombre (bascule en nav)
- **Nom de l'application** personnalisable (affiché dans la nav, les étiquettes, la vitrine)
- **Logo** personnalisable (clic pour agrandissement)
- **Couleur d'accent** (amber par défaut)

### Notifications Telegram
Recevez des résumés automatiques directement dans Telegram — configurables depuis **Paramètres avancés → Notifications** :

| Notification | Fréquence | Contenu |
|---|---|---|
| 🍺 Brassins en cours | Quotidien | Nom, statut, OG/FG, ABV, date de brassage + **dernière densité et température** du densimètre associé (avec ancienneté de la mesure) |
| 🍾 État de la cave | Mensuel | Bières en stock (bouteilles 33cl / 75cl / fût) séparées des bières **épuisées** |
| 📦 Inventaire | Mensuel | **Un message par catégorie** : 🌾 Malts, 🌿 Houblons, 🧫 Levures, 🔮 Autres — seules les catégories non vides sont envoyées |

- Heure d'envoi configurable (quotidien) et jour + heure (mensuel)
- Fuseau horaire configurable (chaîne IANA, ex : `Europe/Paris`)
- Bouton **Envoyer maintenant** pour chaque notification
- Bouton **Tester la connexion** pour valider le bot avant activation
- Notifications Telegram sur les événements calendrier personnalisés (jour J et rappel J-45)

### Intelligence artificielle (IA)
Génération d'images et suggestion de recettes via IA externe — configurables depuis **Paramètres avancés → IA** :

#### Clés API
Deux clés indépendantes, configurables séparément :
- **Clé Google Gemini** : [aistudio.google.com](https://aistudio.google.com)
- **Clé OpenAI** : [platform.openai.com](https://platform.openai.com)

Les clés sont stockées en base de données et retrouvées automatiquement sur tous les appareils. Elles sont exclues de l'export JSON.

#### Génération d'images
Génère automatiquement une étiquette de bière (cave) ou une image de brouillon :

| Fournisseur | Modèle | Notes |
|-------------|--------|-------|
| OpenAI | `gpt-image-1` *(recommandé)* | Meilleure qualité, qualité configurable |
| OpenAI | `gpt-image-1.5` | |
| OpenAI | `chatgpt-image-latest` | |
| OpenAI | `gpt-image-1-mini` | Plus rapide |
| Gemini | `gemini-3.1-flash-image-preview` *(recommandé)* | Preview |
| Gemini | `gemini-2.5-flash-image` | Stable |
| Gemini | `gemini-3-pro-image-preview` | |

- Format **portrait** imposé (1024×1536 pour OpenAI, ratio 3:4 pour Gemini) — adapté à une étiquette
- Qualité configurable pour OpenAI : `auto`, `low`, `medium`, `high`
- **Champ d'instructions supplémentaires** : couleurs, style graphique, ingrédients à illustrer, ambiance…
- Prompt construit automatiquement sans ABV, sans contenance et sans logo de brasserie inventé
- Enregistrement automatique si la bière/le brouillon n'avait pas encore de photo

#### Suggestion de recette (Cahier de brouillons)
Génère automatiquement les ingrédients et les notes d'un brouillon à partir de son titre et de son style :

| Fournisseur | Modèle | Notes |
|-------------|--------|-------|
| Gemini | `gemini-2.5-flash` *(recommandé)* | Rapide et précis |
| Gemini | `gemini-2.0-flash-lite` | Allégé |
| Gemini | `gemini-2.5-pro` | Meilleure qualité |
| Gemini | `gemini-2.5-flash-preview` | Preview |
| Gemini | `gemini-2.5-pro-preview` | Preview |
| OpenAI | `gpt-4.1` *(recommandé)* | |
| OpenAI | `gpt-4.1-mini` | |
| OpenAI | `gpt-4.1-nano` | |
| OpenAI | `gpt-4o` | |
| OpenAI | `o4-mini` | |
| OpenAI | `o3-mini` | |
| OpenAI | `gpt-5` | |
| OpenAI | `gpt-5-mini` | |
| OpenAI | `gpt-3.5-turbo` | |

---

## Vitrine GitHub Pages

Publiez automatiquement un catalogue de vos bières sur **GitHub Pages** en un clic :
- Page HTML statique responsive générée et poussée sur votre dépôt
- Photos des bières, niveaux de stock avec barres de progression (bouteilles 33 cl / 75 cl)
- **Volume en fût** affiché sur chaque carte si la bière est en fût (volume courant, volume initial, barre de progression)
- **Compteur "Litres en fût"** dans les statistiques globales de la vitrine (affiché uniquement si au moins une bière est en fût)
- Logo et nom de l'application, couleur d'accent personnalisée
- Détection intelligente des **fichiers inchangés** (commit uniquement si modification) via l'API Git Data de GitHub (un seul commit pour tous les fichiers)
- Bouton **Forcer** pour créer un commit même si le contenu est identique (utile après un changement de configuration ou pour forcer une republication)

## Sauvegarde GitHub

Poussez l'intégralité de vos données sur un dépôt GitHub en un clic :
- `inventaire.json`, `recettes.json`, `brassins.json`, `cave.json`, `densimetres.json`, `brouillons.json`, `calendrier.json`, `parametres.json`
- Saut automatique des fichiers inchangés

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Python 3 / Flask |
| Base de données | SQLite (2 fichiers : données + mesures densimètre/température) |
| Frontend | HTML / CSS / JavaScript vanilla (pas de framework) |
| Icônes | Font Awesome 6 |
| Scheduler | APScheduler (notifications Telegram planifiées) |
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
