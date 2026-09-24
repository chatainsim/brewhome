// ══════════════════════════════════════════════════════════════════════════════
// STATE
// ══════════════════════════════════════════════════════════════════════════════
const S = { inventory: [], recipes: [], brews: [], beers: [], catalog: [], bjcp: [], spindles: [], tempSensors: [], drafts: [], customEvents: [], brewSteps: [], sodaKegs: [], consumption: null, depletion: [], checklistTemplates: [], shoppingList: [] };

// ── Multi-tab sync ────────────────────────────────────────────────────────────
const _bch = (() => { try { return new BroadcastChannel('brewhome-sync'); } catch(e) { return null; } })();
const _PATH_ENTITY = [
  [/\/api\/inventory/,           'inventory'],
  [/\/api\/recipes/,             'recipes'],
  [/\/api\/brews/,               'brews'],
  [/\/api\/beers/,               'beers'],
  [/\/api\/drafts/,              'drafts'],
  [/\/api\/spindles/,            'spindles'],
  [/\/api\/soda-kegs/,           'sodaKegs'],
  [/\/api\/custom.events/,       'customEvents'],
  [/\/api\/brew-steps/,          'brewSteps'],
  [/\/api\/checklist-templates/, 'checklistTemplates'],
  [/\/api\/shopping-list/,       'shoppingList'],
];
// Pages concernées par chaque entité (d'après _refreshPage)
const _ENTITY_PAGES = {
  inventory:          ['dashboard', 'inventaire', 'stats'],
  recipes:            ['dashboard', 'recettes', 'stats'],
  brews:              ['dashboard', 'brassins', 'calendrier', 'stats', 'kegs'],
  beers:              ['dashboard', 'cave', 'stats', 'kegs'],
  drafts:             ['calendrier', 'brouillons'],
  spindles:           ['brassins', 'spindles'],
  sodaKegs:           ['dashboard', 'brassins', 'cave', 'kegs'],
  customEvents:       ['calendrier'],
  brewSteps:          ['brassins', 'calendrier'],
  checklistTemplates: [],   // settings modal uniquement, pas de page
  shoppingList:       ['shopping'],
  generic:            ['dashboard','inventaire','recettes','brassins','cave','spindles','calendrier','brouillons','stats','kegs','shopping'],
};
function _entityForPath(path) {
  for (const [re, e] of _PATH_ENTITY) if (re.test(path)) return e;
  return 'generic';
}
function _syncAffectsPage(entity, page) {
  const pages = _ENTITY_PAGES[entity] || _ENTITY_PAGES.generic;
  return pages.includes(page);
}
let _syncDebounceTimer = null;
if (_bch) {
  _bch.onmessage = (ev) => {
    if (!ev.data || ev.data.type !== 'change') return;
    const page = document.querySelector('.page.active')?.id?.replace('page-', '') || 'dashboard';
    if (!_syncAffectsPage(ev.data.entity, page)) return;
    clearTimeout(_syncDebounceTimer);
    _syncDebounceTimer = setTimeout(() => _refreshPage(page), 400);
  };
}
// ─────────────────────────────────────────────────────────────────────────────

let invFilter = 'all';
let showArchivedInv=false, showArchivedRec=false, showArchivedBrew=false, showArchivedCave=false;
let appSettings = JSON.parse(localStorage.getItem('brewSettings') || '{}');
const DEFAULT_THRESH = {malt:1000, houblon:50, levure:2, autre:100};
function getThresh(cat) { return ((appSettings.thresholds||{})[cat] ?? DEFAULT_THRESH[cat]); }

// ── Tailles de bouteille (25cl/33cl/50cl/75cl) ─────────────────────────────────
const BOTTLE_SIZES = ['25cl', '33cl', '50cl', '75cl'];

