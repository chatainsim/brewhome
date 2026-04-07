// ══════════════════════════════════════════════════════════════════════════════
// ── CAVE ─────────────────────────────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════

// Auto-push vitrine après modification de la cave (debounce 5 s, silencieux)
const _autoPushVitrineDebounced = debounce(function() {
  const targets = ((appSettings.github || {}).vitrine?.targets || []).filter(t => t.repo && t.pat);
  if (!targets.length) return;
  pushVitrine(false, true);
}, 5000);
function beerStockHtml(current, initial, label) {
  const cur = current || 0;
  const ini = initial || 0;
  const consumed = ini > cur;
  const pct = ini > 0 ? Math.round(cur / ini * 100) : 100;
  // color: green if plenty, amber if below half, red if almost empty
  const barColor = pct > 50 ? 'var(--success)' : pct > 20 ? '#f59e0b' : 'var(--danger)';
  const initLabel = consumed
    ? `<span style="color:var(--muted);font-size:.8rem">/${ini}</span>`
    : '';
  const bar = consumed
    ? `<div class="bottle-bar"><div class="bottle-bar-fill" style="width:${pct}%;background:${barColor}"></div></div>`
    : '';
  return `<div class="beer-stock-item">
    <div class="beer-stock-row"><i class="fas fa-beer-mug-empty" style="font-size:.75rem"></i><span class="beer-stock-val">${cur}</span>${initLabel} <span>${label}</span></div>
    ${bar}
  </div>`;
}

function beerStockValue(b) {
  if (!b.recipe_id) return null;
  const recipe = S.recipes.find(r => r.id === b.recipe_id);
  if (!recipe) return null;
  const totalCost = recipeCost(recipe);
  if (totalCost === null) return null;
  const brew = b.brew_id ? S.brews.find(br => br.id === b.brew_id) : null;
  const volume = (brew?.volume_brewed) || recipe.volume;
  if (!volume || volume <= 0) return null;
  const costPerL = totalCost / volume;
  return (b.stock_33cl || 0) * costPerL * 0.33
       + (b.stock_75cl || 0) * costPerL * 0.75
       + (b.keg_liters  || 0) * costPerL;
}

// ── Depletion helpers ─────────────────────────────────────────────────────────
function _deplFmt(days) {
  if (days <= 0)  return '0 j';
  if (days <= 60) return `${days} j`;
  if (days <= 150) return t('cave.depl_rate').replace ? `≈ ${Math.round(days/7)} sem.` : `≈ ${Math.round(days/7)} sem.`;
  return `≈ ${Math.round(days/30)} mois`;
}

function _deplBadge(beerId) {
  const d = (S.depletion || []).find(x => x.beer_id === beerId);
  if (!d) return '';
  const days = d.days_remaining;
  const color = days <= 7 ? 'var(--danger)' : days <= 21 ? 'var(--warning)' : 'var(--muted)';
  const timeStr = _deplFmt(days);
  const rateStr = t('cave.depl_rate').replace('${r}', d.daily_rate < 0.1 ? (d.daily_rate * 1000).toFixed(0) + ' mL/j' : d.daily_rate.toFixed(2));
  const lowData = d.span_days < 7 ? ` <span style="opacity:.55;font-size:.7rem">${t('cave.depl_low_data')}</span>` : '';
  return `<div style="display:inline-flex;align-items:center;gap:5px;font-size:.73rem;color:${color};padding:3px 8px;border:1px solid ${color}44;border-radius:12px;margin:3px 0 5px;background:${color}0d">
    <i class="fas fa-hourglass-half" style="font-size:.62rem"></i>
    <strong>${timeStr}</strong>${lowData}
    <span style="color:var(--muted);font-size:.7rem">${rateStr}</span>
  </div>`;
}

let _caveAC = null;
const renderCaveDebounced = debounce(renderCave, 200);

