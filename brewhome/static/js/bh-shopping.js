// ══════════════════════════════════════════════════════════════════════════════
// LISTE DE COURSES
// ══════════════════════════════════════════════════════════════════════════════
let _shopEditingId    = null;
let _shopFilter       = 'all';   // 'all' | 'pending' | 'checked'
let _shopSearch       = '';      // texte de recherche (#11)
let _shopInvSugItems  = [];
let _shopLastBuyToken = null;    // undo token from last buy (#13)
let _shopHistoryLoaded  = false; // (#12)
let _shopHistoryVisible = false; // (#12)
let _shopAlertMissing   = [];    // items below min_stock not yet in list (#14)
let _shopAlertDismissed = new Set(); // ids ignorés dans la bannière pour cette session
let _shopHistoryItems   = [];    // cache de l'historique chargé (#12)
let _shopRecipeMissing  = [];    // computed missing for recipe modal (#11)

// ── Catégorie → couleur / icône ───────────────────────────────────────────────
const _SHOP_CAT_STYLE = {
  malt:    { color: '#f59e0b', icon: 'fa-wheat-awn' },
  houblon: { color: '#22c55e', icon: 'fa-leaf' },
  levure:  { color: '#a78bfa', icon: 'fa-flask' },
  autre:   { color: '#94a3b8', icon: 'fa-box' },
};
function _shopCatStyle(cat) {
  return _SHOP_CAT_STYLE[cat] || _SHOP_CAT_STYLE.autre;
}

// ── Filtre ────────────────────────────────────────────────────────────────────
function setShopFilter(f) {
  _shopFilter = f;
  document.querySelectorAll('.shop-filter-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.filter === f);
  });
  renderShopping();
}

function setShopSearch(val) {
  _shopSearch = val.trim().toLowerCase();
  const searchClearBtn = document.getElementById('shop-search-clear');
  if (searchClearBtn) searchClearBtn.style.display = _shopSearch ? '' : 'none';
  renderShopping();
}

function clearShopSearch() {
  const input = document.getElementById('shop-search-input');
  if (input) input.value = '';
  setShopSearch('');
}

// ── Rendu principal ───────────────────────────────────────────────────────────
function renderShopping() {
  const container = document.getElementById('shopping-list-container');
  const emptyDiv  = document.getElementById('shopping-empty');
  if (!container) return;

  // Resynchronise le bouton historique après un retour sur la page
  const histBtn = document.getElementById('shop-history-btn');
  if (histBtn) {
    histBtn.querySelector('span').textContent =
      _shopHistoryVisible ? t('shop.history_hide') : t('shop.history_show');
  }
  // Resynchronise le champ de recherche (applyI18n réinitialise le placeholder
  // mais pas la valeur ni le bouton ×)
  const searchInput    = document.getElementById('shop-search-input');
  const searchClearBtn = document.getElementById('shop-search-clear');
  if (searchInput && searchInput.value !== (_shopSearch || '')) {
    searchInput.value = _shopSearch;
  }
  if (searchClearBtn) searchClearBtn.style.display = _shopSearch ? '' : 'none';

  let items = S.shoppingList || [];

  // Filtrage
  if (_shopFilter === 'pending') items = items.filter(i => !i.checked);
  if (_shopFilter === 'checked') items = items.filter(i =>  i.checked);
  if (_shopSearch) items = items.filter(i => i.name.toLowerCase().includes(_shopSearch));

  // Compteurs pour boutons d'action (#6 + #10)
  const checkedCount = (S.shoppingList || []).filter(i => i.checked).length;
  const buyBtn   = document.getElementById('shop-buy-btn');
  const clearBtn = document.getElementById('shop-clear-checked-btn');
  const buyLbl   = document.getElementById('shop-buy-label');
  const clearLbl = document.getElementById('shop-clear-label');
  if (buyBtn)   buyBtn.style.display   = checkedCount ? '' : 'none';
  if (clearBtn) clearBtn.style.display = checkedCount ? '' : 'none';
  // Affiche le nombre d'articles cochés dans le label quel que soit le filtre actif
  if (buyLbl)   buyLbl.textContent  = checkedCount ? `${t('shop.buy_checked')} (${checkedCount})`   : t('shop.buy_checked');
  if (clearLbl) clearLbl.textContent = checkedCount ? `${t('shop.clear_checked')} (${checkedCount})` : t('shop.clear_checked');

  if (!items.length) {
    const total = S.shoppingList || [];
    if (_shopSearch) {
      container.innerHTML = `<p style="color:var(--muted);text-align:center;padding:24px">${t('shop.search_empty')}</p>`;
      emptyDiv.style.display = 'none';
    } else if (total.length && _shopFilter !== 'all') {
      container.innerHTML = `<p style="color:var(--muted);text-align:center;padding:24px">${t('shop.filter_empty')}</p>`;
      emptyDiv.style.display = 'none';
    } else {
      container.innerHTML = '';
      emptyDiv.style.display = '';
    }
    _renderShopAlertBanner();
    updateShoppingBadge();
    return;
  }
  emptyDiv.style.display = 'none';

  // Groupement par catégorie
  const CAT_ORDER = ['malt', 'houblon', 'levure', 'autre'];
  const groups = {};
  CAT_ORDER.forEach(c => { groups[c] = []; });
  items.forEach(i => {
    const c = groups.hasOwnProperty(i.category) ? i.category : 'autre';
    groups[c].push(i);
  });

  let html = '';
  CAT_ORDER.forEach(cat => {
    const group = groups[cat];
    if (!group.length) return;
    const cs = _shopCatStyle(cat);
    const catLabel = t('cat.' + cat);
    const groupChecked = group.filter(i => i.checked).length;
    const allInCat = (S.shoppingList || []).filter(i => i.category === cat);
    // ids visibles dans ce groupe (filtrés) pour la checkbox "tout cocher"
    const visibleIds = '[' + group.map(i => i.id).join(',') + ']';
    html += `<div class="shop-cat-section" style="margin-bottom:20px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
        <label style="display:flex;align-items:center;cursor:pointer;flex-shrink:0" title="${t('shop.check_all_cat')}" onclick="event.stopPropagation()">
          <input type="checkbox" class="shop-cat-check" data-cat="${cat}"
            ${groupChecked === group.length ? 'checked' : ''}
            onchange="toggleShopCatCheck(${visibleIds}, this.checked)"
            style="width:15px;height:15px;cursor:pointer;accent-color:${cs.color}">
        </label>
        <span style="width:26px;height:26px;border-radius:8px;background:${cs.color}22;display:flex;align-items:center;justify-content:center">
          <i class="fas ${cs.icon}" style="color:${cs.color};font-size:.8rem"></i>
        </span>
        <span style="font-size:.8rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em">${catLabel}</span>
        <span style="font-size:.75rem;color:var(--muted);background:var(--bg2);border-radius:10px;padding:1px 7px">${allInCat.filter(i=>!i.checked).length}/${allInCat.length}</span>
      </div>
      <div class="shop-items-list" data-cat="${cat}">`;
    group.forEach(item => {
      html += _shopItemHtml(item);
    });
    html += `</div></div>`;
  });

  container.innerHTML = html;

  // Indeterminate sur les checkboxes de catégorie (impossible en HTML pur)
  CAT_ORDER.forEach(cat => {
    const cb = container.querySelector(`.shop-cat-check[data-cat="${cat}"]`);
    if (!cb) return;
    const g = groups[cat];
    const nChecked = g.filter(i => i.checked).length;
    cb.indeterminate = nChecked > 0 && nChecked < g.length;
  });

  _renderShopAlertBanner();
  _initShopDrag();
  updateShoppingBadge();
}

