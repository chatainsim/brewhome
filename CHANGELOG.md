# Changelog

Toutes les modifications notables de ce projet sont documentées ici.

---

## [2026-09-19] — 14 · version 0.1.11

### Ajouté
- **Vitrine — rappel de la bière en tête des pages de recette** : le QR code des étiquettes menant directement à la recette, on arrivait sur la liste des ingrédients sans savoir de quelle bière il s'agissait ni ce qu'il en restait. Les pages s'ouvrent désormais sur l'étiquette, le nom, le type, l'ABV, le stock par contenance avec sa barre de remplissage, le contenu du fût, la description et les dates de brassage et d'embouteillage.
- **Vitrine — densités et ABV mesurés** : les pages de recette n'affichaient que les valeurs calculées. Les relevés du brassin apparaissent maintenant juste en dessous, l'écart avec la théorie étant l'information utile. L'API des bières expose pour cela les mesures du brassin, aliasées afin de ne pas écraser l'ABV propre à la bière.

### Corrigé
- **Scripts — modification perdue sans avertissement** : `templates/parts/scripts/*.html` sont les sources et `static/js/bh-*.js` les sorties compilées ; une modification faite directement dans une sortie disparaissait au premier changement de sa source, silencieusement. La compilation compare désormais le contenu et signale le cas dans le journal, en nommant les deux fichiers.

---

## [2026-09-18] — 13 · version 0.1.10

### Corrigé
- **Cave — bouton « Modifier » sans effet, transfert de fût et enregistrement des stocks cassés** : depuis l'ajout des tailles 25 cl et 50 cl, le code de la cave construisait les identifiants de champs à partir de la clé complète (`beer-f-25cl`) alors que le formulaire utilise `beer-f-25`. L'élément étant introuvable, le remplissage du modal s'interrompait avant affichage. Une fonction `sizeId()` rend désormais la convention explicite, appliquée aux dix emplacements concernés.

---

## [2026-09-18] — 12 · version 0.1.9

### Corrigé
- **Profils d'eau — commune dont le nom contient une apostrophe** : le bouton d'enregistrement d'une commune HubEau restait sans effet pour « L'Isle-d'Abeau », « L'Étang-Salé » et consorts. Les données insérées dans les attributs HTML sont désormais échappées pour ce contexte précis, correction appliquée à l'ensemble de l'interface (brouillons, calendrier, recettes, densimètres, cœur).

### Modifié
- **Export SQL — purge des réglages sensibles** : l'export applique désormais la même purge que la sauvegarde GitHub, jetons d'API retirés. Cette logique n'existait que côté sauvegarde ; elle est factorisée en un seul point pour que les deux chemins de sortie ne puissent plus diverger, et couverte par des tests.

---

## [2026-08-28] — 11 · version 0.1.8

### Ajouté
- **Réglages — deep-link direct vers un onglet** : `/#settings-<onglet>` (ex. `/#settings-github`) ouvre désormais directement la modale Réglages sur l'onglet demandé, au lieu de rester sans effet (Réglages est une modale, pas une page `page-*`, donc jusqu'ici hors du deep-link `/#cave`, `/#brassins`… déjà utilisé par l'app Android). Pensé pour un bouton "Synchroniser la cave" côté app Android qui doit atterrir directement sur l'onglet GitHub plutôt que sur Catalogue.

---

## [2026-08-28] — 10 · version 0.1.7

### Corrigé
- **Paramètres — clé API OpenAI non purgée à l'export** : `exportSettings()` purgeait bien les clés Gemini/legacy avant de générer le fichier de réglages téléchargeable, mais avait oublié `openaiApiKey` (champ distinct ajouté avec le provider OpenAI) - une clé configurée pour la génération d'images IA se retrouvait en clair dans l'export. Restauration symétrique ajoutée côté import.
- **Import BeerXML — expansion d'entités XML** : le fichier BeerXML uploadé était parsé avec le parseur XML stdlib nu, sans protection contre l'expansion d'entités internes ("billion laughs") - un fichier corrompu ou malveillant pouvait faire exploser mémoire/CPU du process. Parsing de ce fichier utilisateur passé à `defusedxml`.

---

## [2026-08-22] — 9 · version 0.1.6

### Ajouté
- **Cave — formats de bouteille 25 cl et 50 cl** : s'ajoutent aux formats 33 cl / 75 cl existants, activables individuellement (réglage `bottle_sizes_enabled` dans *Paramètres avancés → Seuils de stock*, 25/50 cl désactivés par défaut). Un format désactivé reste affiché tant qu'une bière y a du stock (pas de perte de données silencieuse). Cave, embouteillage depuis un brassin, calculateur bouteilles, vitrine GitHub Pages et statistiques de consommation généralisés aux 4 formats.

### Corrigé
- **Paramètres — token Telegram écrasé au chargement** : régression du masquage serveur des clés secrètes ; `telegram_token` n'avait pas le même garde que `ai_api_key` contre le placeholder `"***"`, ce qui cassait silencieusement les notifications Telegram à chaque rechargement de la page.
- **Impression de checklist — injection HTML** : le texte des items de checklist de brassage n'était pas échappé lors de l'impression, contrairement à l'affichage écran et à l'éditeur.
- **Brouillons — perte de la dernière frappe en changeant de brouillon** : le debounce de sauvegarde du brouillon précédent n'était pas vidé immédiatement avant de changer de contexte, ce qui pouvait écraser silencieusement la dernière modification du brouillon quitté.
- **Import de recettes — unité d'ingrédient non validée** : `POST /api/import/recipes` acceptait une unité arbitraire (même bug que celui déjà corrigé côté création manuelle).
- **Densimètres — "OG -Infinity" affiché sans mesure** : le graphique de fermentation affichait `-Infinity` quand la fenêtre sélectionnée ne contenait aucune lecture de densité.
- **Brouillons — désélection d'image après suppression** : supprimer une image de la galerie ne recalait pas toujours l'image sélectionnée, qui pouvait silencieusement changer vers une autre photo que celle choisie par l'utilisateur.

