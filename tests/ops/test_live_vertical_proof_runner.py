"""Structural tests for the atomic live vertical proof runner (no live provider)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scripts.ops.run_live_vertical_proof import (
    CANONICAL_VERTICAL_TASK_ID,
    assert_log_contains,
    build_cli_command,
    count_live_pairs,
    resolve_pointer,
    run_vertical_proof,
    safe_task_key,
)


def test_canonical_task_id_is_stable() -> None:
    assert CANONICAL_VERTICAL_TASK_ID.startswith("live-vertical-cli-r2e:")
    assert "Formal workspace mutation forbidden" in CANONICAL_VERTICAL_TASK_ID


def test_build_cli_command_wires_product_entry(tmp_path: Path) -> None:
    cmd = build_cli_command(
        repo_root=tmp_path,
        task_id=CANONICAL_VERTICAL_TASK_ID,
        python_exe="/usr/bin/python3",
        report_file=tmp_path / "report.json",
        output_file=tmp_path / "out.json",
    )
    assert cmd[0] == "/usr/bin/python3"
    assert cmd[1].endswith("scripts/engine/nexus_cli.py")
    assert cmd[2] == "run"
    assert cmd[3] == CANONICAL_VERTICAL_TASK_ID
    assert "--local-assist-policy" in cmd and "advisor" in cmd
    assert "--online-policy" in cmd and "require" in cmd


def test_assert_log_contains_canonical_markers() -> None:
    good = f"{CANONICAL_VERTICAL_TASK_ID}\nprovider=grok\nollama qwen\ngateway_bound=True\n"
    assert assert_log_contains(good, CANONICAL_VERTICAL_TASK_ID) == []
    bad = "Bounded advisory diagnosis without r2e\n"
    fails = assert_log_contains(bad, CANONICAL_VERTICAL_TASK_ID)
    assert "log_missing_canonical_task_id" in fails


def test_count_live_pairs_from_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "paired_results.jsonl"
    rows = [
        {"task_id": f"t{i}", "measurement_quality": "LOCALLY_MEASURED", "arm_a": {}, "arm_b": {}}
        for i in range(5)
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    stats = count_live_pairs(path)
    assert stats["pair_row_count"] == 5
    assert stats["five_live_pairs"] == 5
    assert stats["fixture_rows"] == 0


def test_run_vertical_proof_wires_pointer_and_validator(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    scratch = tmp_path / "scratch"
    camp = repo / ".nexus" / "reports" / "local_assist_live_paired" / "live_paired_20260713T2311Z"
    camp.mkdir(parents=True)
    # five live pair rows
    (camp / "paired_results.jsonl").write_text(
        "\n".join(
            json.dumps({"task_id": f"t{i}", "measurement_quality": "LOCALLY_MEASURED"}) for i in range(5)
        )
        + "\n",
        encoding="utf-8",
    )

    task = CANONICAL_VERTICAL_TASK_ID
    key = safe_task_key(task)
    pointer_dir = repo / ".nexus" / "reports" / "run"
    pointer_dir.mkdir(parents=True)
    ur_dir = repo / ".nexus" / "reports" / "unified_runtime"
    ur_dir.mkdir(parents=True)
    receipt_path = ur_dir / f"{task}.json"
    receipt = {
        "task_id": task,
        "workspace_revision": "rev-test",
        "receipt_complete": True,
        "terminal_status": "SUCCEEDED",
        "local": {
            "invoked": True,
            "gate_passed": True,
            "status": "SUCCEEDED",
            "response": {
                "provider": "ollama",
                "local_model_invoked": True,
                "output_delivered": True,
                "resolved_models": ["qwen2.5-coder:7b-instruct"],
                "provider_call_count": 1,
            },
        },
        "online": {
            "invoked": True,
            "gate_passed": True,
            "status": "SUCCEEDED",
            "response": {
                "provider": "grok",
                "invoked": True,
                "output_delivered": True,
                "provider_call_count": 1,
                "transport": "registered_cli",
                "evidence_refs": [f"online:{task}:local_context_forwarded"],
            },
        },
        "online_preflight": {"status": "ONLINE_READY", "physical_invocation_allowed": True},
        "verifier": {"invoked": True, "gate_passed": True, "status": "SUCCEEDED"},
        "learning": {"invoked": True, "gate_passed": True, "status": "SUCCEEDED"},
        "formal_workspace_mutated": False,
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    pointer = {
        "unified_runtime_task_id": task,
        "unified_runtime_receipt_path": str(receipt_path),
        "local_assist_mode": "advisor",
        "local_assist_success": True,
        "online_success": True,
        "runtime_receipt_complete": True,
        "local_context_forwarded": True,
        "online_provider": "grok",
        "workspace_revision": "rev-test",
    }
    (pointer_dir / f"{key}.unified_runtime_pointer.json").write_text(json.dumps(pointer), encoding="utf-8")

    def fake_run(cmd, **kwargs):
        # Simulate CLI writing report into --report-file path
        report_file = Path(cmd[cmd.index("--report-file") + 1])
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(
            json.dumps(
                {
                    "task_name": task,
                    "unified_runtime_task_id": task,
                    "unified_runtime_receipt_path": str(receipt_path),
                    "local_assist_mode": "advisor",
                    "local_assist_success": True,
                    "online_success": True,
                    "runtime_receipt_complete": True,
                    "local_context_forwarded": True,
                    "online_provider": "grok",
                    "workspace_revision": "rev-test",
                    "formal_workspace_mutated": False,
                }
            ),
            encoding="utf-8",
        )
        stdout = (
            f"Initiating Master Loop for: {task}\n"
            f"gateway_bound=True use_surgical=True provider=grok\n"
            f"ollama model qwen2.5-coder:7b-instruct\n"
            f"Report: {report_file}\n"
        )
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    # Ensure import path sees scripts package
    import sys

    sys.path.insert(0, str(repo.parent if False else Path.cwd()))

    result = run_vertical_proof(
        repo_root=repo,
        scratch=scratch,
        task_id=task,
        runner=fake_run,
        campaign_dir=camp,
        selected_provider="grok",
    )
    assert result["cmd"][2] == "run"
    assert result["cmd"][3] == task
    assert Path(result["log_path"]).is_file()
    log = Path(result["log_path"]).read_text(encoding="utf-8")
    assert "live-vertical-cli-r2e" in log
    assert "grok" in log
    assert "ollama" in log
    assert result["validation"]["status"] == "LIVE_PROOF_PASS"
    assert result["summary"]["product_entry"] == "nexus run"
    assert result["summary"]["runtime_seam"] == "cli->command_service->engine"
    assert result["summary"]["task_id"] == task
    assert result["summary"]["REAL_LOCAL_ONLINE_VERTICAL_PROVEN"] is True
    assert result["closeout"]["five_live_pairs"] == 5
    assert result["closeout"]["pair_row_count"] == 5
    assert result["claim_boundary"]["NEXUS_LIVE_ONLINE_AND_PAIRED_PILOT_COMPLETE"] is True
    assert (scratch / "vertical_proof_summary.json").is_file()
    assert (camp / "campaign_closeout.json").is_file()
    closeout = json.loads((camp / "campaign_closeout.json").read_text(encoding="utf-8"))
    assert closeout["five_live_pairs"] == 5


def test_resolve_pointer_uses_safe_key(tmp_path: Path) -> None:
    p = resolve_pointer(tmp_path, CANONICAL_VERTICAL_TASK_ID)
    assert p.name.endswith(".unified_runtime_pointer.json")
    assert "live-vertical-cli-r2e" in p.name
