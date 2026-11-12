#!/usr/bin/env python3
"""A0 refresh (docs/PREP-2026-11-13.md): re-probe every source docs 01/02/05
depend on and print a dated summary for pasting into the A0 work-order issue.

Read-only. Never writes snapshots itself — snapshot writes are ingest-lane PRs
with hashes. Usage: python3 scripts/a0_refresh.py
"""
import hashlib, json, re, ssl, sys, urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False  # spaceappschallenge.org chain failed verification 2026-11-12; hash still detects changes
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 cosmic-consultants A0"}

def fetch(url, limit=2_000_000):
    # data.nasa.gov intermittently stalls first connects (observed 2026-11-12:
    # 2 of 4 CKAN queries timed out at 60s while others answered). One retry.
    last = None
    for _ in range(2):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90, context=CTX) as r:
                return r.status, r.read(limit)
        except Exception as e:  # noqa: BLE001 - reported as ERROR line by caller
            last = e
    raise last

def line(name, fn):
    try:
        print(f"{name}: {fn()}")
    except Exception as e:
        print(f"{name}: ERROR {type(e).__name__}: {e}")

def challenge():
    _, b = fetch("https://www.spaceappschallenge.org/2026/challenges/permanent-moon-base-locations-and-mars/")
    h = hashlib.sha256(b).hexdigest()[:16]
    resources = "PUBLISHED?" if b"Resources will be available" not in b else "still placeholder"
    upd = re.search(rb"lastPublishedAt..:..([0-9T:.-]+Z)", b)
    return f"sha256[:16]={h} bytes={len(b)} resources={resources} lastPublishedAt={upd.group(1).decode() if upd else '?'} (baseline 2026-11-12: 2026-10-29T19:56:20Z)"

def apis():
    _, b = fetch("https://api.nasa.gov/assets/json/apis.json")
    d = json.loads(b)
    return f"entries={len(d)} names={[a['name'] for a in d]} (baseline: 16)"

def ckan_count(fq=None, q=None):
    p = "rows=0" + (f"&fq={fq}" if fq else "") + (f"&q={q}" if q else "")
    _, b = fetch(f"https://data.nasa.gov/api/3/action/package_search?{p}")
    return json.loads(b)["result"]["count"]

if __name__ == "__main__":
    line("challenge page", challenge)
    line("api.nasa.gov apis.json", apis)
    line("CKAN total (baseline 36518)", lambda: ckan_count())
    line("CKAN tags:mars (1321)", lambda: ckan_count(fq="tags:mars"))
    line("CKAN q=regolith (52)", lambda: ckan_count(q="regolith"))
    line("CKAN q=lunar (596)", lambda: ckan_count(q="lunar"))
    print("\nNext: diff against docs/research/01,02,05 and paste this output into the A0 issue.", file=sys.stderr)
