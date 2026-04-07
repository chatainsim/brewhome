// ══════════════════════════════════════════════════════════════════════════════
// STYLES COURANTS (cave + recettes) — noms simples uniquement
// ══════════════════════════════════════════════════════════════════════════════
const BEER_TYPES = {
  'Ales': ['IPA','Session IPA','Double IPA','West Coast IPA','New England IPA','Hazy IPA','Pale Ale','American Pale Ale','Amber Ale','Brown Ale','Red Ale','Blonde Ale','Golden Ale'],
  'Blondes & Blanches': ['Blonde','Blanche','Witbier','Weizen','Dunkelweizen','Weizenbock','Kristallweizen'],
  'Ambrées & Brunes': ['Ambrée','Brune','Stout','Imperial Stout','Oatmeal Stout','Milk Stout','Sweet Stout','Dry Stout','Porter','Robust Porter','Baltic Porter'],
  'Belges': ['Triple','Dubbel','Quadrupel','Saison','Abbaye','Trappiste','Belgian Pale Ale','Belgian Golden Strong','Belgian Dark Strong','Bière de Garde'],
  'Lagers': ['Lager','Pilsner','Pils','Bock','Doppelbock','Maibock','Dunkel','Schwarzbier','Märzen','Festbier','Helles','Kölsch','Altbier','Vienna Lager','Exportbier'],
  'Sours & Spécialités': ['Sour','Lambic','Gueuze','Kriek','Fruitée','Gose','Berliner Weisse','Flanders Red','Oud Bruin','Brett Beer','Fumée','Rauchbier','Barley Wine','Wheatwine','Scotch Ale','Wee Heavy','Old Ale'],
  'Sans alcool': ['Sans alcool'],
  'Autre': ['Autre'],
};

function _beerTypeLabel(grp) {
  const map = {
    'Ales': t('rec.bt_ales'), 'Blondes & Blanches': t('rec.bt_blanches'),
    'Ambrées & Brunes': t('rec.bt_ambrees'), 'Belges': t('rec.bt_belges'),
    'Lagers': t('rec.bt_lagers'), 'Sours & Spécialités': t('rec.bt_sours'),
    'Sans alcool': t('rec.bt_na'), 'Autre': t('rec.bt_other'),
  };
  return map[grp] || grp;
}

// ── Helpers groupement BJCP ───────────────────────────────────────────────────
function _bjcpByCategory(filter) {
  const bycat = {};
  S.bjcp.filter(filter).forEach(s => {
    if (!bycat[s.category]) bycat[s.category] = [];
    bycat[s.category].push(s);
  });
  return bycat;
}

// ── Brew stats calculator (Brewfather-style) ──────────────────────────────────
const CALC_PARAMS = {
  og:  { label: 'OG',  unit: '',  dec: 3, min: 1.020, max: 1.130 },
  fg:  { label: 'FG',  unit: '',  dec: 3, min: 1.002, max: 1.030 },
  abv: { label: 'ABV', unit: '%', dec: 1, min: 0,     max: 14    },
  ibu: { label: 'IBU', unit: '',  dec: 0, min: 0,     max: 120   },
  ebc: { label: 'EBC', unit: '',  dec: 0, min: 0,     max: 120   },
};

function renderCalcBar(key, val, range, cfg) {
  const span = cfg.max - cfg.min;
  const hasRange = range && range[0] != null && range[1] != null;

  let rangeHtml = '';
  if (hasRange) {
    const rL = Math.min(100, Math.max(0, (range[0] - cfg.min) / span * 100));
    const rR = Math.min(100, Math.max(0, (range[1] - cfg.min) / span * 100));
    rangeHtml = `<div class="calc-bar-range" style="left:${rL.toFixed(1)}%;width:${(rR - rL).toFixed(1)}%"></div>`;
  }

  let markerHtml = '';
  let valColor = 'var(--amber)';
  if (val != null) {
    const pct = Math.min(100, Math.max(0, (val - cfg.min) / span * 100));
    if (hasRange) valColor = (val >= range[0] && val <= range[1]) ? 'var(--success)' : 'var(--danger)';
    markerHtml = `<div class="calc-bar-marker" style="left:${pct.toFixed(1)}%;background:${valColor}"></div>`;
  }

  const valStr    = val != null ? val.toFixed(cfg.dec) + (cfg.unit ? ' ' + cfg.unit : '') : '–';
  const targetStr = hasRange ? `${range[0].toFixed(cfg.dec)}–${range[1].toFixed(cfg.dec)}${cfg.unit ? cfg.unit : ''}` : '';

  return `<div class="calc-bar-row">
    <div class="calc-bar-lbl">${cfg.label}</div>
    <div class="calc-bar-track">${rangeHtml}${markerHtml}</div>
    <div class="calc-bar-val" style="color:${valColor}">${valStr}</div>
    <div class="calc-bar-target">${targetStr ? '⌖ ' + targetStr : ''}</div>
  </div>`;
}

function calcBrewStats() {
  const panel = document.getElementById('rec-calc-panel');
  if (!panel) return;

  const vol = parseFloat(document.getElementById('rec-volume').value) || 20;
  const eff = parseFloat(document.getElementById('rec-efficiency').value) || 72;

  // Selected BJCP style ranges
  const styleName = (document.getElementById('rec-style').value || '').trim();
  const bjcpStyle = S.bjcp.find(x => x.name === styleName) || null;

  // ── OG (L°/kg metric) ───────────────────────────────────────────────────────
  let ogPoints = 0;
  recIngredients.filter(i => i.category === 'malt').forEach(m => {
    if (!m.quantity) return;
    let guVal = m.gu != null ? m.gu : null;
    if (guVal == null) {
      const cat = S.catalog.find(c => c.name.toLowerCase() === m.name.toLowerCase());
      if (cat && cat.gu != null) guVal = cat.gu;
    }
    if (guVal == null) return;
    const kg = m.unit === 'kg' ? m.quantity : m.quantity / 1000;
    ogPoints += kg * guVal * (eff / 100);
  });
  // ── Fermentescibles autres (fruit, miel, sucre, etc. avec GU renseigné) ──────
  recIngredients.filter(i => i.category === 'autre').forEach(a => {
    if (!a.quantity) return;
    let guVal = a.gu != null ? a.gu : null;
    if (guVal == null) {
      const cat = S.catalog.find(c => c.name.toLowerCase() === a.name.toLowerCase());
      if (cat && cat.gu != null) guVal = cat.gu;
    }
    if (guVal == null) return;
    const kg = a.unit === 'kg' ? a.quantity : a.unit === 'g' ? a.quantity / 1000 : 0;
    if (kg <= 0) return;
    // Ajouts en fermentation/conditionnement : 100% disponible (pas de perte de brassage)
    const effFactor = ['fermentation', 'packaging'].includes(a.other_type) ? 1.0 : eff / 100;
    ogPoints += kg * guVal * effFactor;
  });

  const og = ogPoints > 0 ? 1 + ogPoints / vol / 1000 : null;

  // ── FG (75% attenuation) ─────────────────────────────────────────────────────
  const fg = og != null ? 1 + (og - 1) * 0.25 : null;

  // ── ABV ──────────────────────────────────────────────────────────────────────
  const abv = (og != null && fg != null) ? (og - fg) * 131.25 : null;

  // ── IBU (Tinseth or Rager) ───────────────────────────────────────────────────
  const wortOG = og || 1.050;
  const _ibuFormula = appSettings.energy?.ibu_formula || 'tinseth';
  let ibuTotal = 0;
  recIngredients.filter(i => i.category === 'houblon').forEach(h => {
    if (!h.quantity || !h.alpha) return;
    const ht = h.hop_type || 'ebullition';
    if (ht === 'dryhop') return;
    const mins  = ht === 'whirlpool' ? 15 : (h.hop_time != null ? h.hop_time : 60);
    const grams = h.unit === 'kg' ? h.quantity * 1000 : h.quantity;
    if (_ibuFormula === 'rager') {
      const util = 18.11 + 13.86 * Math.tanh((mins - 31.32) / 18.27);
      const adj  = wortOG > 1.050 ? (wortOG - 1.050) / 0.2 : 0;
      ibuTotal += (grams * (util / 100) * (h.alpha / 100) * 1000) / (vol * (1 + adj));
    } else {
      const bigness  = 1.65 * Math.pow(0.000125, wortOG - 1);
      const timeFact = (1 - Math.exp(-0.04 * mins)) / 4.15;
      ibuTotal += bigness * timeFact * (h.alpha / 100) * grams * 1000 / vol;
    }
  });
  const ibuVal = ibuTotal > 0 ? ibuTotal : null;

  // Live IBU badge in hop section header
  const _ibuBadge = document.getElementById('rec-ibu-badge');
  if (_ibuBadge) _ibuBadge.textContent = ibuVal != null ? `· IBU\u00a0${ibuVal.toFixed(0)}` : '';

  // ── EBC / SRM (formule Morey) ─────────────────────────────────────────────
  let totalMcu = 0;
  recIngredients.filter(i => i.category === 'malt').forEach(m => {
    if (!m.quantity) return;
    let mEbc = m.ebc != null ? m.ebc : null;
    if (mEbc == null) {
      const cat = S.catalog.find(c => c.name.toLowerCase() === m.name.toLowerCase());
      if (cat && cat.ebc != null) mEbc = cat.ebc;
    }
    if (mEbc == null) return;
    const kg       = m.unit === 'kg' ? m.quantity : m.quantity / 1000;
    const lovibond = (mEbc / 1.97 + 0.76) / 1.3546;
    totalMcu += (kg * 2.20462 * lovibond) / (vol * 0.264172);
  });
  const srmVal = totalMcu > 0 ? 1.4922 * Math.pow(totalMcu, 0.6859) : null;
  const ebcVal = srmVal != null ? srmVal * 1.97 : null;

  // ── Render ────────────────────────────────────────────────────────────────────
  const rng = bjcpStyle ? {
    og:  [bjcpStyle.og_min,  bjcpStyle.og_max],
    fg:  [bjcpStyle.fg_min,  bjcpStyle.fg_max],
    abv: [bjcpStyle.abv_min, bjcpStyle.abv_max],
    ibu: [bjcpStyle.ibu_min, bjcpStyle.ibu_max],
    ebc: [bjcpStyle.ebc_min, bjcpStyle.ebc_max],
  } : {};

  const styleLabel = bjcpStyle
    ? `<span style="color:var(--muted);font-weight:400;font-size:.7rem;text-transform:none;letter-spacing:0"> — ${esc(bjcpStyle.name)}</span>`
    : '';

  // ── Coût total de la recette ──────────────────────────────────────────────
  const CAT_COST_META = {
    malt:    { label: t('cat.malts'),    color: 'var(--malt)',  icon: 'fas fa-seedling' },
    houblon: { label: t('cat.houblons'), color: 'var(--hop)',   icon: 'fas fa-leaf' },
    levure:  { label: t('cat.levures'),  color: 'var(--yeast)', icon: 'fas fa-flask' },
    autre:   { label: t('cat.autres'),   color: 'var(--other)', icon: 'fas fa-box' },
  };
  const catCosts = { malt: 0, houblon: 0, levure: 0, autre: 0 };
  let totalCost = 0, hasCost = false;
  recIngredients.forEach(ing => {
    const c = ingCost(ing);
    if (c !== null) { catCosts[ing.category] = (catCosts[ing.category] || 0) + c; totalCost += c; hasCost = true; }
  });
  // Coût de l'eau (prix/L × volume total eau)
  const waterPrice = (appSettings.water || {}).price;
  let waterCost = null;
  if (waterPrice != null) {
    // totalWater est déjà calculé plus haut via recCalc — on le recalcule ici
    const grainKg2 = recIngredients.filter(i=>i.category==='malt')
      .reduce((s,i) => s + (i.unit==='kg' ? i.quantity : i.quantity/1000), 0);
    const boil2  = parseFloat(document.getElementById('rec-boil-time').value) || 60;
    const ratio2 = parseFloat(document.getElementById('rec-mash-ratio').value) || 3;
    const evap2  = parseFloat(document.getElementById('rec-evap').value) || 3;
    const abs2   = parseFloat(document.getElementById('rec-absorption').value) || 0.8;
    const preboil2   = vol + evap2 * (boil2/60);
    const totalWater2 = preboil2 + grainKg2 * abs2;
    waterCost = totalWater2 * waterPrice;
    totalCost += waterCost;
    hasCost = true;
  }
  // Coût gaz (montant fixe par brassin)
  const gasCost  = parseFloat(appSettings.energy?.gas_per_brew)  || 0;
  const elecCost = parseFloat(appSettings.energy?.elec_per_brew) || 0;
  if (gasCost  > 0) { totalCost += gasCost;  hasCost = true; }
  if (elecCost > 0) { totalCost += elecCost; hasCost = true; }

  const costHtml = hasCost ? `
    <div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border)">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
        <div style="font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)"><i class="fas fa-euro-sign"></i> ${t('rec.cost_materials_title')}</div>
        <div style="display:flex;gap:16px;align-items:baseline">
          <span style="font-size:1.1rem;font-weight:800;color:var(--success)">${totalCost.toFixed(2)} €</span>
          <span style="font-size:.8rem;color:var(--muted)">${(totalCost / vol).toFixed(2)} €/L</span>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:${waterCost !== null ? '8px' : '0'}">
        ${['malt','houblon','levure','autre'].map(cat => {
          const m = CAT_COST_META[cat];
          const c = catCosts[cat] || 0;
          const pct = totalCost > 0 ? (c / totalCost * 100) : 0;
          if (c === 0) return `<div style="background:var(--card2);border-radius:10px;padding:10px 12px;opacity:.35">
            <div style="font-size:.72rem;color:${m.color};font-weight:600;margin-bottom:4px"><i class="${m.icon}"></i> ${m.label}</div>
            <div style="font-size:.9rem;font-weight:700;color:var(--muted)">—</div>
          </div>`;
          return `<div style="background:var(--card2);border-radius:10px;padding:10px 12px;border-left:3px solid ${m.color}">
            <div style="font-size:.72rem;color:${m.color};font-weight:600;margin-bottom:4px"><i class="${m.icon}"></i> ${m.label}</div>
            <div style="font-size:.95rem;font-weight:700;color:var(--text)">${c.toFixed(2)} €</div>
            <div style="font-size:.72rem;color:var(--muted);margin-top:2px">${pct.toFixed(0)} ${t('rec.cost_pct_total')}</div>
          </div>`;
        }).join('')}
      </div>
      ${waterCost !== null ? `
      <div style="display:flex;align-items:center;gap:8px;margin-top:6px;padding:8px 12px;background:var(--card2);border-radius:10px;border-left:3px solid var(--info)">
        <i class="fas fa-droplet" style="color:var(--info);font-size:.8rem"></i>
        <span style="font-size:.82rem;color:var(--muted);flex:1">${t('rec.cost_water').replace('${price}', ((appSettings.water||{}).price||0).toFixed(4))}</span>
        <span style="font-size:.9rem;font-weight:700;color:var(--info)">${waterCost.toFixed(2)} €</span>
        <span style="font-size:.75rem;color:var(--muted)">${(waterCost/totalCost*100).toFixed(0)} ${t('rec.cost_pct_total')}</span>
      </div>` : ''}
      ${gasCost > 0 ? `
      <div style="display:flex;align-items:center;gap:8px;margin-top:6px;padding:8px 12px;background:var(--card2);border-radius:10px;border-left:3px solid var(--amber)">
        <i class="fas fa-fire-flame-curved" style="color:var(--amber);font-size:.8rem"></i>
        <span style="font-size:.82rem;color:var(--muted);flex:1">${t('rec.cost_gas')}</span>
        <span style="font-size:.9rem;font-weight:700;color:var(--amber)">${gasCost.toFixed(2)} €</span>
        <span style="font-size:.75rem;color:var(--muted)">${(gasCost/totalCost*100).toFixed(0)} ${t('rec.cost_pct_total')}</span>
      </div>` : ''}
      ${elecCost > 0 ? `
      <div style="display:flex;align-items:center;gap:8px;margin-top:6px;padding:8px 12px;background:var(--card2);border-radius:10px;border-left:3px solid var(--gold)">
        <i class="fas fa-bolt" style="color:var(--gold);font-size:.8rem"></i>
        <span style="font-size:.82rem;color:var(--muted);flex:1">${t('rec.cost_elec')}</span>
        <span style="font-size:.9rem;font-weight:700;color:var(--gold)">${elecCost.toFixed(2)} €</span>
        <span style="font-size:.75rem;color:var(--muted)">${(elecCost/totalCost*100).toFixed(0)} ${t('rec.cost_pct_total')}</span>
      </div>` : ''}
    </div>` : '';

  const _ibuLabel = _ibuFormula === 'rager'
    ? `<span style="font-size:.7rem;font-weight:400;color:var(--muted);margin-left:6px">IBU: Rager</span>`
    : `<span style="font-size:.7rem;font-weight:400;color:var(--muted);margin-left:6px">IBU: Tinseth</span>`;

  const _ebcColor = ebcVal != null ? ebcToColor(ebcVal) : null;
  const _colorSwatchHtml = _ebcColor ? `
    <div style="display:flex;align-items:center;gap:10px;padding:6px 0 4px;margin-top:2px">
      <div style="width:34px;height:34px;border-radius:50%;flex-shrink:0;background:${_ebcColor};
        border:2px solid rgba(255,255,255,.18);box-shadow:inset 0 -3px 8px rgba(0,0,0,.35),0 2px 6px rgba(0,0,0,.3)"></div>
      <div>
        <div style="font-size:.82rem;font-weight:600;color:var(--text)">
          EBC\u00a0${ebcVal.toFixed(0)}&ensp;·&ensp;${t('rec.ebc_srm')}\u00a0${srmVal.toFixed(0)}
        </div>
        <div style="font-size:.7rem;color:var(--muted)">${t('rec.ebc_morey')}</div>
      </div>
    </div>` : '';

  panel.innerHTML = `<div class="calc-panel">
    <div class="calc-panel-title"><i class="fas fa-chart-bar"></i> ${t('rec.print_estimations')}${styleLabel}${_ibuLabel}</div>
    ${renderCalcBar('og',  og,     rng.og  || null, CALC_PARAMS.og)}
    ${renderCalcBar('fg',  fg,     rng.fg  || null, CALC_PARAMS.fg)}
    ${renderCalcBar('abv', abv,    rng.abv || null, CALC_PARAMS.abv)}
    ${renderCalcBar('ibu', ibuVal, rng.ibu || null, CALC_PARAMS.ibu)}
    ${renderCalcBar('ebc', ebcVal, rng.ebc || null, CALC_PARAMS.ebc)}
    ${_colorSwatchHtml}
    ${costHtml}
  </div>`;
}

