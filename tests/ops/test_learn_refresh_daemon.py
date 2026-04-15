from scripts.ops import learn_refresh_daemon as daemon


def test_run_cycle_skips_refresh_when_no_due(monkeypatch):
    calls = []

    def fake_run_cmd(args):
        calls.append(args)
        return 0, '{}', ''

    def fake_load_json(path):
        if path == daemon.DEFAULT_PLAN_REPORT:
            return {"due_count": 0, "sources_total": 1}
        return {}

    monkeypatch.setattr(daemon, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(daemon, "load_json", fake_load_json)

    result = daemon.run_cycle(topic="openharness", due_within_days=0)
    assert result["status"] == "SUCCESS"
    assert result["due_count"] == 0
    assert result["refreshed_count"] == 0
    assert result["benchmark_ran"] is False
    assert len(calls) == 1
    assert "learn:refresh-plan" in calls[0]


def test_run_cycle_refreshes_and_benchmarks_when_due(monkeypatch):
    calls = []

    def fake_run_cmd(args):
        calls.append(args)
        cmd = " ".join(args)
        if "learn:refresh-plan" in cmd:
            return 0, '{}', ''
        if "learn:refresh" in cmd:
            return 0, '{}', ''
        if "learn:benchmark" in cmd:
            return 0, '{}', ''
        return 1, '', 'unexpected'

    def fake_load_json(path):
        if path == daemon.DEFAULT_PLAN_REPORT:
            return {"due_count": 1, "sources_total": 1}
        if path == daemon.DEFAULT_REFRESH_REPORT:
            return {"refreshed_count": 1}
        if path == daemon.DEFAULT_BENCHMARK_REPORT:
            return {"best": {"success_rate": 0.8}}
        return {}

    monkeypatch.setattr(daemon, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(daemon, "load_json", fake_load_json)

    result = daemon.run_cycle(
        topic="openharness",
        due_within_days=0,
        benchmark_manifest="docs/research/learn_benchmark_manifest_template.json",
    )
    assert result["status"] == "SUCCESS"
    assert result["due_count"] == 1
    assert result["refreshed_count"] == 1
    assert result["benchmark_ran"] is True
    assert result["benchmark_rc"] == 0
    assert result["benchmark_success_rate"] == 0.8
    assert len(calls) == 3