function _shopItemHtml(item) {
  const cs = _shopCatStyle(item.category);
  const checked = item.checked ? 1 : 0;
  const qtyStr = item.quantity ? `${item.quantity}\u202f${item.unit}` : '';
  return `<div class="card shop-item" data-id="${item.id}"
      style="display:flex;align-items:center;gap:12px;padding:10px 14px;margin-bottom:6px;cursor:default;${checked ? 'opacity:.5' : ''}">
    <label style="display:flex;align-items:center;cursor:pointer;flex-shrink:0" onclick="event.stopPropagation()">
      <input type="checkbox" class="shop-check" ${checked ? 'checked' : ''}
        onchange="toggleShopCheck(${item.id}, this.checked)"
        style="width:18px;height:18px;cursor:pointer;accent-color:${cs.color}">
    </label>
    <div style="flex:1;min-width:0;${checked ? 'text-decoration:line-through' : ''}">
      <div style="font-weight:600;font-size:.9rem;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${_esc(item.name)}</div>
      ${qtyStr ? `<div style="font-size:.78rem;color:var(--muted)">${qtyStr}${item.notes ? ' · ' + _esc(item.notes) : ''}</div>` : (item.notes ? `<div style="font-size:.78rem;color:var(--muted)">${_esc(item.notes)}</div>` : '')}
      ${item.inventory_item_id ? `<div style="font-size:.72rem;color:${cs.color};margin-top:2px"><i class="fas fa-link" style="font-size:.65rem"></i> ${t('shop.linked_inv')}</div>` : ''}
    </div>
    <div style="display:flex;gap:6px;flex-shrink:0">
      <button class="btn btn-ghost" style="padding:4px 8px;font-size:.75rem" onclick="openShopModal(${item.id})" title="${t('common.edit')}">
        <i class="fas fa-pen"></i>
      </button>
      <button class="btn btn-ghost" style="padding:4px 8px;font-size:.75rem;color:var(--danger)" onclick="deleteShopItem(${item.id})" title="${t('common.delete')}">
        <i class="fas fa-trash"></i>
      </button>
    </div>
    <div class="drag-handle" style="cursor:grab;color:var(--muted);padding:0 2px;font-size:.85rem" title="${t('shop.drag')}">
      <i class="fas fa-grip-vertical"></i>
    </div>
  </div>`;
}

function _esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Drag & drop (mouse + touch) ───────────────────────────────────────────────
let _shopDragSrc  = null;
let _shopTouchGhost = null;

function _initShopDrag() {
  document.querySelectorAll('#shopping-list-container .shop-item').forEach(el => {
    // ── Mouse drag ────────────────────────────────────────────────────────────
    el.setAttribute('draggable', 'true');
    el.addEventListener('dragstart', e => {
      _shopDragSrc = el;
      e.dataTransfer.effectAllowed = 'move';
      el.style.opacity = '.4';
    });
    el.addEventListener('dragend', () => {
      el.style.opacity = '';
      document.querySelectorAll('#shopping-list-container .shop-item').forEach(x => x.classList.remove('drag-over'));
    });
    el.addEventListener('dragover', e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      if (el !== _shopDragSrc) el.classList.add('drag-over');
    });
    el.addEventListener('dragleave', () => el.classList.remove('drag-over'));
    el.addEventListener('drop', e => {
      e.preventDefault();
      el.classList.remove('drag-over');
      if (!_shopDragSrc || _shopDragSrc === el) return;
      const parent = el.parentNode;
      const items  = [...parent.querySelectorAll('.shop-item')];
      const srcIdx = items.indexOf(_shopDragSrc);
      const tgtIdx = items.indexOf(el);
      if (srcIdx < tgtIdx) parent.insertBefore(_shopDragSrc, el.nextSibling);
      else                 parent.insertBefore(_shopDragSrc, el);
      _syncShopOrder();
    });

    // ── Touch drag (#8) ───────────────────────────────────────────────────────
    _addTouchDrag(el);
  });
}

