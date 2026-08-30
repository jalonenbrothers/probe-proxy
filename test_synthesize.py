"""Unit tests for M1 synthesis + diff logic (no docker needed)."""
import sys
sys.path.insert(0, ".")
from probe_proxy import synthesize
from probe_proxy.replay import diff_fingerprints


def test_pass_through_default():
    fp = {"root": {"root_status": 200}}
    out = synthesize.synthesize(fp, "app:3000")
    assert "reverse_proxy app:3000" in out["caddyfile"]
    assert out["params"] == []  # plain app -> pure pass-through
    assert "admin off" in out["caddyfile"]
    assert "auto_https off" in out["caddyfile"]


def test_streaming_adds_flush():
    fp = {"sse": {"sse_streamed": True, "sse_first_chunk_ms": 0,
                  "sse_chunks_observed": 5}}
    out = synthesize.synthesize(fp, "app:80")
    assert "flush_interval -1" in out["caddyfile"]


def test_volatile_keys_ignored():
    fp = {"sse": {"sse_streamed": False, "sse_first_chunk_ms": 123,
                  "sse_chunks_observed": 1}}
    out = synthesize.synthesize(fp, "app:80")
    assert out["params"] == []


def test_errored_probe_degrades_with_warning():
    fp = {"websocket": {"error": "ConnectionError"}}
    out = synthesize.synthesize(fp, "app:80")
    assert out["params"] == []  # never a confidently-wrong directive
    assert any("websocket" in w for w in out["warnings"])


def test_compression_never_enabled():
    fp = {"compression": {"compression": "gzip", "vary": True}}
    out = synthesize.synthesize(fp, "app:80")
    assert "encode" not in out["caddyfile"]
    assert any("encode left off" in w for w in out["warnings"])


def test_diff_fingerprints_volatile_excluded():
    direct = {"sse": {"sse_streamed": True, "sse_first_chunk_ms": 1,
                      "sse_chunks_observed": 5}}
    via = {"sse": {"sse_streamed": True, "sse_first_chunk_ms": 99,
                   "sse_chunks_observed": 5}}
    assert diff_fingerprints(direct, via) == []


def test_diff_fingerprints_catches_change():
    direct = {"root": {"root_status": 200}}
    via = {"root": {"root_status": 502}}
    d = diff_fingerprints(direct, via)
    assert d == [{"probe": "root", "key": "root_status",
                  "direct": 200, "via": 502}]


def test_iterate_adds_fixer():
    params, warnings = [], []
    diffs = [{"probe": "sse", "key": "sse_streamed",
              "direct": True, "via": False}]
    assert synthesize.iterate(params, warnings, diffs)
    assert "flush_interval -1" in params


def test_iterate_unknown_diff_reports_no_fixer():
    params, warnings = [], []
    diffs = [{"probe": "websocket", "key": "ws_any_data",
              "direct": False, "via": True}]
    assert not synthesize.iterate(params, warnings, diffs)
    assert any("no known fixer" in w for w in warnings)


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
    print("ALL SYNTH TESTS PASSED")
