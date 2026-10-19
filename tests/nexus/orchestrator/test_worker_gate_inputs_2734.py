"""#2734: the four pre-execution gates on the Gateway worker path (P1).

Each gate either executes with output or is recorded NOT_APPLICABLE naming the missing
input; never the opaque INVOKED_NOT_SUCCESS.  They are receipt-only and never change the
worker's context package, prompt content or completion.
"""

from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from types import SimpleNamespace

import pytest

from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.self_hosted_task_service_parts import worker_gate_inputs as wgi

GATES = wgi.WORKER_PATH_GATES
ALLOWED = ["pkg/mod_a.py", "pkg/mod_b.py"]
VERIFY = ["git diff --check"]


def _git_repo(path):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    for rel in ALLOWED:
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text('"""doc"""\nX = 1\n', encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "b"],
        check=True,
    )


def _status(path):
    return subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain", "--ignored"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _p1(tmp_path, *, allowed=ALLOWED, verify=VERIFY, pending=()):
    """Live P1 shape (i2688-w3c receipt): planner context + plan_payload, Task Card fields."""
    task_id = "p1-gates-2734"
    attempt_id = "attempt-1"
    envelope = {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "workspace_revision": "t" * 40,
        "planner_decision_hash": "d" * 64,
        "planner_plan_hash": "p" * 64,
        "worker_id": "worker-1",
        "provider": "agy",
        "model": "gemini-3.8-flash-medium",
    }
    selected = list(GATES)
    request = {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "workspace_revision": "t" * 40,
        "what": "Add one comment line near the top of each allowed file.",
        "allowed_files": list(allowed),
        "verifier_commands": list(verify),
        "planner_output": {
            "decision_hash": "d" * 64,
            "plan_hash": "p" * 64,
            "selected_capabilities": selected,
            "plan_payload": {
                "selected_capabilities": selected,
                "pending_capabilities": list(pending),
            },
            "context": {
                "task_type": "feature",
                "route_features": {"bounded_allowed_file_count": len(allowed)},
                "codeintel": {
                    "allowed_files": list(allowed),
                    "verify_commands": list(verify),
                    "risk_score": 100,
                },
            },
        },
        "canonical_dispatch_envelope": envelope,
        "provider": "agy",
        "model": "gemini-3.8-flash-medium",
        "action_request_hash": "a" * 64,
    }
    state = {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "status": "SUBMITTED",
        "request": deepcopy(request),
        "action": {"signed": True},
        "action_request_hash": request["action_request_hash"],
        "controller_revision": "c" * 40,
        "canonical_dispatch_envelope": envelope,
    }
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    service._write_state(task_id, state)
    target = tmp_path / "leased-target"
    _git_repo(target)
    contract = SimpleNamespace(
        controller_revision="c" * 40,
        target_base_revision="t" * 40,
        task_id=task_id,
        allowed_files=tuple(allowed),
        verifier_commands=tuple(verify),
    )
    lease = SimpleNamespace(target_worktree=str(target), initial_head="t" * 40)
    return service, request, state, contract, lease


def _materialize(service, request, state, contract, lease):
    prompt, package = service._worker_context_materialization(
        request=request,
        state=state,
        task_id=state["task_id"],
        attempt_id=state["attempt_id"],
        fresh_submission=True,
        contract=contract,
        lease=lease,
        base_prompt="BASE",
        actual_provider="agy",
        actual_model="gemini-3.8-flash-medium",
    )
    record = service._read_state(state["task_id"])["worker_model_context_materialization"]
    entries = {e["name"]: e for e in record["bundle"]["entries"] if e["name"] in GATES}
    return prompt, package, record, entries


def test_p1_gates_execute_or_not_applicable_never_opaque(tmp_path, monkeypatch):
    state_root = tmp_path / "state-root"
    state_root.mkdir()
    monkeypatch.setenv("NEXUS_STATE_ROOT", str(state_root))
    service, request, state, contract, lease = _p1(tmp_path)
    before = _status(lease.target_worktree)
    prompt, package, record, entries = _materialize(service, request, state, contract, lease)

    assert set(entries) == set(GATES)
    for name, entry in entries.items():
        assert entry["status"] != "INVOKED_NOT_SUCCESS", (name, entry)
        assert entry.get("consumer_visibility") == "receipt_only", name
    for name in ("plan_quality_gate", "mempalace_gate", "harness_preflight_sensor"):
        assert entries[name]["status"] == "REAL_INVOKED", name
    assert entries["pregate"]["status"] == "SKIPPED"
    assert entries["pregate"]["skip_reason"] == (
        "NOT_APPLICABLE:" + wgi.PREGATE_NOT_APPLICABLE_REASON
    )
    obs = record["capability_observations"]
    assert obs["plan_quality_gate"]["semantic_status"] == "SUCCEEDED"
    assert obs["harness_preflight_sensor"]["semantic_status"] == "SUCCEEDED"
    assert obs["mempalace_gate"]["semantic_status"] == "SUCCEEDED"
    assert obs["pregate"]["semantic_status"] == "NOT_APPLICABLE"
    # MemPalace writes under NEXUS_STATE_ROOT, never into the task worktree.
    assert (state_root / ".nexus" / "tenants" / wgi.MEMPALACE_TENANT).is_dir()
    assert _status(lease.target_worktree) == before == ""
    # Record-only: no gate output reaches the worker prompt; the package still passes.
    assert package["status"] == "PASS"
    assert "worker-contract-" not in prompt
    assert not set(GATES) & set(package.get("serialized_capability_ids") or [])