// ── BJCP search (champ style recette) ────────────────────────────────────────
function bjcpSearch(input) {
  const q   = input.value.toLowerCase().trim();
  const sug = document.getElementById('bjcp-sug');
  closeBjcpSuggest();
  let html = '';
  let count = 0;

  // Styles courants en premier
  const commonMatches = [];
  for (const types of Object.values(BEER_TYPES)) {
    types.forEach(t => { if (!q || t.toLowerCase().includes(q)) commonMatches.push(t); });
  }
  if (commonMatches.length) {
    html += `<div class="ing-suggest-cat">Styles courants</div>`;
    commonMatches.slice(0, q ? 30 : 10).forEach(t => {
      html += `<div class="ing-suggest-item" onmousedown="selectBjcp(${JSON.stringify(t).replace(/"/g,'&quot;')},0)"><span>${esc(t)}</span></div>`;
      count++;
    });
  }

  // Styles BJCP depuis la DB
  const bycat = _bjcpByCategory(s => !q || s.name.toLowerCase().includes(q) || s.category.toLowerCase().includes(q));
  for (const [cat, styles] of Object.entries(bycat)) {
    html += `<div class="ing-suggest-cat" style="color:var(--gold)">BJCP — ${esc(cat)}</div>`;
    styles.forEach(s => {
      html += `<div class="ing-suggest-item" onmousedown="selectBjcp(${JSON.stringify(s.name).replace(/"/g,'&quot;')},${s.id})"><span style="font-size:.83rem">${esc(s.name)}</span></div>`;
      count++;
    });
    if (!q && count > 50) break;
  }
  if (!html) return;
  sug.innerHTML = html;
  sug.classList.add('open');
}

function closeBjcpSuggest() {
  document.getElementById('bjcp-sug').classList.remove('open');
}

function selectBjcp(styleName, bjcpId) {
  document.getElementById('rec-style').value = styleName;
  closeBjcpSuggest();
  calcBrewStats();
}

// ── TYPE BIÈRE (cave) ─────────────────────────────────────────────────────────
function beerTypeSearch(input) {
  const q   = input.value.toLowerCase().trim();
  const sug = document.getElementById('beer-type-sug');
  closeBeerTypeSuggest();
  let html = '';

  // Styles courants
  for (const [grp, types] of Object.entries(BEER_TYPES)) {
    const matches = types.filter(t => !q || t.toLowerCase().includes(q));
    if (!matches.length) continue;
    html += `<div class="ing-suggest-cat">${esc(_beerTypeLabel(grp))}</div>`;
    matches.forEach(t => {
      html += `<div class="ing-suggest-item" onmousedown="selectBeerType('${t.replace(/'/g,"\\'")}')"><span>${esc(t)}</span></div>`;
    });
  }

  // Styles BJCP depuis la DB (uniquement si recherche active)
  if (q) {
    const bycat = _bjcpByCategory(s => s.name.toLowerCase().includes(q) || s.category.toLowerCase().includes(q));
    for (const [cat, styles] of Object.entries(bycat)) {
      html += `<div class="ing-suggest-cat" style="color:var(--gold)">BJCP — ${esc(cat)}</div>`;
      styles.forEach(s => {
        html += `<div class="ing-suggest-item" onmousedown="selectBeerType('${s.name.replace(/'/g,"\\'")}')"><span style="font-size:.83rem">${esc(s.name)}</span></div>`;
      });
    }
  }

  if (!html) return;
  sug.innerHTML = html;
  sug.classList.add('open');
}

function closeBeerTypeSuggest() {
  const sug = document.getElementById('beer-type-sug');
  if (sug) sug.classList.remove('open');
}

function selectBeerType(type) {
  document.getElementById('beer-f-type').value = type;
  closeBeerTypeSuggest();
}

// ══════════════════════════════════════════════════════════════════════════════
// SPINDLES
// ══════════════════════════════════════════════════════════════════════════════
let _spindleChart = null;
let _spindleChartId = null;
let _spindleChartSeq = 0;  // anti-race : ignore les réponses obsolètes

function spindleAge(dateStr) {
  if (!dateStr) return { color: 'var(--muted)', label: t('spin.age_no_data'), fresh: false };
  const d = new Date(dateStr.replace(' ', 'T'));
  if (isNaN(d.getTime())) return { color: 'var(--muted)', label: '—', fresh: false };
  const mins = (Date.now() - d.getTime()) / 60000;
  const hrs  = mins / 60;
  let label;
  if (mins < 2)       label = t('spin.age_now');
  else if (mins < 60) label = Math.round(mins) + ' min';
  else if (hrs < 5)   label = Math.round(hrs) + ' h ' + (Math.round(mins) % 60 ? Math.round(mins) % 60 + ' min' : '');
  else                label = Math.round(hrs) + ' h';
  const color = hrs < 1 ? 'var(--success)' : hrs < 5 ? '#f59e0b' : 'var(--danger)';
  return { color, label: label.trim(), fresh: hrs < 1 };
}

// ══════════════════════════════════════════════════════════════════════════════
// ── SODA KEGS ─────────────────────────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════

function renderKegs() {
  const grid  = document.getElementById('kegs-grid');
  const empty = document.getElementById('kegs-empty');
  const stats = document.getElementById('kegs-stats');
  const kegs  = S.sodaKegs;

  // ── Revision alert banner ────────────────────────────────────────────────
  const alertEl = document.getElementById('kegs-revision-alert');
  if (alertEl) {
    const today = new Date(); today.setHours(0,0,0,0);
    const overdue = [], soon = [];
    kegs.filter(k => k.next_revision_date && !k.archived).forEach(k => {
      const rev  = new Date(k.next_revision_date);
      const days = Math.round((rev - today) / 86400000);
      if      (days < 0)   overdue.push({ k, days });
      else if (days <= 30) soon.push({ k, days });
    });
    const items = [...overdue, ...soon];
    if (items.length) {
      const hasOverdue = overdue.length > 0;
      const color  = hasOverdue ? 'var(--danger)' : 'var(--amber)';
      const bg     = hasOverdue ? 'rgba(239,68,68,.07)' : 'rgba(245,158,11,.07)';
      const border = hasOverdue ? 'rgba(239,68,68,.25)' : 'rgba(245,158,11,.25)';
      const icon   = hasOverdue ? 'fa-triangle-exclamation' : 'fa-clock';
      const parts  = items.map(({ k, days }) => {
        const label = days < 0
          ? `<span style="color:var(--danger)">${t('keg.revision_overdue')}</span>`
          : `<span style="color:var(--amber)">${t('keg.revision_soon').replace('${days}', days)}</span>`;
        return `<span style="cursor:pointer" onclick="openKegDetail(${k.id})"><strong>${esc(k.name)}</strong> ${label}</span>`;
      }).join('<span style="color:var(--border);margin:0 6px">·</span>');
      alertEl.style.display = '';
      alertEl.innerHTML = `<div style="padding:8px 14px;background:${bg};border:1px solid ${border};border-radius:10px;font-size:.82rem;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <i class="fas ${icon}" style="color:${color}"></i>
        <span style="color:var(--muted);white-space:nowrap">${t('keg.revision_alert_title')} :</span>
        ${parts}
      </div>`;
    } else {
      alertEl.style.display = 'none';
    }
  }

  // Stats
  const total      = kegs.length;
  const fermenting = kegs.filter(k => k.status === 'fermenting').length;
  const serving    = kegs.filter(k => k.status === 'serving').length;
  const emptyCount = kegs.filter(k => k.status === 'empty').length;

  const volServing  = kegs.filter(k => k.status === 'serving' && k.current_liters > 0)
                         .reduce((s, k) => s + (k.current_liters || 0), 0);
  const volTotal    = kegs.filter(k => k.volume_total > 0)
                         .reduce((s, k) => s + (k.volume_total || 0), 0);

  const today = new Date(); today.setHours(0,0,0,0);
  const revDue = kegs.filter(k => k.next_revision_date && !k.archived && new Date(k.next_revision_date) <= new Date(today.getTime() + 30*86400000));
  const revOverdue = revDue.filter(k => new Date(k.next_revision_date) < today);
  const revColor = revOverdue.length ? 'var(--danger)' : revDue.length ? 'var(--amber)' : 'var(--success)';
  const revVal   = revDue.length ? revDue.length : '✓';
  const revTip   = revDue.length
    ? revDue.map(k => k.name).join(', ')
    : t('keg.stat_rev_ok_tip');

  stats.innerHTML = `
    <div class="stat"><div class="stat-val">${total}</div><div class="stat-lbl">${t('keg.stat_total')}</div></div>
    <div class="stat"><div class="stat-val" style="color:var(--amber)">${fermenting}</div><div class="stat-lbl">${t('keg.stat_fermenting')}</div></div>
    <div class="stat"><div class="stat-val" style="color:var(--success)">${serving}</div><div class="stat-lbl">${t('keg.stat_serving')}</div></div>
    <div class="stat"><div class="stat-val" style="color:var(--muted)">${emptyCount}</div><div class="stat-lbl">${t('keg.stat_empty')}</div></div>
    <div class="stat"><div class="stat-val" style="color:var(--info)">${volServing > 0 ? volServing.toFixed(1)+'L' : '–'}</div><div class="stat-lbl">${t('keg.stat_vol_serving')}</div></div>
    <div class="stat"><div class="stat-val" style="color:var(--muted)">${volTotal > 0 ? volTotal.toFixed(0)+'L' : '–'}</div><div class="stat-lbl">${t('keg.stat_capacity')}</div></div>
    <div class="stat" title="${esc(revTip)}"><div class="stat-val" style="color:${revColor}">${revVal}</div><div class="stat-lbl">${t('keg.stat_revisions')}</div></div>
  `;

  if (!kegs.length) {
    grid.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  const statusColors = { empty: 'var(--muted)', fermenting: 'var(--amber)', serving: 'var(--success)', cleaning: '#60a5fa' };
  const statusLabels = { empty: t('keg.status_empty'), fermenting: t('keg.status_fermenting'), serving: t('keg.status_serving'), cleaning: t('keg.status_cleaning') };
  const typeLabels = { corny19: t('keg.type_corny19'), corny6: t('keg.type_corny6') };

  grid.innerHTML = kegs.map(k => {
    const color  = k.color || '#f59e0b';
    const sColor = statusColors[k.status] || 'var(--muted)';
    const sLabel = statusLabels[k.status] || k.status;
    // Pour "other", keg_type contient le texte libre saisi
    const tLabel = typeLabels[k.keg_type] || (k.keg_type !== 'other' ? k.keg_type : '') || '';

    // Photo / placeholder — même structure que beer-card cave
    const kegIcon = k.keg_type === 'corny19'
      ? `<i class="fas fa-jar" style="font-size:3.2rem;color:${color}"></i>`
      : k.keg_type === 'corny6'
      ? `<i class="fas fa-flask" style="font-size:2.4rem;color:${color}"></i>`
      : `<i class="fas fa-jar" style="font-size:2.8rem;color:${color}"></i>`;
    const photoHtml = k.photo
      ? `<div class="beer-photo" style="cursor:pointer" onclick="openKegDetail(${k.id})"><img src="${esc(k.photo)}" alt="${esc(k.name)}"></div>`
      : `<div style="width:100%;height:160px;position:relative;background:var(--card2);overflow:hidden;cursor:pointer" onclick="openKegDetail(${k.id})"><div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);display:flex;flex-direction:column;align-items:center;gap:4px">${kegIcon}${k.volume_total ? `<span style="font-size:.7rem;font-weight:600;color:var(--muted);letter-spacing:.04em">${k.volume_total} L</span>` : ''}</div></div>`;

    // Barre de volume — pattern bottle-bar du thème
    let volumeHtml = '';
    if (k.volume_total && k.current_liters != null) {
      const pct      = Math.min(100, Math.round((k.current_liters / k.volume_total) * 100));
      const barColor = pct > 50 ? 'var(--success)' : pct > 20 ? 'var(--amber)' : 'var(--danger)';
      volumeHtml = `
        <div style="margin:8px 0 4px;padding:7px 10px;background:rgba(245,158,11,.07);border:1px solid rgba(245,158,11,.2);border-radius:8px">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
            <i class="fas fa-jar" style="color:${color};font-size:.85rem"></i>
            <span style="font-weight:700;font-size:.9rem">${k.current_liters} L</span>
            <span style="color:var(--muted);font-size:.78rem">/ ${k.volume_total} L</span>
            <span style="color:var(--muted);font-size:.75rem;margin-left:auto">${pct}%</span>
          </div>
          <div class="bottle-bar" style="width:100%"><div class="bottle-bar-fill" style="width:${pct}%;background:${barColor}"></div></div>
        </div>`;
    }

    // Lien brassin / bière associé (lien direct vers la fiche)
    let linkHtml = '';
    if (k.status === 'fermenting' && k.brew_name) {
      linkHtml = `<div style="font-size:.78rem;margin-top:4px;margin-bottom:2px">
        <a href="#" onclick="event.preventDefault();goToBrew(${k.brew_id})" style="color:var(--amber)">
          <i class="fas fa-fire-burner"></i> ${esc(k.brew_name)}</a></div>`;
    } else if (k.status === 'serving' && k.beer_name) {
      linkHtml = `<div style="font-size:.78rem;margin-top:4px;margin-bottom:2px">
        <a href="#" onclick="event.preventDefault();goToBeerDetail(${k.beer_id})" style="color:var(--success)">
          <i class="fas fa-beer-mug-empty"></i> ${esc(k.beer_name)}</a></div>`;
    }

    // Métadonnées techniques (volume / poids)
    const meta = [
      k.volume_total   ? `${k.volume_total} L` : '',
      k.volume_ferment ? `<i class="fas fa-temperature-arrow-up" style="font-size:.7rem"></i> ${k.volume_ferment} L` : '',
      k.weight_empty   ? `<i class="fas fa-weight-scale" style="font-size:.7rem"></i> ${k.weight_empty} kg` : '',
    ].filter(Boolean).join(' · ');

    return `<div class="beer-card" data-id="${k.id}" draggable="true" style="position:relative">
      <span class="beer-drag-handle" title="${t('keg.drag_to_reorder')}"><i class="fas fa-grip-vertical"></i></span>
      ${photoHtml}
      <div class="beer-body">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px;cursor:pointer" onclick="openKegDetail(${k.id})">
          <div class="beer-name">${esc(k.name)}</div>
          <span style="background:${sColor};color:#fff;padding:2px 9px;border-radius:20px;font-size:.72rem;white-space:nowrap;margin-left:6px">${sLabel}</span>
        </div>
        <div class="beer-type" style="cursor:pointer" onclick="openKegDetail(${k.id})">${k.manufacturer ? `<span style="color:var(--muted)">${esc(k.manufacturer)}</span>${tLabel || meta ? ' · ' : ''}` : ''}${tLabel}${tLabel && meta ? ' · ' : ''}${meta}</div>
        ${volumeHtml}
        ${linkHtml}
        ${k.notes ? `<div style="font-size:.78rem;color:var(--muted);margin-top:6px;font-style:italic;line-height:1.4">${esc(k.notes).substring(0,100)}${k.notes.length>100?'…':''}</div>` : ''}
        ${(() => { if (!k.next_revision_date) return ''; const rev = new Date(k.next_revision_date); const today = new Date(); today.setHours(0,0,0,0); const days = Math.round((rev - today) / 86400000); if (days < 0) return `<div style="font-size:.75rem;margin-top:5px;color:var(--danger)"><i class="fas fa-triangle-exclamation"></i> ${t('keg.revision_overdue')}</div>`; if (days <= 30) return `<div style="font-size:.75rem;margin-top:5px;color:var(--amber)"><i class="fas fa-clock"></i> ${t('keg.revision_soon').replace('${days}', days)}</div>`; return `<div style="font-size:.75rem;margin-top:5px;color:var(--muted)"><i class="fas fa-calendar-check"></i> ${k.next_revision_date}</div>`; })()}
        <div style="display:flex;gap:5px;margin-top:10px">
          ${k.status === 'serving' ? `<button class="btn btn-sm btn-ghost" onclick="openKegPourModal(${k.id})" style="flex:1;color:var(--amber)"><i class="fas fa-beer-mug-empty"></i> ${t('keg.pour_amount')}</button>` : `<button class="btn btn-sm btn-ghost" onclick="openKegStatusModal(${k.id})" style="flex:1"><i class="fas fa-toggle-on"></i> ${t('keg.status_label')}</button>`}
          <button class="btn btn-icon btn-ghost btn-sm" onclick="openKegStatusModal(${k.id})" title="${t('keg.status_label')}"><i class="fas fa-toggle-on"></i></button>
          <button class="btn btn-icon btn-ghost btn-sm" onclick="openKegModal(${k.id})" title="${t('common.edit')}"><i class="fas fa-pen"></i></button>
          <button class="btn btn-icon btn-danger btn-sm" onclick="deleteKeg(${k.id})" title="${t('common.delete')}"><i class="fas fa-trash"></i></button>
        </div>
      </div>
    </div>`;
  }).join('');

  // ── Drag & drop reorder ──
  grid.querySelectorAll('.beer-card[draggable]').forEach(card => {
    card.addEventListener('dragstart', e => {
      e.dataTransfer.setData('text/plain', card.dataset.id);
      e.dataTransfer.effectAllowed = 'move';
      setTimeout(() => card.classList.add('dragging'), 0);
    });
    card.addEventListener('dragend', () => {
      card.classList.remove('dragging');
      grid.querySelectorAll('.beer-card').forEach(c => c.classList.remove('drag-over'));
    });
    card.addEventListener('dragover', e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      grid.querySelectorAll('.beer-card').forEach(c => c.classList.remove('drag-over'));
      const srcId = parseInt(e.dataTransfer.getData('text/plain'));
      if (srcId !== parseInt(card.dataset.id)) card.classList.add('drag-over');
    });
    card.addEventListener('dragleave', () => card.classList.remove('drag-over'));
    card.addEventListener('drop', e => {
      e.preventDefault();
      const srcId = parseInt(e.dataTransfer.getData('text/plain'));
      const tgtId = parseInt(card.dataset.id);
      if (!srcId || srcId === tgtId) return;
      const mi = S.sodaKegs.findIndex(k => k.id === srcId);
      const ti = S.sodaKegs.findIndex(k => k.id === tgtId);
      if (mi === -1 || ti === -1) return;
      const [moved] = S.sodaKegs.splice(mi, 1);
      S.sodaKegs.splice(ti, 0, moved);
      saveKegOrder();
      renderKegs();
    });
  });
}

