from __future__ import annotations

import json

from scripts.ops.build_signal_collector_split_pregate import build_signal_collector_split_pregate, main


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_signal_collector_split_pregate_defers_without_deletion_evidence(tmp_path):
    repo = tmp_path / "repo"
    _write(repo / "nexus/research/flow/route_decider.py", "def collect_route_signals():\n    return {}\n")
    _write(repo / "nexus/app/research_flow_service.py", "from x import collect_route_signals\ncollect_route_signals()\n")
    _write(repo / "tests/app/test_research_flow_service.py", "def test_x(monkeypatch):\n    collect_route_signals()\n")

    report = build_signal_collector_split_pregate(repo_root=repo)

    assert report["status"] == "PASS"
    assert report["decision"] == "DEFERRED"
    assert report["implementation_allowed"] is False
    assert "deletion_test_missing" in report["blockers"]
    assert report["summary"]["definition_count"] == 1
    assert report["summary"]["monkeypatch_sensitive_file_count"] == 1


def test_signal_collector_split_pregate_approves_split_with_deletion_test(tmp_path):
    repo = tmp_path / "repo"
    _write(
        repo / "nexus/research/flow/route_decider.py",
        "from nexus.research.flow.signal_collector import collect_route_signals\n",
    )
    _write(repo / "nexus/research/flow/signal_collector.py", "def collect_route_signals():\n    return {}\n")
    _write(
        repo / "tests/app/test_research_flow_service.py",
        "def test_route_decider_reexports_split_signal_collector_contracts():\n    pass\n",
    )

    report = build_signal_collector_split_pregate(repo_root=repo)

    assert report["decision"] == "APPROVED"
    assert report["implementation_allowed"] is True
    assert report["blockers"] == []
    assert report["summary"]["deletion_test_present"] is True
    assert report["summary"]["facade_reexport_present"] is True


def test_signal_collector_split_pregate_main_writes_report(tmp_path, capsys):
    repo = tmp_path / "repo"
    _write(repo / "nexus/research/flow/route_decider.py", "def collect_route_signals():\n    return {}\n")
    output = tmp_path / "signal.json"

    assert main(["--repo-root", str(repo), "--output", str(output)]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "nexus.signal_collector_split_pregate.v1"
    assert payload["decision"] == "DEFERRED"
    assert '"decision": "DEFERRED"' in capsys.readouterr().out
