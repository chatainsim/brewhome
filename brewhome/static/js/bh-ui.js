// ══════════════════════════════════════════════════════════════════════════════
// ── APPARENCE ────────────────────────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════
function applyAppearance() {
  const name  = appSettings.appName    || 'BrewHome';
  const color = appSettings.accentColor || null;
  const icon  = appSettings.appIcon    || null;

  // Titre de l'onglet
  document.title = name + ' — Gestion Brasserie';

  // Nav brand
  const brand = document.getElementById('nav-brand');
  if (brand) {
    if (icon) {
      brand.innerHTML = `<img src="${esc(icon)}" alt="${esc(name)}" style="height:34px;width:auto;object-fit:contain;border-radius:5px;vertical-align:middle;cursor:zoom-in" onclick="openAppIconLightbox()">`;
    } else {
      const safeName = esc(name);
      const mid = Math.ceil(safeName.length / 2);
      brand.innerHTML = `${safeName.slice(0, mid)}<span>${safeName.slice(mid)}</span>`;
    }
  }

  // Couleur d'accent
  if (color) {
    document.documentElement.style.setProperty('--amber', color);
  } else {
    document.documentElement.style.removeProperty('--amber');
  }

  // Favicon
  const fav = document.getElementById('app-favicon');
  if (fav) {
    fav.href = icon || '/static/favicon.png';
  }

  // Bouton thème (lune/soleil)
  const theme = document.documentElement.getAttribute('data-theme') || 'dark';
  const btn = document.getElementById('btn-theme');
  if (btn) {
    if (theme === 'light') {
      btn.innerHTML = '<i class="fas fa-moon"></i>';
      btn.title = 'Passer en thème sombre';
    } else {
      btn.innerHTML = '<i class="fas fa-sun"></i>';
      btn.title = 'Passer en thème clair';
    }
  }
}

function openAppIconLightbox() {
  const icon = appSettings.appIcon;
  if (!icon) return;
  const name = appSettings.appName || 'BrewHome';
  document.getElementById('beer-lightbox-img').src  = icon;
  document.getElementById('beer-lightbox-img').alt  = name;
  document.getElementById('beer-lightbox-name').textContent = name;
  const lb = document.getElementById('beer-lightbox');
  lb.style.display = 'flex';
}

function renderSettingsApparence() {
  const name  = appSettings.appName    || '';
  const color = appSettings.accentColor || '#ff9500';
  const icon  = appSettings.appIcon    || null;

  document.getElementById('app-name-input').value    = name;
  document.getElementById('app-accent-color').value  = color;

  const prev = document.getElementById('app-icon-preview');
  if (prev) prev.innerHTML = icon
    ? `<img src="${icon}" style="width:100%;height:100%;object-fit:contain">`
    : '<i class="fas fa-image"></i>';

  const removeBtn = document.getElementById('app-icon-remove-btn');
  if (removeBtn) removeBtn.style.display = icon ? '' : 'none';
}

async function saveApparence() {
  const name  = document.getElementById('app-name-input').value.trim();
  const color = document.getElementById('app-accent-color').value;
  appSettings.appName     = name  || null;
  appSettings.accentColor = color !== '#ff9500' ? color : null;
  saveSettings();
  try {
    await api('PUT', '/api/app-settings', {
      app_name:     appSettings.appName     || null,
      accent_color: appSettings.accentColor || null,
      app_icon:     appSettings.appIcon     || null,
    });
  } catch(e) { toast(t('common_err.save_server'), 'error'); return; }
  applyAppearance();
  toast(t('settings.toast.appearance_saved'), 'success');
}

function setAccentPreset(color) {
  document.getElementById('app-accent-color').value = color;
}

function previewAppIcon(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    const img = new Image();
    img.onload = () => {
      const size = 256;
      const canvas = document.createElement('canvas');
      canvas.width = size; canvas.height = size;
      const ctx = canvas.getContext('2d');
      const scale = Math.min(size / img.width, size / img.height);
      const w = img.width * scale, h = img.height * scale;
      ctx.drawImage(img, (size - w) / 2, (size - h) / 2, w, h);
      const b64 = canvas.toDataURL('image/png');
      appSettings.appIcon = b64;
      const prev = document.getElementById('app-icon-preview');
      if (prev) prev.innerHTML = `<img src="${b64}" style="width:100%;height:100%;object-fit:contain">`;
      const removeBtn = document.getElementById('app-icon-remove-btn');
      if (removeBtn) removeBtn.style.display = '';
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
  event.target.value = '';
}

function removeAppIcon() {
  delete appSettings.appIcon;
  saveSettings();
  api('PUT', '/api/app-settings', { app_icon: null }).catch(e => console.warn('[BrewHome] icon reset failed:', e));
  const prev = document.getElementById('app-icon-preview');
  if (prev) prev.innerHTML = '<i class="fas fa-image"></i>';
  const removeBtn = document.getElementById('app-icon-remove-btn');
  if (removeBtn) removeBtn.style.display = 'none';
}

function togglePat(inputId) {
  const el = document.getElementById(inputId);
  el.type = el.type === 'password' ? 'text' : 'password';
}

// Pour les providers custom (Gitea/Forgejo), les fetch passent par le proxy Flask
// afin d'éviter les restrictions CORS du navigateur.
async function _gitFetch(url, options, isCustom) {
  if (!isCustom) return fetch(url, options);
  const authHeader = (options.headers || {})['Authorization'] || '';
  const pat  = authHeader.replace(/^Bearer\s+/i, '');
  const body = options.body !== undefined ? JSON.parse(options.body) : undefined;
  return fetch('/api/git-proxy', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, method: options.method || 'GET', pat, body }),
  });
}

// binary=true : content est déjà du base64 pur (image), pas besoin d'encoder
// apiBase : URL de base de l'API (ex: 'https://api.github.com' ou 'https://gitea.example.com/api/v1')
// Retourne { skipped: true } si le contenu est identique, sinon la réponse de l'API.
async function pushToGithub(repo, pat, branch, filePath, content, message, binary = false, apiBase = 'https://api.github.com') {
  const base = `${apiBase}/repos/${repo}/contents/${filePath}`;
  const isGithub = apiBase === 'https://api.github.com';
  const isCustom = !isGithub;
  const headers = {
    'Authorization': `Bearer ${pat}`,
    'Accept': isGithub ? 'application/vnd.github+json' : 'application/json',
    'Content-Type': 'application/json',
  };

  // Récupérer le fichier existant : SHA (pour le PUT) + contenu base64 (pour comparer)
  let sha, existingB64;
  try {
    const getRes = await _gitFetch(`${base}?ref=${encodeURIComponent(branch)}`, { headers, cache: 'no-store' }, isCustom);
    if (getRes.ok) {
      const data = await getRes.json();
      sha = data.sha;
      existingB64 = (data.content || '').replace(/\s/g, ''); // GitHub/Gitea insèrent des \n dans le base64
    }
  } catch(_) {}

  // Encoder le nouveau contenu
  const encoded = binary ? content : btoa(unescape(encodeURIComponent(content)));

  // Comparer directement le base64 — skip si identique
  if (existingB64 && existingB64 === encoded) return { skipped: true };

  const body = { message, content: encoded, branch };
  if (sha) body.sha = sha;

  // Gitea/Forgejo : POST pour créer (pas de SHA), PUT pour mettre à jour (SHA requis)
  // GitHub : PUT gère les deux cas
  const method = isCustom && !sha ? 'POST' : 'PUT';

  const putRes = await _gitFetch(base, { method, headers, body: JSON.stringify(body) }, isCustom);
  if (!putRes.ok) {
    const err = await putRes.json().catch(() => ({ message: putRes.statusText }));
    throw new Error(err.message || putRes.statusText);
  }
  return putRes.json();
}

// Extrait le base64 pur et l'extension depuis un data URL (ex: data:image/jpeg;base64,...)
function _parsePhotoDataUrl(dataUrl) {
  if (!dataUrl) return null;
  const m = dataUrl.match(/^data:image\/(\w+);base64,(.+)$/s);
  if (!m) return null;
  const ext = m[1] === 'jpeg' ? 'jpg' : m[1];
  return { ext, b64: m[2] };
}

// esc() est définie dans bh-core.js — alias pour compatibilité interne
const _vEsc = esc;

function _vDate(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleDateString(_lang || 'fr', { day:'2-digit', month:'long', year:'numeric' }); }
  catch(_) { return iso; }
}