def test_p1_gates_missing_inputs_are_not_applicable_naming_them(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_STATE_ROOT", raising=False)
    service, request, state, contract, lease = _p1(tmp_path, allowed=[], verify=[])
    _prompt, package, record, entries = _materialize(service, request, state, contract, lease)

    for name, entry in entries.items():
        assert entry["status"] == "SKIPPED", (name, entry)
        assert entry["skip_reason"].startswith("NOT_APPLICABLE:"), name
    assert entries["harness_preflight_sensor"]["skip_reason"].endswith("missing=verify_commands")
    obs = record["capability_observations"]
    pq = obs["plan_quality_gate"]["skip_reason"].split(":missing=")[1].split(",")
    assert {"target_files", "acceptance_criteria", "impact_map"} <= set(pq)
    assert obs["plan_quality_gate"]["semantic_status"] == "NOT_APPLICABLE"
    assert (
        obs["mempalace_gate"]["skip_reason"].split(":missing=")[1].startswith("NEXUS_STATE_ROOT,")
    )
    assert _status(lease.target_worktree) == ""
    assert package["status"] == "PASS"


def test_p1_mempalace_without_state_root_never_writes_task_worktree(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_STATE_ROOT", raising=False)
    service, request, state, contract, lease = _p1(tmp_path)
    _prompt, _package, record, entries = _materialize(service, request, state, contract, lease)

    assert entries["mempalace_gate"]["status"] == "SKIPPED"
    assert record["capability_observations"]["mempalace_gate"]["skip_reason"] == (
        "NOT_APPLICABLE:MEMPALACE_ARTIFACT_CONTEXT_REQUIRED:missing=NEXUS_STATE_ROOT"
    )
    assert _status(lease.target_worktree) == ""


def test_p1_evaluated_gate_failure_is_rejected_with_blockers_and_never_blocks(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("NEXUS_STATE_ROOT", str(tmp_path / "sr"))
    service, request, state, contract, lease = _p1(tmp_path, pending=["swarm"])
    prompt, package, record, entries = _materialize(service, request, state, contract, lease)

    harness = entries["harness_preflight_sensor"]
    assert harness["status"] == "EVALUATED_REJECTED", harness
    assert harness.get("failure_disposition") == "evaluated_rejected"
    assert record["capability_observations"]["harness_preflight_sensor"]["semantic_status"] == (
        "BLOCKED"
    )
    assert package["status"] == "PASS"
    assert prompt.startswith("BASE")


def test_pregate_is_never_run_before_the_edit_on_the_worker_path():
    def explode(_context):
        raise AssertionError("pregate executor must not run on the worker path")

    wrapped = wgi.wrap_worker_gate_invokers({"pregate": explode}, {})
    assert "pregate" not in wgi.wrap_worker_gate_invokers({}, {})
    record = wrapped["pregate"]({"task_id": "t1", "verify_commands": ["true"]})
    assert record["skipped"] is True and record["invoked"] is False
    assert record["applicability"] == "NOT_APPLICABLE"


@pytest.mark.parametrize(
    ("name", "error", "missing"),
    [
        ("pregate", "EXPLICIT_VERIFY_COMMANDS_REQUIRED", ["verify_commands"]),
        ("harness_preflight_sensor", "VERIFY_COMMAND_WIRING_REQUIRED", ["verify_commands"]),
        ("plan_quality_gate", "PLAN_QUALITY_CONTEXT_REQUIRED", ["steps"]),
    ],
)
def test_honest_gate_record_turns_refusals_into_not_applicable(name, error, missing):
    record = {
        "invoked": True,
        "status": "FAILED",
        "response": {"outcome": {"semantic_status": "BLOCKED", "error": error}},
    }
    if name == "plan_quality_gate":
        record["response"]["outcome"]["missing_inputs"] = ["steps"]
    out = wgi.honest_gate_record(name, record, "t1")
    assert out["skipped"] is True
    assert out["missing_inputs"] == missing
    assert out["skip_reason"] == f"NOT_APPLICABLE:{error}:missing=" + ",".join(missing)
    assert json.loads(json.dumps(out)) == out


def test_honest_gate_record_keeps_success_and_unknown_errors_unchanged():
    ok = {"invoked": True, "status": "SUCCEEDED", "response": {"outcome": {}}}
    assert wgi.honest_gate_record("plan_quality_gate", ok, "t1") == ok
    crashed = {
        "invoked": False,
        "status": "BLOCKED",
        "response": {"outcome": {"error": "boom"}},
    }
    assert wgi.honest_gate_record("mempalace_gate", crashed, "t1") == crashed
