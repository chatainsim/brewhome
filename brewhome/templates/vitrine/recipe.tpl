<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Recette — @@0@@</title>
<style>
:root{--bg:#0f0f0f;--card:#1a1a1a;--border:#272727;--text:#e8e0d0;--muted:#888;--amber:@@1@@;--hop:#7ec845;--info:#60a5fa}
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
.calc-panel{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:14px 16px;margin:22px 0 0;text-align:left}
.cb-title{font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.09em;color:var(--amber);margin-bottom:12px}
.cb-sub{color:var(--muted);font-weight:400;text-transform:none;letter-spacing:0;font-size:.7rem}
.cb-formula{margin-left:10px}
.cb-row{display:grid;grid-template-columns:40px 1fr 72px auto;align-items:center;gap:10px;margin-bottom:7px;font-size:.8rem}
.cb-lbl{font-weight:700;color:var(--muted)}
.cb-track{position:relative;height:9px;background:#2a2a2a;border-radius:5px}
.cb-range{position:absolute;top:0;height:100%;background:rgba(245,166,35,.55);border-radius:5px}
.cb-marker{position:absolute;top:-3px;width:3px;height:15px;border-radius:2px}
.cb-val{font-weight:700;text-align:right}
.cb-target{font-size:.7rem;color:var(--muted);white-space:nowrap}
.cb-swatch{display:flex;align-items:center;gap:10px;margin-top:10px}
.cb-dot{width:34px;height:34px;border-radius:50%;flex-shrink:0;border:2px solid rgba(255,255,255,.18);box-shadow:inset 0 -3px 8px rgba(0,0,0,.35)}
.cb-dot-val{font-size:.82rem;font-weight:600}
.cb-dot-lbl{font-size:.7rem;color:var(--muted)}
@media(max-width:560px){.cb-row{grid-template-columns:34px 1fr 62px}.cb-target{display:none}}
.metrics-real{margin-top:10px}
.mc-real{border-color:var(--hop);padding:9px 16px;min-width:82px}
.mc-real .mc-val{color:var(--hop);font-size:1.2rem}
.section{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--amber);margin:24px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--border)}
table{width:100%;border-collapse:collapse;font-size:.87rem}
th{text-align:left;font-size:.66rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);padding:6px 10px;border-bottom:1px solid var(--border)}
td{padding:7px 10px;border-bottom:1px solid rgba(255,255,255,.04)}
tr:last-child td{border-bottom:none}
tr:hover td{background:rgba(255,255,255,.025)}
.mash-info{display:flex;gap:20px;flex-wrap:wrap;background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px 16px;font-size:.88rem}
.mi-val{font-weight:700}.mi-lbl{font-size:.7rem;color:var(--muted);margin-top:2px}
.notes{font-size:.84rem;line-height:1.65;color:#aaa;white-space:pre-wrap;background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px 16px}
.beer-head{display:flex;gap:16px;align-items:flex-start;text-align:left;background:var(--card);border:1px solid var(--border);border-radius:14px;padding:14px;margin:0 0 22px}
.bh-img{width:112px;height:112px;object-fit:cover;border-radius:10px;flex:0 0 auto;background:#000}
.bh-img-ph{display:flex;align-items:center;justify-content:center;font-size:2.4rem}
.bh-body{min-width:0;flex:1}
.bh-name{font-size:1.15rem;font-weight:800;line-height:1.2}
.bh-meta{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:3px;font-size:.78rem;color:var(--muted)}
.bh-abv strong{color:var(--amber)}
.bh-stock{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.bsi{background:rgba(255,255,255,.04);border:1px solid var(--border);border-radius:9px;padding:6px 10px;min-width:58px;text-align:center}
.bsi-n{font-size:1rem;font-weight:800;line-height:1.1}
.bsi-l{font-size:.6rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-top:2px}
.bsi-bar{height:3px;border-radius:2px;background:#333;margin-top:5px;overflow:hidden}
.bsi-fill{height:100%;background:var(--amber)}
.bsi.zero .bsi-n{color:#555}
.bsi.low .bsi-fill{background:#f59e0b}
.bh-desc{font-size:.8rem;line-height:1.5;color:#aaa;margin-top:9px}
.bh-dates{font-size:.72rem;color:var(--muted);margin-top:8px}
.bh-sep{margin:0 6px;opacity:.5}
.bh-link{display:inline-block;margin-top:10px;font-size:.75rem;color:var(--amber);text-decoration:none}
.bh-link:hover{text-decoration:underline}
@media(max-width:520px){.beer-head{flex-direction:column;align-items:stretch}.bh-img{width:100%;height:170px}}
.beer-link-row{text-align:center;padding:32px 0}
a.back-beer{display:inline-block;font-size:.85rem;color:var(--amber);text-decoration:none;padding:8px 22px;border:1px solid var(--amber);border-radius:20px}
a.back-beer:hover{background:rgba(245,166,35,.1)}
footer{text-align:center;padding:20px;font-size:.72rem;color:#444;border-top:1px solid var(--border)}
</style>
</head>
<body>
<header>
  <a href="../index.html" class="back-link">← Cave à bières</a>
  @@2@@
  <h1>@@3@@</h1>
  @@4@@
  <div class="metrics">@@5@@</div>
  @@6@@
  @@15@@
</header>
<div class="container">
  @@7@@
  @@8@@
  @@9@@
  @@10@@
  @@11@@
  @@12@@
  @@13@@
</div>
<footer>Généré par @@14@@</footer>
</body>
</html>