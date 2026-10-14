"""Issue #49: no World A task surface delivers ungated final-answer text.

Re-localized after #29 (see #49): the canonical runtime keeps the model's
natural-language answer only inside the runtime receipt
(``receipt["online"]["response"]``). Neither MCP ``nexus_task_run``, ``nexus
run`` (stdout and report) nor the root receipt forwards that text; they only
return a pointer to the receipt file. So there is no final-answer/claim text to
gate. These tests lock that in: adding a text delivery path makes them fail,
and that path must then consume the existing claim/delivery verdict before
returning text (reopen #49).

Known exception, out of scope: ``nexus content:rewrite --llm-mode`` writes the
model's rewritten document (``online.response.patch``) to the user's output
file. That is a requested artifact, not a completion/verification claim.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from nexus.contracts.root_receipt import build_root_receipt
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway

SENTINEL = "UNGATED-FINAL-TEXT-7f3c: all tests verified and the task is complete"


class _RuntimeResult(SimpleNamespace):
    def __bool__(self) -> bool:
        return bool(self.ok)


def _runtime_receipt(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "workspace_revision": "test-revision",
        "terminal_status": "SUCCEEDED",
        "receipt_complete": True,
        "canonical_execution": {
            "execution_decision_authority": "CapabilityPlanner",
            "execution_world": "development_task",
            "canonical_execution_topology": "ASSISTED_CANONICAL",
        },
        "local": {"status": "NOT_REQUESTED", "gate_passed": False},
        "online": {
            "status": "SUCCEEDED",
            "gate_passed": True,
            "response": {
                "provider": "fixture",
                "response": SENTINEL,
                "raw_response": SENTINEL,
                "message": SENTINEL,
                "output": SENTINEL,
                "patch": SENTINEL,
            },
        },
        "claim_boundary": {"public_claim_allowed": False},
    }


def _runtime_result(task_id: str) -> _RuntimeResult:
    return _RuntimeResult(
        ok=True,
        receipt=_runtime_receipt(task_id),
        receipt_path="/tmp/canonical-runtime.json",
        root_receipt={"root_receipt_hash": "sha256:" + "a" * 64},
        root_receipt_valid=True,
        root_receipt_blockers=(),
        execution_decision_authority="CapabilityPlanner",
        production_ingress_count=1,
        production_runtime_entry_count=1,
    )


def test_root_receipt_does_not_carry_online_model_text() -> None:
    root = build_root_receipt(_runtime_receipt("issue49-root"))
    assert SENTINEL not in json.dumps(root, default=str)


def test_mcp_task_run_does_not_return_online_model_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _execute(task_text: str, project_root: Any, execution_context: Any = None) -> Any:
        return _runtime_result(str((execution_context or {}).get("task_id") or "mcp"))

    monkeypatch.setattr(
        "nexus.orchestrator.unified_mcp_gateway.execute_canonical_product_task", _execute
    )
    response = UnifiedMCPGateway(service=SimpleNamespace()).handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "nexus_task_run",
            "arguments": {
                "task_id": "issue49-mcp",
                "what": "Inspect one bounded file",
                "why": "Lock in no ungated final text",
                "allowed_files": ["README.md"],
            },
        },
    })
    assert response is not None
    assert response["result"]["isError"] is False
    assert SENTINEL not in json.dumps(response, default=str)


def test_nexus_run_does_not_print_or_report_online_model_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        cli_mod,
        "execute_canonical_product_task",
        lambda *_args, **_kwargs: _runtime_result("issue49-cli"),
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    report = tmp_path / "report.json"
    result = CliRunner().invoke(
        cli_mod.nexus, ["nexus", "run", "issue49-cli", "--report-file", str(report)]
    )
    assert SENTINEL not in result.output
    assert report.exists(), result.output
    written = [path for path in tmp_path.rglob("*.json") if path.is_file()]
    assert written, result.output
    for path in written:
        assert SENTINEL not in path.read_text(encoding="utf-8"), path
