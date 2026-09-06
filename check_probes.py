"""Sanity check: probe suite runs end-to-end against a disposable
httpbin container. Exit 0 iff >=10 probes return non-error dicts."""
import sys
from probe_proxy.matrix import run_single
from probe_proxy import probes

fp = run_single("httpbin")
ok = 0
for name, val in fp.items():
    if name.startswith("_"):
        continue
    status = "ERR " if (not isinstance(val, dict) or "error" in val) else "ok  "
    print(f"{status} {name}: {val}")
    if status.strip() == "ok":
        ok += 1
print(f"\n{ok}/{len(probes.PROBES)} probes healthy")
sys.exit(0 if ok >= 10 else 1)