function renderCave() {
  const q = (document.getElementById('cave-search')?.value || '').toLowerCase();
  const active = S.beers.filter(b => !b.archived);
  const arch   = S.beers.filter(b => b.archived);
  const all    = showArchivedCave ? [...active, ...arch] : active;
  const shown  = all.filter(b => !q || b.name.toLowerCase().includes(q) || (b.type||'').toLowerCase().includes(q));

  // Stats on active beers only
  const total33 = active.reduce((s,b) => s + (b.stock_33cl||0), 0);
  const total75 = active.reduce((s,b) => s + (b.stock_75cl||0), 0);
  const totalKeg = active.reduce((s,b) => s + (b.keg_liters||0), 0);
  const totalL  = (total33 * 0.33 + total75 * 0.75 + totalKeg).toFixed(1);
  let stockVal = 0, noPriceCnt = 0;
  active.forEach(b => {
    const v = beerStockValue(b);
    if (v !== null) stockVal += v; else noPriceCnt++;
  });
  const partialNote = noPriceCnt > 0 ? ` <span style="font-size:.68rem;color:var(--muted)">${t('cave.stat_value_partial').replace('${n}', noPriceCnt)}</span>` : '';
  document.getElementById('cave-stats').innerHTML = `
    <div class="stat"><div class="stat-val">${active.length}</div><div class="stat-lbl">${t('cave.stat_beers')}</div></div>
    <div class="stat"><div class="stat-val" style="color:var(--info)">${total33}</div><div class="stat-lbl">${t('cave.stat_bottles_33')}</div></div>
    <div class="stat"><div class="stat-val" style="color:var(--amber)">${total75}</div><div class="stat-lbl">${t('cave.stat_bottles_75')}</div></div>
    <div class="stat"><div class="stat-val" style="color:var(--success)">${totalL}</div><div class="stat-lbl">${t('cave.stat_liters')}</div></div>
    ${stockVal > 0 ? `<div class="stat"><div class="stat-val" style="color:#a78bfa">${stockVal.toFixed(2)} €${partialNote}</div><div class="stat-lbl">${t('cave.stat_value')}</div></div>` : ''}`;

  // Alerte dépletion imminente (≤ 14 j avec données fiables)
  const deplAlertEl = document.getElementById('cave-depl-alert');
  if (deplAlertEl) {
    const urgent = (S.depletion || [])
      .filter(d => d.days_remaining <= 14)
      .sort((a, b) => a.days_remaining - b.days_remaining);
    if (urgent.length) {
      const items = urgent.map(d => {
        const color = d.days_remaining <= 7 ? 'var(--danger)' : 'var(--warning)';
        const label = d.days_remaining === 0
          ? t('cave.depl_today')
          : t('cave.depl_soon').replace('${n}', d.days_remaining);
        return `<span style="color:${color};font-weight:600">${esc(d.beer_name)}</span><span style="color:var(--muted);font-size:.8rem"> (${label})</span>`;
      }).join('<span style="color:var(--border);margin:0 6px">·</span>');
      deplAlertEl.style.display = '';
      deplAlertEl.innerHTML = `<div style="padding:8px 14px;background:rgba(239,68,68,.07);border:1px solid rgba(239,68,68,.25);border-radius:10px;font-size:.82rem;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <i class="fas fa-hourglass-end" style="color:var(--danger)"></i>
        <span style="color:var(--muted);white-space:nowrap">${t('cave.depl_alert_title')} :</span>
        ${items}
      </div>`;
    } else {
      deplAlertEl.style.display = 'none';
    }
  }

  const caveEmpty = document.getElementById('cave-empty');
  caveEmpty.style.display = shown.length ? 'none' : 'block';
  if (!shown.length) {
    document.getElementById('cave-empty-default').style.display   = q ? 'none' : '';
    document.getElementById('cave-empty-noresults').style.display = q ? '' : 'none';
  }
  const caveCount = document.getElementById('cave-search-count');
  if (caveCount) caveCount.textContent = q
    ? t('common.n_results_of').replace('${n}', shown.length).replace('${total}', all.length)
    : t('common.n_results').replace('${n}', shown.length);
  const grid = document.getElementById('cave-grid');

  const beerCardHtml = b => {
    const linkedKeg = S.sodaKegs.find(k => k.beer_id === b.id);
    const photoHtml = b.photo
      ? `<div class="beer-photo" style="cursor:zoom-in" onclick="openBeerLightbox(${b.id})"><img src="${b.photo}" alt="${esc(b.name)}"></div>`
      : `<div class="beer-photo" style="display:flex;align-items:center;justify-content:center;background:var(--card2);color:var(--border);font-size:3rem;cursor:pointer" onclick="openBeerDetail(${b.id})">🍺</div>`;

    // ── Calcul du prix par bouteille ──────────────────────────────────────────
    let priceHtml = '';
    if (b.recipe_id) {
      const recipe = S.recipes.find(r => r.id === b.recipe_id);
      if (recipe) {
        const brew      = b.brew_id ? S.brews.find(br => br.id === b.brew_id) : null;
        // Prefer frozen snapshot; fall back to live computation (no snapshot yet or brew has no volume)
        const totalCost = (brew?.cost_snapshot != null)
          ? brew.cost_snapshot
          : recipeCost(recipe);
        if (totalCost !== null) {
          const volume = (brew?.cost_per_liter_snapshot != null && brew.volume_brewed)
            ? brew.volume_brewed
            : ((brew?.volume_brewed) ? brew.volume_brewed : recipe.volume);
          const costPerL = (brew?.cost_per_liter_snapshot != null)
            ? brew.cost_per_liter_snapshot
            : (volume > 0 ? totalCost / volume : null);
          if (costPerL !== null && volume > 0) {
            const p33 = (costPerL * 0.33).toFixed(2);
            const p75 = (costPerL * 0.75).toFixed(2);
            const volSrc = (brew?.volume_brewed) ? t('rec.vol_from_brew').replace('${vol}', volume) : t('rec.vol_from_recipe').replace('${vol}', volume);
            const stockV = beerStockValue(b);
            const stockVHtml = stockV !== null && stockV > 0
              ? `<span style="color:var(--border)">·</span><span style="color:var(--muted)">${t('cave.card_stock_value')} <strong style="color:#a78bfa">${stockV.toFixed(2)}€</strong></span>`
              : '';
            priceHtml = `
              <div style="display:flex;flex-wrap:wrap;gap:3px 10px;align-items:center;font-size:.77rem;margin-bottom:7px;padding:5px 8px;background:rgba(34,197,94,.07);border-radius:7px;border:1px solid rgba(34,197,94,.18)">
                <span style="color:var(--success);font-weight:700"><i class="fas fa-euro-sign" style="font-size:.65rem"></i> ${totalCost.toFixed(2)}€</span>
                <span style="color:var(--border)">·</span>
                <span style="color:var(--muted)">33cl <strong style="color:var(--success)">${p33}€</strong></span>
                <span style="color:var(--border)">·</span>
                <span style="color:var(--muted)">75cl <strong style="color:var(--success)">${p75}€</strong></span>
                ${stockVHtml}
                <span style="color:var(--border);margin-left:auto;font-size:.7rem;font-style:italic">${volSrc}</span>
              </div>`;
          }
        }
      }
    }

    // ── Section fût ──────────────────────────────────────────────────────────
    const kegL    = b.keg_liters    || 0;
    const kegInit = b.keg_initial_liters || 0;
    const hasKeg  = kegL > 0 || kegInit > 0;
    let kegHtml = '';
    if (hasKeg) {
      const kegPct = kegInit > 0 ? Math.round(kegL / kegInit * 100) : 100;
      const kegBarColor = kegPct > 50 ? 'var(--success)' : kegPct > 20 ? '#f59e0b' : 'var(--danger)';
      const kegInitLabel = kegInit > kegL ? `<span style="color:var(--muted);font-size:.8rem">/${kegInit}L</span>` : '';
      const kegBar = kegInit > kegL
        ? `<div class="bottle-bar"><div class="bottle-bar-fill" style="width:${kegPct}%;background:${kegBarColor}"></div></div>`
        : '';
      kegHtml = `
        <div style="margin:6px 0 8px;padding:7px 10px;background:rgba(251,191,36,.08);border:1px solid rgba(251,191,36,.22);border-radius:8px">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:${kegBar?'4px':'0'}">
            <i class="fas fa-wine-barrel" style="color:var(--amber);font-size:.85rem"></i>
            <span style="font-weight:700;font-size:.9rem">${kegL} L</span>${kegInitLabel}
            <span style="color:var(--muted);font-size:.78rem;margin-left:auto">${t('cave.in_keg')}</span>
          </div>
          ${kegBar}
        </div>`;
    }

    return `
      <div class="beer-card ${b.archived ? 'archived-item' : (((b.stock_33cl||0)+(b.stock_75cl||0)===0&&(b.keg_liters||0)===0)?'beer-card--empty':'')}" data-id="${b.id}" draggable="true" style="position:relative">
        <span class="beer-drag-handle" title="${t('cave.drag_to_reorder')}"><i class="fas fa-grip-vertical"></i></span>
        ${photoHtml}
        <div class="beer-body">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px;cursor:pointer" onclick="openBeerDetail(${b.id})">
            <div class="beer-name">${esc(b.name)}</div>
            ${(() => {
              if (b.abv) return `<div class="beer-abv">${b.abv}%</div>`;
              const brew = b.brew_id ? S.brews.find(br => br.id === b.brew_id) : null;
              if (brew && brew.og && brew.fg)
                return `<div class="beer-abv" style="opacity:.65" title="${t('cave.abv_estimated')}">${((brew.og - brew.fg) * 131.25).toFixed(1)}%~</div>`;
              return '';
            })()}
          </div>
          <div class="beer-type" style="cursor:pointer" onclick="openBeerDetail(${b.id})">${b.type ? esc(b.type) : ''} ${b.recipe_name ? `· <i class="fas fa-scroll" style="font-size:.75rem"></i> ${esc(b.recipe_name)}` : ''}</div>
          ${b.refermentation ? (() => {
            if (!b.bottling_date || !b.refermentation_days)
              return `<div style="display:inline-flex;align-items:center;gap:5px;font-size:.75rem;font-weight:600;color:var(--info);background:rgba(96,165,250,.1);border:1px solid rgba(96,165,250,.25);border-radius:20px;padding:2px 9px;margin:4px 0"><i class="fas fa-rotate"></i> ${t('cave.refermentation')}</div>`;
            const dEnd  = new Date(b.bottling_date + 'T00:00:00');
            dEnd.setDate(dEnd.getDate() + b.refermentation_days);
            const today = new Date(); today.setHours(0,0,0,0);
            const delta = Math.round((dEnd - today) / 86400000);
            let countdown, color, bg, border;
            if (delta > 0) {
              countdown = t('cave.referm_ready_in').replace('${n}', delta);
              color = 'var(--info)'; bg = 'rgba(96,165,250,.1)'; border = 'rgba(96,165,250,.25)';
            } else if (delta === 0) {
              countdown = t('cave.referm_ready_today');
              color = 'var(--success)'; bg = 'rgba(16,185,129,.15)'; border = 'rgba(16,185,129,.4)';
            } else {
              countdown = t('cave.referm_ready_since').replace('${n}', -delta);
              color = 'var(--success)'; bg = 'rgba(16,185,129,.08)'; border = 'rgba(16,185,129,.25)';
            }
            return `<div style="display:inline-flex;align-items:center;gap:5px;font-size:.75rem;font-weight:600;color:${color};background:${bg};border:1px solid ${border};border-radius:20px;padding:2px 9px;margin:4px 0" title="${_ymd(dEnd).split('-').reverse().join('/')}"><i class="fas fa-rotate"></i> ${countdown}</div>`;
          })() : ''}
          ${linkedKeg ? `<div class="brew-spindle-badge" style="border-color:rgba(245,158,11,.35);margin:4px 0">
            <i class="fas fa-jar" style="color:var(--amber);font-size:.75rem"></i>
            <span style="color:var(--muted);font-size:.78rem">${esc(linkedKeg.name)}</span>
            ${linkedKeg.current_liters != null ? `<span class="bsb-grav" style="color:var(--amber)">${linkedKeg.current_liters} L</span>` : ''}
          </div>` : ''}
          ${kegHtml}
          <div class="beer-stocks">
            ${beerStockHtml(b.stock_33cl, b.initial_33cl, '33cl')}
            ${beerStockHtml(b.stock_75cl, b.initial_75cl, '75cl')}
          </div>
          ${_deplBadge(b.id)}
          ${priceHtml}
          ${b.description ? `<div style="font-size:.78rem;color:var(--muted);margin-bottom:8px;line-height:1.4">${esc(b.description).substring(0,100)}${b.description.length>100?'…':''}</div>` : ''}
          ${hasKeg ? `<div style="margin-bottom:5px"><button class="btn btn-sm btn-ghost" onclick="openKegTransferModal(${b.id})" style="width:100%;border-color:rgba(251,191,36,.4);color:var(--amber)"><i class="fas fa-wine-barrel"></i> ${t('cave.keg_transfer')}</button></div>` : ''}
          <div style="display:flex;gap:5px;margin-bottom:5px">
            <button class="btn btn-sm btn-ghost" onclick="withBtn(this,()=>adjustStock(${b.id},-1,0))" title="−1 bouteille 33cl" style="flex:1"><i class="fas fa-minus"></i> 33cl</button>
            <button class="btn btn-sm btn-ghost" onclick="withBtn(this,()=>adjustStock(${b.id},0,-1))" title="−1 bouteille 75cl" style="flex:1"><i class="fas fa-minus"></i> 75cl</button>
          </div>
          <div style="display:flex;gap:5px">
            <button class="btn btn-sm btn-ghost" onclick="editBeer(${b.id})" style="flex:1"><i class="fas fa-pen"></i> ${t('common.edit')}</button>
            <button class="btn btn-icon btn-ghost btn-sm" onclick="openTastingModal(${b.id})" title="${t('tasting.btn')}" style="${b.taste_rating||b.taste_appearance||b.taste_score_aroma?'color:var(--amber)':''}"><i class="fas fa-wine-glass"></i></button>
            <button class="btn btn-icon btn-ghost btn-sm" onclick="openCaveKegModal(${b.id})" title="${linkedKeg ? esc(linkedKeg.name) : t('cave.keg_assign')}" style="${linkedKeg ? 'color:var(--amber)' : ''}"><i class="fas fa-jar"></i></button>
            <button class="btn btn-icon btn-ghost btn-sm" onclick="withBtn(this,()=>archiveItem('cave',${b.id},${b.archived?0:1}))" title="${b.archived?t('common.restore'):t('common.archive')}"><i class="fas fa-${b.archived?'box-open':'box-archive'}"></i></button>
            <button class="btn btn-icon btn-ghost btn-sm" onclick="event.stopPropagation();printBeerLabel(${b.id})" title="${t('cave.print_label')}"><i class="fas fa-tag"></i></button>
            <button class="btn btn-icon btn-danger btn-sm" onclick="deleteBeer(${b.id})" title="${t('common.delete')}"><i class="fas fa-trash"></i></button>
          </div>
        </div>
      </div>`;
  };

  const hasStock  = shown.filter(b => (b.stock_33cl || 0) + (b.stock_75cl || 0) > 0 || (b.keg_liters || 0) > 0);
  const noStock   = shown.filter(b => (b.stock_33cl || 0) + (b.stock_75cl || 0) === 0 && (b.keg_liters || 0) === 0);
  const needSplit = hasStock.length > 0 && noStock.length > 0;

  // Groups as display:contents wrappers — invisible to CSS grid, diffable by _patchList
  const caveGroups = needSplit
    ? [
        { id: 'group-stock', label: t('cave.group_in_stock'), icon: 'check-circle', color: 'var(--success)', items: hasStock },
        { id: 'group-empty', label: t('cave.group_empty'),    icon: 'wine-bottle',  color: 'var(--muted)',   items: noStock  },
      ]
    : [{ id: 'group-all', items: shown }];

  const caveGroupHtml = g => {
    const header = g.label
      ? `<div class="brew-group-header" style="grid-column:1/-1;color:${g.color}"><i class="fas fa-${g.icon}"></i> ${g.label}<span class="brew-group-count">${g.items.length}</span></div>`
      : '';
    return `<div data-id="${g.id}" style="display:contents">${header}${g.items.map(beerCardHtml).join('')}</div>`;
  };

  grid.querySelectorAll(':scope > .skel').forEach(el => el.remove());
  _patchList(grid, caveGroups, g => g.id, caveGroupHtml);

  // Archive button
  const archBtn = document.getElementById('cave-arch-btn');
  if (archBtn) {
    const archCount = arch.length;
    archBtn.textContent = showArchivedCave ? t('cave.show_archives') : `\uD83D\uDDC3\uFE0F Archives (${archCount})`;
  }

  // ── Drag & drop reorder (within same stock group) ──
  if (_caveAC) _caveAC.abort();
  _caveAC = new AbortController();
  const { signal: caveSig } = _caveAC;
  const hasStockIds = new Set(hasStock.map(b => b.id));
  const noStockIds  = new Set(noStock.map(b => b.id));

  grid.querySelectorAll('.beer-card[draggable]').forEach(card => {
    card.addEventListener('dragstart', e => {
      e.dataTransfer.setData('text/plain', card.dataset.id);
      e.dataTransfer.effectAllowed = 'move';
      setTimeout(() => card.classList.add('dragging'), 0);
    }, { signal: caveSig });
    card.addEventListener('dragend', () => {
      card.classList.remove('dragging');
      grid.querySelectorAll('.beer-card').forEach(c => c.classList.remove('drag-over'));
    }, { signal: caveSig });
    card.addEventListener('dragover', e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      grid.querySelectorAll('.beer-card').forEach(c => c.classList.remove('drag-over'));
      const srcId = parseInt(e.dataTransfer.getData('text/plain'));
      if (srcId !== parseInt(card.dataset.id)) card.classList.add('drag-over');
    }, { signal: caveSig });
    card.addEventListener('dragleave', () => card.classList.remove('drag-over'), { signal: caveSig });
    card.addEventListener('drop', e => {
      e.preventDefault();
      const srcId = parseInt(e.dataTransfer.getData('text/plain'));
      const tgtId = parseInt(card.dataset.id);
      if (!srcId || srcId === tgtId) return;
      // Only reorder within same group (en stock ↔ en stock, épuisée ↔ épuisée)
      const sameGroup = (hasStockIds.has(srcId) && hasStockIds.has(tgtId))
                     || (noStockIds.has(srcId)   && noStockIds.has(tgtId))
                     || (!needSplit);
      if (!sameGroup) return;
      const mi = S.beers.findIndex(b => b.id === srcId);
      const ti = S.beers.findIndex(b => b.id === tgtId);
      if (mi === -1 || ti === -1) return;
      const [moved] = S.beers.splice(mi, 1);
      S.beers.splice(ti, 0, moved);
      saveCaveOrder();
      renderCave();
    }, { signal: caveSig });
  });
}