function _addTouchDrag(el) {
  let _offsetX = 0, _offsetY = 0;

  el.addEventListener('touchstart', e => {
    // Ignorer si l'utilisateur touche un bouton ou une checkbox dans la carte
    if (e.target.closest('button, input, label')) return;
    const t = e.touches[0];
    const rect = el.getBoundingClientRect();
    _offsetX = t.clientX - rect.left;
    _offsetY = t.clientY - rect.top;
    _shopDragSrc = el;

    // Créer un fantôme visuel
    _shopTouchGhost = el.cloneNode(true);
    Object.assign(_shopTouchGhost.style, {
      position:      'fixed',
      left:          rect.left + 'px',
      top:           rect.top  + 'px',
      width:         rect.width + 'px',
      opacity:       '0.8',
      pointerEvents: 'none',
      zIndex:        '9999',
      boxShadow:     '0 8px 24px rgba(0,0,0,.35)',
      transform:     'scale(1.02)',
      transition:    'none',
    });
    document.body.appendChild(_shopTouchGhost);
    el.style.opacity = '0.3';
  }, { passive: true });

  el.addEventListener('touchmove', e => {
    if (!_shopTouchGhost || _shopDragSrc !== el) return;
    e.preventDefault();
    const t = e.touches[0];
    _shopTouchGhost.style.left = (t.clientX - _offsetX) + 'px';
    _shopTouchGhost.style.top  = (t.clientY - _offsetY) + 'px';

    // Surligner la cible sous le doigt
    document.querySelectorAll('#shopping-list-container .shop-item').forEach(x => {
      if (x === el) return;
      const r = x.getBoundingClientRect();
      x.classList.toggle('drag-over', t.clientY >= r.top && t.clientY <= r.bottom);
    });
  }, { passive: false });

  el.addEventListener('touchend', e => {
    if (!_shopTouchGhost || _shopDragSrc !== el) return;
    _shopTouchGhost.remove();
    _shopTouchGhost = null;
    el.style.opacity = '';

    const t = e.changedTouches[0];
    let target = null;
    document.querySelectorAll('#shopping-list-container .shop-item').forEach(x => {
      x.classList.remove('drag-over');
      if (x === el) return;
      const r = x.getBoundingClientRect();
      if (t.clientY >= r.top && t.clientY <= r.bottom) target = x;
    });

    if (target) {
      const parent = el.parentNode;
      const items  = [...parent.querySelectorAll('.shop-item')];
      const srcIdx = items.indexOf(el);
      const tgtIdx = items.indexOf(target);
      if (srcIdx < tgtIdx) parent.insertBefore(el, target.nextSibling);
      else                 parent.insertBefore(el, target);
      _syncShopOrder();
    }
    _shopDragSrc = null;
  }, { passive: true });
}

async function _syncShopOrder() {
  const allItems = [...document.querySelectorAll('#shopping-list-container .shop-item')];
  const payload  = allItems.map((el, i) => ({ id: parseInt(el.dataset.id), sort_order: i }));
  // Sauvegarde de l'ordre précédent pour rollback
  const prevOrder = S.shoppingList.map(it => ({ id: it.id, sort_order: it.sort_order }));
  // Mise à jour optimiste
  const idxById = {};
  payload.forEach(p => { idxById[p.id] = p.sort_order; });
  S.shoppingList.forEach(item => {
    if (idxById[item.id] !== undefined) item.sort_order = idxById[item.id];
  });
  S.shoppingList.sort((a, b) => (a.sort_order ?? 9999) - (b.sort_order ?? 9999));
  try {
    await api('PUT', '/api/shopping-list/reorder', payload);
  } catch(e) {
    // Rollback état local et re-rendu
    const prevById = {};
    prevOrder.forEach(p => { prevById[p.id] = p.sort_order; });
    S.shoppingList.forEach(item => {
      if (prevById[item.id] !== undefined) item.sort_order = prevById[item.id];
    });
    S.shoppingList.sort((a, b) => (a.sort_order ?? 9999) - (b.sort_order ?? 9999));
    renderShopping();
    toast(t('shop.err_save_order'), 'error');
  }
}

// ── Toggle coché ──────────────────────────────────────────────────────────────
async function toggleShopCheck(id, checked) {
  const item = (S.shoppingList || []).find(i => i.id === id);
  if (!item) return;
  item.checked = checked ? 1 : 0;
  renderShopping();
  try {
    await api('PUT', `/api/shopping-list/${id}`, { checked: checked ? 1 : 0 });
  } catch(e) {
    item.checked = checked ? 0 : 1; // rollback
    renderShopping();
    toast(t('shop.err_update'), 'error');
  }
}

