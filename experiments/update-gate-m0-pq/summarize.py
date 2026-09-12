import json
from pathlib import Path
d = json.loads(Path('/home/osteri/projects/probe-proxy/experiments/update-gate-m0-pq/results_pq.json').read_text())
print(len(d), "jumps")
for k, v in d.items():
    if "error" in v:
        print(f"ERROR {k}: {v['error'][:80]}")
    else:
        ch = v["changed_fields"]
        print(f"{v['diff_class']:15s} {k}: {list(ch.keys())}")