let _saveCaveOrderTimer = null;
function saveCaveOrder() {
  clearTimeout(_saveCaveOrderTimer);
  _saveCaveOrderTimer = setTimeout(async () => {
    try {
      await api('PUT', '/api/beers/reorder',
        S.beers.map((b, i) => ({ id: b.id, sort_order: i })));
    } catch(e) { toast(t('cave.err_save_order'), 'error'); }
  }, 600);
}

function openImgLightbox(src, name = '') {
  document.getElementById('beer-lightbox-img').src  = src;
  document.getElementById('beer-lightbox-img').alt  = name;
  document.getElementById('beer-lightbox-name').textContent = name;
  document.getElementById('beer-lightbox').style.display = 'flex';
}

function openBeerLightbox(id) {
  const b = S.beers.find(x => x.id === id);
  if (!b || !b.photo) return;
  const lb = document.getElementById('beer-lightbox');
  document.getElementById('beer-lightbox-img').src  = b.photo;
  document.getElementById('beer-lightbox-img').alt  = b.name || '';
  document.getElementById('beer-lightbox-name').textContent = b.name || '';
  lb.style.display = 'flex';
}

function closeBeerLightbox() {
  document.getElementById('beer-lightbox').style.display = 'none';
  document.getElementById('beer-lightbox-img').src = '';
}

let _beerDetailId = null;
function _bdPhotoClick() { if (_beerDetailId) openBeerLightbox(_beerDetailId); }

