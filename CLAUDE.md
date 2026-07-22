# BrewHome — notes pour Claude Code

Application Flask de gestion de brasserie (recettes, stock, brassins, cave).
Vanilla JS côté client, SQLite côté serveur, usage LAN sans authentification.

## ⚠️ Le JS a une source de vérité, et ce n'est pas `static/js/`

`templates/parts/scripts/script_*.html` **est la source**.
`brewhome/static/js/bh-*.js` en est la **sortie compilée**.

`_migrate_scripts_to_js()` (dans `app.py`) recompile `.html → .js` à chaque
chargement de `/`, dès que la source est plus récente que la sortie. La
« compilation » se limite à retirer les balises `<script>` englobantes.

**Conséquence : toute modification faite directement dans un `bh-*.js` est en
sursis.** Elle sera silencieusement écrasée au premier `touch`, `git checkout`
ou édition de la source correspondante. Ce piège a déjà fait diverger trois
fichiers et a failli faire disparaître un correctif de sécurité (sanitisation
des tokens à l'export) — cf. commit `a5f4a56`.

Donc :

- modifier **le `script_*.html`**, puis recompiler ;
- si un `.js` doit être touché en urgence, reporter le changement dans la
  source dans la foulée ;
- avant de commiter du JS, vérifier que source et sortie sont alignées.

Recompiler et contrôler l'alignement des 13 paires :

```bash
cd brewhome && /usr/bin/python3 -c "
import os,re
SRC='templates/parts/scripts'; DST='static/js'
for s in sorted(os.listdir(SRC)):
    if not s.startswith('script_') or not s.endswith('.html'): continue
    d='bh-'+s[len('script_'):-len('.html')]+'.js'
    if not os.path.exists(os.path.join(DST,d)): continue
    c=open(os.path.join(SRC,s),encoding='utf-8').read()
    c=re.sub(r'^\s*<script[^>]*>\n?','',c); c=re.sub(r'\n?</script>[\s\S]*$','',c)
    if s=='script_settings.html': c=c.replace(\"{{ '{{' }}\",'{{').replace(\"{{ '}}' }}\",'}}')
    same = c==open(os.path.join(DST,d),encoding='utf-8').read()
    print(('OK  ' if same else 'DIFF'), d)
    if not same: open(os.path.join(DST,d),'w',encoding='utf-8').write(c)
"
```

`script_settings.html` est un cas particulier : les `{{` littéraux du JS y sont
échappés en `{{ '{{' }}` pour Jinja, et déséchappés à la compilation.

## Tests

Le Python par défaut n'a pas les dépendances ; utiliser l'interpréteur système :

```bash
cd brewhome && /usr/bin/python3 -m pytest tests/ -q
```

En cas de `ModuleNotFoundError` :

```bash
/usr/bin/python3 -m pip install --user --break-system-packages \
  flask apscheduler waitress pillow pytest
```

## Migrations SQLite

`_MIGRATIONS` dans `db.py` est une liste **ordonnée et append-only**, suivie via
la table `schema_version`. Ajouter les nouvelles entrées **à la fin**, jamais
modifier ni réordonner les existantes. Un `ALTER TABLE ... ADD COLUMN` déjà
appliqué échoue en `duplicate column name` : c'est attendu et logué en `debug`.

Deux bases : `brewhome.db` et `brewhome_readings.db` (attachée sous `rdb`,
migrations séparées dans `_READINGS_MIGRATIONS`).

## Cache des assets statiques

`SEND_FILE_MAX_AGE_DEFAULT = 31536000` (1 an). **Tout asset servi sans `?v=` est
figé un an chez le client.** Les `bh-*.js`, `chart.umd.min.js` et les CSS tiers
portent donc `?v={{ static_v }}` dans `index.html`.

`_compute_static_v()` calcule cette version sur le mtime max de tous les `.js`
de `static/js/` **plus** les CSS tiers (`fonts/fa/all.min.css`,
`fonts/google/fonts.css`). Si un nouvel asset versionné est ajouté, l'inclure
dans ce calcul, sinon le `?v=` ne bougera jamais.

En parallèle, `static/sw.js` sert les statiques en **cache-first**. À chaque mise
à jour d'un asset précaché, **incrémenter `CACHE`** (`brewhome-vN`) — sinon le
service worker continue de servir l'ancienne version indéfiniment.

Ne pas précacher un fichier servi avec `?v=` : `caches.match()` compare la
query-string, l'entrée ne pourrait jamais correspondre.

## Font Awesome

Version **Free** : les icônes Pro (`fa-wine-barrel`, `fa-calendar-star`,
`fa-trash-clock`, `fa-calendar-arrow-down`…) s'affichent en carré vide. Vérifier
qu'une icône existe dans `static/fonts/fa/all.min.css` avant de l'utiliser.

Le CSS officiel référence ses polices en relatif (`../webfonts/`), ce qui est
faux ici (le CSS est en `fonts/fa/`, pas en `fonts/fa/css/`). À chaque mise à
jour, réécrire les URLs en `/static/fonts/fa/webfonts/`.

## Git

Deux remotes : `origin` (GitHub, SSH) et `gitea` (local, HTTP).
`git pushall` pousse sur les deux, sans échouer si le Gitea est hors ligne.

## Sécurité

Pas d'authentification applicative (choix assumé, usage LAN).
Les exports et sauvegardes GitHub **doivent** purger les secrets : PAT (y
compris ceux imbriqués dans `gh_data_targets` / `gh_vitrine_targets`), token
Telegram, clés IA. Voir `_github_data_backup()` dans `blueprints/integrations.py`
et `exportSettings()` / `importSettings()` dans `script_settings.html`.
