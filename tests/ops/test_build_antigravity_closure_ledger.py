from __future__ import annotations

import json

from scripts.ops.build_antigravity_closure_ledger import (
    DEFAULT_OUTPUT,
    SOURCE_FILES,
    build_ledger,
    main,
    write_ledger,
)


def _write(path, text="ok"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _source_root(tmp_path):
    source = tmp_path / "brain"
    source.mkdir()
    for name in SOURCE_FILES:
        _write(source / name)
    return source


def test_build_ledger_records_claim_boundary_and_source_files(tmp_path):
    source = _source_root(tmp_path)
    repo = tmp_path / "repo"
    _write(repo / "nexus/learning/outcome_memory.py", "class OutcomeMemoryManager: pass\nEpisodeOutcomeRecord = object\n")
    _write(
        repo / "nexus/app/research_flow_service.py",
        "from nexus.learning.outcome_memory import OutcomeMemoryManager\nsave_episode_and_tune_sync\n",
    )
    _write(repo / "tests/engine/test_rlm_outcome_integration.py", "OutcomeMemoryManager\n")

    ledger = build_ledger(repo_root=repo, source_root=source)

    assert ledger["status"] == "PASS"
    assert ledger["claim_class"] == "PLAN_ONLY"
    assert ledger["runtime_update_allowed"] is False
    assert ledger["swarm_direct_implementation_allowed"] is False
    assert ledger["summary"]["source_files_missing"] == []
    assert ledger["summary"]["status_counts"]["FORBIDDEN_DIRECT"] == 1
    assert ledger["summary"]["status_counts"]["DONE_CONTRACT_READY"] == 3


def test_outcome_memory_row_matches_when_required_files_exist(tmp_path):
    source = _source_root(tmp_path)
    repo = tmp_path / "repo"
    _write(repo / "nexus/learning/outcome_memory.py", "OutcomeMemoryManager\nEpisodeOutcomeRecord\n")
    _write(repo / "nexus/app/research_flow_service.py", "OutcomeMemoryManager\nsave_episode_and_tune_sync\n")
    _write(repo / "tests/engine/test_rlm_outcome_integration.py", "OutcomeMemoryManager\n")

    ledger = build_ledger(repo_root=repo, source_root=source)
    rows = {row["item_id"]: row for row in ledger["rows"]}

    row = rows["routing_v2_outcome_memory_writeback"]
    assert row["status"] == "DONE"
    assert row["all_evidence_matched"] is True


def test_missing_source_files_are_reported_without_failing_builder(tmp_path):
    ledger = build_ledger(repo_root=tmp_path / "repo", source_root=tmp_path / "missing")

    assert ledger["status"] == "PASS"
    assert len(ledger["summary"]["source_files_missing"]) == len(SOURCE_FILES)


def test_write_ledger_dry_run_does_not_write_output(tmp_path):
    source = _source_root(tmp_path)
    output = tmp_path / "docs/reports/ledger.json"

    summary = write_ledger(repo_root=tmp_path / "repo", source_root=source, output=output, dry_run=True)

    assert summary["status"] == "PASS"
    assert summary["dry_run"] is True
    assert output.exists() is False


def test_write_ledger_outputs_json(tmp_path):
    source = _source_root(tmp_path)
    output = tmp_path / "docs/reports/ledger.json"

    summary = write_ledger(repo_root=tmp_path / "repo", source_root=source, output=output)

    assert summary["status"] == "PASS"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "nexus.antigravity_closure_ledger.v1"
    assert payload["summary"]["row_count"] == summary["row_count"]


def test_main_default_output_remains_under_docs_reports(tmp_path, monkeypatch, capsys):
    source = _source_root(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(["--source-root", str(source), "--dry-run"]) == 0

    output = capsys.readouterr().out
    assert f'"output": "{DEFAULT_OUTPUT.as_posix()}"' in output
