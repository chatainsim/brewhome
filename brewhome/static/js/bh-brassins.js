// ══════════════════════════════════════════════════════════════════════════════
// ── GUIDE DE BRASSAGE INTERACTIF ─────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════
let _bgState = null;

function _calcRecipeWaterVols(r, ings) {
  const vol   = r.volume || 20;
  const boil  = r.boil_time || 60;
  const ratio = r.mash_ratio || 3;
  const evap  = r.evap_rate || 3;
  const abs   = r.grain_absorption || 0.8;
  const grainKg = ings.filter(i => i.category === 'malt')
    .reduce((s, i) => s + (i.unit === 'kg' ? i.quantity : i.quantity / 1000), 0);
  const preboil    = vol + evap * (boil / 60);
  const totalWater = preboil + grainKg * abs;
  const mashWater  = grainKg > 0 ? Math.max(grainKg * ratio, totalWater * 0.55) : 0;
  const sparge     = Math.max(0, totalWater - mashWater);
  const fmtL = v => v > 0 ? v.toFixed(1) : '–';
  return {
    mash:    grainKg > 0 ? fmtL(mashWater) : '–',
    sparge:  grainKg > 0 ? fmtL(sparge)    : '–',
    preboil: fmtL(preboil),
    total:   grainKg > 0 ? fmtL(totalWater): '–',
  };
}

async function openBrewingGuideFromBrew(brewId) {
  const brew = S.brews.find(x => x.id === brewId);
  if (!brew || !brew.recipe_id) { toast(t('brew.guide_no_recipe'), 'error'); return; }
  let r = S.recipes.find(x => x.id === brew.recipe_id);
  if (!r || !r.ingredients) {
    try { r = await api('GET', `/api/recipes/${brew.recipe_id}`); }
    catch(e) { toast(t('common.error'), 'error'); return; }
  }
  const ings = r.ingredients || [];
  const boilTime = r.boil_time || 60;
  _bgState = {
    r,
    vol:      brew.volume_brewed || r.volume || 20,
    malts:    ings.filter(i => i.category === 'malt'),
    boilHops: ings.filter(i => i.category === 'houblon' && ['ebullition','whirlpool','flameout'].includes(i.hop_type || 'ebullition'))
                  .sort((a, bb) => (bb.hop_time ?? boilTime) - (a.hop_time ?? boilTime)),
    dryHops:  ings.filter(i => i.category === 'houblon' && i.hop_type === 'dryhop'),
    yeasts:   ings.filter(i => i.category === 'levure'),
    others:   ings.filter(i => i.category === 'autre'),
    boilTime,
    mashTime:  r.mash_time || 60,
    mashTemp:  r.mash_temp || 66,
    fermTemp:  r.ferm_temp || 20,
    step: 0,
    timerSec: 0,
    timerTarget: 0,
    timerRunning: false,
    timerInterval: null,
    notified: new Set(),
    checked: {},
    wv: _calcRecipeWaterVols(r, ings),
  };
  document.getElementById('modal-brew-guide').classList.add('open');
  _bgRenderAll();
}

function openBrewingGuide() {
  if (!recEditingId) { showRecAlert(t('rec.err_open_to_print')); return; }
  const r = S.recipes.find(x => x.id === recEditingId);
  if (!r) return;
  const wv = id => document.getElementById(id)?.textContent?.trim() || '–';
  const boilTime = r.boil_time || 60;
  _bgState = {
    r,
    vol:      parseFloat(document.getElementById('rec-volume')?.value) || r.volume || 20,
    malts:    recIngredients.filter(i => i.category === 'malt'),
    boilHops: recIngredients.filter(i => i.category === 'houblon' && ['ebullition','whirlpool','flameout'].includes(i.hop_type||'ebullition'))
                .sort((a,b) => (b.hop_time??boilTime) - (a.hop_time??boilTime)),
    dryHops:  recIngredients.filter(i => i.category === 'houblon' && i.hop_type === 'dryhop'),
    yeasts:   recIngredients.filter(i => i.category === 'levure'),
    others:   recIngredients.filter(i => i.category === 'autre'),
    boilTime,
    mashTime: r.mash_time || 60,
    mashTemp: r.mash_temp || 66,
    fermTemp: r.ferm_temp || 20,
    step: 0,
    timerSec: 0,
    timerTarget: 0,
    timerRunning: false,
    timerInterval: null,
    notified: new Set(),
    checked: {},
    wv: { mash: wv('rw-mash'), sparge: wv('rw-sparge'), preboil: wv('rw-preboil'), total: wv('rw-total') },
  };
  document.getElementById('modal-brew-guide').classList.add('open');
  _bgRenderAll();
}

let _scaleGuideActive = false;
let _scaleGuidePollInterval = null;
let _scaleGuideStep = 0;

function _sgUpdateUi(active, statusText) {
  const col   = active ? 'var(--hop)'              : '#f0883e';
  const bc    = active ? 'rgba(74,222,128,.35)'    : 'rgba(240,136,62,.35)';
  const bcFs  = active ? 'rgba(74,222,128,.4)'     : 'rgba(240,136,62,.35)';
  const bgFs  = active ? 'rgba(74,222,128,.08)'    : 'rgba(240,136,62,.08)';
  const label = active ? t('rec.scale_guide_stop') : t('rec.scale_guide_start');
  // Modal elements
  const btn  = document.getElementById('scale-guide-btn');
  const lbl  = document.getElementById('scale-guide-label');
  const stat = document.getElementById('scale-guide-status');
  if (btn)  { btn.style.color = col; btn.style.borderColor = bc; }
  if (lbl)  lbl.textContent = label;
  if (stat) { stat.textContent = statusText; stat.style.display = statusText ? 'block' : 'none'; }
  // Fullscreen elements
  const bBtn  = document.getElementById('bfs-scale-btn');
  const bLbl  = document.getElementById('bfs-scale-lbl');
  const bStat = document.getElementById('bfs-scale-status');
  if (bBtn)  { bBtn.style.color = col; bBtn.style.borderColor = bcFs; bBtn.style.background = bgFs; }
  if (bLbl)  bLbl.textContent = label;
  if (bStat) { bStat.textContent = statusText; bStat.style.display = statusText ? 'block' : 'none'; }
}

function _scaleGuidePollFn() {
  fetch('/api/scale-guide').then(r => r.json()).then(data => {
    if (!_scaleGuideActive) return;
    if (!data.active) {
      // Terminé par l'appareil — cocher tous les malts restants
      const total = _bgState?.malts?.length ?? 0;
      for (let i = Math.max(0, _scaleGuideStep - 1); i < total; i++) {
        const key = `malt-${i}`;
        if (_bgState && !_bgState.checked[key]) _bgToggleCheck(key);
      }
      _scaleGuideActive = false;
      clearInterval(_scaleGuidePollInterval);
      _scaleGuidePollInterval = null;
      _scaleGuideStep = 0;
      _sgUpdateUi(false, '');
      return;
    }
    const newStep = data.step || 1;
    if (newStep > _scaleGuideStep) {
      // Cocher les malts désormais terminés (indices scaleGuideStep-1 à newStep-2)
      for (let i = Math.max(0, _scaleGuideStep - 1); i <= newStep - 2; i++) {
        const key = `malt-${i}`;
        if (_bgState && !_bgState.checked[key]) _bgToggleCheck(key);
      }
      _scaleGuideStep = newStep;
    }
    const sg = t('rec.scale_guide_active')
      .replace('${malt}', data.malt_name || '')
      .replace('${kg}', data.target_kg ?? '—')
      .replace('${step}', data.step || 1)
      .replace('${total}', data.total || 1);
    _sgUpdateUi(true, sg);
  }).catch(() => {});
}

async function _bgToggleScaleGuide() {
  if (_scaleGuideActive) {
    clearInterval(_scaleGuidePollInterval);
    _scaleGuidePollInterval = null;
    _scaleGuideStep = 0;
    await fetch('/api/scale-guide/stop', { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}' });
    _scaleGuideActive = false;
    _sgUpdateUi(false, '');
  } else {
    const s = _bgState;
    if (!s?.malts?.length) return;
    const malts = s.malts.map(m => ({ name: m.name, quantity: m.quantity, unit: m.unit || 'g' }));
    const res = await fetch('/api/scale-guide/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recipe_id: s.r?.id, brew_name: s.r?.name || '', malts }),
    }).then(r => r.json()).catch(() => null);
    if (res?.ok) {
      _scaleGuideActive = true;
      _scaleGuideStep = 1;
      _scaleGuidePollInterval = setInterval(_scaleGuidePollFn, 2000);
      const sg = t('rec.scale_guide_active')
        .replace('${malt}', res.first_malt || '')
        .replace('${kg}', '—')
        .replace('${step}', 1)
        .replace('${total}', res.total || 1);
      _sgUpdateUi(true, sg);
    }
  }
}

