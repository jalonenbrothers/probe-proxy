"""Keyword-scan channel (Bulwark-style, computed locally — no Bulwark dep).

For each jump, scan GitHub release notes of every release line strictly
after the old version up to and including the new version (the notes an
operator would read for that upgrade). Flags = regex hits, two channels:
  all    : any soft-or-strong keyword
  strong : breaking/migration/action-required keywords only
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

import corpus

CACHE = Path(__file__).parent / "notes_cache.json"

SOFT = re.compile(
    r"deprecat|removed|renamed|no longer|changed default|schema|"
    r"upgrade guide|reconfigure|required", re.I)
STRONG = re.compile(
    r"breaking|migrat|incompatible|action required|"
    r"must (?:be )?(?:manual|update|reconfigure|migrate)", re.I)


def gh(url: str, tok: str | None = None) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def load_cache() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    return {}


def fetch_repo_releases(repo: str, cache: dict, max_pages: int = 4) -> list:
    """All releases (tag_name, name, published_at, body), cached on disk."""
    if repo in cache:
        return cache[repo]
    rels, url = [], f"https://api.github.com/repos/{repo}/releases?per_page=100"
    for _ in range(max_pages):
        try:
            d = gh(url)
        except Exception as e:
            print(f"  [notes] {repo} page fetch failed: {e}")
            break
        if not d:
            break
        rels += [{"tag": r["tag_name"], "name": r.get("name") or "",
                  "date": r.get("published_at") or "",
                  "body": r.get("body") or ""} for r in d]
        url = (f"https://api.github.com/repos/{repo}/releases?per_page=100"
               f"&page={len(rels)//100 + 1}")
        if len(d) < 100:
            break
        time.sleep(1)
    cache[repo] = rels
    CACHE.write_text(json.dumps(cache))
    return rels


def ver_tuple(v: str):
    v = v.lstrip("v")
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def line_tags_between(app: str, old: str, new: str) -> list[str]:
    """Version tags to scan: new tag itself + the .0 release of every line
    between (old, new]. e.g. 1.35.8 -> 1.37.2 scans 1.36.0, 1.37.0, 1.37.2."""
    spec = corpus.APPS[app]
    fmt = spec["tagfmt"]
    ot, nt = ver_tuple(old), ver_tuple(new)
    if len(ot) == len(nt) == 3 and app not in ("homeassistant", "pihole"):
        tags = []
        maj_min = lambda t: (t[0], t[1])
        # new tag itself
        tags.append(fmt.format(new.lstrip("v")))
        # .0 of intermediate + new lines
        lo, hi = maj_min(ot), maj_min(nt)
        lines = [(ot[0], y) for y in range(ot[1] + 1, 200)] + \
                [(x, 0) for x in range(ot[0] + 1, nt[0] + 1)]
        for mj, mn in lines:
            if lo < (mj, mn) <= hi:
                tags.append(fmt.format(f"{mj}.{mn}.0"))
        return list(dict.fromkeys(t for t in tags))
    # calver apps: just the new tag
    return [fmt.format(new.lstrip("v"))]


def _shift_month(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    m -= 1
    if m == 0:
        y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


def _tag_date(tag: str):
    m = re.fullmatch(r"(20\d{2})\.(\d{2})\.\d+", tag.lstrip("v"))
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None


def scan_jump(app: str, old: str, new: str, cache: dict) -> dict:
    spec = corpus.APPS[app]
    rels = fetch_repo_releases(spec["gh"], cache)
    want = {t.lower() for t in line_tags_between(app, old, new)}
    by_tag = {r["tag"].lower(): r for r in rels}
    bodies, matched = [], []
    for t in want:
        r = by_tag.get(t)
        if r:
            bodies.append(f"# {r['tag']}\n{r['body']}")
            matched.append(r["tag"])
    # calver fallback (pihole: docker calver tags don't match GH semver
    # release tags): scan releases published in the new tag's month or
    # the month before
    if not bodies and (d := _tag_date(new)):
        for r in rels:
            if r["date"][:7] in (d, _shift_month(d)):
                bodies.append(f"# {r['tag']}\n{r['body']}")
                matched.append(r["tag"])
    blob = "\n".join(bodies)
    if not blob:
        return {"flags_all": 0, "flags_strong": 0, "matched_tags": [],
                "note": "no matching release notes found"}
    soft = sorted(set(m.group(0).lower() for m in SOFT.finditer(blob)))
    strong = sorted(set(m.group(0).lower() for m in STRONG.finditer(blob)))
    return {"flags_all": len(soft) + len(strong),
            "flags_strong": len(strong),
            "matched_tags": matched,
            "soft_kw": soft[:12], "strong_kw": strong[:12]}


if __name__ == "__main__":
    cache = load_cache()
    out = {}
    for j in corpus.JUMPS:
        key = f"{j['app']}|{j['old']}|{j['new']}"
        res = scan_jump(j["app"], j["old"], j["new"], cache)
        out[key] = res
        print(f"{j['app']:14s} {j['old']} -> {j['new']}: "
              f"all={res['flags_all']} strong={res['flags_strong']} "
              f"tags={res['matched_tags'][:3]}")
    (Path(__file__).parent / "keyword_results.json").write_text(json.dumps(out, indent=2))
    print("done")