# BrewHome — Référence API

Toutes les routes sont préfixées par l'origine du serveur (ex. `http://localhost:5000`).
Le corps des requêtes et des réponses est en **JSON** sauf mention contraire.

---

## Table des matières

- [Pages & PWA](#pages--pwa)
- [Catalogue d'ingrédients](#catalogue-dingrédients)
- [Inventaire](#inventaire)
- [Liste de courses](#liste-de-courses)
- [Recettes](#recettes)
- [Brassins](#brassins)
- [Photos de brassin](#photos-de-brassin)
- [Bières (cave)](#bières-cave)
- [Consommation](#consommation)
- [Fûts soda](#fûts-soda)
- [Densimètres (iSpindel)](#densimètres-ispindel)
- [Sondes de température](#sondes-de-température)
- [Import / Export](#import--export)
- [BJCP](#bjcp)
- [Corbeille](#corbeille)
- [Statistiques](#statistiques)
- [Version](#version)
- [Notifications Telegram](#notifications-telegram)
- [Mises à jour des librairies statiques](#mises-à-jour-des-librairies-statiques)
- [Proxy Git](#proxy-git)
- [Paramètres de l'application](#paramètres-de-lapplication)
- [Journal d'activité](#journal-dactivité)
- [Événements calendrier personnalisés](#événements-calendrier-personnalisés)
- [Brouillons de recettes](#brouillons-de-recettes)
- [IA — Suggestion de recette](#ia--suggestion-de-recette)
- [Calendrier iCal](#calendrier-ical)
- [Restauration depuis Git](#restauration-depuis-git)
- [Checklists de brassage](#checklists-de-brassage)
- [Guide de pesée](#guide-de-pesée)
- [Administration DB](#administration-db)
- [Administration — images](#administration--images)

---

## Pages & PWA

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/` | Page principale (SPA) |
| GET | `/manifest.json` | Manifeste PWA |
| GET | `/sw.js` | Service Worker |

---

## Catalogue d'ingrédients

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/catalog` | Liste tous les ingrédients du catalogue |
| POST | `/api/catalog` | Crée un nouvel ingrédient |
| PUT | `/api/catalog/<id>` | Met à jour un ingrédient |
| GET | `/api/catalog/<id>/history` | Historique des modifications (50 dernières) |
| DELETE | `/api/catalog/<id>` | Supprime un ingrédient |
| POST | `/api/catalog/import-hopsteiner` | Importe les houblons depuis la base Hopsteiner (GitHub) |

### GET `/api/catalog`

Query params :
- `category` — filtre par catégorie (`malt`, `houblon`, `levure`, `autre`)
- `q` — recherche par nom (LIKE)

### POST `/api/catalog`

Corps requis : `name`, `category`
Champs optionnels : `subcategory`, `ebc`, `gu`, `alpha`, `yeast_type`, `default_unit`, `temp_min`, `temp_max`, `dosage_per_liter`, `attenuation_min`, `attenuation_max`, `alcohol_tolerance`, `max_usage_pct`, `aroma_spec`

Retourne `201` avec l'objet créé.

### PUT `/api/catalog/<id>`

Mêmes champs que POST (sans `category` qui n'est pas modifiable). Retourne `404` si non trouvé.

### DELETE `/api/catalog/<id>`

Suppression définitive (pas de corbeille). Retourne `{ "success": true }` ou `404`.

---

## Inventaire

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/inventory` | Liste les articles d'inventaire actifs |
| POST | `/api/inventory` | Crée un article |
| PUT | `/api/inventory/<id>` | Met à jour un article |
| PUT | `/api/inventory/reorder` | Réordonne les articles |
| DELETE | `/api/inventory/<id>` | Supprime (soft-delete) un article |
| POST | `/api/inventory/<id>/restore` | Restaure un article supprimé |
| DELETE | `/api/inventory/<id>/purge` | Suppression définitive |
| PATCH | `/api/inventory/<id>/qty` | Met à jour uniquement la quantité |
| PATCH | `/api/inventory/<id>` | Met à jour le flag `archived` |
| GET | `/api/inventory/<id>/history` | Historique des mouvements de stock |

### POST `/api/inventory`

Query params : `force=1` pour ignorer la vérification de doublon (même nom + catégorie).
Corps requis : `name`, `category`
Champs optionnels : `quantity`, `unit`, `origin`, `ebc`, `alpha`, `notes`, `price_per_unit`, `yeast_type`, `yeast_mfg_date`, `yeast_open_date`, `yeast_generation`

Retourne `409 { "duplicate": true, "name": "...", "id": ... }` si doublon (sans `force=1`).
Retourne `201` avec l'objet créé.

### PUT `/api/inventory/reorder`

Corps : `[{ "id": 1, "sort_order": 0 }, ...]`

### PATCH `/api/inventory/<id>/qty`

Corps : `{ "quantity": 2.5 }`
Déclenche une alerte Telegram si le stock passe sous le seuil `min_stock`.

### PATCH `/api/inventory/<id>`

Corps : `{ "archived": true|false }`

### GET `/api/inventory/<id>/history`

Query param : `limit` (défaut 100, max 500)
Retourne `{ "item_name": "...", "item_unit": "...", "entries": [...] }` — journal des mouvements de stock (déductions de brassin, ajustements manuels, etc.).

---

## Liste de courses

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/shopping-list` | Liste les articles actifs (non achetés) |
| GET | `/api/shopping-list/history` | Historique des articles achetés (100 derniers) |
| POST | `/api/shopping-list` | Ajoute un article |
| PUT | `/api/shopping-list/<id>` | Met à jour un article |
| PUT | `/api/shopping-list/bulk-check` | Coche/décoche plusieurs articles en une requête |
| PUT | `/api/shopping-list/reorder` | Réordonne les articles |
| POST | `/api/shopping-list/buy` | Marque les articles cochés comme achetés (soft-delete) et met à jour l'inventaire |
| POST | `/api/shopping-list/undo-buy` | Annule un achat récent (voir token d'annulation) |
| DELETE | `/api/shopping-list/<id>` | Supprime un article |

### POST `/api/shopping-list`

Corps requis : `name`, `category` (`malt`, `houblon`, `levure`, `autre`)
Champs optionnels : `quantity` (défaut 1), `unit` (défaut `g`), `notes`, `inventory_item_id` (pour lier l'article à l'inventaire)

### PUT `/api/shopping-list/bulk-check`

Corps : `{ "ids": [1, 2, 3], "checked": true }`

### PUT `/api/shopping-list/reorder`

Corps : `[{ "id": 1, "sort_order": 0 }, ...]`

### POST `/api/shopping-list/buy`

Marque tous les articles actuellement cochés (`checked`) comme achetés et incrémente l'inventaire correspondant (par `inventory_item_id` ou par correspondance de nom). Retourne un token d'annulation utilisable via `/undo-buy` (fenêtre de 8 secondes côté interface).

### POST `/api/shopping-list/undo-buy`

Corps : le token retourné par `/api/shopping-list/buy`. Annule l'achat et restaure les articles ainsi que les quantités d'inventaire déduites.

---

## Recettes

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/recipes` | Liste toutes les recettes actives (avec ingrédients) |
| GET | `/api/recipes/<id>` | Détail d'une recette (avec ingrédients) |
| POST | `/api/recipes` | Crée une recette |
| PUT | `/api/recipes/<id>` | Met à jour une recette (remplace tous les ingrédients) |
| PUT | `/api/recipes/reorder` | Réordonne les recettes |
| PATCH | `/api/recipes/<id>` | Met à jour `archived` ou `rating` |
| DELETE | `/api/recipes/<id>` | Soft-delete |
| POST | `/api/recipes/<id>/restore` | Restaure depuis la corbeille |
| DELETE | `/api/recipes/<id>/purge` | Suppression définitive |
| POST | `/api/recipes/<id>/fork` | Crée une nouvelle version (fork) de la recette |
| GET | `/api/recipes/<id>/history` | Liste l'historique des versions sauvegardées |
| POST | `/api/recipes/<id>/history/<version_id>/restore` | Restaure une version antérieure |

### GET `/api/recipes`

Query params : `limit` (défaut 500, max 1000), `offset`
En-tête de réponse : `X-Total-Count` (nombre total de recettes actives).

### POST / PUT `/api/recipes`

Champs recette : `batch_no`, `name`*, `style`, `volume`, `brew_date`, `bottling_date`, `mash_temp`, `mash_time`, `boil_time`, `mash_ratio`, `evap_rate`, `grain_absorption`, `brewhouse_efficiency`, `ferm_temp`, `ferm_time`, `ferm_profile` (JSON), `notes`, `rating`, `draft_id`, `water_mash_override`, `water_sparge_override`

- `water_mash_override` / `water_sparge_override` : volumes d'eau saisis manuellement (en litres, `null` = calcul automatique)
- `ferm_profile` : profil de fermentation sérialisé en JSON (étapes personnalisées)

Champs par ingrédient (tableau `ingredients`) : `inventory_item_id`, `name`, `category`, `quantity`, `unit`, `hop_time`, `hop_type`, `hop_days`, `other_type`, `other_time`, `ebc`, `alpha`, `notes`

Query param `force=1` : ignore la vérification de doublon de nom. Retourne `409 { "error": "duplicate", "name": "...", "id": ... }` sinon.

### PATCH `/api/recipes/<id>`

Corps : `{ "archived": true|false }` ou `{ "rating": 4 }`

### POST `/api/recipes/<id>/fork`

Crée une copie de la recette avec un numéro de version incrémenté (ex. `IPA v2 → IPA v3`).
Corps optionnel : `{ "version_notes": "Ajout de coriandre" }`
Retourne `201` avec la nouvelle recette.

### GET `/api/recipes/<id>/history`

Retourne la liste des snapshots enregistrés avant chaque PUT (max 20 conservés par recette).
Champs : `id`, `saved_at`, `name`, `style`, `volume`, `n_ingredients`

### POST `/api/recipes/<id>/history/<version_id>/restore`

Restaure la recette à l'état du snapshot désigné (sauvegarde l'état courant avant restauration).

---

## Brassins

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/brews` | Liste tous les brassins actifs |
| POST | `/api/brews` | Crée un brassin (déduit le stock par défaut) |
| PUT | `/api/brews/<id>` | Met à jour un brassin |
| PUT | `/api/brews/reorder` | Réordonne les brassins |
| PATCH | `/api/brews/<id>` | Met à jour `status`, `ferm_time`, `og`, `fg`, etc. |
| DELETE | `/api/brews/<id>` | Soft-delete |
| POST | `/api/brews/<id>/restore` | Restaure depuis la corbeille |
| DELETE | `/api/brews/<id>/purge` | Suppression définitive |
| POST | `/api/brews/<id>/dryhop_done` | Marque le dry hop comme terminé |
| GET | `/api/brews/<id>/fermentation` | Lectures de fermentation d'un brassin |
| POST | `/api/brews/<id>/fermentation` | Ajoute une lecture de fermentation manuelle |
| DELETE | `/api/brews/<id>/fermentation/<reading_id>` | Supprime une lecture de fermentation |
| GET | `/api/brews/<id>/log` | Liste le journal de brassage (notes horodatées) |
| POST | `/api/brews/<id>/log` | Ajoute une entrée au journal |
| DELETE | `/api/brews/<id>/log/<entry_id>` | Supprime une entrée du journal |
| GET | `/api/brew-steps` | Liste toutes les étapes de brassage (tous brassins) |
| GET | `/api/brews/<id>/steps` | Liste les étapes d'un brassin |
| POST | `/api/brews/<id>/steps` | Ajoute une étape à un brassin |
| PUT | `/api/brew-steps/<step_id>` | Met à jour une étape |
| DELETE | `/api/brew-steps/<step_id>` | Supprime une étape |

### POST `/api/brews`

Corps requis : `recipe_id`
Champs optionnels : `name`, `brew_date`, `volume_brewed`, `deduct_stock` (bool, défaut `true`), `force` (bool, ignore le stock insuffisant)
Retourne `409 { "error": "stock_insuffisant", "items": [...] }` si stock insuffisant (sans `force`).

### PATCH `/api/brews/<id>`

Champs modifiables : `status`, `ferm_time`, `og`, `fg`, `abv`, `notes`, `volume_brewed`

### POST `/api/brews/<id>/dryhop_done`

Corps requis : `{ "date": "YYYY-MM-DD" }`. Marque cette date de dry hop comme faite et déduit le stock correspondant une seule fois (idempotent si la date est déjà marquée).

### POST `/api/brews/<id>/fermentation`

Corps requis : `recorded_at`, `gravity`. Champs optionnels : `temperature`, `notes`. Ajoute une lecture manuelle (indépendante d'un densimètre connecté).

### DELETE `/api/brews/<id>/fermentation/<reading_id>`

Seules les lectures manuelles (`source: "manual"`) peuvent être supprimées — retourne `403` pour une lecture importée d'un densimètre.

### GET / POST `/api/brews/<id>/log`

Journal de bord libre du brassin (horodatage manuel). POST — corps requis : `ts`, `note` ; champ optionnel : `step`.

### GET `/api/brew-steps` / `/api/brews/<id>/steps`

Étapes planifiées post-brassage (ex. cold crash, changement de température) avec rappel Telegram optionnel — `GET /api/brew-steps` retourne celles de tous les brassins non archivés (utilisé par le calendrier). Distinct des modèles de [checklists de brassage](#checklists-de-brassage).

POST/PUT — corps requis : `scheduled_date`, `title` ; champs optionnels : `notes`, `telegram_notify` (bool, défaut `true`), `done` (PUT uniquement).

---

## Photos de brassin

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/brews/<id>/photos` | Liste les photos (sans les données base64 complètes, miniatures uniquement) |
| POST | `/api/brews/<id>/photos` | Ajoute une photo |
| GET | `/api/brews/<id>/photos/<photo_id>` | Récupère une photo complète (base64) |
| PATCH | `/api/brews/<id>/photos/<photo_id>` | Met à jour la légende (`caption`) ou l'étape (`step`) d'une photo |
| DELETE | `/api/brews/<id>/photos/<photo_id>` | Supprime une photo |

### POST `/api/brews/<id>/photos`

Corps : `{ "photo": "<data_url_base64>", "step": "...", "caption": "..." }`
Génère automatiquement une miniature (200 px max).

### PATCH `/api/brews/<id>/photos/<photo_id>`

Corps : `{ "step": "...", "caption": "..." }`

---

## Bières (cave)

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/beers` | Liste toutes les bières actives |
| POST | `/api/beers` | Crée une bière |
| PUT | `/api/beers/<id>` | Met à jour une bière |
| PUT | `/api/beers/reorder` | Réordonne les bières |
| PUT | `/api/beers/<id>/tasting` | Met à jour les notes de dégustation |
| PATCH | `/api/beers/<id>/stock` | Met à jour les stocks (enregistre la consommation) |
| PATCH | `/api/beers/<id>` | Met à jour le flag `archived` |
| DELETE | `/api/beers/<id>` | Soft-delete |
| POST | `/api/beers/<id>/restore` | Restaure depuis la corbeille |
| DELETE | `/api/beers/<id>/purge` | Suppression définitive |

### POST / PUT `/api/beers`

Champs : `name`*, `type`, `abv`, `stock_25cl`, `stock_33cl`, `stock_50cl`, `stock_75cl`, `initial_25cl`, `initial_33cl`, `initial_50cl`, `initial_75cl`, `keg_liters`, `keg_initial_liters`, `origin`, `description`, `photo`, `brew_id`, `recipe_id`, `brew_date`, `bottling_date`, `refermentation` (0/1), `refermentation_days`

Les formats 25cl et 50cl sont optionnels et activables individuellement via la clé `app_settings` `bottle_sizes_enabled` (JSON `{ "25cl": bool, "33cl": bool, "50cl": bool, "75cl": bool }`) — voir [Paramètres de l'application](#paramètres-de-lapplication).

### PUT `/api/beers/<id>/tasting`

Champs : `taste_appearance`, `taste_aroma`, `taste_flavor`, `taste_bitterness`, `taste_mouthfeel`, `taste_overall`, `taste_finish`, `taste_rating`, `taste_date`, `taste_score_*`

### PATCH `/api/beers/<id>/stock`

Corps : `{ "stock_25cl": 4, "stock_33cl": 10, "stock_50cl": 2, "stock_75cl": 5, "keg_liters": 18.5 }` (tous optionnels)
Enregistre automatiquement une entrée de consommation pour chaque diminution de stock.

---

## Consommation

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/consumption` | Statistiques de consommation par mois et par bière (top 10) |
| GET | `/api/consumption/depletion` | Estimation des dates d'épuisement par bière (basé sur la cadence) |

---

## Fûts soda

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/soda-kegs` | Liste tous les fûts |
| GET | `/api/soda-kegs/revisions-due` | Fûts dont la révision est dépassée ou due bientôt |
| POST | `/api/soda-kegs` | Crée un fût |
| PUT | `/api/soda-kegs/<id>` | Met à jour un fût |
| PUT | `/api/soda-kegs/reorder` | Réordonne les fûts |
| DELETE | `/api/soda-kegs/<id>` | Suppression définitive |

### POST / PUT `/api/soda-kegs`

Champs : `name`, `keg_type`, `manufacturer`, `volume_total`, `volume_ferment`, `weight_empty`, `status`, `current_liters`, `beer_id`, `brew_id`, `notes`, `color`, `photo`, `last_revision_date`, `revision_interval_months`, `next_revision_date`

### GET `/api/soda-kegs/revisions-due`

Query param : `days` (défaut 30, max 365) — fûts non archivés dont `next_revision_date` est dépassée ou tombe dans les `days` prochains jours.

---

## Densimètres (iSpindel)

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/spindles` | Liste tous les densimètres |
| POST | `/api/spindles` | Crée un densimètre (génère un token) |
| PATCH | `/api/spindles/<id>` | Met à jour `name`, `brew_id`, `notes`, `device_type` — le champ `stable_notif_at` est géré automatiquement par le planificateur de stabilité |
| DELETE | `/api/spindles/<id>` | Supprime le densimètre et toutes ses lectures |
| PUT | `/api/spindles/reorder` | Réordonne les densimètres |
| GET | `/api/spindles/<id>/readings` | Lectures d'un densimètre |
| POST/GET | `/api/spindle/data` | Réception des données depuis l'appareil |
| GET | `/api/spindle/readings/stats` | Statistiques globales des lectures |
| DELETE | `/api/spindle/readings/purge` | Purge les lectures antérieures à N jours |

### GET `/api/spindles/<id>/readings`

Query params : `limit` (défaut 2000), `hours`, `from` (ISO datetime), `to` (ISO datetime)

### POST/GET `/api/spindle/data`

Endpoint universel — supporte iSpindel, Tilt (TiltBridge), GravityMon.
Query param ou corps JSON : `token`
Corps JSON (POST) : `gravity`, `temperature` (ou `Temp` en °F pour Tilt), `battery`, `angle`, `RSSI`

### DELETE `/api/spindle/readings/purge`

Query param : `days` (défaut 30)

---

## Sondes de température

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/temperature` | Liste toutes les sondes |
| POST | `/api/temperature` | Crée une sonde (génère un token) |
| PATCH | `/api/temperature/<id>` | Met à jour `name`, `notes`, `temp_min`, `temp_max`, `sensor_type`, `ha_entity`, `ha_entity_hum`, `brew_id` |
| DELETE | `/api/temperature/<id>` | Supprime la sonde et toutes ses lectures |
| PUT | `/api/temperature/reorder` | Réordonne les sondes |
| GET | `/api/temperature/<id>/readings` | Lectures d'une sonde |
| POST/GET | `/api/temperature/data` | Réception des données depuis Home Assistant ou une sonde |
| GET | `/api/temperature/readings/stats` | Statistiques globales des lectures |
| DELETE | `/api/temperature/readings/purge` | Purge les lectures antérieures à N jours |

### POST `/api/temperature`

Champs : `name`, `notes`, `temp_min`, `temp_max`, `sensor_type` (`sensor` ou `thermostat`), `ha_entity`, `ha_entity_hum`

### POST/GET `/api/temperature/data`

Query param ou corps JSON : `token`
Corps JSON : `temperature`, `humidity`, `target_temp`, `hvac_mode`
Accepte aussi `temp_f` / `Fahrenheit` (converti en °C automatiquement).

### GET `/api/temperature/<id>/readings`

Query params : `limit` (défaut 2000), `hours`, `from` (ISO datetime), `to` (ISO datetime)

### DELETE `/api/temperature/readings/purge`

Query param : `days` (défaut 30)

---

## Import / Export

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/export/catalog` | Export catalogue (JSON) |
| POST | `/api/import/catalog` | Import catalogue |
| GET | `/api/export/inventory` | Export inventaire (JSON) |
| POST | `/api/import/inventory` | Import inventaire |
| GET | `/api/export/recipes` | Export recettes + ingrédients (JSON) |
| POST | `/api/import/recipes` | Import recettes |
| GET | `/api/export/beerxml` | Export recettes au format BeerXML |
| POST | `/api/import/beerxml` | Import recettes depuis BeerXML |
| POST | `/api/import/brewfather` | Import recettes depuis export Brewfather (JSON) |
| GET | `/api/export/brews` | Export brassins + lectures fermentation (JSON) |
| POST | `/api/import/brews` | Import brassins |
| GET | `/api/export/beers` | Export bières (JSON) |
| POST | `/api/import/beers` | Import bières |
| GET | `/api/export/spindles` | Export densimètres + lectures (JSON) |
| POST | `/api/import/spindles` | Import densimètres |
| GET | `/api/export/drafts` | Export brouillons (JSON) |
| POST | `/api/import/drafts` | Import brouillons |
| GET | `/api/export/calendar` | Export événements calendrier (JSON) |
| POST | `/api/import/calendar` | Import événements calendrier |
| POST | `/api/catalog/import-hopsteiner` | Import houblons Hopsteiner depuis GitHub |

### Corps des endpoints d'import

```json
{ "items": [...], "mode": "merge" }
```
- `mode` : `"merge"` (défaut, upsert par nom) ou `"replace"` (supprime puis recrée tout)
- Corps peut aussi être directement un tableau `[...]` (mode `merge` implicite)

Retourne : `{ "imported": N }`

---

## BJCP

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/bjcp` | Liste les styles BJCP |

Query param : `q` — recherche dans le nom et la catégorie.

---

## Corbeille

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/trash` | Liste tous les éléments supprimés (recettes, inventaire, brassins, bières) |

---

## Statistiques

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/stats` | Statistiques globales |

Retourne :
```json
{
  "inventory_count": 42,
  "recipes_count": 10,
  "brews_count": 8,
  "brews_active": 2,
  "beers_count": 15,
  "kegs_count": 3,
  "total_25cl": 6,
  "total_33cl": 120,
  "total_50cl": 3,
  "total_75cl": 48,
  "total_liters": 75.6
}
```

---

## Version

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/version/check` | Vérifie si une mise à jour BrewHome est disponible (GitHub Releases, cache 6 h) |

Retourne :
```json
{
  "current": "1.2.3",
  "latest": "1.3.0",
  "update_available": true,
  "release_url": "https://github.com/chatainsim/brewhome/releases/..."
}
```

---

## Notifications Telegram

| Méthode | Route | Description |
|---------|-------|-------------|
| POST | `/api/telegram/test` | Envoie un message de test avec le token/chat_id fournis |
| POST | `/api/telegram/trigger/<type>` | Déclenche manuellement une notification |
| POST | `/api/notify/timer` | Envoie une notification de minuteur de brassage (avertissement ou fin) |

### POST `/api/telegram/test`

Corps : `{ "token": "...", "chat_id": "..." }`

### POST `/api/telegram/trigger/<type>`

Types disponibles : `brews` (état des brassins), `cave` (stock cave), `inventory` (stock inventaire), `ferm_reminders` (rappels de fermentation + fin de refermentation en cave)

> La notification **densité stable** (`spindle_stable`) est déclenchée automatiquement par le planificateur interne (toutes les 4 h) et n'est pas exposée via cet endpoint.

Utilise la configuration Telegram enregistrée dans les paramètres de l'application.

### POST `/api/notify/timer`

Corps : `{ "name": "...", "type": "warning"|"done" }` (`type` par défaut `"done"`)
Envoyé par les minuteurs de brassage de l'interface (empâtage, ébullition…). Retourne `400` si Telegram n'est pas configuré.

---

## Mises à jour des librairies statiques

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/static/check-updates` | Vérifie les versions disponibles de Chart.js et Font Awesome |
| POST | `/api/static/update/chartjs` | Télécharge et remplace Chart.js par la dernière version npm |
| POST | `/api/static/update/fontawesome` | Télécharge et remplace Font Awesome par la dernière version npm |

### GET `/api/static/check-updates`

Retourne pour chaque lib : `{ "current": "4.4.0", "latest": "4.5.0", "error": null }`

---

## Proxy Git

| Méthode | Route | Description |
|---------|-------|-------------|
| POST | `/api/git-proxy` | Proxifie une requête vers un provider Git (GitHub, GitLab, Gitea/Forgejo) |

### POST `/api/git-proxy`

Corps :
```json
{
  "url": "https://api.github.com/...",
  "method": "GET",
  "pat": "ghp_...",
  "body": { ... }
}
```

Domaines autorisés : `api.github.com`, `gitlab.com`, `codeberg.org`, et les instances Gitea/Forgejo configurées dans les paramètres.
Retourne `403` si l'URL n'est pas dans la liste blanche (protection SSRF).

---

## Paramètres de l'application

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/app-settings` | Récupère tous les paramètres (les clés secrètes sont masquées avec `***`) |
| PUT | `/api/app-settings` | Met à jour les paramètres (upsert par clé) |

### PUT `/api/app-settings`

Corps : objet clé/valeur. Envoyer `null` ou `""` supprime la clé.
Les clés secrètes (tokens API, PAT) ne sont jamais écrasées avec la valeur `"***"`.
Met à jour automatiquement le planificateur Telegram ou GitHub Backup si les clés concernées changent.

---

## Journal d'activité

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/activity` | Liste les entrées du journal |
| POST | `/api/activity` | Ajoute une entrée manuellement |
| DELETE | `/api/activity` | Supprime des entrées |

### GET `/api/activity`

Query params : `limit` (max 200, défaut 50), `offset`, `category`, `exclude`

Retourne : `{ "items": [...], "total": N }`

### POST `/api/activity`

Corps : `{ "category": "...", "action": "...", "label": "...", "entity_id": 1 }`

### DELETE `/api/activity`

Query params : `category` (supprime une catégorie), `exclude` (supprime tout sauf cette catégorie). Sans paramètre : vide tout.

---

## Événements calendrier personnalisés

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/custom_events` | Liste tous les événements |
| POST | `/api/custom_events` | Crée un événement |
| PUT | `/api/custom_events/<id>` | Met à jour un événement |
| DELETE | `/api/custom_events/<id>` | Supprime un événement |

### POST / PUT `/api/custom_events`

Champs : `title`, `emoji`, `event_date` (YYYY-MM-DD), `color`, `notes`, `brew_reminder` (0/1), `telegram_notify` (0/1), `style`, `recipe_id`, `draft_id`, `recurrence`, `brew_reminder_days`

---

## Brouillons de recettes

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/drafts` | Liste tous les brouillons (sans image base64) |
| GET | `/api/drafts/<id>` | Détail complet d'un brouillon (avec image) |
| POST | `/api/drafts` | Crée un brouillon |
| PUT | `/api/drafts/<id>` | Met à jour un brouillon |
| PUT | `/api/drafts/reorder` | Réordonne les brouillons |
| DELETE | `/api/drafts/<id>` | Supprime un brouillon |

### POST / PUT `/api/drafts`

Champs : `title`, `style`, `volume`, `ingredients`, `notes`, `color`, `target_date`, `event_label`, `image` (data URL base64 — redimensionnée automatiquement si trop grande)

---

## IA — Suggestion de recette

| Méthode | Route | Description |
|---------|-------|-------------|
| POST | `/api/ai/draft-suggest` | Génère une recette via l'API Gemini (Google) |

### POST `/api/ai/draft-suggest`

Corps : `{ "style": "IPA", "event_label": "Fête d'été", "event_desc": "...", "notes": "...", "volume": 20 }`

Nécessite `ai_api_key` et optionnellement `ai_model` dans les paramètres de l'application.
Retourne un objet `{ "title": "...", "ingredients": [...], "notes": "..." }`.

---

## Calendrier iCal

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/calendar/ics` | Flux iCal (`.ics`) de tous les événements BrewHome |

Le flux inclut les brassins, embouteillages, fins de fermentation et événements personnalisés.
Peut être abonné dans Google Calendar, Apple Calendar, etc.

---

## Restauration depuis Git

| Méthode | Route | Description |
|---------|-------|-------------|
| POST | `/api/restore/git` | Restaure des données depuis la sauvegarde Git automatique |

### POST `/api/restore/git`

Corps :
```json
{
  "sections": ["inventaire", "recettes", "brassins", "cave", "catalogue", "densimetres", "brouillons", "calendrier"],
  "mode": "merge"
}
```

Utilise la configuration Git enregistrée dans les paramètres de l'application.

---

## Checklists de brassage

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/checklist-templates` | Liste tous les modèles de checklist |
| POST | `/api/checklist-templates` | Crée un modèle |
| PUT | `/api/checklist-templates/<id>` | Met à jour un modèle |
| DELETE | `/api/checklist-templates/<id>` | Supprime un modèle |
| GET | `/api/brews/<id>/checklist` | Récupère la checklist d'un brassin |
| POST | `/api/brews/<id>/checklist` | Sauvegarde (upsert) la checklist d'un brassin |

### POST `/api/checklist-templates`

Corps : `{ "name": "Brassage standard", "description": "...", "items": ["Sanitiser", "Mash in", ...] }`

### POST `/api/brews/<id>/checklist`

Corps : `{ "template_id": 1, "checked_items": ["Sanitiser", "Mash in"] }`

---

## Guide de pesée

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/scale-guide` | État de la session de pesée en cours (le cas échéant) |
| POST | `/api/scale-guide/start` | Démarre une session de pesée guidée pour une liste de malts |
| POST | `/api/scale-guide/next` | Passe au malt suivant |
| POST | `/api/scale-guide/stop` | Arrête la session en cours |

Assiste la pesée des malts d'une recette un par un (utilisé depuis la fiche brassin) : la session (liste de malts + étape courante) est stockée côté serveur dans `app_settings`, ce qui permet de garder la progression même en changeant d'appareil.

### POST `/api/scale-guide/start`

Corps requis : `malts` (tableau de `{ "name", "quantity", "unit" }`). Champs optionnels : `recipe_id`, `brew_name`.
Retourne `{ "ok": true, "total": N, "first_malt": "..." }`.

### GET `/api/scale-guide`

Retourne `{ "active": false }` si aucune session, sinon `{ "active": true, "brew_name", "step", "total", "malt_name", "target_kg" }` (`target_kg` convertit automatiquement depuis `g` si nécessaire).

### POST `/api/scale-guide/next`

Passe à l'étape suivante ; retourne `{ "finished": true, "active": false }` une fois le dernier malt pesé.

---

## Administration DB

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/admin/db-stats` | Taille et nombre de lignes par table (DB principale + DB lectures) |
| POST | `/api/admin/vacuum` | Lance `VACUUM` sur les deux bases SQLite |
| POST | `/api/admin/purge-deleted` | Purge immédiatement les lignes soft-deleted au-delà de la rétention configurée |
| GET | `/api/admin/export-sql` | Exporte la DB principale en SQL (dump complet) |

### GET `/api/admin/db-stats`

Retourne :
```json
{
  "main":     { "size": 204800, "tables": { "beers": 12, "brews": 5, ... } },
  "readings": { "size": 1048576, "tables": { "spindle_readings": 8500, ... } }
}
```

### POST `/api/admin/purge-deleted`

Exécute immédiatement la même purge que la tâche planifiée quotidienne (`inventory_items`, `recipes`, `brews`, `beers` soft-deleted depuis plus longtemps que la rétention configurée). Retourne `{ "deleted": {"table": n, ...}, "total": N, "retention_days": D }`.

### GET `/api/admin/export-sql`

Retourne un fichier texte `.sql` en téléchargement (`Content-Disposition: attachment`).

---

## Administration — images

Outils de maintenance ponctuels liés à la migration des photos (base64 en base → fichiers sur disque). Idempotents, sans effet si déjà migré.

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/admin/draft-images-status` | Diagnostic : état des images de chaque brouillon + fichiers orphelins sur disque |
| POST | `/api/admin/migrate-draft-images` | Migre les images base64 des brouillons vers des fichiers, purge les doublons base64 |
| POST | `/api/admin/restore-draft-images` | Restaure les images de brouillons depuis une sauvegarde `brouillons.json` (GitHub) |
| POST | `/api/admin/migrate-beer-images` | Migre les photos base64 des bières (cave) vers des fichiers |

### POST `/api/admin/restore-draft-images`

Corps : `{ "drafts": [...] }` (contenu du fichier `brouillons.json` d'une sauvegarde GitHub). Ne restaure que les brouillons dont la ligne DB actuelle n'a pas déjà de fichier image lié.

---

## Codes de retour courants

| Code | Signification |
|------|---------------|
| 200 | Succès |
| 201 | Créé |
| 400 | Paramètre manquant ou invalide |
| 401 | Token manquant ou invalide (endpoints capteurs) |
| 403 | URL non autorisée (proxy Git) |
| 404 | Ressource non trouvée |
| 409 | Conflit (doublon ou stock insuffisant) |
| 429 | Trop de requêtes (rate limit capteurs) |
| 500 | Erreur serveur interne |
| 502 | Erreur de service externe (Gemini, GitHub) |