// Les clés de données gardent le suffixe (stock_25cl), les identifiants DOM
// ne l'ont pas (beer-f-25, keg-tr-25). Passer par cette fonction plutôt que
// d'interpoler la taille brute, sinon getElementById renvoie null et
// l'affectation qui suit interrompt tout le rendu.
const sizeId = size => String(size).replace('cl', '');
const BOTTLE_SIZE_LITERS = { '25cl': 0.25, '33cl': 0.33, '50cl': 0.50, '75cl': 0.75 };
const DEFAULT_BOTTLE_SIZES = { '25cl': false, '33cl': true, '50cl': false, '75cl': true };
function bottleSizesEnabled() { return { ...DEFAULT_BOTTLE_SIZES, ...(appSettings.bottleSizes || {}) }; }
function isSizeEnabled(size) { return !!bottleSizesEnabled()[size]; }
// Une taille reste utilisable si activée, OU si une bière donnée y a encore du stock
// (ne jamais masquer du stock existant quand une taille est désactivée après coup)
function isSizeUsable(size, beer) { return isSizeEnabled(size) || (beer && (beer[`stock_${size}`] || 0) > 0); }
const CONSO_CHART_COLORS = {
  '25cl': { bg: 'rgba(192,132,252,.7)', border: '#c084fc' },
  '33cl': { bg: 'rgba(99,102,241,.7)',  border: '#6366f1' },
  '50cl': { bg: 'rgba(244,114,182,.7)', border: '#f472b6' },
  '75cl': { bg: 'rgba(245,158,11,.7)',  border: '#f59e0b' },
};
function beerLiters(beer) {
  if (!beer) return 0;
  return BOTTLE_SIZES.reduce((sum, size) => sum + (beer[`stock_${size}`] || 0) * BOTTLE_SIZE_LITERS[size], 0)
    + (beer.keg_liters || 0);
}
function beerInitialLiters(beer) {
  if (!beer) return 0;
  return BOTTLE_SIZES.reduce((sum, size) => sum + (beer[`initial_${size}`] || 0) * BOTTLE_SIZE_LITERS[size], 0)
    + (beer.keg_initial_liters || 0);
}
function saveSettings() {
  appSettings._ts = Date.now();
  try {
    localStorage.setItem('brewSettings', JSON.stringify(appSettings));
  } catch(e) {
    console.error('[saveSettings] localStorage error:', e);
  }
  _syncSettingsToServer();
}

// Synchronise tous les paramètres non-sensibles vers la base de données
let _syncSettingsTimer = null;
function _syncSettingsToServer() {
  try { if (!appSettings) return; } catch(e) { return; }
  clearTimeout(_syncSettingsTimer);
  _syncSettingsTimer = setTimeout(_doSyncSettingsToServer, 600);
}
function _doSyncSettingsToServer() {
  const payload = {
    app_name:          appSettings.appName          || null,
    accent_color:      appSettings.accentColor      || null,
    app_icon:          appSettings.appIcon          || null,
    thresholds:        appSettings.thresholds       ? JSON.stringify(appSettings.thresholds) : null,
    bottle_sizes_enabled: appSettings.bottleSizes    ? JSON.stringify(appSettings.bottleSizes) : null,
    water:             appSettings.water            ? JSON.stringify(appSettings.water)      : null,
    water_profiles:    appSettings.waterProfiles?.length ? JSON.stringify(appSettings.waterProfiles) : null,
    energy:            appSettings.energy           ? JSON.stringify(appSettings.energy)     : null,
    vessels:           appSettings.vessels          ? JSON.stringify(appSettings.vessels)    : null,
    hubeau:            appSettings.hubeau           ? JSON.stringify(appSettings.hubeau)     : null,
    tz_offset:         appSettings.tz_offset        != null ? String(appSettings.tz_offset) : null,
    lang:              _lang                        || null,
    gh_vitrine_targets:  appSettings.github?.vitrine?.targets?.length ? JSON.stringify(appSettings.github.vitrine.targets) : null,
    gh_data_targets:     appSettings.github?.data?.targets?.length    ? JSON.stringify(appSettings.github.data.targets)    : null,
    gh_data_backup_enabled: appSettings.github?.backup?.enabled ? 'true' : null,
    gh_data_backup_freq:    appSettings.github?.backup?.freq    || null,
    gh_data_backup_hour:    appSettings.github?.backup?.hour    != null ? String(appSettings.github.backup.hour)    : null,
    gh_data_backup_minute:  appSettings.github?.backup?.minute  != null ? String(appSettings.github.backup.minute)  : null,
    gh_data_backup_weekday: appSettings.github?.backup?.weekday != null ? String(appSettings.github.backup.weekday) : null,
    gh_data_backup_day:     appSettings.github?.backup?.day     != null ? String(appSettings.github.backup.day)     : null,
    gh_data_backup_notify:  appSettings.github?.backup?.notify  ? 'true' : null,
    gh_vitrine_auto_enabled: appSettings.github?.vitrine?.auto?.enabled ? 'true' : null,
    gh_vitrine_auto_hour:    appSettings.github?.vitrine?.auto?.hour   != null ? String(appSettings.github.vitrine.auto.hour)   : null,
    gh_vitrine_auto_minute:  appSettings.github?.vitrine?.auto?.minute != null ? String(appSettings.github.vitrine.auto.minute) : null,
    // Toujours explicite (jamais null, qui supprimerait la clé) : un autre appareil
    // doit voir « false » et non garder sa valeur locale.
    ai_enabled:        appSettings.ai?.enabled ? 'true' : 'false',
    ai_provider:       appSettings.ai?.provider     || null,
    ai_model:          appSettings.ai?.model        || null,
    ai_size:           appSettings.ai?.size         || null,
    ai_quality:        appSettings.ai?.quality      || null,
    ai_api_key:        appSettings.ai?.geminiApiKey || appSettings.ai?.apiKey || null,
    telegram_token:    appSettings.telegram?.token    || null,
    telegram_chat_id:  appSettings.telegram?.chatId   || null,
    telegram_tz:       appSettings.telegram?.tz       || null,
    telegram_notifs:      appSettings.telegram?.notifs    ? JSON.stringify(appSettings.telegram.notifs)  : null,
    tg_brewing_events:    appSettings.brewEvents          ? JSON.stringify(appSettings.brewEvents)         : null,
    hidden_world_events:  appSettings.hiddenWorldEvents?.length ? JSON.stringify(appSettings.hiddenWorldEvents) : null,
    world_event_overrides: appSettings.worldEventOverrides && Object.keys(appSettings.worldEventOverrides).length
      ? JSON.stringify(appSettings.worldEventOverrides) : null,
    default_brew_reminder_days: appSettings.defaultBrewReminderDays != null ? String(appSettings.defaultBrewReminderDays) : null,
    settings_ts: String(appSettings._ts || Date.now()),
  };
  api('PUT', '/api/app-settings', payload).catch(e => console.warn('[BrewHome] saveSettings failed:', e));
}

