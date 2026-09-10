"""Determinism check (kill criterion 2: 'diffs are nondeterministic run-to-run
-> KILL'). Re-probes two jumps completely fresh (re-pull images, new
containers, fresh double-probe) and compares the re-derived diff to the
verdict recorded in results.json.

Jumps chosen: vaultwarden 1.34.3->1.35.8 (recorded DIFF, 4 stable fields
after timing strip) and jellyfin 10.11.3->10.11.4 (recorded no-diff).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "probe-proxy"))
sys.path.insert(0, str(HERE))

import corpus
from run_corpus import (probe_image, stable_fingerprint, diff_fps,
                        classify, RESULTS)


def get_fp(dc, app, tag, idx):
    image = f"{corpus.APPS[app]['repo']}:{tag}"
    print(f"  pulling {image} ...", flush=True)
    dc.images.pull(image)
    runs = [probe_image(dc, app, tag, idx * 2),
            probe_image(dc, app, tag, idx * 2 + 1)]
    return stable_fingerprint(runs)


CHECKS = [
    ("vaultwarden", "1.34.3", "1.35.8"),
    ("jellyfin", "10.11.3", "10.11.4"),
]

def main():
    import docker
    dc = docker.from_env()
    res = json.loads(RESULTS.read_text())
    out = {}
    for i, (app, old, new) in enumerate(CHECKS):
        rkey = f"{app}|{old}|{new}"
        rec = res[rkey]
        print(f"[re-probe] {rkey} recorded: diff={rec['diff']}")
        old_stable, _ = get_fp(dc, app, old, i * 2)
        new_stable, _ = get_fp(dc, app, new, i * 2 + 1)
        changed = diff_fps(old_stable, new_stable)
        out[rkey] = {
            "recorded_diff": rec["diff"],
            "repro_diff": bool(changed),
            "repro_n_changed": len(changed),
            "repro_class": classify(changed),
            "repro_changed": sorted(changed.keys()),
            "repro_changed_sorted": sorted(rec["changed_fields"].keys()),
        }
        print(f"  recorded={rec['diff']} ({len(rec['changed_fields'])} fields) "
              f"repro={bool(changed)} ({len(changed)} fields) "
              f"match={'YES' if bool(changed) == rec['diff'] else 'NO'}")
        import subprocess
        for tag in (old, new):
            subprocess.run(["docker", "rmi", f"{corpus.APPS[app]['repo']}:{tag}"],
                           capture_output=True, timeout=120)
    (HERE / "determinism.json").write_text(json.dumps(out, indent=2))
    all_match = all(v["recorded_diff"] == v["repro_diff"] for v in out.values())
    print("DETERMINISM:", "REPRODUCED" if all_match else "MISMATCH")


if __name__ == "__main__":
    main()