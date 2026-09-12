"""pq-gate M0 static-CBOM leg: acdi scan of old/new image rootfs per jump.

For each jump in the live corpus (results_pq.json), extract the image
filesystem (docker create + docker export), run the PINNED acdi binary
(v0.5.2, x86_64 musl — no host toolchain involvement) over it, save both
CBOMs, and diff them with `acdi diff --format json`. The static delta is
the incumbent comparison for the cross-tab: does a static CBOM diff see
crypto changes the live probe misses, and vice versa?

Disk care: images are large; we export to a scratch dir, scan, delete the
export immediately, then docker rmi per last-use (mirrors run_corpus_pq).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

HERE = Path(__file__).parent
ACDI = HERE / "acdi"
CBOM_DIR = HERE / "cboms"
RESULTS = HERE / "results_acdi.json"
LIVE = HERE / "results_pq.json"
SCRATCH = Path("/tmp/pqgate-scratch")


def sh(*args, **kw):
    r = subprocess.run(list(args), capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"{args[0]} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def export_image(repo: str, tag: str, outdir: Path) -> Path:
    image = f"{repo}:{tag}"
    cname = f"pqexport-{repo.replace('/', '-')}-{tag}"
    sh("docker", "create", "--name", cname, image)
    try:
        tarpath = outdir / "rootfs.tar"
        with open(tarpath, "wb") as f:
            subprocess.run(["docker", "export", cname], stdout=f,
                           check=True, timeout=600)
        root = outdir / "rootfs"
        root.mkdir(exist_ok=True)
        # 'data' filter aborts on absolute-symlink members (docker rootfs
        # layers have some, e.g. bin/pidof, etc/alternatives/*). Those are
        # path aliases, not crypto material — skip them rather than die.
        skipped = 0
        with tarfile.open(tarpath) as tf:
            for m in tf.getmembers():
                try:
                    tf.extract(m, root, filter="data")
                except Exception:
                    skipped += 1
        print(f"      (extract: skipped {skipped} bad-link members)",
              flush=True)
        tarpath.unlink()
        return root
    finally:
        sh("docker", "rm", cname)


def scan(root: Path, out: Path) -> int:
    """Run pinned acdi over an extracted rootfs; returns asset count."""
    r = subprocess.run([str(ACDI), "scan", "--quiet", "--format",
                        "cyclonedx-1.7", "-o", str(out), str(root)],
                       capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"acdi scan failed: {r.stderr.strip()[:300]}")
    try:
        return len(json.loads(out.read_text()).get("components", []))
    except Exception:
        return -1


def cbom_delta(old: Path, new: Path) -> dict:
    r = subprocess.run([str(ACDI), "diff", "--format", "json",
                        str(old), str(new)],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        return {"error": r.stderr.strip()[:300]}
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"raw": r.stdout[:2000]}


def main(only_apps: list[str]):
    import corpus_pq as corpus
    live = json.loads(LIVE.read_text())
    res = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    CBOM_DIR.mkdir(exist_ok=True)

    jumps = [j for j in corpus.JUMPS
             if not only_apps or j["app"] in only_apps]
    jumps = [j for j in jumps
             if f"{j['app']}|{j['old']}|{j['new']}" not in res]

    # plan image last-use for rmi after each image's final scan (host disk
    # is 99% full; without this the full corpus needs ~20GB of images)
    last_use = {}
    for i, j in enumerate(jumps):
        last_use.setdefault(j["app"], {})
        for tag in (j["old"], j["new"]):
            last_use[j["app"]][tag] = max(last_use[j["app"]].get(tag, -1), i)

    for i, j in enumerate(jumps):
        rkey = f"{j['app']}|{j['old']}|{j['new']}"
        print(f"[{i+1}/{len(jumps)}] acdi {j['app']} {j['old']} -> "
              f"{j['new']}", flush=True)
        try:
            if SCRATCH.exists():
                shutil.rmtree(SCRATCH)
            SCRATCH.mkdir(parents=True)
            old_root = export_image(corpus.APPS[j["app"]]["repo"],
                                    j["old"], SCRATCH)
            old_cbom = CBOM_DIR / f"{j['app']}-{j['old']}.json"
            n_old = scan(old_root, old_cbom)
            shutil.rmtree(old_root)
            new_root = export_image(corpus.APPS[j["app"]]["repo"],
                                    j["new"], SCRATCH)
            new_cbom = CBOM_DIR / f"{j['app']}-{j['new']}.json"
            n_new = scan(new_root, new_cbom)
            shutil.rmtree(new_root)
            delta = cbom_delta(old_cbom, new_cbom)
            # count added/removed/changed crypto assets
            n_add = n_rem = n_chg = 0
            if isinstance(delta, dict):
                n_add = len(delta.get("added", []))
                n_rem = len(delta.get("removed", []))
                n_chg = len(delta.get("changed", []))
            res[rkey] = {
                "app": j["app"], "old": j["old"], "new": j["new"],
                "note": j["note"],
                "cbom_assets_old": n_old, "cbom_assets_new": n_new,
                "static_crypto_added": n_add,
                "static_crypto_removed": n_rem,
                "static_crypto_changed": n_chg,
                "static_diff": bool(n_add or n_rem or n_chg),
                "delta": delta,
            }
        except Exception as e:
            res[rkey] = {"app": j["app"], "old": j["old"], "new": j["new"],
                         "error": str(e)[:300], "static_diff": False}
        RESULTS.write_text(json.dumps(res, indent=2))
        r = res[rkey]
        print(f"    assets {r.get('cbom_assets_old')} -> "
              f"{r.get('cbom_assets_new')} static_diff="
              f"{r.get('static_diff')} "
              f"(+{r.get('static_crypto_added')} "
              f"-{r.get('static_crypto_removed')} "
              f"~{r.get('static_crypto_changed')}) "
              f"{r.get('error', '')}", flush=True)
        if SCRATCH.exists():
            shutil.rmtree(SCRATCH)
        for tag in (j["old"], j["new"]):
            if isinstance(tag, str) and last_use[j["app"]].get(tag) == i:
                image = f"{corpus.APPS[j['app']]['repo']}:{tag}"
                try:
                    subprocess.run(["docker", "rmi", image],
                                   capture_output=True, timeout=300)
                    print(f"    rmi {image}", flush=True)
                except Exception:
                    pass
    print("DONE —", RESULTS)


if __name__ == "__main__":
    main(sys.argv[1:])