---

## [2026-08-15] — 8 · version 0.1.5

### Corrigé
- **Sécurité — secrets exposés sans authentification** : `GET /api/app-settings` renvoyait en clair le PAT GitHub, le token Telegram et la clé API IA (le masquage `_SECRET_KEYS` était vide depuis toujours). Le JS client écrivait donc systématiquement la vraie clé dans le `localStorage` du navigateur à chaque visite au lieu du placeholder attendu.
- **Recettes — validation d'unité manquante à la création** : `POST /api/recipes` acceptait une unité d'ingrédient arbitraire, contrairement à `PUT` ; elle était ensuite silencieusement neutralisée en `g` à la première modification.
- **Inventaire — seuil de stock bas et péremption perdus à la création** : `min_stock` et `expiry_date` renseignés dès la création d'un article n'étaient pas enregistrés (colonnes absentes de l'`INSERT`), sans effet tant que l'article n'était pas rouvert en édition.
- **Calendrier — rappel de brassage à 0 jour ignoré** : la vue Agenda retombait sur le délai par défaut au lieu du rappel « jour même » explicitement réglé à 0.

---

## [2026-07-22] — 7 · version 0.1.4

### Ajouté
- **Recettes — % max par malt** : chaque malt peut porter une limite de pourcentage dans la facture de malts (5 %, 10 %, 100 %…). Réglable par malt en stock (*Inventaire*), avec repli sur la valeur de référence du *Catalogue* résolue par nom. L'éditeur de recette signale les dépassements (badge rouge + compteur d'alertes sur la section Malt) et la fiche recette les met en évidence. Alerte indicative, jamais bloquante.
- **Navigation par ancre** : `/#cave`, `/#brassins`… ouvrent directement la page correspondante (utilisé par l'app Android).

### Corrigé
- **Recettes — disponibilité du stock à zéro** : un ingrédient présent en stock mais à 0 (ex. houblon à 0 g pour 60 g requis) était signalé « unités diff. » au lieu d'« insuffisant », et n'était pas ajouté à la liste de courses. L'incompatibilité d'unités se teste désormais sur l'absence réelle de l'unité demandée, et non sur une quantité nulle.
- **Icônes manquantes** : quatre icônes Font Awesome *Pro* (absentes de la version Free) s'affichaient en carré vide. Remplacées par leurs équivalents Free — fûts en cave, brouillons, purge de la base et export iCal.
- **Cache des assets** : `chart.umd.min.js` et les CSS tiers étaient servis sans `?v=` alors que les statiques portent un `max-age` d'un an — une mise à jour de ces fichiers n'atteignait jamais le navigateur. Cache-busting ajouté et cache du service worker incrémenté.
- **Chaîne de build JS** : trois correctifs appliqués directement aux `bh-*.js` compilés étaient absents de leurs sources `script_*.html` — dont la purge des tokens à l'export. Une recompilation les aurait silencieusement écrasés. Sources réalignées.

### Modifié
- **Chart.js** 4.5.0 → 4.5.1.
- **Font Awesome** 6.5.0 → 7.3.1 (les 177 icônes utilisées sont conservées).
- Ajout d'un `CLAUDE.md` documentant la chaîne de build et les pièges du projet.

---

## [2026-05-27] — 6

### Corrigé
- **Brassins — création sans nom** : `POST /api/brews` sans champ `name` causait une erreur 500 `NOT NULL constraint failed: brews.name`. Le nom est désormais hérité automatiquement de la recette associée.
- **Brassins — mise à jour sans nom** : `PUT /api/brews/<id>` sans champ `name` écrasait le nom existant avec NULL, provoquant la même erreur 500. Le nom existant est conservé si le champ est absent du payload.
- **Recettes — mise à jour partielle** : `PUT /api/recipes/<id>` sans champ `name` écrasait le nom existant avec NULL. Le nom existant est désormais conservé si le champ est absent.

---

## [2026-05-27] — 5

### Corrigé
- **Calendrier — rappel Sour Beer Day en double** : "Sour Beer Day" était défini deux fois — une fois le 20 septembre (date fixe correcte) et une seconde fois comme le 1er samedi de juillet via un calcul dynamique erroné. Ce doublon déclenchait un rappel Telegram en mai au lieu d'août. La ligne incorrecte est supprimée.

---

## [2026-05-25] — 4

### Corrigé
- **Calendrier — création / mise à jour d'événement** : erreur 500 `NOT NULL constraint failed: custom_calendar_events.brew_reminder_days` lors de l'enregistrement d'un événement sans rappel configuré. Le champ prend désormais par défaut la valeur configurée dans Paramètres → Rappel de brassage (fallback : 45 jours).
- **Calendrier — import backup** : les endpoints `import_calendar` et `restore_from_git` (section calendrier) omettaient `brew_reminder_days` et `recurrence` dans les requêtes INSERT et UPDATE, causant le même crash 500 à l'import et perdant silencieusement la récurrence à la mise à jour.

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
