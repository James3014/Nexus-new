"""Opt-in cross-repo contract: Core-bound repair continuation against a real runtime.

Not collected by default (``pytest.ini`` collects only ``test_*.py``) because CI has
no runtime.  It drives the real Nexus fanout, closure delta and Open SWE transport
against the real ``nexus_open_swe_runtime`` worker/admission/reconcile code; only
the model and the DeepAgents graphs are replaced by deterministic fakes inside the
runtime process.  Run explicitly with a runtime that supports bound continuation:

    NEXUS_OPEN_SWE_RUNTIME_PYTHON=<runtime venv>/bin/python \\
        python -m pytest -q tests/services/contract_bound_continuation_open_swe_runtime.py
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from nexus.services.external_intelligence_closure import (
    _validate_repair_result,
    validate_worker_receipt,
)
from nexus.services.external_intelligence_fanout import (
    AdaptiveWorkerFanoutRuntime,
    CapacityLease,
    FanoutError,
    FanoutStore,
    GitWorktreeAllocator,
)
from tests.services.test_external_intelligence_bound_continuation import write_repair_delta
from tests.services.test_external_intelligence_core_binding import (
    TARGET,
    bound_unit_mapping,
    make_bound_repo,
)

RUNTIME_PYTHON = Path(
    os.environ.get(
        "NEXUS_OPEN_SWE_RUNTIME_PYTHON",
        str(Path.home() / ".local/share/nexus-open-swe-runtime/venv/bin/python"),
    )
)

# Runs inside the runtime's interpreter: the real cli worker path with fake model/graphs.
_RUNTIME_SCRIPT = r"""
import json, sys
from pathlib import Path
from types import SimpleNamespace
import nexus_open_swe_runtime.cli as cli

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
content = {
    "worker_run": "def test_bound():\n    assert True\n",
    "worker_continue": "def test_bound():\n    assert 1 == 1\n",
}.get(payload.get("operation"), "")


class Graph:
    def __init__(self, surface, output, effect=None):
        self.surface, self.output, self.effect = tuple(surface), output, effect

    def get_graph(self):
        tools = {name: object() for name in self.surface}
        return SimpleNamespace(
            nodes={"tools": SimpleNamespace(data=SimpleNamespace(tools_by_name=tools))}
        )

    def invoke(self, _payload, config=None):
        if self.effect is not None:
            self.effect()
        return self.output


def record(name, envelope):
    return {"messages": [SimpleNamespace(tool_calls=[{"name": name, "args": {"envelope": envelope}}])]}


def model_factory(*_args):
    return SimpleNamespace(_conversation_id=None)


def diagnosis_factory(_model, _workspace, _runtime, _key):
    return Graph(cli.DIAGNOSIS_TOOLS, record("record_diagnosis", {
        "status": "ROOT_CAUSE_SUPPORTED",
        "summary": "the failing unit verifier points at the bound target",
        "evidence_paths": [sys.argv[2]],
    }))


def repair_factory(_model, workspace, _runtime, allowed_paths, _key, checkpointer=None, effect_journal=None):
    target = Path(workspace) / allowed_paths[0]

    def effect():
        old = target.read_text(encoding="utf-8") if target.exists() else None
        written = effect_journal.intent(
            turn_id="turn-" + payload["operation"],
            tool_call_id="call-" + payload["operation"],
            tool_name="write_file",
            arguments={"file_path": allowed_paths[0], "content": content},
            path=target,
            preimage=old,
            postimage=content,
        )
        effect_journal.recover_write(written)

    return Graph(cli.REPAIR_TOOLS, record("record_worker_result", {"summary": "bounded repair"}), effect)


if payload.get("operation") in {"worker_run", "worker_continue"}:
    assert payload.get("schema") == cli.REQUEST_SCHEMA
    result = cli._worker_run(
        payload,
        runtime_loader=lambda: {"human_message": lambda content: content},
        model_factory=model_factory,
        diagnosis_factory=diagnosis_factory,
        repair_factory=repair_factory,
    )
else:
    result = cli.dispatch(payload)