// ── Tout cocher / décocher une catégorie (#7) ─────────────────────────────────
async function toggleShopCatCheck(ids, shouldCheck) {
  const toToggle = (S.shoppingList || []).filter(i =>
    ids.includes(i.id) && Boolean(i.checked) !== shouldCheck
  );
  if (!toToggle.length) return;
  // Mise à jour optimiste
  toToggle.forEach(item => { item.checked = shouldCheck ? 1 : 0; });
  renderShopping();
  try {
    await api('PUT', '/api/shopping-list/bulk-check', {
      ids:     toToggle.map(i => i.id),
      checked: shouldCheck ? 1 : 0,
    });
  } catch(e) {
    toToggle.forEach(item => { item.checked = shouldCheck ? 0 : 1; });
    renderShopping();
    toast(t('shop.err_update'), 'error');
  }
}

// ── Valider les achats (#13 — avec token d'annulation) ───────────────────────
async function shopBuyChecked() {
  const count = (S.shoppingList || []).filter(i => i.checked).length;
  if (!count) return;
  const ok = await confirmModal(
    t('shop.buy_confirm').replace('${n}', count)
  );
  if (!ok) return;
  try {
    const res = await api('POST', '/api/shopping-list/buy');
    _shopLastBuyToken = { bought_ids: res.bought_ids, inv_changes: res.inv_changes };
    S.shoppingList = await api('GET', '/api/shopping-list');
    S.inventory = []; // forcer rechargement inventaire
    // Invalider l'historique pour qu'il se recharge à la prochaine ouverture
    _shopHistoryLoaded = false;
    renderShopping();
    _toastWithUndo(t('shop.bought').replace('${n}', res.count));
  } catch(e) { toast(t('shop.err_buy'), 'error'); }
}

// ── Toast avec bouton Annuler (#13) ───────────────────────────────────────────
function _toastWithUndo(msg, duration = 8000) {
  const existing = document.getElementById('shop-undo-toast');
  if (existing) existing.remove();
  const el = document.createElement('div');
  el.id = 'shop-undo-toast';
  el.style.cssText = [
    'position:fixed', 'bottom:24px', 'left:50%', 'transform:translateX(-50%)',
    'background:var(--bg2)', 'border:1px solid var(--border)', 'border-radius:10px',
    'padding:12px 16px', 'display:flex', 'align-items:center', 'gap:12px',
    'box-shadow:0 4px 20px rgba(0,0,0,.25)', 'z-index:10000', 'max-width:90vw',
  ].join(';');
  el.innerHTML = `<span style="color:var(--text);font-size:.9rem">${msg}</span>
    <button class="btn btn-ghost" style="padding:4px 10px;font-size:.8rem;white-space:nowrap" onclick="shopUndoBuy()">
      <i class="fas fa-rotate-left"></i> ${t('shop.undo')}
    </button>`;
  document.body.appendChild(el);
  const timer = setTimeout(() => el.remove(), duration);
  el._clearTimer = () => { clearTimeout(timer); el.remove(); };
}

// ── Annuler le dernier achat (#13) ────────────────────────────────────────────
async function shopUndoBuy() {
  const toastEl = document.getElementById('shop-undo-toast');
  if (toastEl?._clearTimer) toastEl._clearTimer();
  if (!_shopLastBuyToken) { toast(t('shop.undo_expired'), 'error'); return; }
  try {
    await api('POST', '/api/shopping-list/undo-buy', _shopLastBuyToken);
    _shopLastBuyToken = null;
    S.shoppingList = await api('GET', '/api/shopping-list');
    S.inventory = [];
    _shopHistoryLoaded = false;
    renderShopping();
    toast(t('shop.undone'));
  } catch(e) { toast(t('shop.err_undo'), 'error'); }
}

// ── Supprimer les cochés ──────────────────────────────────────────────────────
async function shopClearChecked() {
  const checked = (S.shoppingList || []).filter(i => i.checked);
  if (!checked.length) return;
  const ok = await confirmModal(
    t('shop.clear_confirm').replace('${n}', checked.length)
  );
  if (!ok) return;
  try {
    await Promise.all(checked.map(i => api('DELETE', `/api/shopping-list/${i.id}`)));
    S.shoppingList = S.shoppingList.filter(i => !i.checked);
    renderShopping();
    toast(t('shop.cleared'));
  } catch(e) { toast(t('shop.err_delete'), 'error'); }
}

// ── Supprimer un article ──────────────────────────────────────────────────────
async function deleteShopItem(id) {
  const ok = await confirmModal(t('shop.confirm_delete'));
  if (!ok) return;
  try {
    await api('DELETE', `/api/shopping-list/${id}`);
    S.shoppingList = S.shoppingList.filter(i => i.id !== id);
    renderShopping();
    toast(t('shop.deleted'));
  } catch(e) { toast(t('shop.err_delete'), 'error'); }
}

// ── Modale add / edit ─────────────────────────────────────────────────────────
function openShopModal(id = null) {
  _shopEditingId = id;
  const item = id ? (S.shoppingList || []).find(i => i.id === id) : null;

  document.getElementById('shop-modal-title').textContent = id ? t('shop.modal_edit') : t('shop.modal_add');
  document.getElementById('shop-inv-search').value = '';
  document.getElementById('shop-inv-sug').innerHTML = '';
  document.getElementById('shop-f-name').value    = item?.name     || '';
  document.getElementById('shop-f-cat').value     = item?.category || 'malt';
  document.getElementById('shop-f-qty').value     = item?.quantity ?? 1;
  document.getElementById('shop-f-unit').value    = item?.unit     || 'g';
  document.getElementById('shop-f-notes').value   = item?.notes    || '';
  document.getElementById('shop-f-inv-id').value  = item?.inventory_item_id || '';

  applyI18n(document.getElementById('shop-modal'));
  openModal('shop-modal');
  document.getElementById('shop-f-name').focus();
}

