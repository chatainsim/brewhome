// ══════════════════════════════════════════════════════════════════════════════
// UTILS — disponibles immédiatement (scripts core + lazy)
// ══════════════════════════════════════════════════════════════════════════════
function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ══════════════════════════════════════════════════════════════════════════════
// API
// ══════════════════════════════════════════════════════════════════════════════
async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  if (!r.ok) {
    const err = await r.json().catch(() => ({ error: r.statusText }));
    throw err;
  }
  const data = await r.json();
  if (_bch && method !== 'GET') {
    _bch.postMessage({ type: 'change', entity: _entityForPath(path), ts: Date.now() });
  }
  return data;
}

// ══════════════════════════════════════════════════════════════════════════════
// BUTTON LOADING STATE
// ══════════════════════════════════════════════════════════════════════════════
/**
 * Disable btn, show spinner, await fn(), restore — prevents double-click.
 * Usage in HTML: onclick="withBtn(this, saveXxx)"
 */
function debounce(fn, ms = 200) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

async function withBtn(btn, fn) {
  const orig = btn.innerHTML;
  if (!btn.dataset.origHtml) btn.dataset.origHtml = orig;
  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
  try {
    await fn();
  } finally {
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// NAVIGATION
// ══════════════════════════════════════════════════════════════════════════════
const _navSubParent = { stats: 'dashboard', dbadmin: 'dashboard', brouillons: 'recettes', kegs: 'inventaire' };

// ── Lazy script loader ────────────────────────────────────────────────────────
// Maps a script name to its in-flight/resolved Promise so concurrent
// navigate() calls for the same page never double-load a script.
const _lazyScriptPromises = new Map();
const _PAGE_LAZY_SCRIPTS = {
  // Scripts pré-chargés au boot (dans loadAll) : recettes, cave, calendrier, spindles, settings
  // Les entrées ci-dessous garantissent le chargement même si navigate() est appelé
  // avant que loadAll() ait fini (ex: lien direct ou navigation rapide).
  recettes:   ['bh-recettes.js'],
  brassins:   ['bh-brassins.js'],
  cave:       ['bh-cave.js'],
  spindles:   ['bh-spindles.js', 'bh-settings.js', 'bh-recettes.js'], // ingCost/ebcToColor/brewCost in recettes
  kegs:       ['bh-spindles.js', 'bh-settings.js', 'bh-recettes.js'],
  calendrier: ['bh-calendrier.js'],
  brouillons: ['bh-brouillons.js', 'bh-recettes.js'], // clearRecipeForm/renderIngredientRows etc. in recettes
  dbadmin:    ['bh-settings.js'],
  outils:     ['bh-recettes.js'],
  stats:      ['bh-recettes.js'],  // brewCost/recipeCost/ebcToColor in recettes
  dashboard:  ['bh-cave.js'],      // beerStockValue/_deplFmt in cave
};
function _ensureScript(name) {
  if (!_lazyScriptPromises.has(name)) {
    const p = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = `/static/js/${name}?v=${typeof _BH_STATIC_V !== 'undefined' ? _BH_STATIC_V : ''}`;
      s.onload = resolve;
      s.onerror = () => reject(new Error('Failed to load ' + name));
      document.head.appendChild(s);
    });
    _lazyScriptPromises.set(name, p);
  }
  return _lazyScriptPromises.get(name);
}

async function navigate(page) {
  if (typeof _closeAllNavDd === 'function') _closeAllNavDd();
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + page).classList.add('active');
  document.getElementById('nav-' + page).classList.add('active');
  const parent = _navSubParent[page];
  if (parent) document.getElementById('nav-' + parent)?.classList.add('active');
  window.scrollTo(0, 0);
  const lazy = _PAGE_LAZY_SCRIPTS[page];
  if (lazy) await Promise.all(lazy.map(_ensureScript));
  _refreshPage(page);
}

async function _refreshPage(page) {
  try {
    if (page === 'dashboard') {
      [S.recipes, S.brews, S.beers, S.inventory, S.sodaKegs, S.depletion] = await Promise.all([
        api('GET', '/api/recipes'),
        api('GET', '/api/brews'),
        api('GET', '/api/beers'),
        api('GET', '/api/inventory'),
        api('GET', '/api/soda-kegs'),
        api('GET', '/api/consumption/depletion'),
      ]);
      renderDashboard();
    } else if (page === 'inventaire') {
      S.inventory = await api('GET', '/api/inventory');
      renderInventaire();
    } else if (page === 'recettes') {
      S.recipes = await api('GET', '/api/recipes');
      renderRecipeList();
    } else if (page === 'brassins') {
      [S.brews, S.spindles, S.tempSensors, S.sodaKegs] = await Promise.all([
        api('GET', '/api/brews'),
        api('GET', '/api/spindles'),
        api('GET', '/api/temperature'),
        api('GET', '/api/soda-kegs'),
      ]);
      renderBrassins();
    } else if (page === 'cave') {
      [S.beers, S.sodaKegs, S.depletion] = await Promise.all([
        api('GET', '/api/beers'),
        api('GET', '/api/soda-kegs'),
        api('GET', '/api/consumption/depletion'),
      ]);
      renderCave();
    } else if (page === 'spindles') {
      [S.spindles, S.tempSensors] = await Promise.all([
        api('GET', '/api/spindles'),
        api('GET', '/api/temperature'),
      ]);
      renderSpindles();
      renderTempSensors();
    } else if (page === 'calendrier') {
      [S.brews, S.drafts, S.customEvents] = await Promise.all([
        api('GET', '/api/brews'),
        api('GET', '/api/drafts'),
        api('GET', '/api/custom_events'),
      ]);
      renderCalendar();
    } else if (page === 'brouillons') {
      if (S.drafts.length) renderBrouillons(); // rendu immédiat avec cache
      S.drafts = await api('GET', '/api/drafts');
      renderBrouillons();
    } else if (page === 'stats') {
      [S.brews, S.recipes, S.inventory, S.beers, S.consumption] = await Promise.all([
        api('GET', '/api/brews'),
        S.recipes.length ? Promise.resolve(S.recipes) : api('GET', '/api/recipes'),
        S.inventory.length ? Promise.resolve(S.inventory) : api('GET', '/api/inventory'),
        S.beers.length ? Promise.resolve(S.beers) : api('GET', '/api/beers'),
        api('GET', '/api/consumption'),
      ]);
      renderStatsPage();
    } else if (page === 'kegs') {
      [S.sodaKegs, S.brews, S.beers] = await Promise.all([
        api('GET', '/api/soda-kegs'),
        S.brews.length ? Promise.resolve(S.brews) : api('GET', '/api/brews'),
        S.beers.length ? Promise.resolve(S.beers) : api('GET', '/api/beers'),
      ]);
      renderKegs();
    } else if (page === 'dbadmin') {
      loadDbStats();
      return; // pas de badge à mettre à jour
    } else if (page === 'outils') {
      calcPriming('ot-priming-');
      renderRoDilutionSelectors();
      await ensureRecipesLoaded();
      initRecipeCompare();
      return;
    }
    const stats = await api('GET', '/api/stats');
    updateNavBadges(stats);
  } catch(e) { /* refresh silencieux */ }
}

// ══════════════════════════════════════════════════════════════════════════════
// LAZY-LOAD HELPERS — cache S.* + dédup des fetches simultanés
// ══════════════════════════════════════════════════════════════════════════════
// Usage : await ensureRecipesLoaded()  — no-op si déjà en cache, fetch unique
// Pour invalider : S.recipes = []  puis rappeler ensureRecipesLoaded()
const _ensureInFlight = {};

function _ensureMake(key, url) {
  return async function() {
    if (S[key].length) return;
    if (!_ensureInFlight[key]) {
      _ensureInFlight[key] = api('GET', url)
        .then(d => { S[key] = d; })
        .finally(() => { delete _ensureInFlight[key]; });
    }
    return _ensureInFlight[key];
  };
}

const ensureRecipesLoaded   = _ensureMake('recipes',   '/api/recipes');
const ensureBrewsLoaded     = _ensureMake('brews',     '/api/brews');
const ensureInventoryLoaded = _ensureMake('inventory', '/api/inventory');
const ensureBeersLoaded     = _ensureMake('beers',     '/api/beers');

// ══════════════════════════════════════════════════════════════════════════════
// BUTTON SAVE FLASH
// ══════════════════════════════════════════════════════════════════════════════
let _lastSaveBtn = null;
// Track the most recently clicked non-destructive button
document.addEventListener('click', e => {
  const b = e.target.closest('button');
  if (b && !b.classList.contains('btn-danger') &&
      !b.classList.contains('modal-close') && !b.classList.contains('toast-close')) {
    _lastSaveBtn = b;
  }
}, true);

function _btnFlash(btn) {
  if (!btn || btn._flashing || !document.contains(btn)) return;
  btn._flashing = true;
  const origHtml = btn.innerHTML;
  btn.classList.add('btn-saved-flash');
  btn.innerHTML = '<i class="fas fa-check"></i>';
  setTimeout(() => {
    btn.classList.remove('btn-saved-flash');
    btn.innerHTML = origHtml;
    btn._flashing = false;
  }, 1200);
}

