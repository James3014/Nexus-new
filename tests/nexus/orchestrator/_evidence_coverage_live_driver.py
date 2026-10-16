"""Subprocess driver for the #2181 Evidence Coverage live-path witnesses.

It must run in a fresh interpreter whose ``NEXUS_CORE_REPO_ROOT`` points at a
clean nexus-core checkout, because the in-tree ``product`` package would
otherwise shadow Core. The chain it drives is the live one:

    hashed task card -> Gateway ``nexus_worker_candidate`` -> exact submitted
    request -> real ``SelfHostedTaskService`` runtime -> worker candidate ->
    ``CandidateVerifier`` -> ``LazyCanonicalCoreControlPort`` -> real Core ->
    durable receipt -> reload from the state dir.

Only the provider process is replaced (it writes one bounded file), exactly as
the managed-agent tests do. Usage: ``python <driver> <spec.json>``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

# Import the transport first so the configured Core checkout owns ``product``.
import nexus.orchestrator.canonical_core_transport as transport  # noqa: E402
import nexus.orchestrator.self_hosted_task_service as service_module  # noqa: E402
import nexus.orchestrator.unified_mcp_gateway as gateway_module  # noqa: E402
from nexus.contracts.lifecycle_action import (  # noqa: E402
    LifecycleActionEnvelope,
    canonical_request_hash,
)
from nexus.executors.worker_contract import (  # noqa: E402
    WorkerExecutionReceipt,
    WorkerOutcome,
    WorkerPreflight,
)
from nexus.orchestrator.ambient_core import (  # noqa: E402
    LazyCanonicalCoreControlPort,
    core_universe_identity,
    live_core_db_path,
)
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService  # noqa: E402
from nexus.orchestrator.task_contract import TASK_CARD_EXPECTED_EVIDENCE_FENCE  # noqa: E402
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway  # noqa: E402

_ORIGINAL_GUARD = gateway_module.pre_action_guard


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _card_text(task_id: str, universe: dict[str, Any] | None) -> str:
    lines = [f"# Task Card: {task_id}", "", f"task_id: `{task_id}`", "AUTO_CHAIN: false", ""]
    if universe is not None:
        lines += [
            "## Expected evidence",
            "",
            "```" + TASK_CARD_EXPECTED_EVIDENCE_FENCE,
            json.dumps(universe, indent=2, sort_keys=True),
            "```",
            "",
        ]
    return "\n".join(lines)


def _controller(root: Path, task_id: str, universe: dict[str, Any] | None) -> tuple[Path, str, str]:
    ctl = root / "ctl"
    ctl.mkdir(parents=True)
    _git(ctl, "init", "-q")
    _git(ctl, "config", "user.name", "Coverage Witness")
    _git(ctl, "config", "user.email", "coverage@example.com")
    (ctl / "README.md").write_text("# Repo\n", encoding="utf-8")
    (ctl / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    card_rel = f"tasks/test/{task_id}.md"
    card = ctl / card_rel
    card.parent.mkdir(parents=True)
    card.write_text(_card_text(task_id, universe), encoding="utf-8")
    _git(ctl, "add", "-A")
    _git(ctl, "commit", "-qm", "seed")
    return ctl, _git(ctl, "rev-parse", "HEAD"), card_rel


class _RecordingService(SelfHostedTaskService):
    def submit_task(self, request):  # type: ignore[override]
        self.submitted = [*getattr(self, "submitted", []), json.loads(json.dumps(request))]
        return {"status": "RECORDED", "task_id": request["task_id"]}


def _ready_preflight(arguments: Any) -> dict[str, Any]:
    return {
        "status": "VERSION_VERIFIED",
        "readiness_status": "MODEL_VERIFIED",
        "execution_ready": True,
        "provider": "agy",
        "requested_model": "gemini-3.8-flash-medium",
        "resolved_model": "gemini-3.8-flash-medium",
        "model_reachable": True,
        "requested_model_verified": True,
        "authenticated": True,
        "authentication_evidence": "successful_exact_model_probe",
        "probe_evidence_hash": "e" * 64,
        "binary_path": "/usr/bin/true",
        "binary_sha256": "b" * 64,
        "cli_version_sha256": "c" * 64,
        "probe_expires_at": "2099-01-01T00:00:00+00:00",
    }


def _remint(request: dict[str, Any], mutate) -> dict[str, Any]:
    """Re-mint a self-consistent action around a mutated bound request.

    This is the strongest forgery available to a caller that can rebuild the
    action envelope: every hash in the request agrees with itself.
    """
    bound = json.loads(json.dumps(request["bound_action_request"]))
    mutate(bound)
    action = dict(request["action"])
    action["request_hash"] = canonical_request_hash(bound)
    action = LifecycleActionEnvelope.model_validate(action).model_dump(mode="json")
    forged = dict(request)
    for field in ("expected_evidence", "core_envelope_required"):
        forged.pop(field, None)
        if field in bound:
            forged[field] = bound[field]
    forged.update(
        bound_action_request=bound,
        action=action,
        request_hash=action["request_hash"],
        action_request_hash=action["request_hash"],
    )
    return forged


def _remint_generation(request: dict[str, Any], generation: int) -> dict[str, Any]:
    """A universe generation that differs from the hashed card."""
    return _remint(
        request, lambda bound: bound["expected_evidence"].update(universe_generation=generation)
    )


def _remint_dropped_universe(request: dict[str, Any]) -> dict[str, Any]:
    """The universe and the Core requirement removed from a universe card's task."""

    def drop(bound: dict[str, Any]) -> None:
        bound.pop("expected_evidence", None)
        bound.pop("core_envelope_required", None)

    return _remint(request, drop)