// Reconstruit appSettings depuis les données serveur (priorité sur localStorage)
// Les clés sensibles (PATs GitHub, clé IA) restent uniquement dans localStorage
function _loadSettingsFromServer(srv) {
  if (!srv || !Object.keys(srv).length) return;

  // Résolution de conflit par timestamp
  // Si le localStorage est plus récent que la DB (ex : modif offline non synchronisée),
  // on conserve l'état local et on le pousse vers le serveur au lieu d'écraser.
  const serverTs = parseInt(srv.settings_ts) || 0;
  const localTs  = parseInt(appSettings._ts)  || 0;
  if (localTs > serverTs && serverTs > 0) {
    // Local est plus récent — synchro vers le serveur et on s'arrête
    console.info(
      `[BrewHome] settings: local (${new Date(localTs).toISOString()}) ` +
      `plus récent que serveur (${new Date(serverTs).toISOString()}) — conservation locale`
    );
    _syncSettingsToServer();
    return;
  }
  // Apparence
  if (srv.app_name     != null) appSettings.appName     = srv.app_name     || null;
  if (srv.accent_color != null) appSettings.accentColor = srv.accent_color || null;
  if (srv.app_icon     != null) appSettings.appIcon     = srv.app_icon     || null;
  // Objets complexes (sérialisés en JSON)
  if (srv.thresholds != null) { try { appSettings.thresholds = JSON.parse(srv.thresholds); } catch(e) {} }
  if (srv.bottle_sizes_enabled != null) { try { appSettings.bottleSizes = JSON.parse(srv.bottle_sizes_enabled); } catch(e) {} }
  if (srv.water          != null) { try { appSettings.water         = JSON.parse(srv.water);          } catch(e) {} }
  if (srv.water_profiles != null) { try { appSettings.waterProfiles = JSON.parse(srv.water_profiles); } catch(e) {} }
  if (srv.energy     != null) { try { appSettings.energy     = JSON.parse(srv.energy);     } catch(e) {} }
  if (srv.vessels    != null) { try { appSettings.vessels    = JSON.parse(srv.vessels);    } catch(e) {} }
  if (srv.hubeau     != null) { try { appSettings.hubeau     = JSON.parse(srv.hubeau);     } catch(e) {} }
  if (srv.tz_offset  != null) appSettings.tz_offset = parseFloat(srv.tz_offset) || 0;
  // Langue
  if (srv.lang && LOCALES[srv.lang]) {
    _lang = srv.lang;
    _locale = LOCALES[_lang];
    localStorage.setItem('brewLang', _lang);
  }
  // GitHub
  // Nouveau format : targets JSON
  if (srv.gh_vitrine_targets != null) {
    appSettings.github = appSettings.github || {};
    appSettings.github.vitrine = appSettings.github.vitrine || {};
    try { appSettings.github.vitrine.targets = JSON.parse(srv.gh_vitrine_targets); } catch(e) {}
  }
  // Migration depuis les anciens champs individuels
  if (!appSettings.github?.vitrine?.targets?.length && srv.gh_vitrine_repo) {
    appSettings.github = appSettings.github || {};
    appSettings.github.vitrine = appSettings.github.vitrine || {};
    appSettings.github.vitrine.targets = [{
      provider: srv.gh_vitrine_provider || 'github',
      apiUrl:   srv.gh_vitrine_api_url  || '',
      repo:     srv.gh_vitrine_repo     || '',
      branch:   srv.gh_vitrine_branch   || 'main',
      pat:      srv.gh_vitrine_pat      || '',
    }];
  }
  if (srv.gh_data_targets != null) {
    appSettings.github = appSettings.github || {};
    appSettings.github.data = appSettings.github.data || {};
    try { appSettings.github.data.targets = JSON.parse(srv.gh_data_targets); } catch(e) {}
  }
  if (!appSettings.github?.data?.targets?.length && srv.gh_data_repo) {
    appSettings.github = appSettings.github || {};
    appSettings.github.data = appSettings.github.data || {};
    appSettings.github.data.targets = [{
      provider: srv.gh_data_provider || 'github',
      apiUrl:   srv.gh_data_api_url  || '',
      repo:     srv.gh_data_repo     || '',
      branch:   srv.gh_data_branch   || 'main',
      pat:      srv.gh_data_pat      || '',
    }];
  }
  if (srv.gh_data_backup_enabled != null || srv.gh_data_backup_freq != null) {
    appSettings.github = appSettings.github || {};
    appSettings.github.backup = appSettings.github.backup || {};
    const bk = appSettings.github.backup;
    if (srv.gh_data_backup_enabled != null) bk.enabled = srv.gh_data_backup_enabled === 'true';
    if (srv.gh_data_backup_notify  != null) bk.notify  = srv.gh_data_backup_notify  === 'true';
    if (srv.gh_data_backup_freq    != null) bk.freq    = srv.gh_data_backup_freq;
    if (srv.gh_data_backup_hour    != null) bk.hour    = parseInt(srv.gh_data_backup_hour)   || 2;
    if (srv.gh_data_backup_minute  != null) bk.minute  = parseInt(srv.gh_data_backup_minute) || 0;
    if (srv.gh_data_backup_weekday != null) bk.weekday = parseInt(srv.gh_data_backup_weekday) ?? 0;
    if (srv.gh_data_backup_day     != null) bk.day     = parseInt(srv.gh_data_backup_day)    || 1;
    if (srv.gh_data_last_backup    != null) bk.lastBackup = srv.gh_data_last_backup;
  }
  if (srv.gh_vitrine_auto_enabled != null || srv.gh_vitrine_auto_hour != null) {
    appSettings.github = appSettings.github || {};
    appSettings.github.vitrine = appSettings.github.vitrine || {};
    const au = appSettings.github.vitrine.auto = appSettings.github.vitrine.auto || {};
    if (srv.gh_vitrine_auto_enabled != null) au.enabled = srv.gh_vitrine_auto_enabled === 'true';
    if (srv.gh_vitrine_auto_hour    != null) au.hour    = parseInt(srv.gh_vitrine_auto_hour)   || 2;
    if (srv.gh_vitrine_auto_minute  != null) au.minute  = parseInt(srv.gh_vitrine_auto_minute) || 0;
    if (srv.gh_vitrine_last_push    != null) appSettings.github.vitrine.lastPush = srv.gh_vitrine_last_push;
  }
  // IA — désactivée tant que le serveur ne dit pas explicitement le contraire
  appSettings.ai = appSettings.ai || {};
  appSettings.ai.enabled = srv.ai_enabled === 'true';
  applyAIVisibility();
  if (srv.ai_provider != null || srv.ai_model != null || srv.ai_size != null || srv.ai_quality != null || srv.ai_api_key != null) {
    appSettings.ai = appSettings.ai || {};
    if (srv.ai_provider != null) appSettings.ai.provider = srv.ai_provider;
    if (srv.ai_model    != null) appSettings.ai.model    = srv.ai_model;
    if (srv.ai_size     != null) appSettings.ai.size     = srv.ai_size;
    if (srv.ai_quality  != null) appSettings.ai.quality  = srv.ai_quality;
    // '***' = clé présente en DB mais masquée : ne jamais écraser la valeur locale avec ce placeholder
    if (srv.ai_api_key != null && srv.ai_api_key !== '***') {
      appSettings.ai.apiKey     = srv.ai_api_key; // compat migration
      appSettings.ai.geminiApiKey = srv.ai_api_key;
    }
  }
  // Sanitize : si le placeholder '***' a déjà été stocké en localStorage par erreur, l'effacer
  if (appSettings.ai?.apiKey      === '***') appSettings.ai.apiKey      = '';
  if (appSettings.ai?.geminiApiKey === '***') appSettings.ai.geminiApiKey = '';
  // Telegram
  if (srv.telegram_token != null || srv.telegram_chat_id != null ||
      srv.telegram_tz    != null || srv.telegram_notifs  != null) {
    appSettings.telegram = appSettings.telegram || {};
    // '***' = token présent en DB mais masqué : ne jamais écraser la valeur locale avec ce placeholder
    if (srv.telegram_token != null && srv.telegram_token !== '***') {
      appSettings.telegram.token = srv.telegram_token || '';
    }
    if (srv.telegram_chat_id != null) appSettings.telegram.chatId = srv.telegram_chat_id || '';
    if (srv.telegram_tz      != null) appSettings.telegram.tz     = srv.telegram_tz     || 'Europe/Paris';
    if (srv.telegram_notifs  != null) {
      try { appSettings.telegram.notifs = JSON.parse(srv.telegram_notifs); } catch(e) {}
    }
  }
  // Sanitize : si le placeholder '***' a déjà été stocké en localStorage par erreur, l'effacer
  if (appSettings.telegram?.token === '***') appSettings.telegram.token = '';
  if (srv.tg_brewing_events != null) {
    try { appSettings.brewEvents = JSON.parse(srv.tg_brewing_events); } catch(e) {}
  }
  if (srv.hidden_world_events != null) {
    try { appSettings.hiddenWorldEvents = JSON.parse(srv.hidden_world_events); } catch(e) {}
  }
  if (srv.world_event_overrides != null) {
    try { appSettings.worldEventOverrides = JSON.parse(srv.world_event_overrides); } catch(e) {}
  }
  if (srv.default_brew_reminder_days != null)
    appSettings.defaultBrewReminderDays = parseInt(srv.default_brew_reminder_days) || 45;
  else if (appSettings.defaultBrewReminderDays == null)
    appSettings.defaultBrewReminderDays = 45;
  localStorage.setItem('brewSettings', JSON.stringify(appSettings));
}
// Normalise une quantité vers l'unité de base de sa dimension
function toBaseVal(qty, unit) {
  if (unit === 'kg')  return { v: qty * 1000, dim: 'weight' };
  if (unit === 'g')   return { v: qty,        dim: 'weight' };
  if (unit === 'L')   return { v: qty * 1000, dim: 'volume' };
  if (unit === 'mL')  return { v: qty,        dim: 'volume' };
  return { v: qty, dim: 'count' }; // pièce, sachet, unité, …
}
let settingsCat = 'malt';
let recSort = 'recent';
const STAR_LABELS = () => [t('rec.star_0'), t('rec.star_1'), t('rec.star_2'), t('rec.star_3'), t('rec.star_4'), t('rec.star_5')];
let recEditingId = null;
let recViewMode  = 'edit'; // 'view' | 'edit'
let recIngredients = []; // [{id,category,inventory_item_id,name,quantity,unit,...}]
let _fermProfile      = []; // [{day, temp}] fermentation temperature profile steps
let _wcSourceProfile  = null; // profil eau source actif dans la correction d'eau (null = appSettings.water)
let _invSugItems = []; // cache for inventory suggest clicks
let _rSugItems   = []; // cache for recipe ingredient suggest clicks



// ── Interrupteur global IA ──────────────────────────────────────────────
// Désactivé par défaut. Les éléments marqués .ai-only sont masqués par la
// classe « ai-off » posée sur <html> ; les fonctions qui appellent un
// fournisseur d'IA vérifient aussi isAIEnabled(), au cas où un bouton
// resterait accessible.
function isAIEnabled() {
  try { return !!appSettings?.ai?.enabled; } catch(e) { return false; }
}
function applyAIVisibility() {
  document.documentElement.classList.toggle('ai-off', !isAIEnabled());
}
function toggleAIEnabled(on) {
  appSettings.ai = appSettings.ai || {};
  appSettings.ai.enabled = !!on;
  applyAIVisibility();
  saveSettings();
}