function generateVitrineHtml(beers, photoMap, iconPath) {
  const date   = new Date().toLocaleDateString(_lang || 'fr', { day:'2-digit', month:'long', year:'numeric' });
  const total33  = beers.reduce((s, b) => s + (b.stock_33cl  || 0), 0);
  const total75  = beers.reduce((s, b) => s + (b.stock_75cl  || 0), 0);
  const totalKeg = beers.reduce((s, b) => s + (b.keg_liters  || 0), 0);

  const makeCard = b => {
    const photo  = photoMap && photoMap[b.id];
    const imgSrc = photo ? `images/beer-${b.id}.${photo.ext}` : null;
    const abv    = b.abv != null ? `${parseFloat(b.abv).toFixed(1)} %` : null;
    const s33    = b.stock_33cl  ?? 0;
    const s75    = b.stock_75cl  ?? 0;
    const i33    = b.initial_33cl > 0 ? b.initial_33cl : 0;
    const i75    = b.initial_75cl > 0 ? b.initial_75cl : 0;
    const pct33  = i33 > 0 ? Math.round(Math.min(100, s33 / i33 * 100)) : -1;
    const pct75  = i75 > 0 ? Math.round(Math.min(100, s75 / i75 * 100)) : -1;
    const kegL   = b.keg_liters          ?? 0;
    const kegI   = b.keg_initial_liters  ?? 0;
    const hasKeg = kegL > 0 || kegI > 0;
    const pctKeg = kegI > 0 ? Math.round(Math.min(100, kegL / kegI * 100)) : -1;

    const cls33  = s33 === 0 ? 'zero' : pct33 >= 0 && pct33 <= 40 ? 'low' : 'ok';
    const cls75  = s75 === 0 ? 'zero' : pct75 >= 0 && pct75 <= 40 ? 'low' : 'ok';

    const stockItem = (count, label, cls, pct) => `
      <div class="si ${cls}">
        <div class="si-n">${count > 0 ? count : '–'}</div>
        <div class="si-l">${label}</div>
        ${count > 0 && pct >= 0 ? `<div class="si-bar"><div class="si-fill" style="width:${pct}%"></div></div>` : ''}
        ${count === 0 ? `<div class="si-empty">épuisé</div>` : ''}
      </div>`;

    const kegBarColor = kegL === 0 ? '#333' : pctKeg >= 0 && pctKeg <= 40 ? '#f59e0b' : 'var(--amber)';
    const kegBlock = hasKeg ? `
      <div class="keg-row">
        <span class="keg-icon">🛢</span>
        <div class="keg-info">
          <span class="keg-val">${kegL % 1 === 0 ? kegL : kegL.toFixed(1)} L</span>
          <span class="keg-lbl">en fût</span>
          ${kegI > 0 && kegI > kegL ? `<div class="keg-bar"><div class="keg-fill" style="width:${pctKeg}%;background:${kegBarColor}"></div></div>` : ''}
        </div>
        ${kegI > 0 ? `<span class="keg-init">/ ${kegI % 1 === 0 ? kegI : kegI.toFixed(1)} L</span>` : ''}
      </div>` : '';

    const brewInfo = [
      b.brew_date        ? `🍺 Brassé le ${_vDate(b.brew_date)}`          : '',
      b.bottling_date    ? `🍾 Embouteillé le ${_vDate(b.bottling_date)}` : '',
      b.recipe_name      ? (b.recipe_id ? `<a class="recipe-link" href="recipes/${b.recipe_id}.html">📋 ${_vEsc(b.recipe_name)}</a>` : `📋 ${_vEsc(b.recipe_name)}`) : '',
      b.brew_photos_url  ? `<a class="recipe-link" href="${_vEsc(b.brew_photos_url)}" target="_blank" rel="noopener">📷 Photos</a>` : '',
    ].filter(Boolean);

    return `
    <div class="card" id="beer-${b.id}">
      ${imgSrc
        ? `<img class="card-img" src="${imgSrc}" loading="lazy" alt="${_vEsc(b.name)}" onclick="openLb(this,'${_vEsc(b.name)}')">`
        : `<div class="card-img-ph">🍺</div>`}
      <div class="card-body">
        <div class="card-name">${_vEsc(b.name)}</div>
        ${b.type ? `<div class="card-type">${_vEsc(b.type)}</div>` : ''}
        ${abv    ? `<div class="card-abv">ABV <strong>${abv}</strong></div>` : ''}
        ${b.refermentation ? `<div class="referm-badge">🔄 ${(() => {
          if (!b.bottling_date || !b.refermentation_days) return 'Refermentation en cours';
          const dEnd  = new Date(b.bottling_date + 'T00:00:00');
          dEnd.setDate(dEnd.getDate() + b.refermentation_days);
          const today = new Date(); today.setHours(0,0,0,0);
          const delta = Math.round((dEnd - today) / 86400000);
          if (delta > 0)  return `Prête dans ${delta} j (${_vDate(_ymd(dEnd))})`;
          if (delta === 0) return 'Prête aujourd\'hui ! 🎉';
          return `Prête depuis ${-delta} j`;
        })()}</div>` : ''}
        ${kegBlock}
        <div class="stock-row">
          ${stockItem(s33, '33 cl', cls33, pct33)}
          <div class="stock-sep"></div>
          ${stockItem(s75, '75 cl', cls75, pct75)}
        </div>
        ${b.origin      ? `<div class="card-origin">📍 ${_vEsc(b.origin)}</div>` : ''}
        ${b.description ? `<p class="card-desc">${_vEsc(b.description)}</p>` : ''}
        ${brewInfo.length ? `<div class="card-foot">${brewInfo.join('<span class="sep">·</span>')}</div>` : ''}
        ${appSettings.appName ? `<div class="card-brand">${_vEsc(appSettings.appName)}</div>` : ''}
      </div>
    </div>`;
  };
  const inStock   = beers.filter(b => (b.stock_33cl||0) + (b.stock_75cl||0) + (b.keg_liters||0) > 0);
  const exhausted = beers.filter(b => (b.stock_33cl||0) + (b.stock_75cl||0) + (b.keg_liters||0) === 0);
  const cardsActive    = inStock.map(makeCard).join('');
  const cardsExhausted = exhausted.map(makeCard).join('');

  return `<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ma cave à bières</title>
<style>
:root{--bg:#0f0f0f;--card:#1a1a1a;--border:#272727;--text:#e8e0d0;--muted:#888;--amber:${appSettings.accentColor || '#f5a623'};--hop:#7ec845;--info:#60a5fa}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
header{text-align:center;padding:48px 16px 28px}
h1{font-size:2.2rem;font-weight:900;color:var(--amber);letter-spacing:-.03em;margin-bottom:6px}
.subtitle{font-size:.85rem;color:var(--muted)}
.stats{display:flex;justify-content:center;gap:32px;margin:22px 0 40px;flex-wrap:wrap}
.stat-val{font-size:1.7rem;font-weight:800;color:var(--amber);line-height:1}
.stat-lbl{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-top:3px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:22px;max-width:1200px;margin:0 auto;padding:0 16px 60px}
.card{background:var(--card);border:1px solid var(--border);border-radius:14px;overflow:hidden;display:flex;flex-direction:column;transition:transform .18s,box-shadow .18s}
.card:hover{transform:translateY(-4px);box-shadow:0 16px 48px rgba(0,0,0,.55)}
.card-img{width:100%;height:210px;object-fit:cover;display:block;cursor:zoom-in;transition:opacity .15s}.card-img:hover{opacity:.9}
.card-img-ph{height:110px;background:linear-gradient(135deg,#1e1e1e,#262626);display:flex;align-items:center;justify-content:center;font-size:3rem;color:#333}
#lb{display:none;position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:9999;cursor:zoom-out;align-items:center;justify-content:center;flex-direction:column;gap:14px;padding:20px}
#lb.open{display:flex}
#lb img{max-width:92vw;max-height:82vh;object-fit:contain;border-radius:10px;box-shadow:0 24px 80px rgba(0,0,0,.7)}
#lb-caption{font-size:.9rem;color:#ccc;max-width:80vw;text-align:center}
#lb-close{position:fixed;top:16px;right:20px;font-size:1.6rem;color:#aaa;cursor:pointer;background:none;border:none;line-height:1;padding:4px 8px}
#lb-close:hover{color:#fff}
.card-body{padding:16px;flex:1;display:flex;flex-direction:column;gap:9px}
.card-name{font-size:1.08rem;font-weight:700;line-height:1.3}
.card-type{font-size:.79rem;color:var(--amber);font-style:italic}
.card-abv{font-size:.8rem;color:#999}
.card-abv strong{color:var(--hop);font-size:.95rem}
.stock-row{display:flex;background:#111;border-radius:10px;overflow:hidden;border:1px solid var(--border)}
.stock-sep{width:1px;background:var(--border);flex-shrink:0}
.si{flex:1;padding:10px 12px;display:flex;flex-direction:column;align-items:center;gap:2px}
.si-n{font-size:2rem;font-weight:800;line-height:1}
.si-l{font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.si-bar{width:80%;height:4px;background:#2a2a2a;border-radius:2px;margin-top:5px}
.si-fill{height:100%;border-radius:2px}
.si-empty{font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin-top:2px}
.si.ok  .si-n{color:#4ade80}.si.ok  .si-fill{background:#4ade80}
.si.low .si-n{color:#f59e0b}.si.low .si-fill{background:#f59e0b}
.si.zero .si-n{color:#333}.si.zero .si-empty{color:#c0392b}
.card-origin{font-size:.75rem;color:var(--muted)}
.card-desc{font-size:.82rem;color:#aaa;line-height:1.55;flex:1}
.card-foot{font-size:.71rem;color:#555;display:flex;gap:6px;flex-wrap:wrap;margin-top:2px;padding-top:8px;border-top:1px solid var(--border);align-items:center}
.sep{color:#333}
a.recipe-link{color:var(--amber);text-decoration:none;font-weight:500}
a.recipe-link:hover{text-decoration:underline}
.empty{text-align:center;color:var(--muted);padding:80px 20px;grid-column:1/-1}
footer{text-align:center;padding:20px;font-size:.74rem;color:#444;border-top:1px solid var(--border)}
.appname{font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.18em;color:var(--amber);opacity:.75;margin-bottom:10px}
.card-brand{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:var(--amber);opacity:.45;text-align:right;margin-top:4px}
.keg-row{display:flex;align-items:center;gap:10px;background:rgba(245,166,35,.07);border:1px solid rgba(245,166,35,.2);border-radius:9px;padding:8px 12px}
.keg-icon{font-size:1.15rem;line-height:1}
.keg-info{flex:1;display:flex;flex-wrap:wrap;align-items:center;gap:3px 8px}
.keg-val{font-size:1.05rem;font-weight:800;color:var(--amber)}
.keg-lbl{font-size:.66rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.keg-bar{width:100%;height:4px;background:#2a2a2a;border-radius:2px;margin-top:2px}
.keg-fill{height:100%;border-radius:2px}
.keg-init{font-size:.7rem;color:var(--muted);white-space:nowrap}
.referm-badge{display:inline-flex;align-items:center;gap:5px;font-size:.73rem;font-weight:600;color:#60a5fa;background:rgba(96,165,250,.1);border:1px solid rgba(96,165,250,.25);border-radius:20px;padding:3px 10px}
.section-divider{max-width:1200px;margin:40px auto 28px;padding:0 16px;display:flex;align-items:center;gap:14px}
.section-divider-line{flex:1;height:1px;background:var(--border)}
.section-divider-label{font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#444;white-space:nowrap}
.grid-exhausted .card{opacity:.5;filter:grayscale(.6)}
.grid-exhausted .card:hover{opacity:.75;filter:grayscale(.3)}
</style>
</head>
<body>
<header>
  ${iconPath ? `<img src="${iconPath}" alt="" style="width:56px;height:56px;object-fit:contain;border-radius:12px;margin-bottom:8px;display:block;margin-left:auto;margin-right:auto">` : ''}
  ${appSettings.appName ? `<div class="appname">${_vEsc(appSettings.appName)}</div>` : ''}
  <h1>🍺 Ma cave à bières</h1>
  <div class="subtitle">Mise à jour le ${date}</div>
  <div class="stats">
    <div><div class="stat-val">${beers.length}</div><div class="stat-lbl">Bières</div></div>
    <div><div class="stat-val">${total33}</div><div class="stat-lbl">Bouteilles 33 cl</div></div>
    <div><div class="stat-val">${total75}</div><div class="stat-lbl">Bouteilles 75 cl</div></div>
    ${totalKeg > 0 ? `<div><div class="stat-val">${totalKeg % 1 === 0 ? totalKeg : totalKeg.toFixed(1)}</div><div class="stat-lbl">Litres en fût</div></div>` : ''}
  </div>
</header>
${inStock.length === 0 && exhausted.length === 0
  ? '<div class="grid"><div class="empty">Aucune bière disponible pour le moment.</div></div>'
  : `<div class="grid">${cardsActive}</div>
     ${exhausted.length ? `
     <div class="section-divider">
       <div class="section-divider-line"></div>
       <div class="section-divider-label">Épuisées (${exhausted.length})</div>
       <div class="section-divider-line"></div>
     </div>
     <div class="grid grid-exhausted">${cardsExhausted}</div>` : ''}`
}
<footer>Généré par ${_vEsc(appSettings.appName || 'BrewHome')}</footer>

<div id="lb" onclick="closeLb()">
  <button id="lb-close" onclick="closeLb()" title="${t('common.close')}">✕</button>
  <img id="lb-img" src="" alt="" onclick="event.stopPropagation();closeLb()" style="cursor:zoom-out">
  <div id="lb-caption"></div>
</div>
<script>
function openLb(el, name) {
  document.getElementById('lb-img').src = el.src;
  document.getElementById('lb-caption').textContent = name;
  document.getElementById('lb').classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeLb() {
  document.getElementById('lb').classList.remove('open');
  document.body.style.overflow = '';
}
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  const lb = document.getElementById('lb');
  if (lb?.classList.contains('open')) { closeLb(); return; }
});
<\/script>
</body>
</html>`;
}