def _allow_owner_effect(action, effect, *, key):
    return {
        "schema": "nexus.standing_grant_effect_authorization.v1",
        "action": action.value,
        "effect": dict(effect),
        "mutation_authorized": True,
        "authorization_hash": "f" * 64,
    }


def _create_card_via_gateway(
    ctl: Path, seed_head: str, create: dict[str, Any]
) -> tuple[str, str, dict[str, Any]]:
    """Write the card with the real ``nexus_task_card_create`` handler (#2218).

    Only the Owner standing-grant lookup is replaced; the card bytes, the
    universe validation and the rendering are the Gateway's own.
    """
    gateway_module.CANONICAL_SOURCE_ROOT = ctl
    gateway_module._git = lambda *args, **kwargs: seed_head
    original = UnifiedMCPGateway._require_owner_effect_authority
    UnifiedMCPGateway._require_owner_effect_authority = staticmethod(_allow_owner_effect)  # type: ignore[method-assign]
    try:
        response = UnifiedMCPGateway(service=MagicMock()).handle({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "nexus_task_card_create", "arguments": create},
        })
    finally:
        UnifiedMCPGateway._require_owner_effect_authority = original  # type: ignore[method-assign]
    created = response["result"]["structuredContent"]
    if response["result"]["isError"]:
        raise RuntimeError(f"nexus_task_card_create failed: {created}")
    _git(ctl, "add", "-A")
    _git(ctl, "commit", "-qm", "card")
    return _git(ctl, "rev-parse", "HEAD"), created["card_path"], created


