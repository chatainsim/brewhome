#!/usr/bin/env python3
"""Crée une release (Gitea/Forgejo ou GitHub) taguée avec APP_VERSION et le
contenu du CHANGELOG.md correspondant en description, si elle n'existe pas
déjà - jusqu'ici fait à la main (copier-coller le changelog dans le
formulaire de release du serveur, une fois par plateforme).

Un seul script partagé entre .forgejo/workflows/release.yml et
.github/workflows/release.yml plutôt qu'une logique dupliquée dans chaque
YAML : les deux API sont quasi identiques pour les releases (Forgejo/Gitea
Actions imite le schéma GitHub - mêmes champs tag_name/name/body/
target_commitish, même chemin /repos/{owner}/{repo}/releases), seuls
RELEASE_API_BASE/RELEASE_REPO/RELEASE_TOKEN changent entre les deux appelants.

Idempotent : si une release existe déjà pour la version courante, ne fait
rien (permet de laisser ce script tourner à chaque push sur main sans se
soucier de savoir si la version a effectivement changé)."""
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_app_version():
    path = os.path.join(ROOT, "brewhome", "blueprints", "admin.py")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', content)
    if not m:
        sys.exit("APP_VERSION introuvable dans blueprints/admin.py")
    return m.group(1)


def extract_changelog_section(version):
    path = os.path.join(ROOT, "CHANGELOG.md")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    header_re = re.compile(r"^## \[.*?\] — \d+ · version " + re.escape(version) + r"\s*$", re.M)
    m = header_re.search(content)
    if not m:
        sys.exit(f"Aucune entrée de changelog pour la version {version}")
    rest = content[m.end():]
    boundary = re.search(r"\n---\n|\n## \[", rest)
    end = m.end() + (boundary.start() if boundary else len(rest))
    return content[m.start():end].strip()


def api_request(method, url, token, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode() or "{}"
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode() or "{}"
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"raw": body}


def main():
    api_base = os.environ["RELEASE_API_BASE"].rstrip("/")
    repo = os.environ["RELEASE_REPO"]
    token = os.environ["RELEASE_TOKEN"]
    sha = os.environ["GITHUB_SHA"]

    version = read_app_version()
    print(f"Version détectée : {version}")

    status, _ = api_request("GET", f"{api_base}/repos/{repo}/releases/tags/{version}", token)
    if status == 200:
        print(f"Release {version} déjà publiée sur {api_base} - rien à faire")
        return

    body = extract_changelog_section(version)
    status, resp = api_request(
        "POST",
        f"{api_base}/repos/{repo}/releases",
        token,
        {"tag_name": version, "name": version, "body": body, "target_commitish": sha},
    )
    if status not in (200, 201):
        sys.exit(f"Échec de création de la release ({status}) : {resp}")
    print(f"Release {version} créée : {resp.get('html_url')}")


if __name__ == "__main__":
    main()
