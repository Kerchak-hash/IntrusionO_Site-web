#!/usr/bin/env python3
"""Importe les actualités des flux RSS et leur associe une image du même thème.

Règles :
  1. Chaque article reçoit un thème (cyber, prog, maint) selon ses mots-clés.
  2. L'image est prise UNIQUEMENT dans images/bibliotheque/<thème>/ :
     une image dont le thème ne correspond pas n'est jamais utilisée.
  3. Si le thème n'a pas d'image et que la variable UNSPLASH_KEY est définie,
     une photo est cherchée sur Unsplash avec une requête propre au thème.
  4. Sans image valide, l'article s'affiche avec le fond de marque.

Utilisation, depuis la racine du site :
    python3 scripts/import_actualites.py
    UNSPLASH_KEY=votre_cle python3 scripts/import_actualites.py   (option)
"""
import argparse, datetime, email.utils, hashlib, html, json, os, random, re, shutil, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIBLIO = ROOT / "images" / "bibliotheque"
NEWS = ROOT / "images" / "news"
UA = {"User-Agent": "IntrusionActualites/1.0 (+https://www.votre-domaine.com/)"}
EXT = {".jpg", ".jpeg", ".png", ".webp"}
MOTS = {
    "cyber": ["ransomware", "vulnerab", "breach", "hack", "malware", "phishing", "security", "exploit", "attack", "leak", "cyber"],
    "prog": ["code", "python", "javascript", "github", "developer", "open source", "release", "programming", "api", "framework"],
    "maint": ["update", "patch", "windows", "linux", "backup", "driver", "maintenance", "repair"],
}
REQUETE_UNSPLASH = {"cyber": "cybersecurity network", "prog": "programming code screen", "maint": "computer repair maintenance"}


def fetch(url, headers=None, timeout=25):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def theme_de(texte, defaut):
    t = texte.lower()
    for theme, mots in MOTS.items():
        if any(m in t for m in mots):
            return theme
    return defaut


def date_iso(texte):
    try:
        return email.utils.parsedate_to_datetime(texte).date().isoformat()
    except Exception:
        return datetime.date.today().isoformat()


def image_bibliotheque(theme, cle):
    dossier = BIBLIO / theme
    if not dossier.exists():
        return None, None
    photos = sorted(f for f in dossier.iterdir() if f.suffix.lower() in EXT)
    if not photos:
        return None, None
    # Choix stable pour un même article (pas de changement à chaque import)
    index = int(hashlib.md5(cle.encode()).hexdigest(), 16) % len(photos)
    choisie = photos[index]
    return f"images/bibliotheque/{theme}/{choisie.name}", f"Image de la bibliothèque ({theme})"


def image_unsplash(theme, cle):
    key = os.environ.get("UNSPLASH_KEY")
    if not key:
        return None, None
    q = urllib.parse.urlencode({"query": REQUETE_UNSPLASH[theme], "per_page": 10, "orientation": "landscape"})
    try:
        data = json.loads(fetch(f"https://api.unsplash.com/search/photos?{q}", {"Authorization": f"Client-ID {key}"}))
        resultats = data.get("results", [])
        if not resultats:
            return None, None
        photo = resultats[int(hashlib.md5(cle.encode()).hexdigest(), 16) % len(resultats)]
        url = photo["urls"]["regular"]
        cible = NEWS / (re.sub(r"[^a-z0-9]+", "-", cle.lower())[:60] + ".jpg")
        cible.write_bytes(fetch(url))
        auteur = photo["user"]["name"]
        lien = photo["links"]["html"]
        return f"images/news/{cible.name}", f"Photo : {auteur} sur Unsplash ({lien})"
    except Exception as e:
        print(f"[image Unsplash ignorée] {e}", file=sys.stderr)
        return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=4, help="articles par source")
    args = ap.parse_args()
    config = json.loads((ROOT / "scripts" / "sources.json").read_text(encoding="utf-8"))
    NEWS.mkdir(parents=True, exist_ok=True)
    resultats = []
    for src in config["sources"]:
        try:
            racine = ET.fromstring(fetch(src["url"]))
        except Exception as e:
            print(f"[ignoré] {src['nom']} : {e}", file=sys.stderr)
            continue
        for i, item in enumerate(racine.findall(".//item")[: args.max]):
            titre = html.unescape(item.findtext("title", default="").strip())
            lien = item.findtext("link", default="").strip()
            if not titre or not lien:
                continue
            theme = theme_de(titre, src.get("theme", "cyber"))
            cle = f"{src['nom']}-{i}-{lien}"
            img, credit = image_bibliotheque(theme, cle)
            if not img:
                img, credit = image_unsplash(theme, cle)
            resultats.append({
                "theme": theme, "date": date_iso(item.findtext("pubDate", default="")),
                "url": lien, "src": src["nom"], "img": img, "credit": credit,
                "fr": titre, "en": titre
            })
            time.sleep(0.4)
    resultats.sort(key=lambda a: a["date"], reverse=True)
    (ROOT / "actualites.json").write_text(json.dumps(resultats, ensure_ascii=False, indent=2), encoding="utf-8")
    avec_image = sum(1 for r in resultats if r["img"])
    print(f"{len(resultats)} actualités écrites dans actualites.json ({avec_image} avec image)")


if __name__ == "__main__":
    main()