// ── Autocomplete inventaire (#9 — clavier) ────────────────────────────────────
let _shopInvSugIdx = -1;

function shopInvSuggest(input) {
  _shopInvSugIdx = -1;
  const q = input.value.toLowerCase().trim();
  const sug = document.getElementById('shop-inv-sug');
  const items = (S.inventory || []).filter(i => !i.archived && !i.deleted_at &&
    (i.name.toLowerCase().includes(q) || i.category.toLowerCase().includes(q))
  ).slice(0, 8);
  _shopInvSugItems = items;
  if (!items.length) { sug.style.display = 'none'; return; }
  sug.innerHTML = items.map((it, idx) => {
    const cs = _shopCatStyle(it.category);
    return `<div class="ing-suggest-item" data-sidx="${idx}" onmousedown="shopPickInv(${idx})" style="display:flex;align-items:center;gap:8px">
      <i class="fas ${cs.icon}" style="color:${cs.color};width:14px"></i>
      <span>${_esc(it.name)}</span>
      <span style="margin-left:auto;font-size:.75rem;color:var(--muted)">${t('cat.' + it.category)}</span>
    </div>`;
  }).join('');
  sug.style.display = 'block';
}

function shopInvKeydown(e) {
  const sug = document.getElementById('shop-inv-sug');
  if (!sug || sug.style.display === 'none') return;
  const rows = [...sug.querySelectorAll('.ing-suggest-item')];
  if (!rows.length) return;

  if (e.key === 'ArrowDown') {
    e.preventDefault();
    _shopInvSugIdx = Math.min(_shopInvSugIdx + 1, rows.length - 1);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    _shopInvSugIdx = Math.max(_shopInvSugIdx - 1, 0);
  } else if (e.key === 'Enter') {
    e.preventDefault();
    shopPickInv(_shopInvSugIdx >= 0 ? _shopInvSugIdx : 0);
    return;
  } else if (e.key === 'Escape') {
    closeShopInvSuggest();
    return;
  } else {
    return;
  }

  // Mise à jour visuelle du surlignage
  rows.forEach((r, i) => r.classList.toggle('active', i === _shopInvSugIdx));
  rows[_shopInvSugIdx]?.scrollIntoView({ block: 'nearest' });
}

function shopPickInv(idx) {
  const it = _shopInvSugItems[idx];
  if (!it) return;
  document.getElementById('shop-f-name').value    = it.name;
  document.getElementById('shop-f-cat').value     = it.category;
  document.getElementById('shop-f-unit').value    = it.unit || 'g';
  document.getElementById('shop-f-inv-id').value  = it.id;
  document.getElementById('shop-inv-search').value = '';
  _shopInvSugIdx = -1;
  closeShopInvSuggest();
}

function closeShopInvSuggest() {
  _shopInvSugIdx = -1;
  const sug = document.getElementById('shop-inv-sug');
  if (sug) sug.style.display = 'none';
}

// ── Sauvegarde ────────────────────────────────────────────────────────────────
async function saveShopItem() {
  const name = document.getElementById('shop-f-name').value.trim();
  const cat  = document.getElementById('shop-f-cat').value;
  if (!name) { toast(t('shop.err_name'), 'error'); return; }

  const _rawQty = parseFloat(document.getElementById('shop-f-qty').value);
  const quantity = Number.isFinite(_rawQty) && _rawQty >= 0 ? _rawQty : 1;

  const payload = {
    name,
    category:          cat,
    quantity,
    unit:              document.getElementById('shop-f-unit').value,
    notes:             document.getElementById('shop-f-notes').value.trim() || null,
    inventory_item_id: parseInt(document.getElementById('shop-f-inv-id').value) || null,
  };

  // Détection doublon à la création uniquement
  if (!_shopEditingId) {
    const nameLower = name.toLowerCase();
    const duplicate = (S.shoppingList || []).find(i => i.name.toLowerCase() === nameLower);
    if (duplicate) {
      const ok = await confirmModal(
        t('shop.duplicate_confirm').replace('${name}', name)
      );
      if (!ok) return;
    }
  }

  try {
    if (_shopEditingId) {
      const updated = await api('PUT', `/api/shopping-list/${_shopEditingId}`, payload);
      const idx = S.shoppingList.findIndex(i => i.id === _shopEditingId);
      if (idx !== -1) S.shoppingList[idx] = updated;
      toast(t('shop.updated'));
    } else {
      const created = await api('POST', '/api/shopping-list', payload);
      S.shoppingList.push(created);
      toast(t('shop.added'));
    }
    closeModal('shop-modal');
    renderShopping();
  } catch(e) { toast(t('shop.err_save'), 'error'); }
}

// ── Historique des achats (#12) ───────────────────────────────────────────────
async function toggleShopHistory() {
  const panel = document.getElementById('shop-history-panel');
  const btn   = document.getElementById('shop-history-btn');
  if (!panel) return;
  _shopHistoryVisible = !_shopHistoryVisible;
  if (btn) btn.querySelector('span').textContent = _shopHistoryVisible ? t('shop.history_hide') : t('shop.history_show');
  panel.style.display = _shopHistoryVisible ? '' : 'none';
  if (_shopHistoryVisible && !_shopHistoryLoaded) {
    panel.innerHTML = `<p style="color:var(--muted);text-align:center;padding:16px">${t('common.loading')}</p>`;
    try {
      const items = await api('GET', '/api/shopping-list/history');
      _shopHistoryLoaded = true;
      _renderShopHistory(items, panel);
    } catch(e) {
      panel.innerHTML = `<p style="color:var(--danger);text-align:center;padding:16px">${t('shop.err_history')}</p>`;
    }
  }
}

