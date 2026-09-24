"""Toute clé de traduction utilisée doit exister en français et en anglais.

`t()` renvoie la clé elle-même quand la traduction manque : l'interface
affiche alors « act.ferm_purge » ou « inv.stock_needed » en clair, et un
texte de secours écrit `t('x') || 'Texte'` ne sert jamais (la clé est une
chaîne non vide). Le test charge le vrai dictionnaire avec Node et vérifie
les clés écrites en dur dans les gabarits, les scripts et les entrées de
journal produites par le serveur. Les clés construites à l'exécution
(`t('cat.' + c)`) échappent à cette analyse.
"""

import json
import os
import re
import shutil
import subprocess

import pytest

ICI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS = os.path.join(ICI, 'templates', 'parts')

_MOTIFS = [
    re.compile(r"\bt\(\s*'([a-z_0-9]+(?:\.[a-zA-Z_0-9]+)+)'"),
    re.compile(r'data-i18n(?:-title|-placeholder)?="([a-z_0-9]+(?:\.[a-zA-Z_0-9]+)+)"'),
    re.compile(r"""_i18n['"]?\s*:\s*['"]([a-z_0-9]+(?:\.[a-zA-Z_0-9]+)+)['"]"""),
]


def _cles_utilisees():
    fichiers = [os.path.join(ICI, 'templates', 'index.html')]
    for dossier in (PARTS, os.path.join(PARTS, 'scripts')):
        fichiers += [os.path.join(dossier, f) for f in os.listdir(dossier)
                     if f.endswith('.html') and 'locales' not in f]
    fichiers += [os.path.join(ICI, 'blueprints', f)
                 for f in os.listdir(os.path.join(ICI, 'blueprints')) if f.endswith('.py')]
    cles = {}
    for f in fichiers:
        texte = open(f, encoding='utf-8').read()
        for motif in _MOTIFS:
            for cle in motif.findall(texte):
                if not cle.endswith('_'):          # préfixe complété à l'exécution
                    cles.setdefault(cle, set()).add(os.path.basename(f))
    return cles


def _dictionnaire():
    script = r"""
      const src = require('fs').readFileSync(process.argv[1], 'utf8');
      const L = new Function(src.slice(0, src.indexOf('let _lang')) + '; return LOCALES;')();
      process.stdout.write(JSON.stringify({fr: L.fr, en: L.en}));
    """
    sortie = subprocess.run(['node', '-e', script, os.path.join(ICI, 'static', 'js', 'bh-locales.js')],
                            capture_output=True, text=True, check=True)
    return json.loads(sortie.stdout)


@pytest.mark.skipif(shutil.which('node') is None, reason='Node absent')
@pytest.mark.parametrize('langue', ['fr', 'en'])
def test_toutes_les_cles_sont_traduites(langue):
    dico = _dictionnaire()[langue]
    manquantes = []
    for cle, ou in sorted(_cles_utilisees().items()):
        val = dico
        for part in cle.split('.'):
            val = val.get(part) if isinstance(val, dict) else None
        if not isinstance(val, (str, list)):
            manquantes.append(f"{cle} ({', '.join(sorted(ou))})")
    assert not manquantes, 'Traductions manquantes :\n' + '\n'.join(manquantes)