function openBeerDetail(id) {
  const b = S.beers.find(x => x.id === id);
  if (!b) return;
  _beerDetailId = id;

  // Ouvrir le modal en premier — le contenu est peuplé ensuite
  openModal('beer-detail-modal');

  try {
    const get = elId => document.getElementById(elId);

    get('bd-title').textContent = b.name || '';

    // Photo
    const photoWrap = get('bd-photo-wrap');
    const photoImg  = get('bd-photo');
    if (b.photo && photoWrap && photoImg) {
      photoImg.src = b.photo;
      photoImg.alt = b.name || '';
      photoWrap.style.display = '';
    } else if (photoWrap) {
      photoWrap.style.display = 'none';
    }

    // Badges
    const badges = [];
    if (b.abv)           badges.push(`<span class="badge" style="background:var(--amber);color:#000;font-weight:700">${b.abv}% ABV</span>`);
    if (b.type)          badges.push(`<span class="badge badge-info">${esc(b.type)}</span>`);
    if (b.origin)        badges.push(`<span class="badge" style="background:var(--card2);color:var(--muted)"><i class="fas fa-map-marker-alt"></i> ${esc(b.origin)}</span>`);
    if (b.recipe_name)   badges.push(`<span class="badge" style="background:var(--card2);color:var(--hop)"><i class="fas fa-scroll"></i> ${esc(b.recipe_name)}</span>`);
    if (b.refermentation) {
      let refBadge;
      if (b.bottling_date && b.refermentation_days) {
        const dEnd  = new Date(b.bottling_date + 'T00:00:00');
        dEnd.setDate(dEnd.getDate() + b.refermentation_days);
        const today = new Date(); today.setHours(0,0,0,0);
        const delta = Math.round((dEnd - today) / 86400000);
        if (delta > 0) {
          refBadge = `<span class="badge" style="background:rgba(96,165,250,.15);color:var(--info);border:1px solid rgba(96,165,250,.3)"><i class="fas fa-rotate"></i> ${t('cave.referm_ready_in').replace('${n}', delta)}</span>`;
        } else if (delta === 0) {
          refBadge = `<span class="badge" style="background:rgba(16,185,129,.2);color:var(--success);border:1px solid rgba(16,185,129,.5);animation:timerPulse 1.5s infinite"><i class="fas fa-rotate"></i> ${t('cave.referm_ready_today')}</span>`;
        } else {
          refBadge = `<span class="badge" style="background:rgba(16,185,129,.1);color:var(--success);border:1px solid rgba(16,185,129,.3)"><i class="fas fa-rotate"></i> ${t('cave.referm_ready_since').replace('${n}', -delta)}</span>`;
        }
      } else {
        refBadge = `<span class="badge" style="background:rgba(96,165,250,.15);color:var(--info);border:1px solid rgba(96,165,250,.3)"><i class="fas fa-rotate"></i> ${t('cave.refermentation')}</span>`;
      }
      badges.push(refBadge);
    }
    const badgesEl = get('bd-badges');
    if (badgesEl) badgesEl.innerHTML = badges.join('');

    // Stocks
    const stocksEl = get('bd-stocks');
    if (stocksEl) {
      const kegBlock = (b.keg_liters || b.keg_initial_liters)
        ? `<div style="background:rgba(251,191,36,.08);border:1px solid rgba(251,191,36,.22);border-radius:12px;padding:14px;text-align:center;grid-column:1/-1">
             <div style="font-size:2rem;font-weight:800;color:var(--amber)">${b.keg_liters || 0}</div>
             <div style="font-size:.8rem;color:var(--muted);margin-top:2px"><i class="fas fa-wine-barrel"></i> ${t('cave.vol_keg_label')}</div>
             ${b.keg_initial_liters ? `<div style="font-size:.72rem;color:var(--muted);margin-top:4px">/ ${b.keg_initial_liters} L initial</div>` : ''}
           </div>`
        : '';
      stocksEl.innerHTML = `
        ${kegBlock}
        <div style="background:var(--card2);border-radius:12px;padding:14px;text-align:center">
          <div style="font-size:2rem;font-weight:800;color:var(--info)">${b.stock_33cl || 0}</div>
          <div style="font-size:.8rem;color:var(--muted);margin-top:2px">${t('cave.bottles_label_33')}</div>
          ${b.initial_33cl ? `<div style="font-size:.72rem;color:var(--muted);margin-top:4px">/ ${b.initial_33cl} initial</div>` : ''}
        </div>
        <div style="background:var(--card2);border-radius:12px;padding:14px;text-align:center">
          <div style="font-size:2rem;font-weight:800;color:var(--amber)">${b.stock_75cl || 0}</div>
          <div style="font-size:.8rem;color:var(--muted);margin-top:2px">${t('cave.bottles_label_75')}</div>
          ${b.initial_75cl ? `<div style="font-size:.72rem;color:var(--muted);margin-top:4px">/ ${b.initial_75cl} initial</div>` : ''}
        </div>`;
    }

    // Dépletion
    const deplEl = get('bd-depletion');
    if (deplEl) {
      const d = (S.depletion || []).find(x => x.beer_id === b.id);
      if (d) {
        const color = d.days_remaining <= 7 ? 'var(--danger)' : d.days_remaining <= 21 ? 'var(--warning)' : 'var(--muted)';
        const label = d.days_remaining === 0
          ? t('cave.depl_today')
          : t('cave.depl_soon').replace('${n}', d.days_remaining);
        const dateStr = d.depletion_date ? d.depletion_date.split('-').reverse().join('/') : '';
        const rateStr = t('cave.depl_rate').replace('${r}', d.daily_rate < 0.1 ? (d.daily_rate*1000).toFixed(0)+' mL/j' : d.daily_rate.toFixed(2));
        const lowData = d.span_days < 7 ? ` <span style="opacity:.55;font-size:.72rem">${t('cave.depl_low_data')}</span>` : '';
        deplEl.innerHTML = `<div style="display:inline-flex;align-items:center;gap:7px;flex-wrap:wrap;font-size:.8rem;color:${color};padding:6px 12px;border:1px solid ${color}44;border-radius:10px;background:${color}0d">
          <i class="fas fa-hourglass-half" style="font-size:.75rem"></i>
          <strong>${label}</strong>${dateStr ? ` <span style="color:var(--muted)">(${dateStr})</span>` : ''}${lowData}
          <span style="color:var(--muted);margin-left:4px">${rateStr}</span>
        </div>`;
      } else {
        deplEl.innerHTML = '';
      }
    }

    // Description
    const descEl = get('bd-desc');
    if (descEl) {
      descEl.textContent = b.description || '';
      descEl.style.display = b.description ? '' : 'none';
    }

    // Meta
    const totalL = ((b.stock_33cl||0)*0.33 + (b.stock_75cl||0)*0.75 + (b.keg_liters||0)).toFixed(2);
    const metaParts = [`<i class="fas fa-wine-bottle"></i> ${totalL} L en cave`];
    const fmtDate = d => d ? d.split('-').reverse().join('/') : null;
    if (b.brew_date)        metaParts.push(`<i class="fas fa-fire-flame-curved"></i> Brassé le ${fmtDate(b.brew_date)}`);
    if (b.bottling_date)    metaParts.push(`<i class="fas fa-wine-bottle"></i> Embouteillé le ${fmtDate(b.bottling_date)}`);
    if (b.brew_photos_url)  metaParts.push(`<a href="${esc(b.brew_photos_url)}" target="_blank" rel="noopener" style="color:var(--amber);text-decoration:none"><i class="fas fa-images"></i> ${t('brew.photos_url_open')}</a>`);
    const metaEl = get('bd-meta');
    if (metaEl) metaEl.innerHTML = metaParts.join(' &nbsp;·&nbsp; ');

    // Section dégustation
    const tastingEl = get('bd-tasting');
    if (tastingEl) {
      const hasTasting = b.taste_appearance || b.taste_aroma || b.taste_flavor ||
                         b.taste_bitterness || b.taste_mouthfeel || b.taste_finish || b.taste_overall || b.taste_rating;
      const scores = [b.taste_score_appearance, b.taste_score_aroma, b.taste_score_flavor,
                      b.taste_score_bitterness, b.taste_score_mouthfeel, b.taste_score_finish];
      const hasScores = scores.some(s => s != null && s > 0);
      if (hasTasting || hasScores) {
        const fmtDate = d => d ? d.split('-').reverse().join('/') : null;
        const starsHtml = b.taste_rating
          ? Array.from({length:5}, (_,i) =>
              `<span style="color:${i<b.taste_rating?'var(--amber)':'var(--border)'}">★</span>`).join('')
          : '';
        const TASTING_FIELDS = [
          ['fa-wind',             'var(--hop)',   t('tasting.aroma'),        b.taste_aroma],
          ['fa-circle-half-stroke','var(--info)', t('tasting.mouthfeel'),    b.taste_mouthfeel],
          ['fa-hourglass-end',    'var(--amber)', t('tasting.finish'),       b.taste_finish],
          ['fa-droplet',          'var(--malt)',  t('tasting.flavor'),       b.taste_flavor],
          ['fa-fire',             'var(--amber)', t('tasting.bitterness'),   b.taste_bitterness],
          ['fa-eye',              'var(--info)',  t('tasting.appearance'),   b.taste_appearance],
          ['fa-comment',          'var(--muted)', t('tasting.overall_notes'),b.taste_overall],
        ].filter(f => f[3]);
        const radarSection = hasScores
          ? `<div style="display:flex;gap:16px;align-items:flex-start;margin-bottom:14px;flex-wrap:wrap">
               <div style="flex:0 0 200px;height:200px;position:relative">
                 <canvas id="bd-tasting-radar"></canvas>
               </div>
               <div style="flex:1;min-width:120px;display:flex;flex-direction:column;justify-content:center;gap:5px">
                 ${[
                   [t('tasting.appearance'), b.taste_score_appearance, 'var(--info)'],
                   [t('tasting.aroma'),      b.taste_score_aroma,      'var(--hop)'],
                   [t('tasting.flavor'),     b.taste_score_flavor,     'var(--malt)'],
                   [t('tasting.bitterness'), b.taste_score_bitterness, 'var(--amber)'],
                   [t('tasting.mouthfeel'),  b.taste_score_mouthfeel,  'var(--info)'],
                   [t('tasting.finish'),     b.taste_score_finish,     'var(--amber)'],
                 ].filter(([,v]) => v != null).map(([lbl, val, clr]) =>
                   `<div style="display:flex;align-items:center;gap:7px;font-size:.78rem">
                     <span style="color:${clr};font-weight:600;width:72px;white-space:nowrap">${lbl}</span>
                     <div style="flex:1;height:5px;background:var(--card2);border-radius:3px">
                       <div style="width:${val*10}%;height:100%;background:${clr};border-radius:3px;transition:width .3s"></div>
                     </div>
                     <span style="color:var(--muted);width:20px;text-align:right">${val}</span>
                   </div>`
                 ).join('')}
               </div>
             </div>`
          : '';
        tastingEl.innerHTML = `
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
            <i class="fas fa-wine-glass" style="color:var(--amber)"></i>
            <span style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--amber)">${t('tasting.section_title')}</span>
            ${starsHtml ? `<span style="margin-left:auto;font-size:1rem">${starsHtml}</span>` : ''}
            ${b.taste_date ? `<span style="font-size:.75rem;color:var(--muted)">${fmtDate(b.taste_date)}</span>` : ''}
          </div>
          ${radarSection}
          ${TASTING_FIELDS.length ? `<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            ${TASTING_FIELDS.map(([icon, color, label, val]) => `
              <div style="background:var(--card2);border-radius:9px;padding:10px">
                <div style="font-size:.72rem;font-weight:700;color:${color};margin-bottom:4px">
                  <i class="fas ${icon}"></i> ${label}
                </div>
                <div style="font-size:.82rem;line-height:1.5;white-space:pre-wrap">${esc(val)}</div>
              </div>`).join('')}
          </div>` : ''}`;
        tastingEl.style.display = '';

        // Radar Chart
        if (hasScores) {
          const radarLabels = [t('tasting.appearance'), t('tasting.aroma'), t('tasting.flavor'),
                               t('tasting.bitterness'), t('tasting.mouthfeel'), t('tasting.finish')];
          const radarData   = [b.taste_score_appearance, b.taste_score_aroma, b.taste_score_flavor,
                               b.taste_score_bitterness, b.taste_score_mouthfeel, b.taste_score_finish]
                               .map(v => v || 0);
          const ctx = document.getElementById('bd-tasting-radar');
          if (ctx) {
            if (window._bdTastingRadarChart) { window._bdTastingRadarChart.destroy(); window._bdTastingRadarChart = null; }
            window._bdTastingRadarChart = new Chart(ctx, {
              type: 'radar',
              data: {
                labels: radarLabels,
                datasets: [{
                  data: radarData,
                  backgroundColor: 'rgba(251,191,36,.15)',
                  borderColor:     'rgba(251,191,36,.8)',
                  pointBackgroundColor: 'rgba(251,191,36,1)',
                  pointRadius: 3,
                  borderWidth: 2,
                }]
              },
              options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                  r: {
                    min: 0, max: 10, ticks: { stepSize: 2, display: false },
                    grid:        { color: 'rgba(255,255,255,.08)' },
                    angleLines:  { color: 'rgba(255,255,255,.08)' },
                    pointLabels: { color: 'var(--muted)', font: { size: 10 } },
                  }
                }
              }
            });
          }
        }
      } else {
        tastingEl.style.display = 'none';
      }
    }

    // Bouton Dégustation
    const tastingBtn = get('bd-tasting-btn');
    if (tastingBtn) tastingBtn.onclick = () => { closeModal('beer-detail-modal'); openTastingModal(id); };

    // Bouton Étiquette
    const printBtn = get('bd-print-btn');
    if (printBtn) printBtn.onclick = () => printBeerLabel(id);

    // Bouton Modifier
    const editBtn = get('bd-edit-btn');
    if (editBtn) editBtn.onclick = () => { closeModal('beer-detail-modal'); editBeer(id); };

  } catch(e) {
    console.error('openBeerDetail:', e);
  }
}