let _saveKegOrderTimer = null;
function saveKegOrder() {
  clearTimeout(_saveKegOrderTimer);
  _saveKegOrderTimer = setTimeout(async () => {
    try {
      await api('PUT', '/api/soda-kegs/reorder',
        S.sodaKegs.map((k, i) => ({ id: k.id, sort_order: i })));
    } catch(e) { toast(t('keg.err_save'), 'error'); }
  }, 600);
}

function goToBeerDetail(beerId) {
  navigate('cave');
  // S.beers déjà chargé sur la page kegs — ouvre le détail immédiatement
  setTimeout(() => openBeerDetail(beerId), 50);
}

function goToBrew(brewId) {
  navigate('brassins');
  // Attend le rendu puis scroll + highlight
  setTimeout(() => {
    const card = document.querySelector(`.brew-card[data-id="${brewId}"]`);
    if (!card) return;
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    card.classList.add('card-highlight');
    setTimeout(() => card.classList.remove('card-highlight'), 2000);
  }, 450);
}

function openKegPourModal(kegId) {
  const k = S.sodaKegs.find(k => k.id === kegId);
  if (!k) return;
  document.getElementById('keg-pour-id').value    = kegId;
  document.getElementById('keg-pour-title').textContent = k.name;
  document.getElementById('keg-pour-amount').value = '';
  document.getElementById('keg-pour-result').innerHTML  = '';
  document.getElementById('keg-pour-save-btn').disabled = false;
  const cur = k.current_liters ?? 0;
  const tot = k.volume_total   ?? '?';
  document.getElementById('keg-pour-current').innerHTML =
    `<i class="fas fa-jar" style="color:var(--amber);margin-right:6px"></i>${t('keg.pour_current').replace('${cur}', cur).replace('${tot}', tot)}`;
  openModal('keg-pour-modal');
}

function updateKegPourCalc() {
  const kegId  = parseInt(document.getElementById('keg-pour-id').value);
  const k      = S.sodaKegs.find(k => k.id === kegId);
  if (!k) return;
  const amount = parseFloat(document.getElementById('keg-pour-amount').value) || 0;
  const result = document.getElementById('keg-pour-result');
  const btn    = document.getElementById('keg-pour-save-btn');
  if (amount <= 0) { result.innerHTML = ''; btn.disabled = false; return; }
  const rem = Math.round(((k.current_liters ?? 0) - amount) * 10) / 10;
  if (rem < 0) {
    result.innerHTML = `<span style="color:var(--danger)"><i class="fas fa-triangle-exclamation"></i> ${t('keg.pour_negative_warn')}</span>`;
    btn.disabled = true;
  } else if (rem === 0) {
    result.innerHTML = `<span style="color:var(--amber)"><i class="fas fa-triangle-exclamation"></i> ${t('keg.pour_empty_warn')}</span>`;
    btn.disabled = false;
  } else {
    result.innerHTML = t('keg.pour_remaining').replace('${rem}', rem);
    btn.disabled = false;
  }
}

async function saveKegPour() {
  const kegId  = parseInt(document.getElementById('keg-pour-id').value);
  const k      = S.sodaKegs.find(k => k.id === kegId);
  if (!k) return;
  const amount = parseFloat(document.getElementById('keg-pour-amount').value);
  if (!amount || amount <= 0) return;
  const newLiters = Math.max(0, Math.round(((k.current_liters ?? 0) - amount) * 10) / 10);
  const payload = {
    name: k.name, keg_type: k.keg_type, volume_total: k.volume_total,
    volume_ferment: k.volume_ferment, weight_empty: k.weight_empty,
    status:        newLiters <= 0 ? 'empty' : k.status,
    current_liters: newLiters <= 0 ? 0 : newLiters,
    beer_id: newLiters <= 0 ? null : k.beer_id,
    brew_id: newLiters <= 0 ? null : k.brew_id,
    notes: k.notes, color: k.color, photo: k.photo,
  };
  try {
    const updated = await api('PUT', `/api/soda-kegs/${kegId}`, payload);
    const idx = S.sodaKegs.findIndex(k => k.id === kegId);
    if (idx !== -1) S.sodaKegs[idx] = updated;
    closeModal('keg-pour-modal');
    renderKegs();
    toast(t('keg.pour_saved'));
  } catch(e) { toast(t('keg.err_save'), 'error'); }
}

function openCaveKegModal(beerId) {
  const linked = S.sodaKegs.find(k => k.beer_id === beerId);
  document.getElementById('ck-beer-id').value     = beerId;
  document.getElementById('ck-prev-keg-id').value = linked ? linked.id : '';
  document.getElementById('ck-volume').value       = linked ? (linked.current_liters || '') : '';

  const sel = document.getElementById('ck-keg-id');
  sel.innerHTML = `<option value="">${t('cave.keg_select')}</option>` +
    S.sodaKegs
      .filter(k => !k.beer_id || k.beer_id === beerId)
      .map(k => `<option value="${k.id}"${linked && k.id === linked.id ? ' selected' : ''}>${esc(k.name)}</option>`)
      .join('');

  document.getElementById('ck-unlink-btn').style.display = linked ? '' : 'none';
  openModal('cave-keg-modal');
}

async function saveCaveKegAssoc() {
  const beerId = parseInt(document.getElementById('ck-beer-id').value);
  const kegId  = parseInt(document.getElementById('ck-keg-id').value) || null;
  const volume = parseFloat(document.getElementById('ck-volume').value) || null;
  const prevId = parseInt(document.getElementById('ck-prev-keg-id').value) || null;

  try {
    if (prevId && prevId !== kegId) {
      const prev = S.sodaKegs.find(k => k.id === prevId);
      if (prev) {
        const updated = await api('PUT', `/api/soda-kegs/${prevId}`, { ...prev, beer_id: null, status: 'empty', current_liters: 0 });
        const idx = S.sodaKegs.findIndex(k => k.id === prevId);
        if (idx !== -1) S.sodaKegs[idx] = updated;
      }
    }
    if (kegId) {
      const keg = S.sodaKegs.find(k => k.id === kegId);
      if (keg) {
        const updated = await api('PUT', `/api/soda-kegs/${kegId}`, { ...keg, beer_id: beerId, status: 'serving', current_liters: volume });
        const idx = S.sodaKegs.findIndex(k => k.id === kegId);
        if (idx !== -1) S.sodaKegs[idx] = updated;
      }
    }
    closeModal('cave-keg-modal');
    renderCave();
    toast(t('cave.keg_saved'), 'success');
  } catch(e) { toast(t('keg.err_save'), 'error'); }
}

async function unlinkCaveKeg() {
  const kegId = parseInt(document.getElementById('ck-prev-keg-id').value);
  if (!kegId) return;
  const keg = S.sodaKegs.find(k => k.id === kegId);
  if (!keg) return;
  try {
    const updated = await api('PUT', `/api/soda-kegs/${kegId}`, { ...keg, beer_id: null, status: 'empty', current_liters: 0 });
    const idx = S.sodaKegs.findIndex(k => k.id === kegId);
    if (idx !== -1) S.sodaKegs[idx] = updated;
    closeModal('cave-keg-modal');
    renderCave();
    toast(t('cave.keg_unlinked'), 'success');
  } catch(e) { toast(t('keg.err_save'), 'error'); }
}

function openBrewKegModal(brewId) {
  const brew = S.brews.find(b => b.id === brewId);
  const linked = S.sodaKegs.find(k => k.brew_id === brewId);
  document.getElementById('bk-brew-id').value    = brewId;
  document.getElementById('bk-prev-keg-id').value = linked ? linked.id : '';
  document.getElementById('bk-volume').value      = linked ? (linked.current_liters || '') : '';

  // Peupler le select avec les kegs disponibles (vides ou déjà liés à ce brassin)
  const sel = document.getElementById('bk-keg-id');
  sel.innerHTML = `<option value="">${t('brew.keg_select')}</option>` +
    S.sodaKegs
      .filter(k => !k.brew_id || k.brew_id === brewId)
      .map(k => `<option value="${k.id}"${linked && k.id === linked.id ? ' selected' : ''}>${esc(k.name)}</option>`)
      .join('');

  // Bouton dissocier visible seulement si un keg est déjà lié
  document.getElementById('bk-unlink-btn').style.display = linked ? '' : 'none';
  openModal('brew-keg-modal');
}

async function saveBrewKegAssoc() {
  const brewId  = parseInt(document.getElementById('bk-brew-id').value);
  const kegId   = parseInt(document.getElementById('bk-keg-id').value) || null;
  const volume  = parseFloat(document.getElementById('bk-volume').value) || null;
  const prevId  = parseInt(document.getElementById('bk-prev-keg-id').value) || null;

  try {
    // Dissocier l'ancien keg si différent
    if (prevId && prevId !== kegId) {
      const prev = S.sodaKegs.find(k => k.id === prevId);
      if (prev) {
        const updated = await api('PUT', `/api/soda-kegs/${prevId}`, { ...prev, brew_id: null, status: 'empty', current_liters: 0 });
        const idx = S.sodaKegs.findIndex(k => k.id === prevId);
        if (idx !== -1) S.sodaKegs[idx] = updated;
      }
    }
    // Associer le nouveau keg
    if (kegId) {
      const keg = S.sodaKegs.find(k => k.id === kegId);
      if (keg) {
        const updated = await api('PUT', `/api/soda-kegs/${kegId}`, { ...keg, brew_id: brewId, status: 'fermenting', current_liters: volume });
        const idx = S.sodaKegs.findIndex(k => k.id === kegId);
        if (idx !== -1) S.sodaKegs[idx] = updated;
      }
    }
    closeModal('brew-keg-modal');
    renderBrassins();
    toast(t('brew.keg_saved'), 'success');
  } catch(e) { toast(t('keg.err_save'), 'error'); }
}

async function unlinkBrewKeg() {
  const kegId = parseInt(document.getElementById('bk-prev-keg-id').value);
  if (!kegId) return;
  const keg = S.sodaKegs.find(k => k.id === kegId);
  if (!keg) return;
  try {
    const updated = await api('PUT', `/api/soda-kegs/${kegId}`, { ...keg, brew_id: null, status: 'empty', current_liters: 0 });
    const idx = S.sodaKegs.findIndex(k => k.id === kegId);
    if (idx !== -1) S.sodaKegs[idx] = updated;
    closeModal('brew-keg-modal');
    renderBrassins();
    toast(t('brew.keg_unlinked'), 'success');
  } catch(e) { toast(t('keg.err_save'), 'error'); }
}

function openKegModal(id) {
  const keg = id ? S.sodaKegs.find(k => k.id === id) : null;
  document.getElementById('keg-modal-title').textContent = keg ? t('keg.edit') : t('keg.add');
  document.getElementById('keg-f-id').value       = keg ? keg.id : '';
  document.getElementById('keg-f-name').value     = keg ? (keg.name || '') : '';
  const knownTypes = ['corny19', 'corny6', 'other'];
  const rawType = keg ? (keg.keg_type || 'corny19') : 'corny19';
  const isKnown = knownTypes.includes(rawType);
  document.getElementById('keg-f-type').value = isKnown ? rawType : 'other';
  document.getElementById('keg-f-type-other').value = isKnown ? '' : (rawType || '');
  toggleKegTypeOther();
  document.getElementById('keg-f-volume').value   = keg ? (keg.volume_total || '') : '';
  document.getElementById('keg-f-ferment').value  = keg ? (keg.volume_ferment || '') : '';
  document.getElementById('keg-f-weight').value   = keg ? (keg.weight_empty || '') : '';
  document.getElementById('keg-f-color').value        = keg ? (keg.color || '#f59e0b') : '#f59e0b';
  document.getElementById('keg-f-notes').value        = keg ? (keg.notes || '') : '';
  document.getElementById('keg-f-manufacturer').value          = keg ? (keg.manufacturer || '') : '';
  document.getElementById('keg-f-last-revision').value         = keg ? (keg.last_revision_date || '') : '';
  document.getElementById('keg-f-revision-interval').value     = keg ? (keg.revision_interval_months || 12) : 12;
  updateKegRevisionPreview();
  hideKegManufacturer();
  document.getElementById('keg-f-photo-b64').value = '';
  const prev = document.getElementById('keg-f-photo-preview');
  const rem  = document.getElementById('keg-f-photo-remove');
  if (keg && keg.photo) {
    prev.src = keg.photo; prev.style.display = 'block'; rem.style.display = 'block';
  } else {
    prev.style.display = 'none'; rem.style.display = 'none';
  }
  document.getElementById('keg-f-photo').value = '';
  openModal('keg-modal');
}