print(json.dumps(result))
"""


def _runtime_available() -> bool:
    if not RUNTIME_PYTHON.is_file():
        return False
    probe = subprocess.run(
        [
            str(RUNTIME_PYTHON),
            "-I",
            "-c",
            "import nexus_open_swe_runtime.cli as c; c._bound_continuation_admission",
        ],
        capture_output=True,
        timeout=60,
        check=False,
    )
    return probe.returncode == 0


def _runtime_identity_sha256() -> str:
    probe = subprocess.run(
        [str(RUNTIME_PYTHON), "-I", "-m", "nexus_open_swe_runtime.cli", "--identity"],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return json.loads(probe.stdout)["artifact_identity"]["module_sha256"]


def test_bound_repair_continuation_round_trips_through_real_runtime(tmp_path, monkeypatch):
    assert _runtime_available(), f"runtime with bound continuation not usable at {RUNTIME_PYTHON}"
    import nexus.services.open_swe_external_intelligence as module

    scratch = tmp_path / "runtime-calls"
    scratch.mkdir()
    raw_results: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def runtime_call(_executable, payload, **_kwargs):
        path = scratch / f"payload-{len(list(scratch.iterdir()))}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        completed = subprocess.run(
            [str(RUNTIME_PYTHON), "-I", "-c", _RUNTIME_SCRIPT, str(path), TARGET],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        value = json.loads(completed.stdout.strip().splitlines()[-1])
        raw_results.append((json.loads(json.dumps(payload)), value))
        return value, completed.stderr, payload["operation"] != "identity", ""

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    scenario = make_bound_repo(tmp_path)
    unit = bound_unit_mapping(tmp_path, scenario)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256=_runtime_identity_sha256(),
        runtime_state_root=tmp_path / "runtime-state",
        require_worker_binding=True,
    )
    runtime = AdaptiveWorkerFanoutRuntime(
        allocator=GitWorktreeAllocator(scenario.repo, tmp_path / "workspaces"),
        store=FanoutStore(tmp_path / "state"),
        transport=transport,
    )

    # 1. Initial bound dispatch: the real runtime admits the Nexus-minted binding.
    first = runtime.run([unit], CapacityLease(1, 1, 1, 1))
    assert first["errors"] == {}
    parent = first["receipts"]["u1"]
    assert parent["core_binding_status"] == "BOUND"
    parent_bound = validate_worker_receipt(parent)

    # 2. Unit verification failed: continue with the production repair delta.
    repair_ref, repair_sha = write_repair_delta(parent, tmp_path / "closure" / "repair-deltas")
    repaired = runtime.continue_repair(
        parent, repair_id="d001", repair_ref=repair_ref, repair_sha256=repair_sha
    )
    payload, value = raw_results[-1]
    assert payload["operation"] == "worker_continue"
    assert value["status"] == "COMPLETED", value
    assert value["core_binding_status"] == "BOUND"
    assert value["core_change_set_projection"]["status"] == "PHYSICAL_CHANGESET_BOUND"
    assert value["core_change_set_projection"]["change_set"]["paths"] == [TARGET]
    assert repaired["status"] == "CANDIDATE_READY_FOR_VERIFICATION"
    assert repaired["core_binding_status"] == "BOUND"
    assert repaired["core_binding_hash"] == parent["core_binding_hash"]
    assert repaired["acceptance_contract_hash"] == parent["acceptance_contract_hash"]
    assert repaired["core_binding_operation_id"] == parent["operation_id"]
    _validate_repair_result(parent_bound, repaired)
    workspace = Path(parent["workspace_path"])
    assert "assert 1 == 1" in (workspace / TARGET).read_text(encoding="utf-8")

    # 3. Reconcile of the continuation carries the hashes; without them it is unknown.
    core = {
        "core_binding_hash": parent["core_binding_hash"],
        "acceptance_contract_hash": parent["acceptance_contract_hash"],
    }
    reconciled = transport.reconcile_workspace(
        workspace_path=str(workspace), operation_id=repaired["operation_id"], core_binding=core
    )
    assert reconciled.status == "COMPLETED"
    assert reconciled.core_binding_status == "BOUND"
    assert raw_results[-1][0]["core_binding_hash"] == core["core_binding_hash"]
    unbound_reconcile = transport.reconcile_workspace(
        workspace_path=str(workspace), operation_id=repaired["operation_id"]
    )
    assert unbound_reconcile.status == "OPEN_SWE_OUTCOME_UNKNOWN"

    # 4. A continuation that omits the binding is rejected by the runtime itself.
    second_ref, second_sha = write_repair_delta(repaired, tmp_path / "closure" / "second")
    try:
        runtime.transport = _UnboundContinuation(transport)
        runtime.continue_repair(
            repaired, repair_id="d002", repair_ref=second_ref, repair_sha256=second_sha
        )
    except FanoutError as exc:
        assert str(exc) == "FANOUT_RECONCILIATION_REQUIRED"
    else:  # pragma: no cover - the runtime must not admit it
        raise AssertionError("unbound continuation of a BOUND session was admitted")
    payload, value = raw_results[-1]
    assert payload["operation"] == "worker_continue"
    assert "core_binding_hash" not in payload
    assert value["error_code"] == "OPEN_SWE_BOUND_CONTINUATION_REJECTED_CORE_BINDING_ABSENT"
    assert value["core_binding_status"] == "LEGACY_UNBOUND"


class _UnboundContinuation:
    """Wraps the real transport but drops the Core hashes from a continuation."""

    supports_core_mutation_binding = True

    def __init__(self, inner: Any):
        self.inner = inner
        self.provider_id = inner.provider_id
        self.model_id = inner.model_id
        self.model = inner.model

    def bind_worker(self, worker):
        self.inner.bind_worker(worker)
        return self

    def prepare_operation_id(self, *args, **kwargs):
        return self.inner.prepare_operation_id(*args, **kwargs)

    def continue_session(self, **kwargs):
        kwargs.pop("core_binding", None)
        return self.inner.continue_session(**kwargs)