function openTastingModal(beerId) {
  const b = S.beers.find(x => x.id === beerId);
  if (!b) return;
  document.getElementById('tasting-f-beer-id').value     = beerId;
  document.getElementById('tasting-modal-title').textContent = b.name;
  document.getElementById('tasting-f-date').value        = b.taste_date || new Date().toISOString().split('T')[0];
  document.getElementById('tasting-f-appearance').value  = b.taste_appearance || '';
  document.getElementById('tasting-f-aroma').value       = b.taste_aroma      || '';
  document.getElementById('tasting-f-flavor').value      = b.taste_flavor     || '';
  document.getElementById('tasting-f-bitterness').value  = b.taste_bitterness || '';
  document.getElementById('tasting-f-mouthfeel').value   = b.taste_mouthfeel  || '';
  document.getElementById('tasting-f-finish').value      = b.taste_finish     || '';
  document.getElementById('tasting-f-overall').value     = b.taste_overall    || '';
  document.getElementById('tasting-f-rating').value      = b.taste_rating     || '';
  document.getElementById('tasting-s-appearance').value  = b.taste_score_appearance || '';
  document.getElementById('tasting-s-aroma').value       = b.taste_score_aroma      || '';
  document.getElementById('tasting-s-flavor').value      = b.taste_score_flavor     || '';
  document.getElementById('tasting-s-bitterness').value  = b.taste_score_bitterness || '';
  document.getElementById('tasting-s-mouthfeel').value   = b.taste_score_mouthfeel  || '';
  document.getElementById('tasting-s-finish').value      = b.taste_score_finish     || '';
  // Apply placeholders via i18n
  ['appearance','aroma','flavor','bitterness','mouthfeel','finish','overall'].forEach(k => {
    const el = document.getElementById(`tasting-f-${k}`);
    if (el) el.placeholder = t(`tasting.ph_${k}`);
  });
  renderTastingStars(b.taste_rating || 0);
  openModal('tasting-modal');
}

function setTastingRating(v) {
  const current = parseInt(document.getElementById('tasting-f-rating').value) || 0;
  const newVal = current === v ? 0 : v;
  document.getElementById('tasting-f-rating').value = newVal || '';
  renderTastingStars(newVal);
}

function renderTastingStars(n) {
  document.querySelectorAll('#tasting-star-input .star').forEach((el, i) => {
    el.classList.toggle('on', i < n);
  });
  document.getElementById('tasting-rating-label').textContent = STAR_LABELS()[n] || STAR_LABELS()[0];
}

async function saveTasting() {
  const beerId = parseInt(document.getElementById('tasting-f-beer-id').value);
  const payload = {
    taste_date:        document.getElementById('tasting-f-date').value        || null,
    taste_appearance:  document.getElementById('tasting-f-appearance').value  || null,
    taste_aroma:       document.getElementById('tasting-f-aroma').value       || null,
    taste_flavor:      document.getElementById('tasting-f-flavor').value      || null,
    taste_bitterness:  document.getElementById('tasting-f-bitterness').value  || null,
    taste_mouthfeel:   document.getElementById('tasting-f-mouthfeel').value   || null,
    taste_finish:      document.getElementById('tasting-f-finish').value      || null,
    taste_overall:     document.getElementById('tasting-f-overall').value     || null,
    taste_rating:            parseInt(document.getElementById('tasting-f-rating').value) || null,
    taste_score_appearance:  parseInt(document.getElementById('tasting-s-appearance').value) || null,
    taste_score_aroma:       parseInt(document.getElementById('tasting-s-aroma').value)      || null,
    taste_score_flavor:      parseInt(document.getElementById('tasting-s-flavor').value)     || null,
    taste_score_bitterness:  parseInt(document.getElementById('tasting-s-bitterness').value) || null,
    taste_score_mouthfeel:   parseInt(document.getElementById('tasting-s-mouthfeel').value)  || null,
    taste_score_finish:      parseInt(document.getElementById('tasting-s-finish').value)     || null,
  };
  try {
    const updated = await api('PUT', `/api/beers/${beerId}/tasting`, payload);
    const idx = S.beers.findIndex(b => b.id === beerId);
    if (idx !== -1) S.beers[idx] = { ...S.beers[idx], ...updated };
    closeModal('tasting-modal');
    renderCave();
    toast(t('tasting.saved'), 'success');
  } catch(e) { toast(t('tasting.err_save'), 'error'); }
}