function openKegDetail(id) {
  const k = S.sodaKegs.find(x => x.id === id);
  if (!k) return;

  const get = elId => document.getElementById(elId);
  const color = k.color || '#f59e0b';
  const statusColors = { empty: 'var(--muted)', fermenting: 'var(--amber)', serving: 'var(--success)', cleaning: 'var(--info)' };
  const statusLabels = { empty: t('keg.status_empty'), fermenting: t('keg.status_fermenting'), serving: t('keg.status_serving'), cleaning: t('keg.status_cleaning') };
  const typeLabels   = { corny19: t('keg.type_corny19'), corny6: t('keg.type_corny6') };

  // Titre + icône
  const iconHtml = k.keg_type === 'corny6'
    ? `<i class="fas fa-flask" style="color:${color}"></i>`
    : `<i class="fas fa-jar" style="color:${color}"></i>`;
  get('kd-title-icon').innerHTML = iconHtml;
  get('kd-title-text').textContent = k.name;

  // Photo ou placeholder
  if (k.photo) {
    get('kd-photo').src = k.photo;
    get('kd-photo').alt = k.name;
    get('kd-photo-wrap').style.display = '';
    get('kd-no-photo').style.display   = 'none';
  } else {
    get('kd-photo-wrap').style.display = 'none';
    get('kd-no-photo').style.display   = '';
    get('kd-icon-placeholder').innerHTML = k.keg_type === 'corny6'
      ? `<i class="fas fa-flask" style="color:${color}"></i>`
      : `<i class="fas fa-jar" style="color:${color}"></i>`;
  }

  // Badges
  const sColor = statusColors[k.status] || 'var(--muted)';
  const sLabel = statusLabels[k.status] || k.status;
  const tLabel = typeLabels[k.keg_type] || (k.keg_type && k.keg_type !== 'other' ? k.keg_type : '');
  const badges = [];
  badges.push(`<span class="badge" style="background:${sColor};color:#fff">${sLabel}</span>`);
  if (tLabel) badges.push(`<span class="badge" style="background:var(--card2);color:var(--muted)">${esc(tLabel)}</span>`);
  if (k.manufacturer) badges.push(`<span class="badge" style="background:var(--card2);color:var(--muted)"><i class="fas fa-industry"></i> ${esc(k.manufacturer)}</span>`);
  get('kd-badges').innerHTML = badges.join('');

  // Barre de volume
  let volHtml = '';
  if (k.volume_total && k.current_liters != null) {
    const pct      = Math.min(100, Math.round((k.current_liters / k.volume_total) * 100));
    const barColor = pct > 50 ? 'var(--success)' : pct > 20 ? 'var(--amber)' : 'var(--danger)';
    volHtml = `
      <div style="padding:12px;background:rgba(245,158,11,.07);border:1px solid rgba(245,158,11,.2);border-radius:10px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
          <i class="fas fa-jar" style="color:${color}"></i>
          <span style="font-weight:700;font-size:1.05rem">${k.current_liters} L</span>
          <span style="color:var(--muted);font-size:.85rem">/ ${k.volume_total} L</span>
          <span style="color:var(--muted);font-size:.8rem;margin-left:auto">${pct}%</span>
        </div>
        <div class="bottle-bar" style="width:100%"><div class="bottle-bar-fill" style="width:${pct}%;background:${barColor}"></div></div>
      </div>`;
  }
  get('kd-volume').innerHTML = volHtml;

  // Specs
  const specs = [];
  if (k.volume_total)   specs.push({ icon:'fa-jar',            label:t('keg.field_volume'),  val:`${k.volume_total} L` });
  if (k.volume_ferment) specs.push({ icon:'fa-temperature-arrow-up', label:t('keg.field_ferment'), val:`${k.volume_ferment} L` });
  if (k.weight_empty)   specs.push({ icon:'fa-weight-scale',   label:t('keg.field_weight'),  val:`${k.weight_empty} kg` });
  get('kd-specs').style.display = specs.length ? '' : 'none';
  get('kd-specs').innerHTML = specs.map(s =>
    `<div style="background:var(--card2);border-radius:9px;padding:10px;text-align:center">
       <div style="font-size:.72rem;color:var(--muted);margin-bottom:4px"><i class="fas ${s.icon}"></i> ${s.label}</div>
       <div style="font-weight:700;font-size:.95rem">${s.val}</div>
     </div>`).join('');

  // Association bière / brassin
  let assocHtml = '';
  if (k.status === 'fermenting' && k.brew_name) {
    assocHtml = `<div style="font-size:.85rem;padding:8px 12px;background:rgba(245,158,11,.07);border-radius:8px">
      <i class="fas fa-fire-burner" style="color:var(--amber)"></i>
      <a href="#" onclick="event.preventDefault();closeModal('keg-detail-modal');goToBrew(${k.brew_id})" style="color:var(--amber);margin-left:5px">${esc(k.brew_name)}</a>
    </div>`;
  } else if (k.status === 'serving' && k.beer_name) {
    assocHtml = `<div style="font-size:.85rem;padding:8px 12px;background:rgba(34,197,94,.07);border-radius:8px">
      <i class="fas fa-beer-mug-empty" style="color:var(--success)"></i>
      <a href="#" onclick="event.preventDefault();closeModal('keg-detail-modal');goToBeerDetail(${k.beer_id})" style="color:var(--success);margin-left:5px">${esc(k.beer_name)}</a>
    </div>`;
  }
  get('kd-assoc').innerHTML = assocHtml;

  // Révision
  let revHtml = '';
  if (k.next_revision_date) {
    const rev   = new Date(k.next_revision_date);
    const today = new Date(); today.setHours(0,0,0,0);
    const days  = Math.round((rev - today) / 86400000);
    const fmtDate = d => d.split('-').reverse().join('/');
    if (days < 0) {
      revHtml = `<div style="font-size:.83rem;color:var(--danger);padding:7px 12px;background:rgba(239,68,68,.08);border-radius:8px"><i class="fas fa-triangle-exclamation"></i> ${t('keg.revision_overdue')} — ${fmtDate(k.next_revision_date)}</div>`;
    } else if (days <= 30) {
      revHtml = `<div style="font-size:.83rem;color:var(--amber);padding:7px 12px;background:rgba(245,158,11,.08);border-radius:8px"><i class="fas fa-clock"></i> ${t('keg.revision_soon').replace('${days}', days)} — ${fmtDate(k.next_revision_date)}</div>`;
    } else {
      revHtml = `<div style="font-size:.83rem;color:var(--muted);padding:7px 12px;background:var(--card2);border-radius:8px"><i class="fas fa-calendar-check"></i> ${t('keg.next_revision_label')} ${fmtDate(k.next_revision_date)}</div>`;
    }
  }
  get('kd-revision').innerHTML = revHtml;

  // Notes
  const notesEl = get('kd-notes');
  notesEl.textContent  = k.notes || '';
  notesEl.style.display = k.notes ? '' : 'none';

  // Boutons footer
  const pourBtn   = get('kd-pour-btn');
  const statusBtn = get('kd-status-btn');
  const editBtn   = get('kd-edit-btn');
  pourBtn.style.display = k.status === 'serving' ? '' : 'none';
  pourBtn.onclick   = () => { closeModal('keg-detail-modal'); openKegPourModal(id); };
  statusBtn.onclick = () => { closeModal('keg-detail-modal'); openKegStatusModal(id); };
  editBtn.onclick   = () => { closeModal('keg-detail-modal'); openKegModal(id); };

  openModal('keg-detail-modal');
}

function _calcNextRevDate(lastDate, intervalMonths) {
  if (!lastDate || !intervalMonths) return null;
  const d = new Date(lastDate);
  d.setMonth(d.getMonth() + parseInt(intervalMonths));
  return d.toISOString().split('T')[0];
}

function setKegInterval(months) {
  document.getElementById('keg-f-revision-interval').value = months;
  updateKegRevisionPreview();
}

function updateKegRevisionPreview() {
  const last     = document.getElementById('keg-f-last-revision').value;
  const interval = document.getElementById('keg-f-revision-interval').value;
  const preview  = document.getElementById('keg-f-next-revision-preview');
  if (!preview) return;
  const next = _calcNextRevDate(last, interval);
  if (!next) { preview.style.display = 'none'; return; }
  const fmtDate = d => d.split('-').reverse().join('/');
  const today = new Date(); today.setHours(0,0,0,0);
  const days  = Math.round((new Date(next) - today) / 86400000);
  let color = 'var(--success)'; let icon = 'fa-calendar-check';
  if (days < 0)       { color = 'var(--danger)'; icon = 'fa-triangle-exclamation'; }
  else if (days <= 30){ color = 'var(--amber)';  icon = 'fa-clock'; }
  preview.innerHTML = `<i class="fas ${icon}" style="color:${color}"></i> <span style="color:${color}">${t('keg.next_revision_label')}</span> <strong>${fmtDate(next)}</strong>`;
  preview.style.display = '';
}

function toggleKegTypeOther() {
  const isOther = document.getElementById('keg-f-type').value === 'other';
  document.getElementById('keg-f-type-other').style.display = isOther ? '' : 'none';
  if (isOther) document.getElementById('keg-f-type-other').focus();
}

function suggestFermentVolume() {
  const vol = parseFloat(document.getElementById('keg-f-volume').value);
  const ferment = document.getElementById('keg-f-ferment');
  if (vol && !ferment.value) ferment.value = Math.round(vol * 0.8 * 10) / 10;
}

function _kegTypePreset() {
  const type = document.getElementById('keg-f-type').value;
  const volEl = document.getElementById('keg-f-volume');
  const ferEl = document.getElementById('keg-f-ferment');
  const preset = { corny19: 19, corny6: 6 };
  if (preset[type] && !volEl.value) {
    volEl.value = preset[type];
    if (!ferEl.value) ferEl.value = Math.round(preset[type] * 0.8 * 10) / 10;
  }
}

async function saveKeg() {
  const name = document.getElementById('keg-f-name').value.trim();
  if (!name) { toast(t('keg.err_name'), 'error'); return; }
  const id = document.getElementById('keg-f-id').value;
  const b64 = document.getElementById('keg-f-photo-b64').value;
  const existing = id ? (S.sodaKegs.find(k => k.id == id) || {}) : {};
  const payload = {
    name,
    keg_type:      (() => { const v = document.getElementById('keg-f-type').value; return v === 'other' ? (document.getElementById('keg-f-type-other').value.trim() || 'other') : v; })(),
    manufacturer:  document.getElementById('keg-f-manufacturer').value.trim() || null,
    volume_total:  parseFloat(document.getElementById('keg-f-volume').value) || null,
    volume_ferment:parseFloat(document.getElementById('keg-f-ferment').value) || null,
    weight_empty:  parseFloat(document.getElementById('keg-f-weight').value) || null,
    color:                     document.getElementById('keg-f-color').value,
    notes:                     document.getElementById('keg-f-notes').value.trim() || null,
    last_revision_date:        document.getElementById('keg-f-last-revision').value || null,
    revision_interval_months:  parseInt(document.getElementById('keg-f-revision-interval').value) || 12,
    next_revision_date:        _calcNextRevDate(
                                 document.getElementById('keg-f-last-revision').value,
                                 document.getElementById('keg-f-revision-interval').value
                               ),
    photo:                     b64 || (id ? existing.photo : null),
    // Préserver le statut et les associations lors d'une modification
    status:         existing.status        || 'empty',
    current_liters: existing.current_liters ?? null,
    beer_id:        existing.beer_id       ?? null,
    brew_id:        existing.brew_id       ?? null,
  };
  try {
    if (id) {
      const updated = await api('PUT', `/api/soda-kegs/${id}`, payload);
      const idx = S.sodaKegs.findIndex(k => k.id == id);
      if (idx !== -1) S.sodaKegs[idx] = updated;
      toast(t('keg.updated'), 'success');
    } else {
      const created = await api('POST', '/api/soda-kegs', payload);
      S.sodaKegs.push(created);
      toast(t('keg.added'), 'success');
    }
    closeModal('keg-modal');
    renderKegs();
    const stats = await api('GET', '/api/stats');
    updateNavBadges(stats);
  } catch(e) { toast(t('keg.err_save'), 'error'); }
}

async function deleteKeg(id) {
  const keg = S.sodaKegs.find(k => k.id === id);
  if (!await confirmModal(`${t('common.delete')} "${keg ? keg.name : '?'}" ?`, { danger: true })) return;
  try {
    await api('DELETE', `/api/soda-kegs/${id}`);
    S.sodaKegs = S.sodaKegs.filter(k => k.id !== id);
    renderKegs();
    const stats = await api('GET', '/api/stats');
    updateNavBadges(stats);
    toast(t('keg.deleted'), 'success');
  } catch(e) { toast(t('common.err_delete') || 'Erreur', 'error'); }
}

function openKegStatusModal(id) {
  const keg = S.sodaKegs.find(k => k.id === id);
  if (!keg) return;
  document.getElementById('keg-s-id').value = id;
  document.getElementById('keg-status-modal-title').textContent = keg.name;
  document.getElementById('keg-s-status').value = keg.status || 'empty';

  // Populate brew select
  const brewSel = document.getElementById('keg-s-brew-id');
  brewSel.innerHTML = `<option value="">${t('keg.none')}</option>` +
    S.brews.map(b => `<option value="${b.id}"${keg.brew_id == b.id ? ' selected' : ''}>${esc(b.name)}</option>`).join('');

  // Populate beer select
  const beerSel = document.getElementById('keg-s-beer-id');
  beerSel.innerHTML = `<option value="">${t('keg.none')}</option>` +
    S.beers.map(b => `<option value="${b.id}"${keg.beer_id == b.id ? ' selected' : ''}>${esc(b.name)}</option>`).join('');

  // Set current volumes
  document.getElementById('keg-s-current-brew').value  = keg.current_liters || '';
  document.getElementById('keg-s-current-beer').value  = keg.current_liters || '';
  document.getElementById('keg-s-current-other').value = keg.current_liters || '';

  updateKegStatusFields();
  openModal('keg-status-modal');
}

function updateKegStatusFields() {
  const status = document.getElementById('keg-s-status').value;
  document.getElementById('keg-s-brew-wrap').style.display  = status === 'fermenting' ? '' : 'none';
  document.getElementById('keg-s-beer-wrap').style.display  = status === 'serving'    ? '' : 'none';
  document.getElementById('keg-s-current-wrap').style.display = (status === 'cleaning') ? '' : 'none';
}

async function saveKegStatus() {
  const id     = document.getElementById('keg-s-id').value;
  const status = document.getElementById('keg-s-status').value;
  let current_liters = null, beer_id = null, brew_id = null;
  if (status === 'fermenting') {
    brew_id = parseInt(document.getElementById('keg-s-brew-id').value) || null;
    current_liters = parseFloat(document.getElementById('keg-s-current-brew').value) || null;
  } else if (status === 'serving') {
    beer_id = parseInt(document.getElementById('keg-s-beer-id').value) || null;
    current_liters = parseFloat(document.getElementById('keg-s-current-beer').value) || null;
  } else if (status === 'cleaning') {
    current_liters = parseFloat(document.getElementById('keg-s-current-other').value) || null;
  } else {
    current_liters = 0;
  }
  const keg = S.sodaKegs.find(k => k.id == id);
  if (!keg) return;
  const payload = { ...keg, status, current_liters, beer_id, brew_id };
  try {
    const updated = await api('PUT', `/api/soda-kegs/${id}`, payload);
    const idx = S.sodaKegs.findIndex(k => k.id == id);
    if (idx !== -1) S.sodaKegs[idx] = updated;
    closeModal('keg-status-modal');
    renderKegs();
    toast(t('keg.status_updated'), 'success');
  } catch(e) { toast(t('keg.err_save'), 'error'); }
}

function previewKegPhoto(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    document.getElementById('keg-f-photo-preview').src = e.target.result;
    document.getElementById('keg-f-photo-preview').style.display = 'block';
    document.getElementById('keg-f-photo-remove').style.display  = 'block';
    document.getElementById('keg-f-photo-b64').value = e.target.result;
  };
  reader.readAsDataURL(file);
}

function removeKegPhoto() {
  document.getElementById('keg-f-photo-preview').style.display = 'none';
  document.getElementById('keg-f-photo-remove').style.display  = 'none';
  document.getElementById('keg-f-photo-b64').value = '';
  document.getElementById('keg-f-photo').value = '';
  // Mark photo as removed for existing keg
  const id = document.getElementById('keg-f-id').value;
  if (id) {
    const keg = S.sodaKegs.find(k => k.id == id);
    if (keg) keg._photoRemoved = true;
  }
}

const _KEG_MANUFACTURERS = [
  'Cornelius','Firestone','AEB Group','KegLand','Keg King',
  'SS Brewtech','Spike Brewing','Blichmann Engineering','Torpedo Kegs','Fermtech',
];
function filterKegManufacturer() {
  const input = document.getElementById('keg-f-manufacturer');
  const box   = document.getElementById('keg-manufacturer-suggest');
  const q     = input.value.trim().toLowerCase();
  const items = q ? _KEG_MANUFACTURERS.filter(m => m.toLowerCase().includes(q)) : _KEG_MANUFACTURERS;
  if (!items.length) { box.classList.remove('open'); return; }
  box.innerHTML = items.map(m =>
    `<div class="ing-suggest-item" onmousedown="selectKegManufacturer('${m.replace(/'/g,"\\'")}')"><span>${esc(m)}</span></div>`
  ).join('');
  box.classList.add('open');
}
function selectKegManufacturer(name) {
  document.getElementById('keg-f-manufacturer').value = name;
  hideKegManufacturer();
}
function hideKegManufacturer() {
  document.getElementById('keg-manufacturer-suggest').classList.remove('open');
}

