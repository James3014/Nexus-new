from __future__ import annotations

import json
from pathlib import Path

from nexus.services.local_assist_closeout import (
    LocalAssistAgentCloseout,
    run_local_assist_closeout,
)


def _receipt(
    path: Path,
    *,
    task_id: str,
    action: str = "advisor",
    candidate_count: int = 0,
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "nexus.local_assist.execution_receipt.v1",
                "task_id": task_id,
                "action": action,
                "provider": "ollama",
                "resolved_model": "qwen2.5-s2t-advisor:3b",
                "provider_call_count": 1,
                "candidate_count": candidate_count,
                "receipt_complete": True,
                "claim_boundary": {
                    "runtime_invoked": True,
                    "output_delivered": True,
                },
            }
        ),
        encoding="utf-8",
    )


def _payload(repo: Path, advisor: Path, verified: Path) -> dict[str, object]:
    return {
        "schema": "nexus.local_assist.agent_closeout.v1",
        "task_id": "gemini-m2-001",
        "agent_provider": "gemini",
        "local_assist_requested": True,
        "local_assist_selected": ["advisor", "verified-subtask"],
        "local_assist_invoked": True,
        "local_assist_receipt_paths": [str(advisor), str(verified)],
        "local_assist_output_delivered": True,
        "local_assist_output_consumed": True,
        "local_candidate_selected": True,
        "local_assist_contribution_claim": "consumed_for_candidate_selection",
        "output_consumption_evidence": [
            f"Advisor receipt {advisor}: selected the report target.",
            f"Verified receipt {verified}: confirmed the isolated subtask result.",
        ],
        "final_output": (
            f"Used advisor task gemini-m2-advisor and verified task gemini-m2-verified; "
            f"receipts: {advisor}, {verified}."
        ),
    }


def test_valid_closeout_requires_and_records_consumption_evidence(tmp_path: Path) -> None:
    advisor = tmp_path / "advisor.json"
    verified = tmp_path / "verified.json"
    _receipt(advisor, task_id="gemini-m2-advisor")
    _receipt(verified, task_id="gemini-m2-verified", action="verified-subtask", candidate_count=1)

    result = LocalAssistAgentCloseout.from_dict(_payload(tmp_path, advisor, verified)).validate(tmp_path)

    assert result.ok is True
    assert result.blockers == ()
    assert result.claim_boundary["output_consumed"] is True


def test_receipt_presence_alone_does_not_prove_output_consumed(tmp_path: Path) -> None:
    advisor = tmp_path / "advisor.json"
    verified = tmp_path / "verified.json"
    _receipt(advisor, task_id="gemini-m2-advisor")
    _receipt(verified, task_id="gemini-m2-verified", action="verified-subtask", candidate_count=1)
    payload = _payload(tmp_path, advisor, verified)
    payload["output_consumption_evidence"] = []
    payload["final_output"] = "Task completed."

    result = LocalAssistAgentCloseout.from_dict(payload).validate(tmp_path)

    assert result.ok is False
    assert "output_consumed_requires_evidence" in result.blockers


def test_incomplete_receipt_blocks_agent_closeout(tmp_path: Path) -> None:
    advisor = tmp_path / "advisor.json"
    verified = tmp_path / "verified.json"
    _receipt(advisor, task_id="gemini-m2-advisor")
    verified.write_text(
        json.dumps(
            {
                "task_id": "gemini-m2-verified",
                "provider": "ollama",
                "provider_call_count": 0,
                "receipt_complete": False,
            }
        ),
        encoding="utf-8",
    )

    result = LocalAssistAgentCloseout.from_dict(_payload(tmp_path, advisor, verified)).validate(tmp_path)

    assert result.ok is False
    assert "receipt_incomplete:verified.json" in result.blockers


def test_cli_closeout_writes_machine_report(tmp_path: Path) -> None:
    advisor = tmp_path / "advisor.json"
    verified = tmp_path / "verified.json"
    _receipt(advisor, task_id="gemini-m2-advisor")
    _receipt(verified, task_id="gemini-m2-verified", action="verified-subtask", candidate_count=1)
    closeout_file = tmp_path / "closeout.json"
    closeout_file.write_text(json.dumps(_payload(tmp_path, advisor, verified)), encoding="utf-8")

    result = run_local_assist_closeout(
        closeout_file=closeout_file,
        repo_root=tmp_path,
        report_file=tmp_path / "agent_closeout.json",
    )

    assert result.exit_code == 0
    report = json.loads((tmp_path / "agent_closeout.json").read_text(encoding="utf-8"))
    assert report["status"] == "VERIFIED"
    assert report["claim_boundary"]["output_consumed"] is True
