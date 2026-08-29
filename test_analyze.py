"""Unit checks for the analyzer logic — synthetic fingerprints."""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from analyze import fingerprint_vector

# two identical apps + one different -> 1 of 3 distinguishable
fps = {
    "a": {"root": {"root_status": 200}},
    "b": {"root": {"root_status": 200}},
    "c": {"root": {"root_status": 301}},
}
vecs = {k: fingerprint_vector(v) for k, v in fps.items()}
assert vecs["a"] == vecs["b"]
assert vecs["c"] != vecs["a"]
print("analyzer logic checks: OK")