// ── Global search ─────────────────────────────────────────────────────────────
let _gsActive = false;
let _gsIdx = -1;

function openGlobalSearch() {
  const ov = document.getElementById('global-search-overlay');
  if (!ov) return;
  _gsActive = true;
  _gsIdx = -1;
  ov.style.display = 'flex';
  const inp = document.getElementById('global-search-input');
  if (inp) { inp.value = ''; inp.placeholder = t('search.placeholder'); inp.focus(); }
  document.getElementById('global-search-results').innerHTML = '';
  document.getElementById('global-search-hint').textContent = t('search.hint');
}

function closeGlobalSearch() {
  const ov = document.getElementById('global-search-overlay');
  if (!ov) return;
  _gsActive = false;
  ov.style.display = 'none';
}

function runGlobalSearch() {
  const q = (document.getElementById('global-search-input')?.value || '').toLowerCase().trim();
  const res = document.getElementById('global-search-results');
  if (!res) return;
  _gsIdx = -1;
  if (!q) { res.innerHTML = ''; return; }

  const esc2 = s => String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const sections = [];

  const recs = (S.recipes || []).filter(r =>
    r.name?.toLowerCase().includes(q) || r.style?.toLowerCase().includes(q)
  ).slice(0, 5);
  if (recs.length) sections.push({ label: t('search.section_recipes'), items: recs.map(r => ({
    icon: 'fa-scroll', title: r.name, sub: r.style || '', action: () => { navigate('recettes'); loadRecipeForm(r.id); }
  }))});

  const beers = (S.beers || []).filter(b =>
    b.name?.toLowerCase().includes(q) || b.type?.toLowerCase().includes(q) || b.recipe_name?.toLowerCase().includes(q)
  ).slice(0, 5);
  if (beers.length) sections.push({ label: t('search.section_cave'), items: beers.map(b => ({
    icon: 'fa-beer-mug-empty', title: b.name, sub: b.type || b.recipe_name || '', action: () => { navigate('cave'); openBeerDetail(b.id); }
  }))});

  const invItems = (S.inventory || []).filter(i =>
    i.name?.toLowerCase().includes(q) || i.category?.toLowerCase().includes(q)
  ).slice(0, 4);
  if (invItems.length) sections.push({ label: t('search.section_inv'), items: invItems.map(i => ({
    icon: 'fa-boxes-stacked', title: i.name, sub: i.category || '', action: () => { navigate('inventaire'); openInvModal(i); }
  }))});

  const brews = (S.brews || []).filter(b =>
    b.name?.toLowerCase().includes(q) || b.recipe_name?.toLowerCase().includes(q)
  ).slice(0, 4);
  if (brews.length) sections.push({ label: t('search.section_brews'), items: brews.map(b => ({
    icon: 'fa-fire-burner', title: b.name || b.recipe_name || '', sub: b.status || '', action: () => { navigate('brassins'); }
  }))});

  const TASTING_FIELDS = ['taste_overall','taste_aroma','taste_appearance','taste_flavor','taste_bitterness','taste_mouthfeel','taste_finish'];
  const tastings = (S.beers || [])
    .map(b => {
      const matchedField = TASTING_FIELDS.find(f => b[f]?.toLowerCase().includes(q));
      if (!matchedField) return null;
      return { b, snippet: b[matchedField] };
    }).filter(Boolean).slice(0, 4);
  if (tastings.length) sections.push({ label: t('search.section_tasting'), items: tastings.map(({ b, snippet }) => ({
    icon: 'fa-wine-glass', title: b.name,
    sub: snippet.slice(0, 60) + (snippet.length > 60 ? '…' : ''),
    action: () => { navigate('cave'); openTastingModal(b.id); }
  }))});

  if (!sections.length) {
    const noRes = t('search.no_results').replace('${q}', esc2(q));
    res.innerHTML = '<div style="padding:20px 18px;color:var(--muted);font-size:.9rem">' + noRes + '</div>';
    return;
  }

  let html = '';
  let itemIdx = 0;
  sections.forEach(sec => {
    html += '<div style="padding:6px 18px 2px;font-size:.72rem;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em">' + esc2(sec.label) + '</div>';
    sec.items.forEach(item => {
      html += '<div class="gs-item" data-idx="' + itemIdx + '" style="display:flex;align-items:center;gap:12px;padding:9px 18px;cursor:pointer;border-radius:6px;margin:0 4px" onclick="_gsPickIdx(' + itemIdx + ')">';
      html += '<i class="fas ' + item.icon + '" style="color:var(--muted);width:16px;text-align:center;flex-shrink:0"></i>';
      html += '<div style="flex:1;min-width:0">';
      html += '<div style="font-size:.9rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + esc2(item.title) + '</div>';
      html += item.sub ? '<div style="font-size:.75rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + esc2(item.sub) + '</div>' : '';
      html += '</div></div>';
      itemIdx++;
    });
  });

  res.innerHTML = html;
  res._actions = sections.flatMap(s => s.items.map(i => i.action));
  _gsHighlight(-1);
}

function _gsPickIdx(idx) {
  const res = document.getElementById('global-search-results');
  if (!res?._actions?.[idx]) return;
  closeGlobalSearch();
  res._actions[idx]();
}

function _gsHighlight(idx) {
  const items = document.querySelectorAll('#global-search-results .gs-item');
  items.forEach((el, i) => {
    el.style.background = i === idx ? 'var(--bg2)' : '';
  });
  _gsIdx = idx;
  if (idx >= 0 && items[idx]) items[idx].scrollIntoView({ block: 'nearest' });
}

function handleGlobalSearchKey(e) {
  const items = document.querySelectorAll('#global-search-results .gs-item');
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    _gsHighlight(Math.min(_gsIdx + 1, items.length - 1));
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    _gsHighlight(Math.max(_gsIdx - 1, 0));
  } else if (e.key === 'Enter') {
    if (_gsIdx >= 0) _gsPickIdx(_gsIdx);
    else if (items.length) _gsPickIdx(0);
  } else if (e.key === 'Escape') {
    closeGlobalSearch();
  }
}

// ── Keyboard shortcuts help ────────────────────────────────────────────────────
function openKbdHelp() {
  const ov = document.getElementById('kbd-help-overlay');
  if (!ov) return;
  document.getElementById('kbd-help-title').textContent = t('kbd.title');
  const kbdRow = (k, label) => '<div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0;gap:8px">'
    + '<span style="color:var(--muted);font-size:.82rem">' + label + '</span>'
    + '<kbd style="font-size:.72rem;padding:2px 7px;background:var(--bg2);border:1px solid var(--border);border-radius:5px;white-space:nowrap;flex-shrink:0">' + k + '</kbd>'
    + '</div>';
  document.getElementById('kbd-help-body').innerHTML =
    kbdRow('N', t('kbd.new_brew')) +
    kbdRow('/ or Ctrl+K', t('kbd.search')) +
    kbdRow('?', t('kbd.help')) +
    kbdRow('Ctrl+S', t('kbd.save_recipe')) +
    kbdRow('Esc', t('kbd.close_modal')) +
    kbdRow('Alt+1', t('kbd.page_dashboard')) +
    kbdRow('Alt+2', t('kbd.page_inventaire')) +
    kbdRow('Alt+3', t('kbd.page_recettes')) +
    kbdRow('Alt+4', t('kbd.page_brassins')) +
    kbdRow('Alt+5', t('kbd.page_cave')) +
    kbdRow('Alt+6', t('kbd.page_kegs')) +
    kbdRow('Alt+7', t('kbd.page_spindles')) +
    kbdRow('Alt+8', t('kbd.page_calendrier')) +
    kbdRow('Alt+9', t('kbd.page_stats'));
  ov.style.display = 'flex';
}

