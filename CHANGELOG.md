# Changelog

Toutes les modifications notables de ce projet sont documentées ici.

---

## [2026-05-25] — 4

### Corrigé
- **Calendrier — création d'événement** : erreur 500 `NOT NULL constraint failed: custom_calendar_events.brew_reminder_days` lors de l'enregistrement d'un nouvel événement quand le champ "rappel de brassage (jours)" n'était pas renseigné. La valeur par défaut est maintenant `0`.

---

## [2026-05-21] — 3

### Corrigé
- **Recettes — correction d'eau : noms d'ingrédients** : les minéraux et acides ajoutés via le panneau de correction d'eau s'appelaient "Acide lactique 80% (empatage)" au lieu de "Acide lactique 80%", ce qui empêchait la déduction automatique du stock lors du passage en brassin. Le suffixe (empatage) / (sparge) est retiré du nom ; le moment d'ajout est conservé dans le champ `other_type`.

---

## [2026-05-21] — 2

### Ajouté
- **Inventaire — tri des colonnes** : les en-têtes **Ingrédient** et **Quantité** sont maintenant cliquables pour trier la liste (A→Z, Z→A, ↑, ↓) avec indicateur visuel. Le glisser-déposer est automatiquement désactivé quand un tri est actif.

---

## [2026-05-21] — 1

### Ajouté
- **Catalogue — recherche en temps réel** : dans Paramètres > Catalogue, un champ de recherche filtre instantanément la liste par nom et sous-catégorie
- **Recettes — avertissement volume insuffisant** : lorsque les volumes d'eau saisis manuellement ne permettent pas d'atteindre le volume cible de la recette, une alerte ambrée s'affiche avec le volume estimé réel
- **GitHub** : connexion du répertoire local au dépôt `https://github.com/chatainsim/brewhome` — premier push de l'ensemble du code
- **CHANGELOG.md** : ce fichier

### Modifié
- **Recettes — calcul pré-ébullition en mode manuel** : en mode saisie manuelle des volumes d'eau, le pré-ébullition affiché est désormais calculé à partir de l'eau réellement utilisée (et non de la cible), avec recalcul du volume final estimé
- **Documentation** : mise à jour de `README.md`, `INSTALL.md` et `API.md` (champs `water_mash_override`, `water_sparge_override`, `ferm_profile` ; endpoints fork et historique des recettes)

### Corrigé
- **Recettes — mode visualisation** : les valeurs de saisie manuelle des volumes d'eau ne s'affichaient pas en mode visualisation d'une recette (JS compilé obsolète)

---

## [Pré-historique] — avant le 2026-05-21

> Historique reconstitué depuis le code source. Pas de dates précises disponibles.

### Fonctionnalités existantes au premier commit

**Inventaire**
- Gestion des stocks de malts, houblons, levures et autres ingrédients
- Alertes de stock faible avec seuils configurables par catégorie et unité
- Prix à l'unité pour le calcul de coût des recettes
- Réorganisation par glisser-déposer, archivage
- Déduction automatique du stock lors de la validation d'un brassin

**Recettes**
- Créateur complet : volume, efficacité, températures/durées d'empâtage et d'ébullition
- Calculs automatiques : OG estimée, IBU (Tinseth), EBC, coût matières
- IBU en temps réel dans l'en-tête de la section houblons
- Volumes d'eau automatiques (ratio, absorption, évaporation) avec saisie manuelle
- Comparaison styles BJCP (OG, FG, ABV, IBU, EBC min/max)
- Autocomplétion depuis le catalogue d'ingrédients
- Gestion houblons : type, temps d'addition, dry hop
- Ingrédients "autres" avec 8 moments d'ajout possibles
- Paramètre de fermentation (température, durée)
- Note sur 5 étoiles, vue lecture / édition
- Cloner à X litres (mise à l'échelle automatique)
- Miniature brouillon d'origine, étiquettes cave associées
- Impression (A4/A5, portrait/paysage)
- Import BeerXML avec détection des ingrédients manquants

**Brassins**
- Sessions de brassage liées à une recette
- Lancement depuis une recette avec coût estimé en temps réel
- Saisie OG, FG, ABV calculé ; suivi état (en cours / terminé)
- Association densimètre connecté (graphique densité + température)
- Association sonde de température Home Assistant
- Association soda keg, badge en temps réel
- Passage en cave (stock bouteilles 33/75 cl + volume fût)

**Cave à bières**
- Stock bouteilles (33 cl / 75 cl) et fûts (volume)
- Barre de progression colorée, modal transfert fût → bouteilles
- Association soda keg
- Photo (import fichier ou génération IA)
- Impression d'étiquettes (51 mm, 5 par ligne, A4/A5)

**Soda Kegs**
- Types pré-configurés Corny Keg 19 L et 6 L, type libre
- Suivi statut : Vide / En fermentation / En service / Nettoyage
- Suivi des révisions avec alerte si dépassée ou imminente
- Fiche détail, débit rapide, association bidirectionnelle avec brassins et cave

**Cahier de brouillons**
- Formulaire structuré : titre, style BJCP, volume, ingrédients, notes
- Couleur personnalisable, image (import ou génération IA)
- Vue lecture / édition, auto-save (1 s après la dernière frappe)
- Association à un événement calendrier avec compte à rebours
- Conversion brouillon → recette complète
- Suggestion de recette par IA

**Calendrier**
- Vue mensuelle : brassins, fermentations, embouteillages automatiques
- Événements brassicoles mondiaux générés automatiquement (IPA Day, Oktoberfest…)
- Événements personnalisés avec récurrence (ponctuel, annuel, Nième jour)
- Association événement ↔ style BJCP / recette / brouillon
- Rappel de brassage configurable par événement
- Notifications Telegram (rappel + jour J)

**Densimètres connectés**
- Endpoint universel `POST /api/spindle/data` : iSpindel, Tilt, GravityMon, générique
- Tableau de bord par appareil, graphique de fermentation, association brassin

**Sondes de température (Home Assistant)**
- Types `sensor` (température + humidité) et `climate` (thermostat)
- Association brassin, alertes seuils min/max, graphique historique
- Génération YAML prête à copier pour `configuration.yaml` et `automations.yaml`

**Paramètres avancés**
- Catalogue d'ingrédients (malts, houblons, levures, autres) — enrichissable
- Seuils de stock par catégorie et unité
- Eau & Énergie : prix, profil minéral, récupération automatique via HubEau
- Import / Export JSON par module (tokens exclus de l'export)
- Langue : Français / English (interface entièrement traduite)
- Apparence : thème clair/sombre, nom et logo personnalisables, couleur d'accent
- Mises à jour : vérification version GitHub, mise à jour Chart.js / Font Awesome / Google Fonts

---