function openBeerModal(beer = null) {
  document.getElementById('beer-f-id').value      = beer ? beer.id : '';
  document.getElementById('beer-f-name').value    = beer ? beer.name : '';
  document.getElementById('beer-f-type').value    = beer ? (beer.type||'') : '';
  document.getElementById('beer-f-abv').value     = beer ? (beer.abv||'') : '';
  document.getElementById('beer-f-33').value      = beer ? (beer.stock_33cl||0) : 0;
  document.getElementById('beer-f-75').value      = beer ? (beer.stock_75cl||0) : 0;
  document.getElementById('beer-f-origin').value  = beer ? (beer.origin||'') : '';
  document.getElementById('beer-f-desc').value    = beer ? (beer.description||'') : '';
  document.getElementById('beer-f-photo-b64').value= beer ? (beer.photo||'') : '';
  document.getElementById('beer-f-photo-preview').style.display = beer && beer.photo ? 'block' : 'none';
  document.getElementById('beer-f-photo-remove').style.display  = beer && beer.photo ? 'flex' : 'none';
  if (beer && beer.photo) document.getElementById('beer-f-photo-preview').src = beer.photo;
  document.getElementById('beer-f-brew-date').value     = beer ? (beer.brew_date||'') : '';
  document.getElementById('beer-f-bottling-date').value = beer ? (beer.bottling_date||'') : '';
  document.getElementById('beer-f-refermentation').checked = beer ? !!beer.refermentation : false;
  document.getElementById('beer-f-refermentation-days').value = beer ? (beer.refermentation_days || '') : '';
  document.getElementById('beer-f-referm-days-wrap').style.display = (beer && beer.refermentation) ? '' : 'none';
  document.getElementById('beer-modal-title').textContent = beer ? t('cave.modal_title_edit') : t('cave.modal_title_add');
  // Initial counts — shown only when editing
  const initWrap = document.getElementById('beer-f-init-wrap');
  if (beer) {
    document.getElementById('beer-f-33-init').value = beer.initial_33cl || 0;
    document.getElementById('beer-f-75-init').value = beer.initial_75cl || 0;
    initWrap.style.display = '';
  } else {
    initWrap.style.display = 'none';
  }
  // Keg field
  document.getElementById('beer-f-keg').value = beer ? (beer.keg_liters != null ? beer.keg_liters : '') : '';
  if (beer) {
    document.getElementById('beer-f-keg-init').value = beer.keg_initial_liters != null ? beer.keg_initial_liters : (beer.keg_liters || 0);
    document.getElementById('beer-f-keg-init-wrap').style.display = '';
  } else {
    document.getElementById('beer-f-keg-init-wrap').style.display = 'none';
  }
  // Show AI generation button and extra prompt field only if a key is configured
  const aiConfigured = !!appSettings.ai?.apiKey;
  document.getElementById('beer-gen-ai-btn').style.display      = aiConfigured ? '' : 'none';
  document.getElementById('beer-ai-extra-wrap').style.display   = aiConfigured ? '' : 'none';
  document.getElementById('beer-ai-extra').value = '';
  openModal('beer-modal');
}

function toggleRefermDays() {
  const checked = document.getElementById('beer-f-refermentation').checked;
  document.getElementById('beer-f-referm-days-wrap').style.display = checked ? '' : 'none';
}

function updateKegInitWrap() {
  const isEditing = !!document.getElementById('beer-f-id').value;
  if (isEditing) return; // editing mode: init wrap already visible
  const val = document.getElementById('beer-f-keg').value;
  const initWrap = document.getElementById('beer-f-keg-init-wrap');
  if (initWrap) {
    initWrap.style.display = val ? '' : 'none';
    if (val) {
      const initInput = document.getElementById('beer-f-keg-init');
      if (initInput && !initInput.value) initInput.value = val;
    }
  }
}

function editBeer(id) { openBeerModal(S.beers.find(b => b.id === id)); }

// ══════════════════════════════════════════════════════════════════════════════
// ── ÉTIQUETTES ───────────────────────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════
let _labelBeerId = null;

function printBeerLabel(id) {
  _labelBeerId = id;
  document.getElementById('label-copies').value = 1;
  const fmt = document.getElementById('label-format');
  if (fmt) fmt.value = 'A4 landscape';
  renderLabelPreview();
  openModal('label-modal');
}

function _labelIbuEbc(recipe) {
  if (!recipe) return { ibu: null, ebc: null };
  const vol  = parseFloat(recipe.volume) || 20;
  const og   = 1.055;
  const ings = recipe.ingredients || [];
  let ibuTotal = 0;
  ings.filter(i => i.category === 'houblon' && i.hop_type !== 'dryhop').forEach(h => {
    if (!h.quantity || !h.alpha) return;
    const mins  = h.hop_type === 'whirlpool' ? 15 : (h.hop_time != null ? h.hop_time : 60);
    const grams = h.unit === 'kg' ? h.quantity * 1000 : h.quantity;
    const bigness  = 1.65 * Math.pow(0.000125, og - 1);
    const timeFact = (1 - Math.exp(-0.04 * mins)) / 4.15;
    ibuTotal += bigness * timeFact * (h.alpha / 100) * grams * 1000 / vol;
  });
  let totalMcu = 0;
  ings.filter(i => i.category === 'malt').forEach(m => {
    if (!m.quantity || m.ebc == null) return;
    const kg       = m.unit === 'kg' ? m.quantity : m.quantity / 1000;
    const lovibond = (m.ebc / 1.97 + 0.76) / 1.3546;
    totalMcu += (kg * 2.20462 * lovibond) / (vol * 0.264172);
  });
  const srm = totalMcu > 0 ? 1.4922 * Math.pow(totalMcu, 0.6859) : null;
  return {
    ibu: ibuTotal > 0 ? Math.round(ibuTotal) : null,
    ebc: srm != null   ? Math.round(srm * 1.97) : null,
  };
}