function closeKbdHelp() {
  const ov = document.getElementById('kbd-help-overlay');
  if (ov) ov.style.display = 'none';
}

// ── Main app keydown handler ───────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  const tag = document.activeElement?.tagName;
  const inInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
    || document.activeElement?.isContentEditable;

  if (e.key === 'Escape') {
    if (_gsActive) { closeGlobalSearch(); return; }
    if (document.getElementById('kbd-help-overlay')?.style.display === 'flex') { closeKbdHelp(); return; }
    const lb = document.getElementById('lb');
    if (lb?.classList.contains('open')) { closeLb(); return; }
    const beerLb = document.getElementById('beer-lightbox');
    if (beerLb?.style.display === 'flex') { closeBeerLightbox(); return; }
    const openModals = [...document.querySelectorAll('.modal-overlay.open')];
    if (!openModals.length) return;
    const m = openModals[openModals.length - 1];
    if (m.id === 'modal-settings') closeSettings();
    else if (m.id === 'modal-scale') closeScaleModal();
    else closeModal(m.id);
    return;
  }

  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    const recForm = document.getElementById('rec-form-panel');
    if (recForm && recForm.style.display !== 'none' && typeof saveRecipe === 'function') {
      e.preventDefault();
      _lastSaveBtn = document.querySelector('#rec-actions .btn-primary');
      saveRecipe();
    }
    return;
  }

  if (e.key === 'n' && !inInput && !e.ctrlKey && !e.metaKey && !e.altKey) {
    e.preventDefault();
    const openModals = [...document.querySelectorAll('.modal-overlay.open')];
    if (openModals.length || _gsActive) return;
    navigate('brassins').then(() => openBrewModal());
    return;
  }

  if ((e.key === '/' && !inInput) || (e.key === 'k' && e.ctrlKey && !e.shiftKey)) {
    e.preventDefault();
    openGlobalSearch();
    return;
  }

  if (e.key === '?' && !inInput) {
    e.preventDefault();
    openKbdHelp();
    return;
  }

  if (e.altKey && !e.ctrlKey && !e.shiftKey && !inInput) {
    const openModals = [...document.querySelectorAll('.modal-overlay.open')];
    if (openModals.length || _gsActive) return;
    const pages = ['dashboard','inventaire','recettes','brassins','cave','kegs','spindles','calendrier','stats'];
    const idx = parseInt(e.key) - 1;
    if (idx >= 0 && idx < pages.length) {
      e.preventDefault();
      navigate(pages[idx]);
    }
  }
});

function generateRecipeHtml(rec, beer, theo) {
  const _e = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const ings   = rec.ingredients || [];
  const malts  = ings.filter(i => i.category === 'malt');
  const hops   = ings.filter(i => i.category === 'houblon').sort((a,b) => (b.hop_time||0)-(a.hop_time||0));
  const yeasts = ings.filter(i => i.category === 'levure');
  const misc   = ings.filter(i => i.category === 'autre');

  const HOP_TYPE = { ebullition:'Ébullition', whirlpool:'Whirlpool', flameout:'Flameout', dryhop:'Dry-hop' };
  const mc = (val, lbl) => `<div class="mc"><div class="mc-val">${_e(val)}</div><div class="mc-lbl">${_e(lbl)}</div></div>`;
  const tbl = (thead, tbody) => `<table><thead><tr>${thead.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${tbody}</tbody></table>`;
  const sec = lbl => `<div class="section">${lbl}</div>`;

  const accentColor = typeof appSettings !== 'undefined' ? (appSettings.accentColor || '#f5a623') : '#f5a623';
  const appNameStr  = typeof appSettings !== 'undefined' ? (appSettings.appName || 'BrewHome') : 'BrewHome';

  const totalKg = malts.reduce((s,m) => s + (m.unit==='kg' ? +m.quantity : (+m.quantity)/1000), 0);

  const maltRows  = malts.map(m  => `<tr><td>${_e(m.name)}</td><td>${m.quantity} ${_e(m.unit)}</td><td>${m.ebc!=null?m.ebc:'–'}</td></tr>`).join('');
  const hopRows   = hops.map(h   => `<tr><td>${_e(h.name)}</td><td>${h.quantity} ${_e(h.unit)}</td><td>${h.alpha!=null?h.alpha+' %':'–'}</td><td>${h.hop_time!=null?h.hop_time+' min ':''} ${_e(HOP_TYPE[h.hop_type]||h.hop_type||'')}</td></tr>`).join('');
  const yeastRows = yeasts.map(y => `<tr><td>${_e(y.name)}</td><td>${y.quantity} ${_e(y.unit)}</td></tr>`).join('');
  const miscRows  = misc.map(m   => `<tr><td>${_e(m.name)}</td><td>${m.quantity} ${_e(m.unit)}</td><td>${_e(m.other_type||'–')}</td></tr>`).join('');

  const metricsHtml = theo
    ? [mc(theo.og.toFixed(3),'DI théo.'), mc(theo.fg.toFixed(3),'DF théo.'), mc(theo.abv.toFixed(1)+' %','ABV théo.'), mc((rec.brewhouse_efficiency||72)+' %','Rendement')].join('')
    : mc((rec.brewhouse_efficiency||72)+' %','Rendement');

  const subtitle = [rec.style, rec.volume ? rec.volume+' L' : ''].filter(Boolean).join(' · ');
  const beerLink = beer ? `<div class="beer-link-row"><a href="../index.html#beer-${beer.id}" class="back-beer">🍺 ${_e(beer.name)}</a></div>` : '';

  return `<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Recette — ${_e(rec.name)}</title>
<style>
:root{--bg:#0f0f0f;--card:#1a1a1a;--border:#272727;--text:#e8e0d0;--muted:#888;--amber:${accentColor};--hop:#7ec845;--info:#60a5fa}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
.container{max-width:720px;margin:0 auto;padding:0 16px 60px}
header{text-align:center;padding:36px 16px 20px;max-width:720px;margin:0 auto}
a.back-link{display:inline-block;font-size:.8rem;color:var(--muted);text-decoration:none;margin-bottom:16px;padding:4px 14px;border:1px solid var(--border);border-radius:20px}
a.back-link:hover{color:var(--text);border-color:var(--amber)}
h1{font-size:1.9rem;font-weight:900;color:var(--amber);letter-spacing:-.02em;margin-bottom:6px}
.subtitle{font-size:.85rem;color:var(--muted);margin-bottom:4px}
.metrics{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin:20px 0 0}
.mc{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:12px 18px;text-align:center;min-width:90px}
.mc-val{font-size:1.4rem;font-weight:800;color:var(--amber);line-height:1}
.mc-lbl{font-size:.66rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-top:4px}
.section{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--amber);margin:24px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--border)}
table{width:100%;border-collapse:collapse;font-size:.87rem}
th{text-align:left;font-size:.66rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);padding:6px 10px;border-bottom:1px solid var(--border)}
td{padding:7px 10px;border-bottom:1px solid rgba(255,255,255,.04)}
tr:last-child td{border-bottom:none}
tr:hover td{background:rgba(255,255,255,.025)}
.mash-info{display:flex;gap:20px;flex-wrap:wrap;background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px 16px;font-size:.88rem}
.mi-val{font-weight:700}.mi-lbl{font-size:.7rem;color:var(--muted);margin-top:2px}
.notes{font-size:.84rem;line-height:1.65;color:#aaa;white-space:pre-wrap;background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px 16px}
.beer-link-row{text-align:center;padding:32px 0}
a.back-beer{display:inline-block;font-size:.85rem;color:var(--amber);text-decoration:none;padding:8px 22px;border:1px solid var(--amber);border-radius:20px}
a.back-beer:hover{background:rgba(245,166,35,.1)}
footer{text-align:center;padding:20px;font-size:.72rem;color:#444;border-top:1px solid var(--border)}
</style>
</head>
<body>
<header>
  <a href="../index.html" class="back-link">← Cave à bières</a>
  <h1>${_e(rec.name)}</h1>
  ${subtitle ? `<div class="subtitle">${_e(subtitle)}</div>` : ''}
  <div class="metrics">${metricsHtml}</div>
</header>
<div class="container">
  ${malts.length  ? sec(`Fermentescibles (${totalKg.toFixed(2)} kg)`) + tbl(['Malt','Quantité','EBC'], maltRows)   : ''}
  ${hops.length   ? sec('Houblons')   + tbl(['Houblon','Quantité','Alpha','Addition'], hopRows)  : ''}
  ${yeasts.length ? sec('Levure')     + tbl(['Levure','Quantité'], yeastRows)                    : ''}
  ${misc.length   ? sec('Divers')     + tbl(['Ingrédient','Quantité','Type'], miscRows)          : ''}
  ${(rec.mash_temp||rec.mash_time||rec.boil_time) ? `
  ${sec('Brassage')}
  <div class="mash-info">
    ${rec.mash_temp ? `<div><div class="mi-val">${rec.mash_temp} °C</div><div class="mi-lbl">T° empâtage</div></div>` : ''}
    ${rec.mash_time ? `<div><div class="mi-val">${rec.mash_time} min</div><div class="mi-lbl">Durée empâtage</div></div>` : ''}
    ${rec.boil_time ? `<div><div class="mi-val">${rec.boil_time} min</div><div class="mi-lbl">Ébullition</div></div>` : ''}
    ${rec.volume    ? `<div><div class="mi-val">${rec.volume} L</div><div class="mi-lbl">Volume cible</div></div>` : ''}
  </div>` : ''}
  ${rec.notes ? `${sec('Notes')}<div class="notes">${_e(rec.notes)}</div>` : ''}
  ${beerLink}
</div>
<footer>Généré par ${_e(appNameStr)}</footer>
</body>
</html>`;
}