function renderSpindles() {
  const grid  = document.getElementById('spindle-grid');
  const empty = document.getElementById('spindle-empty');
  const statsEl = document.getElementById('spin-stats');
  const nb = document.getElementById('nb-spin');
  if (nb) nb.textContent = S.spindles.length + S.tempSensors.length;

  const linked     = S.spindles.filter(s => s.brew_id).length;
  const total      = S.spindles.reduce((a, s) => a + (s.reading_count || 0), 0);
  const tempLinked = S.tempSensors.filter(s => s.brew_id).length;
  const tempTotal  = S.tempSensors.reduce((a, s) => a + (s.reading_count || 0), 0);
  const spindleStatsEl = document.getElementById('spin-stats-spindles');
  if (spindleStatsEl) spindleStatsEl.innerHTML = `
    <div class="stat"><div class="stat-val" style="color:var(--info)">${S.spindles.length}</div><div class="stat-lbl">${t('spin.stat_hydrometers')}</div></div>
    <div class="stat"><div class="stat-val">${linked}</div><div class="stat-lbl">${t('spin.stat_linked')}</div></div>
    <div class="stat"><div class="stat-val">${total}</div><div class="stat-lbl">${t('spin.stat_readings')}</div></div>`;
  statsEl.innerHTML = `
    <div class="stat"><div class="stat-val" style="color:#ef4444">${S.tempSensors.length}</div><div class="stat-lbl">${t('spin.stat_temp_probes')}</div></div>
    <div class="stat"><div class="stat-val">${tempLinked}</div><div class="stat-lbl">${t('spin.stat_temp_linked')}</div></div>
    <div class="stat"><div class="stat-val">${tempTotal}</div><div class="stat-lbl">${t('spin.stat_readings')}</div></div>`;

  if (!S.spindles.length) {
    grid.innerHTML = '';
    empty.style.display = '';
    return;
  }
  empty.style.display = 'none';

  grid.innerHTML = S.spindles.map(s => {
    const batV   = s.last_battery;
    const batPct = batV != null ? Math.min(100, Math.max(0, Math.round((batV - 3.0) / (4.2 - 3.0) * 100))) : null;
    const batColor = batPct == null ? 'var(--muted)' : batPct > 50 ? 'var(--success)' : batPct > 20 ? '#f59e0b' : 'var(--danger)';
    const lastAt = fmtReadingDate(s.last_reading_at);
    const gravStr = s.last_gravity    != null ? s.last_gravity.toFixed(3)    : '—';
    const tempStr = s.last_temperature != null ? s.last_temperature.toFixed(1) + '°' : '—';
    const batStr  = batV != null ? batV.toFixed(2) + 'V' : '—';
    const batBar  = batPct != null
      ? `<div class="battery-bar"><div class="battery-fill" style="width:${batPct}%;background:${batColor}"></div></div>`
      : '';

    const age = spindleAge(s.last_reading_at);
    const otherLinkedIds = new Set(S.spindles.filter(sp => sp.brew_id && sp.id !== s.id).map(sp => sp.brew_id));
    const activeBrews = S.brews.filter(b => !b.archived && b.status !== 'completed' && !otherLinkedIds.has(b.id));
    return `
      <div class="spindle-card" data-id="${s.id}" draggable="true" style="border-color:${age.color}44">
        <div class="spindle-card-head">
          <div style="display:flex;align-items:center;gap:4px;min-width:0">
            <span class="spin-drag-handle" title="${t('spin.drag_to_reorder')}"><i class="fas fa-grip-vertical"></i></span>
            <div class="spindle-name">
              <i class="fas fa-water" style="color:var(--info);margin-right:7px"></i>${esc(s.name)}
              ${(() => { const di = DEVICE_INFO[s.device_type] || DEVICE_INFO.generic; return `<span style="font-size:.68rem;margin-left:7px;padding:1px 7px;border-radius:10px;background:${di.color}22;color:${di.color};font-weight:700;vertical-align:middle">${di.label}</span>`; })()}
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:6px">
            <span class="spindle-age-badge${age.fresh ? ' spindle-age-pulse' : ''}" style="color:${age.color};background:${age.color}1a;border-color:${age.color}55" title="${t('spin.last_received')} : ${lastAt}">
              <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${age.color};flex-shrink:0"></span>
              ${age.label}
            </span>
            <button class="btn btn-ghost btn-sm btn-icon" onclick="showSpindleToken(${s.id})" title="${t('spin.token_config')}"><i class="fas fa-key"></i></button>
            <button class="btn btn-ghost btn-sm btn-icon" onclick="openSpindleChart(${s.id})" title="${t('spin.chart_gravity_label')}"><i class="fas fa-chart-line"></i></button>
            <button class="btn btn-ghost btn-sm btn-icon" onclick="openSpindleEditModal(${s.id})" title="${t('common.edit')}"><i class="fas fa-pen"></i></button>
            <button class="btn btn-danger btn-sm btn-icon" onclick="deleteSpindle(${s.id})" title="${t('common.delete')}"><i class="fas fa-trash"></i></button>
          </div>
        </div>
        <div class="spindle-metrics">
          <div class="spindle-metric">
            <div class="spindle-metric-val" title="${s.last_gravity != null ? t('spin.last_received') + ' : ' + lastAt : ''}">${gravStr}</div>
            <div class="spindle-metric-lbl">${t('spin.metric_gravity')}</div>
          </div>
          <div class="spindle-metric">
            <div class="spindle-metric-val" title="${s.last_temperature != null ? t('spin.last_received') + ' : ' + lastAt : ''}">${tempStr}</div>
            <div class="spindle-metric-lbl">${t('spin.metric_temp')}</div>
          </div>
          <div class="spindle-metric">
            <div class="spindle-metric-val" style="font-size:1rem" title="${batV != null ? t('spin.last_received') + ' : ' + lastAt : ''}">${batBar}${batStr}</div>
            <div class="spindle-metric-lbl">${t('spin.metric_battery')}</div>
          </div>
        </div>
        <div class="spindle-brew-link">
          <i class="fas fa-link" style="color:var(--info);flex-shrink:0"></i>
          <select style="flex:1;border:none;background:transparent;color:var(--text);font-family:inherit;font-size:.85rem;cursor:pointer"
                  onchange="linkSpindleBrew(${s.id}, this.value)">
            <option value="">${t('spin.not_linked_brew')}</option>
            ${activeBrews.map(b => `<option value="${b.id}" ${s.brew_id == b.id ? 'selected' : ''}>${esc(b.name)}</option>`).join('')}
          </select>
        </div>
        <div style="font-size:.78rem;color:var(--muted)">
          <i class="fas fa-clock"></i> ${t('spin.last_seen')} : ${lastAt}
          &nbsp;·&nbsp;<i class="fas fa-database"></i> ${s.reading_count || 0} ${(s.reading_count || 0) !== 1 ? t('spin.readings') : t('spin.reading')}
        </div>
      </div>`;
  }).join('');

  // ── Drag & drop reorder ──
  let dragSrcIdx = null;
  grid.querySelectorAll('.spindle-card').forEach((card, idx) => {
    card.addEventListener('dragstart', e => {
      dragSrcIdx = idx;
      card.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    });
    card.addEventListener('dragend', () => {
      card.classList.remove('dragging');
      grid.querySelectorAll('.spindle-card').forEach(c => c.classList.remove('drag-over'));
    });
    card.addEventListener('dragover', e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      grid.querySelectorAll('.spindle-card').forEach(c => c.classList.remove('drag-over'));
      if (dragSrcIdx !== idx) card.classList.add('drag-over');
    });
    card.addEventListener('dragleave', () => card.classList.remove('drag-over'));
    card.addEventListener('drop', e => {
      e.preventDefault();
      if (dragSrcIdx === null || dragSrcIdx === idx) return;
      const [moved] = S.spindles.splice(dragSrcIdx, 1);
      S.spindles.splice(idx, 0, moved);
      dragSrcIdx = null;
      saveSpindleOrder();
      renderSpindles();
    });
  });

  loadSpindleStats();
}

let _saveSpindleOrderTimer = null;
function saveSpindleOrder() {
  clearTimeout(_saveSpindleOrderTimer);
  _saveSpindleOrderTimer = setTimeout(async () => {
    try {
      await api('PUT', '/api/spindles/reorder',
        S.spindles.map((s, i) => ({ id: s.id, sort_order: i })));
    } catch(e) { toast(t('spin.err_save_order'), 'error'); }
  }, 600);
}

// ── Détection fin de fermentation (stabilité densité) ─────────────────────────
function _detectFermStability(readings, stabilityDays = 3, threshold = 0.003) {
  if (!readings || readings.length < 3) return null;
  const cutoff = Date.now() - stabilityDays * 86400000;
  const recent = readings.filter(r => r.gravity != null && new Date(r.recorded_at).getTime() >= cutoff);
  if (recent.length < 2) return null;
  const gravs  = recent.map(r => r.gravity);
  const range  = Math.max(...gravs) - Math.min(...gravs);
  const avg    = gravs.reduce((a,b) => a+b, 0) / gravs.length;
  // Find when the stable plateau started (walk back from last reading)
  let stableFrom = null;
  for (let i = readings.length - 1; i >= 0; i--) {
    const window = readings.slice(i).filter(r => r.gravity != null).map(r => r.gravity);
    if (window.length < 2) break;
    if (Math.max(...window) - Math.min(...window) <= threshold) {
      stableFrom = readings[i].recorded_at;
    } else break;
  }
  return { stable: range <= threshold, range, avg, readingsInWindow: recent.length, stableFrom };
}

