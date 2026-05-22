from __future__ import annotations

import json

from scripts.ops.build_antigravity_p9_narrow_integration_call_sites import (
    DEFAULT_OUTPUT,
    build_report,
    main,
    write_report,
)


def _write(path, text="ok"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repo_with_candidates(tmp_path):
    repo = tmp_path / "repo"
    _write(
        repo / "scripts/bench/gemini_nexus_report.py",
        "def _load_evidence_bundle(path):\n    evidence_bundle = path\n",
    )
    _write(
        repo / "nexus/core/memory_manager.py",
        "def _execute_with_retry():\n    _is_retryable_sqlite_lock()\n",
    )
    _write(
        repo / "nexus/services/codeintel/skeleton_context_adapter.py",
        "def build_code_skeleton_context():\n    lookup_implementation()\n",
    )
    _write(
        repo / "tests/contracts/test_antigravity_local_simulation_contracts.py",
        "\n".join(
            [
                "LocalEventPipeline",
                "build_local_gateway_receipt",
                "provider_call",
                "build_local_memory_hub_snapshot",
                "mutable_global_singleton",
                "unsealed_evidence_event_blocked",
            ]
        ),
    )
    return repo


def test_build_report_selects_narrow_call_sites_without_runtime_or_public_unlock(tmp_path):
    report = build_report(_repo_with_candidates(tmp_path))

    assert report["status"] == "PASS"
    assert report["claim_class"] == "PLAN_ONLY"
    assert report["runtime_default_change_allowed"] is False
    assert report["public_benchmark_allowed"] is False
    assert report["summary"]["selected_count"] == 6
    assert report["summary"]["missing_probe_count"] == 0
    assert report["forbidden_paths_touched"] == []

    rows = {row["adapter"]: row for row in report["selected_call_sites"]}
    assert rows["evidence_sealing_barrier"]["file"] == "scripts/bench/gemini_nexus_report.py"
    assert rows["evidence_sealing_barrier"]["call_site"] == "_load_evidence_bundle"
    assert rows["sqlite_retry_handler"]["file"] == "nexus/core/memory_manager.py"
    assert rows["fault_tolerant_ast_snapshot"]["call_site"] == "build_code_skeleton_context"

    for row in report["selected_call_sites"]:
        assert row["file"]
        assert row["call_site"]
        assert row["focused_test"]
        assert row["rollback_plan"]
        assert row["runtime_default_change_allowed"] is False
        assert row["public_benchmark_allowed"] is False


def test_build_report_marks_missing_probes_without_claiming_ready(tmp_path):
    report = build_report(tmp_path / "repo")

    assert report["status"] == "RETURN"
    assert report["summary"]["missing_probe_count"] == report["summary"]["selected_count"]
    assert {item["adapter"] for item in report["missing_probes"]} == {
        item["adapter"] for item in report["selected_call_sites"]
    }


def test_write_report_outputs_json(tmp_path):
    output = tmp_path / "docs/reports/p9.json"
    summary = write_report(repo_root=_repo_with_candidates(tmp_path), output=output)

    assert summary["status"] == "PASS"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "nexus.antigravity_p9_narrow_integration_call_sites.v1"
    assert payload["summary"]["selected_count"] == summary["selected_count"]


def test_main_default_output_remains_under_docs_reports(tmp_path, monkeypatch, capsys):
    repo = _repo_with_candidates(tmp_path)
    monkeypatch.chdir(repo)

    assert main(["--dry-run"]) == 0

    output = capsys.readouterr().out
    assert f'"output": "{DEFAULT_OUTPUT.as_posix()}"' in output
