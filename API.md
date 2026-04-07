# BrewHome — Référence API

Toutes les routes sont préfixées par l'origine du serveur (ex. `http://localhost:5000`).
Le corps des requêtes et des réponses est en **JSON** sauf mention contraire.

---

## Table des matières

- [Pages & PWA](#pages--pwa)
- [Catalogue d'ingrédients](#catalogue-dingrédients)
- [Inventaire](#inventaire)
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
- [Administration DB](#administration-db)

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

### POST / PUT `/api/recipes`

Champs recette : `batch_no`, `name`*, `style`, `volume`, `brew_date`, `bottling_date`, `mash_temp`, `mash_time`, `boil_time`, `mash_ratio`, `evap_rate`, `grain_absorption`, `brewhouse_efficiency`, `ferm_temp`, `ferm_time`, `notes`, `rating`, `draft_id`

Champs par ingrédient (tableau `ingredients`) : `inventory_item_id`, `name`, `category`, `quantity`, `unit`, `hop_time`, `hop_type`, `hop_days`, `other_type`, `other_time`, `ebc`, `alpha`, `notes`

### PATCH `/api/recipes/<id>`

Corps : `{ "archived": true|false }` ou `{ "rating": 4 }`

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
| GET | `/api/brews/<id>/fermentation` | Lectures de fermentation d'un brassin |

### POST `/api/brews`

Corps requis : `recipe_id`
Champs optionnels : `name`, `brew_date`, `volume_brewed`, `deduct_stock` (bool, défaut `true`), `force` (bool, ignore le stock insuffisant)
Retourne `409 { "error": "stock_insuffisant", "items": [...] }` si stock insuffisant (sans `force`).

### PATCH `/api/brews/<id>`

Champs modifiables : `status`, `ferm_time`, `og`, `fg`, `abv`, `notes`, `volume_brewed`

---

## Photos de brassin

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/brews/<id>/photos` | Liste les photos (sans les données base64 complètes, miniatures uniquement) |
| POST | `/api/brews/<id>/photos` | Ajoute une photo |
| GET | `/api/brews/<id>/photos/<photo_id>` | Récupère une photo complète (base64) |
| DELETE | `/api/brews/<id>/photos/<photo_id>` | Supprime une photo |

### POST `/api/brews/<id>/photos`

Corps : `{ "photo": "<data_url_base64>", "step": "...", "caption": "..." }`
Génère automatiquement une miniature (200 px max).

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

Champs : `name`*, `type`, `abv`, `stock_33cl`, `stock_75cl`, `initial_33cl`, `initial_75cl`, `keg_liters`, `keg_initial_liters`, `origin`, `description`, `photo`, `brew_id`, `recipe_id`, `brew_date`, `bottling_date`, `refermentation` (0/1), `refermentation_days`

### PUT `/api/beers/<id>/tasting`

Champs : `taste_appearance`, `taste_aroma`, `taste_flavor`, `taste_bitterness`, `taste_mouthfeel`, `taste_overall`, `taste_finish`, `taste_rating`, `taste_date`, `taste_score_*`

### PATCH `/api/beers/<id>/stock`

Corps : `{ "stock_33cl": 10, "stock_75cl": 5, "keg_liters": 18.5 }`
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
| POST | `/api/soda-kegs` | Crée un fût |
| PUT | `/api/soda-kegs/<id>` | Met à jour un fût |
| PUT | `/api/soda-kegs/reorder` | Réordonne les fûts |
| DELETE | `/api/soda-kegs/<id>` | Suppression définitive |

### POST / PUT `/api/soda-kegs`

Champs : `name`, `keg_type`, `manufacturer`, `volume_total`, `volume_ferment`, `weight_empty`, `status`, `current_liters`, `beer_id`, `brew_id`, `notes`, `color`, `photo`, `last_revision_date`, `revision_interval_months`, `next_revision_date`

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
  "total_33cl": 120,
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

### POST `/api/telegram/test`

Corps : `{ "token": "...", "chat_id": "..." }`

### POST `/api/telegram/trigger/<type>`

Types disponibles : `brews` (état des brassins), `cave` (stock cave), `inventory` (stock inventaire), `ferm_reminders` (rappels de fermentation + fin de refermentation en cave)

> La notification **densité stable** (`spindle_stable`) est déclenchée automatiquement par le planificateur interne (toutes les 4 h) et n'est pas exposée via cet endpoint.

Utilise la configuration Telegram enregistrée dans les paramètres de l'application.

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

## Administration DB

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/admin/db-stats` | Taille et nombre de lignes par table (DB principale + DB lectures) |
| POST | `/api/admin/vacuum` | Lance `VACUUM` sur les deux bases SQLite |
| GET | `/api/admin/export-sql` | Exporte la DB principale en SQL (dump complet) |

### GET `/api/admin/db-stats`

Retourne :
```json
{
  "main":     { "size": 204800, "tables": { "beers": 12, "brews": 5, ... } },
  "readings": { "size": 1048576, "tables": { "spindle_readings": 8500, ... } }
}
```

### GET `/api/admin/export-sql`

Retourne un fichier texte `.sql` en téléchargement (`Content-Disposition: attachment`).

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
