#!/usr/bin/env python3
"""Holt GTFS-ZIPs vom Nationalen Zugangspunkt (NAP) und veröffentlicht sie im Release "latest".
Gleiche Logik wie naplib.php der App: Datensatz lesen, jüngste gültige GTFS-Datei wählen,
nur bei neuem Stand (und Mindestabstand) laden. Schlüssel nur aus der Umgebung (NAP_API_KEY)."""
import json, os, re, sys, time, hashlib, subprocess, zipfile, urllib.request, urllib.error
from datetime import datetime, timezone

BASE = os.environ.get("NAP_BASE", "https://nap.transportes.gob.es").rstrip("/")
KEY = os.environ.get("NAP_API_KEY", "").strip()
REPO = os.environ.get("GITHUB_REPOSITORY", "investigasteve/camino-gtfs")
TAG = "latest"
DRY = os.environ.get("SYNC_DRY") == "1"          # Test: nichts hochladen
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.environ.get("SYNC_WORK", "/tmp/gtfs-work")
os.makedirs(WORK, exist_ok=True)

def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def nap_get(path):
    req = urllib.request.Request(BASE + path, headers={"ApiKey": KEY, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8")), ""
    except urllib.error.HTTPError as e:
        if e.code in (401, 403): return None, "NAP hat den Zugriff abgelehnt (%d)" % e.code
        return None, "NAP-Fehler %d" % e.code
    except Exception as e:
        return None, "keine Verbindung zum NAP: %s" % e

def pick_file(ds):
    best = None
    for f in ds.get("ficheros") or []:
        t = str(f.get("nombreTipoFichero", "")).lower()
        if "gtfs" not in t: continue
        if re.search(r"\b(rt|real[ -]?time|tiempo real)\b", t): continue
        if f.get("esValido") is False: continue
        if best is None or str(f.get("fechaActualizacion", "")) > str(best.get("fechaActualizacion", "")): best = f
    return best

def day(s):
    try: return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception: return ""

def download(url, dest):
    if not (url.startswith("https://") or BASE.startswith("http://127.0.0.1")): raise RuntimeError("kein https-Link")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as o:
        while True:
            b = r.read(1 << 20)
            if not b: break
            o.write(b)

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def check_zip(p):
    if not zipfile.is_zipfile(p): return "keine gültige ZIP-Datei"
    n = set(zipfile.ZipFile(p).namelist())
    for need in ("stops.txt", "stop_times.txt", "trips.txt"):
        if need not in n: return "%s fehlt in der ZIP" % need
    return ""

def sh(*a):
    return subprocess.run(a, capture_output=True, text=True)

def main():
    mpath = os.path.join(ROOT, "manifest.json")
    m = json.load(open(mpath)) if os.path.exists(mpath) else {}
    m.setdefault("dateien", {}); log = m.setdefault("protokoll", [])
    def L(t):
        print(t); log.insert(0, now() + "  " + t); del log[30:]
    if not KEY:
        L("Kein NAP_API_KEY als Secret hinterlegt."); finish(m, mpath, 1); return
    feeds = [f for f in json.load(open(os.path.join(ROOT, "feeds.json"))) if f.get("aktiv", True)]
    if not DRY and sh("gh", "release", "view", TAG, "--repo", REPO).returncode != 0:
        sh("gh", "release", "create", TAG, "--repo", REPO, "--title", "Aktueller Stand", "--notes", "Fahrplan-Dateien (GTFS), automatisch aus dem NAP.")
    errors = 0; changed = 0
    for fd in feeds:
        z = fd["zip"]; cur = m["dateien"].get(z, {})
        j, err = nap_get("/api/v2/conjunto-dato/%d" % fd["ds"])
        if j is None: L("%s: %s" % (z, err)); errors += 1; continue
        f = pick_file(j.get("data") or {})
        if not f: L("%s: keine GTFS-Datei im Datensatz %d" % (z, fd["ds"])); errors += 1; continue
        stand = str(f.get("fechaActualizacion", "")); bis = day(str(f.get("fechaHasta", "")))
        cur.update({"geprueft": now(), "bis": bis, "von": day(str(f.get("fechaDesde", "")))}); m["dateien"][z] = cur
        got = cur.get("stand_geladen", "")
        age_ok = (time.time() - cur.get("geladen_am", 0)) >= fd.get("min", 7) * 86400
        knapp = bool(bis) and (datetime.strptime(bis, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() - time.time()) < 3 * 86400
        fehlt = not cur.get("sha256")
        if not (fehlt or (got != stand and (age_ok or knapp))):
            continue
        j2, err = nap_get("/api/v2/fichero/%d/descarga" % int(f["id"]))
        url = ((j2 or {}).get("data") or {}).get("enlaceDescarga", "")
        if not url: L("%s: kein Download-Link (%s)" % (z, err)); errors += 1; continue
        p = os.path.join(WORK, z)
        try: download(url, p)
        except Exception as e: L("%s: Download fehlgeschlagen: %s" % (z, e)); errors += 1; continue
        e = check_zip(p)
        if e: L("%s: Datei unbrauchbar: %s" % (z, e)); errors += 1; os.remove(p); continue
        if not DRY:
            r = sh("gh", "release", "upload", TAG, p, "--clobber", "--repo", REPO)
            if r.returncode != 0: L("%s: Hochladen fehlgeschlagen: %s" % (z, r.stderr.strip()[:200])); errors += 1; continue
        cur.update({"bytes": os.path.getsize(p), "sha256": sha256(p), "stand_geladen": stand, "geladen_am": int(time.time()),
                    "url": "https://github.com/%s/releases/download/%s/%s" % (REPO, TAG, z)})
        cur.pop("teile", None); cur.pop("hinweis", None)
        m["dateien"][z] = cur; changed += 1
        L("%s: neuer Stand %s, gültig bis %s, %.1f MB veröffentlicht." % (z, stand[:10], bis, cur["bytes"] / 1048576))
        os.remove(p)
    if not changed and not errors: L("Geprüft: alle Dateien sind aktuell.")
    finish(m, mpath, 1 if errors else 0)

def finish(m, mpath, code):
    m["stand"] = now()
    json.dump(m, open(mpath, "w"), indent=2, ensure_ascii=False)
    sys.exit(code)

main()