def _run(root: Path, scenario: dict[str, Any]) -> dict[str, Any]:
    task_id = scenario["task_id"]
    create = scenario.get("create_card")
    ctl, head, card_rel = _controller(root, task_id, None if create else scenario.get("universe"))
    created: dict[str, Any] | None = None
    if create:
        head, card_rel, created = _create_card_via_gateway(ctl, head, create)
    # Same target namespace the Gateway derives from its source root, on any
    # temp-path layout.
    os.environ["NEXUS_TARGET_ROOT_OVERRIDE"] = str(ctl.parent / "nexus-runtime-targets")
    service_module.CANONICAL_SOURCE_ROOT = ctl
    gateway_module.CANONICAL_SOURCE_ROOT = ctl
    gateway_module._git = lambda *args, **kwargs: head
    gateway_module.pre_action_guard = lambda action, **kwargs: _ORIGINAL_GUARD(
        action, canonical_root=ctl, **kwargs
    )
    card_bytes = (ctl / card_rel).read_bytes()
    import hashlib

    arguments = {
        "task_id": task_id,
        "what": "bounded coverage witness",
        "why": "exercise the live evidence coverage seam",
        "allowed_files": ["README.md"],
        "verifier_commands": scenario["verifiers"],
        "owner_confirmation": True,
        "task_card_path": card_rel,
        "task_card_hash": hashlib.sha256(card_bytes).hexdigest(),
    }
    arguments.update(scenario.get("extra_arguments") or {})
    recorder = _RecordingService(
        state_dir=root / "gateway-state", auto_reconcile=False, ephemeral=True
    )
    gateway = UnifiedMCPGateway(service=recorder)
    gateway._provider_preflight = _ready_preflight  # type: ignore[method-assign]
    response = gateway.handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "nexus_worker_candidate", "arguments": arguments},
    })
    result: dict[str, Any] = {"gateway_is_error": bool(response["result"]["isError"])}
    if created is not None:
        result["created_card"] = {
            "card_path": card_rel,
            "card_hash": created["card_hash"],
            "card_text": (ctl / card_rel).read_text(encoding="utf-8"),
        }
    if result["gateway_is_error"]:
        result["gateway_error"] = response["result"]["structuredContent"]
        return result
    request = recorder.submitted[0]
    bound = request["bound_action_request"]
    result["request_expected_evidence"] = bound.get("expected_evidence")
    result["request_core_envelope_required"] = bound.get("core_envelope_required")
    result["request_has_evidence_keys"] = sorted(
        key for key in ("expected_evidence", "core_envelope_required") if key in bound
    )
    if scenario.get("remint_generation") is not None:
        request = _remint_generation(request, scenario["remint_generation"])
    if scenario.get("drop_universe"):
        request = _remint_dropped_universe(request)

    state_dir = root / "state"
    service = SelfHostedTaskService(
        state_dir=state_dir,
        auto_reconcile=False,
        ephemeral=True,
        ambient_core_port=LazyCanonicalCoreControlPort(state_dir),
    )
    registry = MagicMock()
    # #2346: a worker preflight that refuses (as on #2218 run2) ends the task
    # in FINAL_BLOCK before any provider runs.
    preflight_ready = scenario.get("worker_preflight_ready", True)
    registry.preflight.return_value = WorkerPreflight(
        provider=request["provider"],
        executable="witness-provider",
        executable_available=True,
        authorized=preflight_ready,
        implementation_status="ready",
        ready=preflight_ready,
        reason=None if preflight_ready else "agy: NEXUS_AGY_RUNTIME_AUTHORIZED=1 is required",
    )
    invocations: list[str] = []

    def invoke(provider, contract, lease, **kwargs):
        invocations.append(provider)
        target = Path(lease.target_worktree)
        (target / "README.md").write_text("# Repo\n\nbounded change\n", encoding="utf-8")
        return WorkerExecutionReceipt(
            provider=provider,
            task_id=contract.task_id,
            target_worktree=str(target),
            worker_status="completed",
            outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
            exit_code=0,
            executable_identity="witness-provider",
            argv=("witness-provider",),
            stdout_sha256="a" * 64,
            stderr_sha256="b" * 64,
            wall_time_ms=10,
            process_group_id=os.getpid(),
            process_group_killed=False,
            timed_out=False,
            provider_calls=1,
            evidence_complete=True,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
        )

    registry.invoke = invoke
    service.worker_registry = registry

    def launch_inline(task_id_arg, attempt_id):
        service._run_owned_task(task_id_arg, attempt_id)
        return service._read_state(task_id_arg)

    service._launch_worker = launch_inline  # type: ignore[method-assign]
    try:
        submitted = service.submit_task(request)
        result["submit_status"] = submitted.get("status")
    except Exception as exc:  # recorded, asserted by the caller
        result["submit_error"] = f"{type(exc).__name__}: {exc}"
    state = service._read_state(task_id) or {}
    receipt = state.get("verified_receipt") or {}
    result.update(
        status=state.get("status"),
        terminal_status=state.get("terminal_status"),
        error=state.get("error"),
        promotion_status=state.get("promotion_status"),
        candidate_commit_sha=state.get("candidate_commit_sha"),
        receipt_verified=receipt.get("verified"),
        receipt_commit_allowed=receipt.get("candidate_commit_allowed"),
        receipt_failure_reasons=receipt.get("failure_reasons"),
        core_verification_status=receipt.get("core_verification_status"),
        core_verdict=receipt.get("core_verdict"),
        receipt_keys=sorted(receipt),
        core_db_exists=Path(live_core_db_path(state_dir)).exists(),
    )
    # Restart: a fresh service on the same state root reads the same verdict,
    # and a fresh port reads the same Core session rows.
    reloaded = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    reloaded_receipt = (reloaded._read_state(task_id) or {}).get("verified_receipt") or {}
    result["reloaded_core_verdict"] = reloaded_receipt.get("core_verdict")
    session_id = ((state.get("host_preparation") or {}).get("session_id")) or None
    result["core_session_id"] = session_id
    if session_id and result["core_db_exists"]:
        readback = transport.CanonicalNexusCoreTransportPort(
            db_path=live_core_db_path(state_dir)
        ).readback_session(session_id)
        result["db_verification_row"] = readback["verification_row"]
    # #2346: the terminal Core record of a task that produced no Candidate.
    result["worker_invocations"] = invocations
    result["verified_receipt_present"] = state.get("verified_receipt") is not None
    result["attempt_id"] = state.get("attempt_id")
    result["terminal_core_record"] = state.get("terminal_core_record")
    result["reloaded_terminal_core_record"] = (reloaded._read_state(task_id) or {}).get(
        "terminal_core_record"
    )
    result["db_terminal_row"] = None
    if result["core_db_exists"] and state.get("attempt_id"):
        result["db_terminal_row"] = transport.CanonicalNexusCoreTransportPort(
            db_path=live_core_db_path(state_dir)
        ).readback_terminal_record(task_id, str(state["attempt_id"]))
    return result


