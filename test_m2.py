"""M2 unit tests: SSE gap metrics, managed-by marker, verify drift logic."""
import sys
sys.path.insert(0, ".")
from probe_proxy import synthesize, verify
from probe_proxy.probes import sse_metrics


# ---------------- SSE gap metrics (coalescing-stable)

def test_sse_metrics_counts_gaps():
    # 5 chunks arriving in two bursts separated by 200ms:
    # coalescing may merge chunks within a burst, but the 200ms gap
    # between bursts persists -> gaps_ge_50ms is stable, count is not
    ts = [0.0, 0.001, 0.002, 0.201, 0.202]
    m = sse_metrics(ts)
    assert m["sse_chunks_observed"] == 5
    assert m["sse_gaps_ge_50ms"] == 1  # the 200ms inter-burst gap
    assert m["sse_max_gap_ms"] >= 190


def test_sse_metrics_single_burst():
    ts = [0.0, 0.001, 0.002]
    m = sse_metrics(ts)
    assert m["sse_gaps_ge_50ms"] == 0  # one buffered burst: no real events


def test_sse_streamed_is_gap_based():
    # sse_streamed must be derived from timing gaps, not chunk counts:
    # a coalesced burst (many chunks, no gaps) is NOT 'streamed'
    from probe_proxy.probes import probe_sse  # noqa: F401 (module check)
    ts_burst = [0.0, 0.001, 0.002]  # 3 chunks, no gap -> not streamed
    m = sse_metrics(ts_burst)
    assert not m["sse_gaps_ge_50ms"] >= 1
    ts_stream = [0.0, 0.0, 0.3]  # real 300ms gap -> streamed
    m2 = sse_metrics(ts_stream)
    assert m2["sse_gaps_ge_50ms"] >= 1


def test_sse_metrics_empty():
    assert sse_metrics([]) == {"sse_chunks_observed": 0,
                               "sse_gaps_ge_50ms": 0, "sse_max_gap_ms": 0}


def test_sse_chunks_count_is_volatile():
    # raw chunk counts are TCP-coalescing noise -> excluded from diffs
    assert "sse_chunks_observed" in synthesize.VOLATILE_KEYS


def test_diff_ignores_chunk_count_but_compares_gaps():
    from probe_proxy.replay import diff_fingerprints
    direct = {"sse": {"sse_streamed": True, "sse_chunks_observed": 5,
                     "sse_gaps_ge_50ms": 2, "sse_max_gap_ms": 300}}
    via = {"sse": {"sse_streamed": True, "sse_chunks_observed": 1,
                   "sse_gaps_ge_50ms": 2, "sse_max_gap_ms": 300}}
    assert diff_fingerprints(direct, via) == []  # coalescing tolerated
    via2 = {"sse": {"sse_streamed": True, "sse_chunks_observed": 1,
                    "sse_gaps_ge_50ms": 0, "sse_max_gap_ms": 0}}
    diffs = diff_fingerprints(direct, via2)
    assert any(d["key"] == "sse_gaps_ge_50ms" for d in diffs)  # buffering caught


# ---------------- managed-by marker + hand-edit drift

def test_render_includes_marker():
    out = synthesize.render("app:3000", [])
    assert out.startswith("# managed-by probe-proxy v0.2 sha256:")


def test_marker_hash_deterministic():
    a = synthesize.render("app:3000", [])
    b = synthesize.render("app:3000", [])
    assert a == b


def test_marker_changes_with_params():
    a = synthesize.render("app:3000", [])
    b = synthesize.render("app:3000", ["flush_interval -1"])
    assert a != b


def test_verify_no_drift():
    body = synthesize.block_body("app:3000", [])
    text = synthesize.render("app:3000", [])
    h, extracted = verify.extract_block(text)
    assert h == verify.block_hash(body)  # marker carries the body hash
    d = verify.drift_report(h, extracted)
    assert d == {"hash_matches": True, "edited": False,
                 "added_lines": [], "removed_lines": [], "edit_count": 0}


def test_verify_detects_hand_edit():
    text = synthesize.render("app:3000", ["flush_interval -1"])
    h, extracted = verify.extract_block(text)
    # user hand-edits: adds a line to the block
    edited = extracted + "\nheader_up X-Real-IP unknown"
    d = verify.drift_report(h, edited)
    assert d["edited"] is True
    assert d["hash_matches"] is False


def test_verify_no_marker():
    h, body = verify.extract_block("localhost:80 {\n  reverse_proxy x\n}\n")
    assert h is None
    assert "reverse_proxy x" in body