function _renderShopHistory(items, panel) {
  _shopHistoryItems = items;
  if (!items.length) {
    panel.innerHTML = `<p style="color:var(--muted);text-align:center;padding:16px">${t('shop.history_empty')}</p>`;
    return;
  }
  panel.innerHTML = `<div style="font-size:.8rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">${t('shop.history_title')}</div>` +
    items.map((it, idx) => {
      const cs = _shopCatStyle(it.category);
      const date = new Date(it.bought_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
      const qtyStr = it.quantity ? `${it.quantity}\u202f${it.unit}` : '';
      return `<div class="card" style="display:flex;align-items:center;gap:12px;padding:10px 14px;margin-bottom:6px;opacity:.75">
        <span style="width:24px;height:24px;border-radius:7px;background:${cs.color}22;display:flex;align-items:center;justify-content:center;flex-shrink:0">
          <i class="fas ${cs.icon}" style="color:${cs.color};font-size:.72rem"></i>
        </span>
        <div style="flex:1;min-width:0">
          <div style="font-weight:600;font-size:.88rem">${_esc(it.name)}</div>
          ${qtyStr ? `<div style="font-size:.76rem;color:var(--muted)">${qtyStr}</div>` : ''}
        </div>
        <div style="font-size:.75rem;color:var(--muted);flex-shrink:0">${date}</div>
        <button class="btn btn-ghost" style="padding:3px 8px;font-size:.72rem;flex-shrink:0"
          onclick="shopReaddFromHistory(${idx})" title="${t('shop.readd')}">
          <i class="fas fa-rotate-left"></i>
        </button>
      </div>`;
    }).join('');
}

async function shopReaddFromHistory(idx) {
  const it = _shopHistoryItems[idx];
  if (!it) return;
  const nameLower = it.name.toLowerCase();
  const duplicate = (S.shoppingList || []).find(i => i.name.toLowerCase() === nameLower);
  if (duplicate) {
    const ok = await confirmModal(t('shop.duplicate_confirm').replace('${name}', it.name));
    if (!ok) return;
  }
  try {
    const created = await api('POST', '/api/shopping-list', {
      name:              it.name,
      category:          it.category,
      quantity:          it.quantity,
      unit:              it.unit,
      notes:             it.notes || null,
      inventory_item_id: it.inventory_item_id || null,
    });
    S.shoppingList.push(created);
    renderShopping();
    toast(t('shop.readded').replace('${name}', it.name));
  } catch(e) { toast(t('shop.err_save'), 'error'); }
}

// ── Alertes stock minimum (#14) ───────────────────────────────────────────────
function _renderShopAlertBanner() {
  const banner = document.getElementById('shop-alert-banner');
  if (!banner) return;
  const alerts = (S.inventory || []).filter(i =>
    !i.deleted_at && !i.archived &&
    i.min_stock != null && i.min_stock > 0 &&
    i.quantity < i.min_stock
  );
  if (!alerts.length) { banner.style.display = 'none'; return; }
  const alreadyOnList = new Set((S.shoppingList || []).map(i => i.inventory_item_id).filter(Boolean));
  _shopAlertMissing = alerts.filter(i =>
    !alreadyOnList.has(i.id) && !_shopAlertDismissed.has(i.id)
  );
  if (!_shopAlertMissing.length) { banner.style.display = 'none'; return; }
  banner.style.display = '';

  const rows = _shopAlertMissing.map(i => {
    const cs      = _shopCatStyle(i.category);
    const missing = Math.max(0, i.min_stock - i.quantity);
    const missStr = `${missing}\u202f${i.unit}`;
    return `<div style="display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid rgba(239,68,68,.1)">
      <span style="width:20px;height:20px;border-radius:5px;background:${cs.color}22;display:flex;align-items:center;justify-content:center;flex-shrink:0">
        <i class="fas ${cs.icon}" style="color:${cs.color};font-size:.65rem"></i>
      </span>
      <span style="flex:1;font-size:.85rem;font-weight:600">${_esc(i.name)}</span>
      <span style="font-size:.75rem;color:var(--danger);flex-shrink:0">−${missStr}</span>
      <button class="btn btn-ghost" style="padding:2px 8px;font-size:.72rem;flex-shrink:0"
        onclick="shopAddAlert(${i.id})">
        <i class="fas fa-cart-plus"></i> ${t('shop.alert_add_one')}
      </button>
      <button class="btn btn-ghost" style="padding:2px 6px;font-size:.72rem;flex-shrink:0;color:var(--muted)"
        onclick="shopDismissAlert(${i.id})" title="${t('shop.alert_dismiss')}">
        <i class="fas fa-xmark"></i>
      </button>
    </div>`;
  }).join('');

  banner.innerHTML = `
    <div class="card" style="background:rgba(239,68,68,.06);border:1px solid rgba(239,68,68,.2);padding:12px 16px;margin-bottom:16px">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px">
        <span style="font-weight:600;font-size:.85rem;color:var(--danger)">
          <i class="fas fa-triangle-exclamation"></i> ${t('shop.alert_title').replace('${n}', _shopAlertMissing.length)}
        </span>
        <button class="btn btn-ghost" style="font-size:.75rem;padding:2px 8px;color:var(--danger);border-color:rgba(239,68,68,.3)"
          onclick="withBtn(this, shopAddAlerts)">
          <i class="fas fa-cart-plus"></i> ${t('shop.alert_add_all')}
        </button>
      </div>
      <div>${rows}</div>
    </div>`;
}

async function shopAddAlert(invId) {
  const item = _shopAlertMissing.find(i => i.id === invId);
  if (!item) return;
  try {
    const created = await api('POST', '/api/shopping-list', {
      name:              item.name,
      category:          item.category,
      quantity:          Math.max(0, item.min_stock - item.quantity),
      unit:              item.unit,
      inventory_item_id: item.id,
    });
    S.shoppingList.push(created);
    renderShopping(); // re-rend la bannière et la liste
    toast(t('shop.alert_added').replace('${name}', item.name));
  } catch(e) { toast(t('shop.err_save'), 'error'); }
}

function shopDismissAlert(invId) {
  _shopAlertDismissed.add(invId);
  _renderShopAlertBanner();
}

async function shopAddAlerts() {
  if (!_shopAlertMissing.length) return;
  try {
    const created = await Promise.all(_shopAlertMissing.map(i =>
      api('POST', '/api/shopping-list', {
        name:              i.name,
        category:          i.category,
        quantity:          Math.max(0, i.min_stock - i.quantity),
        unit:              i.unit,
        inventory_item_id: i.id,
      })
    ));
    created.forEach(c => S.shoppingList.push(c));
    _shopAlertMissing = [];
    renderShopping();
    toast(t('shop.alert_added_all').replace('${n}', created.length));
  } catch(e) { toast(t('shop.err_save'), 'error'); }
}

// ── Ajout depuis une recette (#11) ────────────────────────────────────────────
function openShopRecipeModal() {
  const list = document.getElementById('shop-recipe-list');
  if (!list) return;
  const recipes = S.recipes || [];
  list.innerHTML = recipes.length
    ? recipes.map(r =>
        `<label style="display:flex;align-items:center;gap:8px;padding:5px 4px;cursor:pointer;border-radius:6px">
          <input type="checkbox" class="shop-recipe-sel-chk" value="${r.id}"
            onchange="_onShopRecipeSelChange()"
            style="width:14px;height:14px;cursor:pointer;flex-shrink:0">
          <span style="font-size:.87rem">${_esc(r.name)}</span>
        </label>`
      ).join('')
    : `<p style="color:var(--muted);font-size:.85rem;padding:8px 4px">${t('common.no_results')}</p>`;
  _shopRecipeMissing = [];
  const panel  = document.getElementById('shop-recipe-missing');
  if (panel) panel.innerHTML = '';
  const addBtn = document.getElementById('shop-recipe-add-btn');
  if (addBtn) { addBtn.style.display = 'none'; }
  applyI18n(document.getElementById('shop-recipe-modal'));
  openModal('shop-recipe-modal');
}

function _onShopRecipeSelChange() {
  const ids = [...document.querySelectorAll('.shop-recipe-sel-chk:checked')]
    .map(cb => parseInt(cb.value));
  if (!ids.length) {
    _shopRecipeMissing = [];
    const panel = document.getElementById('shop-recipe-missing');
    if (panel) panel.innerHTML = '';
    _updateShopRecipeBtn();
    return;
  }
  const recipes = (S.recipes || []).filter(r => ids.includes(r.id));
  _shopRecipeMissing = _computeMultiRecipeMissing(recipes);
  _renderShopRecipeMissing(_shopRecipeMissing);
}

function _computeMultiRecipeMissing(recipes) {
  // Cumule les besoins de toutes les recettes par ingrédient (même nom = même lot)
  const needed = new Map(); // nameLower → {name, category, needed_v, dim, unit}
  for (const recipe of recipes) {
    for (const ing of (recipe.ingredients || [])) {
      if (!ing.name) continue;
      const key  = ing.name.toLowerCase();
      const base = toBaseVal(ing.quantity || 0, ing.unit || 'g');
      if (!needed.has(key)) {
        needed.set(key, { name: ing.name, category: ing.category || 'autre',
                          needed_v: 0, dim: base.dim, unit: ing.unit || 'g' });
      }
      const entry = needed.get(key);
      if (entry.dim === base.dim) entry.needed_v += base.v;
    }
  }

  const invByName = {};
  (S.inventory || []).forEach(i => {
    if (!i.deleted_at && !i.archived) invByName[i.name.toLowerCase()] = i;
  });

  const result = [];
  for (const [, entry] of needed) {
    const inv      = invByName[entry.name.toLowerCase()];
    const haveBase = inv ? toBaseVal(inv.quantity, inv.unit) : { v: 0, dim: entry.dim };
    if (haveBase.dim !== entry.dim) continue;
    const diffV = entry.needed_v - haveBase.v;
    if (diffV <= 0) continue;
    const [diffAmt, diffUnit] = _shopBaseToDisplay(diffV, entry.dim);
    const [needAmt, needUnit] = _shopBaseToDisplay(entry.needed_v, entry.dim);
    result.push({
      name:              entry.name,
      category:          entry.category,
      quantity:          needAmt,
      unit:              needUnit,
      inv_qty:           inv ? inv.quantity : 0,
      inv_unit:          inv ? inv.unit : entry.unit,
      inventory_item_id: inv ? inv.id : null,
      diff_amt:          diffAmt,
      diff_unit:         diffUnit,
    });
  }
  return result;
}

function _shopBaseToDisplay(baseVal, dim) {
  if (dim === 'weight') {
    if (baseVal >= 1000) return [Math.round(baseVal / 10) / 100, 'kg'];
    return [Math.round(baseVal * 10) / 10, 'g'];
  }
  if (dim === 'volume') {
    if (baseVal >= 1000) return [Math.round(baseVal / 10) / 100, 'L'];
    return [Math.round(baseVal * 10) / 10, 'mL'];
  }
  return [Math.round(baseVal * 100) / 100, ''];
}

function _renderShopRecipeMissing(missing) {
  const panel  = document.getElementById('shop-recipe-missing');
  const addBtn = document.getElementById('shop-recipe-add-btn');
  if (!panel) return;
  if (!missing.length) {
    panel.innerHTML = `<p style="color:var(--success,#22c55e);padding:12px 0;text-align:center">
      <i class="fas fa-check-circle"></i> ${t('shop.recipe_all_ok')}</p>`;
    if (addBtn) addBtn.style.display = 'none';
    return;
  }
  if (addBtn) {
    addBtn.style.display = '';
    addBtn.querySelector('span').textContent = t('shop.recipe_add_n').replace('${n}', missing.length);
  }
  panel.innerHTML = missing.map((ing, idx) => {
    const cs       = _shopCatStyle(ing.category);
    const haveStr  = `${ing.inv_qty}\u202f${ing.inv_unit}`;
    const needStr  = `${ing.quantity}\u202f${ing.unit}`;
    const diffStr  = `+${ing.diff_amt}\u202f${ing.diff_unit}`;
    return `<label style="display:flex;align-items:center;gap:10px;padding:8px;border-radius:8px;cursor:pointer;margin-bottom:4px;background:var(--bg2)">
      <input type="checkbox" class="shop-recipe-chk" data-idx="${idx}" checked
        onchange="_updateShopRecipeBtn()"
        style="width:15px;height:15px">
      <span style="width:22px;height:22px;border-radius:6px;background:${cs.color}22;display:flex;align-items:center;justify-content:center;flex-shrink:0">
        <i class="fas ${cs.icon}" style="color:${cs.color};font-size:.7rem"></i>
      </span>
      <div style="flex:1;min-width:0">
        <div style="font-weight:600;font-size:.87rem">${_esc(ing.name)}</div>
        <div style="font-size:.75rem;color:var(--muted)">${t('shop.have')}: ${haveStr} · ${t('shop.field_qty')}: ${needStr} → <span style="color:var(--danger)">${diffStr}</span></div>
      </div>
    </label>`;
  }).join('');
}

function _updateShopRecipeBtn() {
  const n   = document.querySelectorAll('#shop-recipe-missing .shop-recipe-chk:checked').length;
  const btn = document.getElementById('shop-recipe-add-btn');
  if (!btn) return;
  btn.querySelector('span').textContent = t('shop.recipe_add_n').replace('${n}', n);
  btn.disabled = n === 0;
}

async function shopAddFromRecipe() {
  const panel   = document.getElementById('shop-recipe-missing');
  const checked = _shopRecipeMissing.filter((_, idx) => {
    const cb = panel?.querySelector(`.shop-recipe-chk[data-idx="${idx}"]`);
    return cb ? cb.checked : true;
  });
  if (!checked.length) return;
  try {
    const created = await Promise.all(checked.map(ing =>
      api('POST', '/api/shopping-list', {
        name:              ing.name,
        category:          ing.category,
        quantity:          ing.diff_amt,
        unit:              ing.diff_unit || 'g',
        inventory_item_id: ing.inventory_item_id,
      })
    ));
    created.forEach(c => S.shoppingList.push(c));
    closeModal('shop-recipe-modal');
    renderShopping();
    toast(t('shop.recipe_added').replace('${n}', created.length));
  } catch(e) { toast(t('shop.err_save'), 'error'); }
}

// ── Export / Partage natif (#13) ──────────────────────────────────────────────
function shopExport() {
  const all = S.shoppingList || [];
  if (!all.length) { toast(t('shop.empty_title'), 'error'); return; }

  const CAT_ORDER = ['malt', 'houblon', 'levure', 'autre'];
  const date = new Date().toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' });
  let text = `${t('shop.title')} — ${date}\n${'─'.repeat(42)}\n`;

  CAT_ORDER.forEach(cat => {
    const group = all.filter(i => i.category === cat);
    if (!group.length) return;
    text += `\n${t('cat.' + cat).toUpperCase()}\n`;
    group.forEach(i => {
      const check  = i.checked ? '☑' : '☐';
      const qty    = i.quantity ? `${i.quantity} ${i.unit}` : '';
      const notes  = i.notes ? ` (${i.notes})` : '';
      text += `  ${check}  ${i.name.padEnd(26)} ${qty.padStart(8)}${notes}\n`;
    });
  });

  const shareText = text.trim();
  const fileName  = `liste-courses-${new Date().toISOString().slice(0, 10)}.txt`;

  if (navigator.share) {
    navigator.share({ title: t('shop.title'), text: shareText })
      .catch(() => _shopDownload(shareText, fileName));
  } else {
    _shopDownload(shareText, fileName);
  }
}

function _shopDownload(text, fileName) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── Badge ─────────────────────────────────────────────────────────────────────
function updateShoppingBadge() {
  const el = document.getElementById('nb-shop');
  if (!el) return;
  const n = (S.shoppingList || []).filter(i => !i.checked).length;
  el.textContent = n || '';
}