function _bgClose() {
  if (_bgFs) _bgFsClose();
  if (_bgState?.timerInterval) clearInterval(_bgState.timerInterval);
  if (_scaleGuidePollInterval) { clearInterval(_scaleGuidePollInterval); _scaleGuidePollInterval = null; }
  if (_scaleGuideActive) {
    fetch('/api/scale-guide/stop', { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}' });
    _scaleGuideActive = false;
    _scaleGuideStep = 0;
  }
  _bgState = null;
  _bgFs = false;
  document.getElementById('modal-brew-guide').classList.remove('open');
  document.getElementById('brew-fs').style.display = 'none';
}

function _bgFmt(sec) {
  return String(Math.floor(sec/60)).padStart(2,'0') + ':' + String(sec%60).padStart(2,'0');
}

function _bgBeep(freq, dur) {
  try {
    const ctx = new (window.AudioContext||window.webkitAudioContext)();
    const osc = ctx.createOscillator(), gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    osc.frequency.value = freq||880;
    gain.gain.setValueAtTime(0.25, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime+(dur||0.4));
    osc.start(); osc.stop(ctx.currentTime+(dur||0.4));
  } catch(e) {}
}

function _bgGoStep(n) {
  if (!_bgState) return;
  if (_bgState.timerInterval) clearInterval(_bgState.timerInterval);
  _bgState.timerInterval = null;
  _bgState.timerRunning = false;
  _bgState.step = n;
  _bgState.timerSec = 0;
  _bgState.timerTarget = [0, 0, _bgState.mashTime*60, _bgState.boilTime*60, 0][n] || 0;
  _bgState.notified = new Set();
  _bgRenderAll();
}

function _bgStartTimer() {
  const s = _bgState;
  if (!s || s.timerRunning) return;
  s.timerRunning = true;
  s.timerInterval = setInterval(() => {
    s.timerSec++;
    if (s.step === 3) {
      const em = s.timerSec / 60;
      s.boilHops.forEach((h, idx) => {
        const key = `hop-${idx}`;
        const ht = h.hop_type||'ebullition';
        const addAt = ['whirlpool','flameout'].includes(ht) ? s.boilTime : s.boilTime-(h.hop_time??s.boilTime);
        if (!s.notified.has(key) && em >= addAt) {
          s.notified.add(key);
          _bgBeep(660, 0.3);
          setTimeout(() => _bgBeep(880, 0.5), 400);
        }
      });
    }
    if (s.timerTarget > 0) {
      const remaining = s.timerTarget - s.timerSec;
      const stepName = s.step === 2
        ? `Empâtage (${s.mashTime} min)`
        : `Ébullition (${s.boilTime} min)`;
      if (remaining === 300 && !s.notified.has('tg_warn')) {
        s.notified.add('tg_warn');
        _tgNotifyTimer(stepName, 'warning');
      }
      if (s.timerSec >= s.timerTarget) {
        s.timerSec = s.timerTarget;
        clearInterval(s.timerInterval); s.timerInterval = null; s.timerRunning = false;
        _bgBeep(880,0.3); setTimeout(()=>_bgBeep(660,0.3),350); setTimeout(()=>_bgBeep(880,0.5),700);
        if (!s.notified.has('tg_done')) {
          s.notified.add('tg_done');
          _tgNotifyTimer(stepName, 'done');
        }
      }
    }
    _bgRenderTimer();
  }, 1000);
  _bgRenderTimer();
}

function _bgPauseTimer() {
  const s = _bgState; if (!s) return;
  clearInterval(s.timerInterval); s.timerInterval = null; s.timerRunning = false;
  _bgRenderTimer();
}

function _bgResetTimer() {
  const s = _bgState; if (!s) return;
  if (s.timerInterval) clearInterval(s.timerInterval);
  s.timerInterval = null; s.timerRunning = false; s.timerSec = 0; s.notified = new Set();
  _bgRenderTimer();
}

function _bgToggleCheck(key) {
  const s = _bgState; if (!s) return;
  s.checked[key] = !s.checked[key];
  const el = document.querySelector(`[data-bgck="${key}"]`);
  if (!el) return;
  const checked = s.checked[key];
  el.style.background = checked ? 'rgba(74,222,128,.08)' : 'var(--card2)';
  el.style.borderColor = checked ? 'var(--hop)' : 'var(--border)';
  const box = el.querySelector('.bg-cbbox');
  if (box) { box.style.background = checked?'var(--hop)':'transparent'; box.style.borderColor = checked?'var(--hop)':'var(--muted)'; }
  const icon = el.querySelector('.bg-cbicon');
  if (icon) icon.textContent = checked ? '✓' : '';
  const lbl = el.querySelector('.bg-cblbl');
  if (lbl) { lbl.style.opacity = checked?'.5':'1'; lbl.style.textDecoration = checked?'line-through':'none'; }
}

function _bgCheckItem(key, label) {
  const checked = _bgState?.checked[key]||false;
  return `<div data-bgck="${key}" onclick="_bgToggleCheck('${key}')" style="display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;margin-bottom:6px;cursor:pointer;background:${checked?'rgba(74,222,128,.08)':'var(--card2)'};border:1px solid ${checked?'var(--hop)':'var(--border)'};transition:all .2s">
    <div class="bg-cbbox" style="width:22px;height:22px;border-radius:5px;border:2px solid ${checked?'var(--hop)':'var(--muted)'};background:${checked?'var(--hop)':'transparent'};display:flex;align-items:center;justify-content:center;flex-shrink:0">
      <span class="bg-cbicon" style="color:white;font-size:.85rem;font-weight:700">${checked?'✓':''}</span>
    </div>
    <div class="bg-cblbl" style="flex:1;opacity:${checked?.5:1};text-decoration:${checked?'line-through':'none'}">${label}</div>
  </div>`;
}

function _bgTimerBtns(s) {
  return s.timerRunning
    ? `<button class="btn btn-ghost" onclick="_bgPauseTimer()"><i class="fas fa-pause"></i> ${t('rec.guide_pause')}</button>`
    : `<button class="btn btn-primary" onclick="_bgStartTimer()"><i class="fas fa-play"></i> ${t('rec.guide_start')}</button>`;
}

// ── Steps HTML ────────────────────────────────────────────────────────────────
function _bgHtmlPrep() {
  const s = _bgState;
  let h = `<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:18px">`;
  [[s.wv.mash+' L', t('rec.guide_water_mash')],[s.wv.sparge+' L',t('rec.guide_water_sparge')],
   [s.wv.preboil+' L',t('rec.guide_water_preboil')],[s.wv.total+' L',t('rec.guide_water_total')]
  ].forEach(([v,l])=>{
    h+=`<div style="background:var(--card2);border-radius:8px;padding:10px 14px;display:flex;align-items:center;gap:10px"><span style="font-size:1.15rem;font-weight:700;color:var(--info)">${v}</span><span style="font-size:.78rem;color:var(--muted)">${l}</span></div>`;
  });
  h += '</div>';
  if (s.malts.length) {
    h += `<div style="font-weight:600;margin-bottom:8px;color:var(--malt)"><i class="fas fa-wheat-awn"></i> ${t('rec.guide_malts')}</div>`;
    s.malts.forEach((m,i) => {
      const qty = m.unit==='kg' ? `${m.quantity} kg` : `${m.quantity} g`;
      h += _bgCheckItem(`malt-${i}`, `<strong>${qty}</strong> — ${esc(m.name)}`);
    });
    const _sgOn = _scaleGuideActive;
    h += `<div style="margin-top:4px;margin-bottom:8px">
      <button id="scale-guide-btn" onclick="_bgToggleScaleGuide()" class="btn btn-ghost" style="font-size:.82rem;gap:6px;color:${_sgOn?'var(--hop)':'#f0883e'};border-color:${_sgOn?'rgba(74,222,128,.35)':'rgba(240,136,62,.35)'}">
        <i class="fas fa-weight-scale"></i>
        <span id="scale-guide-label">${_sgOn ? t('rec.scale_guide_stop') : t('rec.scale_guide_start')}</span>
      </button>
      <div id="scale-guide-status" style="font-size:.8rem;color:var(--muted);margin-top:5px;display:none"></div>
    </div>`;
    h += '<div style="height:8px"></div>';
  }
  const allHops = [...s.boilHops, ...s.dryHops];
  if (allHops.length) {
    h += `<div style="font-weight:600;margin-bottom:8px;color:var(--hop)"><i class="fas fa-leaf"></i> ${t('rec.guide_hops')}</div>`;
    allHops.forEach((hop,i) => {
      const qty = hop.unit==='kg' ? `${hop.quantity*1000} g` : `${hop.quantity} ${hop.unit}`;
      const info = hop.hop_type==='dryhop' ? '(Dry Hop)'
        : hop.hop_type==='whirlpool' ? '(Whirlpool)'
        : hop.hop_type==='flameout'  ? '(Flameout)'
        : `T-${hop.hop_time??'?'} min`;
      h += _bgCheckItem(`hop-${i}`, `<strong>${qty}</strong> — ${esc(hop.name)} <span style="color:var(--muted);font-size:.8rem">${info}</span>`);
    });
    h += '<div style="height:12px"></div>';
  }
  if (s.yeasts.length) {
    h += `<div style="font-weight:600;margin-bottom:8px;color:var(--amber)"><i class="fas fa-flask"></i> ${t('rec.guide_yeast')}</div>`;
    s.yeasts.forEach((y,i) => h += _bgCheckItem(`yeast-${i}`, `<strong>${y.quantity} ${y.unit}</strong> — ${esc(y.name)}`));
    h += '<div style="height:12px"></div>';
  }
  if (s.others.length) {
    h += `<div style="font-weight:600;margin-bottom:8px;color:var(--muted)"><i class="fas fa-mortar-pestle"></i> ${t('rec.guide_others')}</div>`;
    s.others.forEach((o,i) => h += _bgCheckItem(`other-${i}`, `<strong>${o.quantity} ${o.unit}</strong> — ${esc(o.name)}`));
  }
  return h;
}

function _bgHtmlMill() {
  const s = _bgState;
  const totalKg = s.malts.reduce((sum,m) => sum+(m.unit==='kg'?m.quantity:m.quantity/1000), 0);
  let h = `<div style="text-align:center;padding:10px 0 18px">
    <div style="font-size:2.5rem;margin-bottom:8px">🌾</div>
    <div style="font-size:1.1rem;font-weight:600;margin-bottom:4px">${t('rec.guide_mill_title')}</div>
    <div style="color:var(--muted);font-size:.9rem">${totalKg.toFixed(2)} kg ${t('rec.guide_mill_total')}</div>
  </div>`;
  s.malts.forEach((m,i) => {
    const qty = m.unit==='kg' ? `${m.quantity} kg` : `${m.quantity} g`;
    h += _bgCheckItem(`mill-${i}`, `<strong>${qty}</strong> — ${esc(m.name)}`);
  });
  h += `<div style="margin-top:16px;padding:12px 14px;background:var(--card2);border-radius:8px;border-left:3px solid var(--malt);font-size:.87rem;line-height:1.5">
    <i class="fas fa-circle-info" style="color:var(--malt)"></i> ${t('rec.guide_mill_tip')}
  </div>`;
  return h;
}

function _bgHtmlMash() {
  const s = _bgState;
  const rem = Math.max(0, s.timerTarget - s.timerSec);
  const pct = s.timerTarget > 0 ? Math.min(100, s.timerSec/s.timerTarget*100) : 0;
  return `<div style="text-align:center;padding:10px 0 14px">
    <div style="font-size:3rem;font-weight:700;letter-spacing:.04em;color:var(--primary);font-variant-numeric:tabular-nums" id="bg-mash-time">${_bgFmt(rem)}</div>
    <div style="color:var(--muted);margin-top:4px">${s.mashTime} min · ${s.mashTemp}°C</div>
    <div style="height:6px;background:var(--border);border-radius:3px;margin:12px auto;max-width:320px;overflow:hidden">
      <div id="bg-mash-prog" style="height:100%;width:${pct}%;background:var(--primary);transition:width .8s linear;border-radius:3px"></div>
    </div>
    <div style="display:flex;gap:10px;justify-content:center;margin-top:8px" id="bg-mash-btns">
      ${_bgTimerBtns(s)}
      <button class="btn btn-ghost" onclick="_bgResetTimer()"><i class="fas fa-rotate-left"></i> ${t('rec.guide_reset')}</button>
    </div>
  </div>
  <div style="background:var(--card2);border-radius:8px;padding:14px 16px;margin-top:8px">
    <div style="font-weight:600;margin-bottom:10px"><i class="fas fa-temperature-high" style="color:var(--amber)"></i> ${t('rec.guide_mash_params')}</div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;text-align:center">
      <div><div style="font-size:1.4rem;font-weight:700;color:var(--amber)">${s.mashTemp}°C</div><div style="font-size:.75rem;color:var(--muted)">${t('rec.guide_mash_temp')}</div></div>
      <div><div style="font-size:1.4rem;font-weight:700;color:var(--primary)">${s.mashTime} min</div><div style="font-size:.75rem;color:var(--muted)">${t('rec.guide_mash_time')}</div></div>
      <div><div style="font-size:1.4rem;font-weight:700;color:var(--info)">${s.wv.mash} L</div><div style="font-size:.75rem;color:var(--muted)">${t('rec.guide_water_mash')}</div></div>
    </div>
  </div>`;
}

function _bgBoilScheduleHtml() {
  const s = _bgState;
  const em = s.timerSec / 60;
  let h = `<div style="font-weight:600;margin-bottom:10px;color:var(--hop)"><i class="fas fa-leaf"></i> ${t('rec.guide_hop_schedule')}</div>`;
  if (!s.boilHops.length) return h + `<div style="color:var(--muted);font-size:.9rem;padding:8px 0">${t('rec.guide_no_hops')}</div>`;
  s.boilHops.forEach((hop, idx) => {
    const ht = hop.hop_type||'ebullition';
    const addAt = ['whirlpool','flameout'].includes(ht) ? s.boilTime : s.boilTime-(hop.hop_time??s.boilTime);
    const due = em >= addAt;
    const notif = s.notified.has(`hop-${idx}`);
    const remMin = Math.max(0, addAt - em);
    const bg = notif ? 'rgba(74,222,128,.08)' : due ? 'rgba(251,191,36,.15)' : 'var(--card2)';
    const bc = notif ? 'var(--hop)' : due ? 'var(--warning)' : 'var(--border)';
    const emoji = notif ? '✅' : due ? '🔔' : '🌿';
    const timeLabel = notif ? t('rec.guide_hop_added') : due ? `⚡ ${t('rec.guide_hop_now')}` : `T-${Math.ceil(remMin)} min`;
    const timeColor = notif ? 'var(--hop)' : due ? 'var(--warning)' : 'var(--muted)';
    h += `<div style="display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;margin-bottom:6px;background:${bg};border:1px solid ${bc};transition:all .4s">
      <div style="font-size:1.2rem;flex-shrink:0">${emoji}</div>
      <div style="flex:1">
        <div style="font-weight:600">${esc(hop.name)}</div>
        <div style="font-size:.78rem;color:var(--muted)">${hop.quantity} ${hop.unit}${hop.alpha?' · '+hop.alpha+'% AA':''}</div>
      </div>
      <div style="font-size:.85rem;font-weight:600;color:${timeColor}">${timeLabel}</div>
    </div>`;
  });
  return h;
}

function _bgHtmlBoil() {
  const s = _bgState;
  const rem = Math.max(0, s.timerTarget - s.timerSec);
  const pct = s.timerTarget > 0 ? Math.min(100, s.timerSec/s.timerTarget*100) : 0;
  return `<div style="text-align:center;padding:8px 0 12px">
    <div style="font-size:3rem;font-weight:700;letter-spacing:.04em;color:var(--amber);font-variant-numeric:tabular-nums" id="bg-boil-time">${_bgFmt(rem)}</div>
    <div style="color:var(--muted);margin-top:2px">${s.boilTime} min total</div>
    <div style="height:6px;background:var(--border);border-radius:3px;margin:10px auto;max-width:320px;overflow:hidden">
      <div id="bg-boil-prog" style="height:100%;width:${pct}%;background:var(--amber);transition:width .8s linear;border-radius:3px"></div>
    </div>
    <div style="display:flex;gap:10px;justify-content:center;margin-top:6px" id="bg-boil-btns">
      ${_bgTimerBtns(s)}
      <button class="btn btn-ghost" onclick="_bgResetTimer()"><i class="fas fa-rotate-left"></i> ${t('rec.guide_reset')}</button>
    </div>
  </div>
  <div id="bg-boil-sched">${_bgBoilScheduleHtml()}</div>`;
}

function _bgHtmlPitch() {
  const s = _bgState;
  let h = `<div style="text-align:center;padding:10px 0 16px">
    <div style="font-size:2.5rem;margin-bottom:8px">🌡️</div>
    <div style="font-size:1.05rem;font-weight:600;margin-bottom:4px">${t('rec.guide_cool_title')}</div>
    <div style="font-size:2rem;font-weight:700;color:var(--info)">${s.fermTemp}°C</div>
    <div style="color:var(--muted);font-size:.85rem;margin-top:4px">${t('rec.guide_ferm_time')} : ${s.r.ferm_time||14} ${t('rec.ing_days')}</div>
  </div>`;
  if (s.yeasts.length) {
    h += `<div style="font-weight:600;margin-bottom:8px;color:var(--amber)"><i class="fas fa-flask"></i> ${t('rec.guide_pitch_yeast')}</div>`;
    s.yeasts.forEach((y,i) => h += _bgCheckItem(`lpitch-${i}`, `<strong>${y.quantity} ${y.unit}</strong> — ${esc(y.name)}`));
    h += '<div style="height:12px"></div>';
  }
  if (s.dryHops.length) {
    h += `<div style="font-weight:600;margin-bottom:8px;color:var(--hop)"><i class="fas fa-leaf"></i> ${t('rec.hop_dryhop')}</div>`;
    s.dryHops.forEach((dh,i) => {
      const days = dh.hop_days != null ? ` — ${dh.hop_days} ${t('rec.ing_days')}` : '';
      h += _bgCheckItem(`ldryhop-${i}`, `<strong>${dh.quantity} ${dh.unit}</strong> — ${esc(dh.name)}${days}`);
    });
    h += '<div style="height:12px"></div>';
  }
  h += `<div style="padding:12px 14px;background:var(--card2);border-radius:8px;border-left:3px solid var(--hop);font-size:.87rem;line-height:1.5;margin-bottom:12px">
    <i class="fas fa-circle-info" style="color:var(--hop)"></i> ${t('rec.guide_og_reminder')}
  </div>
  <button class="btn btn-ghost" onclick="openPrimingCalc()" style="width:100%;color:var(--info);border-color:rgba(99,179,237,.4)"><i class="fas fa-flask"></i> ${t('rec.priming_btn')}</button>`;
  return h;
}

// ── Render orchestration ──────────────────────────────────────────────────────
let _bgFs = false;

function _bgRenderAll() {
  if (_bgFs) { _bgFsRenderAll(); return; }
  const s = _bgState; if (!s) return;
  const STEPS = [
    t('rec.guide_step_prep'), t('rec.guide_step_mill'),
    t('rec.guide_step_mash'), t('rec.guide_step_boil'), t('rec.guide_step_pitch'),
  ];
  const ICONS = ['⚖️','🌾','🌡️','🔥','🫙'];
  document.getElementById('bg-title').textContent = `${ICONS[s.step]} ${esc(s.r.name)} — ${STEPS[s.step]}`;

  // Progress bar
  let bar = '<div style="display:flex;align-items:center;gap:0">';
  STEPS.forEach((lbl, i) => {
    if (i > 0) bar += `<div style="flex:1;height:2px;background:${i<=s.step?'var(--primary)':'var(--border)'}"></div>`;
    bar += `<div onclick="_bgGoStep(${i})" title="${lbl}" style="cursor:pointer;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.75rem;font-weight:700;flex-shrink:0;background:${i<s.step?'var(--primary)':i===s.step?'var(--primary)':'var(--card2)'};color:${i<=s.step?'white':'var(--muted)'};border:2px solid ${i<=s.step?'var(--primary)':'var(--border)'};transition:all .2s">${i<s.step?'✓':i+1}</div>`;
  });
  bar += '</div><div style="display:flex;margin-top:6px">';
  STEPS.forEach((lbl, i) => {
    bar += `<div style="flex:${i===0?0.5:i===STEPS.length-1?0.5:1};text-align:center;font-size:.65rem;color:${i===s.step?'var(--primary)':'var(--muted)'};font-weight:${i===s.step?700:400};overflow:hidden;white-space:nowrap">${lbl}</div>`;
  });
  bar += '</div>';
  document.getElementById('bg-steps-bar').innerHTML = bar;

  // Content
  const contentFns = [_bgHtmlPrep, _bgHtmlMill, _bgHtmlMash, _bgHtmlBoil, _bgHtmlPitch];
  document.getElementById('bg-content').innerHTML = contentFns[s.step]();

  // Footer
  const TOTAL = STEPS.length;
  let foot = '<div style="display:flex;justify-content:space-between;align-items:center;width:100%;gap:8px">';
  foot += s.step > 0
    ? `<button class="btn btn-ghost" onclick="_bgGoStep(${s.step-1})"><i class="fas fa-arrow-left"></i> ${t('common.back')}</button>`
    : `<button class="btn btn-ghost" onclick="_bgClose()"><i class="fas fa-xmark"></i> ${t('common.close')}</button>`;
  foot += `<span style="font-size:.8rem;color:var(--muted)">${s.step+1} / ${TOTAL}</span>`;
  foot += s.step < TOTAL-1
    ? `<button class="btn btn-primary" onclick="_bgGoStep(${s.step+1})">${t('common.next')} <i class="fas fa-arrow-right"></i></button>`
    : `<button class="btn btn-primary" onclick="_bgClose()"><i class="fas fa-check"></i> ${t('rec.guide_done')}</button>`;
  foot += '</div>';
  document.getElementById('bg-footer').innerHTML = foot;
}

function _bgRenderTimer() {
  if (_bgFs) { _bgFsRenderTimer(); return; }
  const s = _bgState; if (!s) return;
  const rem = Math.max(0, s.timerTarget - s.timerSec);
  const pct = s.timerTarget > 0 ? Math.min(100, s.timerSec/s.timerTarget*100) : 0;
  if (s.step === 2) {
    const te = document.getElementById('bg-mash-time');
    const pe = document.getElementById('bg-mash-prog');
    const be = document.getElementById('bg-mash-btns');
    if (te) te.textContent = _bgFmt(rem);
    if (pe) pe.style.width = pct + '%';
    if (be) be.innerHTML = _bgTimerBtns(s) + `<button class="btn btn-ghost" onclick="_bgResetTimer()"><i class="fas fa-rotate-left"></i> ${t('rec.guide_reset')}</button>`;
  } else if (s.step === 3) {
    const te = document.getElementById('bg-boil-time');
    const pe = document.getElementById('bg-boil-prog');
    const be = document.getElementById('bg-boil-btns');
    if (te) te.textContent = _bgFmt(rem);
    if (pe) pe.style.width = pct + '%';
    if (be) be.innerHTML = _bgTimerBtns(s) + `<button class="btn btn-ghost" onclick="_bgResetTimer()"><i class="fas fa-rotate-left"></i> ${t('rec.guide_reset')}</button>`;
    const se = document.getElementById('bg-boil-sched');
    if (se) se.innerHTML = _bgBoilScheduleHtml();
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// ── GUIDE BRASSAGE — MODE PLEIN ÉCRAN ────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════

function _bgFsOpen() {
  if (!_bgState) return;
  _bgFs = true;
  document.getElementById('brew-fs').style.display = 'flex';
  document.getElementById('modal-brew-guide').style.opacity = '0';
  document.getElementById('modal-brew-guide').style.pointerEvents = 'none';
  try { document.documentElement.requestFullscreen?.(); } catch(e) {}
  window.addEventListener('resize', _bgFsOnResize);
  _bgFsRenderAll();
}

function _bgFsClose() {
  _bgFs = false;
  document.getElementById('brew-fs').style.display = 'none';
  const mg = document.getElementById('modal-brew-guide');
  mg.style.opacity = ''; mg.style.pointerEvents = '';
  try { document.fullscreenElement && document.exitFullscreen?.(); } catch(e) {}
  window.removeEventListener('resize', _bgFsOnResize);
  _bgRenderAll();
}

let _bgFsResizeTimer = null;
function _bgFsOnResize() {
  clearTimeout(_bgFsResizeTimer);
  _bgFsResizeTimer = setTimeout(_bgFsRenderAll, 120);
}

// Shared button style factory
function _bfsBtn(label, onclick, variant = 'ghost') {
  const bg  = variant === 'primary' ? 'var(--primary)' : variant === 'success' ? 'var(--success)' : '#ffffff14';
  const bc  = variant === 'ghost' ? '#ffffff22' : 'transparent';
  const col = variant === 'ghost' ? '#ccc' : '#fff';
  return `<button onclick="${onclick}" style="flex:1;height:clamp(52px,8vh,72px);font-size:clamp(.95rem,2.2vw,1.4rem);font-weight:700;border-radius:14px;cursor:pointer;border:1px solid ${bc};background:${bg};color:${col};display:flex;align-items:center;justify-content:center;gap:10px;padding:0 clamp(12px,2.5vw,28px)">${label}</button>`;
}

function _bgFsTimerControls(s) {
  const startPause = s.timerRunning
    ? _bfsBtn(`<i class="fas fa-pause"></i> ${t('rec.guide_pause')}`, '_bgPauseTimer()')
    : _bfsBtn(`<i class="fas fa-play"></i> ${t('rec.guide_start')}`, '_bgStartTimer()', 'primary');
  return `<div id="bfs-timer-btns" style="display:flex;gap:12px;justify-content:center;width:min(520px,90%);margin:0 auto">${startPause}${_bfsBtn(`<i class="fas fa-rotate-left"></i> ${t('rec.guide_reset')}`, '_bgResetTimer()')}</div>`;
}

function _bgFsHtmlTimer(color) {
  const s = _bgState;
  const rem = Math.max(0, s.timerTarget - s.timerSec);
  const pct = s.timerTarget > 0 ? Math.min(100, s.timerSec / s.timerTarget * 100) : 0;
  const done = s.timerTarget > 0 && s.timerSec >= s.timerTarget;
  return `
    <div style="text-align:center;width:100%;display:flex;flex-direction:column;align-items:center;gap:clamp(8px,1.5vh,20px)">
      <div id="bfs-timer" style="font-size:clamp(6rem,20vw,18rem);font-weight:900;letter-spacing:.03em;color:${done?'var(--success)':color};line-height:1;font-variant-numeric:tabular-nums;text-shadow:0 0 60px ${color}44">${_bgFmt(rem)}</div>
      <div style="height:clamp(8px,1.2vh,16px);background:#1a1a22;border-radius:99px;width:min(640px,90%);overflow:hidden">
        <div id="bfs-prog" style="height:100%;width:${pct.toFixed(2)}%;background:${color};border-radius:99px;transition:width .8s linear"></div>
      </div>
      ${_bgFsTimerControls(s)}
    </div>`;
}

function _bgFsHtmlMash() {
  const s = _bgState;
  return `
    ${_bgFsHtmlTimer('#3b82f6')}
    <div style="display:flex;gap:clamp(16px,4vw,48px);justify-content:center;margin-top:clamp(16px,3vh,40px);flex-wrap:wrap">
      ${[
        [s.mashTemp + '°C', t('rec.guide_mash_temp'), 'var(--amber)'],
        [s.mashTime + ' min', t('rec.guide_mash_time'), '#3b82f6'],
        [s.wv.mash + ' L', t('rec.guide_water_mash'), '#60a5fa'],
        [s.wv.sparge + ' L', t('rec.guide_water_sparge'), '#818cf8'],
      ].map(([val, lbl, col]) => `<div style="text-align:center">
        <div style="font-size:clamp(2rem,5vw,4.5rem);font-weight:800;color:${col}">${val}</div>
        <div style="font-size:clamp(.7rem,1.5vw,1.1rem);color:#555;margin-top:4px">${lbl}</div>
      </div>`).join('')}
    </div>`;
}

function _bgFsHtmlBoil() {
  const s = _bgState;
  const em = s.timerSec / 60;
  let schedHtml = '';
  if (s.boilHops.length) {
    schedHtml = `<div style="width:min(760px,95%);margin:clamp(12px,2vh,24px) auto 0;display:flex;flex-direction:column;gap:10px">`;
    s.boilHops.forEach((hop, idx) => {
      const ht     = hop.hop_type || 'ebullition';
      const addAt  = ['whirlpool','flameout'].includes(ht) ? s.boilTime : s.boilTime - (hop.hop_time ?? s.boilTime);
      const due    = em >= addAt;
      const notif  = s.notified.has(`hop-${idx}`);
      const remMin = Math.max(0, addAt - em);
      const bg     = notif ? '#052e16' : due ? '#422006' : '#0f172a';
      const bc     = notif ? '#16a34a' : due ? '#f59e0b' : '#1e293b';
      const emoji  = notif ? '✅' : due ? '🔔' : '🌿';
      const timeLbl= notif ? t('rec.guide_hop_added') : due ? `⚡ ${t('rec.guide_hop_now')}` : `T‑${Math.ceil(remMin)} min`;
      const timeCol= notif ? '#22c55e' : due ? '#f59e0b' : '#475569';
      const idKey  = `bfs-hop-${idx}`;
      schedHtml += `<div id="${idKey}" style="display:flex;align-items:center;gap:clamp(10px,2vw,20px);padding:clamp(10px,1.5vh,18px) clamp(14px,2vw,24px);border-radius:12px;background:${bg};border:1px solid ${bc};transition:all .4s">
        <div style="font-size:clamp(1.5rem,3vw,2.5rem);flex-shrink:0">${emoji}</div>
        <div style="flex:1;min-width:0">
          <div style="font-size:clamp(1rem,2.5vw,2rem);font-weight:700;color:#fff">${esc(hop.name)}</div>
          <div style="font-size:clamp(.7rem,1.5vw,1.2rem);color:#64748b">${hop.quantity} ${hop.unit}${hop.alpha ? ' · ' + hop.alpha + '% AA' : ''}</div>
        </div>
        <div style="font-size:clamp(1rem,2.5vw,1.8rem);font-weight:800;color:${timeCol};white-space:nowrap">${timeLbl}</div>
      </div>`;
    });
    schedHtml += '</div>';
  }
  return `${_bgFsHtmlTimer('var(--amber)')}${schedHtml}`;
}

function _bgFsCheckItem(key, mainHtml, subHtml = '') {
  const checked = _bgState?.checked[key] || false;
  const bg = checked ? '#052e16' : '#0f172a';
  const bc = checked ? '#16a34a' : '#1e293b';
  return `<div data-bgck="${key}" onclick="_bgToggleCheck('${key}')" style="display:flex;align-items:center;gap:clamp(12px,2vw,20px);padding:clamp(12px,1.8vh,22px) clamp(14px,2vw,24px);border-radius:12px;margin-bottom:10px;cursor:pointer;background:${bg};border:1px solid ${bc};transition:all .2s">
    <div class="bg-cbbox" style="width:clamp(28px,4vw,42px);height:clamp(28px,4vw,42px);border-radius:8px;border:2px solid ${checked?'#16a34a':'#334155'};background:${checked?'#16a34a':'transparent'};display:flex;align-items:center;justify-content:center;flex-shrink:0">
      <span class="bg-cbicon" style="color:white;font-size:clamp(.9rem,2vw,1.5rem);font-weight:900">${checked ? '✓' : ''}</span>
    </div>
    <div style="flex:1;min-width:0">
      <div class="bg-cblbl" style="font-size:clamp(1rem,2.5vw,2rem);font-weight:700;color:${checked?'#475569':'#fff'};text-decoration:${checked?'line-through':'none'}">${mainHtml}</div>
      ${subHtml ? `<div style="font-size:clamp(.7rem,1.5vw,1.1rem);color:#475569;margin-top:3px">${subHtml}</div>` : ''}
    </div>
  </div>`;
}

function _bgFsHtmlPrep() {
  const s = _bgState;
  let h = `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(clamp(140px,25vw,220px),1fr));gap:12px;margin-bottom:clamp(16px,3vh,32px);width:100%">`;
  [[s.wv.mash+' L', t('rec.guide_water_mash'), '#3b82f6'],
   [s.wv.sparge+' L', t('rec.guide_water_sparge'), '#818cf8'],
   [s.wv.preboil+' L', t('rec.guide_water_preboil'), '#60a5fa'],
   [s.wv.total+' L', t('rec.guide_water_total'), '#38bdf8'],
  ].forEach(([v,l,c]) => {
    h += `<div style="background:#0f172a;border:1px solid #1e293b;border-radius:12px;padding:clamp(12px,2vh,22px);text-align:center">
      <div style="font-size:clamp(1.5rem,4vw,3.5rem);font-weight:800;color:${c}">${v}</div>
      <div style="font-size:clamp(.7rem,1.5vw,1rem);color:#64748b;margin-top:4px">${l}</div>
    </div>`;
  });
  h += '</div><div style="width:100%">';
  // Malts — section spéciale avec bouton balance guidée
  if (s.malts.length) {
    const _sgOn = _scaleGuideActive;
    h += `<div style="font-size:clamp(.9rem,2vw,1.5rem);font-weight:700;color:var(--amber);margin:clamp(10px,1.5vh,18px) 0 8px">🌾 ${t('rec.guide_malts')}</div>`;
    s.malts.forEach((m, i) => {
      const qty = m.unit==='kg' ? `${m.quantity} kg` : `${m.quantity} ${m.unit}`;
      h += _bgFsCheckItem(`malt-${i}`, `${qty} — ${esc(m.name)}`);
    });
    h += `<div style="margin-top:clamp(8px,1.5vh,16px);margin-bottom:clamp(10px,2vh,20px)">
      <button id="bfs-scale-btn" onclick="_bgToggleScaleGuide()" style="display:inline-flex;align-items:center;gap:10px;padding:clamp(10px,1.5vh,16px) clamp(16px,2.5vw,28px);border-radius:12px;border:1px solid ${_sgOn?'rgba(74,222,128,.4)':'rgba(240,136,62,.35)'};background:${_sgOn?'rgba(74,222,128,.08)':'rgba(240,136,62,.08)'};color:${_sgOn?'var(--hop)':'#f0883e'};font-size:clamp(.9rem,2vw,1.5rem);font-weight:600;cursor:pointer">
        <i class="fas fa-weight-scale"></i>
        <span id="bfs-scale-lbl">${_sgOn ? t('rec.scale_guide_stop') : t('rec.scale_guide_start')}</span>
      </button>
      <div id="bfs-scale-status" style="font-size:clamp(.75rem,1.5vw,1.1rem);color:#64748b;margin-top:8px;display:none"></div>
    </div>`;
  }
  // Autres ingrédients
  [[[...s.boilHops,...s.dryHops], 'hop', '🍃', t('rec.guide_hops'), '#22c55e'],
   [s.yeasts, 'yeast', '🧫', t('rec.guide_yeast'), '#f59e0b'],
   [s.others, 'other', '🧪', t('rec.guide_others'), '#94a3b8'],
  ].forEach(([arr, pfx, icon, lbl, col]) => {
    if (!arr.length) return;
    h += `<div style="font-size:clamp(.9rem,2vw,1.5rem);font-weight:700;color:${col};margin:clamp(10px,1.5vh,18px) 0 8px">${icon} ${lbl}</div>`;
    arr.forEach((item, i) => {
      const qty = item.unit==='kg' ? `${item.quantity} kg` : `${item.quantity} ${item.unit}`;
      h += _bgFsCheckItem(`${pfx}-${i}`, `${qty} — ${esc(item.name)}`);
    });
  });
  h += '</div>';
  return h;
}

function _bgFsHtmlMill() {
  const s = _bgState;
  const totalKg = s.malts.reduce((sum,m) => sum+(m.unit==='kg'?m.quantity:m.quantity/1000), 0);
  let h = `<div style="text-align:center;margin-bottom:clamp(16px,3vh,32px);width:100%">
    <div style="font-size:clamp(3rem,8vw,7rem)">🌾</div>
    <div style="font-size:clamp(1.5rem,4vw,3.5rem);font-weight:800;color:#fff;margin-top:8px">${totalKg.toFixed(2)} kg</div>
    <div style="font-size:clamp(.8rem,1.8vw,1.3rem);color:#64748b">${t('rec.guide_mill_total')}</div>
  </div><div style="width:100%">`;
  s.malts.forEach((m,i) => {
    const qty = m.unit==='kg' ? `${m.quantity} kg` : `${m.quantity} g`;
    h += _bgFsCheckItem(`mill-${i}`, `${qty} — ${esc(m.name)}`, m.ebc ? `EBC ${m.ebc}` : '');
  });
  h += '</div>';
  return h;
}

function _bgFsHtmlPitch() {
  const s = _bgState;
  let h = `<div style="text-align:center;margin-bottom:clamp(16px,3vh,32px);width:100%">
    <div style="font-size:clamp(3rem,8vw,7rem)">🌡️</div>
    <div style="font-size:clamp(2rem,6vw,5rem);font-weight:900;color:#3b82f6;margin:8px 0">${s.fermTemp}°C</div>
    <div style="font-size:clamp(.8rem,1.8vw,1.3rem);color:#64748b">${t('rec.guide_cool_title')} · ${t('rec.guide_ferm_time')} ${s.r.ferm_time||14} j</div>
  </div><div style="width:100%">`;
  if (s.yeasts.length) {
    h += `<div style="font-size:clamp(.9rem,2vw,1.5rem);font-weight:700;color:var(--amber);margin-bottom:8px">🧫 ${t('rec.guide_yeast')}</div>`;
    s.yeasts.forEach((y,i) => h += _bgFsCheckItem(`lpitch-${i}`, `${y.quantity} ${y.unit} — ${esc(y.name)}`));
  }
  if (s.dryHops.length) {
    h += `<div style="font-size:clamp(.9rem,2vw,1.5rem);font-weight:700;color:#22c55e;margin:clamp(10px,1.5vh,18px) 0 8px">🍃 ${t('rec.hop_dryhop')}</div>`;
    s.dryHops.forEach((dh,i) => {
      const days = dh.hop_days != null ? ` — ${dh.hop_days} j` : '';
      h += _bgFsCheckItem(`ldryhop-${i}`, `${dh.quantity} ${dh.unit} — ${esc(dh.name)}${days}`);
    });
  }
  h += '</div>';
  return h;
}

// ── Mode portrait mobile ──────────────────────────────────────────────────────
function _bgIsMobilePortrait() {
  return _bgFs && window.innerWidth <= 600 && window.innerHeight > window.innerWidth;
}

function _bgFsPortraitNextHopHtml() {
  const s = _bgState;
  if (!s.boilHops.length) return `<div style="padding:14px;text-align:center;color:#475569;font-size:.9rem">${t('rec.guide_no_hops')}</div>`;
  const em = s.timerSec / 60;
  let nextIdx = -1;
  for (let i = 0; i < s.boilHops.length; i++) {
    if (!s.notified.has(`hop-${i}`)) { nextIdx = i; break; }
  }
  if (nextIdx === -1) {
    return `<div id="bfs-p-nexthop-wrap"><div style="padding:16px 18px;background:#052e16;border:2px solid #16a34a;border-radius:14px;text-align:center">
      <span style="font-size:1.1rem;font-weight:700;color:#22c55e">✅ ${t('rec.guide_hops')} — ${t('rec.guide_hop_added')}</span>
    </div></div>`;
  }
  const hop = s.boilHops[nextIdx];
  const ht = hop.hop_type || 'ebullition';
  const addAt = ['whirlpool','flameout'].includes(ht) ? s.boilTime : s.boilTime - (hop.hop_time ?? s.boilTime);
  const due = em >= addAt;
  const remMin = Math.max(0, addAt - em);
  const timeLbl = due ? `⚡ ${t('rec.guide_hop_now')}` : `T‑${Math.ceil(remMin)} min`;
  const timeCol = due ? '#f59e0b' : '#94a3b8';
  const bg = due ? 'rgba(245,158,11,.08)' : '#0f172a';
  const bc = due ? '#f59e0b55' : '#1e293b';
  return `<div id="bfs-p-nexthop-wrap"><div style="padding:16px 18px;background:${bg};border:2px solid ${bc};border-radius:14px;transition:background .4s,border-color .4s">
    <div style="font-size:.65rem;text-transform:uppercase;letter-spacing:.1em;color:#475569;margin-bottom:6px">${t('rec.guide_next_hop')}</div>
    <div style="display:flex;align-items:center;justify-content:space-between;gap:12px">
      <div style="min-width:0">
        <div style="font-size:1.6rem;font-weight:800;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(hop.name)}</div>
        <div style="font-size:.85rem;color:#64748b;margin-top:2px">${hop.quantity} ${hop.unit}${hop.alpha ? ' · ' + hop.alpha + '% AA' : ''}</div>
      </div>
      <div style="font-size:2rem;font-weight:900;color:${timeCol};white-space:nowrap;flex-shrink:0">${timeLbl}</div>
    </div>
  </div></div>`;
}

function _bgFsPortraitHtml() {
  const s = _bgState;
  const hasTimer = s.step === 2 || s.step === 3;
  const color = s.step === 2 ? '#3b82f6' : 'var(--amber)';
  const rem  = Math.max(0, s.timerTarget - s.timerSec);
  const pct  = s.timerTarget > 0 ? Math.min(100, s.timerSec / s.timerTarget * 100) : 0;
  const done = s.timerTarget > 0 && s.timerSec >= s.timerTarget;

  if (!hasTimer) {
    const fns = [_bgFsHtmlPrep, _bgFsHtmlMill, null, null, _bgFsHtmlPitch];
    return `<div style="width:100%;display:flex;flex-direction:column;align-items:center">${fns[s.step]()}</div>`;
  }

  let html = `<div style="display:flex;flex-direction:column;width:100%;gap:14px">`;

  // Giant timer
  html += `<div style="text-align:center;padding:4px 0">
    <div id="bfs-p-timer" style="font-size:clamp(4.5rem,18vh,11rem);font-weight:900;line-height:1;letter-spacing:.02em;color:${done?'var(--success)':color};font-variant-numeric:tabular-nums;text-shadow:0 0 48px ${color}44">${_bgFmt(rem)}</div>
    <div style="height:8px;background:#1a1a22;border-radius:99px;width:88%;margin:12px auto 0;overflow:hidden">
      <div id="bfs-p-prog" style="height:100%;width:${pct.toFixed(2)}%;background:${color};border-radius:99px;transition:width .8s linear"></div>
    </div>
  </div>`;

  // Mash: info cards 2×2
  if (s.step === 2) {
    html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
      ${[[s.mashTemp + '°C', t('rec.guide_mash_temp'), color],
         [s.mashTime + ' min', t('rec.guide_mash_time'), '#60a5fa'],
         [s.wv.mash + ' L',   t('rec.guide_water_mash'), '#818cf8'],
         [s.wv.sparge + ' L', t('rec.guide_water_sparge'), '#a78bfa'],
      ].map(([v,l,c]) => `<div style="background:#0f172a;border:1px solid #1e293b;border-radius:12px;padding:10px 14px;text-align:center">
        <div style="font-size:clamp(1.3rem,5vw,2rem);font-weight:800;color:${c}">${v}</div>
        <div style="font-size:.7rem;color:#64748b;margin-top:3px">${l}</div>
      </div>`).join('')}
    </div>`;
  }

  // Boil: next hop card
  if (s.step === 3) html += _bgFsPortraitNextHopHtml();

  html += `</div>`;
  return html;
}

function _bgFsPortraitFooter(s) {
  const STEPS = [t('rec.guide_step_prep'), t('rec.guide_step_mill'), t('rec.guide_step_mash'), t('rec.guide_step_boil'), t('rec.guide_step_pitch')];
  const TOTAL = STEPS.length;
  const hasTimer = s.step === 2 || s.step === 3;
  let foot = `<div style="display:flex;flex-direction:column;gap:8px;width:100%">`;
  if (hasTimer) {
    const playPause = s.timerRunning
      ? _bfsBtn(`<i class="fas fa-pause"></i> ${t('rec.guide_pause')}`, '_bgPauseTimer()')
      : _bfsBtn(`<i class="fas fa-play"></i> ${t('rec.guide_start')}`, '_bgStartTimer()', 'primary');
    foot += `<div id="bfs-p-btn" style="display:flex;gap:10px">${playPause}${_bfsBtn(`<i class="fas fa-rotate-left"></i>`, '_bgResetTimer()')}</div>`;
  }
  const back = s.step > 0
    ? _bfsBtn(`<i class="fas fa-arrow-left"></i>`, `_bgGoStep(${s.step-1})`)
    : _bfsBtn(`<i class="fas fa-xmark"></i>`, '_bgFsClose()');
  const dots = `<div style="display:flex;gap:6px;align-items:center;justify-content:center;flex:1">${[...Array(TOTAL)].map((_,i) => `<span style="width:${i===s.step?10:6}px;height:${i===s.step?10:6}px;border-radius:50%;display:inline-block;background:${i===s.step?'#fff':'#ffffff33'};transition:all .2s"></span>`).join('')}</div>`;
  const fwd = s.step < TOTAL-1
    ? _bfsBtn(`<i class="fas fa-arrow-right"></i>`, `_bgGoStep(${s.step+1})`, 'primary')
    : _bfsBtn(`<i class="fas fa-check"></i>`, '_bgFsClose()', 'success');
  foot += `<div style="display:flex;gap:8px;align-items:center">${back}${dots}${fwd}</div>`;
  foot += `</div>`;
  return foot;
}

function _bgFsRenderAll() {
  const s = _bgState; if (!s) return;
  const STEPS = [t('rec.guide_step_prep'), t('rec.guide_step_mill'), t('rec.guide_step_mash'), t('rec.guide_step_boil'), t('rec.guide_step_pitch')];
  const ICONS  = ['⚖️','🌾','🌡️','🔥','🫙'];

  document.getElementById('bfs-recipe').textContent  = s.r.name;
  document.getElementById('bfs-step').textContent    = `${ICONS[s.step]} ${STEPS[s.step]}`;
  document.getElementById('bfs-stepnum').textContent = `${s.step+1} / ${STEPS.length}`;

  const portrait = _bgIsMobilePortrait();
  const center = document.getElementById('bfs-center');
  center.style.padding = portrait ? '10px 14px' : '';

  if (portrait) {
    center.innerHTML = _bgFsPortraitHtml();
    document.getElementById('bfs-footer').innerHTML = _bgFsPortraitFooter(s);
    return;
  }

  const fns = [_bgFsHtmlPrep, _bgFsHtmlMill, _bgFsHtmlMash, _bgFsHtmlBoil, _bgFsHtmlPitch];
  center.innerHTML = `<div style="width:100%;display:flex;flex-direction:column;align-items:center">${fns[s.step]()}</div>`;

  const TOTAL = STEPS.length;
  let foot = '';
  foot += s.step > 0
    ? _bfsBtn(`<i class="fas fa-arrow-left"></i> ${t('common.back')}`, `_bgGoStep(${s.step-1})`)
    : _bfsBtn(`<i class="fas fa-xmark"></i> ${t('common.close')}`, '_bgFsClose()');
  foot += `<div style="display:flex;gap:8px;align-items:center;justify-content:center;flex:1">${[...Array(TOTAL)].map((_,i) => `<span style="width:${i===s.step?12:8}px;height:${i===s.step?12:8}px;border-radius:50%;display:inline-block;background:${i===s.step?'#fff':'#ffffff33'};transition:all .2s"></span>`).join('')}</div>`;
  foot += s.step < TOTAL-1
    ? _bfsBtn(`${t('common.next')} <i class="fas fa-arrow-right"></i>`, `_bgGoStep(${s.step+1})`, 'primary')
    : _bfsBtn(`<i class="fas fa-check"></i> ${t('rec.guide_done')}`, '_bgFsClose()', 'success');
  document.getElementById('bfs-footer').innerHTML = foot;
}

function _bgFsRenderTimer() {
  const s = _bgState; if (!s) return;
  const rem = Math.max(0, s.timerTarget - s.timerSec);
  const pct = s.timerTarget > 0 ? Math.min(100, s.timerSec / s.timerTarget * 100) : 0;
  const done = s.timerTarget > 0 && s.timerSec >= s.timerTarget;
  const color = s.step === 2 ? '#3b82f6' : 'var(--amber)';

  if (_bgIsMobilePortrait()) {
    // Portrait mode: update portrait-specific elements
    const tp = document.getElementById('bfs-p-timer');
    const pp = document.getElementById('bfs-p-prog');
    const bp = document.getElementById('bfs-p-btn');
    if (tp) { tp.textContent = _bgFmt(rem); tp.style.color = done ? 'var(--success)' : color; }
    if (pp) pp.style.width = pct.toFixed(2) + '%';
    if (bp) {
      const playPause = s.timerRunning
        ? _bfsBtn(`<i class="fas fa-pause"></i> ${t('rec.guide_pause')}`, '_bgPauseTimer()')
        : _bfsBtn(`<i class="fas fa-play"></i> ${t('rec.guide_start')}`, '_bgStartTimer()', 'primary');
      bp.innerHTML = playPause + _bfsBtn(`<i class="fas fa-rotate-left"></i>`, '_bgResetTimer()');
    }
    if (s.step === 3) {
      const wrap = document.getElementById('bfs-p-nexthop-wrap');
      if (wrap) wrap.outerHTML = _bgFsPortraitNextHopHtml();
    }
    return;
  }

  const te = document.getElementById('bfs-timer');
  const pe = document.getElementById('bfs-prog');
  const be = document.getElementById('bfs-timer-btns');
  if (te) { te.textContent = _bgFmt(rem); te.style.color = done ? 'var(--success)' : color; }
  if (pe) pe.style.width = pct.toFixed(2) + '%';
  if (be) {
    const startPause = s.timerRunning
      ? _bfsBtn(`<i class="fas fa-pause"></i> ${t('rec.guide_pause')}`, '_bgPauseTimer()')
      : _bfsBtn(`<i class="fas fa-play"></i> ${t('rec.guide_start')}`, '_bgStartTimer()', 'primary');
    be.innerHTML = startPause + _bfsBtn(`<i class="fas fa-rotate-left"></i> ${t('rec.guide_reset')}`, '_bgResetTimer()');
  }

  // Update hop schedule in boil step
  if (s.step === 3) {
    const em = s.timerSec / 60;
    s.boilHops.forEach((hop, idx) => {
      const el = document.getElementById(`bfs-hop-${idx}`);
      if (!el) return;
      const ht    = hop.hop_type || 'ebullition';
      const addAt = ['whirlpool','flameout'].includes(ht) ? s.boilTime : s.boilTime - (hop.hop_time ?? s.boilTime);
      const due   = em >= addAt;
      const notif = s.notified.has(`hop-${idx}`);
      const remMin= Math.max(0, addAt - em);
      el.style.background = notif ? '#052e16' : due ? '#422006' : '#0f172a';
      el.style.borderColor= notif ? '#16a34a' : due ? '#f59e0b' : '#1e293b';
      const emojiEl = el.querySelector('div:first-child');
      const timeLblEl = el.querySelector('div:last-child');
      if (emojiEl) emojiEl.textContent = notif ? '✅' : due ? '🔔' : '🌿';
      if (timeLblEl) {
        timeLblEl.textContent = notif ? t('rec.guide_hop_added') : due ? `⚡ ${t('rec.guide_hop_now')}` : `T‑${Math.ceil(remMin)} min`;
        timeLblEl.style.color = notif ? '#22c55e' : due ? '#f59e0b' : '#475569';
      }
    });
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// ── CYCLE DE VIE DU BRASSIN ───────────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════

function openBrewLifecycle(id) {
  const b = S.brews.find(x => x.id === id);
  if (!b) return;
  document.getElementById('blc-title').textContent = b.name;
  document.getElementById('blc-body').innerHTML = _renderLifecycle(b);
  openModal('brew-lifecycle-modal');
}

function _renderLifecycle(b) {
  if (!b.brew_date) return `<p style="color:var(--muted);text-align:center;padding:24px 0">${t('brew.lifecycle_no_date')}</p>`;

  const today = new Date(); today.setHours(0,0,0,0);
  const _d = s => { if (!s) return null; const d = new Date(s); d.setHours(0,0,0,0); return d; };
  const _diff = (a, b) => a && b ? Math.round((b - a) / 86400000) : null;
  const _fmt  = s => { if (!s) return null; if (s instanceof Date) { return `${s.getFullYear()}-${String(s.getMonth()+1).padStart(2,'0')}-${String(s.getDate()).padStart(2,'0')}`; } return String(s).slice(0,10); };

  // Bière en cave liée au brassin (pour récupérer les dates et stocks)
  const linkedBeers = S.beers.filter(bx => !bx.archived && (
    bx.brew_id === b.id ||
    (!bx.brew_id && b.recipe_id && bx.recipe_id === b.recipe_id)
  ));
  const linkedBeer = linkedBeers[0] || null;

  // Key dates — bottling_date priorité : brassin, sinon bière en cave
  const dBrew       = _d(b.brew_date);
  const dBottle     = _d(b.bottling_date || linkedBeer?.bottling_date);
  const dFirstDrink = _d(b.first_consumption);
  const dLastDrink  = _d(b.last_consumption);

  // Fermentation end = bottling_date si dispo, sinon brew_date + ferm_time
  const fermDays = b.ferm_time || null;
  const dFermEnd = dBottle || (fermDays ? new Date(dBrew.getTime() + fermDays * 86400000) : null);

  // Refermentation end = bottling_date + refermentation_days (si défini sur la bière en cave)
  const refermDays = linkedBeer?.refermentation && linkedBeer?.refermentation_days ? linkedBeer.refermentation_days : null;
  const dRefermEnd = (refermDays && dBottle) ? new Date(dBottle.getTime() + refermDays * 86400000) : null;

  // Phase durations
  const fermLen   = _diff(dBrew, dFermEnd);
  const refermLen = dRefermEnd ? _diff(dBottle, dRefermEnd) : null;
  // Portion écoulée de la refermentation (embouteillage → min(aujourd'hui, fin))
  const refermElapsed = dRefermEnd ? Math.max(0, _diff(dBottle, dRefermEnd > today ? today : dRefermEnd)) : null;
  // Cave : de la fin de refermentation (ou embouteillage) jusqu'à la première consommation
  // Si la refermentation n'est pas encore terminée, la phase cave n'a pas encore commencé
  const caveStart = dRefermEnd || dFermEnd;
  const caveEffectiveStart = (caveStart && caveStart <= today) ? caveStart : null;
  const caveLen   = caveEffectiveStart ? Math.max(0, _diff(caveEffectiveStart, dFirstDrink || today)) : null;
  // Consommation : seulement si première consommation connue
  const consoLen  = dFirstDrink ? _diff(dFirstDrink, dLastDrink || today) : null;

  // Span: du brassage jusqu'au dernier jalon connu (fin refermentation si dans le futur, sinon aujourd'hui)
  const spanEnd   = dLastDrink || dFirstDrink || (dRefermEnd && dRefermEnd > today ? dRefermEnd : today);
  const totalDays = Math.max(1, _diff(dBrew, spanEnd));

  // Milestones for the bar
  const milestones = [
    { key: 'brew',   date: dBrew,       label: t('brew.lifecycle_brewing'),    color: 'var(--amber)',   icon: 'fa-fire-burner' },
    { key: 'ferm',   date: dFermEnd,    label: t('brew.lifecycle_bottling'),    color: 'var(--info)',    icon: 'fa-wine-bottle', estimated: !dBottle },
    { key: 'referm', date: dRefermEnd,  label: t('brew.lifecycle_referm_end'), color: 'var(--other)', icon: 'fa-rotate' },
    { key: 'first',  date: dFirstDrink, label: t('brew.lifecycle_consumption'), color: 'var(--hop)',     icon: 'fa-beer-mug-empty' },
    { key: 'last',   date: dLastDrink,  label: t('brew.lifecycle_depleted'),    color: 'var(--error)',   icon: 'fa-box-archive' },
  ].filter(m => m.date);

  // Build bar segments
  const segments = [];
  if (dFermEnd && fermLen != null && fermLen > 0) {
    segments.push({ label: t('brew.lifecycle_phase_ferm'), days: fermLen, color: 'var(--info)', pct: fermLen / totalDays * 100 });
  }
  if (dRefermEnd && refermElapsed != null && refermElapsed > 0) {
    segments.push({ label: t('brew.lifecycle_phase_referm'), days: refermLen, color: 'var(--other)', pct: refermElapsed / totalDays * 100 });
  }
  if (caveEffectiveStart && caveLen != null && caveLen > 0) {
    segments.push({ label: t('brew.lifecycle_phase_cave'), days: caveLen, color: 'var(--amber)', pct: caveLen / totalDays * 100 });
  }
  if (consoLen !== null && consoLen >= 0) {
    segments.push({ label: t('brew.lifecycle_phase_conso'), days: consoLen, color: 'var(--hop)', pct: consoLen / totalDays * 100 });
  }

  // Today marker position
  const todayPct = today >= dBrew ? Math.min(100, _diff(dBrew, today) / totalDays * 100) : null;

  // ── HTML ──
  const segHtml = segments.length
    ? segments.map(s => `<div style="height:100%;width:${s.pct.toFixed(2)}%;background:${s.color};opacity:.85;transition:width .3s" title="${s.label} — ${s.days}${t('brew.lifecycle_days').replace('${n}','').trim() || 'j'}"></div>`).join('')
    : `<div style="height:100%;width:100%;background:var(--muted);opacity:.3"></div>`;

  const todayMarkerHtml = todayPct != null && todayPct < 100
    ? `<div style="position:absolute;top:0;bottom:0;left:${todayPct.toFixed(2)}%;width:2px;background:rgba(255,255,255,.85);z-index:2">
         <div style="position:absolute;top:-20px;left:50%;transform:translateX(-50%);font-size:.65rem;color:var(--text);white-space:nowrap;background:var(--card2);padding:1px 4px;border-radius:4px;border:1px solid var(--border)">${t('brew.lifecycle_today')}</div>
       </div>`
    : '';

  // Milestone dots below bar
  const dotHtml = milestones.map(m => {
    const pct = Math.min(100, Math.max(0, _diff(dBrew, m.date) / totalDays * 100));
    const est = m.estimated ? ` <span style="font-size:.65rem;color:var(--muted)">(${t('brew.lifecycle_estimated')})</span>` : '';
    return `<div style="position:absolute;left:${pct.toFixed(2)}%;transform:translateX(-50%);text-align:center;top:0">
      <div style="width:10px;height:10px;border-radius:50%;background:${m.color};border:2px solid var(--card);margin:0 auto"></div>
      <div style="font-size:.65rem;color:var(--muted);white-space:nowrap;margin-top:2px">${_fmt(m.date)}</div>
      <div style="font-size:.7rem;font-weight:600;color:var(--text);white-space:nowrap">${m.label}${est}</div>
    </div>`;
  }).join('');

  // Phase stat cards
  const phaseCards = [
    { label: t('brew.lifecycle_phase_ferm'),   days: fermLen,   color: 'var(--info)',    icon: 'fa-flask',          est: !dBottle },
    ...(dRefermEnd ? [{ label: t('brew.lifecycle_phase_referm'), days: refermLen, color: 'var(--other)', icon: 'fa-rotate', est: false }] : []),
    { label: t('brew.lifecycle_phase_cave'),   days: caveLen,   color: 'var(--amber)',   icon: 'fa-box',            est: !dFirstDrink, hide: caveLen === null },
    { label: t('brew.lifecycle_phase_conso'),  days: consoLen,  color: 'var(--hop)',     icon: 'fa-beer-mug-empty', est: dFirstDrink && !dLastDrink },
  ];
  const cardHtml = phaseCards.filter(c => !c.hide).map(c => {
    const val = c.days != null
      ? `${c.days}${t('brew.lifecycle_days').replace('${n}','').trim() || 'j'}${c.est ? `<span style="font-size:.72rem;color:var(--muted)"> ${t('brew.lifecycle_ongoing')}</span>` : ''}`
      : `<span style="color:var(--muted)">—</span>`;
    return `<div style="flex:1;min-width:140px;padding:14px 16px;border-radius:10px;background:var(--card2);border:1px solid var(--border);text-align:center">
      <div style="font-size:1.1rem;margin-bottom:4px"><i class="fas ${c.icon}" style="color:${c.color}"></i></div>
      <div style="font-size:.78rem;color:var(--muted);margin-bottom:4px">${c.label}</div>
      <div style="font-size:1.25rem;font-weight:700;color:var(--text)">${val}</div>
    </div>`;
  }).join('');

  // Beer stock info (utilise linkedBeers calculé plus haut)
  const totalStock = linkedBeers.reduce((s, bx) => s + (bx.stock_33cl||0)*0.33 + (bx.stock_75cl||0)*0.75 + (bx.keg_liters||0), 0);
  const stockHtml = linkedBeers.length ? `<div style="margin-top:16px;padding:10px 14px;border-radius:8px;background:var(--card2);border:1px solid var(--border);font-size:.82rem;color:var(--muted)">
    <i class="fas fa-beer-mug-empty" style="color:var(--hop)"></i>
    ${linkedBeers.map(bx => {
      const parts = [];
      if (bx.stock_33cl) parts.push(`${bx.stock_33cl}×33cl`);
      if (bx.stock_75cl) parts.push(`${bx.stock_75cl}×75cl`);
      if (bx.keg_liters) parts.push(`${bx.keg_liters}L fût`);
      return `<strong style="color:var(--text)">${esc(bx.name)}</strong>: ${parts.length ? parts.join(' + ') : t('cave.empty_cave')}`;
    }).join(' · ')}
    · <strong style="color:var(--hop)">${totalStock.toFixed(1)} L</strong>
  </div>` : '';

  return `
    <div style="margin-bottom:30px">
      <!-- Bar + dots with horizontal padding so edge labels aren't clipped -->
      <div style="padding:0 36px;box-sizing:border-box">
        <div style="position:relative;height:28px;border-radius:8px;overflow:hidden;background:var(--card2);border:1px solid var(--border);display:flex">
          ${segHtml}
          ${todayMarkerHtml}
        </div>
        <!-- Milestone dots -->
        <div style="position:relative;height:64px;margin-top:4px;overflow:visible">
          ${dotHtml}
        </div>
      </div>
    </div>
    <!-- Phase cards -->
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px">
      ${cardHtml}
    </div>
    ${stockHtml}`;
}

// ══════════════════════════════════════════════════════════════════════════════
// ── BRASSINS ─────────────────────────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════
const BREW_STATUS = {
  planned:     { get label() { return t('brew.status_planned'); },       color: 'var(--info)' },
  in_progress: { get label() { return t('brew.status_in_progress'); },   color: 'var(--amber)' },
  fermenting:  { get label() { return t('brew.status_fermenting'); },    color: 'var(--hop)' },
  completed:   { get label() { return t('brew.status_completed'); },     color: 'var(--success)' },
};
function brewStatusBadge(s) {
  const st = BREW_STATUS[s] || { label: s || t('brew.status_planned'), color: 'var(--muted)' };
  return `<span style="font-size:.72rem;font-weight:700;padding:2px 8px;border-radius:20px;background:${st.color}22;color:${st.color};border:1px solid ${st.color}55;vertical-align:middle">${st.label}</span>`;
}

function _spindleAgo(dateStr) {
  if (!dateStr) return null;
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (diff < 60)   return t('brew.ago_sec').replace('${diff}', diff);
  if (diff < 3600) return t('brew.ago_min').replace('${diff}', Math.floor(diff/60));
  if (diff < 86400)return t('brew.ago_hour').replace('${diff}', Math.floor(diff/3600));
  return t('brew.ago_day').replace('${diff}', Math.floor(diff/86400));
}

let _brewAC = null;

function renderBrassins() {
  const q      = (document.getElementById('brew-search')?.value || '').toLowerCase();
  const active = S.brews.filter(b => !b.archived);
  const arch   = S.brews.filter(b => b.archived);
  const all    = showArchivedBrew ? [...active, ...arch] : active;
  const shown  = all.filter(b => !q || b.name.toLowerCase().includes(q) || (b.recipe_name || '').toLowerCase().includes(q));

  // Stats on active brews only (not affected by search)
  const withEff = active.filter(b => b.actual_efficiency != null);
  const avgEff  = withEff.length ? withEff.reduce((s,b) => s + b.actual_efficiency, 0) / withEff.length : null;
  const effStat = avgEff != null
    ? `<div class="stat" title="${t('brew.eff_avg_tip').replace('${n}', withEff.length)}"><div class="stat-val" style="color:var(--info)">${avgEff.toFixed(1)}%</div><div class="stat-lbl">${t('brew.eff_avg')}</div></div>`
    : '';
  document.getElementById('brew-stats').innerHTML = `
    <div class="stat"><div class="stat-val">${active.length}</div><div class="stat-lbl">${t('brew.stat_total')}</div></div>
    <div class="stat"><div class="stat-val" style="color:var(--hop)">${active.filter(b=>b.status==='completed').length}</div><div class="stat-lbl">${t('brew.stat_completed')}</div></div>
    <div class="stat"><div class="stat-val" style="color:var(--amber)">${active.length ? (active.filter(b=>b.abv).reduce((s,b)=>s+b.abv,0) / (active.filter(b=>b.abv).length || 1)).toFixed(1)+'%' : '–'}</div><div class="stat-lbl">${t('brew.stat_abv_avg')}</div></div>
    <div class="stat"><div class="stat-val" style="color:var(--info)">${active.length ? active.filter(b=>b.volume_brewed).reduce((s,b)=>s+(b.volume_brewed||0),0).toFixed(0)+'L' : '–'}</div><div class="stat-lbl">${t('brew.stat_vol_total')}</div></div>
    ${effStat}`;

  const list = document.getElementById('brew-list');
  const emptyEl = document.getElementById('brew-empty');
  emptyEl.style.display = shown.length ? 'none' : 'block';
  if (!shown.length) {
    document.getElementById('brew-empty-cta').style.display        = q ? 'none' : '';
    document.getElementById('brew-empty-noresults').style.display  = q ? '' : 'none';
  }
  const brewCount = document.getElementById('brew-search-count');
  if (brewCount) brewCount.textContent = q
    ? t('common.n_results_of').replace('${n}', shown.length).replace('${total}', all.length)
    : t('common.n_results').replace('${n}', shown.length);

  if (!shown.length) { list.innerHTML = ''; }
  else {
    const STATUS_ORDER = ['planned', 'in_progress', 'fermenting', 'completed'];
    const STATUS_ICONS = {
      planned:     'fas fa-calendar-plus',
      in_progress: 'fas fa-fire-flame-curved',
      fermenting:  'fas fa-flask',
      completed:   'fas fa-check-circle',
    };

    const _brewCardHtml = b => {
      const sp  = S.spindles.find(s => s.brew_id === b.id);
      const ts  = S.tempSensors.find(s => s.brew_id === b.id);
      const keg = S.sodaKegs.find(k => k.brew_id === b.id);

      // ── Atténuation réelle ──────────────────────────────────────────────────
      const attReal = (b.og && b.fg && b.og > 1) ? ((b.og - b.fg) / (b.og - 1) * 100) : null;
      let attHtml = '';
      if (attReal != null) {
        let attColor = 'var(--muted)';
        let attIcon  = '';
        let attTip   = t('brew.att_real');
        const rec = b.recipe_id ? S.recipes.find(r => r.id === b.recipe_id) : null;
        if (rec) {
          const yeast = (rec.ingredients || []).find(i => i.category === 'levure');
          if (yeast) {
            const cy = S.catalog.find(c => c.name.toLowerCase() === yeast.name.toLowerCase() && c.category === 'levure');
            const aMin = cy?.attenuation_min, aMax = cy?.attenuation_max;
            if (aMin != null && aMax != null) {
              attTip = t('brew.att_expected').replace('${min}', aMin).replace('${max}', aMax);
              if (attReal >= aMin && attReal <= aMax) {
                attColor = 'var(--success)'; attIcon = '<i class="fas fa-circle-check" style="font-size:.7rem"></i> ';
              } else if (attReal < aMin) {
                attColor = 'var(--amber)';   attIcon = '<i class="fas fa-triangle-exclamation" style="font-size:.7rem"></i> ';
              } else {
                attColor = 'var(--info)';    attIcon = '<i class="fas fa-circle-info" style="font-size:.7rem"></i> ';
              }
            }
          }
        }
        attHtml = ` · <span style="color:${attColor}" title="${attTip}">${attIcon}${t('brew.attenuation')} ${attReal.toFixed(1)}%</span>`;
      }

      // ── Coût réel ────────────────────────────────────────────────────────
      const costData = brewCost(b);
      const costHtml = costData
        ? ` · <span style="color:var(--success);cursor:pointer" onclick="event.stopPropagation();openBrewCostModal(${b.id})" title="${t('brew.cost_breakdown')}"><i class="fas fa-euro-sign" style="font-size:.65rem"></i> ${costData.total.toFixed(2)}${costData.perLiter != null ? ` <span style="font-size:.73rem;color:var(--muted)">(${costData.perLiter.toFixed(2)} ${t('brew.cost_per_liter')})</span>` : ''}</span>`
        : '';

      // ── Efficacité cuve ──────────────────────────────────────────────────
      let effHtml = '';
      // Préférer la valeur stockée (fiable même si recette modifiée), fallback calcul live
      const storedEff  = b.actual_efficiency;
      const effResult  = storedEff != null ? null : _calcBrewEff(b.og, b.volume_brewed, b.recipe_id);
      const eff        = storedEff ?? effResult?.eff ?? null;
      const recipeEff  = effResult?.recipeEff ?? (b.recipe_id ? (S.recipes.find(r=>r.id===b.recipe_id)?.brewhouse_efficiency ?? null) : null);
      if (eff != null) {
        let effColor = 'var(--muted)', effIcon = '';
        let effTip = t('brew.eff_real');
        if (recipeEff != null) {
          effTip = t('brew.eff_target').replace('${pct}', recipeEff);
          const delta = eff - recipeEff;
          if (Math.abs(delta) <= 3) {
            effColor = 'var(--success)'; effIcon = '<i class="fas fa-circle-check" style="font-size:.7rem"></i> ';
          } else if (delta < 0) {
            effColor = 'var(--amber)';   effIcon = '<i class="fas fa-triangle-exclamation" style="font-size:.7rem"></i> ';
          } else {
            effColor = 'var(--info)';    effIcon = '<i class="fas fa-circle-arrow-up" style="font-size:.7rem"></i> ';
          }
        }
        effHtml = ` · <span style="color:${effColor}" title="${effTip}">${effIcon}${t('brew.eff_real')} ${eff.toFixed(1)}%</span>`;
      }
      let spindleHtml = '';
      let spindleBtn  = '';
      let tempBadge   = '';
      let tempBtn     = '';
      if (sp) {
        const gravStr = sp.last_gravity    != null ? sp.last_gravity.toFixed(3)    : null;
        const tempStr = sp.last_temperature != null ? sp.last_temperature.toFixed(1) : null;
        const ago     = _spindleAgo(sp.last_reading_at);
        const isLive  = sp.last_reading_at && (Date.now() - new Date(sp.last_reading_at).getTime()) < 3_600_000;
        const stableHtml = sp.gravity_stable
          ? `<span title="${t('spin.ferm_stable_hint')}" style="color:var(--success);font-size:.7rem;font-weight:700;margin-left:2px"><i class="fas fa-circle-check"></i> ${t('spin.ferm_stable')}</span>`
          : '';
        spindleHtml = `
          <div class="brew-spindle-badge">
            ${isLive ? '<span class="bsb-live"></span>' : '<i class="fas fa-water" style="color:var(--info);font-size:.75rem"></i>'}
            <span style="color:var(--muted);font-size:.78rem">${esc(sp.name)}</span>
            ${gravStr ? `<span class="bsb-grav"><i class="fas fa-weight-hanging" style="font-size:.7rem"></i> ${gravStr}</span>` : ''}
            ${tempStr ? `<span class="bsb-temp">${tempStr}°C</span>` : ''}
            ${ago ? `<span class="bsb-ago">${ago}</span>` : ''}
            ${stableHtml}
          </div>`;
        spindleBtn = `<button class="btn btn-ghost btn-sm btn-icon" onclick="openSpindleChart(${sp.id})" title="${t('spin.chart_gravity_label')} — ${esc(sp.name)}"><i class="fas fa-water" style="color:var(--info)"></i></button>`;
      }
      if (ts) {
        const tVal = ts.last_temperature != null ? ts.last_temperature.toFixed(1) + '°C' : null;
        const ago  = _spindleAgo(ts.last_reading_at);
        const isLive = ts.last_reading_at && (Date.now() - new Date(ts.last_reading_at).getTime()) < 3_600_000;
        tempBadge = `
          <div class="brew-spindle-badge" style="border-color:#ef444440">
            ${isLive ? '<span class="bsb-live" style="background:#ef4444"></span>' : '<i class="fas fa-thermometer-half" style="color:#ef4444;font-size:.75rem"></i>'}
            <span style="color:var(--muted);font-size:.78rem">${esc(ts.name)}</span>
            ${tVal ? `<span class="bsb-temp" style="color:#ef4444">${tVal}</span>` : ''}
            ${ago ? `<span class="bsb-ago">${ago}</span>` : ''}
          </div>`;
        tempBtn = `<button class="btn btn-ghost btn-sm btn-icon" onclick="openTempChart(${ts.id})" title="${t('spin.chart_temp_label')} — ${esc(ts.name)}"><i class="fas fa-thermometer-half" style="color:#ef4444"></i></button>`;
      }
      return `
      <div class="brew-card ${b.archived ? 'archived-item' : ''}" data-id="${b.id}" draggable="true">
        <span class="brew-drag-handle" title="${t('brew.drag_to_reorder')}"><i class="fas fa-grip-vertical"></i></span>
        <div class="brew-card-info">
          <div class="brew-card-name">${esc(b.name)}</div>
          <div class="brew-card-meta">
            ${b.recipe_name ? `<i class="fas fa-scroll"></i> ${esc(b.recipe_name)} · ` : ''}
            ${b.brew_date ? `<i class="fas fa-calendar"></i> ${b.brew_date} · ` : ''}
            ${b.volume_brewed ? `${b.volume_brewed}L · ` : ''}
            ${b.abv ? `<strong style="color:var(--amber)">${b.abv}% ABV</strong>` : ''}
            ${b.og ? ` · OG ${b.og}` : ''}${b.fg ? ` → FG ${b.fg}` : ''}
            ${attHtml}${effHtml}${costHtml}
          </div>
          <div id="brew-note-display-${b.id}" onclick="event.stopPropagation();toggleBrewQuickNote(${b.id})" style="font-size:.78rem;color:var(--muted);margin-top:4px;cursor:text;${b.notes ? '' : 'display:none'}">${esc(b.notes||'')}</div>
          <div id="brew-qnote-${b.id}" style="display:none;margin-top:6px">
            <textarea id="brew-qnote-ta-${b.id}" rows="2" onclick="event.stopPropagation()" onblur="saveBrewQuickNote(${b.id})" onkeydown="if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();saveBrewQuickNote(${b.id})}" style="width:100%;font-size:.8rem;resize:vertical;border-radius:6px;border:1px solid var(--primary);background:var(--card2);color:var(--text);padding:6px 8px;box-sizing:border-box" placeholder="${t('brew.field_notes')}">${esc(b.notes||'')}</textarea>
          </div>
          <div id="brew-photos-${b.id}" style="display:none;margin-top:8px"></div>
          ${keg ? `<div class="brew-spindle-badge" style="border-color:rgba(245,158,11,.35);margin-top:6px">
            <i class="fas fa-jar" style="color:var(--amber);font-size:.75rem"></i>
            <span style="color:var(--muted);font-size:.78rem">${esc(keg.name)}</span>
            ${keg.current_liters != null ? `<span class="bsb-grav" style="color:var(--amber)">${keg.current_liters} L</span>` : ''}
          </div>` : ''}
          ${spindleHtml}${tempBadge}
        </div>
        <div style="display:flex;gap:6px;flex-shrink:0">
          ${spindleBtn}${tempBtn}
          ${b.recipe_id && !['fermenting','completed'].includes(b.status) ? `<button class="btn btn-ghost btn-sm btn-icon" onclick="event.stopPropagation();openBrewTimerForBrew(${b.id})" title="${t('brew.timer_title')}"><i class="fas fa-stopwatch" style="color:var(--amber)"></i></button>` : ''}
          ${b.recipe_id && !['fermenting','completed'].includes(b.status) ? `<button class="btn btn-ghost btn-sm btn-icon" onclick="event.stopPropagation();openBrewingGuideFromBrew(${b.id})" title="${t('rec.guide_btn')}"><i class="fas fa-fire-burner" style="color:var(--amber)"></i></button>` : ''}
          ${b.fermentation_count > 0 ? `<button class="btn btn-ghost btn-sm btn-icon" onclick="openBrewFermentationChart(${b.id})" title="${t('brew.readings')} (${b.fermentation_count})"><i class="fas fa-chart-line" style="color:var(--info)"></i></button>` : ''}
          <button class="btn btn-ghost btn-sm btn-icon" onclick="openFermLog(${b.id},this)" data-brew-name="${esc(b.name)}" title="${t('brew.ferm_log_title')}${b.fermentation_count > 0 ? ` (${b.fermentation_count})` : ''}" style="${b.fermentation_count > 0 ? 'color:var(--info)' : ''}"><i class="fas fa-flask"></i></button>
          <button class="btn btn-ghost btn-sm btn-icon" onclick="openBrewLog(${b.id},this)" data-brew-name="${esc(b.name)}" title="${t('brew.blog_title')}${b.log_count > 0 ? ` (${b.log_count})` : ''}" style="${b.log_count > 0 ? 'color:var(--amber)' : ''}"><i class="fas fa-book-open"></i></button>
          ${b.photos_url
            ? `<a href="${esc(b.photos_url)}" target="_blank" rel="noopener" class="btn btn-ghost btn-sm btn-icon" title="${t('brew.photos_url_open')}" style="color:var(--amber);text-decoration:none"><i class="fas fa-images"></i></a>`
            : `<button class="btn btn-ghost btn-sm btn-icon" onclick="event.stopPropagation();toggleBrewPhotos(${b.id})" title="${t('brew.photos')}${b.photo_count > 0 ? ` (${b.photo_count})` : ''}" style="${b.photo_count > 0 ? 'color:var(--amber)' : ''}"><i class="fas fa-camera"></i></button>`
          }
          <button class="btn btn-ghost btn-sm btn-icon" onclick="openBrewKegModal(${b.id})" title="${keg ? esc(keg.name) : t('brew.keg_assign')}" style="${keg ? 'color:var(--amber)' : ''}"><i class="fas fa-jar"></i></button>
          ${b.status === 'completed' ? `<button class="btn btn-sm btn-success" onclick="openAfterBrewModal(${b.id})" title="${t('brew.to_cave')}"><i class="fas fa-beer-mug-empty"></i> ${t('brew.to_cave')}</button>` : ''}
          ${!['fermenting','completed'].includes(b.status) ? `<button class="btn btn-ghost btn-sm btn-icon" onclick="openBrewChecklist(${b.id})" title="${t('checklist.open_btn')}"><i class="fas fa-clipboard-check" style="color:var(--success)"></i></button>` : ''}
          <button class="btn btn-ghost btn-sm btn-icon" onclick="openBrewLifecycle(${b.id})" title="${t('brew.lifecycle_btn')}"><i class="fas fa-timeline" style="color:var(--amber)"></i></button>
          <button class="btn btn-icon btn-ghost btn-sm" onclick="withBtn(this,()=>archiveItem('brew',${b.id},${b.archived?0:1}))" title="${b.archived?t('common.restore'):t('common.archive')}"><i class="fas fa-${b.archived?'box-open':'box-archive'}"></i></button>
          <button class="btn btn-icon btn-ghost btn-sm" onclick="event.stopPropagation();toggleBrewQuickNote(${b.id})" title="${t('brew.field_notes')}" id="brew-qnote-btn-${b.id}"><i class="fas fa-note-sticky"></i></button>
          <button class="btn btn-icon btn-ghost btn-sm" onclick="openBrewEditModal(${b.id})" title="${t('common.edit')}"><i class="fas fa-pen"></i></button>
          <button class="btn btn-icon btn-danger btn-sm" onclick="deleteBrew(${b.id})"><i class="fas fa-trash"></i></button>
        </div>
      </div>`;
    };

    const groups = STATUS_ORDER.map(status => ({
      status,
      brews: shown.filter(b => (b.status || 'planned') === status),
    })).filter(g => g.brews.length > 0);

    // Groups as display:contents wrappers — invisible to CSS, diffable by _patchList
    list.querySelectorAll(':scope > .skel').forEach(el => el.remove());
    _patchList(list, groups, g => `group-${g.status}`, g => {
      const st = BREW_STATUS[g.status];
      return `<div class="brew-group" data-id="group-${g.status}">
          <div class="brew-group-header">
            <i class="${STATUS_ICONS[g.status]}" style="color:${st.color}"></i>
            <span style="color:${st.color}">${st.label}</span>
            <span class="brew-group-count">${g.brews.length}</span>
          </div>
          ${g.brews.map(_brewCardHtml).join('')}
        </div>`;
    });
  }

  // Archive button
  const archBtn = document.getElementById('brew-arch-btn');
  if (archBtn) {
    const archCount = arch.length;
    archBtn.textContent = showArchivedBrew ? t('brew.show_archives') : `\uD83D\uDDC3\uFE0F Archives (${archCount})`;
  }

  // ── Drag & drop reorder (within each status group) ──
  if (_brewAC) _brewAC.abort();
  _brewAC = new AbortController();
  const { signal: brewSig } = _brewAC;

  list.querySelectorAll('.brew-group').forEach(group => {
    group.querySelectorAll('.brew-card[draggable]').forEach(card => {
      card.addEventListener('dragstart', e => {
        e.dataTransfer.setData('text/plain', card.dataset.id);
        e.dataTransfer.effectAllowed = 'move';
        setTimeout(() => card.classList.add('dragging'), 0);
      }, { signal: brewSig });
      card.addEventListener('dragend', () => {
        card.classList.remove('dragging');
        group.querySelectorAll('.brew-card').forEach(c => c.classList.remove('drag-over'));
      }, { signal: brewSig });
      card.addEventListener('dragover', e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        group.querySelectorAll('.brew-card').forEach(c => c.classList.remove('drag-over'));
        const srcId = parseInt(e.dataTransfer.getData('text/plain'));
        if (srcId !== parseInt(card.dataset.id)) card.classList.add('drag-over');
      }, { signal: brewSig });
      card.addEventListener('dragleave', () => card.classList.remove('drag-over'), { signal: brewSig });
      card.addEventListener('drop', e => {
        e.preventDefault();
        const srcId = parseInt(e.dataTransfer.getData('text/plain'));
        const tgtId = parseInt(card.dataset.id);
        if (!srcId || srcId === tgtId) return;
        const mi = S.brews.findIndex(b => b.id === srcId);
        const ti = S.brews.findIndex(b => b.id === tgtId);
        if (mi === -1 || ti === -1) return;
        // Only reorder within the same status group
        if (S.brews[mi].status !== S.brews[ti].status) return;
        const [moved] = S.brews.splice(mi, 1);
        S.brews.splice(ti, 0, moved);
        saveBrewOrder();
        renderBrassins();
      }, { signal: brewSig });
    });
  });

  // Refresh analytics panel if it's open
  if (document.getElementById('brew-analytics-panel')?.style.display !== 'none') {
    renderBrewAnalytics();
  }
}

let _saveBrewOrderTimer = null;
function saveBrewOrder() {
  clearTimeout(_saveBrewOrderTimer);
  _saveBrewOrderTimer = setTimeout(async () => {
    try {
      await api('PUT', '/api/brews/reorder',
        S.brews.map((b, i) => ({ id: b.id, sort_order: i })));
    } catch(e) { toast(t('brew.err_save_order'), 'error'); }
  }, 600);
}

function openBrewModal(recipeId = null) {
  _dirtyModals.delete('brew-modal');
  // Populate recipe select
  const sel = document.getElementById('brew-f-recipe');
  sel.innerHTML = '<option value="">— Choisir une recette —</option>' +
    S.recipes.filter(r => !r.archived).map(r =>
      `<option value="${r.id}">${esc(r.name)}${r.style ? ' · ' + esc(r.style) : ''} (${r.volume}L)</option>`
    ).join('');
  document.getElementById('brew-f-name').value  = '';
  document.getElementById('brew-f-date').value  = new Date().toISOString().split('T')[0];
  document.getElementById('brew-f-vol').value   = '';
  document.getElementById('brew-f-og').value    = '';
  document.getElementById('brew-f-fg').value    = '';
  document.getElementById('brew-f-abv').value   = '';
  document.getElementById('brew-f-notes').value = '';
  document.getElementById('brew-ingredients-section').style.display = 'none';
  document.getElementById('brew-f-style-hint').style.display = 'none';
  if (recipeId) { sel.value = recipeId; onBrewRecipeChange(); }
  // Auto-numéro : max(batch_number connu) sinon fallback sur total brews
  const _bNums = (S.brews || []).map(b => parseInt(b.batch_number) || 0).filter(n => n > 0);
  const nextNum = _bNums.length > 0 ? Math.max(..._bNums) + 1 : (S.brews || []).length + 1;
  document.getElementById('brew-f-number').value = nextNum;
  showBrewAlert('');
  // Ouvrir directement (sans passer par openModal pour éviter la récursion)
  document.getElementById('brew-modal').classList.add('open');
  setTimeout(() => { document.getElementById('brew-f-number').value = nextNum; }, 150);
}


// Recettes nav : toujours revenir en mode liste
document.getElementById('nav-recettes').onclick = () => { navigate('recettes'); showRecipeListOnly(); };

function toBaseUnit(qty, unit) {
  if (unit === 'kg') return qty * 1000;
  if (unit === 'g')  return qty;
  if (unit === 'L')  return qty * 1000;
  if (unit === 'ml' || unit === 'mL') return qty;
  return qty; // sachet, pièce
}

function onBrewRecipeChange() {
  const recipeId = parseInt(document.getElementById('brew-f-recipe').value);
  const recipe = S.recipes.find(r => r.id === recipeId);
  const section = document.getElementById('brew-ingredients-section');
  const list    = document.getElementById('brew-ing-list');

  if (!recipe) {
    section.style.display = 'none';
    document.getElementById('brew-f-style-hint').style.display = 'none';
    return;
  }

  // Afficher le style de la recette
  const _styleEl = document.getElementById('brew-f-style-hint');
  const _styleVal = document.getElementById('brew-f-style-val');
  const _style = (recipe.style || '').trim();
  if (_styleEl && _styleVal) {
    if (_style) { _styleVal.textContent = _style; _styleEl.style.display = ''; }
    else _styleEl.style.display = 'none';
  }

  // Auto-fill name avec numéro de brassin
  if (!document.getElementById('brew-f-name').value) {
    const num = document.getElementById('brew-f-number').value;
    const prefix = num ? `Brassin #${num} – ` : '';
    document.getElementById('brew-f-name').value = prefix + recipe.name;
  }
  document.getElementById('brew-f-vol').value = recipe.volume;
  if (recipe.notes && !document.getElementById('brew-f-notes').value)
    document.getElementById('brew-f-notes').value = recipe.notes;
  if (recipe.brew_date && !document.getElementById('brew-f-date').value)
    document.getElementById('brew-f-date').value = recipe.brew_date;

  section.style.display = '';
  const costEl = document.getElementById('brew-cost-estimate');
  if (!recipe.ingredients.length) {
    list.innerHTML = `<p style="color:var(--muted)">${t('rec.no_ing')}</p>`;
    if (costEl) costEl.innerHTML = '';
    return;
  }

  list.innerHTML = recipe.ingredients.map(ing => {
    const inv = ing.inventory_item_id ? S.inventory.find(i => i.id === ing.inventory_item_id) : null;
    const stockBase  = inv ? toBaseUnit(inv.quantity, inv.unit) : null;
    const neededBase = toBaseUnit(ing.quantity, ing.unit);
    let sbcls='sb-na', stockTxt=t('inv.not_linked');
    if (stockBase !== null) {
      if (stockBase >= neededBase) { sbcls='sb-ok'; stockTxt=t('inv.qty_avail').replace('${qty}', inv.quantity).replace('${unit}', inv.unit); }
      else if (stockBase > 0)     { sbcls='sb-low'; stockTxt=`${inv.quantity} ${inv.unit} / besoin ${ing.quantity} ${ing.unit}`; }
      else                        { sbcls='sb-empty'; stockTxt=t('inv.empty_all'); }
    }
    return `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--border)">
      <div>
        <span class="badge badge-${ing.category}" style="margin-right:8px">${catLabel(ing.category)}</span>
        <strong>${esc(ing.name)}</strong> — ${ing.quantity} ${ing.unit}
        ${ing.category==='houblon' ? (
            ing.hop_type==='dryhop'    ? `<span style="color:var(--info);font-size:.8rem"> [Dry Hop${ing.hop_days!=null?' · '+ing.hop_days+' j':''}]</span>`
          : ing.hop_type==='whirlpool' ? `<span style="color:var(--muted);font-size:.8rem"> [Whirlpool${ing.hop_time!=null?' −'+ing.hop_time+' min':''}]</span>`
          : ing.hop_time!=null         ? `<span style="color:var(--muted);font-size:.8rem"> (−${ing.hop_time} min)</span>`
          : '') : ''}
      </div>
      <span class="stock-badge ${sbcls}">${stockTxt}</span>
    </div>`;
  }).join('');

  // ── Coût estimé ────────────────────────────────────────────────────────────
  if (costEl) {
    let totalCost = 0, hasCost = false;
    recipe.ingredients.forEach(ing => {
      const c = ingCost(ing);
      if (c !== null) { totalCost += c; hasCost = true; }
    });
    const gasCost  = parseFloat(appSettings.energy?.gas_per_brew)  || 0;
    const elecCost = parseFloat(appSettings.energy?.elec_per_brew) || 0;
    if (gasCost  > 0) { totalCost += gasCost;  hasCost = true; }
    if (elecCost > 0) { totalCost += elecCost; hasCost = true; }

    if (hasCost) {
      const vol = recipe.volume || 20;
      const perL = totalCost / vol;
      costEl.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;margin-top:10px;padding:8px 12px;background:rgba(16,185,129,.07);border:1px solid rgba(16,185,129,.25);border-radius:8px">
          <span style="font-size:.83rem;color:var(--muted)"><i class="fas fa-euro-sign" style="color:var(--success)"></i> ${t('brew.est_cost')}</span>
          <span style="font-weight:700;color:var(--success)">${totalCost.toFixed(2)} €
            <span style="font-size:.75rem;font-weight:400;color:var(--muted);margin-left:6px">${perL.toFixed(2)} €/L</span>
          </span>
        </div>`;
    } else {
      costEl.innerHTML = '';
    }
  }
}

document.getElementById('brew-f-og').oninput = document.getElementById('brew-f-fg').oninput = function() {
  const og = parseFloat(document.getElementById('brew-f-og').value);
  const fg = parseFloat(document.getElementById('brew-f-fg').value);
  if (og && fg) document.getElementById('brew-f-abv').value = ((og - fg) * 131.25).toFixed(2);
};

function _bewRecompute() {
  const og  = parseFloat(document.getElementById('bew-og').value);
  const fg  = parseFloat(document.getElementById('bew-fg').value);
  const vol = parseFloat(document.getElementById('bew-vol').value);
  if (og && fg) document.getElementById('bew-abv').value = ((og - fg) * 131.25).toFixed(2);
  _updateBewAttRow(og, fg);
  const brewId   = parseInt(document.getElementById('bew-id').value);
  const recipeId = S.brews.find(b => b.id === brewId)?.recipe_id ?? null;
  _updateBewEffRow(og, vol, recipeId);
  _updateBewOGAnalysis(og, vol, recipeId);
}
document.getElementById('bew-og').oninput  = _bewRecompute;
document.getElementById('bew-fg').oninput  = _bewRecompute;
document.getElementById('bew-vol').oninput = _bewRecompute;

function _updateBewAttRow(og, fg) {
  const row = document.getElementById('bew-att-row');
  if (!row) return;
  if (!og || !fg || og <= 1) { row.style.display = 'none'; return; }
  const att = (og - fg) / (og - 1) * 100;
  document.getElementById('bew-att-val').textContent = att.toFixed(1) + '%';
  // Yeast range from linked recipe
  const brewId = parseInt(document.getElementById('bew-id').value);
  const brew   = S.brews.find(b => b.id === brewId);
  const rec    = brew?.recipe_id ? S.recipes.find(r => r.id === brew.recipe_id) : null;
  let attColor = 'var(--text)', badgeHtml = '', yeastHtml = '';
  if (rec) {
    const yeast = (rec.ingredients || []).find(i => i.category === 'levure');
    const cy    = yeast ? S.catalog.find(c => c.name.toLowerCase() === yeast.name.toLowerCase() && c.category === 'levure') : null;
    const aMin  = cy?.attenuation_min, aMax = cy?.attenuation_max;
    if (aMin != null && aMax != null) {
      yeastHtml = t('brew.att_expected').replace('${min}', aMin).replace('${max}', aMax);
      if (att >= aMin && att <= aMax) {
        attColor  = 'var(--success)';
        badgeHtml = `<i class="fas fa-circle-check"></i> ${t('brew.att_in_range')}`;
      } else if (att < aMin) {
        attColor  = 'var(--amber)';
        badgeHtml = `<i class="fas fa-triangle-exclamation"></i> ${t('brew.att_low')}`;
      } else {
        attColor  = 'var(--info)';
        badgeHtml = `<i class="fas fa-circle-info"></i> ${t('brew.att_high')}`;
      }
    }
  }
  document.getElementById('bew-att-val').style.color   = attColor;
  document.getElementById('bew-att-badge').innerHTML   = badgeHtml;
  document.getElementById('bew-att-badge').style.color = attColor;
  document.getElementById('bew-att-yeast').textContent  = yeastHtml;
  row.style.display = 'flex';
}

// ── Efficacité cuve ──────────────────────────────────────────────────────────
// Retourne { eff, recipeEff } ou null si données insuffisantes.
// eff = (OG_mesurée - 1) × 1000 × vol / Σ(kg × GU) × 100
function _calcBrewEff(og, vol, recipeId) {
  if (!og || !vol || og <= 1) return null;
  const rec = recipeId ? S.recipes.find(r => r.id === recipeId) : null;
  if (!rec) return null;
  let maxExtract = 0;
  (rec.ingredients || []).filter(i => i.category === 'malt').forEach(m => {
    if (!m.quantity) return;
    let guVal = m.gu != null ? m.gu : null;
    if (guVal == null) {
      const cat = S.catalog.find(c => c.name.toLowerCase() === m.name.toLowerCase());
      if (cat?.gu != null) guVal = cat.gu;
    }
    if (guVal == null) return;
    maxExtract += (m.unit === 'kg' ? m.quantity : m.quantity / 1000) * guVal;
  });
  if (maxExtract <= 0) return null;
  const actualExtract = (og - 1) * 1000 * vol;
  const eff = actualExtract / maxExtract * 100;
  return { eff, recipeEff: rec.brewhouse_efficiency ?? null };
}

function _updateBewEffRow(og, vol, recipeId) {
  const row = document.getElementById('bew-eff-row');
  if (!row) return;
  const result = _calcBrewEff(og, vol, recipeId);
  if (!result) { row.style.display = 'none'; return; }
  const { eff, recipeEff } = result;
  document.getElementById('bew-eff-val').textContent = eff.toFixed(1) + '%';
  let effColor = 'var(--amber)', badgeHtml = '', targetHtml = '';
  if (recipeEff != null) {
    targetHtml = t('brew.eff_target').replace('${pct}', recipeEff);
    const delta = eff - recipeEff;
    if (Math.abs(delta) <= 3) {
      effColor  = 'var(--success)';
      badgeHtml = `<i class="fas fa-circle-check"></i> ${t('brew.eff_on_target')}`;
    } else if (delta < 0) {
      effColor  = 'var(--amber)';
      badgeHtml = `<i class="fas fa-triangle-exclamation"></i> ${t('brew.eff_below')}`;
    } else {
      effColor  = 'var(--info)';
      badgeHtml = `<i class="fas fa-circle-arrow-up"></i> ${t('brew.eff_above')}`;
    }
  }
  document.getElementById('bew-eff-val').style.color    = effColor;
  document.getElementById('bew-eff-badge').innerHTML    = badgeHtml;
  document.getElementById('bew-eff-badge').style.color  = effColor;
  document.getElementById('bew-eff-target').textContent = targetHtml;
  row.style.display = 'flex';
}

// ── Analyse OG manquante ──────────────────────────────────────────────────────

function _updateBewOGAnalysis(og, vol, recipeId) {
  const el = document.getElementById('bew-og-analysis');
  if (!el) return;
  if (!og || og <= 1 || !vol || !recipeId) { el.style.display = 'none'; return; }

  const rec  = recipeId ? S.recipes.find(r => r.id === recipeId) : null;
  if (!rec) { el.style.display = 'none'; return; }

  // _recTheoretical est défini dans script_recettes.html (même scope global)
  const theo = typeof _recTheoretical === 'function' ? _recTheoretical(rec) : null;
  if (!theo || og >= theo.og) { el.style.display = 'none'; return; }

  const shortfall = ((theo.og - og) * 1000).toFixed(1);
  const items     = [];
  let suggestion  = '';

  // Cause 1 : rendement inférieur à la cible
  const effResult = _calcBrewEff(og, vol, recipeId);
  const actualEff = effResult?.eff;
  const targetEff = rec.brewhouse_efficiency || 72;
  if (actualEff != null && targetEff - actualEff > 2) {
    const delta = (targetEff - actualEff).toFixed(1);
    items.push(`<div style="display:flex;align-items:baseline;gap:7px">
      <i class="fas fa-arrow-trend-down" style="color:#f87171;flex-shrink:0"></i>
      <span>${t('brew.og_cause_eff').replace('${actual}', actualEff.toFixed(1)).replace('${target}', targetEff.toFixed(0)).replace('${delta}', delta)}</span>
    </div>`);
    // Suggestion : volume idéal à ce rendement pour atteindre l'OG théorique
    if (theo.maxPts > 0) {
      const idealVol = theo.maxPts * (actualEff / 100) / ((theo.og - 1) * 1000);
      if (idealVol > 0.5 && vol - idealVol > 0.2) {
        suggestion = t('brew.og_suggestion')
          .replace('${eff}', actualEff.toFixed(0))
          .replace('${vol}', idealVol.toFixed(1))
          .replace('${reduce}', (vol - idealVol).toFixed(1));
      }
    }
  }

  // Cause 2 : volume supérieur au volume cible
  const targetVol = rec.volume || 20;
  if (vol > targetVol + 0.3) {
    items.push(`<div style="display:flex;align-items:baseline;gap:7px">
      <i class="fas fa-droplet" style="color:var(--info);flex-shrink:0"></i>
      <span>${t('brew.og_cause_vol').replace('${actual}', vol.toFixed(1)).replace('${target}', targetVol)}</span>
    </div>`);
  }

  el.innerHTML = `
    <div style="background:rgba(251,191,36,.08);border:1px solid rgba(251,191,36,.3);border-radius:8px;padding:10px 13px;font-size:.82rem;margin-top:4px">
      <div style="font-weight:700;color:var(--amber);margin-bottom:${items.length ? 8 : 0}px;display:flex;align-items:center;gap:7px">
        <i class="fas fa-triangle-exclamation"></i>
        ${t('brew.og_below_theo').replace('${og}', og.toFixed(3)).replace('${theo}', theo.og.toFixed(3)).replace('${pts}', shortfall)}
      </div>
      ${items.length ? `<div style="display:grid;gap:4px;color:var(--text)">${items.join('')}</div>` : ''}
      ${suggestion ? `<div style="margin-top:8px;padding-top:8px;border-top:1px solid rgba(251,191,36,.2);color:var(--info);display:flex;align-items:baseline;gap:7px">
        <i class="fas fa-lightbulb" style="flex-shrink:0"></i><span>${suggestion}</span></div>` : ''}
    </div>`;
  el.style.display = '';
}

// ── Stock insuffisant : ajout rapide à l'inventaire ───────────────────────────
let _swItems = [];

function toggleSwForm(idx) {
  const form = document.getElementById(`sw-form-${idx}`);
  form.style.display = form.style.display === 'none' ? '' : 'none';
}

async function quickAddToInventory(idx) {
  const item = _swItems[idx];
  const qty  = parseFloat(document.getElementById(`sw-qty-${idx}`).value) || 0;
  const unit = document.getElementById(`sw-unit-${idx}`).value;
  const btn  = document.getElementById(`sw-btn-${idx}`);
  btn.disabled = true;
  try {
    const existing = S.inventory.find(i =>
      i.name.toLowerCase() === item.name.toLowerCase() && i.category === item.category
    );
    if (existing) {
      await api('PUT', `/api/inventory/${existing.id}`, {
        ...existing,
        quantity: (existing.quantity || 0) + qty,
        unit,
      });
    } else {
      await api('POST', '/api/inventory', {
        name: item.name, category: item.category || 'autre', quantity: qty, unit,
      });
    }
    S.inventory = await api('GET', '/api/inventory');
    document.getElementById(`sw-form-${idx}`).style.display = 'none';
    btn.style.display = 'none';
    document.getElementById(`sw-done-${idx}`).style.display = '';
    toast(t('inv.added'), 'success');
  } catch(e) {
    btn.disabled = false;
    toast(t('common.error'), 'error');
  }
}

function showBrewAlert(msg, type='danger') {
  const el = document.getElementById('brew-alert');
  if (!msg) { el.classList.remove('show'); return; }
  el.className = `alert alert-${type} show`;
  el.textContent = msg;
}

async function confirmBrew(force = false) {
  const recipeId = parseInt(document.getElementById('brew-f-recipe').value);
  if (!recipeId) { showBrewAlert(t('rec.err_choose_recipe')); return; }
  const name = document.getElementById('brew-f-name').value.trim();
  if (!name) { showBrewAlert(t('rec.err_brew_name')); return; }

  const _cfVol = parseFloat(document.getElementById('brew-f-vol').value) || null;
  const payload = {
    recipe_id: recipeId,
    name, force,
    batch_number:  parseInt(document.getElementById('brew-f-number').value) || null,
    deduct_stock:  document.getElementById('brew-deduct').checked,
    brew_date:     document.getElementById('brew-f-date').value || null,
    volume_brewed: _cfVol,
    og:   parseFloat(document.getElementById('brew-f-og').value) || null,
    fg:   parseFloat(document.getElementById('brew-f-fg').value) || null,
    abv:  parseFloat(document.getElementById('brew-f-abv').value) || null,
    notes: document.getElementById('brew-f-notes').value.trim() || null,
    status: 'planned',
  };
  // Snapshot cost with current prices so future price changes don't affect this brew
  const _cfRecipe = S.recipes.find(r => r.id === recipeId);
  if (_cfRecipe) {
    const _cfCost = brewCost({ recipe_id: recipeId, volume_brewed: _cfVol });
    if (_cfCost) {
      payload.cost_snapshot           = _cfCost.total    != null ? +_cfCost.total.toFixed(4)    : null;
      payload.cost_per_liter_snapshot = _cfCost.perLiter != null ? +_cfCost.perLiter.toFixed(4) : null;
    }
  }
  try {
    const brew = await api('POST', '/api/brews', payload);
    S.brews.unshift(brew);
    // Refresh inventory after deduction
    S.inventory = await api('GET', '/api/inventory');
    renderInventaire();
    renderBrassins();
    closeModal('brew-modal');
    closeModal('stock-warn-modal');
    const stats = await api('GET', '/api/stats');
    updateNavBadges(stats);
    toast(t('brew.saved_toast'), 'success');
  } catch(err) {
    if (err.error === 'stock_insuffisant') {
      _swItems = err.items;
      const warnList = document.getElementById('stock-warn-list');
      warnList.innerHTML = err.items.map((i, idx) => `
        <div style="border-bottom:1px solid var(--border)">
          <div style="padding:8px 12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
            <strong style="flex:1;min-width:100px">${esc(i.name)}</strong>
            <span style="color:var(--danger);font-size:.82rem;flex-shrink:0">${t('inv.stock_needed')} ${i.needed} ${i.unit} — ${t('inv.stock_available')} ${i.available} ${i.unit}</span>
            <span id="sw-done-${idx}" style="display:none;color:var(--success);font-size:.82rem"><i class="fas fa-check-circle"></i> ${t('inv.added')}</span>
            <button id="sw-btn-${idx}" class="btn btn-sm" style="font-size:.75rem;padding:3px 10px;flex-shrink:0" onclick="toggleSwForm(${idx})">
              <i class="fas fa-plus"></i> ${t('brew.add_to_inv')}
            </button>
          </div>
          <div id="sw-form-${idx}" style="display:none;padding:6px 12px 12px;background:rgba(0,0,0,.12);border-top:1px solid var(--border)">
            <div style="display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap">
              <div>
                <div style="font-size:.72rem;color:var(--muted);margin-bottom:3px">${t('rec.ing_qty')}</div>
                <input id="sw-qty-${idx}" type="number" value="${i.needed}" min="0" step="0.001" style="width:88px;font-size:.85rem">
              </div>
              <div>
                <div style="font-size:.72rem;color:var(--muted);margin-bottom:3px">${t('rec.ing_unit')}</div>
                <select id="sw-unit-${idx}" style="font-size:.85rem">
                  ${['g','kg','L','mL','sachet','pièce'].map(u=>`<option ${u===i.unit?'selected':''}>${u}</option>`).join('')}
                </select>
              </div>
              <button class="btn btn-sm btn-success" style="font-size:.8rem" onclick="quickAddToInventory(${idx})">
                <i class="fas fa-check"></i> ${t('common.add')}
              </button>
            </div>
          </div>
        </div>`).join('');
      closeModal('brew-modal');
      openModal('stock-warn-modal');
    } else if (err.error === 'duplicate_batch_number') {
      showBrewAlert(t('brew.err_duplicate_batch').replace('${n}', err.detail));
    } else {
      showBrewAlert(t('common.error') + ' : ' + (err.detail || err.error || err.message || JSON.stringify(err)));
    }
  }
}

async function deleteBrew(id) {
  const brew = S.brews.find(b => b.id === id);
  const msg  = brew
    ? t('brew.confirm_delete_named').replace('${name}', brew.name)
    : t('brew.confirm_delete');
  if (!await confirmModal(msg, { danger: true })) return;
  try {
    await api('DELETE', `/api/brews/${id}`);
    S.brews = S.brews.filter(b => b.id !== id);
    renderBrassins();
    const stats = await api('GET', '/api/stats');
    updateNavBadges(stats);
    toast(t('brew.deleted'), 'success');
  } catch(e) { toast(t('common.delete') + ' — ' + t('common.error'), 'error'); }
}

function _validateBrewEditFields() {
  const checks = [
    { id: 'bew-og',        label: 'OG',              min: 1.000, max: 1.200, optional: true },
    { id: 'bew-fg',        label: 'FG',              min: 0.990, max: 1.200, optional: true },
    { id: 'bew-abv',       label: 'ABV (%)',         min: 0,     max: 30,    optional: true },
    { id: 'bew-vol',       label: t('brew.field_volume'),     min: 0.1, max: 1000, optional: true },
    { id: 'bew-ferm-time', label: t('rec.ferm_time_label'),   min: 1,   max: 730,  optional: true },
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

function showBrewEditAlert(msg, type='danger') {
  const el = document.getElementById('brew-edit-alert');
  if (!msg) { el.classList.remove('show'); return; }
  el.className = `alert alert-${type} show`;
  el.textContent = msg;
}

function openBrewEditModal(id) {
  const b = S.brews.find(x => x.id === id);
  if (!b) return;
  document.getElementById('bew-id').value     = b.id;
  document.getElementById('bew-name').value   = b.name || '';
  document.getElementById('bew-status').value = b.status || 'planned';
  document.getElementById('bew-date').value   = b.brew_date || '';
  document.getElementById('bew-vol').value    = b.volume_brewed || '';
  document.getElementById('bew-og').value     = b.og || '';
  document.getElementById('bew-fg').value     = b.fg || '';
  document.getElementById('bew-abv').value    = b.abv || '';
  document.getElementById('bew-notes').value      = b.notes || '';
  document.getElementById('bew-photos-url').value  = b.photos_url || '';
  const recipeDays = b.recipe_ferm_time;
  const inp = document.getElementById('bew-ferm-time');
  inp.value       = b.brew_ferm_time != null ? b.brew_ferm_time : '';
  inp.placeholder = recipeDays != null ? recipeDays : '14';
  const hint = document.getElementById('bew-ferm-time-hint');
  if (hint) hint.textContent = recipeDays != null
    ? `${recipeDays} j (${t('brew.ferm_time_recipe_hint')})`
    : '';
  _updateBewAttRow(b.og, b.fg);
  _updateBewEffRow(b.og, b.volume_brewed, b.recipe_id ?? null);
  showBrewEditAlert('');
  openModal('brew-edit-modal');
}

function toggleBrewQuickNote(id) {
  const wrap = document.getElementById(`brew-qnote-${id}`);
  const disp = document.getElementById(`brew-note-display-${id}`);
  const btn  = document.getElementById(`brew-qnote-btn-${id}`);
  if (!wrap) return;
  const open = wrap.style.display === 'none';
  wrap.style.display = open ? '' : 'none';
  if (disp) disp.style.display = open ? 'none' : (disp.textContent.trim() ? '' : 'none');
  if (btn)  btn.style.color = open ? 'var(--primary)' : '';
  if (open) {
    const ta = document.getElementById(`brew-qnote-ta-${id}`);
    if (ta) { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); }
  }
}

let _qnoteTimer = {};
async function saveBrewQuickNote(id) {
  const ta = document.getElementById(`brew-qnote-ta-${id}`);
  if (!ta) return;
  const notes = ta.value.trim() || null;
  const brew  = S.brews.find(b => b.id === id);
  if (!brew || brew.notes === notes) { toggleBrewQuickNote(id); return; }
  clearTimeout(_qnoteTimer[id]);
  try {
    await api('PATCH', `/api/brews/${id}`, { notes });
    brew.notes = notes;
    const disp = document.getElementById(`brew-note-display-${id}`);
    if (disp) { disp.textContent = notes || ''; disp.style.display = notes ? '' : 'none'; }
    toggleBrewQuickNote(id);
    toast(t('common.saved') || 'Enregistré', 'success');
  } catch(e) { toast(t('common.error'), 'error'); }
}

async function saveBrewEdit() {
  const id = parseInt(document.getElementById('bew-id').value);
  const fieldErrors = _validateBrewEditFields();
  if (fieldErrors.length) {
    showBrewEditAlert(t('rec.err_field_range').replace('${fields}', fieldErrors.join(', ')));
    return;
  }
  const _bewVol = parseFloat(document.getElementById('bew-vol').value) || null;
  const payload = {
    name:          document.getElementById('bew-name').value.trim() || null,
    status:        document.getElementById('bew-status').value,
    brew_date:     document.getElementById('bew-date').value || null,
    volume_brewed: _bewVol,
    og:            parseFloat(document.getElementById('bew-og').value) || null,
    fg:            parseFloat(document.getElementById('bew-fg').value) || null,
    abv:           parseFloat(document.getElementById('bew-abv').value) || null,
    notes:         document.getElementById('bew-notes').value.trim() || null,
    photos_url:    document.getElementById('bew-photos-url').value.trim() || null,
    ferm_time:     document.getElementById('bew-ferm-time').value !== ''
                     ? parseInt(document.getElementById('bew-ferm-time').value) || null
                     : null,
  };
  // Snapshot cost at save time so future price changes don't alter historical data
  const _bewBrew = S.brews.find(b => b.id === id);
  if (_bewBrew) {
    const _bewCost = brewCost({ ..._bewBrew, volume_brewed: _bewVol });
    if (_bewCost) {
      payload.cost_snapshot           = _bewCost.total          != null ? +_bewCost.total.toFixed(4)          : null;
      payload.cost_per_liter_snapshot = _bewCost.perLiter       != null ? +_bewCost.perLiter.toFixed(4)       : null;
    }
  }
  try {
    const updated = await api('PUT', `/api/brews/${id}`, payload);
    const idx = S.brews.findIndex(b => b.id === id);
    if (idx !== -1) S.brews[idx] = updated;
    renderBrassins();
    renderCalendar();
    closeModal('brew-edit-modal');
    toast(t('brew.updated'), 'success');
  } catch(e) {
    if (e.error === 'duplicate_batch_number') {
      showBrewEditAlert(t('brew.err_duplicate_batch').replace('${n}', e.detail));
    } else {
      showBrewEditAlert(t('common.error') + ' : ' + (e.detail || e.error || e.message || JSON.stringify(e)));
    }
  }
}

// ── Calcul optimal bouteilles 75cl / 33cl ────────────────────────────────────
// Retourne {n75, n33, wasteCl} pour minimiser le volume non embouteillé.
// Contrainte : au moins MIN75 bouteilles de 75cl (si le volume le permet).
function calcOptimalBottles(volL, min75 = 7) {
  const V = Math.round(volL * 100); // centilitres entiers
  if (V <= 0) return { n75: 0, n33: 0, wasteCl: 0 };
  const n75max = Math.floor(V / 75);
  const start  = Math.min(min75, n75max); // si V < 6×75cl on part du max possible
  let best = null;
  for (let n75 = start; n75 <= n75max; n75++) {
    const rem   = V - n75 * 75;
    const n33   = Math.floor(rem / 33);
    const waste = rem - n33 * 33;
    if (best === null || waste < best.wasteCl) best = { n75, n33, wasteCl: waste };
  }
  // Fallback si même start=0 n'a pas tourné (V < 75cl)
  if (!best) {
    const n33 = Math.floor(V / 33);
    best = { n75: 0, n33, wasteCl: V - n33 * 33 };
  }
  return best;
}

function updateAbBottleHint() {
  const volBrewed = parseFloat(document.getElementById('ab-brew-vol')?.value) || 0;
  const keg       = parseFloat(document.getElementById('ab-keg').value) || 0;
  const n33       = parseInt(document.getElementById('ab-33').value) || 0;
  const n75       = parseInt(document.getElementById('ab-75').value) || 0;
  const hintEl    = document.getElementById('ab-bottle-hint');
  if (!hintEl || volBrewed <= 0) { if (hintEl) hintEl.innerHTML = ''; return; }

  const volBottled = Math.max(0, volBrewed - keg);
  const accounted  = (n75 * 75 + n33 * 33) / 100; // litres
  const remainCl   = Math.round((volBottled - accounted) * 100);

  let remHtml;
  if (Math.abs(remainCl) <= 2) {
    remHtml = `<span style="color:var(--success)"><i class="fas fa-circle-check"></i> ${t('brew.ab_hint_exact')}</span>`;
  } else if (remainCl > 0) {
    remHtml = `<span style="color:var(--amber)"><i class="fas fa-triangle-exclamation"></i> ${t('brew.ab_hint_remaining')}: <strong>${remainCl} cl</strong></span>`;
  } else {
    remHtml = `<span style="color:var(--danger)"><i class="fas fa-circle-xmark"></i> ${t('brew.ab_hint_overflow')}: <strong>${Math.abs(remainCl)} cl</strong></span>`;
  }
  const totalHtml = `<span style="color:var(--muted)">${accounted.toFixed(2)} L ${t('brew.ab_hint_vol')} / ${volBottled.toFixed(1)} L</span>`;
  hintEl.innerHTML = `<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:.77rem;margin-top:6px;padding:6px 10px;background:var(--card2);border-radius:6px">${totalHtml}${remHtml}</div>`;
}

function abKegChanged() {
  const volBrewed = parseFloat(document.getElementById('ab-brew-vol')?.value) || 0;
  const keg       = parseFloat(document.getElementById('ab-keg').value) || 0;
  const volBottled = Math.max(0, volBrewed - keg);
  const opt = calcOptimalBottles(volBottled, 7);
  document.getElementById('ab-75').value = opt.n75;
  document.getElementById('ab-33').value = opt.n33;
  updateAbBottleHint();
}

let _abManualMode = false;

function toggleAbManual() {
  _abManualMode = !_abManualMode;
  const icon  = document.getElementById('ab-manual-icon');
  const label = document.getElementById('ab-manual-label');
  const btn   = document.getElementById('ab-manual-btn');
  if (_abManualMode) {
    if (icon)  { icon.className = 'fas fa-pencil'; }
    if (label) { label.textContent = t('brew.ab_manual'); label.removeAttribute('data-i18n'); }
    if (btn)   { btn.style.color = 'var(--amber)'; }
  } else {
    if (icon)  { icon.className = 'fas fa-rotate'; }
    if (label) { label.textContent = t('brew.ab_auto'); label.setAttribute('data-i18n', 'brew.ab_auto'); }
    if (btn)   { btn.style.color = 'var(--muted)'; }
  }
}

function ab75Changed() {
  const volBrewed  = parseFloat(document.getElementById('ab-brew-vol')?.value) || 0;
  const keg        = parseFloat(document.getElementById('ab-keg').value) || 0;
  const n75        = parseInt(document.getElementById('ab-75').value) || 0;
  if (!_abManualMode) {
    const volBottled = Math.max(0, volBrewed - keg);
    const remCl      = Math.round(volBottled * 100) - n75 * 75;
    document.getElementById('ab-33').value = remCl > 0 ? Math.floor(remCl / 33) : 0;
  }
  updateAbBottleHint();
}

function ab33Changed() {
  const volBrewed  = parseFloat(document.getElementById('ab-brew-vol')?.value) || 0;
  const keg        = parseFloat(document.getElementById('ab-keg').value) || 0;
  const n33        = parseInt(document.getElementById('ab-33').value) || 0;
  if (!_abManualMode) {
    const volBottled = Math.max(0, volBrewed - keg);
    const remCl      = Math.round(volBottled * 100) - n33 * 33;
    document.getElementById('ab-75').value = remCl > 0 ? Math.floor(remCl / 75) : 0;
  }
  updateAbBottleHint();
}

function openAfterBrewModal(id) {
  // Réinitialiser le mode manuel à chaque ouverture
  if (_abManualMode) toggleAbManual();
  const b = S.brews.find(x => x.id === id);
  if (!b) return;
  const recipe = b.recipe_id ? S.recipes.find(r => r.id === b.recipe_id) : null;
  document.getElementById('ab-brew-id').value  = b.id;
  document.getElementById('ab-recipe-id').value= b.recipe_id || '';
  document.getElementById('ab-name').value     = b.name;
  document.getElementById('ab-type').value     = recipe ? (recipe.style || '') : '';
  document.getElementById('ab-abv').value      = b.abv || '';
  document.getElementById('ab-keg').value      = '';
  document.getElementById('ab-brew-vol').value = b.volume_brewed || 0;
  // Calcul optimal bouteilles depuis le volume total
  const opt = calcOptimalBottles(b.volume_brewed || 0, 7);
  document.getElementById('ab-75').value = opt.n75;
  document.getElementById('ab-33').value = opt.n33;
  // Pre-fill description from brew notes (event info flows here)
  const _abNotes = b.notes || (recipe ? recipe.notes : '') || '';
  document.getElementById('ab-desc').value     = _abNotes;
  document.getElementById('ab-brew-date').value     = b.brew_date || '';
  document.getElementById('ab-bottling-date').value = new Date().toISOString().slice(0, 10);
  // Image : chercher via draft_id de la recette
  const draftImage = (() => {
    if (!recipe?.draft_id) return null;
    const draft = S.drafts.find(d => d.id === recipe.draft_id);
    return draft?.image || null;
  })();
  document.getElementById('ab-draft-image').value = draftImage || '';
  const abImgWrap = document.getElementById('ab-img-preview-wrap');
  const abImg     = document.getElementById('ab-img-preview');
  if (draftImage && abImgWrap && abImg) {
    abImg.src = draftImage;
    abImgWrap.style.display = '';
  } else if (abImgWrap) {
    abImgWrap.style.display = 'none';
  }
  updateAbBottleHint();
  openModal('after-brew-modal');
}

async function createBeerFromBrew() {
  const kegVal = document.getElementById('ab-keg').value;
  const kegLiters = kegVal !== '' ? (parseFloat(kegVal) || 0) : null;
  const payload = {
    name:       document.getElementById('ab-name').value,
    type:       document.getElementById('ab-type').value || null,
    abv:        parseFloat(document.getElementById('ab-abv').value) || null,
    stock_33cl: parseInt(document.getElementById('ab-33').value) || 0,
    stock_75cl: parseInt(document.getElementById('ab-75').value) || 0,
    keg_liters: kegLiters,
    description:  document.getElementById('ab-desc').value.trim() || null,
    brew_id:      parseInt(document.getElementById('ab-brew-id').value) || null,
    recipe_id:    parseInt(document.getElementById('ab-recipe-id').value) || null,
    brew_date:    document.getElementById('ab-brew-date').value || null,
    bottling_date:document.getElementById('ab-bottling-date').value || null,
    photo:        document.getElementById('ab-draft-image').value || null,
  };
  try {
    const beer = await api('POST', '/api/beers', payload);
    S.beers.unshift(beer);
    renderCave();
    closeModal('after-brew-modal');
    const stats = await api('GET', '/api/stats');
    updateNavBadges(stats);
    navigate('cave');
    toast(t('cave.beer_added_from_brew'), 'success');
  } catch(e) { toast(t('cave.err_add'), 'error'); }
}


// ── JOURNAL DE BRASSAGE HORODATÉ ─────────────────────────────────────────────

const _BBL_STEP_ICONS = {
  empatage:      'fa-temperature-half',
  ebullition:    'fa-fire-flame-curved',
  houblonnage:   'fa-leaf',
  refroid:       'fa-snowflake',
  ensemencement: 'fa-bacteria',
  transfert:     'fa-arrow-right-arrow-left',
  embouteillage: 'fa-bottle-water',
  divers:        'fa-circle-info',
};

async function openBrewLog(brewId, btn) {
  const brewName = btn?.dataset?.brewName || '';
  document.getElementById('bbl-brew-id').value = brewId;
  document.getElementById('bbl-title').textContent = t('brew.blog_title') + (brewName ? ' — ' + brewName : '');
  const now = new Date(); now.setSeconds(0, 0);
  document.getElementById('bbl-f-ts').value = new Date(now - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  document.getElementById('bbl-f-step').value = '';
  document.getElementById('bbl-f-note').value = '';
  document.getElementById('bbl-alert').style.display = 'none';
  openModal('brew-log-modal');
  await _bblRefresh(brewId);
}

async function _bblRefresh(brewId) {
  try {
    const rows = await api('GET', `/api/brews/${brewId}/log`);
    _bblRenderList(brewId, rows);
  } catch(e) { /* silent */ }
}

function _bblRenderList(brewId, rows) {
  const el = document.getElementById('bbl-list');
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div style="text-align:center;color:var(--muted);font-size:.88rem;padding:12px 0">${t('brew.blog_empty')}</div>`;
    return;
  }
  const stepLabel = v => {
    if (!v) return '';
    const key = 'brew.blog_step_' + {
      empatage:'mash', ebullition:'boil', houblonnage:'hop',
      refroid:'cool', ensemencement:'pitch', transfert:'transfer',
      embouteillage:'bottle', divers:'misc'
    }[v];
    return key ? t(key) : v;
  };
  el.innerHTML = `<div style="display:flex;flex-direction:column;gap:0">
    ${rows.map((r, i) => {
      const _d = new Date(r.ts.replace(' ', 'T'));
      const _p = n => String(n).padStart(2, '0');
      const dtStr = `${_d.getFullYear()}-${_p(_d.getMonth()+1)}-${_p(_d.getDate())} ${_p(_d.getHours())}:${_p(_d.getMinutes())}`;
      const icon  = r.step ? _BBL_STEP_ICONS[r.step] || 'fa-circle-info' : 'fa-pen-to-square';
      const badge = r.step ? `<span style="font-size:.68rem;background:var(--amber)22;color:var(--amber);border-radius:4px;padding:1px 6px;margin-left:6px;white-space:nowrap">${stepLabel(r.step)}</span>` : '';
      const sep   = i < rows.length - 1 ? 'border-bottom:1px solid var(--border)' : '';
      return `<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;${sep}">
        <div style="width:28px;height:28px;border-radius:50%;background:var(--amber)22;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px">
          <i class="fas ${icon}" style="font-size:.72rem;color:var(--amber)"></i>
        </div>
        <div style="flex:1;min-width:0">
          <div style="font-size:.78rem;color:var(--muted);white-space:nowrap">${dtStr}${badge}</div>
          <div style="font-size:.88rem;margin-top:2px;word-break:break-word">${esc(r.note)}</div>
        </div>
        <button class="btn btn-icon btn-danger btn-sm" style="padding:2px 6px;flex-shrink:0;margin-top:2px"
          onclick="deleteBrewLogEntry(${brewId},${r.id})"><i class="fas fa-trash" style="font-size:.7rem"></i></button>
      </div>`;
    }).join('')}
  </div>`;
}

async function saveBrewLogEntry() {
  const brewId  = parseInt(document.getElementById('bbl-brew-id').value);
  const tsVal   = document.getElementById('bbl-f-ts').value;
  const stepVal = document.getElementById('bbl-f-step').value;
  const noteVal = document.getElementById('bbl-f-note').value.trim();
  const alertEl = document.getElementById('bbl-alert');
  if (!tsVal || !noteVal) {
    alertEl.textContent = t('brew.blog_err_required');
    alertEl.style.display = 'block';
    return;
  }
  alertEl.style.display = 'none';
  try {
    await api('POST', `/api/brews/${brewId}/log`, { ts: tsVal, step: stepVal || null, note: noteVal });
    document.getElementById('bbl-f-note').value = '';
    // Advance time by 30 min for convenience
    const d = new Date(tsVal); d.setMinutes(d.getMinutes() + 30);
    document.getElementById('bbl-f-ts').value = new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    toast(t('brew.blog_saved'), 'success');
    await _bblRefresh(brewId);
    const idx = S.brews.findIndex(b => b.id === brewId);
    if (idx !== -1) { S.brews[idx].log_count = (S.brews[idx].log_count || 0) + 1; renderBrassins(); }
  } catch(e) { toast(t('brew.blog_err_save'), 'error'); }
}

async function deleteBrewLogEntry(brewId, entryId) {
  if (!await confirmModal(t('brew.blog_confirm_delete'), { danger: true })) return;
  try {
    await api('DELETE', `/api/brews/${brewId}/log/${entryId}`);
    toast(t('brew.blog_deleted'), 'success');
    await _bblRefresh(brewId);
    const idx = S.brews.findIndex(b => b.id === brewId);
    if (idx !== -1) { S.brews[idx].log_count = Math.max(0, (S.brews[idx].log_count || 1) - 1); renderBrassins(); }
  } catch(e) { toast(t('brew.blog_err_delete'), 'error'); }
}

// ── JOURNAL DE FERMENTATION MANUEL ───────────────────────────────────────────

async function openFermLog(brewId, btn) {
  const brewName = btn?.dataset?.brewName || '';
  document.getElementById('bfl-brew-id').value = brewId;
  document.getElementById('bfl-title').textContent = t('brew.ferm_log_title') + (brewName ? ' — ' + brewName : '');
  // Default datetime to now
  const now = new Date();
  now.setSeconds(0, 0);
  document.getElementById('bfl-f-date').value = new Date(now - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  document.getElementById('bfl-f-gravity').value = '';
  document.getElementById('bfl-f-temp').value = '';
  document.getElementById('bfl-f-notes').value = '';
  document.getElementById('bfl-alert').style.display = 'none';
  openModal('brew-ferm-log-modal');
  await _bflRefresh(brewId);
}

async function _bflRefresh(brewId) {
  try {
    const rows = await api('GET', `/api/brews/${brewId}/fermentation?source=manual`);
    _bflRenderList(brewId, rows);
  } catch(e) { /* silent */ }
}

function _bflRenderList(brewId, rows) {
  const el = document.getElementById('bfl-list');
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div style="text-align:center;color:var(--muted);font-size:.88rem;padding:12px 0" data-i18n="brew.ferm_log_empty">${t('brew.ferm_log_empty')}</div>`;
    return;
  }
  const sorted = [...rows].sort((a, b) => a.recorded_at < b.recorded_at ? -1 : 1);
  el.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:.85rem">
    <thead>
      <tr style="color:var(--muted);border-bottom:1px solid var(--border)">
        <th style="text-align:left;padding:4px 6px;font-weight:600">${t('common.date')}</th>
        <th style="text-align:center;padding:4px 6px;font-weight:600">SG</th>
        <th style="text-align:center;padding:4px 6px;font-weight:600">${t('brew.ferm_log_temp')}</th>
        <th style="text-align:left;padding:4px 6px;font-weight:600">${t('brew.field_notes')}</th>
        <th style="width:32px"></th>
      </tr>
    </thead>
    <tbody>
      ${sorted.map(r => `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:5px 6px;white-space:nowrap">${r.recorded_at.replace('T', ' ').slice(0, 16)}</td>
        <td style="text-align:center;padding:5px 6px;font-weight:600;color:var(--accent)">${r.gravity ? r.gravity.toFixed(3) : '—'}</td>
        <td style="text-align:center;padding:5px 6px">${r.temperature != null ? r.temperature + '°' : '—'}</td>
        <td style="padding:5px 6px;color:var(--muted)">${esc(r.notes || '')}</td>
        <td style="padding:5px 4px;text-align:center">
          <button class="btn btn-icon btn-danger btn-sm" style="padding:2px 6px" onclick="deleteFermEntry(${brewId},${r.id})"><i class="fas fa-trash" style="font-size:.7rem"></i></button>
        </td>
      </tr>`).join('')}
    </tbody>
  </table>`;
}

async function saveFermEntry() {
  const brewId = parseInt(document.getElementById('bfl-brew-id').value);
  const dateVal = document.getElementById('bfl-f-date').value;
  const gravityVal = document.getElementById('bfl-f-gravity').value;
  const tempVal = document.getElementById('bfl-f-temp').value;
  const notesVal = document.getElementById('bfl-f-notes').value.trim();
  const alertEl = document.getElementById('bfl-alert');

  if (!dateVal || !gravityVal) {
    alertEl.textContent = t('brew.ferm_log_err_required');
    alertEl.style.display = 'block';
    return;
  }
  const grav = parseFloat(gravityVal);
  const temp = tempVal !== '' ? parseFloat(tempVal) : null;
  if (isNaN(grav) || grav < 0.900 || grav > 1.200) {
    alertEl.textContent = `FG/OG (0.900–1.200)`;
    alertEl.style.display = 'block';
    return;
  }
  if (temp !== null && (isNaN(temp) || temp < -10 || temp > 80)) {
    alertEl.textContent = `${t('brew.field_temp')} (-10–80 °C)`;
    alertEl.style.display = 'block';
    return;
  }
  alertEl.style.display = 'none';

  try {
    await api('POST', `/api/brews/${brewId}/fermentation`, {
      recorded_at: dateVal,
      gravity: parseFloat(gravityVal),
      temperature: tempVal ? parseFloat(tempVal) : null,
      notes: notesVal || null,
    });
    document.getElementById('bfl-f-gravity').value = '';
    document.getElementById('bfl-f-temp').value = '';
    document.getElementById('bfl-f-notes').value = '';
    // Advance date by 1 day for convenience
    const d = new Date(dateVal);
    d.setDate(d.getDate() + 1);
    document.getElementById('bfl-f-date').value = d.toISOString().slice(0, 16);
    toast(t('brew.ferm_log_saved'), 'success');
    await _bflRefresh(brewId);
    // Refresh fermentation count in brew card
    const idx = S.brews.findIndex(b => b.id === brewId);
    if (idx !== -1) {
      S.brews[idx].fermentation_count = (S.brews[idx].fermentation_count || 0) + 1;
      renderBrassins();
    }
  } catch(e) { toast(t('brew.ferm_log_err_save'), 'error'); }
}

async function deleteFermEntry(brewId, readingId) {
  if (!await confirmModal(t('brew.ferm_log_confirm_delete'), { danger: true })) return;
  try {
    await api('DELETE', `/api/brews/${brewId}/fermentation/${readingId}`);
    toast(t('brew.ferm_log_deleted'), 'success');
    await _bflRefresh(brewId);
  } catch(e) { toast(t('brew.ferm_log_err_delete'), 'error'); }
}


// ══════════════════════════════════════════════════════════════════════════════
// ── ANALYTICS BRASSERIE ───────────────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════

let _baCharts = {};

function toggleBrewAnalytics() {
  const panel = document.getElementById('brew-analytics-panel');
  const btn   = document.getElementById('brew-analytics-btn');
  const open  = panel.style.display === 'none';
  panel.style.display = open ? '' : 'none';
  btn.classList.toggle('active', open);
  if (open) renderBrewAnalytics();
}

function _baDestroy() {
  Object.values(_baCharts).forEach(c => { try { c.destroy(); } catch(_) {} });
  _baCharts = {};
}

function renderBrewAnalytics() {
  _baDestroy();
  const all    = (S.brews || []).filter(b => !b.archived);
  const done   = all.filter(b => b.status === 'completed');

  // ── KPIs ─────────────────────────────────────────────────────────────────
  const successRate = all.length ? Math.round(done.length / all.length * 100) : null;
  const kpisEl = document.getElementById('brew-analytics-kpis');
  if (kpisEl) {
    const srColor = successRate == null ? 'var(--muted)' : successRate >= 90 ? 'var(--success)' : successRate >= 70 ? 'var(--amber)' : '#ef4444';
    const srTip   = successRate != null ? t('brew.analytics_success_tip').replace('${n}', done.length).replace('${total}', all.length) : '';
    kpisEl.innerHTML = successRate != null
      ? `<span title="${srTip}"><i class="fas fa-trophy" style="color:${srColor};font-size:.8rem"></i> <strong style="color:${srColor}">${successRate}%</strong> <span style="color:var(--muted)">${t('brew.analytics_success_rate')}</span></span>`
      : '';
  }

  const CHART_OPTS = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: '#888', font: { size: 10 } }, grid: { color: '#2a2a2a' } },
      y: { ticks: { color: '#888', font: { size: 10 } }, grid: { color: '#2a2a2a' }, beginAtZero: true },
    },
  };

  // ── Monthly volume (last 12 months) ───────────────────────────────────────
  const volCtx = document.getElementById('ba-vol-chart');
  if (volCtx) {
    const now    = new Date();
    const labels = [], volData = [];
    for (let i = 11; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      labels.push(d.toLocaleDateString(undefined, { month: 'short', year: '2-digit' }));
      const ym = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;
      volData.push(done.filter(b => (b.brew_date||'').startsWith(ym))
        .reduce((s, b) => s + (b.volume_brewed || 0), 0));
    }
    _baCharts.vol = new Chart(volCtx, {
      type: 'bar',
      data: { labels, datasets: [{ data: volData, backgroundColor: '#3b82f680', borderColor: '#3b82f6', borderWidth: 1.5 }] },
      options: { ...CHART_OPTS, scales: { ...CHART_OPTS.scales, y: { ...CHART_OPTS.scales.y, ticks: { ...CHART_OPTS.scales.y.ticks, callback: v => v > 0 ? v+'L' : v } } } },
    });
  }

  // ── Style leaderboard ─────────────────────────────────────────────────────
  const styleCtx = document.getElementById('ba-style-chart');
  if (styleCtx) {
    const styleCounts = {};
    all.forEach(b => {
      const style = b.recipe_style || (S.recipes.find(r => r.id === b.recipe_id)?.style) || null;
      if (style) styleCounts[style] = (styleCounts[style] || 0) + 1;
    });
    const top = Object.entries(styleCounts).sort((a, b) => b[1] - a[1]).slice(0, 7);
    if (top.length) {
      _baCharts.style = new Chart(styleCtx, {
        type: 'bar',
        data: {
          labels: top.map(([s]) => s),
          datasets: [{ data: top.map(([,n]) => n), backgroundColor: '#f59e0b80', borderColor: '#f59e0b', borderWidth: 1.5 }],
        },
        options: { ...CHART_OPTS, indexAxis: 'y',
          scales: { ...CHART_OPTS.scales, y: { ticks: { color: '#ccc', font: { size: 10 } }, grid: { color: '#2a2a2a' } } } },
      });
    } else {
      styleCtx.parentElement.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--muted);font-size:.8rem">${t('brew.analytics_no_data')}</div>`;
    }
  }

  // ── Efficiency trend (chronological, completed with measured OG) ──────────
  const effCtx = document.getElementById('ba-eff-chart');
  if (effCtx) {
    const withEff = done
      .filter(b => b.actual_efficiency != null && b.brew_date)
      .sort((a, b) => a.brew_date.localeCompare(b.brew_date));
    if (withEff.length >= 2) {
      const labels  = withEff.map(b => b.brew_date.slice(0,7));
      const data    = withEff.map(b => +b.actual_efficiency.toFixed(1));
      const avg     = data.reduce((s,v) => s+v, 0) / data.length;
      _baCharts.eff = new Chart(effCtx, {
        type: 'line',
        data: {
          labels,
          datasets: [
            { data, borderColor: '#10b981', backgroundColor: '#10b98130', fill: true, tension: 0.35, pointRadius: 3 },
            { data: data.map(() => +avg.toFixed(1)), borderColor: '#10b98155', borderDash: [4,4], pointRadius: 0, borderWidth: 1.5 },
          ],
        },
        options: { ...CHART_OPTS, scales: { ...CHART_OPTS.scales, y: { ...CHART_OPTS.scales.y, ticks: { ...CHART_OPTS.scales.y.ticks, callback: v => v+'%' } } } },
      });
    } else {
      effCtx.parentElement.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--muted);font-size:.8rem">${t('brew.analytics_eff_none')}</div>`;
    }
  }

  // ── Cost/litre trend ──────────────────────────────────────────────────────
  const cplCtx = document.getElementById('ba-cpl-chart');
  if (cplCtx) {
    const withCpl = done
      .filter(b => b.brew_date)
      .sort((a, b) => a.brew_date.localeCompare(b.brew_date))
      .map(b => ({ b, cost: brewCost(b) }))
      .filter(({ cost }) => cost?.perLiter != null);
    if (withCpl.length >= 2) {
      const labels   = withCpl.map(({ b }) => b.brew_date.slice(0,7));
      const data     = withCpl.map(({ cost }) => +cost.perLiter.toFixed(2));
      const avg      = data.reduce((s,v) => s+v, 0) / data.length;
      _baCharts.cpl  = new Chart(cplCtx, {
        type: 'line',
        data: {
          labels,
          datasets: [
            { data, borderColor: '#a78bfa', backgroundColor: '#a78bfa30', fill: true, tension: 0.35, pointRadius: 3 },
            { data: data.map(() => +avg.toFixed(2)), borderColor: '#a78bfa55', borderDash: [4,4], pointRadius: 0, borderWidth: 1.5 },
          ],
        },
        options: { ...CHART_OPTS, scales: { ...CHART_OPTS.scales, y: { ...CHART_OPTS.scales.y, ticks: { ...CHART_OPTS.scales.y.ticks, callback: v => v+'€' } } } },
      });
    } else {
      cplCtx.parentElement.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--muted);font-size:.8rem">${t('brew.analytics_no_data')}</div>`;
    }
  }
}