def _host_universe_identities(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    """The card identity the host computes with the real pinned Core (#2246)."""
    identities: dict[str, Any] = {}
    for scenario in scenarios:
        universe = scenario.get("universe")
        if universe is None:
            continue
        try:
            identities[scenario["name"]] = core_universe_identity(universe)
        except Exception as exc:
            identities[scenario["name"]] = f"ERROR:{type(exc).__name__}:{exc}"
    return identities


def _core_conformance_universe_identity() -> dict[str, Any]:
    """Core's own conformance vector through the host's card->wire projection."""
    if not transport.CORE_AVAILABLE:
        return {"ok": False, "error": "CORE_UNAVAILABLE"}
    from product.protocol.generic_verification import GENERIC_PROTOCOL_CONFORMANCE_VECTORS

    checked = []
    for name, vector in GENERIC_PROTOCOL_CONFORMANCE_VECTORS.items():
        if not isinstance(vector, dict) or "expected_universe_identity" not in vector:
            continue
        contract = vector["value"]
        card_universe = {
            "universe_generation": contract.get("universe_generation", 0),
            "subjects": contract["expected_subjects"],
        }
        checked.append({
            "vector": name,
            "expected": vector["expected_universe_identity"],
            "host": core_universe_identity(card_universe),
        })
    return {
        "ok": bool(checked) and all(c["expected"] == c["host"] for c in checked),
        "checked": checked,
    }


def main() -> int:
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    # Resolved: the Gateway compares resolved paths against its source root.
    work = Path(spec["work"]).resolve()
    results: dict[str, Any] = {
        "core_available": transport.CORE_AVAILABLE,
        "core_import_error": transport.CORE_IMPORT_ERROR,
        # What this (Gateway-hosting) process itself reports to a deploy probe.
        "gateway_core_provenance": gateway_module.gateway_core_provenance(),
        "public_core_provenance": gateway_module.public_core_provenance(),
        "driver_pid": os.getpid(),
        "host_core_universe_identities": _host_universe_identities(spec["scenarios"]),
    }
    try:
        results["core_conformance_universe_identity"] = _core_conformance_universe_identity()
    except Exception as exc:
        results["core_conformance_universe_identity"] = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    for scenario in spec["scenarios"]:
        name = scenario["name"]
        try:
            results[name] = _run(work / name, scenario)
        except Exception as exc:
            results[name] = {
                "driver_error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc(),
            }
    Path(spec["out"]).write_text(json.dumps(results, default=str, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