// ══════════════════════════════════════════════════════════════════════════════
// TOAST
// ══════════════════════════════════════════════════════════════════════════════
function toast(msg, type = 'info') {
  if (type === 'success' && _lastSaveBtn) { _btnFlash(_lastSaveBtn); _lastSaveBtn = null; }
  const el = document.createElement('div');
  el.className = `toast-item toast-${type}`;
  const icon = type === 'success' ? 'check-circle' : type === 'error' ? 'circle-xmark' : 'circle-info';
  el.innerHTML = `<i class="fas fa-${icon}"></i><span style="flex:1">${esc(msg)}</span><button class="toast-close" onclick="this.parentElement.remove()" title="${esc(t('common.close'))}">✕</button>`;
  document.getElementById('toast').appendChild(el);
  // Auto-fermeture : 5s pour les erreurs, 3s pour les autres
  const delay = type === 'error' ? 15000 : 5000;
  const timer = setTimeout(() => el.remove(), delay);
  // Annuler le timer si l'utilisateur ferme manuellement
  el.querySelector('.toast-close').addEventListener('click', () => clearTimeout(timer));
}

// ══════════════════════════════════════════════════════════════════════════════
// CONFIRM MODAL
// ══════════════════════════════════════════════════════════════════════════════
function confirmModal(msg, opts = {}) {
  return new Promise(resolve => {
    const overlay = document.getElementById('modal-confirm');
    document.getElementById('modal-confirm-msg').textContent = msg;
    const okBtn = document.getElementById('modal-confirm-ok');
    const clBtn = document.getElementById('modal-confirm-cancel');
    okBtn.textContent = opts.confirmLabel || (opts.danger ? t('common.delete') : t('common.confirm'));
    clBtn.textContent = opts.cancelLabel  || t('common.cancel');
    okBtn.style.cssText = opts.danger
      ? 'background:#ef4444;color:#fff;border-color:#ef4444'
      : 'background:var(--accent);color:#000;border-color:var(--accent)';
    overlay.style.display = 'flex';
    function cleanup(result) {
      overlay.style.display = 'none';
      okBtn.onclick = null;
      clBtn.onclick = null;
      resolve(result);
    }
    okBtn.onclick = () => cleanup(true);
    clBtn.onclick = () => cleanup(false);
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// DOM DIFF UTILITY
// ══════════════════════════════════════════════════════════════════════════════
/**
 * Patch a container's direct keyed children without full innerHTML replacement.
 * Elements with [data-id] are diffed; non-keyed siblings are left untouched.
 * Items whose rendered HTML hasn't changed are reused as-is (no DOM op).
 */
function _patchList(container, items, idFn, htmlFn) {
  const entries  = items.map(item => ({ id: String(idFn(item)), html: htmlFn(item).trim() }));
  const newIdSet = new Set(entries.map(e => e.id));

  // Remove elements no longer in the list
  Array.from(container.querySelectorAll(':scope > [data-id]'))
    .filter(el => !newIdSet.has(el.dataset.id))
    .forEach(el => el.remove());

  // Build map of remaining elements
  const existing = new Map();
  container.querySelectorAll(':scope > [data-id]').forEach(el => existing.set(el.dataset.id, el));

  // Upsert in correct order
  let prev = null;
  for (const { id, html } of entries) {
    const ex = existing.get(id);
    let el;

    if (ex && ex.outerHTML === html) {
      el = ex; // identical → reuse, no DOM write
    } else {
      const tmpl = document.createElement('template');
      tmpl.innerHTML = html;
      el = tmpl.content.firstElementChild;
      if (ex) ex.replaceWith(el);
    }

    // Ensure correct position
    const actualPrev = el.parentNode === container ? el.previousElementSibling : null;
    if (el.parentNode !== container) {
      prev ? prev.after(el) : container.prepend(el);
    } else if (actualPrev !== prev) {
      prev ? prev.after(el) : container.prepend(el);
    }

    prev = el;
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// ARCHIVE
// ══════════════════════════════════════════════════════════════════════════════
async function archiveItem(entity, id, archived) {
  const paths = {inv:'inventory', rec:'recipes', brew:'brews', cave:'beers'};
  try {
    const updated = await api('PATCH', `/api/${paths[entity]}/${id}`, {archived});
    const arr = {inv:S.inventory, rec:S.recipes, brew:S.brews, cave:S.beers}[entity];
    const idx = arr.findIndex(x=>x.id===id);
    if(idx!==-1) arr[idx] = {...arr[idx], archived: archived?1:0};
    ({inv:renderInventaire, rec:renderRecipeList, brew:renderBrassins, cave:renderCave})[entity]();
    toast(archived ? t('common.archived') : t('common.restored'), 'success');
    if (entity === 'cave' && typeof _autoPushVitrineDebounced === 'function') _autoPushVitrineDebounced();
  } catch(e) { toast(t('common.err_archive'), 'error'); }
}

function toggleShowArchived(section) {
  if(section==='inv')  { showArchivedInv  = !showArchivedInv;  renderInventaire(); }
  if(section==='rec')  { showArchivedRec  = !showArchivedRec;  renderRecipeList(); }
  if(section==='brew') { showArchivedBrew = !showArchivedBrew; renderBrassins();   }
  if(section==='cave') { showArchivedCave = !showArchivedCave; renderCave();       }
}

// ══════════════════════════════════════════════════════════════════════════════
// SETTINGS MODAL
// ══════════════════════════════════════════════════════════════════════════════
async function openSettings() {
  _dirtyModals.delete('modal-settings');
  await _ensureScript('bh-settings.js');
  renderSettingsCatalog(settingsCat);
  settingsTab('catalogue');
  document.getElementById('modal-settings').classList.add('open');
  _sizeSettingsBody();
  setTimeout(_sizeSettingsBody, 100);
}
function _settingsEnsureTab(tab) {
  const el = document.getElementById('stab-' + tab);
  if (!el || el.dataset.loaded) return;
  const tpl = document.getElementById('stab-' + tab + '-tpl');
  if (!tpl) return;
  el.appendChild(tpl.content.cloneNode(true));
  el.dataset.loaded = '1';
  applyI18n();
  if (tab === 'import') {
    const inp = document.getElementById('ical-url-input');
    if (inp) inp.value = window.location.origin + '/api/calendar/ics';
  }
}
function _sizeSettingsBody() {
  const modal = document.querySelector('#modal-settings .modal');
  const head  = document.querySelector('#modal-settings .modal-head');
  const foot  = document.querySelector('#modal-settings .modal-foot');
  const body  = document.getElementById('settings-modal-body');
  const nav   = document.getElementById('settings-nav');
  if (!modal || !head || !foot || !body || !nav) return;
  const h = modal.offsetHeight - head.offsetHeight - foot.offsetHeight;
  console.log('[Settings] modal:', modal.offsetHeight, 'head:', head.offsetHeight, 'foot:', foot.offsetHeight, '→ body h:', h);
  body.style.height = h + 'px';
  nav.style.height  = h + 'px';
}
function closeSettings() { closeModal('modal-settings'); }

function settingsTab(tab) {
  _settingsEnsureTab(tab);
  document.querySelectorAll('#modal-settings .snav-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.getElementById('stab-catalogue').style.display   = tab === 'catalogue'   ? '' : 'none';
  document.getElementById('stab-thresholds').style.display  = tab === 'thresholds'  ? '' : 'none';
  document.getElementById('stab-water').style.display       = tab === 'water'       ? '' : 'none';
  document.getElementById('stab-calendrier').style.display  = tab === 'calendrier'  ? '' : 'none';
  document.getElementById('stab-import').style.display      = tab === 'import'      ? '' : 'none';
  document.getElementById('stab-github').style.display      = tab === 'github'      ? '' : 'none';
  document.getElementById('stab-lang').style.display        = tab === 'lang'        ? '' : 'none';
  document.getElementById('stab-apparence').style.display   = tab === 'apparence'   ? '' : 'none';
  document.getElementById('stab-ai').style.display          = tab === 'ai'          ? '' : 'none';
  document.getElementById('stab-notif').style.display       = tab === 'notif'       ? '' : 'none';
  document.getElementById('stab-updates').style.display     = tab === 'updates'     ? '' : 'none';
  document.getElementById('stab-trash').style.display       = tab === 'trash'       ? '' : 'none';
  document.getElementById('stab-checklist').style.display   = tab === 'checklist'   ? '' : 'none';
  if (tab === 'calendrier') renderSettingsCalendrier();
  if (tab === 'water')      renderWaterProfilesManager();
  document.getElementById('settings-save-btn').style.display  = tab === 'thresholds' ? '' : 'none';
  document.getElementById('github-save-btn').style.display    = tab === 'github'     ? '' : 'none';
  document.getElementById('apparence-save-btn').style.display = tab === 'apparence'  ? '' : 'none';
  document.getElementById('ai-save-btn').style.display        = tab === 'ai'         ? '' : 'none';
  document.getElementById('notif-save-btn').style.display     = tab === 'notif'      ? '' : 'none';
  if (tab === 'thresholds') renderSettingsThresholds();
  if (tab === 'water')      renderSettingsWater();
  if (tab === 'github')     renderSettingsGithub();
  if (tab === 'lang')       renderSettingsLang();
  if (tab === 'apparence')  renderSettingsApparence();
  if (tab === 'ai')         renderSettingsAI();
  if (tab === 'notif')      renderSettingsNotif();
  if (tab === 'updates')    checkStaticUpdates();
  if (tab === 'trash')      renderSettingsTrash();
  if (tab === 'checklist')  renderSettingsChecklists();
}

function renderSettingsCatalog(cat) {
  settingsCat = cat;
  document.querySelectorAll('#settings-cat-chips .cat-chip').forEach(c => {
    c.classList.toggle('active', c.dataset.cat === cat);
  });
  const items = S.catalog.filter(c => c.category === cat)
    .sort((a,b) => (a.subcategory||'').localeCompare(b.subcategory||'') || a.name.localeCompare(b.name));
  const list = document.getElementById('settings-catalog-list');
  list.innerHTML = items.length ? items.map(item => _catalogRowHtml(item, cat)).join('')
    : `<div style="color:var(--muted);text-align:center;padding:20px 0;font-size:.87rem">${t('inv.empty')}</div>`;
  // Afficher les bons champs selon catégorie
  document.getElementById('scat-ebc-wrap').style.display    = cat === 'malt'    ? '' : 'none';
  document.getElementById('scat-maxpct-wrap').style.display = cat === 'malt'    ? '' : 'none';
  document.getElementById('scat-alpha-wrap').style.display  = cat === 'houblon' ? '' : 'none';
  document.getElementById('scat-aroma-wrap').style.display  = cat === 'houblon' ? '' : 'none';
  document.getElementById('scat-ytype-wrap').style.display  = cat === 'levure'  ? '' : 'none';
  document.getElementById('scat-yeast-wrap').style.display  = cat === 'levure'  ? '' : 'none';
  document.getElementById('scat-unit').value = cat === 'malt' ? 'kg' : 'g';
}

function _catalogRowHtml(item, cat) {
  return `
    <div class="catalog-row" id="crow-${item.id}">
      <div style="flex:1">
        <div>
          <span style="font-weight:600">${esc(item.name)}</span>
          ${item.subcategory ? `<span style="font-size:.78rem;color:var(--muted);margin-left:6px">${esc(item.subcategory)}</span>` : ''}
          ${item.ebc        != null ? `<span class="badge badge-malt"    style="font-size:.68rem;margin-left:4px">EBC ${item.ebc}</span>` : ''}
          ${item.max_usage_pct != null ? `<span class="badge badge-malt" style="font-size:.68rem;margin-left:4px;opacity:.8">max ${item.max_usage_pct}%</span>` : ''}
          ${item.alpha      != null ? `<span class="badge badge-houblon" style="font-size:.68rem;margin-left:4px">α ${item.alpha}%</span>` : ''}
          ${item.yeast_type ? `<span class="badge badge-levure" style="font-size:.68rem;margin-left:4px">${esc(item.yeast_type)}</span>` : ''}
          ${item.temp_min != null || item.temp_max != null ? `<span class="badge badge-levure" style="font-size:.68rem;margin-left:4px;opacity:.8">${item.temp_min??'?'}–${item.temp_max??'?'}°C</span>` : ''}
          ${item.attenuation_min != null || item.attenuation_max != null ? `<span class="badge badge-levure" style="font-size:.68rem;margin-left:4px;opacity:.7">${item.attenuation_min??'?'}–${item.attenuation_max??'?'}%</span>` : ''}
          ${item.alcohol_tolerance != null ? `<span class="badge badge-levure" style="font-size:.68rem;margin-left:4px;opacity:.6">tol. ${item.alcohol_tolerance}%</span>` : ''}
          ${item.dosage_per_liter != null ? `<span class="badge badge-levure" style="font-size:.68rem;margin-left:4px;opacity:.6">${item.dosage_per_liter}g/L</span>` : ''}
          ${item.gu != null && item.category === 'autre' ? `<span class="badge" style="font-size:.68rem;margin-left:4px;background:rgba(251,191,36,.15);color:var(--amber)">${item.gu} GU/kg</span>` : ''}
          <span style="font-size:.72rem;color:var(--muted);margin-left:6px">[${item.default_unit || 'g'}]</span>
        </div>
        ${item.aroma_spec ? `<div style="font-size:.71rem;color:var(--muted);font-style:italic;margin-top:1px;line-height:1.3">${esc(item.aroma_spec)}</div>` : ''}
      </div>
      <button class="btn btn-icon btn-ghost btn-sm" onclick="editCatalogInline(${item.id})" title="${t('common.edit')}"><i class="fas fa-pen"></i></button>
      <button class="btn btn-icon btn-danger btn-sm" onclick="deleteCatalogItem(${item.id})" title="${t('common.delete')}"><i class="fas fa-trash"></i></button>
    </div>`;
}

function editCatalogInline(id) {
  const item = S.catalog.find(c => c.id === id);
  if (!item) return;
  const cat = item.category;
  const extraField =
    cat === 'malt'    ? `<input type="number" id="cedit-ebc-${id}"    value="${item.ebc    ?? ''}" step="0.1" placeholder="EBC"    style="width:70px" title="EBC">
                         <input type="number" id="cedit-maxpct-${id}" value="${item.max_usage_pct ?? ''}" step="1" min="0" max="100" placeholder="% max" style="width:70px" title="${t('settings.catalogue.field_maxpct')}">` :
    cat === 'houblon' ? `<input type="number" id="cedit-alpha-${id}"  value="${item.alpha  ?? ''}" step="0.1" placeholder="α%"     style="width:70px" title="Alpha %">
                         <input type="text"   id="cedit-aroma-${id}"  value="${esc(item.aroma_spec||'')}" placeholder="${t('settings.catalogue.field_aroma')}…" style="flex:1;min-width:140px" title="${t('settings.catalogue.field_aroma')}">` :
    cat === 'levure'  ? `<input type="text"   id="cedit-ytype-${id}"  value="${esc(item.yeast_type||'')}"  placeholder="${t('settings.catalogue.field_ytype')}" style="width:80px" title="${t('settings.catalogue.field_ytype')}">` :
    cat === 'autre'   ? `<input type="number" id="cedit-gu-${id}"     value="${item.gu ?? ''}"              step="1" min="0" placeholder="GU/kg" style="width:80px" title="${t('settings.catalogue.field_gu_autre')}">` : '';
  const yeastExtra = cat === 'levure' ? `
    <div style="width:100%;display:flex;flex-wrap:wrap;gap:6px;margin-top:4px;padding-top:6px;border-top:1px solid var(--border)">
      <input type="number" id="cedit-tmin-${id}"   value="${item.temp_min??''}"          step="0.5" placeholder="T°min°C" style="width:80px" title="${t('settings.catalogue.field_tmin')}">
      <input type="number" id="cedit-tmax-${id}"   value="${item.temp_max??''}"          step="0.5" placeholder="T°max°C" style="width:80px" title="${t('settings.catalogue.field_tmax')}">
      <input type="number" id="cedit-dosage-${id}" value="${item.dosage_per_liter??''}"  step="0.01" placeholder="g/L"    style="width:70px" title="${t('settings.catalogue.field_dosage')}">
      <input type="number" id="cedit-attmin-${id}" value="${item.attenuation_min??''}"   step="1"    placeholder="Att.min%" style="width:78px" title="${t('settings.catalogue.field_att_min')}">
      <input type="number" id="cedit-attmax-${id}" value="${item.attenuation_max??''}"   step="1"    placeholder="Att.max%" style="width:78px" title="${t('settings.catalogue.field_att_max')}">
      <input type="number" id="cedit-alctol-${id}" value="${item.alcohol_tolerance??''}" step="0.5"  placeholder="Tol.alc%" style="width:82px" title="${t('settings.catalogue.field_alc_tol')}">
    </div>` : '';
  const _unitLabels = { 'unité': t('inv.unit_unite'), 'sachet': t('inv.unit_sachet'), 'pièce': t('inv.unit_piece') };
  const unitOpts = ['kg','g','L','mL','unité','sachet'].map(u =>
    `<option value="${u}" ${item.default_unit===u?'selected':''}>${_unitLabels[u]||u}</option>`).join('');

  document.getElementById(`crow-${id}`).outerHTML = `
    <div class="catalog-row" id="crow-${id}" style="flex-wrap:wrap;gap:6px">
      <input type="text" id="cedit-name-${id}" value="${esc(item.name)}" style="flex:1;min-width:130px" placeholder="${t('inv.field_name')}">
      <input type="text" id="cedit-sub-${id}"  value="${esc(item.subcategory||'')}" style="width:110px" placeholder="${t('inv.field_sub')}">
      ${extraField}
      <select id="cedit-unit-${id}" style="width:70px" title="${t('settings.catalogue.field_unit')}">${unitOpts}</select>
      <button class="btn btn-success btn-icon btn-sm" onclick="saveCatalogEdit(${id})" title="${t('common.save')}"><i class="fas fa-check"></i></button>
      <button class="btn btn-ghost  btn-icon btn-sm" onclick="renderSettingsCatalog(settingsCat)" title="${t('common.cancel')}"><i class="fas fa-xmark"></i></button>
      ${yeastExtra}
    </div>`;
  document.getElementById(`cedit-name-${id}`).focus();
}

async function saveCatalogEdit(id) {
  const item = S.catalog.find(c => c.id === id);
  if (!item) return;
  const cat  = item.category;
  const name = document.getElementById(`cedit-name-${id}`).value.trim();
  if (!name) { toast(t('settings.toast.err_name_required'), 'error'); return; }
  const fv = (elId) => { const el = document.getElementById(elId); return el && el.value !== '' ? parseFloat(el.value) : null; };
  const payload = {
    name,
    category:    cat,
    subcategory: document.getElementById(`cedit-sub-${id}`).value.trim() || null,
    ebc:         cat === 'malt'    ? fv(`cedit-ebc-${id}`)    : null,
    max_usage_pct: cat === 'malt'  ? fv(`cedit-maxpct-${id}`) : null,
    alpha:       cat === 'houblon' ? fv(`cedit-alpha-${id}`)  : null,
    gu:          cat === 'autre'   ? fv(`cedit-gu-${id}`)     : null,
    aroma_spec:  cat === 'houblon' ? (document.getElementById(`cedit-aroma-${id}`)?.value.trim() || null) : null,
    yeast_type:  cat === 'levure'  ? (document.getElementById(`cedit-ytype-${id}`)?.value.trim() || null) : null,
    temp_min:          cat === 'levure' ? fv(`cedit-tmin-${id}`)   : null,
    temp_max:          cat === 'levure' ? fv(`cedit-tmax-${id}`)   : null,
    dosage_per_liter:  cat === 'levure' ? fv(`cedit-dosage-${id}`) : null,
    attenuation_min:   cat === 'levure' ? fv(`cedit-attmin-${id}`) : null,
    attenuation_max:   cat === 'levure' ? fv(`cedit-attmax-${id}`) : null,
    alcohol_tolerance: cat === 'levure' ? fv(`cedit-alctol-${id}`) : null,
    default_unit: document.getElementById(`cedit-unit-${id}`).value,
  };
  try {
    const updated = await api('PUT', `/api/catalog/${id}`, payload);
    const idx = S.catalog.findIndex(c => c.id === id);
    if (idx !== -1) S.catalog[idx] = updated;
    renderSettingsCatalog(settingsCat);
    toast(t('settings.toast.catalog_updated'), 'success');
  } catch(e) { toast(t('settings.toast.err_update'), 'error'); }
}

async function addCatalogItem() {
  const name = document.getElementById('scat-name').value.trim();
  if (!name) { toast(t('settings.toast.err_name_required'), 'error'); return; }
  const sfv = (id) => { const el = document.getElementById(id); return el && el.value !== '' ? parseFloat(el.value) : null; };
  const payload = {
    name,
    category:    settingsCat,
    subcategory: document.getElementById('scat-sub').value.trim() || null,
    ebc:         sfv('scat-ebc'),
    max_usage_pct: sfv('scat-maxpct'),
    alpha:       sfv('scat-alpha'),
    aroma_spec:  document.getElementById('scat-aroma')?.value.trim() || null,
    yeast_type:  document.getElementById('scat-ytype').value.trim() || null,
    temp_min:          sfv('scat-tmin'),
    temp_max:          sfv('scat-tmax'),
    dosage_per_liter:  sfv('scat-dosage'),
    attenuation_min:   sfv('scat-attmin'),
    attenuation_max:   sfv('scat-attmax'),
    alcohol_tolerance: sfv('scat-alctol'),
    default_unit: document.getElementById('scat-unit').value,
  };
  try {
    const item = await api('POST', '/api/catalog', payload);
    S.catalog.push(item);
    ['scat-name','scat-sub','scat-ebc','scat-maxpct','scat-alpha','scat-aroma','scat-ytype',
     'scat-tmin','scat-tmax','scat-dosage','scat-attmin','scat-attmax','scat-alctol']
      .forEach(id => { const el = document.getElementById(id); if(el) el.value = ''; });
    renderSettingsCatalog(settingsCat);
    toast(t('settings.toast.catalog_added'), 'success');
  } catch(e) { toast(t('settings.toast.err_add'), 'error'); }
}

async function deleteCatalogItem(id) {
  try {
    await api('DELETE', `/api/catalog/${id}`);
    S.catalog = S.catalog.filter(c => c.id !== id);
    renderSettingsCatalog(settingsCat);
    toast(t('settings.toast.catalog_deleted'), 'success');
  } catch(e) { toast(t('settings.toast.err_delete'), 'error'); }
}

const AUTRE_UNITS = ['g','kg','mL','L','pièce','sachet'];

// ── Calendrier settings ────────────────────────────────────────────────────
let _editingWorldEv = null;

function saveDefaultBrewReminderDays(val) {
  const days = parseInt(val);
  appSettings.defaultBrewReminderDays = (days > 0 && days <= 365) ? days : 45;
  document.getElementById('settings-default-remind-days').value = appSettings.defaultBrewReminderDays;
  saveSettings();
  renderCalendar();
  _refreshDaysLabels();
  toast(t('settings.toast.remind_days_saved'), 'success');
}

function renderSettingsCalendrier() {
  const inp = document.getElementById('settings-default-remind-days');
  if (inp) inp.value = appSettings.defaultBrewReminderDays || 45;
  _renderSettingsWorldEvents();
  _renderSettingsCustomEvents();
}

function _renderSettingsWorldEvents() {
  const hidden    = appSettings.hiddenWorldEvents    || [];
  const overrides = appSettings.worldEventOverrides  || {};
  const allEvs = _brewingEvents(new Date().getFullYear());
  const seen = new Set();
  const unique = allEvs.filter(e => { const k = e.canonical || e.label; if (seen.has(k)) return false; seen.add(k); return true; });

  const btn = document.getElementById('cal-toggle-all-btn');
  const allHidden = unique.every(e => hidden.includes(e.canonical || e.label));
  if (btn) btn.textContent = allHidden ? t('settings.cal.show_all') : t('settings.cal.hide_all');

  const list = document.getElementById('settings-world-ev-list');
  if (!list) return;

  list.innerHTML = unique.map(ev => {
    const eKey      = ev.canonical || ev.label;
    const isHidden  = hidden.includes(eKey);
    const ov        = overrides[eKey] || {};
    const origDet   = _BREW_EV_DETAILS[eKey] || {};
    const dEmoji    = ov.emoji || ev.emoji;
    const dLabel    = ov.label || ev.label;
    const dColor    = ov.color || ev.color || '#f59e0b';
    const _origDesc = _lang === 'en' ? (origDet.desc_en || origDet.desc || '') : (origDet.desc || '');
    const dDesc     = ov.desc  !== undefined ? ov.desc  : _origDesc;
    const _origStyle = _lang === 'en' ? (origDet.style_en || origDet.style || '') : (origDet.style || '');
    const dStyle    = ov.style !== undefined ? ov.style : _origStyle;
    const origDate  = _brewingEvents(new Date().getFullYear()).find(e => (e.canonical || e.label) === eKey)?.date || '';
    const dDateFull = ov.date_mmdd ? `${new Date().getFullYear()}-${ov.date_mmdd}` : origDate;
    const hasOv     = !!(ov.emoji || ov.label || ov.color || ov.desc !== undefined || ov.style !== undefined || ov.date_mmdd);
    const id        = _wevId(eKey);
    const safeOrig  = eKey.replace(/\\/g,'\\\\').replace(/'/g,"\\'");

    if (_editingWorldEv === eKey) {
      return `<div style="padding:12px;border-radius:8px;background:var(--card2);border:1px solid rgba(245,158,11,.4)">
        <div style="display:flex;gap:8px;margin-bottom:8px;align-items:center">
          <div>
            <div style="font-size:.68rem;color:var(--muted);margin-bottom:3px">Emoji</div>
            <input id="wev-emoji-${id}" type="text" value="${dEmoji}"
              style="width:46px;text-align:center;font-size:1.15rem;padding:4px;border-radius:6px;
              border:1px solid var(--border);background:var(--input,var(--card))">
          </div>
          <div style="flex:1">
            <div style="font-size:.68rem;color:var(--muted);margin-bottom:3px">Nom</div>
            <input id="wev-label-${id}" type="text" value="${dLabel.replace(/"/g,'&quot;')}" class="form-control" style="font-size:.85rem">
          </div>
          <div>
            <div style="font-size:.68rem;color:var(--muted);margin-bottom:3px">Couleur</div>
            <input id="wev-color-${id}" type="color" value="${dColor}"
              style="width:38px;height:34px;border:none;border-radius:6px;cursor:pointer;padding:0;background:none;display:block">
          </div>
          <div>
            <div style="font-size:.68rem;color:var(--muted);margin-bottom:3px">${t('settings.cal.field_date')}</div>
            <input id="wev-date-${id}" type="date" value="${dDateFull}" class="form-control"
              style="font-size:.8rem;width:148px" title="${t('settings.cal.field_date')}">
          </div>
        </div>
        <div style="font-size:.72rem;color:var(--muted);margin-bottom:8px;padding:5px 8px;
          background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:6px">
          ${_worldEvRecurrenceLabel(eKey)}
        </div>
        <div style="margin-bottom:8px">
          <div style="font-size:.68rem;color:var(--muted);margin-bottom:3px">${t('settings.cal.field_desc')}</div>
          <textarea id="wev-desc-${id}" class="form-control" rows="2" style="font-size:.82rem;resize:vertical"
            placeholder="${t('settings.cal.field_desc')}…">${dDesc.replace(/</g,'&lt;')}</textarea>
        </div>
        <div style="margin-bottom:10px">
          <div style="font-size:.68rem;color:var(--muted);margin-bottom:3px">${t('settings.cal.field_style')}</div>
          <input id="wev-style-${id}" type="text" class="form-control" value="${dStyle.replace(/"/g,'&quot;')}"
            style="font-size:.82rem" placeholder="${t('rec.bjcp_placeholder')}">
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <button class="btn btn-primary btn-sm" onclick="saveWorldEventOverride('${safeOrig}')">
            <i class="fas fa-check"></i> ${t('common.save')}
          </button>
          <button class="btn btn-ghost btn-sm" onclick="_editingWorldEv=null;_renderSettingsWorldEvents()">
            <i class="fas fa-xmark"></i> ${t('common.cancel')}
          </button>
          ${hasOv ? `<button class="btn btn-ghost btn-sm" style="color:var(--muted);margin-left:auto"
            onclick="resetWorldEventOverride('${safeOrig}')">
            <i class="fas fa-rotate-left"></i> ${t('settings.cal.reset')}
          </button>` : ''}
        </div>
      </div>`;
    }

    return `<div style="display:flex;align-items:center;gap:10px;padding:7px 10px;border-radius:8px;
        background:var(--card2);border:1px solid var(--border);opacity:${isHidden ? '.45' : '1'}">
      <span style="font-size:1rem;flex-shrink:0">${dEmoji}</span>
      <div style="flex:1;min-width:0">
        <div style="font-size:.82rem;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(dLabel)}</div>
        ${dDesc ? `<div style="font-size:.7rem;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(dDesc.slice(0,60))}${dDesc.length>60?'…':''}</div>` : ''}
      </div>
      ${hasOv ? `<span style="font-size:.65rem;color:var(--amber);padding:1px 5px;border-radius:4px;
        background:rgba(245,158,11,.12);flex-shrink:0">${t('settings.cal.modified_badge')}</span>` : ''}
      <div style="text-align:right;flex-shrink:0">
        <div style="font-size:.72rem;color:var(--muted)">${ov.date_mmdd ? new Date(`${new Date().getFullYear()}-${ov.date_mmdd}T00:00:00`).toLocaleDateString(_lang||'fr',{day:'numeric',month:'short'}) : _worldEvMonthLabel(eKey)}</div>
        <div style="font-size:.65rem;color:var(--muted);opacity:.7">${_worldEvRecurrenceLabel(eKey).split('·')[0].trim()}</div>
      </div>
      <button class="btn btn-ghost btn-icon btn-sm" title="${t('common.edit')}"
        onclick="_editingWorldEv='${safeOrig}';_renderSettingsWorldEvents()">
        <i class="fas fa-pen" style="font-size:.7rem"></i>
      </button>
      <label style="position:relative;display:inline-flex;align-items:center;cursor:pointer;flex-shrink:0">
        <input type="checkbox" ${isHidden ? '' : 'checked'} style="width:auto;opacity:0;position:absolute;pointer-events:none"
          onchange="toggleWorldEvent('${safeOrig}', this.checked)">
        <span style="width:36px;height:20px;border-radius:10px;transition:background .2s;display:block;
          background:${isHidden ? 'var(--border)' : dColor}"></span>
        <span style="position:absolute;left:${isHidden ? '2px' : '18px'};top:2px;width:16px;height:16px;
          border-radius:50%;background:#fff;transition:left .2s;display:block;box-shadow:0 1px 3px rgba(0,0,0,.3)"></span>
      </label>
    </div>`;
  }).join('');
}

function _wevId(label) { return label.replace(/[^a-zA-Z0-9]/g, '-'); }

function _worldEvRecurrenceLabel(eKey) {
  const year  = new Date().getFullYear();
  const evCur  = _brewingEvents(year).find(e => (e.canonical || e.label) === eKey);
  const evNext = _brewingEvents(year + 1).find(e => (e.canonical || e.label) === eKey);
  if (!evCur) return '';
  const cur  = evCur.date;
  const MONTHS = t('cal.months');
  const dCur = new Date(cur + 'T00:00:00');
  const month = dCur.getMonth(); // 0-indexed
  if (!evNext || cur.slice(5) === evNext.date.slice(5)) {
    // Même MM-JJ chaque année
    return `🔁 ${t('cal.rec_yearly')} · ${dCur.toLocaleDateString(_lang || 'fr', { day: 'numeric', month: 'long' })}`;
  }
  // Nième jour de la semaine du mois
  const nth    = Math.ceil(dCur.getDate() / 7);
  const dow    = dCur.getDay();
  const nthLbls = [null, t('cal.rec_1st'), t('cal.rec_2nd'), t('cal.rec_3rd'), t('cal.rec_4th')];
  const dowLbls = [t('cal.rec_dow_0'), t('cal.rec_dow_1'), t('cal.rec_dow_2'),
                   t('cal.rec_dow_3'), t('cal.rec_dow_4'), t('cal.rec_dow_5'), t('cal.rec_dow_6')];
  return `🔁 ${nthLbls[nth] || nth + 'e'} ${dowLbls[dow]} ${t('cal.rec_of')} ${MONTHS[month]}`;
}

function _worldEvMonthLabel(canonicalOrLabel) {
  const year = new Date().getFullYear();
  const evs  = _brewingEvents(year);
  const ev   = evs.find(e => (e.canonical || e.label) === canonicalOrLabel);
  if (!ev) return '';
  return new Date(ev.date + 'T00:00:00').toLocaleDateString(_lang || 'fr', { day:'numeric', month:'short' });
}

function saveWorldEventOverride(originalLabel) {
  const id      = _wevId(originalLabel);
  const emoji   = document.getElementById(`wev-emoji-${id}`)?.value.trim();
  const label   = document.getElementById(`wev-label-${id}`)?.value.trim();
  const color   = document.getElementById(`wev-color-${id}`)?.value;
  const desc    = document.getElementById(`wev-desc-${id}`)?.value.trim();
  const style   = document.getElementById(`wev-style-${id}`)?.value.trim();
  const dateVal = document.getElementById(`wev-date-${id}`)?.value; // YYYY-MM-DD
  const orig    = _brewingEvents(new Date().getFullYear()).find(e => (e.canonical || e.label) === originalLabel) || {};
  const origDet = _BREW_EV_DETAILS[originalLabel] || {};
  const origMmdd = (orig.date || '').slice(5); // MM-DD
  if (!appSettings.worldEventOverrides) appSettings.worldEventOverrides = {};
  const ov = {};
  if (emoji && emoji !== orig.emoji)        ov.emoji = emoji;
  if (label && label !== originalLabel)     ov.label = label;
  if (color && color !== orig.color)        ov.color = color;
  const _origDescBase = _lang === 'en' ? (origDet.desc_en || origDet.desc || '') : (origDet.desc || '');
  if (desc  !== undefined && desc  !== _origDescBase)  ov.desc  = desc;
  const _origStyleBase = _lang === 'en' ? (origDet.style_en || origDet.style || '') : (origDet.style || '');
  if (style !== undefined && style !== _origStyleBase)  ov.style = style;
  const newMmdd = dateVal ? dateVal.slice(5) : '';
  if (newMmdd && newMmdd !== origMmdd)      ov.date_mmdd = newMmdd;
  if (Object.keys(ov).length) {
    appSettings.worldEventOverrides[originalLabel] = ov;
  } else {
    delete appSettings.worldEventOverrides[originalLabel];
  }
  _editingWorldEv = null;
  saveSettings();
  _renderSettingsWorldEvents();
  renderCalendar();
  toast(t('settings.toast.event_updated'), 'success');
}

function resetWorldEventOverride(originalLabel) {
  if (appSettings.worldEventOverrides) delete appSettings.worldEventOverrides[originalLabel];
  _editingWorldEv = null;
  saveSettings();
  _renderSettingsWorldEvents();
  renderCalendar();
  toast(t('settings.toast.event_reset'), 'success');
}

function toggleWorldEvent(label, visible) {
  if (!appSettings.hiddenWorldEvents) appSettings.hiddenWorldEvents = [];
  if (visible) {
    appSettings.hiddenWorldEvents = appSettings.hiddenWorldEvents.filter(l => l !== label);
  } else {
    if (!appSettings.hiddenWorldEvents.includes(label)) appSettings.hiddenWorldEvents.push(label);
  }
  saveSettings();
  _renderSettingsWorldEvents();
  renderCalendar();
  toast(t('settings.toast.world_event_saved'), 'success');
}

function toggleAllWorldEvents() {
  const hidden = appSettings.hiddenWorldEvents || [];
  const allEvs = _brewingEvents(new Date().getFullYear());
  const seen = new Set(); const unique = allEvs.filter(e => { const k = e.canonical||e.label; if(seen.has(k)) return false; seen.add(k); return true; });
  const allHidden = unique.every(e => hidden.includes(e.canonical || e.label));
  appSettings.hiddenWorldEvents = allHidden ? [] : unique.map(e => e.canonical || e.label);
  saveSettings();
  _renderSettingsWorldEvents();
  renderCalendar();
  toast(t('settings.toast.world_event_saved'), 'success');
}

function _renderSettingsCustomEvents() {
  const list = document.getElementById('settings-custom-ev-list');
  if (!list) return;
  const evs = (S.customEvents || []).sort((a,b) => (a.event_date||'').localeCompare(b.event_date||''));
  if (!evs.length) {
    list.innerHTML = `<div style="color:var(--muted);text-align:center;padding:16px 0;font-size:.85rem">${t('settings.toast.no_custom_events')}</div>`;
    return;
  }
  list.innerHTML = evs.map(ev => {
    const c = ev.color || '#f59e0b';
    const dateStr = ev.event_date
      ? new Date(ev.event_date + 'T00:00:00').toLocaleDateString(_lang || 'fr', { day:'numeric', month:'short', year:'numeric' })
      : '—';
    return `<div style="display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:9px;
        background:var(--card2);border:1px solid ${c}44">
      <span style="font-size:1.1rem;flex-shrink:0">${ev.emoji || '📅'}</span>
      <div style="flex:1;min-width:0">
        <div style="font-weight:600;font-size:.85rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(ev.title)}</div>
        <div style="font-size:.72rem;color:var(--muted)">${dateStr}
          ${ev.recurrence ? ' · 🔁 ' + (() => { try { const _rt = JSON.parse(ev.recurrence).type; return t('cal.' + ({yearly:'rec_yearly_short',yearly_nth_dow:'rec_yearly_short',monthly:'rec_monthly_short',monthly_nth_dow:'rec_monthly_short',weekly:'rec_weekly_short'}[_rt] || 'rec_yearly_short')); } catch(e) { return t('cal.rec_yearly_short'); } })() : ''}
          ${ev.brew_reminder ? ` · <i class="fas fa-bell" style="color:#a855f7"></i> J-${ev.brew_reminder_days ?? appSettings.defaultBrewReminderDays ?? 45}` : ''}
          ${ev.telegram_notify ? ' · <i class="fas fa-paper-plane" style="color:#0088cc"></i>' : ''}
        </div>
      </div>
      <div style="display:flex;gap:5px;flex-shrink:0">
        <button class="btn btn-ghost btn-icon btn-sm" title="${t('common.edit')}"
          onclick="closeSettings();editCustomEvent(${ev.id})">
          <i class="fas fa-pen"></i>
        </button>
        <button class="btn btn-ghost btn-icon btn-sm" style="color:var(--danger)" title="${t('common.delete')}"
          onclick="_settingsDeleteCustomEvent(${ev.id})">
          <i class="fas fa-trash"></i>
        </button>
      </div>
    </div>`;
  }).join('');
}

async function _settingsDeleteCustomEvent(id) {
  if (!await confirmModal(t('settings.toast.custom_event_confirm_delete'), { danger: true })) return;
  try {
    await api('DELETE', `/api/custom_events/${id}`);
    S.customEvents = S.customEvents.filter(x => x.id !== id);
    renderCalendar();
    _renderSettingsCustomEvents();
    toast(t('settings.toast.event_deleted'), 'success');
  } catch(e) { toast(t('settings.toast.err_delete'), 'error'); }
}

function renderSettingsThresholds() {
  const th = appSettings.thresholds || {};
  const tzEl = document.getElementById('tz-offset');
  if (tzEl) tzEl.value = appSettings.tz_offset ?? 0;
  document.getElementById('thresh-malt').value    = th.malt    ?? 1000;
  document.getElementById('thresh-houblon').value = th.houblon ?? 50;
  document.getElementById('thresh-levure').value  = th.levure  ?? 2;
  const lvUnit = document.getElementById('thresh-levure-unit');
  if (lvUnit) lvUnit.textContent = t('inv.unit_sachet') + '(s)';
  // Per-unit thresholds for "autre" — build grid dynamically so labels are always translated
  const au = th.autre_units || { g: 100 };
  const _unitLabel = u => {
    if (u === 'pièce')  return t('settings.thresholds.unit_piece_pl');
    if (u === 'sachet') return t('settings.thresholds.unit_sachet_pl');
    return u;
  };
  const _step = u => ({ kg: 0.1, 'mL': 1, L: 0.1 }[u] ?? 1);
  const grid = document.getElementById('thresh-autre-grid');
  if (grid) {
    grid.innerHTML = AUTRE_UNITS.map(u => `
      <div style="display:flex;align-items:center;gap:6px">
        <label style="width:52px;font-size:.85rem;color:var(--muted)">${_unitLabel(u)}</label>
        <input type="number" id="tau-${u}" min="0" step="${_step(u)}" placeholder="—" style="width:80px" value="${au[u] != null ? au[u] : ''}">
      </div>`).join('');
  }
}

function saveThresholds() {
  const autre_units = {};
  AUTRE_UNITS.forEach(u => {
    const v = document.getElementById(`tau-${u}`)?.value;
    autre_units[u] = v !== '' && v != null ? parseFloat(v) : null;
  });
  appSettings.thresholds = {
    malt:        parseFloat(document.getElementById('thresh-malt').value)    || 1000,
    houblon:     parseFloat(document.getElementById('thresh-houblon').value) || 50,
    levure:      parseFloat(document.getElementById('thresh-levure').value)  || 2,
    autre_units,
  };
  saveSettings();
  renderInventaire();
  toast(t('settings.toast.thresholds_saved'), 'success');
}

const WATER_FIELDS = ['price','ph','ca','mg','na','so4','cl','hco3'];

function renderSettingsWater() {
  const w = appSettings.water || {};
  WATER_FIELDS.forEach(k => {
    const el = document.getElementById(`water-${k}`);
    if (el) el.value = w[k] != null ? w[k] : '';
  });
  const gasEl  = document.getElementById('energy-gas');
  if (gasEl)  gasEl.value  = appSettings.energy?.gas_per_brew  != null ? appSettings.energy.gas_per_brew  : '';
  const elecEl = document.getElementById('energy-elec');
  if (elecEl) elecEl.value = appSettings.energy?.elec_per_brew != null ? appSettings.energy.elec_per_brew : '';
  const ibuFEl = document.getElementById('ibu-formula');
  if (ibuFEl) ibuFEl.value = appSettings.energy?.ibu_formula || 'tinseth';
  const vs = appSettings.vessels || {};
  ['sparge','mash','boil'].forEach(k => {
    const el = document.getElementById(`vessel-${k}`);
    if (el) el.value = vs[k] != null ? vs[k] : '';
  });
  // Restaurer la sélection HubEau
  const hub = appSettings.hubeau || {};
  const deptEl = document.getElementById('hubeau-dept');
  if (deptEl && hub.dept) {
    deptEl.value = hub.dept;
    hubEauDeptChange(hub.commune || null);
  }
}

// ══ HubEau – récupération automatique profil eau ═══════════════════════════

const HUBEAU_PARAMS = [
  { code: '1302', field: 'water-ph',   label: 'pH',           unit: '',      convert: v => Math.round(v * 10) / 10 },
  { code: '1374', field: 'water-ca',   label: 'Calcium',      unit: 'mg/L',  convert: v => Math.round(v) },
  { code: '1372', field: 'water-mg',   label: 'Magnésium',    unit: 'mg/L',  convert: v => Math.round(v) },
  { code: '1375', field: 'water-na',   label: 'Sodium',       unit: 'mg/L',  convert: v => Math.round(v) },
  { code: '1337', field: 'water-cl',   label: 'Chlorures',    unit: 'mg/L',  convert: v => Math.round(v) },
  { code: '1338', field: 'water-so4',  label: 'Sulfates',     unit: 'mg/L',  convert: v => Math.round(v) },
  // 1347 = TAC (Titre Alcalimétrique Complet) en °f → HCO₃⁻ mg/L (×12.2)
  { code: '1347', field: 'water-hco3', label: 'Bicarbonates (via TAC)', unit: 'mg/L', convert: v => Math.round(v * 12.2) },
];

async function hubEauDeptChange(preselect) {
  const dept = document.getElementById('hubeau-dept').value;
  const communeEl = document.getElementById('hubeau-commune');
  const fetchBtn  = document.getElementById('hubeau-fetch-btn');
  document.getElementById('hubeau-result').style.display = 'none';
  communeEl.disabled = true;
  fetchBtn.disabled  = true;
  communeEl.innerHTML = '<option value="">— Commune —</option>';
  if (!dept) { appSettings.hubeau = {}; saveSettings(); return; }
  // Sauvegarder le département (conserver la commune si on est en cours de restauration)
  appSettings.hubeau = { ...(appSettings.hubeau || {}), dept, commune: preselect || null };
  saveSettings();
  communeEl.innerHTML = `<option value="">${t('settings.toast.hubeau_loading')}</option>`;
  try {
    const url = `https://hubeau.eaufrance.fr/api/v1/qualite_eau_potable/resultats_dis?code_departement=${encodeURIComponent(dept)}&code_parametre=1302&size=5000&fields=code_commune,nom_commune`;
    const json = await fetch(url).then(r => r.json());
    const seen = new Set();
    const communes = (json.data || []).filter(c => {
      if (!c.nom_commune || seen.has(c.code_commune)) return false;
      seen.add(c.code_commune); return true;
    }).sort((a, b) => a.nom_commune.localeCompare(b.nom_commune, 'fr'));
    if (!communes.length) {
      communeEl.innerHTML = `<option value="">${t('settings.toast.hubeau_no_commune')}</option>`;
      return;
    }
    communeEl.innerHTML = '<option value="">— Commune —</option>' +
      communes.map(c => `<option value="${c.code_commune}">${c.nom_commune}</option>`).join('');
    // Restaurer la commune sauvegardée si elle est dans la liste
    if (preselect && communes.some(c => c.code_commune === preselect)) {
      communeEl.value = preselect;
      fetchBtn.disabled = false;
      // Mettre à jour le nom en cas de changement de libellé API
      const restored = communes.find(c => c.code_commune === preselect);
      if (restored) {
        appSettings.hubeau = { ...(appSettings.hubeau || {}), communeName: restored.nom_commune };
        saveSettings();
      }
    }
    communeEl.disabled = false;
    communeEl.onchange = () => {
      const code = communeEl.value;
      const name = code ? communeEl.options[communeEl.selectedIndex]?.text?.trim() || null : null;
      fetchBtn.disabled = !code;
      document.getElementById('hubeau-result').style.display = 'none';
      appSettings.hubeau = { ...(appSettings.hubeau || {}), commune: code || null, communeName: name };
      saveSettings();
    };
  } catch (e) {
    communeEl.innerHTML = `<option value="">${t('settings.toast.hubeau_error')}</option>`;
  }
}

async function hubEauFetch() {
  const commune    = document.getElementById('hubeau-commune').value;
  if (!commune) return;
  const communeEl  = document.getElementById('hubeau-commune');
  const communeText = communeEl?.options[communeEl.selectedIndex]?.text?.trim() || commune;
  const btn = document.getElementById('hubeau-fetch-btn');
  btn.disabled = true;
  btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${t('settings.toast.hubeau_loading')}`;
  const resultDiv = document.getElementById('hubeau-result');
  resultDiv.style.display = 'none';
  try {
    const BASE = 'https://hubeau.eaufrance.fr/api/v1/qualite_eau_potable/resultats_dis';
    const fetched = {};
    await Promise.all(HUBEAU_PARAMS.map(async p => {
      const url = `${BASE}?code_commune=${commune}&code_parametre=${p.code}&size=1&fields=resultat_numerique,date_prelevement`;
      const json = await fetch(url).then(r => r.json());
      if (json.data && json.data.length > 0) {
        const d = json.data[0];
        if (d.resultat_numerique != null) {
          fetched[p.code] = { raw: d.resultat_numerique, date: (d.date_prelevement || '').slice(0, 10) };
        }
      }
    }));

    if (!Object.keys(fetched).length) {
      resultDiv.innerHTML = `<p style="font-size:.85rem;color:var(--muted)"><i class="fas fa-circle-info"></i> ${t('settings.water.hubeau_no_data')}</p>`;
    } else {
      let rows = '';
      HUBEAU_PARAMS.forEach(p => {
        if (!fetched[p.code]) return;
        const converted = p.convert(fetched[p.code].raw);
        const curRaw    = document.getElementById(p.field)?.value;
        const current   = curRaw !== '' && curRaw != null ? parseFloat(curRaw) : null;
        const changed   = current === null || current !== converted;
        rows += `<tr data-field="${p.field}" data-value="${converted}">
          <td style="padding:5px 8px;font-size:.83rem">${p.label}</td>
          <td style="padding:5px 8px;font-size:.83rem;color:var(--muted)">${current !== null ? current + (p.unit ? ' ' + p.unit : '') : '—'}</td>
          <td style="padding:5px 8px;font-size:.83rem;font-weight:${changed ? '700' : '400'};color:${changed ? 'var(--success)' : 'inherit'}">${converted}${p.unit ? ' ' + p.unit : ''}</td>
          <td style="padding:5px 8px;font-size:.78rem;color:var(--muted)">${fetched[p.code].date}</td>
          <td style="padding:5px 8px;text-align:center"><input type="checkbox" class="hubeau-chk" ${changed ? 'checked' : ''} style="width:15px;height:15px;cursor:pointer"></td>
        </tr>`;
      });
      resultDiv.innerHTML = `
        <p style="font-size:.78rem;color:var(--muted);margin-bottom:8px"><i class="fas fa-circle-info"></i> ${t('settings.water.hubeau_hint_apply')}</p>
        <table style="width:100%;border-collapse:collapse;margin-bottom:12px">
          <thead>
            <tr style="font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid var(--border)">
              <th style="padding:4px 8px;text-align:left;font-weight:600">${t('settings.water.hubeau_col_param')}</th>
              <th style="padding:4px 8px;text-align:left;font-weight:600">${t('settings.water.hubeau_col_current')}</th>
              <th style="padding:4px 8px;text-align:left;font-weight:600">HubEau</th>
              <th style="padding:4px 8px;text-align:left;font-weight:600">${t('common.date')}</th>
              <th style="padding:4px 8px;text-align:center;font-weight:600">${t('settings.water.hubeau_col_apply')}</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <button class="btn btn-primary btn-sm" onclick="hubEauApply()"><i class="fas fa-check"></i> ${t('settings.water.hubeau_apply_btn')}</button>
          <button class="btn btn-ghost btn-sm" onclick="showHubEauSaveForm('${esc(communeText)}')">
            <i class="fas fa-bookmark"></i> ${t('settings.water.hubeau_save_profile')}
          </button>
          <button class="btn btn-ghost btn-sm" onclick="document.getElementById('hubeau-result').style.display='none'">${t('common.close')}</button>
        </div>
        <div id="hubeau-save-form" style="display:none;margin-top:8px;align-items:center;gap:6px;flex-wrap:wrap">
          <input type="text" id="hubeau-profile-name-inp" style="flex:1;min-width:150px;max-width:240px;font-size:.82rem"
            placeholder="${t('rec.wc_profile_name_ph')}"
            onkeydown="if(event.key==='Enter')saveHubEauAsProfile();if(event.key==='Escape')document.getElementById('hubeau-save-form').style.display='none'">
          <button class="btn btn-sm btn-primary" onclick="saveHubEauAsProfile()"><i class="fas fa-check"></i></button>
          <button class="btn btn-sm btn-ghost" onclick="document.getElementById('hubeau-save-form').style.display='none'"><i class="fas fa-xmark"></i></button>
        </div>`;
    }
  } catch (e) {
    resultDiv.innerHTML = `<p style="font-size:.85rem;color:var(--danger)"><i class="fas fa-triangle-exclamation"></i> ${t('settings.water.hubeau_err')} ${esc(e.message)}</p>`;
  }
  resultDiv.style.display = 'block';
  btn.disabled  = false;
  btn.innerHTML = `<i class="fas fa-satellite-dish"></i> ${t('settings.water.hubeau_fetch')}`;
}

function hubEauApply() {
  document.querySelectorAll('#hubeau-result tr[data-field]').forEach(row => {
    const chk = row.querySelector('.hubeau-chk');
    if (chk && chk.checked) {
      const input = document.getElementById(row.dataset.field);
      if (input) input.value = row.dataset.value;
    }
  });
  document.getElementById('hubeau-result').style.display = 'none';
}

function showHubEauSaveForm(defaultName) {
  const form = document.getElementById('hubeau-save-form');
  const inp  = document.getElementById('hubeau-profile-name-inp');
  if (!form || !inp) return;
  inp.value = defaultName;
  form.style.display = 'flex';
  inp.focus();
  inp.select();
}

function saveHubEauAsProfile() {
  const nameEl = document.getElementById('hubeau-profile-name-inp');
  const name   = nameEl?.value.trim();
  if (!name) { nameEl?.focus(); return; }
  // Lire toutes les valeurs du tableau de résultats (field = "water-ph", "water-ca"…)
  const vals = { ph: null, ca: null, mg: null, na: null, so4: null, cl: null, hco3: null };
  document.querySelectorAll('#hubeau-result tr[data-field]').forEach(row => {
    const key = row.dataset.field.replace('water-', '');
    if (key in vals) vals[key] = parseFloat(row.dataset.value);
  });
  const profile = {
    id:   Date.now().toString(36) + Math.random().toString(36).slice(2, 5),
    name, isSource: true, ...vals,
  };
  if (!appSettings.waterProfiles) appSettings.waterProfiles = [];
  appSettings.waterProfiles.push(profile);
  _syncSettingsToServer();
  document.getElementById('hubeau-save-form').style.display = 'none';
  renderWaterProfileButtons();
  renderWaterProfilesManager();
  toast(t('rec.wc_profile_saved').replace('${name}', name), 'success');
}

// ════════════════════════════════════════════════════════════════════════════

function saveWaterSettings() {
  const w = {};
  WATER_FIELDS.forEach(k => {
    const v = document.getElementById(`water-${k}`)?.value;
    w[k] = v !== '' && v != null ? parseFloat(v) : null;
  });
  appSettings.water = w;
  const gasVal  = document.getElementById('energy-gas')?.value;
  const elecVal = document.getElementById('energy-elec')?.value;
  appSettings.energy = {
    gas_per_brew:  gasVal  !== '' && gasVal  != null ? parseFloat(gasVal)  : null,
    elec_per_brew: elecVal !== '' && elecVal != null ? parseFloat(elecVal) : null,
    ibu_formula:   document.getElementById('ibu-formula')?.value || 'tinseth',
  };
  const vs = {};
  ['sparge','mash','boil'].forEach(k => {
    const v = document.getElementById(`vessel-${k}`)?.value;
    vs[k] = v !== '' && v != null ? parseFloat(v) : null;
  });
  appSettings.vessels = vs;
  saveSettings();
  toast(t('settings.toast.water_saved'), 'success');
}

// ══════════════════════════════════════════════════════════════════════════════
// MODALS
// ══════════════════════════════════════════════════════════════════════════════

// ── Dirty guard ───────────────────────────────────────────────────────────────
// Marks a modal as dirty when the user edits any field inside it.
// Cleared on open (fresh start) and when the save button is clicked.
const _dirtyModals = new Set();

// Track any input/change inside a modal overlay (capture phase)
document.addEventListener('input', e => {
  if (e.target.matches('[data-no-dirty]')) return;
  const ov = e.target.closest('.modal-overlay');
  if (ov) _dirtyModals.add(ov.id);
}, true);
document.addEventListener('change', e => {
  if (e.target.matches('[data-no-dirty]')) return;
  const ov = e.target.closest('.modal-overlay');
  if (ov) _dirtyModals.add(ov.id);
}, true);

// Clear dirty when the primary save button is clicked (before withBtn runs)
document.addEventListener('click', e => {
  const btn = e.target.closest('.modal-foot .btn-primary');
  if (btn) {
    const ov = btn.closest('.modal-overlay');
    if (ov) _dirtyModals.delete(ov.id);
  }
}, true);

function openModal(id) {
  _dirtyModals.delete(id);
  if (id === 'brew-modal') { openBrewModal(); return; }
  const el = document.getElementById(id);
  // Reset any buttons left in spinner state from a previous withBtn call that
  // never completed (e.g. modal closed while the request was still in flight).
  el.querySelectorAll('button[data-orig-html]').forEach(btn => {
    if (btn.querySelector('.fa-spinner')) {
      btn.disabled = false;
      btn.innerHTML = btn.dataset.origHtml;
    }
  });
  el.classList.add('open');
}
function closeModal(id) {
  if (_dirtyModals.has(id)) {
    const el = document.getElementById(id);
    if (el?.querySelector('.modal-foot .btn-primary') && !confirm(t('common.unsaved_confirm'))) return;
    _dirtyModals.delete(id);
  }
  document.getElementById(id).classList.remove('open');
}

// ══════════════════════════════════════════════════════════════════════════════
// LOAD ALL DATA
// ══════════════════════════════════════════════════════════════════════════════
// ── Vérification de version ────────────────────────────────────────────────
async function checkAppVersion() {
  // Cache localStorage 6h pour ne pas interroger GitHub à chaque rechargement
  const CACHE_KEY = '_bh_version_check';
  const cached = (() => { try { return JSON.parse(localStorage.getItem(CACHE_KEY) || 'null'); } catch { return null; } })();
  if (cached && Date.now() - cached.ts < 6 * 3600 * 1000) {
    if (cached.data?.update_available) _showVersionNotif(cached.data);
    return;
  }
  try {
    const data = await api('GET', '/api/version/check');
    localStorage.setItem(CACHE_KEY, JSON.stringify({ ts: Date.now(), data }));
    if (data?.update_available) _showVersionNotif(data);
  } catch (e) {
    // Silencieux — pas critique
  }
}

function _showVersionNotif(data) {
  // Point rouge sur l'icône paramètres
  const dot = document.getElementById('update-dot');
  if (dot) {
    dot.style.display = 'block';
    dot.title = t('settings.updates.app_new_version').replace('${latest}', data.latest);
  }
  // Toast persistant avec lien vers la release (pas d'auto-fermeture)
  const msg = t('settings.updates.app_new_version').replace('${latest}', data.latest);
  const link = data.release_url || 'https://github.com/chatainsim/brewhome/releases';
  const linkLabel = t('settings.updates.app_new_version_link');
  const el = document.createElement('div');
  el.className = 'toast-item toast-info';
  el.innerHTML = `<i class="fas fa-circle-arrow-up"></i><span style="flex:1">${esc(msg)} — <a href="${esc(link)}" target="_blank" rel="noopener" style="color:inherit;font-weight:700;text-decoration:underline">${esc(linkLabel)}</a></span><button class="toast-close" onclick="this.parentElement.remove()" title="${esc(t('common.close'))}">✕</button>`;
  document.getElementById('toast')?.appendChild(el);
  // Pas de timer — l'utilisateur ferme manuellement
}

async function loadAll() {
  // Pré-charger les scripts requis pour le rendu initial EN PARALLÈLE des appels API.
  // Ces scripts contiennent des fonctions appelées par les renderers core (inventaire) :
  //   bh-recettes  → brewCost / recipeCost / ebcToColor  (stats, dashboard cost, spindles)
  //   bh-cave      → beerStockValue / _deplFmt            (dashboard)
  //   bh-calendrier→ renderCalendar                       (badge calendrier)
  //   bh-spindles  → renderSpindles                       (init spindles)
  //   bh-settings  → renderTempSensors                    (init capteurs)
  const lazyForInit = Promise.all([
    _ensureScript('bh-recettes.js'),
    _ensureScript('bh-cave.js'),
    _ensureScript('bh-calendrier.js'),
    _ensureScript('bh-spindles.js'),
    _ensureScript('bh-settings.js'),
  ]);

  // Toutes les données initiales en une seule vague parallèle
  const [
    stats, catalog, bjcp, serverAppSettings, customEvents, drafts, spindles, tempSensors,
    recipes, brews, beers, inventory, sodaKegs, depletion,
  ] = await Promise.all([
    api('GET', '/api/stats'),
    api('GET', '/api/catalog'),
    api('GET', '/api/bjcp'),
    api('GET', '/api/app-settings').catch(() => ({})),
    api('GET', '/api/custom_events').catch(() => []),
    api('GET', '/api/drafts').catch(() => []),
    api('GET', '/api/spindles'),
    api('GET', '/api/temperature'),
    api('GET', '/api/recipes'),
    api('GET', '/api/brews'),
    api('GET', '/api/beers'),
    api('GET', '/api/inventory'),
    api('GET', '/api/soda-kegs'),
    api('GET', '/api/consumption/depletion').catch(() => []),
  ]);

  await lazyForInit; // s'assurer que les scripts sont prêts avant les renders
  _loadSettingsFromServer(serverAppSettings);
  S.catalog      = catalog;
  S.bjcp         = bjcp;
  S.spindles     = spindles;
  S.tempSensors  = tempSensors;
  S.customEvents = customEvents;
  S.drafts       = drafts;
  S.recipes      = recipes;
  S.brews        = brews;
  S.beers        = beers;
  S.inventory    = inventory;
  S.sodaKegs     = sodaKegs;
  S.depletion    = depletion;
  updateNavBadges(stats);
  renderCalendar();     // peuple _calEvStore → badge calendrier
  renderSpindles();
  renderTempSensors();
  renderDashboard();
  // Vérification de version en arrière-plan (non bloquant)
  checkAppVersion();
}

function updateNavBadges(stats) {
  if (!stats) return;
  document.getElementById('nb-inv').textContent = stats.inventory_count;
  document.getElementById('nb-rec').textContent = stats.recipes_count;
  document.getElementById('nb-bra').textContent = stats.brews_count;
  document.getElementById('nb-cav').textContent = stats.beers_count;
  const nbKegs = document.getElementById('nb-kegs');
  if (nbKegs) nbKegs.textContent = stats.kegs_count || '';
  updateBrouillonsBadge();
  updateBackupNavBadge();
}
function updateBackupNavBadge() {
  const btn = document.getElementById('nav-backup-btn');
  const dot = document.getElementById('nav-backup-dot');
  if (!btn || !dot) return;
  const bk = appSettings.github?.backup;
  if (!bk?.enabled && !bk?.lastBackup) { btn.style.display = 'none'; return; }
  btn.style.display = '';
  if (!bk.lastBackup) {
    dot.style.background = 'var(--amber)';
    btn.title = t('dash.wgt_backup_never');
    return;
  }
  const lastDt  = new Date(bk.lastBackup);
  const diffDays = Math.floor((Date.now() - lastDt) / 86400000);
  dot.style.background = diffDays <= 3 ? 'var(--success)' : diffDays <= 10 ? 'var(--amber)' : 'var(--danger)';
  btn.title = lastDt.toLocaleString(_lang === 'en' ? 'en-US' : 'fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}
function updateBrouillonsBadge() {
  const el = document.getElementById('nb-bro');
  if (el) el.textContent = S.drafts.length;
}
function updateCalBadge() {
  const el = document.getElementById('nb-cal');
  if (!el) return;
  const count = _calEvStore.filter(ev => {
    if (!ev.date) return false;
    const d = new Date(ev.date + 'T00:00:00');
    return d.getFullYear() === _calYear && d.getMonth() === _calMonth;
  }).length;
  el.textContent = count || 0;
}

// ══════════════════════════════════════════════════════════════════════════════
// DÉMARRAGE DE L'APPLICATION
// (déplacé depuis script_calendrier.html pour s'exécuter avec les scripts core)
// ══════════════════════════════════════════════════════════════════════════════
(async () => {
  // Appliquer le thème sauvegardé (le bouton est mis à jour par applyAppearance via bh-ui.js)
  const savedTheme = localStorage.getItem('brewhome-theme') || 'dark';
  document.documentElement.setAttribute('data-theme', savedTheme);

  // ── Dropdowns nav tactiles ─────────────────────────────────────────────────
  // Sur mobile, .nav-links a overflow-x:auto ce qui force overflow-y:auto →
  // le dropdown position:absolute est clippé. Solution : position:fixed
  // calculée depuis getBoundingClientRect() pour échapper au scroll container.
  window._closeAllNavDd = function(except) {
    document.querySelectorAll('.nav-group.dd-open').forEach(g => {
      if (g === except) return;
      g.classList.remove('dd-open');
      const dd = g.querySelector('.nav-dropdown');
      if (dd) { dd.style.cssText = ''; }
    });
  };
  const _closeAllNavDd = window._closeAllNavDd;
  document.querySelectorAll('.nav-group').forEach(group => {
    const mainBtn  = group.querySelector(':scope > .nav-btn');
    const dropdown = group.querySelector('.nav-dropdown');
    if (!mainBtn || !dropdown) return;
    mainBtn.addEventListener('touchstart', function(e) {
      if (!group.classList.contains('dd-open')) {
        e.preventDefault();
        _closeAllNavDd(group);
        const rect = mainBtn.getBoundingClientRect();
        dropdown.style.position = 'fixed';
        dropdown.style.top      = rect.bottom + 'px';
        dropdown.style.left     = Math.min(rect.left, window.innerWidth - 170) + 'px';
        dropdown.style.zIndex   = '9999';
        group.classList.add('dd-open');
      }
    }, { passive: false });
  });
  document.addEventListener('touchstart', e => {
    if (!e.target.closest('.nav-group')) _closeAllNavDd();
  }, { passive: true });
  document.addEventListener('click', e => {
    if (!e.target.closest('.nav-group')) _closeAllNavDd();
  });

  await loadAll();
  applyI18n();
  applyAppearance();
  // clearRecipeForm() appelé à la demande lors de la navigation vers recettes
  const brewDateEl = document.getElementById('brew-f-date');
  if (brewDateEl) brewDateEl.value = new Date().toISOString().split('T')[0];
})();