async function pushVitrine(force = false, silent = false) {
  _captureGithubSettings();
  const targets = ((appSettings.github || {}).vitrine?.targets || []).filter(tgt => tgt.repo && tgt.pat);
  if (!targets.length) { toast(t('settings.github.err_missing_vitrine'), 'error'); return; }

  // Désactiver l'autre bouton pendant l'opération (withBtn gère le bouton cliqué)
  const btnForce = document.getElementById(force ? 'btn-push-vitrine' : 'btn-push-vitrine-force');
  if (btnForce) btnForce.disabled = true;

  // S'assurer que les bières sont chargées
  if (!S.beers.length) {
    try { S.beers = await api('GET', '/api/beers'); } catch(e) { console.warn('[BrewHome] beers load failed during push:', e); }
  }
  const beers   = S.beers.filter(b => !b.archived);
  const dateStr = new Date().toISOString().slice(0, 10);

  // Construire la map des photos (id → {ext, b64})
  const photoMap = {};
  beers.forEach(b => {
    const p = _parsePhotoDataUrl(b.photo);
    if (p) photoMap[b.id] = p;
  });

  // Logo de l'application
  const appIconParsed = _parsePhotoDataUrl(appSettings.appIcon || null);
  const iconPath = appIconParsed ? `images/app-icon.${appIconParsed.ext}` : null;

  // Charger les recettes liées aux bières
  const recipeIds = [...new Set(beers.filter(b => b.recipe_id).map(b => b.recipe_id))];
  if (recipeIds.length) {
    try { await ensureRecipesLoaded(); } catch(e) { console.warn('[BrewHome] recipes load failed during push:', e); }
  }
  const recipeMap = {};
  S.recipes.forEach(r => { if (recipeIds.includes(r.id)) recipeMap[r.id] = r; });

  const html = generateVitrineHtml(beers, photoMap, iconPath);
  const json = JSON.stringify(beers, null, 2);

  // Pages de recettes
  const recipeFiles = Object.values(recipeMap).map(rec => {
    const beer = beers.find(b => b.recipe_id === rec.id);
    const theo = typeof _recTheoretical === 'function' ? _recTheoretical(rec) : null;
    return { path: `recipes/${rec.id}.html`, b64: btoa(unescape(encodeURIComponent(generateRecipeHtml(rec, beer, theo)))) };
  });

  // Liste des fichiers : { path, b64 }
  const files = [
    { path: 'index.html', b64: btoa(unescape(encodeURIComponent(html))) },
    { path: 'beers.json', b64: btoa(unescape(encodeURIComponent(json))) },
    ...recipeFiles,
    ...Object.entries(photoMap).map(([id, { ext, b64 }]) => ({ path: `images/beer-${id}.${ext}`, b64 })),
    ...(appIconParsed ? [{ path: iconPath, b64: appIconParsed.b64 }] : []),
  ];

  try {
    let totalPushed = 0, totalSkipped = 0;
    for (const cfg of targets) {
      const isCustom = cfg.provider === 'custom';
      const apiBase  = isCustom && cfg.apiUrl ? cfg.apiUrl.replace(/\/+$/, '') : 'https://api.github.com';

      if (isCustom) {
        // Gitea/Forgejo : Contents API fichier par fichier
        for (const f of files) {
          const res = await pushToGithub(cfg.repo, cfg.pat, cfg.branch, f.path,
            f.b64, `vitrine: ${f.path} ${dateStr}`, true, apiBase);
          if (!force && res?.skipped) totalSkipped++; else totalPushed++;
        }
      } else {
        // GitHub : API Git Data — commit unique (blobs → tree → commit → ref)
        const GH = `${apiBase}/repos/${cfg.repo}`;
        const headers = {
          'Authorization': `Bearer ${cfg.pat}`,
          'Accept': 'application/vnd.github+json',
          'Content-Type': 'application/json',
        };
        const refRes  = await fetch(`${GH}/git/ref/heads/${encodeURIComponent(cfg.branch)}`, { headers, cache: 'no-store' });
        if (!refRes.ok) throw new Error((await refRes.json()).message || 'Branche introuvable');
        const { object: { sha: currentCommitSha } } = await refRes.json();
        const commitRes = await fetch(`${GH}/git/commits/${currentCommitSha}`, { headers });
        if (!commitRes.ok) throw new Error('Impossible de lire le commit courant');
        const { tree: { sha: baseTreeSha } } = await commitRes.json();
        const treeRes = await fetch(`${GH}/git/trees/${baseTreeSha}?recursive=1`, { headers });
        const existingMap = {};
        if (treeRes.ok) ((await treeRes.json()).tree || []).forEach(item => { existingMap[item.path] = item.sha; });
        const blobs = await Promise.all(files.map(async f => {
          const res = await fetch(`${GH}/git/blobs`, { method: 'POST', headers, body: JSON.stringify({ content: f.b64, encoding: 'base64' }) });
          if (!res.ok) throw new Error(`Blob ${f.path} : ${(await res.json()).message}`);
          const { sha } = await res.json();
          return { path: f.path, sha, changed: existingMap[f.path] !== sha };
        }));
        const changed = force ? blobs : blobs.filter(b => b.changed);
        if (changed.length) {
          const newTreeRes = await fetch(`${GH}/git/trees`, { method: 'POST', headers, body: JSON.stringify({ base_tree: baseTreeSha, tree: changed.map(b => ({ path: b.path, mode: '100644', type: 'blob', sha: b.sha })) }) });
          if (!newTreeRes.ok) throw new Error((await newTreeRes.json()).message || 'Erreur création tree');
          const { sha: newTreeSha } = await newTreeRes.json();
          const newCommitRes = await fetch(`${GH}/git/commits`, { method: 'POST', headers, body: JSON.stringify({ message: `vitrine: mise à jour ${dateStr} (${changed.length} fichier(s))`, tree: newTreeSha, parents: [currentCommitSha] }) });
          if (!newCommitRes.ok) throw new Error((await newCommitRes.json()).message || 'Erreur création commit');
          const { sha: newCommitSha } = await newCommitRes.json();
          const patchRes = await fetch(`${GH}/git/refs/heads/${encodeURIComponent(cfg.branch)}`, { method: 'PATCH', headers, body: JSON.stringify({ sha: newCommitSha }) });
          if (!patchRes.ok) throw new Error((await patchRes.json()).message || 'Erreur mise à jour branche');
          totalPushed += changed.length;
          totalSkipped += blobs.length - changed.length;
        } else {
          totalSkipped += blobs.length;
        }
      }
    }

    if (!force && totalPushed === 0) {
      if (!silent) toast(t('settings.github.vitrine_up_to_date'), 'success');
      return;
    }
    if (!silent) {
      const skipTxt  = totalSkipped ? t('settings.github.vitrine_skipped').replace('${n}', totalSkipped) : '';
      const forceTxt = force ? t('settings.github.vitrine_forced') : '';
      toast(t('settings.github.vitrine_pushed').replace('${beers}', beers.length).replace('${files}', totalPushed) + skipTxt + forceTxt, 'success');
    }
    _logActivity('backup', 'vitrine', `Vitrine publiée : ${totalPushed} fichier(s)`);
  } catch(e) {
    if (!silent) toast(t('settings.github.err_vitrine') + ' ' + e.message, 'error');
    else console.warn('[BrewHome] auto-push vitrine:', e.message);
  } finally {
    if (btnForce) btnForce.disabled = false;
  }
}

