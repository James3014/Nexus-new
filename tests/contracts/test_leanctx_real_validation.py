from scripts.ops.leanctx_real_validation import get_validation_report

def test_report_schema_mock():
    report = get_validation_report("mock", tasks=20)
    required_keys = {
        "sample_size",
        "token_delta_pct",
        "latency_delta_pct",
        "task_success_rate_delta_pct",
        "fallback_rate",
        "p95_latency_legacy",
        "p95_latency_leanctx",
        "recommendation",
        "reasons",
    }
    assert required_keys.issubset(report.keys())
    assert report["recommendation"] == "GO"
    assert report["sample_size"] == 20


def test_no_go_when_binary_missing(monkeypatch):
    monkeypatch.setattr("scripts.ops.leanctx_real_validation.shutil.which", lambda _: None)
    report = get_validation_report("real", tasks=20)
    assert report["recommendation"] == "NO_GO"
    assert any("binary is missing" in r for r in report["reasons"])
    assert report["sample_size"] == 20


def test_go_when_thresholds_pass(monkeypatch):
    monkeypatch.setattr(
        "scripts.ops.leanctx_real_validation.shutil.which", lambda _: "/usr/local/bin/lean-ctx"
    )
    metrics = {
        "legacy_tokens_total": 1000.0,
        "leanctx_tokens_total": 900.0,
        "legacy_success_rate": 0.90,
        "leanctx_success_rate": 0.92,
        "fallback_events": 0,
        "legacy_latency_samples": [1.0] * 20,
        "leanctx_latency_samples": [1.05] * 20,
    }
    monkeypatch.setattr(
        "scripts.ops.leanctx_real_validation.collect_real_metrics", lambda tasks: metrics
    )
    report = get_validation_report("real", tasks=20)
    assert report["recommendation"] == "GO"
    assert report["token_delta_pct"] < 0
    assert report["latency_delta_pct"] <= 10
    assert report["fallback_rate"] < 0.05


def test_no_go_when_threshold_breached(monkeypatch):
    monkeypatch.setattr(
        "scripts.ops.leanctx_real_validation.shutil.which", lambda _: "/usr/local/bin/lean-ctx"
    )
    metrics = {
        "legacy_tokens_total": 1000.0,
        "leanctx_tokens_total": 900.0,
        "legacy_success_rate": 0.90,
        "leanctx_success_rate": 0.92,
        "fallback_events": 2,  # 2 / 20 = 0.10 > 0.05
        "legacy_latency_samples": [1.0] * 20,
        "leanctx_latency_samples": [1.05] * 20,
    }
    monkeypatch.setattr(
        "scripts.ops.leanctx_real_validation.collect_real_metrics", lambda tasks: metrics
    )
    report = get_validation_report("real", tasks=20)
    assert report["recommendation"] == "NO_GO"
    assert any("fallback_rate must be < 0.05" in r for r in report["reasons"])