async function openBrewFermentationChart(brewId) {
  const brew = S.brews.find(b => b.id === brewId);
  document.getElementById('spindle-chart-title').textContent =
    `Fermentation — ${brew ? esc(brew.name) : ''}`;
  document.getElementById('spindle-chart-range').style.display = 'none';
  openModal('spindle-chart-modal');

  if (_spindleChart) { _spindleChart.destroy(); _spindleChart = null; }
  const stale = Chart.getChart('spindle-chart-canvas');
  if (stale) stale.destroy();
  document.getElementById('spindle-chart-table').innerHTML =
    `<p style="text-align:center;color:var(--muted);padding:20px 0"><i class="fas fa-spinner fa-spin"></i> ${t('common.loading')}</p>`;

  try {
    const readings = await api('GET', `/api/brews/${brewId}/fermentation`);

    if (!readings.length) {
      document.getElementById('spindle-chart-table').innerHTML =
        `<p style="text-align:center;color:var(--muted);padding:30px 0">${t('brew.no_ferm_readings')}</p>`;
      return;
    }

    const labels    = readings.map(r => fmtReadingDate(r.recorded_at));
    const gravities = readings.map(r => r.gravity);
    const temps     = readings.map(r => r.temperature);
    const ptRadius  = readings.length > 60 ? 0 : 3;

    // Courbe cible de température (depuis ferm_profile ou ferm_temp flat)
    let targetTempData = null;
    if (brew && brew.recipe_id) {
      let recipe = S.recipes.find(r => r.id === brew.recipe_id);
      if (!recipe) {
        try { recipe = await api('GET', `/api/recipes/${brew.recipe_id}`); } catch(e) {}
      }
      if (recipe) {
        const profile = recipe.ferm_profile ? JSON.parse(recipe.ferm_profile) : null;
        const firstTs = new Date(readings[0].recorded_at).getTime();
        const arr = readings.map(r => {
          const dayOffset = (new Date(r.recorded_at).getTime() - firstTs) / 86400000;
          if (profile && profile.length) {
            let temp = profile[0].temp;
            for (const step of profile) {
              if (step.day <= dayOffset) temp = step.temp;
              else break;
            }
            return temp;
          } else if (recipe.ferm_temp && recipe.ferm_time != null) {
            return dayOffset <= recipe.ferm_time ? recipe.ferm_temp : null;
          }
          return null;
        });
        if (arr.some(v => v !== null)) targetTempData = arr;
      }
    }

    // Détection stabilité
    const stability = _detectFermStability(readings);

    // OG = max des mesures de la fenêtre affichée (delta ABV cohérent avec le graphique visible)
    const og = Math.max(...gravities.filter(g => g != null));
    const abvChartLabel = t('brew.abv_chart_label').replace('${og}', og.toFixed(3));
    const abvData = gravities.map(g => g != null ? parseFloat(((og - g) * 131.25).toFixed(2)) : null);
    const abvFinal = abvData[abvData.length - 1];

    // Ligne de stabilité (densité plateau)
    const stableLineDataset = stability?.stable ? [{
      label: `${t('spin.ferm_stable')} (${stability.avg.toFixed(3)})`,
      data: Array(labels.length).fill(stability.avg),
      borderColor: '#22c55e', borderWidth: 1.5, borderDash: [6,4],
      backgroundColor: 'transparent', pointRadius: 0, yAxisID: 'yGrav', fill: false,
    }] : [];

    const canvas = document.getElementById('spindle-chart-canvas');
    canvas.style.width  = '100%';
    canvas.style.height = '100%';
    _spindleChart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: t('spin.metric_gravity'), data: gravities, borderColor: '#ff9500',
            backgroundColor: 'rgba(255,149,0,.12)', yAxisID: 'yGrav',
            tension: 0.35, pointRadius: ptRadius, fill: true },
          { label: abvChartLabel, data: abvData, borderColor: '#22c55e',
            backgroundColor: 'rgba(34,197,94,.08)', yAxisID: 'yAbv',
            tension: 0.35, pointRadius: ptRadius, fill: false },
          { label: `${t('spin.metric_temp')} (°C)`, data: temps, borderColor: '#3b82f6',
            backgroundColor: 'rgba(59,130,246,.08)', yAxisID: 'yTemp',
            tension: 0.35, pointRadius: ptRadius, fill: false },
          ...(targetTempData ? [{
            label: t('brew.target_temp_curve'),
            data: targetTempData, borderColor: '#f59e0b',
            backgroundColor: 'transparent', yAxisID: 'yTemp',
            tension: 0, pointRadius: 0, fill: false,
            borderWidth: 1.5, borderDash: [6, 3],
          }] : []),
          ...stableLineDataset,
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { labels: { color: '#ccc', font: { size: 12 },
            filter: item => item.datasetIndex < (3 + (targetTempData ? 1 : 0)) } },
          tooltip: {
            callbacks: {
              label: ctx => {
                const v = ctx.parsed.y;
                if (ctx.dataset.yAxisID === 'yAbv')                              return ` ${t('spin.abv_est')} : ${v != null ? v.toFixed(2) + ' %' : '—'}`;
                if (ctx.dataset.label === t('spin.metric_gravity'))              return ` ${t('spin.metric_gravity')} : ${v != null ? v.toFixed(3) : '—'}`;
                if (ctx.dataset.label === `${t('spin.metric_temp')} (°C)`)      return ` ${t('spin.temp')} : ${v != null ? v.toFixed(1) + ' °C' : '—'}`;
                if (ctx.dataset.label === t('brew.target_temp_curve'))           return ` ${t('brew.target_temp_curve')} : ${v != null ? v.toFixed(1) + ' °C' : '—'}`;
                return ` ${ctx.dataset.label} : ${v}`;
              },
            },
          },
        },
        scales: {
          x: { ticks: { color: '#888', maxTicksLimit: 10, font: { size: 11 } }, grid: { color: '#2a2a2a' } },
          yGrav: { type: 'linear', position: 'left',
            ticks: { color: '#ff9500', font: { size: 11 } }, grid: { color: '#2a2a2a' },
            title: { display: true, text: t('spin.metric_gravity'), color: '#ff9500', font: { size: 11 } } },
          yAbv: { type: 'linear', position: 'right', min: 0,
            ticks: { color: '#22c55e', font: { size: 11 }, callback: v => v.toFixed(1) + '%' },
            grid: { drawOnChartArea: false },
            title: { display: true, text: 'ABV %', color: '#22c55e', font: { size: 11 } } },
          yTemp: { type: 'linear', position: 'right',
            display: temps.some(v => v != null) || !!targetTempData,
            ticks: { color: '#3b82f6', font: { size: 11 }, callback: v => v.toFixed(1) + '°' },
            grid: { drawOnChartArea: false },
            title: { display: true, text: '°C', color: '#3b82f6', font: { size: 11 } } },
        },
      },
    });

    const recent = readings.slice(-10).reverse();
    const abvLabel = abvFinal != null ? `${t('spin.abv_final_est')} <strong style="color:#22c55e">${abvFinal.toFixed(2)}%</strong>` : '';
    const stabilityBadge = stability?.stable
      ? `<span style="background:rgba(34,197,94,.15);border:1px solid #22c55e55;border-radius:20px;padding:2px 9px;font-size:.75rem;color:#22c55e;font-weight:700" title="${t('spin.ferm_stable_hint')}"><i class="fas fa-circle-check"></i> ${t('spin.ferm_stable')} · ${t('spin.ferm_stable_grav')} ${stability.avg.toFixed(3)}</span>`
      : `<span style="font-size:.75rem;color:var(--amber)"><i class="fas fa-flask"></i> ${t('spin.ferm_not_stable')}</span>`;
    document.getElementById('spindle-chart-table').innerHTML = `
      <div style="display:flex;gap:16px;align-items:center;margin-bottom:10px;flex-wrap:wrap">
        <h4 style="margin:0;font-size:.9rem;color:var(--muted)">${t('spin.chart_readings_archived').replace('${n}', readings.length)}</h4>
        <span style="font-size:.82rem;color:var(--muted)">OG ${og.toFixed(3)}</span>
        ${abvLabel ? `<span style="font-size:.82rem">${abvLabel}</span>` : ''}
        ${stability ? stabilityBadge : ''}
      </div>
      <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:.82rem">
        <thead><tr style="color:var(--muted);border-bottom:1px solid var(--border)">
          <th style="text-align:left;padding:5px 8px">${t('spin.col_date_time')}</th>
          <th style="text-align:center;padding:5px 8px">${t('spin.metric_gravity')}</th>
          <th style="text-align:center;padding:5px 8px">${t('spin.abv_est')}</th>
          <th style="text-align:center;padding:5px 8px">${t('spin.temp')} (°C)</th>
          <th style="text-align:center;padding:5px 8px">${t('spin.battery')}</th>
          <th style="text-align:center;padding:5px 8px">${t('spin.angle')}</th>
        </tr></thead>
        <tbody>
          ${recent.map(r => {
            const abv = r.gravity != null ? ((og - r.gravity) * 131.25).toFixed(2) : null;
            return `
            <tr style="border-bottom:1px solid rgba(255,255,255,.04)">
              <td style="padding:5px 8px;color:var(--muted)">${fmtReadingDate(r.recorded_at)}</td>
              <td style="text-align:center;padding:5px 8px;color:var(--amber);font-weight:600">${r.gravity != null ? r.gravity.toFixed(3) : '—'}</td>
              <td style="text-align:center;padding:5px 8px;color:#22c55e;font-weight:600">${abv != null ? abv + '%' : '—'}</td>
              <td style="text-align:center;padding:5px 8px;color:#3b82f6">${r.temperature != null ? r.temperature.toFixed(1) + '°' : '—'}</td>
              <td style="text-align:center;padding:5px 8px;color:var(--muted)">${r.battery != null ? r.battery.toFixed(2) + 'V' : '—'}</td>
              <td style="text-align:center;padding:5px 8px;color:var(--muted)">${r.angle != null ? r.angle.toFixed(1) + '°' : '—'}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;
  } catch(e) {
    document.getElementById('spindle-chart-table').innerHTML =
      `<p style="text-align:center;color:var(--danger);padding:30px 0">${t('spin.err_load_chart')}</p>`;
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// FEATURE: Coût réel du brassin
// ══════════════════════════════════════════════════════════════════════════════

function openBrewCostModal(brewId) {
  const b = S.brews.find(x => x.id === brewId);
  if (!b) return;
  const cd = brewCost(b);
  const mo = document.getElementById('brew-cost-modal');
  if (!mo) return;
  document.getElementById('bcm-title').textContent = esc(b.name);
  const body = document.getElementById('bcm-body');
  if (!cd) {
    body.innerHTML = `<p style="color:var(--muted);text-align:center;padding:16px 0">${t('brew.cost_no_prices')}</p>`;
    openModal('brew-cost-modal');
    return;
  }

  const CAT_ICONS  = { malt:'fa-wheat-awn', houblon:'fa-seedling', levure:'fa-flask', autre:'fa-box' };
  const CAT_COLORS = { malt:'var(--malt)', houblon:'var(--hop)', levure:'var(--yeast)', autre:'var(--muted)' };
  const CAT_LABELS = { malt: t('cat.malt'), houblon: t('cat.houblon'), levure: t('cat.levure'), autre: t('cat.autre') };

  // Scale note
  const scaleNote = Math.abs(cd.scaleFactor - 1) > 0.01
    ? `<div style="font-size:.75rem;color:var(--muted);margin-bottom:10px;padding:6px 10px;background:var(--card2);border-radius:6px"><i class="fas fa-scale-balanced" style="margin-right:4px"></i>${t('brew.cost_scaled').replace('${f}', cd.scaleFactor.toFixed(2))}</div>` : '';

  // ── Ingredients section (collapsible by category) ──────────────────────────
  const ingsByCat = {};
  (cd.ingDetails || []).forEach(ing => {
    if (!ingsByCat[ing.category]) ingsByCat[ing.category] = [];
    ingsByCat[ing.category].push(ing);
  });
  const ingSection = Object.entries(cd.cats)
    .filter(([, v]) => v > 0)
    .map(([cat, catTotal]) => {
      const color = CAT_COLORS[cat] || 'var(--muted)';
      const icon  = CAT_ICONS[cat] || 'fa-box';
      const label = CAT_LABELS[cat] || cat;
      const pct   = cd.total > 0 ? (catTotal / cd.total * 100).toFixed(0) : 0;
      const subRows = (ingsByCat[cat] || []).map(ing =>
        `<div style="display:flex;align-items:center;gap:6px;padding:3px 0 3px 22px;font-size:.78rem;color:var(--muted)">
          <span style="flex:1">${esc(ing.name)}</span>
          <span style="font-size:.72rem">${(ing.qty).toFixed(ing.qty < 1 ? 3 : 1)} ${ing.unit}</span>
          <span style="font-weight:600;color:var(--text);min-width:48px;text-align:right">${ing.cost.toFixed(2)} €</span>
        </div>`).join('');
      return `<div style="border-bottom:1px solid var(--border)">
        <div style="display:flex;align-items:center;gap:8px;padding:8px 0">
          <i class="fas ${icon}" style="color:${color};width:14px;flex-shrink:0"></i>
          <span style="flex:1;font-size:.85rem;font-weight:600">${label}</span>
          <span style="font-size:.72rem;color:var(--muted);margin-right:6px">${pct}%</span>
          <strong style="color:${color};min-width:52px;text-align:right">${catTotal.toFixed(2)} €</strong>
        </div>
        ${subRows}
      </div>`;
    }).join('');

  // ── Water row ──────────────────────────────────────────────────────────────
  const waterRow = cd.waterCost != null && cd.waterCost > 0
    ? `<div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid var(--border)">
        <i class="fas fa-droplet" style="color:var(--info);width:14px;flex-shrink:0"></i>
        <span style="flex:1;font-size:.85rem">${t('rec.cost_water').replace('${price}', ((appSettings.water||{}).price||0).toFixed(4))}</span>
        <span style="font-size:.72rem;color:var(--muted);margin-right:6px">${cd.total > 0 ? (cd.waterCost/cd.total*100).toFixed(0) : 0}%</span>
        <strong style="color:var(--info);min-width:52px;text-align:right">${cd.waterCost.toFixed(2)} €</strong>
      </div>` : '';

  // ── Energy rows ────────────────────────────────────────────────────────────
  const gasRow  = cd.gas > 0
    ? `<div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid var(--border)">
        <i class="fas fa-fire-flame-curved" style="color:var(--amber);width:14px;flex-shrink:0"></i>
        <span style="flex:1;font-size:.85rem">${t('rec.cost_gas')}</span>
        <span style="font-size:.72rem;color:var(--muted);margin-right:6px">${cd.total > 0 ? (cd.gas/cd.total*100).toFixed(0) : 0}%</span>
        <strong style="color:var(--amber);min-width:52px;text-align:right">${cd.gas.toFixed(2)} €</strong>
      </div>` : '';
  const elecRow = cd.elec > 0
    ? `<div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid var(--border)">
        <i class="fas fa-bolt" style="color:var(--gold);width:14px;flex-shrink:0"></i>
        <span style="flex:1;font-size:.85rem">${t('rec.cost_elec')}</span>
        <span style="font-size:.72rem;color:var(--muted);margin-right:6px">${cd.total > 0 ? (cd.elec/cd.total*100).toFixed(0) : 0}%</span>
        <strong style="color:var(--gold);min-width:52px;text-align:right">${cd.elec.toFixed(2)} €</strong>
      </div>` : '';

  // ── Total + cost/liter + cost/bottle ──────────────────────────────────────
  const vol = b.volume_brewed || 0;
  const perLiterRow = cd.perLiter != null
    ? `<div style="display:flex;align-items:center;gap:6px;padding:4px 0">
        <i class="fas fa-droplet" style="color:var(--muted);font-size:.75rem;width:14px"></i>
        <span style="flex:1;font-size:.8rem;color:var(--muted)">${t('brew.cost_per_liter')}${vol > 0 ? ` (${vol} L)` : ''}</span>
        <strong style="font-size:.95rem;color:var(--success)">${cd.perLiter.toFixed(2)} €</strong>
      </div>` : '';
  const per33Row = cd.per33 != null
    ? `<div style="display:flex;align-items:center;gap:6px;padding:4px 0">
        <i class="fas fa-wine-bottle" style="color:var(--muted);font-size:.75rem;width:14px"></i>
        <span style="flex:1;font-size:.8rem;color:var(--muted)">${t('brew.cost_per_bottle_33')}</span>
        <strong style="font-size:.95rem;color:var(--success)">${cd.per33.toFixed(2)} €</strong>
      </div>` : '';
  const per75Row = cd.per75 != null
    ? `<div style="display:flex;align-items:center;gap:6px;padding:4px 0">
        <i class="fas fa-wine-bottle" style="color:var(--muted);font-size:.75rem;width:14px"></i>
        <span style="flex:1;font-size:.8rem;color:var(--muted)">${t('brew.cost_per_bottle_75')}</span>
        <strong style="font-size:.95rem;color:var(--success)">${cd.per75.toFixed(2)} €</strong>
      </div>` : '';

  body.innerHTML = `
    ${scaleNote}
    <div style="margin-bottom:8px">${ingSection}${waterRow}${gasRow}${elecRow}</div>
    <div style="display:flex;justify-content:space-between;align-items:baseline;padding:10px 0 8px;font-size:1.1rem;font-weight:800;border-top:2px solid var(--border)">
      <span>Total</span>
      <span style="color:var(--success)">${cd.total.toFixed(2)} €</span>
    </div>
    <div style="display:flex;flex-direction:column;gap:2px;padding:6px 10px;background:var(--card2);border-radius:8px">
      ${perLiterRow}${per33Row}${per75Row}
      ${!perLiterRow && !per33Row && !per75Row ? `<div style="font-size:.78rem;color:var(--muted);text-align:center;padding:4px 0">${t('brew.cost_no_volume')}</div>` : ''}
    </div>`;

  openModal('brew-cost-modal');
}

// ══════════════════════════════════════════════════════════════════════════════
// FEATURE: Photos du brassin
// ══════════════════════════════════════════════════════════════════════════════

const _PHOTO_STEPS_FR = ['Empâtage','Ébullition','Fermentation','Embouteillage','Dégustation','Autre'];
const _PHOTO_STEPS_EN = ['Mashing','Boiling','Fermentation','Bottling','Tasting','Other'];

async function toggleBrewPhotos(brewId) {
  const el = document.getElementById(`brew-photos-${brewId}`);
  if (!el) return;
  if (el.style.display !== 'none') { el.style.display = 'none'; return; }
  el.style.display = '';
  el.innerHTML = `<p style="color:var(--muted);font-size:.8rem;padding:4px 0"><i class="fas fa-spinner fa-spin"></i></p>`;
  try {
    const photos = await api('GET', `/api/brews/${brewId}/photos`);
    _renderBrewPhotosGallery(brewId, photos, el);
  } catch(e) {
    el.innerHTML = `<p style="color:var(--danger);font-size:.8rem">${esc(e.message)}</p>`;
  }
}

function _renderBrewPhotosGallery(brewId, photos, el) {
  if (!el) el = document.getElementById(`brew-photos-${brewId}`);
  if (!el) return;
  const lang = document.documentElement.lang || 'fr';
  const steps = lang === 'en' ? _PHOTO_STEPS_EN : _PHOTO_STEPS_FR;
  const thumbs = photos.map(p => `
    <div style="position:relative;width:80px;height:80px;flex-shrink:0;cursor:pointer;border-radius:8px;overflow:hidden;border:1px solid var(--border)" onclick="openBrewPhotoView(${brewId},${p.id})" title="${esc(p.caption||p.step||'')}">
      ${p.thumb ? `<img src="${p.thumb}" style="width:100%;height:100%;object-fit:cover">` : `<div style="width:100%;height:100%;background:var(--card2);display:flex;align-items:center;justify-content:center"><i class="fas fa-image" style="color:var(--muted)"></i></div>`}
      ${p.step ? `<div style="position:absolute;bottom:0;left:0;right:0;background:rgba(0,0,0,.6);font-size:.6rem;color:#fff;padding:2px 4px;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(p.step)}</div>` : ''}
    </div>`).join('');
  el.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:4px 0">
      ${thumbs || `<span style="font-size:.78rem;color:var(--muted)">${t('brew.photo_empty')}</span>`}
      <button class="btn btn-ghost btn-sm btn-icon" onclick="openBrewPhotoUploadModal(${brewId})" title="${t('brew.photo_add')}" style="width:80px;height:80px;border-radius:8px;border:1px dashed var(--border);flex-direction:column;gap:4px;color:var(--muted)">
        <i class="fas fa-plus"></i>
        <span style="font-size:.65rem;text-transform:none">${t('brew.photo_add')}</span>
      </button>
    </div>`;
}

function openBrewPhotoUploadModal(brewId) {
  document.getElementById('bpu-brew-id').value = brewId;
  document.getElementById('bpu-preview').style.display = 'none';
  document.getElementById('bpu-file').value = '';
  document.getElementById('bpu-caption').value = '';
  document.getElementById('bpu-step').value = '';
  document.getElementById('bpu-data').value = '';
  openModal('brew-photo-upload-modal');
}

function _bpuFileChange(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    document.getElementById('bpu-data').value = e.target.result;
    const img = document.getElementById('bpu-preview-img');
    img.src = e.target.result;
    document.getElementById('bpu-preview').style.display = '';
  };
  reader.readAsDataURL(file);
}

async function saveBrewPhoto() {
  const brewId = parseInt(document.getElementById('bpu-brew-id').value);
  const photo  = document.getElementById('bpu-data').value;
  if (!photo) { toast(t('brew.photo_add'), 'error'); return; }
  try {
    const result = await api('POST', `/api/brews/${brewId}/photos`, {
      photo,
      step:    document.getElementById('bpu-step').value || null,
      caption: document.getElementById('bpu-caption').value || null,
    });
    closeModal('brew-photo-upload-modal');
    toast(t('brew.photo_saved'), 'success');
    // Update photo_count in S.brews
    const brew = S.brews.find(b => b.id === brewId);
    if (brew) brew.photo_count = (brew.photo_count || 0) + 1;
    // Refresh gallery if open
    const el = document.getElementById(`brew-photos-${brewId}`);
    if (el && el.style.display !== 'none') {
      const photos = await api('GET', `/api/brews/${brewId}/photos`);
      _renderBrewPhotosGallery(brewId, photos, el);
    }
    // Refresh card button color
    renderBrassins();
  } catch(e) { toast(e.message, 'error'); }
}

let _bpvPhotos = [];
let _bpvIdx    = 0;
let _bpvBrewId = 0;

async function openBrewPhotoView(brewId, photoId) {
  try {
    _bpvBrewId = brewId;
    _bpvPhotos = await api('GET', `/api/brews/${brewId}/photos`);
    _bpvIdx    = Math.max(0, _bpvPhotos.findIndex(p => p.id === photoId));
    openModal('brew-photo-view-modal');
    await _bpvLoad();
  } catch(e) { toast(e.message, 'error'); }
}

async function _bpvLoad() {
  const p = _bpvPhotos[_bpvIdx];
  if (!p) return;
  const multi = _bpvPhotos.length > 1;
  // Counter
  document.getElementById('bpv-counter').textContent = multi ? `${_bpvIdx + 1} / ${_bpvPhotos.length}` : '';
  // Nav buttons
  const prevBtn = document.getElementById('bpv-prev');
  const nextBtn = document.getElementById('bpv-next');
  prevBtn.style.display = multi ? '' : 'none';
  nextBtn.style.display = multi ? '' : 'none';
  prevBtn.disabled = _bpvIdx === 0;
  nextBtn.disabled = _bpvIdx === _bpvPhotos.length - 1;
  // Fields from list (immediate)
  document.getElementById('bpv-caption').value  = p.caption || '';
  document.getElementById('bpv-step').value     = p.step    || '';
  document.getElementById('bpv-date').textContent = p.created_at ? new Date(p.created_at).toLocaleDateString() : '';
  document.getElementById('bpv-photo-id').value  = p.id;
  document.getElementById('bpv-brew-id').value   = _bpvBrewId;
  document.getElementById('bpv-del-btn').onclick = () => deleteBrewPhoto(_bpvBrewId, p.id);
  // Load full image
  const imgEl = document.getElementById('bpv-img');
  imgEl.style.opacity = '0.4';
  imgEl.src = p.thumb || '';
  try {
    const full = await api('GET', `/api/brews/${_bpvBrewId}/photos/${p.id}`);
    imgEl.src = full.photo;
    imgEl.alt = p.caption || p.step || '';
    imgEl.style.opacity = '1';
  } catch(e) { imgEl.style.opacity = '1'; }
}

async function _bpvNav(delta) {
  const idx = _bpvIdx + delta;
  if (idx < 0 || idx >= _bpvPhotos.length) return;
  _bpvIdx = idx;
  await _bpvLoad();
}

// Keyboard navigation
document.addEventListener('keydown', e => {
  if (!document.getElementById('brew-photo-view-modal')?.classList.contains('open')) return;
  if (e.key === 'ArrowLeft')  { e.preventDefault(); _bpvNav(-1); }
  if (e.key === 'ArrowRight') { e.preventDefault(); _bpvNav(1);  }
});

async function saveBrewPhotoEdit() {
  const brewId  = parseInt(document.getElementById('bpv-brew-id').value);
  const photoId = parseInt(document.getElementById('bpv-photo-id').value);
  const step    = document.getElementById('bpv-step').value.trim();
  const caption = document.getElementById('bpv-caption').value.trim();
  await api('PATCH', `/api/brews/${brewId}/photos/${photoId}`, { step: step || null, caption: caption || null });
  // Update local cache
  const cached = _bpvPhotos.find(p => p.id === photoId);
  if (cached) { cached.step = step || null; cached.caption = caption || null; }
  toast(t('brew.photo_edit_saved'), 'success');
  // Refresh gallery thumbnail overlay
  const el = document.getElementById(`brew-photos-${brewId}`);
  if (el && el.style.display !== 'none') _renderBrewPhotosGallery(brewId, _bpvPhotos, el);
}

async function deleteBrewPhoto(brewId, photoId) {
  if (!await confirmModal(t('brew.photo_del_confirm'), { danger: true })) return;
  try {
    await api('DELETE', `/api/brews/${brewId}/photos/${photoId}`);
    toast(t('brew.photo_deleted'), 'success');
    const brew = S.brews.find(b => b.id === brewId);
    if (brew && brew.photo_count > 0) brew.photo_count--;
    // Remove from local list and navigate
    _bpvPhotos.splice(_bpvIdx, 1);
    if (!_bpvPhotos.length) {
      closeModal('brew-photo-view-modal');
    } else {
      _bpvIdx = Math.min(_bpvIdx, _bpvPhotos.length - 1);
      await _bpvLoad();
    }
    // Refresh gallery
    const el = document.getElementById(`brew-photos-${brewId}`);
    if (el && el.style.display !== 'none') _renderBrewPhotosGallery(brewId, _bpvPhotos, el);
    renderBrassins();
  } catch(e) { toast(e.message, 'error'); }
}

// ══════════════════════════════════════════════════════════════════════════════
// FEATURE: Comparaison brassins
// ══════════════════════════════════════════════════════════════════════════════

let _compareChart = null;
const _cmpFermCache = new Map(); // brewId → readings (invalidé si fermentation_count change)
const _cmpFermMeta  = new Map(); // brewId → fermentation_count au moment du cache

function _cmpInvalidateStale() {
  const brewIds = new Set(S.brews.map(b => b.id));
  for (const [id] of _cmpFermCache) {
    const brew = S.brews.find(b => b.id === id);
    // Invalide si le brassin n'existe plus ou si son fermentation_count a changé
    if (!brew || brew.fermentation_count !== _cmpFermMeta.get(id)) {
      _cmpFermCache.delete(id);
      _cmpFermMeta.delete(id);
    }
  }
  // Nettoie aussi les entrées de brews supprimés
  for (const id of _cmpFermMeta.keys()) {
    if (!brewIds.has(id)) { _cmpFermCache.delete(id); _cmpFermMeta.delete(id); }
  }
}

function openBrewCompareModal() {
  _cmpInvalidateStale();
  const list = document.getElementById('brew-cmp-list');
  if (!list) return;
  const eligible = S.brews.filter(b => !b.archived);
  if (!eligible.length) {
    toast(t('brew.compare_empty'), 'info'); return;
  }
  list.innerHTML = eligible.map(b => {
    const days = b.brew_date ? Math.floor((Date.now() - new Date(b.brew_date)) / 86400000) : null;
    const meta = [b.brew_date || '', days != null ? `J+${days}` : '', b.og ? `OG ${b.og}` : ''].filter(Boolean).join(' · ');
    const noData = !b.fermentation_count;
    return `
      <label style="display:flex;align-items:flex-start;gap:8px;padding:8px 6px;cursor:pointer;border-radius:6px;border:1px solid transparent;transition:border .15s"
             onmouseover="this.style.borderColor='var(--border)'" onmouseout="this.style.borderColor='transparent'">
        <input type="checkbox" value="${b.id}" style="width:auto;margin-top:2px" onchange="renderCompareChart()">
        <div>
          <div style="font-size:.85rem;font-weight:600">${esc(b.name)}</div>
          <div style="font-size:.72rem;color:var(--muted)">${meta}${noData ? `<span style="opacity:.6"> — ${t('brew.compare_no_data')}</span>` : ''}</div>
        </div>
      </label>`;
  }).join('');
  document.getElementById('brew-cmp-empty').style.display = '';
  if (_compareChart) { _compareChart.destroy(); _compareChart = null; }
  openModal('brew-compare-modal');
}

async function renderCompareChart() {
  const selected = [...document.querySelectorAll('#brew-cmp-list input:checked')]
    .map(cb => parseInt(cb.value)).slice(0, 5);
  const emptyEl = document.getElementById('brew-cmp-empty');
  if (!selected.length) {
    if (emptyEl) emptyEl.style.display = '';
    if (_compareChart) { _compareChart.destroy(); _compareChart = null; }
    return;
  }
  if (emptyEl) emptyEl.style.display = 'none';
  const COLORS = ['#ff9500','#22c55e','#3b82f6','#a855f7','#ef4444'];
  const datasets = await Promise.all(selected.map(async (brewId, i) => {
    const brew = S.brews.find(b => b.id === brewId);
    if (!_cmpFermCache.has(brewId)) {
      _cmpFermCache.set(brewId, await api('GET', `/api/brews/${brewId}/fermentation`));
      _cmpFermMeta.set(brewId, brew?.fermentation_count ?? 0);
    }
    const readings = _cmpFermCache.get(brewId);
    const t0 = brew.brew_date
      ? new Date(brew.brew_date + 'T00:00:00').getTime()
      : (readings[0] ? new Date(readings[0].recorded_at).getTime() : Date.now());
    const points = readings.filter(r => r.gravity != null).map(r => ({
      x: (new Date(r.recorded_at).getTime() - t0) / 86400000,
      y: r.gravity,
    }));
    return {
      label: brew.name,
      data: points,
      borderColor: COLORS[i],
      backgroundColor: COLORS[i] + '18',
      tension: 0.35,
      pointRadius: points.length > 60 ? 0 : 3,
      fill: false,
      showLine: true,
    };
  }));
  const canvas = document.getElementById('brew-compare-canvas');
  if (_compareChart) { _compareChart.destroy(); _compareChart = null; }
  const stale = Chart.getChart('brew-compare-canvas');
  if (stale) stale.destroy();
  _compareChart = new Chart(canvas.getContext('2d'), {
    type: 'scatter',
    data: { datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#ccc', font: { size: 12 } } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(3) ?? '—'}` } },
      },
      scales: {
        x: { type: 'linear', title: { display: true, text: t('brew.compare_x'), color: '#888', font: { size: 11 } },
             ticks: { color: '#888', font: { size: 11 } }, grid: { color: '#2a2a2a' } },
        y: { type: 'linear', title: { display: true, text: t('spin.metric_gravity'), color: '#ff9500', font: { size: 11 } },
             ticks: { color: '#ff9500', font: { size: 11 }, callback: v => v.toFixed(3) },
             grid: { color: '#2a2a2a' } },
      },
    },
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// FEATURE: Timer de brassage
// ══════════════════════════════════════════════════════════════════════════════

let _brewTimers = [];
let _brewTimerNextId = 1;
let _brewTimerInterval = null;
let _brewTimerAudioCtx = null;

function _ensureTimerPanel() {
  if (document.getElementById('brew-timer-panel')) return;
  const panel = document.createElement('div');
  panel.id = 'brew-timer-panel';
  panel.style.cssText = 'position:fixed;bottom:80px;right:24px;z-index:300;width:320px;background:var(--card);border:1px solid var(--border);border-radius:14px;box-shadow:0 8px 32px rgba(0,0,0,.5);display:none;flex-direction:column;overflow:hidden';
  panel.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;padding:12px 14px;border-bottom:1px solid var(--border);background:var(--card2)">
      <i class="fas fa-stopwatch" style="color:var(--amber)"></i>
      <span style="font-weight:700;font-size:.9rem;flex:1" id="brew-timer-title"></span>
      <button onclick="toggleBrewTimerPanel()" style="background:none;border:none;color:var(--muted);cursor:pointer;font-size:.8rem;padding:2px 4px" title="Fermer">✕</button>
    </div>
    <div id="brew-timer-list" style="padding:10px 12px;max-height:380px;overflow-y:auto"></div>
    <div style="padding:10px 12px;border-top:1px solid var(--border);background:var(--card2)">
      <div style="display:flex;gap:6px;margin-bottom:8px">
        <input id="brew-timer-name" type="text" placeholder="" style="flex:1;font-size:.8rem;padding:5px 8px" oninput="">
        <input id="brew-timer-mins" type="number" min="1" max="999" value="60" style="width:60px;font-size:.8rem;padding:5px 8px">
        <button class="btn btn-primary btn-sm" onclick="addBrewTimer()" id="brew-timer-add-btn" style="white-space:nowrap;font-size:.78rem;padding:5px 10px"></button>
      </div>
      <div id="brew-timer-presets" style="display:flex;gap:4px;flex-wrap:wrap"></div>
    </div>`;
  document.body.appendChild(panel);
  _renderTimerPanelI18n();
}

function _renderTimerPanelI18n() {
  const ti = document.getElementById('brew-timer-title');
  const ph = document.getElementById('brew-timer-name');
  const ab = document.getElementById('brew-timer-add-btn');
  if (ti) ti.textContent = t('brew.timer_title');
  if (ph) ph.placeholder = t('brew.timer_name_ph');
  if (ab) ab.textContent = t('brew.timer_add');
  const presets = document.getElementById('brew-timer-presets');
  if (presets) {
    const lang = document.documentElement.lang || 'fr';
    const ps = lang === 'en'
      ? [['Mash 60min',60],['Boil 60min',60],['Boil 90min',90],['Hop +30min',30],['Hop +15min',15],['Hop +5min',5]]
      : [['Empâtage 60min',60],['Ébullition 60min',60],['Ébullition 90min',90],['Houblon +30min',30],['Houblon +15min',15],['Houblon +5min',5]];
    presets.innerHTML = ps.map(([name,mins]) =>
      `<button class="btn btn-ghost btn-sm" style="font-size:.7rem;padding:3px 7px" onclick="addBrewTimer('${name}',${mins})">${name}</button>`
    ).join('');
  }
}

function toggleBrewTimerPanel() {
  _ensureTimerPanel();
  const panel = document.getElementById('brew-timer-panel');
  if (!panel) return;
  const visible = panel.style.display !== 'none';
  panel.style.display = visible ? 'none' : 'flex';
  if (!visible) _renderTimerList();
}

async function openBrewTimerForBrew(brewId) {
  _ensureTimerPanel();
  const brew = S.brews.find(b => b.id === brewId);
  if (!brew?.recipe_id) { toggleBrewTimerPanel(); return; }

  let rec = S.recipes.find(r => r.id === brew.recipe_id);
  if (!rec) {
    try { rec = await api('GET', `/api/recipes/${brew.recipe_id}`); } catch(e) { toggleBrewTimerPanel(); return; }
  }

  const presets = document.getElementById('brew-timer-presets');
  if (!presets) { toggleBrewTimerPanel(); return; }

  const mash = rec.mash_time || 60;
  const boil = rec.boil_time || 60;

  // Étapes fixes : empâtage + ébullition
  const steps = [
    { name: `${t('brew.timer_step_mash')} ${mash} min`, mins: mash, color: 'var(--malt)' },
    { name: `${t('brew.timer_step_boil')} ${boil} min`, mins: boil, color: 'var(--amber)' },
  ];

  // Ajouts de houblon à l'ébullition (triés du plus tardif au plus précoce)
  const boilHops = (rec.ingredients || [])
    .filter(i => i.category === 'houblon' && i.hop_type === 'ebullition' && i.hop_time > 0)
    .sort((a, b) => b.hop_time - a.hop_time);
  const seenTimes = new Set();
  boilHops.forEach(h => {
    if (seenTimes.has(h.hop_time)) return;
    seenTimes.add(h.hop_time);
    steps.push({ name: `${t('brew.timer_step_hop')} +${h.hop_time} min`, mins: h.hop_time, color: 'var(--hop)' });
  });

  // Hop stand / whirlpool
  const hasWhirl = (rec.ingredients || []).some(i => i.category === 'houblon' && i.hop_type === 'whirlpool');
  if (hasWhirl) steps.push({ name: `${t('brew.timer_step_hopstand')} 20 min`, mins: 20, color: 'var(--hop)' });

  presets.innerHTML = steps.map(s =>
    `<button class="btn btn-ghost btn-sm" style="font-size:.7rem;padding:3px 7px;border-color:${s.color}40"
      onclick="addBrewTimer('${s.name.replace(/'/g, "\\'")}',${s.mins})">${s.name}</button>`
  ).join('');

  const ti = document.getElementById('brew-timer-title');
  if (ti) ti.textContent = `${t('brew.timer_title')} — ${esc(brew.name)}`;

  const panel = document.getElementById('brew-timer-panel');
  if (panel) panel.style.display = 'flex';
  _renderTimerList();
}

function addBrewTimer(name, mins) {
  _ensureTimerPanel();
  const nameVal = name || document.getElementById('brew-timer-name')?.value.trim() || t('brew.timer_name_ph');
  const minsVal = mins || parseInt(document.getElementById('brew-timer-mins')?.value) || 60;
  _brewTimers.push({ id: _brewTimerNextId++, name: nameVal, totalSecs: minsVal * 60, remainingSecs: minsVal * 60, running: false, done: false });
  if (document.getElementById('brew-timer-name')) document.getElementById('brew-timer-name').value = '';
  // Start global tick if not running
  if (!_brewTimerInterval) {
    _brewTimerInterval = setInterval(_tickTimers, 1000);
  }
  _renderTimerList();
  const panel = document.getElementById('brew-timer-panel');
  if (panel) panel.style.display = 'flex';
}

function _tgNotifyTimer(name, type) {
  fetch('/api/notify/timer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, type }),
  }).catch(() => {});
}