async function pushGithubData() {
  _captureGithubSettings();
  const targets = ((appSettings.github || {}).data?.targets || []).filter(tgt => tgt.repo && tgt.pat);
  if (!targets.length) {
    toast(t('settings.github.err_missing_data'), 'error');
    return;
  }

  const dateStr = new Date().toISOString().slice(0,10);
  try {
    // Fetch all data in parallel (pas de conflit GitHub ici)
    const [inv, rec, brews, beers, spindles, catalog, drafts, calendar] = await Promise.all([
      api('GET', '/api/export/inventory'),
      api('GET', '/api/export/recipes'),
      api('GET', '/api/export/brews'),
      api('GET', '/api/export/beers'),
      api('GET', '/api/export/spindles'),
      api('GET', '/api/export/catalog'),
      api('GET', '/api/export/drafts'),
      api('GET', '/api/export/calendar'),
    ]);
    // Paramètres avancés (sans PAT)
    const settingsOut = JSON.parse(JSON.stringify(appSettings));
    if (settingsOut.github?.vitrine) delete settingsOut.github.vitrine.pat;
    if (settingsOut.github?.data)    delete settingsOut.github.data.pat;
    // Push séquentiel pour éviter les conflits de SHA sur la même branche
    const dataFiles = [
      { path: 'inventaire.json',  content: JSON.stringify(inv,         null, 2), msg: `backup: inventaire ${dateStr}` },
      { path: 'recettes.json',    content: JSON.stringify(rec,         null, 2), msg: `backup: recettes ${dateStr}` },
      { path: 'brassins.json',    content: JSON.stringify(brews,       null, 2), msg: `backup: brassins ${dateStr}` },
      { path: 'cave.json',        content: JSON.stringify(beers,       null, 2), msg: `backup: cave ${dateStr}` },
      { path: 'densimetres.json', content: JSON.stringify(spindles,    null, 2), msg: `backup: densimètres ${dateStr}` },
      { path: 'catalogue.json',   content: JSON.stringify(catalog,     null, 2), msg: `backup: catalogue ${dateStr}` },
      { path: 'brouillons.json',  content: JSON.stringify(drafts,      null, 2), msg: `backup: brouillons ${dateStr}` },
      { path: 'calendrier.json',  content: JSON.stringify(calendar,    null, 2), msg: `backup: calendrier ${dateStr}` },
      { path: 'parametres.json',  content: JSON.stringify(settingsOut, null, 2), msg: `backup: paramètres ${dateStr}` },
    ];
    let totalPushed = 0, totalSkipped = 0;
    for (const cfg of targets) {
      const isCustom = cfg.provider === 'custom';
      const apiBase  = isCustom && cfg.apiUrl ? cfg.apiUrl.replace(/\/+$/, '') : 'https://api.github.com';
      for (const f of dataFiles) {
        const res = await pushToGithub(cfg.repo, cfg.pat, cfg.branch, f.path, f.content, f.msg, false, apiBase);
        res?.skipped ? totalSkipped++ : totalPushed++;
      }
    }
    const skipTxt = totalSkipped ? t('settings.github.vitrine_skipped').replace('${n}', totalSkipped) : '';
    toast(t('settings.github.data_pushed').replace('${files}', totalPushed) + skipTxt, 'success');
    _logActivity('backup', 'manual', JSON.stringify({_i18n:'act.backup_manual', n: totalPushed}));
    if (!appSettings.github) appSettings.github = {};
    if (!appSettings.github.backup) appSettings.github.backup = {};
    appSettings.github.backup.lastBackup = new Date().toLocaleString('sv').slice(0, 16);
    updateBackupNavBadge();
  } catch(e) {
    toast(t('settings.github.err_data') + ' ' + e.message, 'error');
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════════════════════════
// SETTINGS — MISES À JOUR STATIQUES
// ══════════════════════════════════════════════════════════════════════════════

// ── CHECKLISTS ────────────────────────────────────────────────────────────────

const CHECKLIST_PHASES = ['preparation','empatage','ebullition','refroidissement','fermentation','embouteillage','autre'];

function _phaseLabel(phase) {
  return t('checklist.phase_' + phase) || phase;
}

// Template par défaut intégré
function _defaultChecklistItems() {
  return [
    { id:'prep_1', phase:'preparation',     text: t('checklist.def_prep_1') },
    { id:'prep_2', phase:'preparation',     text: t('checklist.def_prep_2') },
    { id:'prep_3', phase:'preparation',     text: t('checklist.def_prep_3') },
    { id:'prep_4', phase:'preparation',     text: t('checklist.def_prep_4') },
    { id:'mash_1', phase:'empatage',        text: t('checklist.def_mash_1') },
    { id:'mash_2', phase:'empatage',        text: t('checklist.def_mash_2') },
    { id:'mash_3', phase:'empatage',        text: t('checklist.def_mash_3') },
    { id:'mash_4', phase:'empatage',        text: t('checklist.def_mash_4') },
    { id:'boil_1', phase:'ebullition',      text: t('checklist.def_boil_1') },
    { id:'boil_2', phase:'ebullition',      text: t('checklist.def_boil_2') },
    { id:'boil_3', phase:'ebullition',      text: t('checklist.def_boil_3') },
    { id:'boil_4', phase:'ebullition',      text: t('checklist.def_boil_4') },
    { id:'cool_1', phase:'refroidissement', text: t('checklist.def_cool_1') },
    { id:'cool_2', phase:'refroidissement', text: t('checklist.def_cool_2') },
    { id:'cool_3', phase:'refroidissement', text: t('checklist.def_cool_3') },
    { id:'ferm_1', phase:'fermentation',    text: t('checklist.def_ferm_1') },
    { id:'ferm_2', phase:'fermentation',    text: t('checklist.def_ferm_2') },
    { id:'ferm_3', phase:'fermentation',    text: t('checklist.def_ferm_3') },
    { id:'bot_1',  phase:'embouteillage',   text: t('checklist.def_bot_1') },
    { id:'bot_2',  phase:'embouteillage',   text: t('checklist.def_bot_2') },
    { id:'bot_3',  phase:'embouteillage',   text: t('checklist.def_bot_3') },
    { id:'bot_4',  phase:'embouteillage',   text: t('checklist.def_bot_4') },
    { id:'bot_5',  phase:'embouteillage',   text: t('checklist.def_bot_5') },
  ];
}

// ── Template editor ──────────────────────────────────────────────────────────

let _cedItems = []; // items en cours d'édition

function openChecklistEditor(id = null) {
  _cedItems = [];
  document.getElementById('ced-id').value   = id || '';
  document.getElementById('ced-name').value = '';
  document.getElementById('ced-desc').value = '';
  document.getElementById('ced-title').textContent = id
    ? t('checklist.edit_template') : t('checklist.new_template');

  if (id) {
    const tpl = S.checklistTemplates.find(x => x.id === id);
    if (tpl) {
      document.getElementById('ced-name').value = tpl.name;
      document.getElementById('ced-desc').value = tpl.description || '';
      _cedItems = JSON.parse(JSON.stringify(tpl.items || []));
    }
  }
  _renderCedItems();
  openModal('checklist-editor-modal');
  setTimeout(() => document.getElementById('ced-name').focus(), 80);
}

function _renderCedItems() {
  const el = document.getElementById('ced-items-list');
  if (!_cedItems.length) {
    el.innerHTML = `<div style="padding:20px;text-align:center;color:var(--muted);font-size:.84rem">${t('checklist.empty')}</div>`;
    return;
  }
  const byPhase = {};
  CHECKLIST_PHASES.forEach(p => { byPhase[p] = []; });
  _cedItems.forEach((item, idx) => {
    const p = item.phase || 'autre';
    if (!byPhase[p]) byPhase[p] = [];
    byPhase[p].push({ ...item, _idx: idx });
  });
  el.innerHTML = CHECKLIST_PHASES
    .filter(p => byPhase[p].length > 0)
    .map(p => `
      <div style="padding:6px 10px 2px;font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);background:var(--card2);border-bottom:1px solid var(--border)">${_phaseLabel(p)}</div>
      ${byPhase[p].map(item => `
        <div class="ced-item" data-idx="${item._idx}">
          <span class="ced-item-text">${esc(item.text)}</span>
          <button class="ced-move-btn" onclick="_cedMove(${item._idx},-1)" title="↑"><i class="fas fa-chevron-up"></i></button>
          <button class="ced-move-btn" onclick="_cedMove(${item._idx},1)" title="↓"><i class="fas fa-chevron-down"></i></button>
          <select style="font-size:.72rem;padding:1px 4px;border-radius:4px;border:1px solid var(--border);background:var(--card2);color:var(--text)"
            onchange="_cedChangePhase(${item._idx},this.value)">
            ${CHECKLIST_PHASES.map(ph => `<option value="${ph}"${ph===item.phase?' selected':''}>${_phaseLabel(ph)}</option>`).join('')}
          </select>
          <button class="ced-del-btn" onclick="_cedRemove(${item._idx})" title="${t('common.delete')}"><i class="fas fa-trash"></i></button>
        </div>`).join('')}`).join('');
}

function addChecklistEditorItem() {
  const txt   = (document.getElementById('ced-new-item-text').value || '').trim();
  const phase = document.getElementById('ced-new-phase').value || 'preparation';
  if (!txt) return;
  _cedItems.push({ id: 'item_' + Date.now() + '_' + Math.random().toString(36).slice(2,6), phase, text: txt });
  document.getElementById('ced-new-item-text').value = '';
  document.getElementById('ced-new-item-text').focus();
  _renderCedItems();
}

function _cedRemove(idx) { _cedItems.splice(idx, 1); _renderCedItems(); }

function _cedMove(idx, dir) {
  const to = idx + dir;
  if (to < 0 || to >= _cedItems.length) return;
  [_cedItems[idx], _cedItems[to]] = [_cedItems[to], _cedItems[idx]];
  _renderCedItems();
}

function _cedChangePhase(idx, phase) {
  _cedItems[idx].phase = phase;
  _renderCedItems();
}

async function importDefaultTemplate() {
  if (_cedItems.length && !await confirmModal(t('checklist.reset_confirm'))) return;
  _cedItems = _defaultChecklistItems();
  if (!document.getElementById('ced-name').value)
    document.getElementById('ced-name').value = t('checklist.def_name');
  _renderCedItems();
}

async function saveChecklistTemplate() {
  const name = (document.getElementById('ced-name').value || '').trim();
  if (!name) { toast(t('checklist.template_name') + ' ?', 'error'); return; }
  const id   = parseInt(document.getElementById('ced-id').value) || null;
  const payload = {
    name,
    description: document.getElementById('ced-desc').value.trim() || null,
    items: _cedItems,
  };
  try {
    const saved = id
      ? await api('PUT',  `/api/checklist-templates/${id}`, payload)
      : await api('POST', '/api/checklist-templates', payload);
    if (id) {
      const i = S.checklistTemplates.findIndex(x => x.id === id);
      if (i >= 0) S.checklistTemplates[i] = { ...saved, items: _cedItems };
    } else {
      S.checklistTemplates.push({ ...saved, items: _cedItems });
    }
    closeModal('checklist-editor-modal');
    renderSettingsChecklists();
    toast(t('common.saved'), 'success');
  } catch(e) { toast(t('common.error'), 'error'); }
}

async function deleteChecklistTemplate(id) {
  if (!await confirmModal(t('checklist.confirm_delete'), { danger: true })) return;
  try {
    await api('DELETE', `/api/checklist-templates/${id}`);
    S.checklistTemplates = S.checklistTemplates.filter(x => x.id !== id);
    renderSettingsChecklists();
    toast(t('common.deleted') || t('common.delete'), 'success');
  } catch(e) { toast(t('common.error'), 'error'); }
}

async function renderSettingsChecklists() {
  if (!S.checklistTemplates.length) {
    try {
      const data = await api('GET', '/api/checklist-templates');
      S.checklistTemplates = data.map(tpl => ({
        ...tpl, items: typeof tpl.items === 'string' ? JSON.parse(tpl.items) : (tpl.items || [])
      }));
    } catch(e) { /* ignore */ }
  }
  const el = document.getElementById('checklist-templates-list');
  if (!el) return;
  if (!S.checklistTemplates.length) {
    el.innerHTML = `<div style="text-align:center;color:var(--muted);padding:24px 0;font-size:.85rem">${t('checklist.empty')}</div>`;
    return;
  }
  el.innerHTML = S.checklistTemplates.map(tpl => {
    const count = (tpl.items || []).length;
    return `<div style="display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;background:var(--card2);margin-bottom:8px">
      <i class="fas fa-clipboard-list" style="color:var(--primary);flex-shrink:0"></i>
      <div style="flex:1;min-width:0">
        <div style="font-weight:600;font-size:.9rem">${esc(tpl.name)}</div>
        ${tpl.description ? `<div style="font-size:.77rem;color:var(--muted)">${esc(tpl.description)}</div>` : ''}
        <div style="font-size:.74rem;color:var(--muted);margin-top:2px">${count} ${t('checklist.items_title').toLowerCase()}</div>
      </div>
      <button class="btn btn-ghost btn-sm btn-icon" onclick="openChecklistEditor(${tpl.id})" title="${t('checklist.edit_template')}"><i class="fas fa-pen"></i></button>
      <button class="btn btn-ghost btn-sm btn-icon" onclick="deleteChecklistTemplate(${tpl.id})" title="${t('checklist.delete_template')}"><i class="fas fa-trash" style="color:var(--danger)"></i></button>
    </div>`;
  }).join('');
}

// ── Brew checklist modal ─────────────────────────────────────────────────────

let _bcl = { brewId: null, templateId: null, checkedItems: [], template: null };
let _bclSaveTimer = null;

async function openBrewChecklist(brewId) {
  const b = S.brews.find(x => x.id === brewId);
  if (!b) return;
  document.getElementById('bcl-brew-name').textContent = esc(b.name);

  // Charger les templates si nécessaire
  if (!S.checklistTemplates.length) {
    try {
      const data = await api('GET', '/api/checklist-templates');
      S.checklistTemplates = data.map(tpl => ({
        ...tpl, items: typeof tpl.items === 'string' ? JSON.parse(tpl.items) : (tpl.items || [])
      }));
    } catch(e) { /* ignore */ }
  }

  // Charger l'état sauvegardé du brassin
  let savedState = { template_id: null, checked_items: [] };
  try { savedState = await api('GET', `/api/brews/${brewId}/checklist`); } catch(e) { /* ignore */ }

  _bcl.brewId      = brewId;
  _bcl.templateId  = savedState.template_id || (S.checklistTemplates[0]?.id ?? null);
  _bcl.checkedItems = savedState.checked_items || [];

  _renderBclTemplateSelect();
  _renderBclItems();
  openModal('brew-checklist-modal');
}

function _renderBclTemplateSelect() {
  const sel = document.getElementById('bcl-template-select');
  if (!sel) return;
  if (!S.checklistTemplates.length) {
    sel.innerHTML = `<option value="">${t('checklist.no_template')}</option>`;
    return;
  }
  sel.innerHTML = S.checklistTemplates.map(tpl =>
    `<option value="${tpl.id}"${tpl.id === _bcl.templateId ? ' selected' : ''}>${esc(tpl.name)}</option>`
  ).join('');
}

function checklistSelectTemplate(val) {
  _bcl.templateId   = parseInt(val) || null;
  _bcl.checkedItems = [];
  _renderBclItems();
  _bclScheduleSave();
}

function _renderBclItems() {
  const itemsEl = document.getElementById('bcl-items');
  const tpl = S.checklistTemplates.find(x => x.id === _bcl.templateId);
  _bcl.template = tpl || null;

  if (!tpl) {
    itemsEl.innerHTML = `<div style="text-align:center;color:var(--muted);padding:24px 0;font-size:.85rem">${t('checklist.no_template')}</div>`;
    _updateBclProgress(0, 0);
    return;
  }

  const items = tpl.items || [];
  const total = items.length;
  const done  = items.filter(i => _bcl.checkedItems.includes(i.id)).length;
  _updateBclProgress(done, total);

  const byPhase = {};
  CHECKLIST_PHASES.forEach(p => { byPhase[p] = []; });
  items.forEach(item => {
    const p = item.phase || 'autre';
    if (!byPhase[p]) byPhase[p] = [];
    byPhase[p].push(item);
  });

  itemsEl.innerHTML = CHECKLIST_PHASES
    .filter(p => byPhase[p].length > 0)
    .map(p => {
      const phItems = byPhase[p];
      const pDone   = phItems.filter(i => _bcl.checkedItems.includes(i.id)).length;
      return `
        <div class="cl-phase-header">
          <span style="flex:1">${_phaseLabel(p)}</span>
          <span style="font-size:.7rem">${pDone}/${phItems.length}</span>
        </div>
        ${phItems.map(item => {
          const checked = _bcl.checkedItems.includes(item.id);
          return `<div class="cl-item${checked ? ' checked' : ''}" onclick="toggleBrewChecklistItem('${item.id}')">
            <input type="checkbox"${checked ? ' checked' : ''} onclick="event.stopPropagation();toggleBrewChecklistItem('${item.id}')">
            <span class="cl-text">${esc(item.text)}</span>
          </div>`;
        }).join('')}`;
    }).join('');
}

function toggleBrewChecklistItem(itemId) {
  const idx = _bcl.checkedItems.indexOf(itemId);
  if (idx >= 0) _bcl.checkedItems.splice(idx, 1);
  else _bcl.checkedItems.push(itemId);
  _renderBclItems();
  _bclScheduleSave();
}

function _updateBclProgress(done, total) {
  const pct = total > 0 ? Math.round(done / total * 100) : 0;
  const label = t('checklist.progress').replace('${done}', done).replace('${total}', total);
  document.getElementById('bcl-progress-label').textContent = label;
  document.getElementById('bcl-progress-pct').textContent = total > 0 ? pct + '%' : '';
  document.getElementById('bcl-progress-bar').style.width = pct + '%';
}

function _bclScheduleSave() {
  clearTimeout(_bclSaveTimer);
  _bclSaveTimer = setTimeout(_bclDoSave, 800);
}

async function _bclDoSave() {
  if (!_bcl.brewId) return;
  try {
    await api('POST', `/api/brews/${_bcl.brewId}/checklist`, {
      template_id:   _bcl.templateId,
      checked_items: _bcl.checkedItems,
    });
  } catch(e) { console.warn('checklist save:', e); }
}

async function resetBrewChecklist() {
  if (!await confirmModal(t('checklist.reset_confirm'))) return;
  _bcl.checkedItems = [];
  _renderBclItems();
  _bclScheduleSave();
}

// ── Impression ───────────────────────────────────────────────────────────────

function printBrewChecklist() {
  const b   = S.brews.find(x => x.id === _bcl.brewId);
  const tpl = _bcl.template;
  if (!b || !tpl) return;

  const rec = b.recipe_id ? S.recipes.find(r => r.id === b.recipe_id) : null;
  const items = tpl.items || [];
  const done  = items.filter(i => _bcl.checkedItems.includes(i.id)).length;

  const byPhase = {};
  CHECKLIST_PHASES.forEach(p => { byPhase[p] = []; });
  items.forEach(item => {
    const p = item.phase || 'autre';
    if (!byPhase[p]) byPhase[p] = [];
    byPhase[p].push(item);
  });

  const phasesHtml = CHECKLIST_PHASES
    .filter(p => byPhase[p].length > 0)
    .map(p => `
      <div style="margin-top:14px">
        <div style="font-size:9pt;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#555;border-bottom:1px solid #ccc;padding-bottom:3px;margin-bottom:6px">${_phaseLabel(p)}</div>
        ${byPhase[p].map(item => {
          const checked = _bcl.checkedItems.includes(item.id);
          return `<div style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;border-bottom:1px solid #eee">
            <div style="width:14px;height:14px;border:1.5px solid #888;border-radius:2px;flex-shrink:0;margin-top:1px;background:${checked ? '#16a34a' : 'white'};display:flex;align-items:center;justify-content:center">
              ${checked ? '<span style="color:white;font-size:9pt;line-height:1">✓</span>' : ''}
            </div>
            <span style="font-size:10pt;${checked ? 'text-decoration:line-through;color:#888' : ''}">${item.text}</span>
          </div>`;
        }).join('')}
      </div>`).join('');

  const html = `
    <div style="max-width:680px;margin:0 auto">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px;padding-bottom:12px;border-bottom:2px solid #222">
        <div>
          <div style="font-size:18pt;font-weight:800">${esc(b.name)}</div>
          ${rec ? `<div style="font-size:10pt;color:#555;margin-top:2px"><i>Recette : ${esc(rec.name)}</i></div>` : ''}
          ${b.brew_date ? `<div style="font-size:9pt;color:#777">Date : ${b.brew_date}</div>` : ''}
        </div>
        <div style="text-align:right">
          <div style="font-size:9pt;color:#555">${esc(tpl.name)}</div>
          <div style="font-size:9pt;font-weight:700;margin-top:4px">${done} / ${items.length} ✓</div>
          <div style="font-size:8pt;color:#999;margin-top:2px">${new Date().toLocaleDateString()}</div>
        </div>
      </div>
      ${phasesHtml}
    </div>`;

  const area = document.getElementById('checklist-print-area');
  if (area) area.innerHTML = html;

  let styleTag = document.getElementById('_checklist-page-style');
  if (!styleTag) { styleTag = document.createElement('style'); styleTag.id = '_checklist-page-style'; document.head.appendChild(styleTag); }
  styleTag.textContent = '@page{size:A4 portrait;margin:15mm}';

  window.print();
  setTimeout(() => { if (area) area.innerHTML = ''; }, 2000);
}

// ── CORBEILLE ─────────────────────────────────────────────────────────────────

async function renderSettingsTrash() {
  const el = document.getElementById('trash-content');
  if (!el) return;
  el.innerHTML = `<div style="color:var(--muted);font-size:.85rem"><i class="fas fa-spinner fa-spin"></i></div>`;
  const data = await api('GET', '/api/trash');
  const sections = [
    { key: 'recipes',   label: t('settings.trash.section_recipes'), icon: 'fa-scroll',      table: 'recipes',   sub: r => r.style || '' },
    { key: 'inventory', label: t('settings.trash.section_inv'),     icon: 'fa-boxes-stacked',table: 'inventory', sub: r => `${r.quantity ?? ''} ${r.unit ?? ''} — ${t('cat.' + r.category)}` },
    { key: 'brews',     label: t('settings.trash.section_brews'),   icon: 'fa-fire-burner',  table: 'brews',     sub: r => r.brew_date || '' },
    { key: 'beers',     label: t('settings.trash.section_beers'),   icon: 'fa-wine-bottle',  table: 'beers',     sub: r => r.abv ? `${r.abv}%` : '' },
  ];
  let html = '';
  let total = 0;
  for (const s of sections) {
    const items = data[s.key] || [];
    if (!items.length) continue;
    total += items.length;
    html += `<div style="margin-bottom:20px">
      <div style="font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:8px">
        <i class="fas ${s.icon}"></i> ${esc(s.label)}
      </div>`;
    for (const r of items) {
      const deletedDate = r.deleted_at ? r.deleted_at.slice(0, 10) : '';
      html += `<div style="display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:8px;background:var(--card2);margin-bottom:6px">
        <div style="flex:1;min-width:0">
          <div style="font-weight:600;font-size:.88rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(r.name)}</div>
          <div style="font-size:.76rem;color:var(--muted)">${esc(s.sub(r))}${deletedDate ? ' · ' + t('settings.trash.deleted_on') + ' ' + deletedDate : ''}</div>
        </div>
        <button class="btn btn-sm btn-ghost" style="flex-shrink:0;color:var(--success)" onclick="trashRestore('${s.table}',${r.id})">
          <i class="fas fa-rotate-left"></i> ${esc(t('settings.trash.restore'))}
        </button>
        <button class="btn btn-sm btn-ghost" style="flex-shrink:0;color:var(--danger)" onclick="trashDeleteForever('${s.table}',${r.id})">
          <i class="fas fa-xmark"></i>
        </button>
      </div>`;
    }
    html += `</div>`;
  }
  el.innerHTML = total === 0
    ? `<div style="color:var(--muted);font-size:.85rem;text-align:center;padding:24px 0"><i class="fas fa-trash-can" style="font-size:2rem;display:block;margin-bottom:8px;opacity:.3"></i>${esc(t('settings.trash.empty'))}</div>`
    : html;
}

async function trashRestore(table, id) {
  const ep = { recipes: 'recipes', inventory: 'inventory', brews: 'brews', beers: 'beers' }[table];
  await api('POST', `/api/${ep}/${id}/restore`);
  await loadAll();
  renderSettingsTrash();
}

async function trashDeleteForever(table, id) {
  if (!await confirmModal(t('settings.trash.confirm_delete'), { danger: true })) return;
  const ep = { recipes: 'recipes', inventory: 'inventory', brews: 'brews', beers: 'beers' }[table];
  await api('DELETE', `/api/${ep}/${id}/purge`);
  renderSettingsTrash();
}

// ══════════════════════════════════════════════════════════════════════════════

let _updatesChecked = false;

async function checkStaticUpdates(force = false) {
  if (_updatesChecked && !force) return;
  const list = document.getElementById('updates-list');
  if (!list) return;
  list.innerHTML = `<div style="color:var(--muted);font-size:.85rem"><i class="fas fa-spinner fa-spin"></i> ${t('settings.updates.checking')}</div>`;
  // Version application en parallèle
  const appRow = document.getElementById('app-version-row');
  if (appRow) appRow.innerHTML = `<div style="color:var(--muted);font-size:.85rem"><i class="fas fa-spinner fa-spin"></i> ${t('settings.updates.checking')}</div>`;
  try {
    const [data, appVer] = await Promise.all([
      api('GET', '/api/static/check-updates'),
      api('GET', '/api/version/check').catch(() => null),
    ]);
    // ── Carte version application ──────────────────────────────────────────
    if (appRow) {
      let appStatusHtml, appBtnHtml = '';
      if (!appVer) {
        appStatusHtml = `<span style="color:var(--muted);font-size:.8rem">${t('settings.updates.err_check')} —</span>`;
      } else if (appVer.update_available) {
        appStatusHtml = `<span style="color:var(--amber);font-size:.8rem"><i class="fas fa-arrow-up"></i> ${t('settings.updates.status_update').replace('${current}', esc(appVer.current))} <strong>v${esc(appVer.latest)}</strong></span>`;
        appBtnHtml = `<a href="${esc(appVer.release_url || 'https://github.com/chatainsim/brewhome/releases')}" target="_blank" rel="noopener" class="btn btn-sm btn-ghost" style="border-color:rgba(245,158,11,.4);color:var(--amber);text-decoration:none"><i class="fas fa-arrow-up-right-from-square"></i> ${t('settings.updates.app_new_version_link')}</a>`;
      } else {
        appStatusHtml = `<span style="color:var(--success);font-size:.8rem"><i class="fas fa-circle-check"></i> ${t('settings.updates.status_ok').replace('${version}', esc(appVer.current))}</span>`;
      }
      appRow.innerHTML = `<div style="display:flex;align-items:center;gap:12px;padding:10px 14px;background:var(--card2);border-radius:10px;border:1px solid var(--border)">
        <i class="fas fa-beer-mug-empty" style="color:var(--amber);font-size:1.1rem;width:18px;text-align:center;flex-shrink:0"></i>
        <div style="flex:1;min-width:0">
          <div style="font-weight:700;font-size:.9rem">${t('settings.updates.app_label')} <span style="font-size:.75rem;color:var(--muted);font-weight:400">${t('settings.updates.app_desc')}</span></div>
          <div style="margin-top:3px">${appStatusHtml}</div>
        </div>
        ${appBtnHtml}
      </div>`;
    }
    _updatesChecked = true;
    const libs = [
      {
        key: 'chartjs', label: 'Chart.js', icon: 'fas fa-chart-line', color: 'var(--info)',
        updateFn: 'updateStaticLib("chartjs")',
        desc: t('settings.updates.lib_chartjs'),
      },
      {
        key: 'fontawesome', label: 'Font Awesome', icon: 'fas fa-icons', color: 'var(--amber)',
        updateFn: 'updateStaticLib("fontawesome")',
        desc: t('settings.updates.lib_fontawesome'),
      },
      {
        key: 'googlefonts', label: 'Google Fonts', icon: 'fas fa-font', color: '#10b981',
        updateFn: null,
        desc: t('settings.updates.lib_googlefonts'),
      },
    ];
    list.innerHTML = libs.map(lib => {
      const d = data[lib.key] || {};
      const current = d.current || '–';
      const latest  = d.latest  || null;
      const upToDate = latest && current === latest;
      const hasUpdate = latest && current !== latest;
      const err = d.error;
      let statusHtml;
      if (err) {
        statusHtml = `<span style="color:var(--danger);font-size:.8rem"><i class="fas fa-triangle-exclamation"></i> ${t('settings.updates.err_check')} ${esc(err)}</span>`;
      } else if (lib.key === 'googlefonts') {
        statusHtml = `<span style="color:var(--muted);font-size:.8rem">${t('settings.updates.lib_updated_at')} ${esc(current)} · ${d.size ? Math.round(d.size/1024)+'  KB' : ''}</span>`;
      } else if (upToDate) {
        statusHtml = `<span style="color:var(--success);font-size:.8rem"><i class="fas fa-circle-check"></i> ${t('settings.updates.status_ok').replace('${version}', esc(current))}</span>`;
      } else if (hasUpdate) {
        statusHtml = `<span style="color:var(--amber);font-size:.8rem"><i class="fas fa-arrow-up"></i> ${t('settings.updates.status_update').replace('${current}', esc(current))} <strong>${esc(latest)}</strong></span>`;
      } else {
        statusHtml = `<span style="color:var(--muted);font-size:.8rem">${t('settings.updates.err_status')} ${esc(current)}</span>`;
      }
      const btnHtml = lib.updateFn && hasUpdate
        ? `<button class="btn btn-sm btn-ghost" id="upd-btn-${lib.key}" onclick='${lib.updateFn}' style="border-color:rgba(245,158,11,.4);color:var(--amber)"><i class="fas fa-download"></i> ${t('settings.updates.lib_update_to')} ${esc(latest)}</button>`
        : '';
      return `<div style="display:flex;align-items:center;gap:12px;padding:10px 14px;background:var(--card2);border-radius:10px;border:1px solid var(--border)">
        <i class="${lib.icon}" style="color:${lib.color};font-size:1.1rem;width:18px;text-align:center;flex-shrink:0"></i>
        <div style="flex:1;min-width:0">
          <div style="font-weight:700;font-size:.9rem">${lib.label} <span style="font-size:.75rem;color:var(--muted);font-weight:400">${lib.desc}</span></div>
          <div style="margin-top:3px">${statusHtml}</div>
        </div>
        ${btnHtml}
      </div>`;
    }).join('');
  } catch(e) {
    list.innerHTML = `<div style="color:var(--danger);font-size:.85rem"><i class="fas fa-triangle-exclamation"></i> ${t('settings.updates.err_check')} ${esc(e.message)}</div>`;
    if (appRow) appRow.innerHTML = '';
  }
}

async function updateStaticLib(lib) {
  const btn = document.getElementById(`upd-btn-${lib}`);
  if (btn) { btn.disabled = true; btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${t('settings.updates.lib_updating')}`; }
  try {
    const res = await api('POST', `/api/static/update/${lib}`);
    const libLabel = lib === 'chartjs' ? 'Chart.js' : 'Font Awesome';
    toast(t('settings.updates.updated_ok').replace('${lib}', libLabel).replace('${version}', res.version), 'success');
    _updatesChecked = false;
    await checkStaticUpdates(true);
  } catch(e) {
    toast(t('settings.github.err_update') + ' ' + (e.detail || e.error || e.message || JSON.stringify(e)), 'error');
    if (btn) { btn.disabled = false; btn.innerHTML = `<i class="fas fa-download"></i> ${t('settings.updates.lib_update_to')}`; }
  }
}