function _buildOneLabelHtml(b, recipe, opts = {}) {
  const {
    showQr = false, showStyle = true, showAbv = true,
    showIbu = true, showEbc = true, showPhoto = true,
    showIngredients = true, showDates = true,
  } = (typeof opts === 'boolean' ? { showQr: opts } : opts);

  const accentColor = appSettings.accentColor || '#ff9500';
  const _lum = hex => { const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16); return (0.299*r+0.587*g+0.114*b)/255; };
  const headerTextColor = _lum(accentColor) > 0.55 ? '#111' : '#fff';
  const fmtDate = d => d ? d.split('-').reverse().join('/') : null;
  const fmtQty = i => esc(i.name) + (i.hop_type === 'dryhop' ? ' <span style="color:#888;font-style:italic">(DH)</span>' : '');

  // Ingrédients groupés (Autres : seulement sucre, miel, lactose)
  const AUTRES_LABEL = ['sucre', 'miel', 'lactose', 'épice', 'epice', 'cannelle', 'coriandre', 'gingembre', 'vanille', 'cardamome', 'poivre', 'cumin', 'anis', 'muscade', 'piment', 'zeste'];
  let ingHtml = '';
  if (showIngredients) {
    if (recipe && recipe.ingredients && recipe.ingredients.length) {
      const groups = [
        { cat: 'malt',    label: t('cat.malts'),    filter: null },
        { cat: 'houblon', label: t('cat.houblons'), filter: null },
        { cat: 'autre',   label: t('cat.autres'),   filter: i => AUTRES_LABEL.some(k => i.name.toLowerCase().includes(k)) },
      ];
      groups.forEach(({ cat, label, filter }) => {
        let items = recipe.ingredients.filter(i => i.category === cat);
        if (filter) items = items.filter(filter);
        // Dédoublonnage : unique par (nom, dry hop)
        const seen = new Set();
        items = items.filter(i => {
          const key = i.name.toLowerCase() + '|' + (i.hop_type === 'dryhop' ? '1' : '0');
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
        if (!items.length) return;
        ingHtml += `<div class="beer-label-section">${label}</div>
          <div>${items.map(fmtQty).join(', ')}</div>`;
      });
    } else {
      ingHtml = '<div style="color:#aaa;font-size:6.5pt;font-style:italic">Aucune recette liée</div>';
    }
  }

  const beerStyle = recipe?.style || b.type || '';
  // Style uniquement dans le header (ABV déplacé en bas)
  const subtitle  = showStyle ? beerStyle : '';
  const photoSection = showPhoto
    ? (b.photo
        ? `<img class="beer-label-photo" src="${b.photo}" alt="${esc(b.name)}">`
        : `<div class="beer-label-nophoto">🍺</div>`)
    : '';

  // EBC color bar
  const { ibu, ebc } = _labelIbuEbc(recipe);
  const ebcBarColor = ebc != null ? ebcToColor(ebc) : (accentColor + '44');
  const ebcBar = `<div style="height:2.5mm;background:${ebcBarColor}"></div>`;

  const footLeft = showDates ? [
    b.brew_date     ? `🍺\u202f${fmtDate(b.brew_date)}`     : null,
    b.bottling_date ? `🍾\u202f${fmtDate(b.bottling_date)}` : null,
  ].filter(Boolean).join(' · ') : '';

  // QR code: encode key beer info
  let qrHtml = '';
  if (showQr) {
    const qrData = [
      appSettings.appName || 'BrewHome',
      b.name,
      [beerStyle, b.abv ? b.abv + '% ABV' : null].filter(Boolean).join(' · '),
      ibu != null ? `IBU ${ibu}` : null,
      b.bottling_date ? '🍾 ' + fmtDate(b.bottling_date) : null,
    ].filter(Boolean).join('\n');
    const qrUrl = 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&format=png&data=' + encodeURIComponent(qrData);
    qrHtml = `<img src="${qrUrl}" style="width:14mm;height:14mm;display:block;flex-shrink:0" alt="QR">`;
  }

  // Stats footer : IBU + EBC + ABV (tous regroupés en bas)
  const statsItems = [
    showIbu && ibu != null ? `IBU\u202f${ibu}` : null,
    showEbc && ebc != null ? `EBC\u202f${ebc}` : null,
    showAbv && b.abv       ? `${b.abv}%\u202fABV` : null,
  ].filter(Boolean);
  const statsText = statsItems.join(' · ');
  const footerRight = qrHtml
    || (statsText ? `<span style="font-size:5pt;color:#555;font-weight:700">${statsText}</span>` : `<span style="font-weight:800;color:#f59e0b;letter-spacing:.02em">${esc(appSettings.appName || 'BrewHome')}</span>`);

  return `
    <div class="beer-label">
      <div class="beer-label-header" style="background:${accentColor};color:${headerTextColor}">
        <div class="beer-label-title">${esc(b.name)}</div>
        ${subtitle ? `<div class="beer-label-sub">${subtitle}</div>` : ''}
      </div>
      ${ebcBar}
      ${photoSection}
      <div class="beer-label-body">
        ${ingHtml}
      </div>
      <div class="beer-label-footer" style="${showQr ? 'align-items:center;padding:1mm 3mm' : ''}">
        <span style="color:#000">${footLeft}</span>
        ${footerRight}
      </div>
    </div>`;
}

function _readLabelOpts() {
  const chk = id => document.getElementById(id)?.checked ?? true;
  return {
    showQr:         document.getElementById('label-qr')?.checked || false,
    showStyle:      chk('label-show-style'),
    showAbv:        chk('label-show-abv'),
    showIbu:        chk('label-show-ibu'),
    showEbc:        chk('label-show-ebc'),
    showPhoto:      chk('label-show-photo'),
    showIngredients:chk('label-show-ing'),
    showDates:      chk('label-show-dates'),
  };
}

function renderLabelPreview() {
  const b = S.beers.find(x => x.id === _labelBeerId);
  if (!b) return;
  const recipe  = b.recipe_id ? S.recipes.find(r => r.id === b.recipe_id) : null;
  const copies  = Math.max(1, Math.min(30, parseInt(document.getElementById('label-copies')?.value || '1', 10)));
  const opts    = _readLabelOpts();
  const preview = document.getElementById('label-preview-wrap');
  if (preview) preview.innerHTML = Array.from({ length: copies }, () => _buildOneLabelHtml(b, recipe, opts)).join('');
}

function doPrintLabel() {
  const b = S.beers.find(x => x.id === _labelBeerId);
  if (!b) return;
  const recipe  = b.recipe_id ? S.recipes.find(r => r.id === b.recipe_id) : null;
  const copies  = Math.max(1, Math.min(30, parseInt(document.getElementById('label-copies')?.value || '1', 10)));
  const pageSize = document.getElementById('label-format')?.value || 'A4 landscape';
  const opts    = _readLabelOpts();
  const html    = Array.from({ length: copies }, () => _buildOneLabelHtml(b, recipe, opts)).join('');
  const area    = document.getElementById('label-print-area');
  // Inject dynamic @page rule so the selected format is applied
  let styleTag = document.getElementById('_label-page-style');
  if (!styleTag) { styleTag = document.createElement('style'); styleTag.id = '_label-page-style'; document.head.appendChild(styleTag); }
  styleTag.textContent = `@page{size:${pageSize};margin:10mm}`;
  if (area) { area.innerHTML = html; area.style.display = 'flex'; }
  window.print();
  setTimeout(() => { if (area) { area.innerHTML = ''; area.style.display = 'none'; } }, 800);
}

function printAllCaveLabels() {
  const active = (S.beers || []).filter(b => !b.archived);
  if (!active.length) { toast(t('cave.empty_cave'), 'info'); return; }
  const q = (document.getElementById('cave-search')?.value || '').toLowerCase();
  const visible = q ? active.filter(b => b.name.toLowerCase().includes(q) || (b.type||'').toLowerCase().includes(q)) : active;
  if (!visible.length) { toast(t('common.no_results'), 'info'); return; }

  const html = visible.map(b => {
    const recipe = b.recipe_id ? S.recipes.find(r => r.id === b.recipe_id) : null;
    return _buildOneLabelHtml(b, recipe, false);
  }).join('');

  let styleTag = document.getElementById('_label-page-style');
  if (!styleTag) { styleTag = document.createElement('style'); styleTag.id = '_label-page-style'; document.head.appendChild(styleTag); }
  styleTag.textContent = `@page{size:A4 landscape;margin:10mm}`;
  const area = document.getElementById('label-print-area');
  if (area) { area.innerHTML = html; area.style.display = 'flex'; }
  window.print();
  setTimeout(() => { if (area) { area.innerHTML = ''; area.style.display = 'none'; } }, 800);
}

function previewBeerPhoto(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    // Compress
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      const maxW = 800;
      let w = img.width, h = img.height;
      if (w > maxW) { h = h * maxW / w; w = maxW; }
      canvas.width = w; canvas.height = h;
      canvas.getContext('2d').drawImage(img, 0, 0, w, h);
      const b64 = canvas.toDataURL('image/jpeg', 0.75);
      document.getElementById('beer-f-photo-b64').value = b64;
      document.getElementById('beer-f-photo-preview').src = b64;
      document.getElementById('beer-f-photo-preview').style.display = 'block';
      document.getElementById('beer-f-photo-remove').style.display  = 'flex';
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
}

function removeBeerPhoto() {
  document.getElementById('beer-f-photo-b64').value = '';
  document.getElementById('beer-f-photo-preview').src = '';
  document.getElementById('beer-f-photo-preview').style.display = 'none';
  document.getElementById('beer-f-photo-remove').style.display  = 'none';
  document.getElementById('beer-f-photo').value = '';
}

function showBeerAlert(msg, type = 'danger') {
  const el = document.getElementById('beer-modal-alert');
  if (!el) return;
  if (!msg) { el.classList.remove('show'); return; }
  el.className = `alert alert-${type} show`;
  el.textContent = msg;
}

function _validateBeerFields() {
  const checks = [
    { id: 'beer-f-abv', label: 'ABV (%)', min: 0,   max: 30,   optional: true },
    { id: 'beer-f-33',  label: '33cl',    min: 0,   max: 9999, optional: false },
    { id: 'beer-f-75',  label: '75cl',    min: 0,   max: 9999, optional: false },
    { id: 'beer-f-keg', label: t('cave.field_keg'),  min: 0, max: 1000, optional: true },
  ];
  const errors = [];
  checks.forEach(({ id, label, min, max, optional }) => {
    const el = document.getElementById(id);
    if (!el || (optional && el.value === '')) return;
    el.style.borderColor = '';
    const val = parseFloat(el.value);
    if (isNaN(val) || val < min || val > max) {
      errors.push(`${label} (${min}–${max})`);
      el.style.borderColor = 'var(--danger)';
      el.addEventListener('input', () => { el.style.borderColor = ''; }, { once: true });
    }
  });
  return errors;
}

async function saveBeer() {
  const name = document.getElementById('beer-f-name').value.trim();
  if (!name) { showBeerAlert(t('cave.name_required')); return; }
  const fieldErrors = _validateBeerFields();
  if (fieldErrors.length) {
    showBeerAlert(t('rec.err_field_range').replace('${fields}', fieldErrors.join(', ')));
    return;
  }
  const id = document.getElementById('beer-f-id').value;
  const stock33 = parseInt(document.getElementById('beer-f-33').value) || 0;
  const stock75 = parseInt(document.getElementById('beer-f-75').value) || 0;
  const kegVal = document.getElementById('beer-f-keg').value;
  const kegLiters = kegVal !== '' ? (parseFloat(kegVal) || 0) : null;
  const payload = {
    name,
    type:         document.getElementById('beer-f-type').value || null,
    abv:          parseFloat(document.getElementById('beer-f-abv').value) || null,
    stock_33cl:   stock33,
    stock_75cl:   stock75,
    // On edit: send the (possibly corrected) initial values; on create: not sent for bottles, backend uses stock as initial
    ...(id ? {
      initial_33cl: parseInt(document.getElementById('beer-f-33-init').value) || 0,
      initial_75cl: parseInt(document.getElementById('beer-f-75-init').value) || 0,
    } : {}),
    keg_liters: kegLiters,
    // Always send keg initial when a keg value is present (user may declare a partial keg on creation)
    ...(kegLiters !== null ? {
      keg_initial_liters: parseFloat(document.getElementById('beer-f-keg-init').value) || kegLiters,
    } : {}),
    origin:        document.getElementById('beer-f-origin').value.trim() || null,
    description:   document.getElementById('beer-f-desc').value.trim() || null,
    photo:         document.getElementById('beer-f-photo-b64').value || null,
    brew_date:       document.getElementById('beer-f-brew-date').value || null,
    bottling_date:   document.getElementById('beer-f-bottling-date').value || null,
    refermentation:  document.getElementById('beer-f-refermentation').checked ? 1 : 0,
    refermentation_days: parseInt(document.getElementById('beer-f-refermentation-days').value) || null,
  };
  try {
    if (id) {
      const updated = await api('PUT', `/api/beers/${id}`, payload);
      const idx = S.beers.findIndex(b => b.id === parseInt(id));
      if (idx !== -1) S.beers[idx] = updated;
    } else {
      const created = await api('POST', '/api/beers', payload);
      S.beers.unshift(created);
    }
    closeModal('beer-modal');
    renderCave();
    const stats = await api('GET', '/api/stats');
    updateNavBadges(stats);
    toast(id ? t('cave.beer_updated') : t('cave.beer_added'), 'success');
    _autoPushVitrineDebounced();
  } catch(e) { toast(t('cave.err_save'), 'error'); }
}

async function adjustStock(id, d33, d75) {
  const beer = S.beers.find(b => b.id === id);
  if (!beer) return;
  const payload = {
    stock_33cl: Math.max(0, (beer.stock_33cl||0) + d33),
    stock_75cl: Math.max(0, (beer.stock_75cl||0) + d75),
  };
  try {
    const updated = await api('PATCH', `/api/beers/${id}/stock`, payload);
    const idx = S.beers.findIndex(b => b.id === id);
    if (idx !== -1) S.beers[idx] = { ...S.beers[idx], ...updated };
    // Recompute depletion estimate client-side (stock a changé, daily_rate reste identique)
    const depIdx = (S.depletion || []).findIndex(d => d.beer_id === id);
    if (depIdx !== -1) {
      const nb = S.beers[idx];
      const newL = ((nb.stock_33cl||0)*0.33 + (nb.stock_75cl||0)*0.75 + (nb.keg_liters||0));
      if (newL > 0) {
        const rate = S.depletion[depIdx].daily_rate;
        const daysRem = Math.round(newL / rate);
        const depDate = new Date(); depDate.setDate(depDate.getDate() + daysRem);
        S.depletion[depIdx] = { ...S.depletion[depIdx], current_liters: Math.round(newL*100)/100, days_remaining: daysRem, depletion_date: depDate.toISOString().slice(0,10) };
      } else {
        S.depletion.splice(depIdx, 1);
      }
    }
    renderCave();
    _autoPushVitrineDebounced();
  } catch(e) { toast(t('cave.err_stock'), 'error'); }
}

async function deleteBeer(id) {
  if (!await confirmModal(t('cave.confirm_delete'), { danger: true })) return;
  try {
    await api('DELETE', `/api/beers/${id}`);
    S.beers = S.beers.filter(b => b.id !== id);
    renderCave();
    const stats = await api('GET', '/api/stats');
    updateNavBadges(stats);
    toast(t('cave.beer_deleted'), 'success');
    _autoPushVitrineDebounced();
  } catch(e) { toast(t('cave.err_save'), 'error'); }
}

// ══════════════════════════════════════════════════════════════════════════════
// ── TRANSFERT FÛT ────────────────────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════
let _kegTransferId = null;

function openKegTransferModal(id) {
  const beer = S.beers.find(b => b.id === id);
  if (!beer) return;
  _kegTransferId = id;
  document.getElementById('keg-tr-name').textContent    = beer.name;
  document.getElementById('keg-tr-current').textContent = `${t('cave.keg_available')} ${beer.keg_liters || 0} L`;
  document.getElementById('keg-tr-consumed').value = 0;
  document.getElementById('keg-tr-33').value = 0;
  document.getElementById('keg-tr-75').value = 0;
  document.getElementById('keg-tr-save-btn').disabled = true;
  updateKegCalc();
  openModal('keg-transfer-modal');
}

function updateKegCalc() {
  const beer = S.beers.find(b => b.id === _kegTransferId);
  if (!beer) return;
  const available = beer.keg_liters || 0;
  const consumed  = parseFloat(document.getElementById('keg-tr-consumed').value) || 0;
  const b33       = parseInt(document.getElementById('keg-tr-33').value)          || 0;
  const b75       = parseInt(document.getElementById('keg-tr-75').value)          || 0;
  const bottled   = b33 * 0.33 + b75 * 0.75;
  const total     = consumed + bottled;
  const remaining = Math.max(0, available - total);
  const over      = total > available;
  const ok        = total > 0 && !over;
  const warnStyle = over ? 'color:var(--danger);font-weight:700' : '';
  document.getElementById('keg-tr-calc').innerHTML = `
    <div style="display:grid;grid-template-columns:1fr auto;gap:2px 12px">
      <span style="color:var(--muted)">Disponible en fût</span><span><strong>${available.toFixed(2)} L</strong></span>
      <span style="color:var(--muted)">Consommé directement</span><span><strong>${consumed.toFixed(2)} L</strong></span>
      <span style="color:var(--muted)">Embouteillé (${b33}×33cl + ${b75}×75cl)</span><span><strong>${bottled.toFixed(2)} L</strong></span>
      <span style="${warnStyle}">Total prélevé</span><span style="${warnStyle}"><strong>${total.toFixed(2)} L</strong>${over ? ' ⚠ dépassement' : ''}</span>
      <span style="color:var(--muted)">Restant en fût</span><span><strong>${remaining.toFixed(2)} L</strong></span>
    </div>`;
  document.getElementById('keg-tr-save-btn').disabled = !ok;
}

async function saveKegTransfer() {
  const beer = S.beers.find(b => b.id === _kegTransferId);
  if (!beer) return;
  const available = beer.keg_liters || 0;
  const consumed  = parseFloat(document.getElementById('keg-tr-consumed').value) || 0;
  const b33       = parseInt(document.getElementById('keg-tr-33').value) || 0;
  const b75       = parseInt(document.getElementById('keg-tr-75').value) || 0;
  const total     = consumed + b33 * 0.33 + b75 * 0.75;
  if (total <= 0 || total > available) { toast(t('cave.err_keg_vol'), 'error'); return; }
  const payload = {
    keg_liters: Math.max(0, parseFloat((available - total).toFixed(3))),
    stock_33cl: (beer.stock_33cl || 0) + b33,
    stock_75cl: (beer.stock_75cl || 0) + b75,
  };
  try {
    const updated = await api('PATCH', `/api/beers/${beer.id}/stock`, payload);
    const idx = S.beers.findIndex(b => b.id === beer.id);
    if (idx !== -1) S.beers[idx] = { ...S.beers[idx], ...updated };
    closeModal('keg-transfer-modal');
    renderCave();
    toast(t('cave.keg_saved'), 'success');
  } catch(e) { toast(t('cave.err_keg'), 'error'); }
}