function _tickTimers() {
  let anyRunning = false;
  _brewTimers.forEach(timer => {
    if (timer.running && !timer.done) {
      timer.remainingSecs--;
      if (timer.remainingSecs <= 0) {
        timer.remainingSecs = 0;
        timer.running = false;
        timer.done = true;
        _timerDone(timer);
        _tgNotifyTimer(timer.name, 'done');
      } else {
        if (timer.remainingSecs === 300 && !timer.notifiedWarn) {
          timer.notifiedWarn = true;
          _tgNotifyTimer(timer.name, 'warning');
        }
        anyRunning = true;
      }
    } else if (timer.running) {
      anyRunning = true;
    }
  });
  if (!anyRunning && _brewTimerInterval) {
    const stillRunning = _brewTimers.some(t => t.running);
    if (!stillRunning) { clearInterval(_brewTimerInterval); _brewTimerInterval = null; }
  }
  _renderTimerList();
}

function _fmtSecs(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
  return `${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
}

function _renderTimerList() {
  const el = document.getElementById('brew-timer-list');
  if (!el) return;
  if (!_brewTimers.length) {
    el.innerHTML = `<p style="color:var(--muted);font-size:.82rem;text-align:center;padding:8px 0">${t('brew.timer_empty')}</p>`;
    return;
  }
  el.innerHTML = _brewTimers.map(timer => {
    const pct = (1 - timer.remainingSecs / timer.totalSecs) * 100;
    const color = timer.done ? 'var(--success)' : timer.running ? 'var(--amber)' : 'var(--info)';
    const icon  = timer.done ? 'fa-check-circle' : timer.running ? 'fa-pause' : 'fa-play';
    const pulse = timer.done ? 'animation:timerPulse 1s infinite' : '';
    return `
      <div style="background:var(--card2);border-radius:10px;padding:9px 11px;margin-bottom:7px;border:1px solid ${timer.done?'var(--success)':'var(--border)'}">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
          <span style="flex:1;font-size:.83rem;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(timer.name)}</span>
          <span style="font-size:1rem;font-weight:800;color:${color};font-variant-numeric:tabular-nums;${pulse}">${_fmtSecs(timer.remainingSecs)}</span>
        </div>
        <div style="height:4px;background:var(--border);border-radius:2px;margin-bottom:7px;overflow:hidden">
          <div style="height:100%;width:${pct.toFixed(1)}%;background:${color};transition:width .9s linear;border-radius:2px"></div>
        </div>
        <div style="display:flex;gap:5px;justify-content:flex-end">
          ${!timer.done ? `<button class="btn btn-ghost btn-sm" style="font-size:.72rem;padding:3px 8px" onclick="_toggleTimer(${timer.id})">
            <i class="fas ${timer.running ? 'fa-pause' : 'fa-play'}"></i> ${timer.running ? 'Pause' : 'Start'}
          </button>` : ''}
          <button class="btn btn-ghost btn-sm" style="font-size:.72rem;padding:3px 8px" onclick="_resetTimer(${timer.id})"><i class="fas fa-rotate-left"></i></button>
          <button class="btn btn-ghost btn-sm" style="font-size:.72rem;padding:3px 8px;color:var(--danger)" onclick="_removeTimer(${timer.id})"><i class="fas fa-trash"></i></button>
        </div>
      </div>`;
  }).join('');
}

function _toggleTimer(id) {
  const timer = _brewTimers.find(t => t.id === id);
  if (!timer || timer.done) return;
  timer.running = !timer.running;
  if (timer.running && !_brewTimerInterval) {
    _brewTimerInterval = setInterval(_tickTimers, 1000);
  }
  _renderTimerList();
}

function _resetTimer(id) {
  const timer = _brewTimers.find(t => t.id === id);
  if (!timer) return;
  timer.remainingSecs = timer.totalSecs;
  timer.running = false;
  timer.done = false;
  _renderTimerList();
}

function _removeTimer(id) {
  _brewTimers = _brewTimers.filter(t => t.id !== id);
  if (!_brewTimers.some(t => t.running) && _brewTimerInterval) {
    clearInterval(_brewTimerInterval); _brewTimerInterval = null;
  }
  _renderTimerList();
}

function _timerDone(timer) {
  // Beep
  try {
    if (!_brewTimerAudioCtx) _brewTimerAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const ctx = _brewTimerAudioCtx;
    [0, 0.35, 0.7].forEach(offset => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.4, ctx.currentTime + offset);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + offset + 0.28);
      osc.start(ctx.currentTime + offset);
      osc.stop(ctx.currentTime + offset + 0.3);
    });
  } catch(e) {}
  // Browser notification
  try {
    const msg = t('brew.timer_done').replace('${name}', timer.name);
    if (Notification.permission === 'granted') {
      new Notification('BrewHome — Timer', { body: msg });
    } else if (Notification.permission !== 'denied') {
      Notification.requestPermission().then(p => {
        if (p === 'granted') new Notification('BrewHome — Timer', { body: msg });
      });
    }
  } catch(e) {}
  _renderTimerList();
}

let _editSpindleId = null;

// ── Densimètres : types d'appareils ──────────────────────────────────────────
const DEVICE_INFO = {
  ispindel:   { label: 'iSpindel',   color: '#f59e0b' },
  tilt:       { label: 'Tilt',       color: '#3b82f6' },
  gravitymon: { label: 'GravityMon', color: '#10b981' },
  generic:    { get label() { return t('spin.device_generic'); }, color: '#6b7280' },
};

function _spindleConfigHtml(deviceType, token, host) {
  const url = `${host}/api/spindle/data?token=${token}`;
  const urlLine = `<div style="display:flex;gap:8px;align-items:flex-start;margin:6px 0 4px">
    <code style="flex:1;font-size:.78rem;word-break:break-all;color:var(--info);background:var(--bg);padding:6px 8px;border-radius:6px;border:1px solid var(--border)">${url}</code>
    <button class="btn btn-ghost btn-sm" onclick="navigator.clipboard.writeText('${url}').then(()=>toast(t('spin.url_copied'),'success'))" title="${t('spin.cfg_copy_url')}"><i class="fas fa-copy"></i></button>
  </div>`;
  switch (deviceType) {
    case 'tilt':
      return `<div style="font-size:.82rem;color:var(--muted)">
        <p style="font-weight:600;margin-bottom:6px;color:var(--text)"><i class="fas fa-circle-info" style="color:#3b82f6"></i> ${t('spin.cfg_tilt_title')}</p>
        <ul style="margin:0 0 8px 16px;line-height:1.7">
          <li>Service : <strong>Custom HTTP</strong></li>
          <li>Method : <strong>POST</strong></li>
          <li>URL :</li>
        </ul>
        ${urlLine}
        <p style="margin-top:6px"><i class="fas fa-rotate" style="color:#f59e0b"></i> ${t('spin.cfg_tilt_temp_note')}</p>
        <p>${t('spin.cfg_tilt_fields')} <code>SG</code>, <code>Temp</code> (°F), <code>Color</code></p>
      </div>`;
    case 'gravitymon':
      return `<div style="font-size:.82rem;color:var(--muted)">
        <p style="font-weight:600;margin-bottom:6px;color:var(--text)"><i class="fas fa-circle-info" style="color:#10b981"></i> ${t('spin.cfg_gmon_title')}</p>
        <ul style="margin:0 0 8px 16px;line-height:1.7">
          <li>Service : ${t('spin.cfg_gmon_service')}</li>
          <li>Method : <strong>POST</strong></li>
          <li>URL :</li>
        </ul>
        ${urlLine}
        <p style="margin-top:6px">${t('spin.cfg_gmon_fields')} <code>gravity</code>, <code>temperature</code> (°C), <code>battery</code>, <code>angle</code>, <code>rssi</code></p>
      </div>`;
    case 'generic':
      return `<div style="font-size:.82rem;color:var(--muted)">
        <p style="font-weight:600;margin-bottom:6px;color:var(--text)"><i class="fas fa-circle-info" style="color:#6b7280"></i> ${t('spin.cfg_gen_title')}</p>
        <p style="margin-bottom:6px">${t('spin.cfg_gen_desc')}</p>
        ${urlLine}
        <p style="margin-top:8px;font-weight:600;color:var(--text)">${t('spin.cfg_gen_fields')}</p>
        <table style="font-size:.78rem;border-collapse:collapse;width:100%;margin-top:4px">
          <tr><td style="padding:2px 8px 2px 0;color:var(--text)"><code>gravity</code></td><td>or <code>SG</code>, <code>specific_gravity</code></td></tr>
          <tr><td style="padding:2px 8px 2px 0;color:var(--text)"><code>temperature</code></td><td>or <code>temp</code>, <code>celsius</code> (°C) — or <code>temp_f</code> (°F)</td></tr>
          <tr><td style="padding:2px 8px 2px 0;color:var(--text)"><code>battery</code></td><td>or <code>voltage</code> (V, ex: 3.85)</td></tr>
          <tr><td style="padding:2px 8px 2px 0;color:var(--text)"><code>angle</code></td><td>or <code>tilt</code></td></tr>
          <tr><td style="padding:2px 8px 2px 0;color:var(--text)"><code>rssi</code></td><td>or <code>RSSI</code>, <code>signal</code></td></tr>
        </table>
        <p style="margin-top:6px">${t('spin.cfg_gen_token_hint')} <code>{"token":"…","gravity":…}</code></p>
      </div>`;
    default: // ispindel
      return `<div style="font-size:.82rem;color:var(--muted)">
        <p style="font-weight:600;margin-bottom:6px;color:var(--text)"><i class="fas fa-circle-info" style="color:#f59e0b"></i> ${t('spin.cfg_ispindel_title')}</p>
        <ul style="margin:0 0 8px 16px;line-height:1.7">
          <li>Service : <strong>HTTP</strong></li>
          <li>Method : <strong>POST</strong></li>
          <li>Port : <strong>5000</strong></li>
          <li>Path : <strong>/api/spindle/data</strong></li>
          <li>URL :</li>
        </ul>
        ${urlLine}
      </div>`;
  }
}

function openSpindleModal() {
  _editSpindleId = null;
  document.getElementById('spindle-modal-title').textContent = t('spin.modal_add');
  document.getElementById('spin-f-name').value = '';
  document.getElementById('spin-f-notes').value = '';
  document.getElementById('spin-f-type').value = 'ispindel';
  document.getElementById('spin-type-wrap').style.display = '';
  document.getElementById('spindle-token-section').style.display = 'none';
  document.getElementById('spindle-save-btn').style.display = '';
  document.getElementById('spindle-save-btn').innerHTML = `<i class="fas fa-plus"></i> ${t('spin.create')}`;
  openModal('spindle-modal');
}

function openSpindleEditModal(id) {
  const sp = S.spindles.find(s => s.id === id);
  if (!sp) return;
  _editSpindleId = id;
  document.getElementById('spindle-modal-title').textContent = `${t('common.edit')} — ${sp.name}`;
  document.getElementById('spin-f-name').value  = sp.name;
  document.getElementById('spin-f-notes').value = sp.notes || '';
  document.getElementById('spin-f-type').value  = sp.device_type || 'ispindel';
  document.getElementById('spin-type-wrap').style.display = '';
  document.getElementById('spindle-token-section').style.display = 'none';
  document.getElementById('spindle-save-btn').style.display = '';
  document.getElementById('spindle-save-btn').innerHTML = `<i class="fas fa-floppy-disk"></i> ${t('common.save')}`;
  openModal('spindle-modal');
}

async function saveSpindle() {
  const name = document.getElementById('spin-f-name').value.trim();
  if (!name) { toast(t('spin.name_required'), 'error'); return; }
  const notes       = document.getElementById('spin-f-notes').value.trim() || null;
  const device_type = document.getElementById('spin-f-type').value || 'ispindel';

  // ── Mode édition ──
  if (_editSpindleId !== null) {
    try {
      const updated = await api('PATCH', `/api/spindles/${_editSpindleId}`, { name, notes, device_type });
      const idx = S.spindles.findIndex(s => s.id === _editSpindleId);
      if (idx !== -1) S.spindles[idx] = updated;
      renderSpindles();
      closeModal('spindle-modal');
      toast(t('spin.updated'), 'success');
    } catch(e) { toast(t('spin.err_update'), 'error'); }
    return;
  }

  // ── Mode création ──
  try {
    const sp = await api('POST', '/api/spindles', { name, notes, device_type });
    S.spindles.unshift(sp);
    renderSpindles();
    document.getElementById('spindle-token-display').textContent = sp.token;
    document.getElementById('spindle-token-instructions').innerHTML =
      _spindleConfigHtml(sp.device_type || 'ispindel', sp.token, window.location.origin);
    document.getElementById('spindle-token-section').style.display = '';
    document.getElementById('spindle-save-btn').style.display = 'none';
    toast(t('spin.created'), 'success');
  } catch(e) { toast(t('spin.err_create'), 'error'); }
}

function copySpindleToken() {
  const tok = document.getElementById('spindle-token-display').textContent;
  navigator.clipboard.writeText(tok).then(() => toast(t('spin.token_copied'), 'success'));
}

function showSpindleToken(spindleId) {
  const sp = S.spindles.find(s => s.id === spindleId);
  if (!sp) return;
  const devInfo = DEVICE_INFO[sp.device_type] || DEVICE_INFO.generic;
  document.getElementById('stm-spindle-name').innerHTML =
    `${esc(sp.name)} — <span style="color:${devInfo.color};font-weight:600">${devInfo.label}</span>`;
  document.getElementById('stm-token').textContent = sp.token;
  const url = `${window.location.origin}/api/spindle/data?token=${sp.token}`;
  document.getElementById('stm-url').textContent = url;
  document.getElementById('stm-instructions').innerHTML =
    _spindleConfigHtml(sp.device_type || 'ispindel', sp.token, window.location.origin);
  openModal('spindle-token-modal');
}

function copyStmToken() {
  const tok = document.getElementById('stm-token').textContent;
  navigator.clipboard.writeText(tok).then(() => toast(t('spin.token_copied'), 'success'));
}

function copyStmUrl() {
  const raw = document.getElementById('stm-url').textContent;
  navigator.clipboard.writeText(raw).then(() => toast(t('spin.url_copied'), 'success'));
}

async function linkSpindleBrew(spindleId, brewId) {
  try {
    const updated = await api('PATCH', `/api/spindles/${spindleId}`, {
      brew_id: brewId ? parseInt(brewId) : null,
    });
    const idx = S.spindles.findIndex(s => s.id === spindleId);
    if (idx !== -1) S.spindles[idx] = updated;
    renderSpindles();
    toast(brewId ? t('spin.linked') : t('spin.unlinked'), 'success');
  } catch(e) { toast(t('spin.err_link'), 'error'); }
}

async function deleteSpindle(id) {
  if (!await confirmModal(t('spin.confirm_delete'), { danger: true })) return;
  try {
    await api('DELETE', `/api/spindles/${id}`);
    S.spindles = S.spindles.filter(s => s.id !== id);
    renderSpindles();
    toast(t('spin.deleted'), 'success');
  } catch(e) { toast(t('spin.err_delete'), 'error'); }
}

async function openSpindleChart(spindleId) {
  _spindleChartId = spindleId;
  const sp = S.spindles.find(s => s.id === spindleId);
  document.getElementById('spindle-chart-title').textContent = `Suivi — ${sp ? esc(sp.name) : ''}`;

  // Afficher la barre de plage et reset à 24h
  const rangeBar = document.getElementById('spindle-chart-range');
  rangeBar.style.display = 'flex';
  rangeBar.querySelectorAll('.sc-range').forEach(b => {
    b.classList.remove('btn-primary'); b.classList.add('btn-ghost');
  });
  rangeBar.querySelector('[data-range="24"]').classList.replace('btn-ghost', 'btn-primary');
  document.getElementById('sc-custom-range').style.display = 'none';

  openModal('spindle-chart-modal');
  await _loadSpindleChart({ hours: 24 });
}

async function _loadSpindleChart({ hours, from, to } = {}) {
  const seq = ++_spindleChartSeq;
  if (_spindleChart) { _spindleChart.destroy(); _spindleChart = null; }
  const stale = Chart.getChart('spindle-chart-canvas');
  if (stale) stale.destroy();
  document.getElementById('spindle-chart-table').innerHTML =
    `<p style="text-align:center;color:var(--muted);padding:20px 0"><i class="fas fa-spinner fa-spin"></i> ${t('common.loading')}</p>`;

  try {
    let url = `/api/spindles/${_spindleChartId}/readings?limit=2000`;
    if (hours)  url += `&hours=${hours}`;
    if (from)   url += `&from=${encodeURIComponent(from)}`;
    if (to)     url += `&to=${encodeURIComponent(to)}`;

    const readings = await api('GET', url);
    if (seq !== _spindleChartSeq) return;  // requête obsolète, une plus récente a pris le relais

    if (!readings.length) {
      document.getElementById('spindle-chart-table').innerHTML =
        `<p style="text-align:center;color:var(--muted);padding:30px 0">${t('brew.no_readings_period')}</p>`;
      return;
    }

    const labels    = readings.map(r => fmtReadingDate(r.recorded_at));
    const gravities = readings.map(r => r.gravity);
    const temps     = readings.map(r => r.temperature);
    const ptRadius  = readings.length > 60 ? 0 : 3;

    // OG = max des mesures de la fenêtre affichée (delta ABV cohérent avec le graphique visible)
    const og = Math.max(...gravities.filter(g => g != null));
    const abvChartLabel = t('brew.abv_chart_label').replace('${og}', og.toFixed(3));
    const abvData = gravities.map(g => g != null ? parseFloat(((og - g) * 131.25).toFixed(2)) : null);
    const abvFinal = abvData[abvData.length - 1];

    const canvas = document.getElementById('spindle-chart-canvas');
    canvas.style.width  = '100%';
    canvas.style.height = '100%';
    _spindleChart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: t('spin.metric_gravity'),
            data: gravities,
            borderColor: '#ff9500',
            backgroundColor: 'rgba(255,149,0,.12)',
            yAxisID: 'yGrav',
            tension: 0.35,
            pointRadius: ptRadius,
            fill: true,
          },
          {
            label: abvChartLabel,
            data: abvData,
            borderColor: '#22c55e',
            backgroundColor: 'rgba(34,197,94,.08)',
            yAxisID: 'yAbv',
            tension: 0.35,
            pointRadius: ptRadius,
            fill: false,
          },
          {
            label: `${t('spin.metric_temp')} (°C)`,
            data: temps,
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59,130,246,.08)',
            yAxisID: 'yTemp',
            tension: 0.35,
            pointRadius: ptRadius,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { labels: { color: '#ccc', font: { size: 12 } } },
          tooltip: {
            callbacks: {
              label: ctx => {
                const v = ctx.parsed.y;
                if (ctx.dataset.yAxisID === 'yAbv')                         return ` ${t('spin.abv_est')} : ${v != null ? v.toFixed(2) + ' %' : '—'}`;
                if (ctx.dataset.label === t('spin.metric_gravity'))           return ` ${t('spin.metric_gravity')} : ${v != null ? v.toFixed(3) : '—'}`;
                if (ctx.dataset.label === `${t('spin.metric_temp')} (°C)`)   return ` ${t('spin.temp')} : ${v != null ? v.toFixed(1) + ' °C' : '—'}`;
                return ` ${ctx.dataset.label} : ${v}`;
              },
            },
          },
        },
        scales: {
          x: {
            ticks: { color: '#888', maxTicksLimit: 10, font: { size: 11 } },
            grid:  { color: '#2a2a2a' },
          },
          yGrav: {
            type: 'linear', position: 'left',
            ticks: { color: '#ff9500', font: { size: 11 } },
            grid:  { color: '#2a2a2a' },
            title: { display: true, text: t('spin.metric_gravity'), color: '#ff9500', font: { size: 11 } },
          },
          yAbv: {
            type: 'linear', position: 'right',
            min: 0,
            ticks: { color: '#22c55e', font: { size: 11 }, callback: v => v.toFixed(1) + '%' },
            grid:  { drawOnChartArea: false },
            title: { display: true, text: 'ABV %', color: '#22c55e', font: { size: 11 } },
          },
          yTemp: {
            type: 'linear', position: 'right',
            display: false,
            grid:  { drawOnChartArea: false },
          },
        },
      },
    });

    const recent = readings.slice(-10).reverse();
    const ogLabel = `OG ${og.toFixed(3)}`;
    const abvLabel = abvFinal != null ? `${t('spin.abv_est')} <strong style="color:#22c55e">${abvFinal.toFixed(2)}%</strong>` : '';
    document.getElementById('spindle-chart-table').innerHTML = `
      <div style="display:flex;gap:16px;align-items:center;margin-bottom:10px;flex-wrap:wrap">
        <h4 style="margin:0;font-size:.9rem;color:var(--muted)">${t('spin.chart_readings_live').replace('${n}', readings.length)}</h4>
        <span style="font-size:.82rem;color:var(--muted)">${ogLabel}</span>
        ${abvLabel ? `<span style="font-size:.82rem">${abvLabel}</span>` : ''}
      </div>
      <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:.82rem">
        <thead><tr style="color:var(--muted);border-bottom:1px solid var(--border)">
          <th style="text-align:left;padding:5px 8px">${t('spin.col_date_time')}</th>
          <th style="text-align:center;padding:5px 8px">${t('spin.metric_gravity')}</th>
          <th style="text-align:center;padding:5px 8px">${t('spin.abv_est')}</th>
          <th style="text-align:center;padding:5px 8px">${t('spin.temp')} (°C)</th>
          <th style="text-align:center;padding:5px 8px">${t('spin.battery')}</th>
          <th style="text-align:center;padding:5px 8px">${t('spin.angle')}</th>
        </tr></thead>
        <tbody>
          ${recent.map(r => {
            const abv = r.gravity != null ? ((og - r.gravity) * 131.25).toFixed(2) : null;
            return `
            <tr style="border-bottom:1px solid rgba(255,255,255,.04)">
              <td style="padding:5px 8px;color:var(--muted)">${fmtReadingDate(r.recorded_at)}</td>
              <td style="text-align:center;padding:5px 8px;color:var(--amber);font-weight:600">${r.gravity != null ? r.gravity.toFixed(3) : '—'}</td>
              <td style="text-align:center;padding:5px 8px;color:#22c55e;font-weight:600">${abv != null ? abv + '%' : '—'}</td>
              <td style="text-align:center;padding:5px 8px;color:#3b82f6">${r.temperature != null ? r.temperature.toFixed(1) + '°' : '—'}</td>
              <td style="text-align:center;padding:5px 8px;color:var(--muted)">${r.battery != null ? r.battery.toFixed(2) + 'V' : '—'}</td>
              <td style="text-align:center;padding:5px 8px;color:var(--muted)">${r.angle != null ? r.angle.toFixed(1) + '°' : '—'}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;
  } catch(e) { if (seq === _spindleChartSeq) toast(t('spin.err_load'), 'error'); }
}

function setSpindleRange(btn, range) {
  document.querySelectorAll('.sc-range').forEach(b => {
    b.classList.remove('btn-primary'); b.classList.add('btn-ghost');
  });
  btn.classList.remove('btn-ghost'); btn.classList.add('btn-primary');
  const customEl = document.getElementById('sc-custom-range');
  if (range === 'custom') {
    customEl.style.display = 'flex';
    return;
  }
  customEl.style.display = 'none';
  _loadSpindleChart({ hours: range > 0 ? range : null });
}

function applyCustomSpindleRange() {
  const fromVal = document.getElementById('sc-from').value;
  const toVal   = document.getElementById('sc-to').value;
  if (!fromVal) { toast(t('spin.select_date_start'), 'error'); return; }
  // Convertir heure affichée (UTC + tz_offset) → heure serveur (UTC)
  const tz = getTzOffset();
  const toServerTs = str => {
    if (!str) return null;
    const d = new Date(str + ':00Z');
    d.setTime(d.getTime() - tz * 3600000);
    return d.toISOString().slice(0, 19).replace('T', ' ');
  };
  _loadSpindleChart({ from: toServerTs(fromVal), to: toServerTs(toVal) });
}

