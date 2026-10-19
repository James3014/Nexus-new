# pyright: reportOptionalMemberAccess=false, reportMissingImports=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false
#!/usr/bin/env python3
"""Capability wiring audit: does a planner-selected capability run real code and leave evidence?

For every CapabilityPlanner node in scope this script

1. forces the node into a ``CapabilityPlan`` through the production planning seam
   (``plan_canonical_task_bundle``; the forcing knob is the route-oracle line
   ``Expected capability receipts: <node>`` in the task statement, the same string the
   benchmark wearing contract uses),
2. executes it through the real chain ``run_mainchain`` -> ``UnifiedRuntime`` ->
   ``capability_registry`` invoker -> ``capability_executor_registry`` executor (or the
   postflight / local-stage owner), against a small deterministic fixture workspace under
   ``scripts/ops/wiring_fixtures/<capability>/``,
3. asserts a physical, input-dependent effect (an artifact on disk, a hit, a block, an
   exit code) and runs a negative control where one exists,
4. issues one verdict per capability from the receipt plus the artifact.

Verdicts: REAL, SIMULATED, STUB, BLOCKED_<reason>, NOT_SELECTABLE, RETIRING,
MODEL_UNAVAILABLE.  No benchmark is scored.  Nothing here changes routing, policy, or
admission; the script only observes.

``claim_boundary.simulated``: since nexus-runtime #187 the runtime derives the flag from
the receipt's own execution evidence (``attested_claim_boundary``), so it is recorded in the
matrix (``receipt_claims_simulated``) and must agree with the physical evidence.  A row whose
executor ran and whose artifact assertion passed while the receipt still says
``simulated=true`` is REAL_UNATTESTED: a producer that under-reports its own execution.
See docs/experiments/capability_wiring_audit_2026-10.md.

Usage::

    .venv/bin/python scripts/ops/capability_wiring_audit.py
    .venv/bin/python scripts/ops/capability_wiring_audit.py --only sandbox,mempalace_gate
    .venv/bin/python scripts/ops/capability_wiring_audit.py --no-model
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import dataclasses
import hashlib
import inspect
import json
import os
import re
import shutil
import subprocess  # nosec B404 - fixed git argv only
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURE_ROOT = Path(__file__).resolve().parent / "wiring_fixtures"
SCHEMA = "nexus.capability_wiring_audit.v1"
PY = sys.executable
TOKEN_CEILING = 128000
OLLAMA_URL = os.environ.get("NEXUS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
AUDIT_MODEL = os.environ.get("NEXUS_WIRING_AUDIT_MODEL", "qwen2.5-coder:7b-instruct")

# ----------------------------------------------------------------------------- verdicts

REAL = "REAL"
REAL_UNATTESTED = "REAL_UNATTESTED"
SIMULATED = "SIMULATED"
STUB = "STUB"
NOT_SELECTABLE = "NOT_SELECTABLE"
RETIRING = "RETIRING"
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
BLOCKED_PREFIX = "BLOCKED_"
NOT_EXECUTABLE = "NOT_EXECUTABLE"
UNREACHABLE_NO_PLANNER_NODE = "UNREACHABLE_NO_PLANNER_NODE"

# Archived by the retirement PR (owned by another agent); never executed here.
RETIRING_CAPABILITIES: dict[str, str] = {
    "federation": "federation (archive PR)",
    "oracle_shadow": "aos_oracle / oracle promote (archive PR)",
    "stress_test": "stress_test + _exec_stress_test (archive PR)",
    "ui_validator": "ui_explorer / ui-validator + _exec_ui_validator (archive PR)",
    "benchmark": "benchmark_service + _exec_benchmark (archive PR)",
    "learning_closure": "_exec_learning_closure (archive PR; executor only, not a planner node)",
    # Second batch (ARCHIVED_2026-10-13.md, #1906): the invoker returns the archived skip reason.
    "integration_manager": "archived_retired_integration_manager_2026-10-13 (second archive batch)",
    "swarm_quiet_moment": "archived_echo_swarm_quiet_moment_2026-10-13 (second archive batch)",
    "llm_judge_panel": "archived_alias_llm_judge_panel_2026-10-13 (second archive batch)",
    # Legacy-engine batch (ARCHIVED_2026-10-13-legacy-engine.md): the AutonomicRouter body was
    # the legacy NexusEngine router; no policy rule enabled the node and nothing read its output.
    "autonomic_router": "archived_legacy_engine_autonomic_router_2026-10-13 (legacy-engine archive batch)",
}

# Executor-registry keys with no planner node, removed from EXECUTOR_REGISTRY by the second
# archive batch (ARCHIVED_2026-10-13.md, #1906).  EXECUTOR_ONLY below keeps what each one did.
RETIRED_EXECUTOR_ONLY_REASON = "archived_executor_only_no_planner_node_2026-10-13"
RETIRED_EXECUTOR_ONLY_NOTES: dict[str, str] = {
    "policy_capability_gate": (
        "executor removed 2026-10-13; nexus/services/policy_gate.py kept (legacy self_heal_selector)"
    ),
    "nightshift_runner_service": (
        "alias key removed 2026-10-13; the function stays as the body of the nightshift node"
    ),
    "battle_swarm": "alias key removed 2026-10-13; swarm / multi_agent nodes keep the real executor",
}

POSTFLIGHT_CAPABILITIES = frozenset({
    "artifact_gate",
    "claim_gate",
    "delivery_gate",
    "acceptance_check",
    "bdd_acceptance_skill",
})
LOCAL_STAGE_CAPABILITIES = frozenset({"local_model_executor", "repair_loop"})


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": bool(self.passed), "detail": str(self.detail)[:400]}


def _blocked(reason: Any) -> str:
    text = str(reason)
    return text if text.startswith(BLOCKED_PREFIX) else BLOCKED_PREFIX + text


def classify_verdict(obs: Mapping[str, Any]) -> tuple[str, str]:
    """Pure verdict logic over a normalized observation (testable without the runtime).

    ``obs`` keys (all optional, missing means falsy / empty):
      retiring, selected, not_selectable_reason, model_required, model_available,
      status (SUCCEEDED|FAILED|SKIPPED|BLOCKED|MISSING), invoked, gate_passed, skip_reason,
      block_reason, evidence_refs, stub, fixture_provider, hard_coded, input_insensitive,
      checks (list of {"name","passed","detail"}).
    Returns ``(verdict, reason)``.
    """
    if obs.get("retiring"):
        return RETIRING, str(obs.get("retiring"))
    if obs.get("selected") is False:
        return NOT_SELECTABLE, str(obs.get("not_selectable_reason") or "planner_did_not_select")
    if obs.get("model_required") and obs.get("model_available") is False:
        return MODEL_UNAVAILABLE, str(
            obs.get("model_unavailable_reason") or "model_endpoint_unreachable"
        )
    status = str(obs.get("status") or "").upper()
    if status == "MISSING":
        return _blocked(
            obs.get("block_reason") or "capability_not_reached"
        ), "capability_never_invoked"
    if status == "SKIPPED" or obs.get("skip_reason"):
        return _blocked(obs.get("skip_reason") or "skipped"), "explicit_skip_receipt"
    block_reason = str(obs.get("block_reason") or "")
    if status == "BLOCKED" or (block_reason and not obs.get("gate_passed")):
        return _blocked(block_reason or "blocked"), "executor_or_runtime_blocked"
    if obs.get("stub"):
        return STUB, "structural_stub_or_constant_receipt"
    if obs.get("fixture_provider"):
        return SIMULATED, "fixture_provider_or_synthetic_evidence"
    if obs.get("hard_coded"):
        first = obs["hard_coded"][0] if isinstance(obs["hard_coded"][0], Mapping) else {}
        where = f"{first.get('pattern')}@{first.get('file')}:{first.get('line')}" if first else ""
        return SIMULATED, "executor_uses_hard_coded_inputs:" + where
    if obs.get("input_insensitive"):
        return STUB, "outcome_independent_of_fixture_input"
    checks = [c for c in (obs.get("checks") or []) if isinstance(c, Mapping)]
    failed = [c for c in checks if not c.get("passed")]
    gate_passed = bool(obs.get("gate_passed"))
    has_evidence = bool(obs.get("evidence_refs"))
    if gate_passed and has_evidence and obs.get("invoked") is not False and checks and not failed:
        if obs.get("receipt_claims_simulated"):
            return (
                REAL_UNATTESTED,
                "executor_ran_and_artifact_passed_but_receipt_claims_simulated_true",
            )
        return REAL, "invoked_with_evidence_and_artifact_assertions_passed"
    if gate_passed and failed:
        return STUB, "gate_passed_without_checkable_effect:" + str(failed[0].get("name"))
    if gate_passed and not has_evidence:
        return STUB, "gate_passed_without_evidence_refs"
    if gate_passed and not checks:
        return STUB, "gate_passed_without_any_artifact_assertion"
    detail = str(failed[0].get("detail") or failed[0].get("name")) if failed else "gate_failed"
    return _blocked(
        block_reason or "gate_failed_on_valid_fixture"
    ), "executor_ran_but_gate_failed:" + detail


# ------------------------------------------------------------------------------ helpers


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def copy_fixture(name: str, dest: Path) -> Path:
    src = FIXTURE_ROOT / name
    if src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True)
    else:
        dest.mkdir(parents=True, exist_ok=True)
    return dest


@contextlib.contextmanager
def chdir(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


@dataclass(frozen=True)
class Policy:
    """Runtime authorization switches an audit run sets (everything else is untouched)."""

    name: str
    env: Mapping[str, str] = field(default_factory=dict)
    note: str = ""


# Production default: ``nexus run`` / mainchain does not set either switch (verified by grep:
# the only writers of these variables are tests, the A/B armor lane and canary helpers).
POLICY_PRODUCTION = Policy("production_default", {}, "neither authorization switch is set")
# Same switch the revived A/B armor lane sets in ``armor_environment`` (scripts/eval/run_memory_ab_v1.py).
POLICY_LOCAL_MODEL = Policy(
    "local_model_call_allowed",
    {"NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1"},
    "same switch as the A/B armor lane; local model on the M5 tunnel only",
)
# Executors autoreason/ddtree gate on the EXTERNAL flag although their bodies are offline Python.
POLICY_EXTERNAL_FLAG = Policy(
    "external_runtime_authorized_flag",
    {"NEXUS_EXTERNAL_RUNTIME_AUTHORIZED": "1"},
    "emergency-override env var; autoreason/ddtree bodies make no provider call",
)
POLICY_COMMITTEE_FLAG = Policy(
    "committee_feature_flag",
    {"NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1", "NEXUS_USE_COMMITTEE": "1"},
    "CommitteeControllerV263 is disabled unless NEXUS_USE_COMMITTEE=1",
)
SCRUBBED_ENV = (
    "NEXUS_LOCAL_MODEL_CALL_ALLOWED",
    "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED",
    "NEXUS_USE_COMMITTEE",
)


@contextlib.contextmanager
def policy_env(policy: Policy, extra: Mapping[str, str] | None = None) -> Iterator[None]:
    updates: dict[str, str | None] = {key: None for key in SCRUBBED_ENV}
    updates.update(policy.env)
    updates.update(dict(extra or {}))
    saved = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextlib.contextmanager
def capture_console() -> Iterator[list[str]]:
    """Collect what executors print/log while they run (some print their policy denial)."""
    import io
    import logging

    buffer = io.StringIO()
    lines: list[str] = []
    handler = logging.Handler(level=logging.WARNING)
    handler.emit = lambda record: lines.append(record.getMessage())  # type: ignore[method-assign]
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            yield lines
    finally:
        root.removeHandler(handler)
        lines.extend(buffer.getvalue().splitlines())


def blocking_console_line(lines: list[str]) -> str:
    for line in lines:
        if re.search(r"blocked by|denied|deny|rejected|refus", line, re.IGNORECASE):
            return line.strip()
    return ""


def probe_model(timeout: float = 4.0) -> dict[str, Any]:
    """Reachability of the M5 Ollama tunnel. Never starts a local model."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=timeout) as response:  # nosec B310 - operator-configured http endpoint
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {
            "available": False,
            "url": OLLAMA_URL,
            "reason": f"{type(exc).__name__}: {exc}"[:200],
            "models": [],
        }
    models = sorted(
        str(item.get("name")) for item in payload.get("models", []) if isinstance(item, Mapping)
    )
    return {
        "available": AUDIT_MODEL in models,
        "url": OLLAMA_URL,
        "model": AUDIT_MODEL,
        "models": models,
        "reason": "" if AUDIT_MODEL in models else f"model {AUDIT_MODEL} not listed by /api/tags",
    }


def source_location(fn: Callable[..., Any] | None) -> dict[str, Any]:
    if fn is None:
        return {"function": None, "file": None, "line": None}
    target = inspect.unwrap(fn)
    try:
        lines, start = inspect.getsourcelines(target)
        path = inspect.getsourcefile(target) or ""
    except (OSError, TypeError):
        return {
            "function": getattr(target, "__qualname__", repr(target)),
            "file": None,
            "line": None,
        }
    try:
        rel = str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        marker = "site-packages/"
        if marker in path:
            rel = path.split(marker, 1)[1]
        elif "/nexus_runtime/" in path:
            rel = "nexus_runtime/" + path.split("/nexus_runtime/", 1)[1]
        else:
            rel = path
    return {
        "function": getattr(target, "__qualname__", target.__name__),
        "file": rel,
        "line": start,
        "_lines": lines,
    }


def scan_hard_coded(fn: Callable[..., Any] | None, patterns: list[str]) -> list[dict[str, Any]]:
    """Static evidence that an executor body fixes an input the fixture tries to vary."""
    if fn is None or not patterns:
        return []
    loc = source_location(fn)
    lines = loc.get("_lines") or []
    start = int(loc.get("line") or 0)
    found: list[dict[str, Any]] = []
    for pattern in patterns:
        for offset, text in enumerate(lines):
            if pattern in text:
                found.append({
                    "pattern": pattern,
                    "file": loc.get("file"),
                    "line": start + offset,
                    "text": text.strip()[:160],
                })
                break
    return found


# ------------------------------------------------------------------- observation model


@dataclass
class Obs:
    """Normalized view of what one capability did in one execution."""

    source: str  # "e2e" (full UnifiedRuntime) | "registry" (production invoker, no runtime)
    stage: dict[str, Any] = field(default_factory=dict)
    resp: dict[str, Any] = field(default_factory=dict)
    outcome: dict[str, Any] = field(default_factory=dict)
    row: dict[str, Any] = field(default_factory=dict)
    receipt_terminal: str = ""
    receipt_failure_class: str = ""
    admission: dict[str, Any] = field(default_factory=dict)
    executor_receipt: dict[str, Any] = field(default_factory=dict)  # CapabilityReceipt.to_dict()
    receipt: dict[str, Any] = field(default_factory=dict)  # whole UnifiedRuntime receipt (e2e only)
    console_hint: str = (
        ""  # first blocking line the executor printed/logged (nightshift prints its policy denial)
    )

    @property
    def reached(self) -> bool:
        return bool(self.stage or self.row)

    @property
    def gate_passed(self) -> bool:
        if self.stage:
            return bool(self.stage.get("gate_passed")) and not bool(self.stage.get("skipped"))
        return bool(self.row.get("gate_passed")) and not bool(self.row.get("skipped"))

    @property
    def invoked(self) -> bool:
        if self.stage:
            return bool(self.stage.get("invoked"))
        return bool(self.row.get("invoked"))

    @property
    def evidence_refs(self) -> list[str]:
        refs = list(self.stage.get("evidence_refs") or self.row.get("evidence_refs") or [])
        return [str(ref) for ref in refs]

    @property
    def skip_reason(self) -> str:
        if self.stage.get("skipped") or self.row.get("skipped"):
            return str(
                self.stage.get("skip_reason")
                or self.row.get("skip_reason")
                or self.row.get("reason")
                or "skipped"
            )
        return ""

    @property
    def physical_callable(self) -> str:
        return str(self.stage.get("physical_callable") or self.row.get("physical_callable") or "")

    def block_reason(self) -> str:
        """Exact reason string for a blocked / failed capability, '' when it passed."""
        if self.gate_passed:
            return ""
        parts: list[str] = []
        reason = str(self.resp.get("reason") or "")
        inner = self.resp.get("response") if isinstance(self.resp.get("response"), Mapping) else {}
        violations = inner.get("contract_violations") if isinstance(inner, Mapping) else None
        if reason:
            parts.append(reason)
        if violations:
            parts.append(",".join(str(v) for v in violations))
        error = self.outcome.get("error")
        if error:
            parts.append(str(error)[:200])
        if not parts and isinstance(inner, Mapping) and inner.get("blockers"):
            parts.append(",".join(str(b) for b in inner["blockers"]))
        if not parts and isinstance(self.outcome.get("blockers"), list):
            parts.append(",".join(str(b) for b in self.outcome["blockers"]))
        if not parts and str(self.outcome.get("semantic_status") or "").upper() in {
            "BLOCKED",
            "FAILED",
            "UNVERIFIED",
        }:
            terminal = _result_terminal(self.outcome)
            parts.append(
                "semantic_status="
                + str(self.outcome.get("semantic_status"))
                + (f"(terminal_status={terminal})" if terminal else "")
            )
        if self.console_hint and not self.gate_passed:
            parts.append("console:" + self.console_hint[:180])
        if not parts and not self.stage and self.row:
            row_status = str(self.row.get("status") or "")
            row_reason = str(self.row.get("reason") or "")
            if row_status or row_reason:
                parts.append(":".join(item for item in (row_status, row_reason) if item))
            local = (
                self.receipt.get("local") if isinstance(self.receipt.get("local"), Mapping) else {}
            )
            lineage = (
                local.get("formal_local_runtime_lineage")
                if isinstance(local.get("formal_local_runtime_lineage"), Mapping)
                else {}
            )
            if lineage:
                blockers = ",".join(str(b) for b in lineage.get("blockers") or [])
                parts.append(
                    f"local_stage[{blockers}; executor_invoked={lineage.get('executor_invoked')}; model_call_count={lineage.get('model_call_count')}]"
                )
        return ":".join(parts)

    def status(self) -> str:
        if not self.reached:
            return "MISSING"
        if self.skip_reason:
            return "SKIPPED"
        if self.gate_passed:
            return "SUCCEEDED"
        if self.block_reason() or str(self.resp.get("status") or "").upper() == "BLOCKED":
            return "BLOCKED"
        return "FAILED"


def _result_terminal(outcome: Mapping[str, Any]) -> str:
    result = outcome.get("result")
    return str(result.get("terminal_status") or "") if isinstance(result, Mapping) else ""


def make_obs(
    cap: str,
    *,
    source: str,
    stage: Mapping[str, Any] | None,
    receipt: Mapping[str, Any] | None = None,
    executor_receipt: Any = None,
) -> Obs:
    stage_map = dict(stage or {})
    resp = (
        dict(stage_map.get("response") or {})
        if isinstance(stage_map.get("response"), Mapping)
        else {}
    )
    inner = resp.get("response") if isinstance(resp.get("response"), Mapping) else {}
    outcome = (
        inner.get("outcome")
        if isinstance(inner, Mapping) and isinstance(inner.get("outcome"), Mapping)
        else {}
    )
    if not outcome and isinstance(resp.get("outcome"), Mapping):
        outcome = resp["outcome"]
    if not outcome and isinstance(inner, Mapping) and inner.get("action"):
        outcome = inner  # postflight invokers report the gate verdict directly
    row: dict[str, Any] = {}
    receipt_map = dict(receipt or {})
    for item in receipt_map.get("capabilities") or []:
        if isinstance(item, Mapping) and item.get("name") == cap:
            row = dict(item)
            break
    admission = (
        receipt_map.get("workforce_admission")
        if isinstance(receipt_map.get("workforce_admission"), Mapping)
        else {}
    )
    exec_dict: dict[str, Any] = {}
    if executor_receipt is not None and hasattr(executor_receipt, "to_dict"):
        try:
            from nexus.engine.capability_receipts import attested_receipt_dict

            exec_dict = attested_receipt_dict(executor_receipt)
        except Exception as exc:  # noqa: BLE001 - recorded, not fatal
            exec_dict = {"to_dict_error": f"{type(exc).__name__}: {exc}"[:200]}
    return Obs(
        source=source,
        stage=stage_map,
        resp=resp,
        outcome=dict(outcome),
        row=row,
        receipt_terminal=str(receipt_map.get("terminal_status") or ""),
        receipt_failure_class=str(receipt_map.get("failure_class") or ""),
        admission={
            "decision": admission.get("overall_decision"),
            "reasons": list(admission.get("overall_reasons") or []),
        }
        if admission
        else {},
        executor_receipt=exec_dict,
        receipt=receipt_map,
    )


def claim_boundary_simulated(
    obs: Obs, receipt: Mapping[str, Any] | None
) -> tuple[bool | None, str]:
    """Where the ``simulated`` flag a downstream consumer would read comes from.

    Most specific first: the executor's own ``CapabilityReceipt``, then this capability's row
    in the UnifiedRuntime receipt (``capabilities[]``, runtime-attested per capability), and
    only then the task-level ``receipt_base`` (which also covers the online stand-in).
    """
    cap_cb = (
        ((obs.executor_receipt.get("receipt_base") or {}).get("claim_boundary") or {})
        if obs.executor_receipt
        else {}
    )
    if "simulated" in cap_cb:
        # fail closed: only an explicit False is real
        return (
            cap_cb["simulated"] is not False,
            "CapabilityReceipt.to_dict().receipt_base.claim_boundary (runtime-attested, #187)",
        )
    row_cb = (obs.row or {}).get("claim_boundary") if isinstance(obs.row, Mapping) else None
    if isinstance(row_cb, Mapping) and "simulated" in row_cb:
        # fail closed: only an explicit False is real
        return (
            row_cb["simulated"] is not False,
            "UnifiedRuntime receipt.capabilities[<cap>].claim_boundary (runtime-attested)",
        )
    rb_cb = ((receipt or {}).get("receipt_base") or {}).get("claim_boundary") or {}
    if "simulated" in rb_cb:
        # fail closed: only an explicit False is real
        return rb_cb[
            "simulated"
        ] is not False, "UnifiedRuntime receipt.receipt_base.claim_boundary (task level)"
    return None, "not_observed"


# ---------------------------------------------------------------------- planner stage


def oracle_statement(statement: str, cap: str) -> str:
    return f"{statement.rstrip()}\n\nNexus route oracle contract:\n- Expected capability receipts: {cap}.\n"


def plan_for(
    cap: str, statement: str, task_type: str, route_features: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Force ``cap`` through the production planning seam and report the plan."""
    from nexus.services.runtime_compat import (
        UnifiedRuntimeRequest,
        build_canonical_runtime_context,
        plan_canonical_task_bundle,
    )

    request = UnifiedRuntimeRequest(
        task_id=f"wiring-plan-{cap}",
        workspace_revision="wiring-audit-rev",
        task_statement=oracle_statement(statement, cap),
        task_type=task_type,
        route={"recommended_flow": "direct", "route_features": dict(route_features or {})},
        online_enabled=True,
        local_enabled=False,
        online_prompt="wiring audit",
    )
    bundle = plan_canonical_task_bundle(build_canonical_runtime_context(request))
    plan = bundle.plan
    trace = [
        item
        for item in plan.decision_trace
        if isinstance(item, Mapping) and item.get("capability") == cap
    ]
    state = next(
        (
            label
            for label, group in (
                ("required", plan.required_capabilities),
                ("conditional", plan.conditional_capabilities),
                ("optional", plan.optional_capabilities),
                ("forbidden", plan.forbidden_capabilities),
            )
            if cap in group
        ),
        "absent",
    )
    return {
        "selected": cap in plan.selected_capabilities,
        "state": state,
        "reasons": list(trace[0].get("reasons") or []) if trace else [],
        "selected_capabilities": list(plan.selected_capabilities),
        "plan_hash": bundle.plan_hash,
        "forcing": "route-oracle line 'Expected capability receipts: %s' in task_statement" % cap,
    }


# ----------------------------------------------------------------- executor resolution


def resolve_executor(cap: str) -> dict[str, Any]:
    """Executor key, function, file and line plus how the registry reaches it."""
    from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY
    from nexus.services import capability_registry as registry

    key = registry.EXECUTOR_REGISTRY_ALIASES.get(cap, cap)
    info: dict[str, Any] = {"registry_key": key}
    if cap in LOCAL_STAGE_CAPABILITIES:
        from nexus.services.local_heal.local_model_executor import LocalModelExecutor

        loc = source_location(LocalModelExecutor.run)
        info.update({
            "reached_via": "LOCAL_STAGE (UnifiedRuntime local stage -> LocalAssistService -> LocalModelExecutor)"
        })
    elif cap == "prompt_compression":
        from nexus_runtime.kernel.capabilities import build_prompt_compression_capability_invoker

        loc = source_location(build_prompt_compression_capability_invoker)
        info.update({
            "reached_via": "RUNTIME_INVOKER (registry maps prompt_compression to the runtime-owned compression edge, not _exec_prompt_compression)"
        })
    elif cap in {"artifact_gate", "claim_gate", "delivery_gate"}:
        from nexus_runtime.support.services.online_nexus_context import evaluate_postflight_gate

        loc = source_location(evaluate_postflight_gate)
        info.update({
            "reached_via": "POSTFLIGHT_INVOKER (online_nexus_context.build_plan_gated_postflight_invokers, after the verifier stage)"
        })
    else:
        fn = EXECUTOR_REGISTRY.get(key)
        loc = source_location(inspect.unwrap(fn) if fn else None)
        gated = cap in registry.ESCALATE_ONLY or cap in registry.PROBE_ONLY_REASON_CODES
        postflight = cap in POSTFLIGHT_CAPABILITIES
        via = "EXECUTOR_REGISTRY"
        if gated:
            via += " via build_escalate_gated_invoker (skipped unless escalate-triggered)"
        if postflight:
            via += " (run after the verifier stage)"
        info.update({"reached_via": via})
    info.update({k: v for k, v in loc.items() if not k.startswith("_")})
    info["_fn_lines"] = loc.get("_lines")
    return info


@contextlib.contextmanager
def record_executors() -> Iterator[dict[str, Any]]:
    """Observe (not alter) the CapabilityReceipt every registry executor returns."""
    from nexus.core import capability_executor_registry as reg

    originals = dict(reg.EXECUTOR_REGISTRY)
    records: dict[str, Any] = {}

    def wrap(key: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        def inner(plan: Any, task_desc: str) -> Any:
            receipt = fn(plan, task_desc)
            records[key] = receipt
            return receipt

        inner.__wrapped__ = fn  # type: ignore[attr-defined]
        return inner

    for key, fn in originals.items():
        reg.EXECUTOR_REGISTRY[key] = wrap(key, fn)
    try:
        yield records
    finally:
        reg.EXECUTOR_REGISTRY.clear()
        reg.EXECUTOR_REGISTRY.update(originals)


# --------------------------------------------------------------------- scenarios/specs


@dataclass
class Scenario:
    """One fixture-backed invocation of a capability through the production path."""

    statement: str
    task_type: str = "code_change"
    codeintel: dict[str, Any] = field(default_factory=dict)
    route_extra: dict[str, Any] = field(default_factory=dict)
    route_features: dict[str, Any] = field(default_factory=dict)
    verifier_command: tuple[str, ...] | None = None
    check: Callable[[Path, Obs], list[Check]] | None = None
    local_request_factory: Callable[[str], Any] | None = None
    local_enabled: bool = False
    online_enabled: bool = True
    local_worker: dict[str, Any] | None = None
    extra_env: dict[str, str] = field(default_factory=dict)
    # Workforce route whose worker the audit binds for the online stand-in.
    online_route: str = "fast_bounded_implementation"
    # UnifiedRuntimeRequest.canonical_context (execution world identity); None keeps the default.
    canonical_context: dict[str, Any] | None = None


Builder = Callable[[Path, str], "Scenario | None"]


@dataclass
class CapSpec:
    cap: str
    fixture: str | None
    build: Builder
    policies: tuple[Policy, ...] = (POLICY_PRODUCTION,)
    needs_model: bool = False
    hard_coded: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
    negative_check: Callable[[Obs, Obs], Check] | None = None
    flags: Callable[[Obs], dict[str, bool]] | None = None
    probe: Callable[[Path], dict[str, Any]] | None = None
    forced_note: str = ""
    # NOT_EXECUTABLE:<reason> for planner nodes whose execution contract has no physical
    # callable (or whose executor can never run); the run is still recorded as evidence.
    not_executable: str = ""
    # (dotted callable, literal) pairs scanned in a callee the executor delegates to.
    callee_hard_coded: tuple[tuple[str, str], ...] = ()


@dataclass
class Execution:
    obs: Obs
    receipt: dict[str, Any]
    planner: dict[str, Any]
    ws: Path
    policy: Policy
    triggered: bool
    path: str  # e2e | registry
    e2e_obs: Obs | None = None
    scen: Scenario | None = None
    console: list[str] = field(default_factory=list)


def online_worker(route_name: str = "fast_bounded_implementation") -> dict[str, Any]:
    """Online Workforce worker for the audit: the policy's own route for the demanded role.

    Default is bounded implementation; a spec may name another Workforce route when the
    forcing line itself changes the demanded role (see ``Scenario.online_route``).

    Controls are the ones the canonical product adapter physically supplies
    (``canonical_task_seam._actual_runtime_controls`` with one allowed file and a verifier command).
    The online channel itself is a deterministic no-op stand-in (no cloud call) declared as the
    admitted provider; the binding only lets Workforce Admission ALLOW the run so the capability
    invokers are reached.
    """
    from nexus.engine.canonical_task_seam import _actual_runtime_controls
    from nexus.services.model_workforce_policy import WorkforcePolicyLoader

    loader = WorkforcePolicyLoader()
    worker_id = loader.resolve_route(route_name)
    worker = loader.load().workers[worker_id]
    controls = set(
        _actual_runtime_controls(allowed_files=("target",), verifier_command=(PY, "verify.py"))
    )
    # The audit has no Task Card; declaring the control is the same shortcut as
    # scripts/ops/unified_runtime_scenarios.py (the gateway derives it from a verified card).
    controls.add("task_card")
    return {
        "worker_id": worker_id,
        "provider": worker.provider,
        "model": worker.model,
        "controls": sorted(controls),
    }


def worker_binding(route_name: str = "fast_bounded_implementation") -> dict[str, Any]:
    info = online_worker(route_name)
    return {"online": {"worker_id": info["worker_id"], "controls": info["controls"]}}


def make_verifier(
    ws: Path, command: tuple[str, ...], task_id: str
) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Real isolated verifier over the fixture; its artifact hash is a sha256 of the real run."""

    def verifier(context: Mapping[str, Any]) -> dict[str, Any]:
        from nexus.services.local_heal.isolated_verifier import (
            IsolatedVerifierRequest,
            run_isolated_verifier,
        )

        bundle = (
            context.get("capability_evidence_bundle")
            if isinstance(context.get("capability_evidence_bundle"), Mapping)
            else {}
        )
        source_hash = str(bundle.get("source_hash") or "")
        isolated = run_isolated_verifier(
            IsolatedVerifierRequest(
                task_id=str(context.get("task_id") or task_id),
                workspace_path=str(ws),
                verifier_command=tuple(command),
                timeout_sec=30.0,
                verifier_allowed=True,
            )
        )
        passed = isolated.verifier_status == "pass" and isolated.exit_code == 0
        payload = json.dumps(
            {
                "task_id": isolated.task_id,
                "exit_code": isolated.exit_code,
                "stdout_tail": isolated.stdout_tail,
                "stderr_tail": isolated.stderr_tail,
                "source_hash": source_hash,
                "command": list(command),
            },
            sort_keys=True,
        ).encode("utf-8")
        return {
            "task_id": str(context.get("task_id") or task_id),
            "invoked": True,
            "gate_passed": passed,
            "semantic_status": "VERIFIED" if passed else "UNVERIFIED",
            "verifier_status": isolated.verifier_status,
            "verifier_artifact": ("sha256:" + sha256_bytes(payload)) if passed else "",
            "source_hash": source_hash if passed else "",
            "evidence_refs": [f"isolated-verifier:{isolated.task_id}"],
            "exit_code": isolated.exit_code,
            "stdout_tail": isolated.stdout_tail,
            "physical_callable": "nexus.services.local_heal.isolated_verifier.run_isolated_verifier",
        }

    return verifier


ONLINE_SEEN_FILE = ".wiring_audit_online_seen.json"


def online_stand_in(
    task_id: str, route_name: str = "fast_bounded_implementation"
) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Deterministic no-model stand-in for the online channel (never a provider call).

    It records (observes) the prompt it was handed in ``ONLINE_SEEN_FILE`` under the cwd, so a
    capability that rewrites the online prompt (prompt_compression) can be checked physically.
    """
    provider = str(online_worker(route_name)["provider"])

    def online(context: Mapping[str, Any]) -> dict[str, Any]:
        prompt = str(context.get("online_prompt") or "")
        with contextlib.suppress(OSError):
            Path(ONLINE_SEEN_FILE).write_text(
                json.dumps({
                    "task_id": task_id,
                    "online_prompt_chars": len(prompt),
                    "online_prompt_head": prompt[:160],
                    "online_prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
                    "online_prompt": prompt[:50000],
                    "capability_context_compressed": bool(
                        context.get("capability_context_compressed")
                    ),
                }),
                encoding="utf-8",
            )
        return {
            "task_id": task_id,
            "invoked": True,
            "status": "SUCCEEDED",
            "gate_passed": True,
            "response": {"text": "wiring-audit online stand-in"},
            "evidence_refs": ["wiring-audit:online_stand_in"],
            "physical_callable": "scripts.ops.capability_wiring_audit.online_stand_in",
        }

    online.provider = provider  # type: ignore[attr-defined]
    online.online_invoker_provider = provider  # type: ignore[attr-defined]
    return online


def _build_request(cap: str, scen: Scenario, ws: Path, task_id: str, trigger: bool) -> Any:
    from nexus.services.runtime_compat import UnifiedRuntimeRequest

    codeintel = {"workspace_root": str(ws), **scen.codeintel}
    bindings: dict[str, Any] = worker_binding(scen.online_route) if scen.online_enabled else {}
    if scen.local_worker:
        bindings["local"] = dict(scen.local_worker)
    route: dict[str, Any] = {
        "recommended_flow": "direct" if scen.online_enabled else "local_only",
        "injected_transport": True,
        "online_policy": "auto" if scen.online_enabled else "deny",
        "workspace_root": str(ws),
        "workforce_admission_enabled": True,
        "workforce_bindings": bindings,
        "route_features": dict(scen.route_features),
    }
    if scen.online_enabled:
        route["provider"] = str(online_worker(scen.online_route)["provider"])
    if trigger:
        route["escalate_triggered"] = True
    route.update(scen.route_extra)
    return UnifiedRuntimeRequest(
        task_id=task_id,
        workspace_revision="wiring-audit-rev",
        task_statement=oracle_statement(scen.statement, cap),
        task_type=scen.task_type,
        route=route,
        online_enabled=bool(scen.online_enabled),
        local_enabled=bool(scen.local_enabled),
        online_prompt=scen.statement,
        online_model_name=str(online_worker(scen.online_route)["model"])
        if scen.online_enabled
        else None,
        codeintel=codeintel,
        local_request=scen.local_request_factory(task_id) if scen.local_request_factory else None,
        canonical_context=dict(scen.canonical_context) if scen.canonical_context else None,
    )


def run_e2e(
    cap: str,
    scen: Scenario,
    ws: Path,
    policy: Policy,
    *,
    trigger: bool,
    task_id: str,
    receipt_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Full chain: run_mainchain -> UnifiedRuntime -> registry invokers -> executors."""
    from nexus.services.mainchain_entry import build_mainchain_capability_invokers, run_mainchain

    request = _build_request(cap, scen, ws, task_id, trigger)
    verifier = make_verifier(ws, scen.verifier_command, task_id) if scen.verifier_command else None
    local_service = None
    if scen.local_enabled:
        from nexus.services.local_assist_service import LocalAssistService

        local_service = LocalAssistService()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        capture_console() as console,
        record_executors() as records,
        policy_env(policy, scen.extra_env),
        chdir(ws),
    ):
        receipt = run_mainchain(
            request,
            online_invoker=online_stand_in(task_id, scen.online_route),
            local_service=local_service,
            capability_invokers=build_mainchain_capability_invokers(
                codeintel=dict(request.codeintel)
            ),
            verifier=verifier,
            learning=None,
            receipt_path=receipt_path,
            with_nexus_armor=True,
        )
    return dict(receipt), dict(records), console


def run_registry_level(
    cap: str, scen: Scenario, ws: Path, policy: Policy, *, trigger: bool, task_id: str
) -> tuple[Obs, dict[str, Any]]:
    """Production invoker only (no runtime): used when the runtime blocks before reaching the node."""
    from nexus_runtime.kernel.capabilities import _capability_stage
    from nexus_runtime.kernel.constants import REQUEST_SCHEMA

    from nexus.services.mainchain_entry import build_mainchain_capability_invokers
    from nexus.services.runtime_compat import (
        build_canonical_runtime_context,
        plan_canonical_task_bundle,
    )

    request = _build_request(cap, scen, ws, task_id, trigger)
    # Plan from a request without the constraint feed: the canonical seam may refuse that feed
    # (e.g. keys containing 'model'), which is itself recorded by the e2e attempt.
    plan_request = _build_request(
        cap, dataclasses.replace(scen, codeintel={}), ws, task_id, trigger
    )
    bundle = plan_canonical_task_bundle(build_canonical_runtime_context(plan_request))
    plan_payload = bundle.to_dict()["plan_payload"]
    verifier_ctx: dict[str, Any] = {}
    with (
        capture_console() as console,
        record_executors() as records,
        policy_env(policy, scen.extra_env),
        chdir(ws),
    ):
        if scen.verifier_command:
            verifier_ctx = make_verifier(ws, scen.verifier_command, task_id)({
                "task_id": task_id,
                "capability_evidence_bundle": {
                    "source_hash": sha256_bytes(
                        f"wiring-audit-rev:{request.task_statement}".encode()
                    )
                },
            })
        invokers = build_mainchain_capability_invokers(codeintel=dict(request.codeintel))
        context = {
            "schema": REQUEST_SCHEMA,
            "task_id": task_id,
            "workspace_revision": "wiring-audit-rev",
            "task_statement": request.task_statement,
            "task_type": request.task_type,
            "route": dict(request.route),
            "codeintel": dict(request.codeintel),
            "pillars": {},
            "planner": dict(plan_payload),
            "local": {},
            "online_prompt": request.online_prompt,
            "capability_results": {},
        }
        if verifier_ctx:
            context["verifier"] = verifier_ctx
        raw = invokers[cap](context)
    stage = _capability_stage(cap, task_id, raw)
    key = _registry_key(cap)
    obs = make_obs(cap, source="registry", stage=stage, executor_receipt=records.get(key))
    obs.console_hint = blocking_console_line(console)
    return obs, dict(records)


def _registry_key(cap: str) -> str:
    from nexus.services import capability_registry as registry

    return registry.EXECUTOR_REGISTRY_ALIASES.get(cap, cap)


def execute(
    spec: CapSpec,
    variant: str,
    work_root: Path,
    policy: Policy,
    *,
    trigger: bool,
    out_dir: Path,
    tag: str,
) -> Execution | None:
    """Copy the fixture, build the scenario, run e2e, fall back to registry-level when not reached."""
    ws = work_root / f"{spec.cap}__{tag}"
    if ws.exists():
        shutil.rmtree(ws)
    if spec.fixture:
        copy_fixture(spec.fixture, ws)
    else:
        ws.mkdir(parents=True)
    scen = spec.build(ws, variant)
    if scen is None:
        return None
    task_id = re.sub(r"[^A-Za-z0-9_-]", "_", f"wiring-{spec.cap}-{tag}")[:100]
    planner = plan_for(spec.cap, scen.statement, scen.task_type, scen.route_features)
    if not planner["selected"]:
        return Execution(Obs(source="none"), {}, planner, ws, policy, trigger, "none", scen=scen)
    receipt_path = out_dir / "receipts" / f"{spec.cap}.{tag}.e2e.json"
    try:
        receipt, records, console = run_e2e(
            spec.cap, scen, ws, policy, trigger=trigger, task_id=task_id, receipt_path=receipt_path
        )
    except ValueError as exc:
        if not str(exc).startswith("canonical_context_"):
            raise
        # The production request seam refuses the audit's input before any capability can run.
        receipt = {
            "terminal_status": "REJECTED_AT_REQUEST",
            "failure_class": "canonical_context_rejected",
            "workforce_admission": {
                "overall_decision": "NOT_EVALUATED",
                "overall_reasons": [str(exc)],
            },
        }
        records = {}
        console = []
    stage = (receipt.get("capability_results") or {}).get(spec.cap)
    key = _registry_key(spec.cap)
    e2e_obs = make_obs(
        spec.cap, source="e2e", stage=stage, receipt=receipt, executor_receipt=records.get(key)
    )
    e2e_obs.console_hint = blocking_console_line(console)
    path = "e2e"
    obs = e2e_obs
    if not e2e_obs.reached:
        # Local-stage capabilities are reported on the capability row only; anything else the
        # runtime never reached is re-run through the production invoker for executor-level truth.
        if spec.cap not in LOCAL_STAGE_CAPABILITIES:
            ws_reg = work_root / f"{spec.cap}__{tag}__registry"
            if ws_reg.exists():
                shutil.rmtree(ws_reg)
            if spec.fixture:
                copy_fixture(spec.fixture, ws_reg)
            else:
                ws_reg.mkdir(parents=True)
            scen_reg = spec.build(ws_reg, variant)
            if scen_reg is None:
                raise RuntimeError("scenario_vanished")
            obs, _ = run_registry_level(
                spec.cap, scen_reg, ws_reg, policy, trigger=trigger, task_id=task_id + "_reg"
            )
            ws = ws_reg
            path = "registry"
    return Execution(
        obs,
        receipt,
        planner,
        ws,
        policy,
        trigger,
        path,
        e2e_obs=e2e_obs,
        scen=scen,
        console=list(console),
    )


# --------------------------------------------------------------------- evaluation


def default_flags(obs: Obs) -> dict[str, bool]:
    physical = obs.physical_callable.lower()
    inner = obs.resp.get("response") if isinstance(obs.resp.get("response"), Mapping) else {}
    stub = bool(obs.resp.get("stub")) or "structural_stub" in physical
    fixture = "fixture" in physical or str((inner or {}).get("source") or "").startswith("fixture")
    return {"stub": stub, "fixture_provider": fixture}


def verdict_obs(
    spec: CapSpec,
    primary: Obs,
    executor: Obs,
    checks: list[Check],
    *,
    hard_coded: list[dict[str, Any]],
    input_insensitive: bool,
    receipt_claims_simulated: bool | None = None,
) -> dict[str, Any]:
    flags = (spec.flags or default_flags)(executor)
    return {
        "receipt_claims_simulated": receipt_claims_simulated,
        "selected": True,
        "status": executor.status(),
        "invoked": executor.invoked,
        "gate_passed": executor.gate_passed,
        "skip_reason": executor.skip_reason,
        "block_reason": executor.block_reason(),
        "evidence_refs": executor.evidence_refs,
        "stub": flags.get("stub", False),
        "fixture_provider": flags.get("fixture_provider", False),
        "hard_coded": hard_coded,
        "input_insensitive": input_insensitive,
        "checks": [c.to_dict() for c in checks],
    }


def unreached_reason(obs: Obs) -> str:
    reasons = "; ".join(str(item) for item in obs.admission.get("reasons") or [])
    base = obs.receipt_failure_class or obs.receipt_terminal or "capability_not_reached"
    return f"{base}: {reasons}" if reasons else base


def is_auth_block(obs: Obs) -> bool:
    """A block a further authorization switch could lift (auth gate or feature flag)."""
    reason = obs.block_reason()
    return any(
        token in reason for token in ("BLOCKED_EXTERNAL_AUTH", "auth_gate", "FEATURE_DISABLED")
    )


def audit_capability(
    spec: CapSpec, work_root: Path, out_dir: Path, model: Mapping[str, Any], *, allow_model: bool
) -> dict[str, Any]:
    from nexus.services import capability_registry as registry

    cap = spec.cap
    row: dict[str, Any] = {
        "capability": cap,
        "fixture": f"scripts/ops/wiring_fixtures/{spec.fixture}" if spec.fixture else None,
    }
    executor_info = resolve_executor(cap)
    fn_lines = executor_info.pop("_fn_lines", None)
    row["executor"] = executor_info
    gated = cap in registry.ESCALATE_ONLY or cap in registry.PROBE_ONLY_REASON_CODES
    row["gaps"] = list(spec.gaps)

    if spec.needs_model and (not allow_model or not model.get("available")):
        row["verdict"], row["verdict_reason"] = classify_verdict({
            "selected": True,
            "model_required": True,
            "model_available": False,
            "model_unavailable_reason": str(model.get("reason") or "model_audit_disabled"),
        })
        row["model"] = dict(model)
        return row

    # Production default behaviour of an escalate-gated node: planner selects, invoker skips.
    if gated:
        ex0 = execute(
            spec,
            "positive",
            work_root,
            POLICY_PRODUCTION,
            trigger=False,
            out_dir=out_dir,
            tag="untriggered",
        )
        if ex0 is not None and ex0.e2e_obs is not None:
            row["untriggered_production_default"] = {
                "status": ex0.e2e_obs.status(),
                "skip_reason": ex0.e2e_obs.skip_reason,
                "reached": ex0.e2e_obs.reached,
            }
    row["trigger_switch"] = (
        "route.escalate_triggered=True (set by product_capability_canary_helper; not by nexus run)"
        if gated
        else None
    )

    attempts: list[dict[str, Any]] = []
    final: Execution | None = None
    for policy in spec.policies:
        ex = execute(
            spec,
            "positive",
            work_root,
            policy,
            trigger=gated,
            out_dir=out_dir,
            tag=f"pos_{policy.name}",
        )
        if ex is None:
            continue
        final = ex
        attempts.append({
            "policy": policy.name,
            "env": dict(policy.env),
            "status": ex.obs.status(),
            "path": ex.path,
            "block_reason": ex.obs.block_reason(),
        })
        if not ex.planner["selected"] or not is_auth_block(ex.obs):
            break
    if final is None:
        raise RuntimeError("no_execution")
    row["planner"] = final.planner
    row["policy_attempts"] = attempts
    if cap in NATURAL_TRIGGERS:
        row["production_default_selection"] = natural_selection(cap)
    if not final.planner["selected"]:
        row["verdict"], row["verdict_reason"] = classify_verdict({
            "selected": False,
            "not_selectable_reason": "planner_reasons="
            + ",".join(final.planner["reasons"])
            + f";state={final.planner['state']}",
        })
        _attach_probe(spec, row, work_root)
        return row

    exe_obs = final.obs
    primary = final.e2e_obs or final.obs
    row["product_path_reachable"] = bool(primary.reached)
    row["receipt_terminal_status"] = primary.receipt_terminal
    row["workforce_admission"] = primary.admission
    row["policy_switches_needed"] = dict(final.policy.env)
    row["policy_used"] = final.policy.name
    row["path"] = final.path
    simulated, source = claim_boundary_simulated(
        exe_obs if exe_obs.executor_receipt else primary, primary.receipt or final.receipt
    )
    row["receipt_claims_simulated"] = simulated
    row["claim_boundary_simulated_source"] = source
    row["evidence_refs"] = exe_obs.evidence_refs
    row["physical_callable"] = exe_obs.physical_callable
    row["console_tail"] = [line[:240] for line in final.console if line.strip()][-25:]

    checks: list[Check] = []
    if exe_obs.reached and final.scen is not None and final.scen.check is not None:
        try:
            checks = list(final.scen.check(final.ws, exe_obs))
        except Exception as exc:  # noqa: BLE001 - a crashing assertion is itself a finding
            checks = [Check("assertion_crashed", False, f"{type(exc).__name__}: {exc}")]

    input_insensitive = False
    if spec.negative_check is not None and exe_obs.reached:
        neg = execute(
            spec, "negative", work_root, final.policy, trigger=gated, out_dir=out_dir, tag="neg"
        )
        if neg is not None and neg.obs.reached:
            nc = spec.negative_check(exe_obs, neg.obs)
            checks.append(nc)
            input_insensitive = not nc.passed
            row["negative_control"] = {
                **nc.to_dict(),
                "negative_status": neg.obs.status(),
                "negative_block_reason": neg.obs.block_reason(),
            }
        else:
            row["negative_control"] = {
                "name": "negative_control",
                "passed": None,
                "detail": "negative scenario did not reach the capability",
            }

    hard_coded = scan_hard_coded_from_lines(fn_lines, executor_info, list(spec.hard_coded))
    hard_coded += scan_callee_hard_coded(spec.callee_hard_coded)
    row["hard_coded_inputs"] = hard_coded
    row["checks"] = [c.to_dict() for c in checks]

    exec_verdict, exec_reason = classify_verdict(
        verdict_obs(
            spec,
            exe_obs,
            exe_obs,
            checks,
            hard_coded=hard_coded,
            input_insensitive=input_insensitive,
            receipt_claims_simulated=simulated,
        )
        if exe_obs.reached
        else {"selected": True, "status": "MISSING", "block_reason": unreached_reason(primary)}
    )
    if primary.reached:
        row["verdict"], row["verdict_reason"] = exec_verdict, exec_reason
    else:
        row["verdict"], row["verdict_reason"] = classify_verdict({
            "selected": True,
            "status": "MISSING",
            "block_reason": unreached_reason(primary),
        })
        row["executor_level_verdict"] = exec_verdict
        row["executor_level_reason"] = exec_reason
    if len(attempts) > 1:
        first_obs = {
            "selected": True,
            "status": attempts[0]["status"],
            "block_reason": attempts[0]["block_reason"],
        }
        row["verdict_production_default"] = (
            classify_verdict(first_obs)[0] if attempts[0]["status"] != "SUCCEEDED" else "see_final"
        )
    if spec.not_executable:
        row["observed_verdict"] = row["verdict"]
        row["observed_verdict_reason"] = row["verdict_reason"]
        row["verdict"] = f"{NOT_EXECUTABLE}:{spec.not_executable}"
        row["verdict_reason"] = "execution_contract_has_no_runnable_physical_callable"
    _attach_probe(spec, row, work_root)
    row["outcome_excerpt"] = json.loads(json.dumps(exe_obs.outcome, default=str))
    row["receipt_path"] = str((out_dir / "receipts" / f"{cap}.json").relative_to(out_dir))
    return row


def _attach_probe(spec: CapSpec, row: dict[str, Any], work_root: Path) -> None:
    if spec.probe is None:
        return
    probe_ws = work_root / f"{spec.cap}__probe"
    if probe_ws.exists():
        shutil.rmtree(probe_ws)
    if spec.fixture:
        copy_fixture(spec.fixture, probe_ws)
    else:
        probe_ws.mkdir(parents=True)
    try:
        row["component_probe"] = spec.probe(probe_ws)
    except Exception as exc:  # noqa: BLE001
        row["component_probe"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}


def scan_callee_hard_coded(pairs: tuple[tuple[str, str], ...]) -> list[dict[str, Any]]:
    """Literal evidence inside a callee the executor delegates to (``module:qualname``)."""
    import importlib

    found: list[dict[str, Any]] = []
    for target, pattern in pairs:
        module_name, _, qualname = target.partition(":")
        obj: Any = importlib.import_module(module_name)
        for part in qualname.split("."):
            obj = getattr(obj, part)
        found += scan_hard_coded(obj, [pattern])
    return found


def scan_hard_coded_from_lines(
    lines: list[str] | None, executor_info: Mapping[str, Any], patterns: list[str]
) -> list[dict[str, Any]]:
    if not lines or not patterns:
        return []
    start = int(executor_info.get("line") or 0)
    found: list[dict[str, Any]] = []
    for pattern in patterns:
        for offset, text in enumerate(lines):
            if pattern in text:
                found.append({
                    "pattern": pattern,
                    "file": executor_info.get("file"),
                    "line": start + offset,
                    "text": text.strip()[:160],
                })
                break
    return found


# ------------------------------------------------------------------- scenario builders


def _result(obs: Obs) -> dict[str, Any]:
    value = obs.outcome.get("result")
    return dict(value) if isinstance(value, Mapping) else {}


def _git(ws: Path, *args: str) -> str:
    done = subprocess.run(  # nosec B603 B607 - fixed git argv
        ["git", "-c", "user.email=wiring@audit.local", "-c", "user.name=wiring-audit", *args],
        cwd=ws,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout


def _verifier_stdout(obs: Obs) -> str:
    verifier = (
        obs.receipt.get("verifier") if isinstance(obs.receipt.get("verifier"), Mapping) else {}
    )
    response = verifier.get("response") if isinstance(verifier.get("response"), Mapping) else {}
    return str(response.get("stdout_tail") or verifier.get("stdout_tail") or "")


def build_codeintel(ws: Path, variant: str) -> Scenario:
    symbol = "compute_total" if variant == "positive" else "no_such_symbol_wiring_audit"

    def check(_ws: Path, obs: Obs) -> list[Check]:
        res = _result(obs)
        files = [str(f) for f in res.get("files") or []]
        return [
            Check(
                "lookup_performed",
                obs.outcome.get("lookup_performed") is True,
                str(obs.outcome.get("lookup_performed")),
            ),
            Check(
                "known_symbol_found",
                obs.outcome.get("found") is True,
                f"found={obs.outcome.get('found')}",
            ),
            Check(
                "match_points_at_service_module",
                any(f.endswith("service.py") for f in files),
                f"files={files}",
            ),
        ]

    return Scenario(
        statement="Inspect compute_total before changing the discount rule",
        task_type="code_change",
        codeintel={"target_file": "app/service.py", "target_symbol": symbol},
        check=check,
    )


def neg_codeintel(pos: Obs, neg: Obs) -> Check:
    ok = pos.outcome.get("found") is True and neg.outcome.get("found") is False
    return Check(
        "negative_control:unknown_symbol_not_found",
        ok,
        f"pos.found={pos.outcome.get('found')} neg.found={neg.outcome.get('found')}",
    )


def probe_codeintel(ws: Path) -> dict[str, Any]:
    """Component probe: what the codeintel services can say that the executor does not surface."""
    from nexus.services.codeintel.graph_builder import build_graph
    from nexus.services.codeintel.impact_service import analyze_impact

    graph = build_graph(ws)
    impact = analyze_impact(ws, ["app/service.py"])
    nodes = graph.get("nodes") or []
    return {
        "ok": len(nodes) >= 4 and "app/api.py" in list(impact.impacted_files),
        "graph_nodes": len(nodes),
        "graph_edges": len(graph.get("edges") or []),
        "impact_set_for_compute_total_module": list(impact.impacted_files),
        "note": "build_graph/analyze_impact produce a 4-node graph and the impact set directly; the registry executor only calls PythonCodeSkeletonProvider.lookup_implementation",
    }


def build_research(ws: Path, variant: str) -> Scenario:
    question = (ws / "question.md").read_text(encoding="utf-8").strip()
    statement = (
        question
        if variant == "positive"
        else "Which package manager does the wiring audit negative control use?"
    )

    def check(_ws: Path, obs: Obs) -> list[Check]:
        findings = [str(f) for f in _result(obs).get("findings") or []]
        return [
            Check(
                "task_text_reached_handler",
                bool(findings) and findings != ["Empty research task."],
                f"findings={findings}",
            ),
            Check(
                "findings_reference_the_question",
                any("compute_total" in f or "discount" in f.lower() for f in findings),
                f"findings={findings}",
            ),
        ]

    return Scenario(statement=statement, task_type="research", check=check)


def neg_research(pos: Obs, neg: Obs) -> Check:
    same = _result(pos) == _result(neg)
    return Check(
        "negative_control:different_question_gives_different_result",
        not same,
        "identical result for two different questions" if same else "results differ",
    )


def build_hyper(ws: Path, variant: str) -> Scenario:
    # Local channel: every model candidate is a verified-subtask of the Workforce-admitted ollama
    # worker (armored local lane, M5 endpoint); the sprint re-scores it with its own pytest run.
    # The negative variant drops the test file, so the local channel has no verifier and must not
    # call the model.
    original_hash = sha256_file(ws / "pricing.py")
    codeintel: dict[str, Any] = {
        "hyper_candidate_count": 3,
        "hyper_min_candidate_pool": 2,
        "hyper_target_file": "pricing.py",
        "hyper_llm_mode": True,
        "hyper_llm_channel": "local",
    }
    if variant == "positive":
        codeintel["hyper_test_file"] = "test_pricing.py"

    def check(root: Path, obs: Obs) -> list[Check]:
        result = _result(obs)
        candidates = [c for c in obs.outcome.get("candidates") or [] if isinstance(c, Mapping)]
        model_ok = [
            c
            for c in candidates
            if str(c.get("source") or "").startswith("llm") and float(c.get("score") or 0) >= 1.0
        ]
        local_runs = [
            u
            for u in obs.outcome.get("unified_runtime_receipts") or []
            if isinstance(u, Mapping) and u.get("local_status") == "SUCCEEDED"
        ]
        return [
            Check(
                "sprint_status_success",
                str(result.get("status") or "").upper() in {"SUCCESS", "SUCCEEDED"},
                f"status={result.get('status')} reason={result.get('reason')}",
            ),
            Check(
                "sprint_produced_at_least_two_candidates",
                int(result.get("attempt_count") or 0) >= 2,
                f"attempt_count={result.get('attempt_count')}",
            ),
            Check(
                "llm_mode_effective_local_channel",
                obs.outcome.get("llm_mode_effective") is True
                and obs.outcome.get("llm_channel") == "local",
                f"llm_mode_effective={obs.outcome.get('llm_mode_effective')} channel={obs.outcome.get('llm_channel')} guard={obs.outcome.get('learn_slo_guard')}",
            ),
            Check(
                "model_candidate_verified_by_sprint_pytest",
                bool(model_ok) and int(obs.outcome.get("model_calls") or 0) >= 1,
                f"model_verified={len(model_ok)} model_calls={obs.outcome.get('model_calls')} sources={[c.get('source') for c in candidates]}",
            ),
            Check(
                "local_lane_runs_succeeded",
                bool(local_runs),
                f"local unified runs={len(local_runs)}",
            ),
            Check(
                "target_file_restored_after_scoring",
                sha256_file(root / "pricing.py") == original_hash,
                "pricing.py hash unchanged",
            ),
        ]

    return Scenario(
        statement=(
            "Fix apply_discount in pricing.py: the percent must be divided by 100, not 10, "
            "so test_pricing.py passes"
        ),
        task_type="research",
        codeintel=codeintel,
        # Same armor-on local switches as the Local stage rows, plus the documented benchmark
        # override of the learn-phase SLO guard (a fresh fixture has no learn-phase history; without
        # it the sprint silently drops llm_mode, which the receipt now reports).
        # NEXUS_LOCAL_MODEL_CALL_ALLOWED stays with the policy attempts, so the production default
        # attempt still runs without it.
        extra_env={
            **{
                key: value
                for key, value in local_stage_env(ws).items()
                if key != "NEXUS_LOCAL_MODEL_CALL_ALLOWED"
            },
            "NEXUS_FORCE_LLM_DESPITE_LEARN_SLO": "1",
        },
        check=check,
    )


def neg_hyper(pos: Obs, neg: Obs) -> Check:
    neg_calls = int(neg.outcome.get("model_calls") or 0)
    neg_status = str(neg.outcome.get("sprint_status") or "")
    neg_runs = len(neg.outcome.get("unified_runtime_receipts") or [])
    ok = pos.gate_passed and not neg.gate_passed and neg_calls == 0 and neg_runs == 0
    return Check(
        "negative_control:no_test_file_no_model_call",
        ok,
        f"neg.sprint_status={neg_status} neg.model_calls={neg_calls} neg.local_runs={neg_runs} neg.block_reason={neg.block_reason()}",
    )


def build_nightshift(ws: Path, variant: str) -> Scenario:
    def check(root: Path, obs: Obs) -> list[Check]:
        reports = (
            sorted(
                str(p.relative_to(root)) for p in (root / ".nexus" / "reports").glob("nightshift_*")
            )
            if (root / ".nexus" / "reports").is_dir()
            else []
        )
        return [
            Check("recovery_report_written", bool(reports), f"reports={reports}"),
            Check(
                "terminal_success",
                obs.outcome.get("terminal_success") is True,
                f"terminal_success={obs.outcome.get('terminal_success')}",
            ),
        ]

    return Scenario(
        statement="Nightshift pass over the README wording",
        task_type="research",
        codeintel={"nightshift_target_file": "README.md"},
        check=check,
    )


def _commit_fixture_repo(ws: Path) -> None:
    """Swarm worktrees need a git workspace: commit the copied fixture to a scratch repository."""
    git = ["git", "-c", "user.name=wiring-audit", "-c", "user.email=wiring-audit@invalid"]
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=ws, check=True)  # nosec B603 B607
    subprocess.run([*git, "add", "-A"], cwd=ws, check=True)  # nosec B603 B607
    subprocess.run([*git, "commit", "-q", "-m", "fixture"], cwd=ws, check=True)  # nosec B603 B607


SWARM_OWNER_FIXTURE_APPROVER = "owner-authorized-wiring-audit-fixture"


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def owner_fixture_integrate_swarm_winner(
    root: Path, pending: Mapping[str, Any], winner: Mapping[str, Any], state_dir: Path
) -> dict[str, Any]:
    """Owner step of the swarm fixture: approve the run's exact verified winner, then integrate.

    A swarm run can never integrate by itself: an approval binds an exact candidate commit,
    which only exists after the run.  This step plays the Owner on the audit's own fixture
    (Owner-authorized, batch 3): it persists an APPROVED lifecycle task bound to the winner
    commit/tree in a fixture-local state root, records external acceptance + a consumed
    integrate approval through ``bind_candidate_integration_closure``, and offers the winner
    again through the run's own facade call (``integrate_swarm_winner`` ->
    ``SelfHostedTaskService.integrate_approved`` -> ``ControlledIntegrationManager``).
    Labelled approver: ``SWARM_OWNER_FIXTURE_APPROVER``.  Never used outside the audit.
    """
    from datetime import timedelta

    from nexus.contracts.target_integration_lifecycle import ExternalAcceptanceReceipt
    from nexus.engine.swarm_run import integrate_swarm_winner
    from nexus.executors.cli_worker import bounded_environment_receipt
    from nexus.orchestrator.repository_contract_gate import RepositoryContractGate
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
    from nexus.orchestrator.worktree_manager import WorktreeManager

    task_id = str(pending["task_id"])
    candidate = str(pending["candidate_commit_sha"])
    base = str(pending["target_base_revision"])
    target_file = str(pending["target_file"])
    integration_branch = str(pending["integration_branch"])
    git = ["git", "-c", "user.name=wiring-audit", "-c", "user.email=wiring-audit@invalid"]
    # The canonical root must sit on the integration branch at the approved base.
    subprocess.run(  # nosec B603 B607
        [*git, "checkout", "-q", "-B", integration_branch, base], cwd=root, check=True
    )
    now = datetime.now(timezone.utc)
    verifier = str(Path(sys.executable).resolve())
    # Fixture-local lifecycle root plus a fixture git identity for the integration merge
    # commit (CI runners have no global git identity).
    fixture_env = {
        "NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR": str(state_dir),
        "GIT_AUTHOR_NAME": "wiring-audit",
        "GIT_AUTHOR_EMAIL": "wiring-audit@invalid",
        "GIT_COMMITTER_NAME": "wiring-audit",
        "GIT_COMMITTER_EMAIL": "wiring-audit@invalid",
    }
    previous_env = {key: os.environ.get(key) for key in fixture_env}
    os.environ.update(fixture_env)
    try:
        service = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False)
        request = {
            "task_id": task_id,
            "campaign_id": "wiring-audit-swarm",
            "what": "integrate the verified swarm winner",
            "why": "capability wiring audit swarm fixture",
            "controller_revision": base,
            "target_base_revision": base,
            "controller_repo_root": str(root),
            "target_repo_root": str(root.parent / f"{root.name}.target"),
            "target_worktree_root": str(root.parent),
            "allowed_files": [target_file],
            "verifier_commands": [verifier],
            "worker": "codex",
        }
        contract = service.build_contract(request)
        card = state_dir / "task-cards" / f"{task_id}.md"
        card.parent.mkdir(parents=True, exist_ok=True)
        card.write_text(
            f"# {task_id}\n\nOwner-authorized wiring-audit fixture: integrate swarm winner "
            f"{candidate} ({target_file}); verifier {pending.get('verify_script')}.\n",
            encoding="utf-8",
        )
        task_card_hash = hashlib.sha256(card.read_bytes()).hexdigest()
        gate = RepositoryContractGate(WorktreeManager(root_dir=str(root), create_root=False))
        policy_inputs = gate._policy_input_hashes(root.resolve(), base)
        verified_receipt = {
            "repository_contract_gate_passed": True,
            "repository_contract_policy_revision_hash": gate._policy_revision_hash(
                base, policy_inputs
            ),
            "verifier_evidence": [
                {
                    "command": verifier,
                    "status": "COMPLETED",
                    "exit_code": 0,
                    "executable_identity": verifier,
                    "executable_sha256": hashlib.sha256(Path(verifier).read_bytes()).hexdigest(),
                    "argv": [],
                    "env": bounded_environment_receipt({"PYTHONDONTWRITEBYTECODE": "1"}),
                    "timed_out": False,
                    "process_group_killed": False,
                }
            ],
            "swarm_verify": {
                "script": pending.get("verify_script"),
                "result": winner.get("verify_result"),
                "exit_codes": winner.get("verify_exit_codes"),
            },
        }
        packet = {
            "candidate_commit_sha": candidate,
            "candidate_tree_sha": str(pending["candidate_tree_sha"]),
            "candidate_state_hash": _sha256_json(dict(winner)),
            "verified_receipt_hash": _sha256_json(verified_receipt),
        }
        service._write_state(
            task_id,
            {
                "task_id": task_id,
                "attempt_id": "attempt-1",
                "status": "APPROVED",
                "promotion_status": "APPROVED",
                "request": request,
                "contract": contract.model_dump(mode="json"),
                "contract_kind": "TRACKED_TASK_CARD",
                "contract_hash": contract.contract_hash,
                "task_card_hash": task_card_hash,
                "candidate_ref": f"refs/nexus-candidates/{task_id}/{candidate}",
                "controller_revision": base,
                "promotion_packet": packet,
                "verified_receipt": verified_receipt,
                "approved_binding": {
                    **packet,
                    "approval_grant": {
                        "approval_scope": "ALLOW_ACTION_ONCE",
                        "approved_by": SWARM_OWNER_FIXTURE_APPROVER,
                        "consumed_at": now.isoformat(),
                    },
                },
                "lease": {
                    "lease_id": f"lease-{task_id}",
                    "target_worktree": request["target_repo_root"],
                    "target_branch": integration_branch,
                },
            },
        )
        artifact = state_dir / "acceptance-artifacts" / task_id / "swarm_verify.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps(verified_receipt["swarm_verify"]), encoding="utf-8")
        acceptance = ExternalAcceptanceReceipt(
            schema="nexus.external_acceptance_receipt.v1",
            task_id=task_id,
            attempt_id="attempt-1",
            candidate_commit=candidate,
            receipt_hash=hashlib.sha256(artifact.read_bytes()).hexdigest(),
            reviewer_id=SWARM_OWNER_FIXTURE_APPROVER,
            passed=True,
            verifier_artifact=str(artifact),
        )
        runtime = {
            "tool_manifest_hash": _sha256_json({"tool": "wiring-audit"}),
            "full_tool_schema_hash": _sha256_json({"schema": "wiring-audit"}),
            "permission_policy_hash": _sha256_json({"policy": "wiring-audit"}),
            "lifecycle_revision": "wiring-audit",
            "server_instance_id": "wiring-audit",
        }
        approval = {
            "schema": "nexus.approval.v2",
            "approval_id": f"wiring-audit-{task_id}",
            "approved_by": SWARM_OWNER_FIXTURE_APPROVER,
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=30)).isoformat(),
            "bound_task_id": task_id,
            "bound_attempt_id": "attempt-1",
            "bound_action_type": "CANDIDATE_INTEGRATE",
            "approval_scope": "ALLOW_ACTION_ONCE",
            "contract_kind": "TRACKED_TASK_CARD",
            "contract_hash": contract.contract_hash,
            "task_card_hash": task_card_hash,
            "expected_canonical_head": base,
            "integration_branch": integration_branch,
            **packet,
            "acceptance_receipt_hash": acceptance.receipt_hash,
            **runtime,
        }
        bound = service.bind_candidate_integration_closure(
            task_id,
            external_acceptance=acceptance,
            approval=approval,
            runtime_identity=runtime,
            expected_canonical_head=base,
            integration_branch=integration_branch,
        )
        integration = integrate_swarm_winner(root, task_id, dict(winner), "", base)
        final = service.get_task(task_id) or {}
    finally:
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    raw_history = final.get("status_history")
    history: list[Any] = list(raw_history) if isinstance(raw_history, list) else []
    return {
        "approver": SWARM_OWNER_FIXTURE_APPROVER,
        "bound_status": bound.get("status"),
        "integration": integration,
        "lifecycle_status": final.get("status"),
        "integration_branch": integration_branch,
        # Why a non-INTEGRATED outcome happened (status trail + failure fields).
        "status_trail": [dict(item) for item in history[-4:] if isinstance(item, dict)],
        "failure_detail": {
            key: str(value)[:300]
            for key, value in final.items()
            if any(token in key for token in ("error", "failure", "blocker", "reason"))
            and value not in (None, "", [], {})
        },
    }


def build_swarm(ws: Path, variant: str) -> Scenario:
    _commit_fixture_repo(ws)
    if variant != "positive":
        # Another task already holds calc.py: the run must stop at the lock, before any worktree.
        lock = ws / ".nexus" / "multi_agent" / "locks" / "file_locks.json"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(json.dumps({"locks": {"calc.py": "other-task"}}), encoding="utf-8")
    # Fixture-local lifecycle state root: the run's facade lookup and the Owner step read and
    # write here, never the production self-hosted state.
    state_dir = ws.parent / f"{ws.name}.self-hosted-state"

    def check(root: Path, obs: Obs) -> list[Check]:
        checks = _swarm_run_checks(root, obs)
        if variant != "positive":
            return checks
        report = (
            obs.outcome.get("swarm_report")
            if isinstance(obs.outcome.get("swarm_report"), Mapping)
            else {}
        )
        pending = report.get("pending_owner_approval")
        winner = report.get("winner") if isinstance(report.get("winner"), Mapping) else {}
        checks.append(
            Check(
                "run_stops_at_owner_approval_for_its_winner",
                obs.block_reason() == "INTEGRATION_OWNER_AUTHORITY_REQUIRED"
                or "INTEGRATION_OWNER_AUTHORITY_REQUIRED" in obs.block_reason(),
                f"block_reason={obs.block_reason()} pending={pending}",
            )
        )
        if not isinstance(pending, Mapping) or pending.get("candidate_commit_sha") != winner.get(
            "commit"
        ):
            checks.append(Check("owner_approved_winner_integrated", False, f"pending={pending}"))
            return checks
        owner = owner_fixture_integrate_swarm_winner(root, pending, winner, state_dir)
        integration = owner.get("integration") or {}
        branch = str(owner.get("integration_branch") or "")
        head = subprocess.run(  # nosec B603 B607
            ["git", "rev-parse", branch], cwd=root, capture_output=True, text=True
        ).stdout.strip()
        contains = (
            subprocess.run(  # nosec B603 B607
                ["git", "merge-base", "--is-ancestor", str(winner.get("commit")), head],
                cwd=root,
                capture_output=True,
            ).returncode
            == 0
        )
        repro = subprocess.run(  # nosec B603 B607
            [sys.executable, "repro.py"], cwd=root, capture_output=True, text=True, timeout=60
        )
        obs.outcome["owner_fixture_integration"] = owner
        checks.append(
            Check(
                "owner_approved_winner_integrated",
                integration.get("merge_performed") is True
                and owner.get("lifecycle_status") == "INTEGRATED"
                and contains
                and repro.returncode == 0,
                f"approver={owner.get('approver')} status={owner.get('lifecycle_status')} "
                f"merge={integration.get('merge_performed')} head={head[:12]} "
                f"contains_winner={contains} repro_exit={repro.returncode} "
                f"refusal={integration.get('refusal')}",
            )
        )
        return checks

    return Scenario(
        statement="Coordinate two agents on the swarm fixture: fix add in calc.py so repro.py passes",
        task_type="research",
        codeintel={
            "swarm_target_file": "calc.py",
            "swarm_verify_script": "repro.py",
            "swarm_parallelism": 2,
        },
        # Armor-on local switches of the Local stage rows (M5 endpoint); the model-call switch
        # itself stays with the policy attempts.
        extra_env={
            **{
                key: value
                for key, value in local_stage_env(ws).items()
                if key != "NEXUS_LOCAL_MODEL_CALL_ALLOWED"
            },
            "NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR": str(state_dir),
        },
        check=check,
    )


def _swarm_run_checks(root: Path, obs: Obs) -> list[Check]:
    original_hash = sha256_file(FIXTURE_ROOT / "swarm" / "calc.py")
    report = (
        obs.outcome.get("swarm_report")
        if isinstance(obs.outcome.get("swarm_report"), Mapping)
        else {}
    )
    workers = [w for w in report.get("workers") or [] if isinstance(w, Mapping)]
    commits = [str(w.get("commit") or "") for w in workers if w.get("commit")]
    commits_exist = bool(commits) and all(
        subprocess.run(  # nosec B603 B607
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=root, capture_output=True
        ).returncode
        == 0
        for sha in commits
    )
    integration = (
        report.get("integration") if isinstance(report.get("integration"), Mapping) else {}
    )
    lock = report.get("lock") if isinstance(report.get("lock"), Mapping) else {}
    return [
        Check(
            "swarm_executed_workers",
            obs.outcome.get("action") == "run_bounded_swarm"
            and int(obs.outcome.get("workers_executed") or 0) >= 2
            and int(obs.outcome.get("model_calls") or 0) >= 1,
            f"action={obs.outcome.get('action')} executed={obs.outcome.get('workers_executed')} model_calls={obs.outcome.get('model_calls')}",
        ),
        Check(
            "no_construct_only_rejection",
            obs.outcome.get("error") != "import_construct_not_execution",
            f"error={obs.outcome.get('error')}",
        ),
        Check(
            "file_lock_held_then_released",
            lock.get("held_by_this_task") is True and lock.get("released") is True,
            f"lock={dict(lock)}",
        ),
        Check(
            "worker_commits_in_object_store",
            commits_exist and len(commits) >= 2,
            f"commits={commits}",
        ),
        Check(
            "winner_verified_by_repro",
            (report.get("winner") or {}).get("verify_result") == "pass",
            f"winner={report.get('winner')} results={[w.get('verify_result') for w in workers]}",
        ),
        Check(
            "integration_offered_to_controlled_manager",
            integration.get("attempted") is True
            and "SelfHostedTaskService.integrate_approved"
            in str(integration.get("authority") or "")
            and integration.get("merge_performed") is False
            and bool(integration.get("refusal")),
            f"integration={dict(integration)}",
        ),
        Check(
            "worktrees_removed_and_workspace_untouched",
            sorted(report.get("worktrees_removed") or []) == sorted(report.get("worktrees") or [])
            and sha256_file(root / "calc.py") == original_hash,
            f"worktrees={report.get('worktrees')} removed={report.get('worktrees_removed')}",
        ),
    ]


def neg_swarm(pos: Obs, neg: Obs) -> Check:
    report = (
        neg.outcome.get("swarm_report")
        if isinstance(neg.outcome.get("swarm_report"), Mapping)
        else {}
    )
    ok = (
        "FILE_LOCK_CONFLICT" in neg.block_reason()
        and not report.get("worktrees")
        and int(neg.outcome.get("model_calls") or 0) == 0
    )
    return Check(
        "negative_control:foreign_lock_blocks_before_worktrees",
        ok,
        f"neg.block_reason={neg.block_reason()} worktrees={report.get('worktrees')} lock={report.get('lock')}",
    )


def build_drone(ws: Path, variant: str) -> Scenario:
    statement = (
        "Split the parallel work of the drone fixture"
        if variant == "positive"
        else "A completely different drone request for the negative control"
    )

    def check(root: Path, obs: Obs) -> list[Check]:
        new_files = sorted(
            str(p.relative_to(root))
            for p in root.rglob("*")
            if p.is_file() and p.name != "README.md" and ".nexus" not in p.parts
        )
        return [
            Check(
                "subtask_artifact_written", bool(new_files), f"files_besides_fixture={new_files}"
            ),
            Check(
                "action_normalized_from_task",
                _result(obs).get("normalized_action") not in (None, "", "UNKNOWN"),
                f"normalized_action={_result(obs).get('normalized_action')}",
            ),
        ]

    return Scenario(statement=statement, task_type="research", check=check)


def neg_drone(pos: Obs, neg: Obs) -> Check:
    same = _result(pos) == _result(neg)
    return Check(
        "negative_control:different_task_gives_different_result",
        not same,
        "identical drone result for different tasks" if same else "results differ",
    )


def build_ultra_review(ws: Path, variant: str) -> Scenario:
    """Positive: a benign diff the review must pass with every lane executed.

    Negative: the planted diff (``eval(input())`` plus a behaviour change that breaks
    ``tests/test_app.py``): the review must FAIL with both findings recorded; since #2732 the
    receipt is record-only (advisory_only), so it no longer fails the gate.
    """
    _git(ws, "init", "-q")
    _git(ws, "add", "app.py", "tests/test_app.py")
    _git(ws, "commit", "-q", "-m", "baseline")
    patch = "benign_patch.txt" if variant == "positive" else "planted_patch.txt"
    shutil.copyfile(ws / patch, ws / "app.py")

    def check(_ws: Path, obs: Obs) -> list[Check]:
        res = _result(obs)
        executed = list(obs.outcome.get("executed_checks") or [])
        return [
            Check(
                "diff_captured",
                int(res.get("diff_bytes") or 0) > 0,
                f"diff_bytes={res.get('diff_bytes')}",
            ),
            Check(
                "every_lane_executed_real_checks",
                {"bandit", "ruff-security", "py_compile", "ruff-correctness", "tests/test_app.py"}
                <= set(executed),
                f"executed_checks={executed}",
            ),
            Check(
                "benign_diff_passes",
                obs.gate_passed is True and res.get("review_status") == "PASS",
                f"gate={obs.gate_passed} review_status={res.get('review_status')} findings={obs.outcome.get('findings')}",
            ),
        ]

    # The forcing line names a review capability, so the planner demands Workforce role
    # independent_review; the audit binds that route's worker (still the no-model stand-in).
    return Scenario(
        statement="Review the working tree diff for unsafe calls",
        task_type="review",
        check=check,
        online_route="independent_review",
    )


def neg_ultra_review(pos: Obs, neg: Obs) -> Check:
    findings = [f for f in neg.outcome.get("findings") or [] if isinstance(f, Mapping)]
    rules = sorted({f"{f.get('lane')}:{f.get('rule_id')}" for f in findings})
    eval_flagged = any(
        r in rules for r in ("security_sentry:bandit:B307", "security_sentry:ruff:S307")
    )
    test_flagged = "ghost_regression:regression_test_failed" in rules
    # #2732: ultra_review is record-only. The planted diff must still FAIL the review and its
    # findings must be recorded, but the receipt no longer fails the gate (advisory_only).
    ok = (
        pos.gate_passed is True
        and neg.gate_passed is True
        and neg.outcome.get("advisory_only") is True
        and _result(neg).get("review_status") == "FAIL"
        and neg.outcome.get("review_passed") is False
        and eval_flagged
        and test_flagged
    )
    return Check(
        "negative_control:planted_eval_and_failing_test_recorded_as_advisory_findings",
        ok,
        f"gate pos={pos.gate_passed} neg={neg.gate_passed}; neg status={_result(neg).get('review_status')} "
        f"advisory_only={neg.outcome.get('advisory_only')} rules={rules}",
    )


def probe_ultra_review(ws: Path) -> dict[str, Any]:
    from nexus.engine.ultra_review_service import UltraReviewService

    _git(ws, "init", "-q")
    _git(ws, "add", "app.py", "tests/test_app.py")
    _git(ws, "commit", "-q", "-m", "baseline")
    shutil.copyfile(ws / "planted_patch.txt", ws / "app.py")
    with chdir(ws):
        payload = UltraReviewService(project_root=ws).run(
            dry_run=False,
            report_path=".nexus/reports/ultra_review/probe.json",
            sandbox_root=".nexus/reports/ultra_review/probe_sandboxes",
        )
    return {
        "ok": payload.get("status") == "FAIL" and payload.get("gate_passed") is False,
        "status": payload.get("status"),
        "finding_rule_ids": [f.get("rule_id") for f in payload.get("findings") or []],
        "note": "UltraReviewService.run(dry_run=False) called directly on the planted diff",
    }


def _load_candidates(ws: Path, name: str) -> list[dict[str, Any]]:
    return list(read_json(ws / name))


def build_autoreason(ws: Path, variant: str) -> Scenario:
    def check(_ws: Path, obs: Obs) -> list[Check]:
        borda = _result(obs).get("borda_scores") or {}
        ids = sorted(str(k) for k in borda)
        return [
            Check(
                "ranked_three_seeded_candidates", set(ids) == {"A", "B", "C"}, f"ranked ids={ids}"
            ),
            Check(
                "scores_not_constant",
                len(set(borda.values())) > 1 if isinstance(borda, Mapping) else False,
                f"borda={borda}",
            ),
        ]

    return Scenario(
        statement="Choose the best patch candidate for the fixture",
        task_type="repair",
        codeintel={"autoreason_candidates": _load_candidates(ws, "candidates.json")},
        check=check,
    )


def probe_autoreason(ws: Path) -> dict[str, Any]:
    from nexus.engine.autoreason_service import AutoreasonService

    result = AutoreasonService().run(
        candidates=_load_candidates(ws, "candidates.json"),
        task_desc="Choose the best patch candidate",
    )
    borda = result.get("borda_scores") or {}
    return {
        "ok": len(set(borda.values())) > 1 and result.get("winner") == "A",
        "winner": result.get("winner"),
        "borda_scores": borda,
        "judge_mode": result.get("judge_mode"),
        "note": "AutoreasonService itself ranks 3 seeded candidates deterministically; the registry executor never forwards them",
    }


def build_ddtree(ws: Path, variant: str) -> Scenario:
    def check(_ws: Path, obs: Obs) -> list[Check]:
        res = _result(obs)
        stats = res.get("tree_stats") if isinstance(res.get("tree_stats"), Mapping) else {}
        return [
            Check(
                "pruned_five_candidate_pool",
                int(stats.get("branch_count") or 0) == 5,
                f"branch_count={stats.get('branch_count')}",
            ),
            Check(
                "recorded_pruned_count_ge_2",
                int(stats.get("pruned_count") or 0) >= 2,
                f"pruned_count={stats.get('pruned_count')}",
            ),
        ]

    return Scenario(
        statement="Prune the candidate pool for the fixture",
        task_type="repair",
        codeintel={
            "ddtree_candidates": _load_candidates(ws, "candidates.json"),
            "ddtree_max_candidates": 3,
        },
        check=check,
    )


def probe_ddtree(ws: Path) -> dict[str, Any]:
    from nexus.engine.ddtree_adapter import DDTreeAdapter

    plan = DDTreeAdapter().plan(
        _load_candidates(ws, "candidates.json"), enabled=True, max_candidates=3, task_desc="prune"
    )
    stats = plan.get("tree_stats") or {}
    return {
        "ok": len(plan.get("selected_candidate_ids") or []) <= 3
        and int(stats.get("pruned_count") or 0) == 2,
        "selected_candidate_ids": plan.get("selected_candidate_ids"),
        "pruned_count": stats.get("pruned_count"),
        "note": "DDTreeAdapter prunes 5 seeded candidates to 3 when called directly; the registry executor passes one hard-coded candidate",
    }


def build_lancedb(ws: Path, variant: str) -> Scenario:
    from nexus.services.lancedb_roots import KNOWLEDGE, resolve_lancedb_root
    from nexus.services.memory_repository import MemoryRepository

    rows = read_json(ws / "policy_rows.json")
    repository = MemoryRepository(resolve_lancedb_root(KNOWLEDGE, ws, honor_env=False))
    repository.ensure_table("policy", initial_data=rows, fts_column="action")
    query = "refund window" if variant == "positive" else "zzzqqq nonexistent wiring token"

    def check(_ws: Path, obs: Obs) -> list[Check]:
        records = _result(obs).get("records") or []
        ids = [str(r.get("rule_id")) for r in records if isinstance(r, Mapping)]
        return [
            Check(
                "query_performed",
                obs.outcome.get("query_performed") is True,
                str(obs.outcome.get("query_performed")),
            ),
            Check("seeded_card_retrieved", "wiring-policy-001" in ids, f"rule_ids={ids}"),
        ]

    return Scenario(
        statement="Look up the refund window policy",
        task_type="research",
        codeintel={"search_query": query, "search_table": "policy", "search_limit": 3},
        check=check,
    )


def neg_hits(pos: Obs, neg: Obs) -> Check:
    ph, nh = int(pos.outcome.get("hit_count") or 0), int(neg.outcome.get("hit_count") or 0)
    return Check(
        "negative_control:unrelated_query_has_no_hits",
        ph >= 1 and nh == 0,
        f"hit_count pos={ph} neg={nh}",
    )


def build_memory(ws: Path, variant: str) -> Scenario:
    from nexus.core.memory_manager import ProjectMemoryManager

    manager = ProjectMemoryManager(ws)
    for item in read_json(ws / "insights.json"):
        manager.add_insight(item["topic"], item["content"], item.get("insight_type", "RCA"))
    query = "refund" if variant == "positive" else "zzzqqq-nonexistent"

    def check(_ws: Path, obs: Obs) -> list[Check]:
        return [
            Check(
                "search_performed",
                obs.outcome.get("search_performed") is True,
                str(obs.outcome.get("search_performed")),
            ),
            Check(
                "seeded_insight_retrieved",
                int(obs.outcome.get("hit_count") or 0) >= 1,
                f"hit_count={obs.outcome.get('hit_count')}",
            ),
        ]

    return Scenario(
        statement="Recall the refund window insight",
        task_type="research",
        codeintel={"memory_query": query},
        check=check,
    )


def _shard_has_artifact(root: Path, artifact_id: str) -> bool:
    shard_dir = root / ".nexus" / "tenants" / "wiring-audit"
    return any(
        artifact_id in p.read_text(encoding="utf-8", errors="replace")
        for p in shard_dir.rglob("*")
        if p.is_file()
    )


def probe_memory(ws: Path) -> dict[str, Any]:
    from nexus.core.memory_manager import ProjectMemoryManager

    manager = ProjectMemoryManager(ws)
    for item in read_json(ws / "insights.json"):
        manager.add_insight(item["topic"], item["content"], item.get("insight_type", "RCA"))
    hits = manager.search("refund")
    whole_statement = manager.search(oracle_statement("Recall the refund window insight", "memory"))
    return {
        "ok": len(hits) == 1 and not whole_statement,
        "hits_for_keyword": len(hits),
        "hits_for_full_task_statement": len(whole_statement),
        "note": "ProjectMemoryManager.search is a SQL LIKE substring; the registry executor passes the entire task statement (oracle contract included) as the pattern",
    }


def build_mempalace(ws: Path, variant: str) -> Scenario:
    artifact = read_json(
        ws / ("artifact_clean.json" if variant == "positive" else "artifact_blacklisted.json")
    )

    def check(_ws: Path, obs: Obs) -> list[Check]:
        return [
            Check(
                "ingest_performed",
                obs.outcome.get("ingest_performed") is True,
                str(obs.outcome.get("ingest_performed")),
            ),
            Check(
                "roundtrip_verified",
                obs.outcome.get("verification_passed") is True,
                str(obs.outcome.get("verification_passed")),
            ),
            Check(
                "shard_written_to_disk",
                _shard_has_artifact(_ws, artifact["artifact_id"]),
                "tenant shard .nexus/tenants/wiring-audit must contain the artifact id",
            ),
        ]

    return Scenario(
        statement="Record capability evidence in the palace",
        task_type="research",
        codeintel={
            "mempalace_tenant_id": "wiring-audit",
            "mempalace_artifact_type": "capability_evidence",
            "mempalace_artifact": artifact,
            "mempalace_query": artifact["artifact_id"],
        },
        check=check,
    )


def neg_mempalace(pos: Obs, neg: Obs) -> Check:
    ok = (
        pos.outcome.get("verification_passed") is True
        and neg.outcome.get("verification_passed") is False
        and neg.outcome.get("ingest_performed") is True
    )
    return Check(
        "negative_control:blacklisted_tool_is_blocked",
        ok,
        f"verified pos={pos.outcome.get('verification_passed')} neg={neg.outcome.get('verification_passed')}",
    )


def build_belief(ws: Path, variant: str) -> Scenario:
    from nexus.core.belief_contracts import AuditOutcome
    from nexus.core.belief_engine import BeliefEngine

    statement = "Assume the discount rule is correct"
    assumption = oracle_statement(statement, "belief")
    if variant == "positive":
        engine = BeliefEngine(state_file=ws / ".nexus" / "belief_state.json")
        engine.process_audit_outcome(
            AuditOutcome(
                task_id="wiring-seed",
                assumption=assumption,
                passed=False,
                evidence_id="ev_wiring_seed_failure",
                reason="seeded failed outcome",
            )
        )

    def check(_ws: Path, obs: Obs) -> list[Check]:
        confidence = obs.outcome.get("confidence")
        return [
            Check(
                "belief_store_read",
                obs.outcome.get("physical_callable", "").endswith("assess_confidence"),
                str(obs.outcome.get("physical_callable")),
            ),
            Check(
                "confidence_lowered_by_seeded_failure",
                isinstance(confidence, (int, float)) and confidence < 0.5,
                f"confidence={confidence} (unseeded default is 0.7)",
            ),
        ]

    return Scenario(statement=statement, task_type="research", check=check)


def neg_belief(pos: Obs, neg: Obs) -> Check:
    pc, nc = pos.outcome.get("confidence"), neg.outcome.get("confidence")
    return Check(
        "negative_control:unseeded_belief_keeps_default",
        pc != nc,
        f"confidence seeded={pc} unseeded={nc}",
    )


def _gate_scenario(ws: Path, variant: str, statement: str) -> Scenario:
    command = (
        (PY, "verify.py")
        if variant == "positive"
        else (PY, "-c", "assert False, 'wiring negative control'")
    )
    return Scenario(statement=statement, task_type="code_change", verifier_command=command)


def build_gate(cap: str) -> Builder:
    def build(ws: Path, variant: str) -> Scenario:
        scen = _gate_scenario(ws, variant, "Verify gates_target after the change")

        def check(_ws: Path, obs: Obs) -> list[Check]:
            out = obs.outcome
            proof = out.get("proof") if isinstance(out.get("proof"), Mapping) else {}
            checks = [
                Check(
                    "verifier_really_ran",
                    "wiring-gates-verifier-pass" in _verifier_stdout(obs),
                    f"verifier stdout={_verifier_stdout(obs)[:80]!r}",
                ),
                Check(
                    "verifier_artifact_is_sha256",
                    str(proof.get("verifier_artifact") or "").startswith("sha256:"),
                    str(proof.get("verifier_artifact"))[:30],
                ),
                Check(
                    "source_hash_bound_to_verifier",
                    bool(proof.get("source_hash"))
                    and proof.get("source_hash") == proof.get("verifier_source_hash"),
                    f"source={str(proof.get('source_hash'))[:12]} verifier={str(proof.get('verifier_source_hash'))[:12]}",
                ),
            ]
            if cap in {"claim_gate", "delivery_gate"}:
                checks.append(
                    Check(
                        "gate_decision_pass",
                        out.get("status") == "PASS" and not out.get("blockers"),
                        f"status={out.get('status')} blockers={out.get('blockers')}",
                    )
                )
            else:
                checks.append(
                    Check(
                        "gate_decision_pass",
                        out.get("status") == "PASS" and not out.get("blockers"),
                        f"status={out.get('status')} blockers={out.get('blockers')}",
                    )
                )
            return checks

        scen.check = check
        return scen

    return build


def neg_gate(pos: Obs, neg: Obs) -> Check:
    blockers = (
        (neg.outcome.get("blockers") or []) if isinstance(neg.outcome.get("blockers"), list) else []
    )
    ok = pos.gate_passed and not neg.gate_passed and bool(blockers)
    return Check(
        "negative_control:failing_verifier_blocks_gate",
        ok,
        f"pos.gate={pos.gate_passed} neg.gate={neg.gate_passed} neg.blockers={blockers[:3]}",
    )


def build_acceptance(ws: Path, variant: str) -> Scenario:
    scen = _gate_scenario(ws, variant, "Verify gates_target for acceptance")

    def check(_ws: Path, obs: Obs) -> list[Check]:
        return [
            Check(
                "verifier_really_ran",
                "wiring-gates-verifier-pass" in _verifier_stdout(obs),
                f"verifier stdout={_verifier_stdout(obs)[:80]!r}",
            ),
            Check(
                "acceptance_passed",
                obs.outcome.get("passed") is True,
                f"passed={obs.outcome.get('passed')} missing={obs.outcome.get('missing_evidence')}",
            ),
            Check(
                "verifier_artifact_carried",
                str(obs.outcome.get("verifier_artifact") or "").startswith("sha256:"),
                str(obs.outcome.get("verifier_artifact"))[:30],
            ),
        ]

    scen.check = check
    return scen


def neg_acceptance(pos: Obs, neg: Obs) -> Check:
    ok = (
        pos.outcome.get("passed") is True
        and neg.outcome.get("passed") is False
        and bool(neg.outcome.get("missing_evidence"))
    )
    return Check(
        "negative_control:failing_verifier_rejects_acceptance",
        ok,
        f"pos.passed={pos.outcome.get('passed')} neg.passed={neg.outcome.get('passed')} neg.missing={neg.outcome.get('missing_evidence')}",
    )


def build_pregate(ws: Path, variant: str) -> Scenario:
    commands = [f"{PY} target.py"] if variant == "positive" else [f"{PY} -c 'raise SystemExit(3)'"]

    def check(_ws: Path, obs: Obs) -> list[Check]:
        results = obs.outcome.get("results") or []
        return [
            Check(
                "command_ran",
                int(obs.outcome.get("command_count") or 0) == 1,
                f"command_count={obs.outcome.get('command_count')}",
            ),
            Check(
                "all_passed",
                obs.outcome.get("all_passed") is True,
                f"all_passed={obs.outcome.get('all_passed')}",
            ),
            Check("per_command_result_recorded", bool(results), f"results={str(results)[:120]}"),
        ]

    return Scenario(
        statement="Run the pregate verify commands",
        task_type="code_change",
        codeintel={"verify_commands": commands, "verify_timeout_sec": 30},
        check=check,
    )


def neg_pregate(pos: Obs, neg: Obs) -> Check:
    ok = pos.outcome.get("all_passed") is True and neg.outcome.get("all_passed") is False
    return Check(
        "negative_control:failing_command_fails_gate",
        ok,
        f"all_passed pos={pos.outcome.get('all_passed')} neg={neg.outcome.get('all_passed')}",
    )


def build_forecast(ws: Path, variant: str) -> Scenario:
    tasks = read_json(ws / "tasks.json")
    feed = tasks["high_risk"] if variant == "positive" else tasks["low_risk"]

    def check(root: Path, obs: Obs) -> list[Check]:
        res = _result(obs)
        state_path = Path(str(obs.outcome.get("state_path") or ""))
        return [
            Check(
                "high_risk_task_rejected",
                res.get("proceed") is False,
                f"proceed={res.get('proceed')} reason={res.get('reason')}",
            ),
            Check(
                "rejection_persisted_with_ash_strategy",
                bool(obs.outcome.get("ash_strategy"))
                and obs.outcome.get("state_persisted") is True,
                f"ash={obs.outcome.get('ash_strategy')} persisted={obs.outcome.get('state_persisted')}",
            ),
            Check("state_file_on_disk", state_path.is_file(), str(state_path)),
        ]

    return Scenario(
        statement="Forecast the risk of rewriting the whole billing module",
        task_type="research",
        codeintel=dict(feed),
        check=check,
    )


def neg_forecast(pos: Obs, neg: Obs) -> Check:
    ok = _result(pos).get("proceed") is False and _result(neg).get("proceed") is True
    return Check(
        "negative_control:low_risk_task_proceeds",
        ok,
        f"proceed pos={_result(pos).get('proceed')} neg={_result(neg).get('proceed')}",
    )


def build_plan_quality(ws: Path, variant: str) -> Scenario:
    plan = read_json(ws / "plan.json")
    if variant != "positive":
        plan["impact_map"] = {}

    def check(_ws: Path, obs: Obs) -> list[Check]:
        return [
            Check(
                "inputs_present",
                obs.outcome.get("input_fields_present") is True,
                str(obs.outcome.get("input_fields_present")),
            ),
            Check(
                "impact_map_evaluated",
                obs.outcome.get("impact_map_evaluated") is True,
                str(obs.outcome.get("impact_map_evaluated")),
            ),
            Check(
                "plan_passed",
                obs.outcome.get("passed") is True,
                f"passed={obs.outcome.get('passed')} result={_result(obs)}",
            ),
        ]

    return Scenario(
        statement="Check the plan quality of the compute_total patch",
        task_type="code_change",
        codeintel=plan,
        check=check,
    )


def neg_plan_quality(pos: Obs, neg: Obs) -> Check:
    ok = (
        pos.gate_passed
        and not neg.gate_passed
        and "PLAN_QUALITY_CONTEXT_REQUIRED" in neg.block_reason()
    )
    return Check(
        "negative_control:empty_impact_map_blocks", ok, f"neg.block_reason={neg.block_reason()}"
    )


def build_sandbox(ws: Path, variant: str) -> Scenario:
    command = [PY, "probe.py"] if variant == "positive" else [PY, "-c", "raise SystemExit(3)"]

    def check(root: Path, obs: Obs) -> list[Check]:
        run_id = str(_result(obs).get("run_id") or "")
        report = root / ".nexus" / "sandbox" / "runs" / run_id / "sandbox_result.json"
        payload = read_json(report) if report.is_file() else {}
        return [
            Check(
                "sandbox_executed",
                obs.outcome.get("sandbox_executed") is True,
                str(obs.outcome.get("sandbox_executed")),
            ),
            Check(
                "workspace_isolated_copy",
                obs.outcome.get("workspace_isolated") is True
                and str(payload.get("effective_cwd") or "") != str(root),
                f"effective_cwd={str(payload.get('effective_cwd'))[-60:]}",
            ),
            Check(
                "exit_code_zero",
                obs.outcome.get("exit_code") == 0,
                f"exit_code={obs.outcome.get('exit_code')}",
            ),
            Check(
                "stdout_token_in_result_file",
                "wiring-sandbox-stdout-token" in str(payload.get("stdout") or ""),
                f"sandbox_result.json stdout={payload.get('stdout')!r}",
            ),
        ]

    return Scenario(
        statement="Run the probe script in the sandbox",
        task_type="code_change",
        codeintel={"sandbox_command": command, "sandbox_timeout_sec": 30},
        check=check,
    )


def neg_sandbox(pos: Obs, neg: Obs) -> Check:
    ok = pos.outcome.get("exit_code") == 0 and neg.outcome.get("exit_code") == 3
    return Check(
        "negative_control:failing_command_reports_exit_3",
        ok,
        f"exit pos={pos.outcome.get('exit_code')} neg={neg.outcome.get('exit_code')}",
    )


def build_harness_sensor(ws: Path, variant: str) -> Scenario:
    commands = [f"{PY} target.py"] if variant == "positive" else []

    def check(_ws: Path, obs: Obs) -> list[Check]:
        selected = obs.outcome.get("selected_capabilities")
        return [
            Check(
                "sensor_schema_emitted",
                obs.outcome.get("schema_version") == "nexus_harness_preflight_sensor.v1",
                str(obs.outcome.get("schema_version")),
            ),
            Check(
                "sensor_saw_planned_selection",
                bool(selected),
                f"selected_capabilities={selected} pending={obs.outcome.get('pending_capabilities')}",
            ),
        ]

    return Scenario(
        statement="Check harness readiness before the patch",
        task_type="repair",
        codeintel={"verify_commands": commands, "verify_timeout_sec": 30},
        check=check,
    )


def neg_harness_sensor(pos: Obs, neg: Obs) -> Check:
    ok = (
        pos.gate_passed
        and not neg.gate_passed
        and "VERIFY_COMMAND_WIRING_REQUIRED" in neg.block_reason()
    )
    return Check(
        "negative_control:no_verify_commands_blocks", ok, f"neg.block_reason={neg.block_reason()}"
    )


def build_committee(ws: Path, variant: str) -> Scenario:
    # Proposals name their proposer "proposer_id" (the canonical context seam rejects any
    # "model" key). Each candidate patch is applied to its own workspace copy and judged by
    # running repro.py there; only candidate-a (a + b) passes, so the committee must pick it.
    proposals = read_json(ws / "proposals.json")
    if variant != "positive":
        proposals = proposals[:1]
    original_hash = sha256_file(ws / "calc.py")

    def check(root: Path, obs: Obs) -> list[Check]:
        results = [r for r in obs.outcome.get("execution_results") or [] if isinstance(r, Mapping)]
        worlds = [Path(str(r.get("workspace") or "")) for r in results]
        return [
            Check(
                "quorum_of_candidates",
                int(obs.outcome.get("candidate_count") or 0) >= 2,
                f"candidate_count={obs.outcome.get('candidate_count')}",
            ),
            Check(
                "verdicts_recorded",
                int(obs.outcome.get("verdict_count") or 0) >= 1,
                f"verdict_count={obs.outcome.get('verdict_count')}",
            ),
            Check(
                "winner_or_abstain",
                bool(obs.outcome.get("winner_id")) or obs.outcome.get("explicit_abstain") is True,
                f"winner={obs.outcome.get('winner_id')} abstain={obs.outcome.get('explicit_abstain')}",
            ),
            Check(
                "each_candidate_executed_in_own_copy",
                len(results) >= 2
                and all(r.get("apply_status") == "applied" for r in results)
                and all(w.is_dir() and w.is_relative_to(root) for w in worlds),
                f"apply={[r.get('apply_status') for r in results]} exit_codes={[r.get('exit_codes') for r in results]}",
            ),
            Check(
                "winner_is_the_only_passing_candidate",
                obs.outcome.get("winner_proposer_id") == "wiring-proposer-a"
                and [r.get("verify_result") for r in results] == ["pass", "fail", "fail"],
                f"winner_proposer={obs.outcome.get('winner_proposer_id')} results={[r.get('verify_result') for r in results]}",
            ),
            Check(
                "workspace_untouched",
                sha256_file(root / "calc.py") == original_hash,
                "calc.py hash unchanged",
            ),
        ]

    return Scenario(
        statement="Pick between three independent candidate patches",
        task_type="repair",
        codeintel={
            "committee_proposals": proposals,
            "committee_verify_commands": ["python3 repro.py"],
        },
        check=check,
    )


def neg_committee(pos: Obs, neg: Obs) -> Check:
    ok = (
        pos.gate_passed
        and not neg.gate_passed
        and "TWO_INDEPENDENT_CANDIDATES_REQUIRED" in neg.block_reason()
    )
    return Check(
        "negative_control:single_candidate_blocks", ok, f"neg.block_reason={neg.block_reason()}"
    )


def build_xray(ws: Path, variant: str) -> Scenario:
    if variant != "positive":
        (ws / "nexus" / "services" / "capability_registry.py").unlink()

    def check(root: Path, obs: Obs) -> list[Check]:
        reports = sorted(root.glob(".nexus/runtime/*/xray_report_full.md"))
        text = reports[0].read_text(encoding="utf-8", errors="replace") if reports else ""
        return [
            Check(
                "xray_report_on_disk",
                bool(reports),
                f"reports={[str(r.relative_to(root)) for r in reports]}",
            ),
            Check(
                "report_lists_fixture_symbols",
                "registry_alpha" in text,
                f"report bytes={len(text)}",
            ),
        ]

    return Scenario(
        statement="Deep scan the dependency graph of the xray fixture",
        task_type="research",
        codeintel={"xray_targets": ["nexus/services/capability_registry.py"]},
        check=check,
    )


def neg_xray(pos: Obs, neg: Obs) -> Check:
    ok = pos.gate_passed and not neg.gate_passed
    return Check(
        "negative_control:missing_hard_coded_target_fails",
        ok,
        f"gate pos={pos.gate_passed} neg={neg.gate_passed} (only the hard-coded nexus/services/capability_registry.py matters)",
    )


def build_metabolism(ws: Path, variant: str) -> Scenario:
    usage = 110000 if variant == "positive" else 1000

    def check(root: Path, obs: Obs) -> list[Check]:
        res = _result(obs)
        stack, seed = (
            root / ".nexus" / "metabolism" / "task_stack.json",
            root / ".nexus" / "metabolism" / "session_seed.json",
        )
        return [
            Check("checkpoint_on_disk", stack.is_file(), str(stack)),
            Check(
                "seed_on_disk_hash_matches",
                seed.is_file() and sha256_file(seed) == res.get("seed_hash"),
                f"seed_hash={str(res.get('seed_hash'))[:12]}",
            ),
            Check(
                "threshold_crossed",
                res.get("threshold_crossed") is True,
                f"threshold_crossed={res.get('threshold_crossed')}",
            ),
        ]

    return Scenario(
        statement="Resume the long session after distillation",
        task_type="research",
        codeintel={"metabolism_token_usage": usage, "metabolism_token_limit": TOKEN_CEILING},
        check=check,
    )


def neg_metabolism(pos: Obs, neg: Obs) -> Check:
    ok = (
        pos.gate_passed
        and not neg.gate_passed
        and "TOKEN_THRESHOLD_NOT_REACHED" in neg.block_reason()
    )
    return Check(
        "negative_control:low_usage_skips_distillation",
        ok,
        f"neg.block_reason={neg.block_reason()}",
    )


def build_meta_opt(ws: Path, variant: str) -> Scenario:
    episode = read_json(ws / "episode.json") if variant == "positive" else None
    codeintel: dict[str, Any] = {"meta_opt_episode": episode} if episode else {}

    def check(root: Path, obs: Obs) -> list[Check]:
        return [
            Check(
                "episode_persisted",
                obs.outcome.get("episode_persisted") is True,
                str(obs.outcome.get("episode_persisted")),
            ),
            Check(
                "policy_persisted",
                obs.outcome.get("policy_persisted") is True,
                str(obs.outcome.get("policy_persisted")),
            ),
            Check(
                "autotune_pass",
                obs.outcome.get("autotune_status") == "PASS",
                str(obs.outcome.get("autotune_status")),
            ),
        ]

    return Scenario(
        statement="Tune the routing policy from the seeded episode",
        task_type="research",
        codeintel=codeintel,
        check=check,
    )


def neg_meta_opt(pos: Obs, neg: Obs) -> Check:
    ok = (
        pos.gate_passed
        and not neg.gate_passed
        and "REAL_OUTCOME_EPISODE_REQUIRED" in neg.block_reason()
    )
    return Check("negative_control:no_episode_blocks", ok, f"neg.block_reason={neg.block_reason()}")


def resolve_local_worker(model: str) -> dict[str, Any] | None:
    """Workforce-admitted ollama worker for ``model`` (same resolution the A/B armor lane uses)."""
    from nexus.services.model_workforce_policy import WorkforcePolicyLoader

    workers = WorkforcePolicyLoader().load().workers
    for worker in workers.values():
        if (
            worker.provider == "ollama"
            and worker.model == model
            and "bounded_code_candidate" in worker.roles
            and worker.availability == "AVAILABLE"
        ):
            return {"worker_id": worker.worker_id, "controls": list(worker.requires)}
    return None


def local_stage_env(ws: Path) -> dict[str, str]:
    """Armor-on switches the A/B lane sets in ``armor_environment`` (local-only, M5 endpoint)."""
    return {
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR": "1",
        "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY": "localheal_pipeline",
        "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER": "ollama",
        "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL": AUDIT_MODEL,
        "NEXUS_LOCAL_MODEL_NAME": AUDIT_MODEL,
        "NEXUS_ARMOR_ARTIFACT_ROOT": str(ws / ".armor"),
        "NEXUS_ARMOR_ALLOW_EPHEMERAL": "1",
        "NEXUS_FORCE_FULL_ARMOR": "1",
    }


def build_local_stage(cap: str) -> Builder:
    def build(ws: Path, variant: str) -> Scenario | None:
        if variant != "positive":
            return None
        worker = resolve_local_worker(AUDIT_MODEL)
        statement = "Repair calc.py: add(a, b) subtracts instead of adding; change `a - b` to `a + b` so add returns the sum of its two arguments"
        original_hash = sha256_file(ws / "calc.py")

        def factory(task_id: str) -> Any:
            from nexus.services.local_assist_service import (
                REQUEST_SCHEMA,
                LocalAssistRequest,
                build_planner_snapshot,
            )

            snapshot = build_planner_snapshot(
                task_statement=statement, model=AUDIT_MODEL, topology="localheal_pipeline"
            )
            snapshot.update({
                "model_call_allowed": True,
                "mutation_allowed": True,
                "verifier_allowed": True,
            })
            return LocalAssistRequest(
                schema=REQUEST_SCHEMA,
                task_id=task_id,
                parent_task_id=task_id,
                workspace_root=str(ws),
                workspace_revision="wiring-audit-rev",
                task_statement=statement,
                action="verified-subtask",
                allowed_files=("calc.py",),
                target_file="calc.py",
                target_symbol="add",
                evidence_refs=(f"wiring-audit:{task_id}:request",),
                verifier_command=(PY, "repro.py"),
                time_budget=240.0,
                requested_role="candidate",
                planner_snapshot=snapshot,
            )

        def check(root: Path, obs: Obs) -> list[Check]:
            local_stage = (
                obs.receipt.get("local") if isinstance(obs.receipt.get("local"), Mapping) else {}
            )
            lineage = (
                local_stage.get("formal_local_runtime_lineage")
                if isinstance(local_stage.get("formal_local_runtime_lineage"), Mapping)
                else {}
            )
            exec_receipt: dict[str, Any] = {}
            receipt_path = Path(str(lineage.get("receipt_path") or ""))
            if receipt_path.is_file():
                exec_receipt = read_json(receipt_path)
            ledger = [
                item
                for item in exec_receipt.get("provider_call_ledger") or []
                if isinstance(item, Mapping)
            ]
            worlds = (
                sorted((root / ".armor" / "workspaces").glob("*/calc.py"))
                if (root / ".armor" / "workspaces").is_dir()
                else []
            )
            edited = any(sha256_file(path) != original_hash for path in worlds)
            checks = [
                Check(
                    "executor_invoked",
                    lineage.get("executor_invoked") is True,
                    f"executor_invoked={lineage.get('executor_invoked')}",
                ),
                Check(
                    "model_really_called",
                    lineage.get("local_model_invoked") is True
                    and int(lineage.get("model_call_count") or 0) >= 1,
                    f"local_model_invoked={lineage.get('local_model_invoked')} model_call_count={lineage.get('model_call_count')}",
                ),
                Check(
                    "provider_ledger_has_ollama_metrics_for_audit_model",
                    any(
                        item.get("resolved_model") == AUDIT_MODEL
                        and int(item.get("ollama_eval_count") or 0) > 0
                        for item in ledger
                    ),
                    f"ledger phases={[item.get('phase') for item in ledger]}",
                ),
                Check(
                    "candidate_edit_materialized_in_isolated_world",
                    edited,
                    f"world-C calc.py files={[str(p.relative_to(root)) for p in worlds]}",
                ),
                Check(
                    "candidate_delivered_to_runtime",
                    lineage.get("output_delivered") is True,
                    f"output_delivered={lineage.get('output_delivered')} blockers={lineage.get('blockers')}",
                ),
                Check(
                    "source_file_untouched_by_isolated_apply",
                    sha256_file(root / "calc.py") == original_hash,
                    "calc.py hash unchanged",
                ),
            ]
            if cap == "repair_loop":
                checks.append(
                    Check(
                        "verifier_passed_on_candidate",
                        str(lineage.get("verifier_status") or "").lower() == "pass",
                        f"verifier_status={lineage.get('verifier_status')}",
                    )
                )
            return checks

        return Scenario(
            statement=statement,
            task_type="repair",
            route_features={
                "deterministic_verifier_available": True,
                "memory_hits": 0,
                "findings_hits": 0,
            },
            local_enabled=True,
            online_enabled=False,
            local_worker=worker,
            local_request_factory=factory,
            extra_env=local_stage_env(ws),
            # Local-only armored execution is World C (local_armor), as the A/B armor lane
            # declares. The World C receipt validator rejects any other world.
            canonical_context={"execution_world": "local_armor"},
            check=check,
        )

    return build


# ------------------------------------------------- 2026-10-13 extension: the other planner nodes


def _plain_scenario(statement: str, **kwargs: Any) -> Scenario:
    return Scenario(statement=statement, **kwargs)


def _seed_into(ws: Path, name: str, relative: str) -> None:
    dest = ws / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ws / name, dest)


def build_semantic_failure_sensor(ws: Path, variant: str) -> Scenario:
    # The seeded lesson shares tokens only with the positive statement; the executor reads the
    # lesson store .nexus/knowledge/lesson_events.jsonl under the cwd (= workspace).
    _seed_into(ws, "lesson_events.jsonl", ".nexus/knowledge/lesson_events.jsonl")
    statement = (
        "Fix ZeroDivisionError from compute_total on empty_cart"
        if variant == "positive"
        else "Rename logging helper inside utils"
    )

    def check(_ws: Path, obs: Obs) -> list[Check]:
        res = _result(obs)
        return [
            Check(
                "seeded_lesson_found",
                int(res.get("hit_count") or 0) >= 1,
                f"hit_count={res.get('hit_count')} top_hit_type={res.get('top_hit_type')}",
            )
        ]

    return Scenario(statement=statement, task_type="repair", check=check)


def neg_semantic_failure_sensor(pos: Obs, neg: Obs) -> Check:
    ph = int(_result(pos).get("hit_count") or 0)
    nh = int(_result(neg).get("hit_count") or 0)
    return Check(
        "negative_control:unrelated_failure_has_no_similar_bug",
        ph >= 1 and nh == 0,
        f"hit_count pos={ph} neg={nh}",
    )


def build_bdd_acceptance(ws: Path, variant: str) -> Scenario:
    scen = _gate_scenario(ws, variant, "Verify gates_target for the acceptance scenario")

    def check(_ws: Path, obs: Obs) -> list[Check]:
        res = _result(obs)
        return [
            Check(
                "verifier_really_ran",
                "wiring-gates-verifier-pass" in _verifier_stdout(obs),
                f"verifier stdout={_verifier_stdout(obs)[:80]!r}",
            ),
            Check(
                "delegated_acceptance_passed",
                res.get("acceptance_gate_passed") is True,
                f"result={res}",
            ),
        ]

    scen.check = check
    return scen


def neg_bdd_acceptance(pos: Obs, neg: Obs) -> Check:
    ok = (
        _result(pos).get("acceptance_gate_passed") is True
        and _result(neg).get("acceptance_gate_passed") is False
    )
    return Check(
        "negative_control:failing_verifier_rejects_acceptance",
        ok,
        f"pos={_result(pos).get('acceptance_gate_passed')} neg={_result(neg).get('acceptance_gate_passed')}",
    )


def build_jit(ws: Path, variant: str) -> Scenario:
    tools = read_json(ws / "tools.json")
    # "測試" is the keyword JITToolInjector.apply_mask looks for (test/read tools only).
    statement = "測試 target.py after the change"
    usage = 1200 if variant == "positive" else 20000

    def check(_ws: Path, obs: Obs) -> list[Check]:
        res = _result(obs)
        selected = list(res.get("selected_tools") or [])
        return [
            Check(
                "mask_narrowed_to_test_and_read_tools",
                bool(selected) and all(("test" in t or "read" in t) for t in selected),
                f"selected={selected}",
            ),
            Check(
                "quota_checked_and_passed",
                obs.outcome.get("quota_checked") is True
                and obs.outcome.get("quota_passed") is True,
                f"quota_passed={obs.outcome.get('quota_passed')} usage={res.get('token_usage')}",
            ),
            Check(
                "receipt_declares_simulated_mask",
                obs.outcome.get("simulated") is True
                and (obs.outcome.get("claim_boundary") or {}).get("claim") == "SIMULATED",
                f"simulated={obs.outcome.get('simulated')} mask_kind={obs.outcome.get('mask_kind')}",
            ),
        ]

    return Scenario(
        statement=statement,
        task_type="code_change",
        codeintel={"jit_all_tools": tools, "jit_token_usage": usage},
        check=check,
    )


def neg_jit(pos: Obs, neg: Obs) -> Check:
    ok = pos.gate_passed and not neg.gate_passed and neg.outcome.get("quota_passed") is False
    return Check(
        "negative_control:over_quota_usage_fails_gate",
        ok,
        f"pos.gate={pos.gate_passed} neg.gate={neg.gate_passed} neg.quota={neg.outcome.get('quota_passed')}",
    )


def probe_jit(ws: Path) -> dict[str, Any]:
    from nexus.core.jit_tool_injector import JITToolInjector

    tools = read_json(ws / "tools.json")
    return {
        "english_goal_mask": JITToolInjector.apply_mask("Run the tests for target.py", tools),
        "chinese_test_goal_mask": JITToolInjector.apply_mask("測試 target.py", tools),
        "note": "apply_mask matches only the Chinese keywords 測試/核驗/具現/修復; any other goal gets all_tools[:5]",
    }


def build_semantic_searcher(ws: Path, variant: str) -> Scenario:
    from nexus.services.lancedb_roots import KNOWLEDGE, resolve_lancedb_root
    from nexus.services.memory_repository import MemoryRepository

    rows = read_json(ws / "policy_rows.json")
    repository = MemoryRepository(resolve_lancedb_root(KNOWLEDGE, ws, honor_env=False))
    repository.ensure_table("policy", initial_data=rows, fts_column="action")
    query = "refund window" if variant == "positive" else "zzzqqq nonexistent wiring token"

    def check(_ws: Path, obs: Obs) -> list[Check]:
        hits = _result(obs).get("hits") or []
        ids = [str(h.get("id")) for h in hits if isinstance(h, Mapping)]
        return [
            Check(
                "search_performed",
                obs.outcome.get("search_performed") is True,
                str(obs.outcome.get("search_performed")),
            ),
            Check("seeded_card_retrieved", "wiring-policy-001" in ids, f"ids={ids}"),
        ]

    return Scenario(
        statement="Look up the refund window policy",
        task_type="research",
        codeintel={"search_query": query, "search_table": "policy", "search_limit": 3},
        check=check,
    )


def _online_seen(ws: Path) -> dict[str, Any]:
    path = ws / ONLINE_SEEN_FILE
    return read_json(path) if path.is_file() else {}


def build_prompt_compression(ws: Path, variant: str) -> Scenario:
    filler = " ".join(f"step{i} keeps the ledger balanced" for i in range(400))
    statement = (
        f"Update target.py so the ledger stays balanced. Notes: {filler}"
        if variant == "positive"
        else "Update target.py so the ledger stays balanced."
    )

    def check(root: Path, obs: Obs) -> list[Check]:
        resp = obs.outcome
        seen = _online_seen(root)
        return [
            Check(
                "context_truncated_to_budget",
                resp.get("truncated") is True
                and int(resp.get("compressed_context_chars") or 0) <= 4096,
                f"original={resp.get('original_context_chars')} compressed={resp.get('compressed_context_chars')}",
            ),
            Check(
                "online_channel_received_compressed_prompt",
                seen.get("capability_context_compressed") is True
                and bool(resp.get("compressed_context"))
                and str(resp.get("compressed_context")) in str(seen.get("online_prompt") or ""),
                f"online_seen={ {k: seen.get(k) for k in ('online_prompt_chars', 'capability_context_compressed')} } compressed_context_embedded={str(resp.get('compressed_context') or '') in str(seen.get('online_prompt') or '')}",
            ),
            Check(
                "online_prompt_shorter_than_statement",
                0 < int(seen.get("online_prompt_chars") or 0) < len(statement),
                f"online_prompt_chars={seen.get('online_prompt_chars')} statement_chars={len(statement)}",
            ),
        ]

    return Scenario(statement=statement, task_type="code_change", check=check)


def _compressed_prompt_chars(obs: Obs) -> int:
    with contextlib.suppress(TypeError, ValueError):
        return len(
            str(json.loads(str(obs.outcome.get("compressed_context") or "{}")).get("prompt"))
        )
    return -1


def neg_prompt_compression(pos: Obs, neg: Obs) -> Check:
    """The compressed context must follow the input (a different prompt, a different result)."""
    ok = pos.outcome.get("compressed_context") != neg.outcome.get("compressed_context") and int(
        pos.outcome.get("original_context_chars") or 0
    ) > int(neg.outcome.get("original_context_chars") or 0)
    return Check(
        "negative_control:short_prompt_gives_different_context",
        ok,
        f"original pos={pos.outcome.get('original_context_chars')} neg={neg.outcome.get('original_context_chars')}; "
        f"compressed pos={pos.outcome.get('compressed_context_chars')} neg={neg.outcome.get('compressed_context_chars')} "
        f"(neg truncated={neg.outcome.get('truncated')}, neg prompt kept={_compressed_prompt_chars(neg)} chars)",
    )


def build_asi(ws: Path, variant: str) -> Scenario:
    records = read_json(ws / "records.json")[variant]

    def check(_ws: Path, obs: Obs) -> list[Check]:
        res = _result(obs)
        constraints = [c for c in res.get("constraints") or [] if isinstance(c, Mapping)]
        return [
            Check(
                "one_constraint_for_repeated_family",
                int(obs.outcome.get("constraints_count") or 0) == 1
                and bool(constraints)
                and constraints[0].get("blocked_pattern") == "retry_wrapper",
                f"constraints_count={obs.outcome.get('constraints_count')} first={constraints[:1]}",
            ),
            Check(
                "evidence_refs_come_from_seeded_records",
                sorted(obs.outcome.get("extracted_evidence_refs") or [])
                == ["asi:run-1:retry", "asi:run-2:retry"],
                f"extracted={obs.outcome.get('extracted_evidence_refs')}",
            ),
        ]

    return Scenario(
        statement="Extract constraints from the discarded retry attempts",
        task_type="research",
        codeintel={"asi_failure_records": records},
        check=check,
    )


def neg_asi(pos: Obs, neg: Obs) -> Check:
    ok = (
        pos.gate_passed
        and not neg.gate_passed
        and int(neg.outcome.get("constraints_count") or 0) == 0
    )
    return Check(
        "negative_control:distinct_families_yield_no_constraint",
        ok,
        f"pos.gate={pos.gate_passed} neg.gate={neg.gate_passed} neg.count={neg.outcome.get('constraints_count')}",
    )


def build_architecture_scout(ws: Path, variant: str) -> Scenario:
    records = read_json(ws / "records.json")[variant]
    statement = "Plan a seam for the flaky retry timeout in the billing module"

    def check(_ws: Path, obs: Obs) -> list[Check]:
        res = _result(obs)
        out = obs.outcome
        return [
            Check(
                "plateau_detected_from_seeded_ledger",
                out.get("plateau_detected") is True,
                f"plateau_detected={out.get('plateau_detected')} error={out.get('error')}",
            ),
            Check(
                "scout_plan_ready",
                res.get("status") == "READY" and bool(res.get("recommended_family")),
                f"status={res.get('status')} reason={res.get('reason')} family={res.get('recommended_family')}",
            ),
            Check(
                "forbidden_family_is_plateau_family",
                list(res.get("forbidden_families") or []) == ["flow:retry_wrapper"],
                f"forbidden_families={res.get('forbidden_families')}",
            ),
        ]

    # The forcing line contains the node name, and "architecture" is a complex-task keyword, so
    # the planner demands role main_engineering; the audit binds that route's worker.
    return Scenario(
        statement=statement,
        task_type="research",
        codeintel={"asi_failure_records": records},
        check=check,
        online_route="main_engineering",
    )


def neg_architecture_scout(pos: Obs, neg: Obs) -> Check:
    ok = (
        pos.gate_passed
        and not neg.gate_passed
        and neg.outcome.get("plateau_detected") is False
        and str(neg.outcome.get("error") or "").startswith("PLATEAU_NOT_DETECTED")
    )
    return Check(
        "negative_control:mixed_ledger_has_no_plateau",
        ok,
        f"pos.gate={pos.gate_passed} neg.gate={neg.gate_passed} neg.error={neg.outcome.get('error')}",
    )


def neg_status_changes(field_name: str) -> Callable[[Obs, Obs], Check]:
    def neg(pos: Obs, neg_obs: Obs) -> Check:
        pv, nv = _result(pos).get(field_name), _result(neg_obs).get(field_name)
        return Check(
            f"negative_control:different_task_changes_{field_name}",
            pv != nv,
            f"{field_name} pos={pv!r} neg={nv!r}",
        )

    return neg


def build_formal_report(ws: Path, variant: str) -> Scenario:
    evidence = read_json(ws / "evidence.json")
    if variant != "positive":
        evidence["formal_verification"] = [{"check": "pytest", "status": "FAIL"}]

    def check(_ws: Path, obs: Obs) -> list[Check]:
        res = _result(obs)
        markdown = str(res.get("markdown") or "")
        return [
            Check(
                "report_ready_and_claim_pass",
                obs.outcome.get("report_status") == "READY"
                and obs.outcome.get("claim_status") == "PASS",
                f"report_status={obs.outcome.get('report_status')} claim={obs.outcome.get('claim_status')}",
            ),
            Check(
                "seeded_evidence_counted",
                obs.outcome.get("judge_vote_count") == 1
                and obs.outcome.get("verification_passed") is True
                and obs.outcome.get("route_receipt_count") == 1,
                f"votes={obs.outcome.get('judge_vote_count')} verification={obs.outcome.get('verification_passed')} receipts={obs.outcome.get('route_receipt_count')} markdown_head={markdown[:60]!r}",
            ),
        ]

    return Scenario(
        statement="Build the evidence report for the refund change",
        task_type="research",
        codeintel=evidence,
        check=check,
    )


def neg_formal_report(pos: Obs, neg: Obs) -> Check:
    ok = pos.gate_passed and not neg.gate_passed and neg.outcome.get("claim_status") == "BLOCKED"
    return Check(
        "negative_control:failed_verification_blocks_claim",
        ok,
        f"pos.gate={pos.gate_passed} neg.gate={neg.gate_passed} neg.claim={neg.outcome.get('claim_status')}",
    )


def _seed_learn_claims(ws: Path) -> None:
    from nexus.research.learn_mode import LearnModeService

    with chdir(ws):
        LearnModeService(project_root=ws).ingest(
            source="local", source_file=str(ws / "notes.md"), topic="refund policy"
        )


def build_learn_mode(ws: Path, variant: str) -> Scenario:
    if variant == "positive":
        _seed_learn_claims(ws)

    def check(_ws: Path, obs: Obs) -> list[Check]:
        res = _result(obs)
        return [
            Check(
                "seeded_project_claims_counted",
                int(res.get("claims_count") or 0) >= 1,
                f"claims_count={res.get('claims_count')} run_root={obs.outcome.get('resolved_run_root')}",
            )
        ]

    return Scenario(
        statement="Learn the refund policy citations", task_type="research", check=check
    )


def neg_learn_counts(field_name: str) -> Callable[[Obs, Obs], Check]:
    def neg(pos: Obs, neg_obs: Obs) -> Check:
        pv, nv = _result(pos).get(field_name), _result(neg_obs).get(field_name)
        return Check(
            f"negative_control:unseeded_project_changes_{field_name}",
            pv != nv,
            f"{field_name} seeded={pv!r} unseeded={nv!r}",
        )

    return neg


def probe_learn_mode(ws: Path) -> dict[str, Any]:
    from nexus.research.learn_mode import LearnModeService

    _seed_learn_claims(ws)
    with chdir(ws):
        project = LearnModeService(project_root=ws).build_report()
        per_task = LearnModeService(
            project_root=ws, run_root=ws / ".nexus" / "runtime" / "probe-task"
        ).build_report()
    return {
        "project_root_report_claims_count": project.get("claims_count"),
        "per_task_run_root_claims_count": per_task.get("claims_count"),
        "note": "same service; before 2026-10-13 the executor passed run_root=<project>/.nexus/runtime/<task_id> (the per_task value), now it reads the project store",
    }


def build_learn_phase_slo(ws: Path, variant: str) -> Scenario:
    # Seeded at the project level (where LearnModeService(project_root) reads it).
    if variant == "positive":
        _seed_into(ws, "phase_writeback.jsonl", ".nexus/reports/learn/phase_writeback.jsonl")

    def check(_ws: Path, obs: Obs) -> list[Check]:
        res = _result(obs)
        glob = res.get("global") if isinstance(res.get("global"), Mapping) else {}
        return [
            Check(
                "seeded_writebacks_counted",
                int(glob.get("writeback_required") or 0) >= 1,
                f"global={glob}",
            ),
            Check(
                "missing_writebacks_fail_slo",
                res.get("phase_slo_pass") is False,
                f"phase_slo_pass={res.get('phase_slo_pass')}",
            ),
        ]

    return Scenario(statement="Check the learn phase slo", task_type="research", check=check)


def probe_learn_phase_slo(ws: Path) -> dict[str, Any]:
    from nexus.research.learn_mode import LearnModeService

    _seed_into(ws, "phase_writeback.jsonl", ".nexus/reports/learn/phase_writeback.jsonl")
    with chdir(ws):
        project = LearnModeService(project_root=ws).build_phase_slo_report(window=50)
        per_task = LearnModeService(
            project_root=ws, run_root=ws / ".nexus" / "runtime" / "probe-task"
        ).build_phase_slo_report(window=1)
    return {
        "project_root_phase_slo_pass": project.get("phase_slo_pass"),
        "project_root_writeback_required": (project.get("global") or {}).get("writeback_required"),
        "per_task_run_root_phase_slo_pass": per_task.get("phase_slo_pass"),
        "per_task_run_root_writeback_required": (per_task.get("global") or {}).get(
            "writeback_required"
        ),
    }


def build_file_lock(ws: Path, variant: str) -> Scenario:
    targets = ["target.py"] if variant == "positive" else []

    def check(root: Path, obs: Obs) -> list[Check]:
        lock_path = Path(str(obs.outcome.get("lock_file") or ""))
        payload = read_json(lock_path) if lock_path.is_file() else {}
        return [
            Check("lock_file_on_disk", lock_path.is_file(), str(lock_path)),
            Check(
                "lock_recorded_target_file",
                "target.py"
                in json.dumps((obs.outcome.get("result") or {}).get("task_files") or []),
                f"task_files={(obs.outcome.get('result') or {}).get('task_files')}",
            ),
            Check(
                "lock_released_on_task_completion",
                "target.py" not in dict(payload.get("locks") or {}),
                f"lock_after_run={json.dumps(payload)[:160]}",
            ),
            Check(
                "access_granted_and_files_match",
                obs.outcome.get("access_granted") is True
                and obs.outcome.get("task_files_match") is True,
                f"access={obs.outcome.get('access_granted')} match={obs.outcome.get('task_files_match')}",
            ),
        ]

    return Scenario(
        statement="Coordinate the write boundary for target.py",
        task_type="code_change",
        codeintel={"target_files": targets},
        check=check,
    )


def build_entropy_guard_v2(ws: Path, variant: str) -> Scenario:
    # Positive: a real prose/code output (the fixture's release note) must PASS; negative: the
    # same note with a credential-like key pasted in must be VETOED.  The audited text is the
    # output under review (codeintel.entropy_audit_text), never the task statement.
    note = (ws / "release_note.md").read_text(encoding="utf-8")
    if variant != "positive":
        # Credential-shaped value generated at run time (never stored, so no secret scanner
        # sees a literal): base64 of a fixed digest, 44 mixed-class chars.
        key = base64.b64encode(hashlib.sha256(b"wiring-audit-entropy-fixture").digest()).decode()
        note += f"\nDeploy key: {key}\n"

    def check(root: Path, obs: Obs) -> list[Check]:
        result = _result(obs)
        digest = hashlib.sha256(note.encode("utf-8")).hexdigest()
        return [
            Check(
                "audited_the_output_not_the_task",
                result.get("text_sha256") == digest,
                f"text_sha256={str(result.get('text_sha256'))[:12]} expected={digest[:12]}",
            ),
            Check(
                "real_output_passes",
                result.get("status") == "PASSED" and result.get("high_entropy_segments") == 0,
                f"status={result.get('status')} max_segment={result.get('max_segment_entropy')}",
            ),
        ]

    return Scenario(
        statement="Run an entropy audit on the changelog text",
        task_type="research",
        codeintel={"entropy_audit_text": note},
        route_features={"output_entropy_audit": True},
        # The planner demands an independent_review role for this validation node.
        online_route="independent_review",
        check=check,
    )


def neg_entropy_guard_v2(pos: Obs, neg: Obs) -> Check:
    p, n = _result(pos), _result(neg)
    ok = (
        p.get("status") == "PASSED"
        and n.get("status") == "VETOED"
        and not neg.gate_passed
        and int(n.get("high_entropy_segments") or 0) >= 1
        and float(n.get("max_segment_entropy") or 0) > float(p.get("max_segment_entropy") or 0)
    )
    return Check(
        "negative_control:leaked_key_vetoed",
        ok,
        f"pos={p.get('status')}/{p.get('max_segment_entropy')} neg={n.get('status')}/{n.get('max_segment_entropy')}",
    )


def neg_file_lock(pos: Obs, neg: Obs) -> Check:
    ok = (
        pos.gate_passed
        and not neg.gate_passed
        and "REAL_TARGET_FILES_REQUIRED" in neg.block_reason()
    )
    return Check(
        "negative_control:no_target_files_blocks", ok, f"neg.block_reason={neg.block_reason()}"
    )


def probe_file_lock(ws: Path) -> dict[str, Any]:
    """Two tasks lock the same file through the executor: is the second one refused?"""
    from nexus.core.belief_contracts import CapabilityExecutionPlan
    from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY

    out: dict[str, Any] = {}
    for task_id in ("lock-task-a", "lock-task-b"):
        plan = CapabilityExecutionPlan(
            plan_id=f"probe:{task_id}",
            task_id=task_id,
            phases=["R"],
            constraints={"workspace_root": str(ws), "target_files": ["target.py"]},
        )
        receipt = EXECUTOR_REGISTRY["file_lock_security_gate"](plan, "probe")
        outcome = dict(receipt.outcome or {})
        out[task_id] = {
            "gate_passed": receipt.gate_passed,
            "conflicts": outcome.get("conflicts"),
            "lock_file": outcome.get("lock_file"),
        }
    out["second_task_refused"] = bool(out["lock-task-b"]["conflicts"])
    out["holders"] = outcome.get("holders")
    out["note"] = (
        "one registry per workspace (.nexus/multi_agent/locks/file_locks.json) keyed by file;"
        " before 2026-10-13 the file was keyed by task id and the second task was not refused"
    )
    return out


def build_control_plane(
    statement: str, expected_reason: str = "control_plane_reference"
) -> Builder:
    def build(ws: Path, variant: str) -> Scenario:
        def check(_ws: Path, obs: Obs) -> list[Check]:
            stage = obs.stage or obs.row
            return [
                Check(
                    "receipt_states_not_executable",
                    obs.skip_reason == f"{NOT_EXECUTABLE}:{expected_reason}"
                    and not obs.invoked
                    and not bool(stage.get("outcome_contributed")),
                    f"skip_reason={obs.skip_reason!r} invoked={obs.invoked} outcome_contributed={stage.get('outcome_contributed')}",
                )
            ]

        return Scenario(statement=statement, task_type="code_change", check=check)

    return build


def build_judge_panel(ws: Path, variant: str) -> Scenario:
    fixture = read_json(ws / "candidates.json")
    candidates = list(fixture[variant])

    def check(_ws: Path, obs: Obs) -> list[Check]:
        out = obs.outcome
        ids = sorted(str(c["candidate_id"]) for c in candidates)
        ranking = [str(item) for item in out.get("ranking") or []]
        return [
            Check(
                "ranked_the_plan_candidates",
                sorted(ranking) == ids and int(out.get("candidate_count") or 0) == len(ids),
                f"ranking={ranking} candidate_count={out.get('candidate_count')}",
            ),
            Check(
                "local_ollama_judge_called",
                out.get("provider") == "ollama" and bool(out.get("judge_model")),
                f"provider={out.get('provider')} model={out.get('judge_model')}",
            ),
            Check(
                "winner_is_the_real_fix",
                out.get("winner") == "cand-b",
                f"winner={out.get('winner')}",
            ),
        ]

    return Scenario(
        statement=str(fixture["task"]),
        task_type="code_change",
        codeintel={"judge_panel_candidates": candidates},
        check=check,
    )


def neg_judge_panel(pos: Obs, neg: Obs) -> Check:
    pw, nw = pos.outcome.get("winner"), neg.outcome.get("winner")
    return Check(
        "negative_control:swapped_content_moves_the_winner",
        pw == "cand-b" and nw == "cand-a",
        f"winner pos={pw!r} neg={nw!r} (negative swaps the summaries of the two ids)",
    )


def build_external_doc_scout(ws: Path, variant: str) -> Scenario | None:
    return build_control_plane(
        "Check the vendor docs for the refund API", expected_reason="no_live_connector"
    )(ws, variant)


def build_learn_scheduler(ws: Path, variant: str) -> Scenario:
    # Positive: the workspace learn store has a passing phase SLO summary (real schema);
    # negative: no summary.  The executor must read the workspace, not the checkout.
    # The ledger is seeded too: learn_phase_slo (selected on the same route) rebuilds the
    # summary from it before the scheduler reads it.
    if variant == "positive":
        from nexus.research.learn_mode import LearnModeService

        learn = ws / ".nexus" / "reports" / "learn"
        learn.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "task_id": f"wiring-ok-{phase}-{i}",
                "phase": phase,
                "phase_status": "SUCCESS",
                "writeback_policy": {"required": True},
                "writeback_done": True,
            }
            for phase in ("X", "R")
            for i in range(3)
        ]
        (learn / "phase_writeback.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
        LearnModeService(project_root=ws).build_phase_slo_report(window=300)

    def check(root: Path, obs: Obs) -> list[Check]:
        report = root / ".nexus" / "reports" / "learn" / "scheduler_last_run.json"
        return [
            Check("scheduler_report_on_disk", report.is_file(), str(report)),
            Check(
                "scheduler_exit_zero",
                _result(obs).get("exit_code") == 0,
                f"exit_code={_result(obs).get('exit_code')} slo_readiness={_result(obs).get('slo_readiness')}",
            ),
        ]

    return Scenario(statement="Run the learn scheduler", task_type="research", check=check)


def neg_learn_scheduler(pos: Obs, neg: Obs) -> Check:
    pe, ne = _result(pos).get("exit_code"), _result(neg).get("exit_code")
    return Check(
        "negative_control:no_workspace_slo_summary_exits_2",
        pe == 0 and ne == 2 and not neg.gate_passed,
        f"seeded_exit={pe} unseeded_exit={ne}",
    )


def _closed_loopback_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def build_registry_sync(ws: Path, variant: str) -> Scenario:
    # Loopback only: a port with no listener (never an external host).
    port = _closed_loopback_port()

    def check(_ws: Path, obs: Obs) -> list[Check]:
        import socket

        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                reachable = True
        except OSError:
            reachable = False
        return [
            Check(
                "receipt_matches_peer_reachability",
                obs.gate_passed == reachable
                and bool(obs.outcome.get("peer_contacted")) == reachable,
                f"127.0.0.1:{port} reachable={reachable}; receipt gate={obs.gate_passed} peer_contacted={obs.outcome.get('peer_contacted')} row_count={obs.outcome.get('row_count')} error={obs.outcome.get('error')}",
            )
        ]

    return Scenario(
        statement="Sync the skill registry from the peer",
        task_type="code_change",
        codeintel={
            "registry_peer_host": "127.0.0.1",
            "registry_peer_port": port,
            "registry_query_tokens": ["wiring"],
        },
        check=check,
    )


# Natural selection under production defaults: no route-oracle line, the planning seam
# (plan_canonical_task_bundle) and the policy rule that would enable the node.  ``route_extra``
# documents rules whose input the seam drops (CanonicalTaskContext.planner_inputs only forwards
# route_features); ``rule`` is the policy_evaluator.py / capability_planner.py rule or "none".
NATURAL_TRIGGERS: dict[str, dict[str, Any]] = {
    "semantic_failure_sensor": {
        "rule": "none (no enable() call in policy_evaluator.py or capability_planner.py)",
        "statement": "Repair the failing compute_total test after a ZeroDivisionError",
        "task_type": "repair",
    },
    "bdd_acceptance_skill": {
        "rule": "none (no enable() call in policy_evaluator.py or capability_planner.py)",
        "statement": "Run the acceptance closeout checks for the delivery receipt",
    },
    "jit_validation": {
        "rule": "policy_evaluator: 'jit' in task text, or acceptance/benchmark/evidence signal",
        "statement": "Apply jit tool masking before editing target.py",
    },
    "semantic_searcher": {
        "rule": "policy_evaluator: lancedb hits or 'semantic'/'retrieval' in task text",
        "statement": "Use semantic retrieval to find the refund window policy",
        "task_type": "research",
    },
    "prompt_compression": {
        "rule": "capability_planner: route.prompt_compression is truthy",
        "statement": "Update target.py so the ledger stays balanced",
        "route_extra": {"prompt_compression": True},
    },
    "asi_constraint_extractor": {
        "rule": "policy_evaluator: route_features.blocked_assumptions_count > 0 or 'constraint' in task text",
        "statement": "Check the blocked assumption constraint across tasks",
        "task_type": "research",
    },
    "architecture_scout": {
        "rule": "policy_evaluator: route_features.research_role == 'architecture_scout' or plateau_detected",
        "statement": "Plan a seam for the billing module",
        "task_type": "research",
        "route_features": {"research_role": "architecture_scout"},
    },
    "formal_report": {
        "rule": "policy_evaluator: acceptance/benchmark signal or 'formal report'/'public report' in task text",
        "statement": "Write the formal report for the refund change",
        "task_type": "research",
    },
    "learn_mode": {
        "rule": "policy_evaluator: learning_signal ('learn','citation','slo','kpi','source','claim')",
        "statement": "Learn the refund policy citations",
        "task_type": "research",
    },
    "learn_phase_slo": {
        "rule": "policy_evaluator: learning_signal ('learn','citation','slo','kpi','source','claim')",
        "statement": "Learn the refund policy citations",
        "task_type": "research",
    },
    "file_lock": {
        "rule": "policy_evaluator: multi_agent_signal ('multi-agent','owner','file lock','worktree','integrate') or cross-module risk>=60",
        "statement": "Take a file lock on target.py for the multi-agent edit",
    },
    "direct_mode": {
        "rule": "policy_evaluator: route.recommended_flow == 'baseline'",
        "statement": "Update target.py to round totals",
        "route_extra": {"recommended_flow": "baseline"},
    },
    "msa_router": {
        "rule": "policy_evaluator: route.msa_routing.candidate_count > 0 or top_score >= 0.75",
        "statement": "Update target.py to round totals",
        "route_extra": {"msa_routing": {"candidate_count": 3, "top_score": 0.9}},
    },
    "research_control_plane": {
        "rule": "policy_evaluator: research_control_signal ('research control','auto-flow','experiment','optimizer','rollback','semantic status')",
        "statement": "Run the research control experiment with rollback",
        "task_type": "research",
    },
    "swarm_quiet_moment": {
        "rule": "policy_evaluator: 'swarm' in task text or cross-module risk>=70",
        "statement": "Run a swarm pass over target.py",
    },
    "integration_manager": {
        "rule": "policy_evaluator: 'merge'/'integrate'/'integration' in task text",
        "statement": "Merge the approved change for target.py",
    },
    "autonomic_router": {
        "rule": "none (no enable() call; capability_coverage_gap: reserved_until_planner_ssot_migration)",
        "statement": "Route the refund change to the right mode",
    },
    "judge_panel": {
        "rule": "policy_evaluator: confidence < 0.75, candidate factory, evidence or governance signal",
        "statement": "Rank the candidate fixes for target.py",
        "route_features": {"adjusted_root_cause_confidence": 0.5},
    },
    "llm_judge_panel": {
        "rule": "none (legacy alias; never enabled)",
        "statement": "Rank the candidate fixes for target.py",
        "route_features": {"adjusted_root_cause_confidence": 0.5},
    },
    "external_doc_scout": {
        "rule": "policy_evaluator: route_features.claim_uncertainty, or doc_scout_hits with a scout role",
        "statement": "Check the vendor docs for the refund API",
        "task_type": "research",
        "route_features": {"claim_uncertainty": True},
    },
    "learn_scheduler": {
        "rule": "none (no enable() call; reserved_until_scheduler_freshness_signals)",
        "statement": "Schedule the learn refresh for stale sources",
        "task_type": "research",
    },
    "registry_sync": {
        "rule": "policy_evaluator: registry_signal ('registry'/'skill' in task text) or skill candidates",
        "statement": "Sync the skill registry from the peer",
    },
}


def natural_selection(cap: str) -> dict[str, Any]:
    """Plan without the forcing line through the production seam; report the node's state."""
    from nexus.services.runtime_compat import (
        UnifiedRuntimeRequest,
        build_canonical_runtime_context,
        plan_canonical_task_bundle,
    )

    spec = NATURAL_TRIGGERS[cap]
    route: dict[str, Any] = {
        "recommended_flow": "direct",
        "route_features": dict(spec.get("route_features") or {}),
    }
    route.update(dict(spec.get("route_extra") or {}))
    request = UnifiedRuntimeRequest(
        task_id=f"wiring-natural-{cap}",
        workspace_revision="wiring-audit-rev",
        task_statement=str(spec["statement"]),
        task_type=str(spec.get("task_type") or "code_change"),
        route=route,
        online_enabled=True,
        local_enabled=False,
        online_prompt="wiring audit",
    )
    plan = plan_canonical_task_bundle(build_canonical_runtime_context(request)).plan
    trace = [
        item
        for item in plan.decision_trace
        if isinstance(item, Mapping) and item.get("capability") == cap
    ]
    state = next(
        (
            label
            for label, group in (
                ("required", plan.required_capabilities),
                ("conditional", plan.conditional_capabilities),
                ("optional", plan.optional_capabilities),
                ("forbidden", plan.forbidden_capabilities),
            )
            if cap in group
        ),
        "absent",
    )
    dropped = sorted(set(spec.get("route_extra") or {}))
    return {
        "rule": spec["rule"],
        "trigger_statement": spec["statement"],
        "trigger_route_features": dict(spec.get("route_features") or {}),
        "trigger_route_keys_dropped_by_seam": dropped,
        "selected_without_forcing": cap in plan.selected_capabilities,
        "state": state,
        "reasons": list(trace[0].get("reasons") or []) if trace else [],
    }


def verdict_bucket(verdict: Any) -> str:
    text = str(verdict)
    if text.startswith(BLOCKED_PREFIX):
        return "BLOCKED"
    if text.startswith(NOT_EXECUTABLE):
        return NOT_EXECUTABLE
    return text


# ------------------------------------------------ executor-registry keys with no planner node

# What each executor does, from reading its body (verified against the run: gate, outcome keys,
# and the quoted literals below are re-scanned from source on every run).  Keys the second
# archive batch removed from EXECUTOR_REGISTRY (2026-10-13) keep their description here and
# are reported RETIRING instead of being invoked.
EXECUTOR_ONLY: dict[str, dict[str, Any]] = {
    "policy_capability_gate": {
        "kind": "REAL_CALL_FIXTURE_INPUTS",
        "does": "calls nexus.services.policy_gate.apply_policy_gate with fixed health metrics and repo_root=/tmp (writes /tmp/.nexus/knowledge/policy_memory.jsonl); returns str(GateDecision), always INFO for these metrics",
        "literals": ['health_metrics={"memory_usage"', 'repo_root=Path("/tmp")'],
    },
    "aos_oracle": {
        "kind": "STUB_CONSTANT_STATUS",
        "does": "AosService(repo_root=/tmp).get_status() returns the literal {'status': 'OPERATIONAL', 'aos_version': '145.2', 'trust_score': 0.98, 'governance': 'ACTIVE'} (aos_service.py); oracle_shadow / oracle:apply are archived, this key is a leftover",
        "literals": ['cls(repo_root=Path("/tmp"))'],
    },
    "learn_refresh_service": {
        "kind": "STUB_CONSTRUCT_ONLY",
        "does": "constructs LearnRefreshService(repo_root=/tmp) and reports class_instantiated; no refresh runs; the registry's construct-only guard then rejects it (import_construct_not_execution)",
        "literals": ['cls(repo_root=Path("/tmp"))', '"class_instantiated": True'],
    },
    "zero_trust_v2_behavior": {
        "kind": "STUB_CONSTRUCT_ONLY",
        "does": "builds the behavior runner adapter and returns function_called=True (gate passes); the adapter is never run",
        "literals": ['"function_called": True'],
    },
    "predictive_auditor": {
        "kind": "REAL_CALL_DEGRADED",
        "does": "PredictiveAuditor().audit_risk({task_id, constraints}); with no Wisdom Registry table it returns risk_score 0.0 / PROCEED (with a table it would embed locally via self.model.encode)",
        "literals": ['"risk_score"'],
    },
    "spec_guarded": {
        "kind": "REAL_CALL_FIXTURE_INPUTS",
        "does": "SpecGuardV2().validate_diagnosis({'task_id'}, constraints) with an empty diagnosis and empty constraints; reports validated (defaults True)",
        "literals": [
            'inst.validate_diagnosis({"task_id": plan.task_id}',
            'result.get("validated", True)',
        ],
    },
    "decision_formula_engine": {
        "kind": "STUB_CONSTRUCT_ONLY",
        "does": "constructs DecisionFormulaEngine(context=...) and reports class_instantiated; no formula evaluated; rejected as import_construct_not_execution",
        "literals": ['"class_instantiated": True'],
    },
    "reflex_loop": {
        "kind": "REAL_CALL_HARD_CODED_TMP",
        "does": "ReflexLoop(project_root=/tmp).run_cycle(): NAS tuner + BattleSwarm tuning against /tmp logs; writes /tmp/.nexus/config/reflex_params.json",
        "literals": ['cls(project_root="/tmp")'],
    },
    "dual_loop": {
        "kind": "STUB_CONSTRUCT_ONLY",
        "does": "constructs DualLoopOrchestrator(project_root=/tmp) and reports class_instantiated; rejected as import_construct_not_execution",
        "literals": ['cls(project_root="/tmp")', '"class_instantiated": True'],
    },
    "mfp_gate": {
        "kind": "REAL_CALL_CONSTANT_INPUTS",
        "does": "evaluate_mfp with constant confidence=0.99, semantic_entropy=0.1, history_success_rate=0.96, so it always returns passed=True (input-independent)",
        "literals": ["confidence=0.99, semantic_entropy=0.1, history_success_rate=0.96"],
    },
    "promotion_engine": {
        "kind": "STUB_CONSTRUCT_ONLY",
        "does": "constructs PromotionEngine() and reports class_instantiated; rejected as import_construct_not_execution",
        "literals": ['"class_instantiated": True'],
    },
    "subagent_outcome_service": {
        "kind": "STUB_CONSTRUCT_ONLY",
        "does": "constructs SubagentOutcomeService(project_root=/tmp) and reports class_instantiated; rejected as import_construct_not_execution",
        "literals": ['cls(project_root=Path("/tmp"))', '"class_instantiated": True'],
    },
    "attempt_settlement_service": {
        "kind": "STUB_CONSTRUCT_ONLY",
        "does": "constructs AttemptSettlementService with /tmp paths, zero metrics and transaction_mgr={'status': 'simulated'}; rejected as import_construct_not_execution",
        "literals": ['run_dir=Path("/tmp/run")', 'transaction_mgr={"status": "simulated"}'],
    },
    "battle_swarm": {
        "kind": "ALIAS",
        "does": "delegates to _exec_swarm_multi_agent (same body as the swarm / multi_agent rows); auth-blocked at production default",
        "literals": ["return _exec_swarm_multi_agent(plan, task_desc)"],
    },
    "nightshift_runner_service": {
        "kind": "AUTH_GATED_REAL_CALL",
        "does": "same body as the nightshift row (nightshift aliases it); blocked without NEXUS_LOCAL_MODEL_CALL_ALLOWED / NEXUS_EXTERNAL_RUNTIME_AUTHORIZED; default target README.md",
        "literals": ['constraints.get("nightshift_target_file") or "README.md"'],
    },
    "research_and_source_discipline": {
        "kind": "REAL_CALL_MISUSED_INPUT",
        "does": "PythonCodeSkeletonProvider(root=cwd).lookup_implementation(<whole task text>) - the task sentence is looked up as a symbol name",
        "literals": ["inst.lookup_implementation(str(task_desc or plan.task_id))"],
    },
}


def executor_only_keys() -> dict[str, Any]:
    """Executor-registry keys that no planner node (nor alias) maps to, minus archived ones."""
    from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY
    from nexus.services import capability_registry as registry

    planner = set(registry.list_planner_capability_names())
    aliased = set(registry.EXECUTOR_REGISTRY_ALIASES.values())
    contract_keys = {
        str(c.get("executor_key"))
        for c in registry.PLANNER_EXECUTION_CONTRACTS.values()
        if isinstance(c, Mapping) and c.get("executor_key")
    }
    computed = sorted(set(EXECUTOR_REGISTRY) - planner - aliased - contract_keys)
    return {
        "computed": computed,
        "retiring_excluded": sorted(set(computed) & set(RETIRING_CAPABILITIES)),
        "audited": sorted(EXECUTOR_ONLY),
        "unlisted": sorted(set(computed) - set(EXECUTOR_ONLY) - set(RETIRING_CAPABILITIES)),
        "listed_but_reachable": sorted(
            set(EXECUTOR_ONLY) - set(computed) - (set(EXECUTOR_ONLY) - set(EXECUTOR_REGISTRY))
        ),
        "retired_from_registry": sorted(set(EXECUTOR_ONLY) - set(EXECUTOR_REGISTRY)),
    }


def _tmp_snapshot() -> dict[str, float]:
    roots = [Path("/private/tmp/.nexus"), Path("/private/tmp/run"), Path("/private/tmp/nexus")]
    snap: dict[str, float] = {}
    for root in roots:
        if root.is_dir():
            for path in list(root.rglob("*"))[:5000]:
                with contextlib.suppress(OSError):
                    snap[str(path)] = path.stat().st_mtime
    return snap


def audit_executor_only(key: str, work_root: Path) -> dict[str, Any]:
    """Invoke one unreachable executor directly (production default env, workspace cwd)."""
    from nexus.core.belief_contracts import CapabilityExecutionPlan
    from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY

    info = EXECUTOR_ONLY[key]
    if key not in EXECUTOR_REGISTRY:
        note = RETIRED_EXECUTOR_ONLY_NOTES.get(key, "executor and registry key removed 2026-10-13")
        verdict, reason = classify_verdict({"retiring": f"{RETIRED_EXECUTOR_ONLY_REASON}: {note}"})
        return {
            "executor_key": key,
            "verdict": verdict,
            "verdict_reason": reason,
            "kind": info["kind"],
            "does": info["does"],
            "executor": {},
            "invoked": None,
            "gate_passed": None,
            "quoted_lines": [],
            "literals_missing": [],
        }
    fn = EXECUTOR_REGISTRY[key]
    loc = source_location(fn)
    ws = work_root / f"executor_only__{key}"
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    (ws / "target.py").write_text("def compute_total(items):\n    return sum(items)\n")
    plan = CapabilityExecutionPlan(
        plan_id=f"wiring-executor-only:{key}",
        task_id=f"wiring-executor-only-{key}",
        phases=["R"],
        constraints={},
    )
    before = _tmp_snapshot()
    started = time.monotonic()
    with capture_console() as console, policy_env(POLICY_PRODUCTION), chdir(ws):
        try:
            receipt = fn(plan, "Update target.py to round totals")
            error = ""
        except Exception as exc:  # noqa: BLE001 - recorded
            receipt, error = None, f"{type(exc).__name__}: {exc}"[:300]
    after = _tmp_snapshot()
    tmp_writes = sorted(path for path, mtime in after.items() if before.get(path) != mtime)
    outcome = dict(getattr(receipt, "outcome", None) or {}) if receipt is not None else {}
    literals = scan_hard_coded(fn, list(info.get("literals") or []))
    return {
        "executor_key": key,
        "verdict": UNREACHABLE_NO_PLANNER_NODE,
        "kind": info["kind"],
        "does": info["does"],
        "executor": {k: v for k, v in loc.items() if not k.startswith("_")},
        "invoked": getattr(receipt, "invoked", None),
        "gate_passed": getattr(receipt, "gate_passed", None),
        "raised": error,
        "outcome_excerpt": json.loads(json.dumps(outcome, default=str)[:1200])
        if len(json.dumps(outcome, default=str)) <= 1200
        else {"truncated": json.dumps(outcome, default=str)[:1200]},
        "quoted_lines": literals,
        "literals_missing": sorted(
            set(info.get("literals") or []) - {item["pattern"] for item in literals}
        ),
        "tmp_paths_written": tmp_writes[:20],
        "console_tail": [line[:200] for line in console if line.strip()][-8:],
        "audit_seconds": round(time.monotonic() - started, 2),
    }


def executor_only_table(rows: list[Mapping[str, Any]]) -> str:
    lines = [
        "| executor key | verdict | kind | gate_passed | what it does | quoted line(s) |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        quotes = "; ".join(
            f"`{_short(q.get('text'), 90)}` (:{q.get('line')})"
            for q in row.get("quoted_lines") or []
        )
        lines.append(
            f"| {row.get('executor_key')} | {row.get('verdict')} | {row.get('kind')} | "
            f"{row.get('gate_passed')} | {_short(row.get('does'), 160)} | {quotes or '-'} |"
        )
    return "\n".join(lines)


# -------------------------------------------------------------------------- the specs

_SPEC_LIST: list[CapSpec] = [
    CapSpec(
        "codeintel",
        "codeintel",
        build_codeintel,
        negative_check=neg_codeintel,
        probe=probe_codeintel,
        gaps=(
            "executor performs lookup_implementation only: no code graph, no impact set, no related tests are produced",
        ),
    ),
    CapSpec(
        "research",
        "research",
        build_research,
        negative_check=neg_research,
        policies=(POLICY_PRODUCTION, POLICY_EXTERNAL_FLAG),
        gaps=(
            "(fixed in #1862) the executor passes the task under 'task'; outbound provider calls need NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1",
        ),
    ),
    CapSpec(
        "research_route",
        "research",
        build_research,
        negative_check=neg_research,
        policies=(POLICY_PRODUCTION, POLICY_EXTERNAL_FLAG),
        gaps=(
            "selected on every run (required node) but the invoker skips unless escalate-triggered; when triggered it reuses the research executor (same 'task_statement' vs 'task' key mismatch)",
        ),
    ),
    CapSpec(
        "hyper",
        "hyper",
        build_hyper,
        policies=(POLICY_PRODUCTION, POLICY_LOCAL_MODEL),
        needs_model=True,
        hard_coded=("candidate_count=1", 'target_file="README.md"', "llm_mode=False"),
        negative_check=neg_hyper,
        gaps=(
            "the learn-phase SLO guard drops llm_mode on any workspace without learn-phase history (audit sets NEXUS_FORCE_LLM_DESPITE_LEARN_SLO=1; the receipt reports llm_mode_effective)",
        ),
    ),
    CapSpec(
        "nightshift",
        "nightshift",
        build_nightshift,
        policies=(POLICY_PRODUCTION, POLICY_LOCAL_MODEL),
        gaps=(
            "AutoResearchNightShift runs one round with a bare task string; the phase policy reads <workspace_root>/.nexus/reports/learn/phase_slo_summary.json (right directory); until 2026-10-13 it read a never-written overall_pass_rate key, so every real summary was PassRate=0%; the fixture workspace has no summary, so it is still denied (SLO=phase_slo_summary_missing) before any model call and no recovery report is written",
        ),
    ),
    CapSpec(
        "swarm",
        "swarm",
        build_swarm,
        policies=(POLICY_PRODUCTION, POLICY_LOCAL_MODEL),
        needs_model=True,
        negative_check=neg_swarm,
        gaps=(
            "integration goes through the single Candidate integration owner (SelfHostedTaskService.integrate_approved -> ControlledIntegrationManager, #947) and needs a persisted APPROVED lifecycle task bound to the exact winner commit, which only exists after the run; the run therefore stops BLOCKED (INTEGRATION_OWNER_AUTHORITY_REQUIRED) with pending_owner_approval, and the fixture's Owner step (owner_fixture_integrate_swarm_winner, labelled approver) then integrates that winner through the same facade; the lifecycle state root is fixture-local (NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR), never production",
        ),
    ),
    CapSpec(
        "multi_agent",
        "swarm",
        build_swarm,
        policies=(POLICY_PRODUCTION, POLICY_LOCAL_MODEL),
        needs_model=True,
        negative_check=neg_swarm,
        gaps=("alias of swarm_multi_agent (same executor)",),
    ),
    CapSpec(
        "drone",
        "drone",
        build_drone,
        negative_check=neg_drone,
        gaps=(
            "executor calls TacticalDrone.repair_response_schema/normalize_action on the task text only; no sub-task is dispatched and gate_passed is true for any task",
        ),
    ),
    CapSpec(
        "ultra_review",
        "ultra_review",
        build_ultra_review,
        negative_check=neg_ultra_review,
        probe=probe_ultra_review,
        gaps=(
            "fixed 2026-10-13 (group D): executor runs UltraReviewService.run(dry_run=False) in a sandbox git worktree; lanes run bandit + ruff S rules (added lines), py_compile + ruff correctness rules and pytest on mapped tests; untracked new files are overlaid but not part of the reviewed diff",
        ),
    ),
    CapSpec(
        "autoreason",
        "autoreason",
        build_autoreason,
        policies=(POLICY_PRODUCTION, POLICY_EXTERNAL_FLAG),
        probe=probe_autoreason,
        hard_coded=('"id": "c0"',),
        gaps=(
            "executor ranks one hard-coded candidate {'id': 'c0', 'score': 1.0}; context cannot carry candidates (no allowlisted constraint)",
        ),
    ),
    CapSpec(
        "ddtree",
        "ddtree",
        build_ddtree,
        policies=(POLICY_PRODUCTION, POLICY_EXTERNAL_FLAG),
        probe=probe_ddtree,
        hard_coded=('"candidate_id": "c0"', "max_candidates=2"),
        gaps=(
            "executor plans one hard-coded candidate c0 with max_candidates=2, so nothing can be pruned (pruned_count is always 0)",
        ),
    ),
    CapSpec(
        "lancedb",
        "lancedb",
        build_lancedb,
        negative_check=neg_hits,
        gaps=(
            "searches only the 'policy' FTS table of the workspace knowledge root; no vector search",
        ),
    ),
    CapSpec(
        "memory",
        "memory",
        build_memory,
        negative_check=neg_hits,
        probe=probe_memory,
        gaps=(
            "the memory_query constraint is never fed (UnifiedRuntime context has no memory_query); the executor searches with the whole task statement as a LIKE pattern, so a hit needs a stored insight containing that entire text",
        ),
    ),
    CapSpec(
        "mempalace_gate",
        "mempalace_gate",
        build_mempalace,
        negative_check=neg_mempalace,
        gaps=(
            "the blacklist check runs only on retrieved artifacts (MemPalace.verify), not on tool invocations",
        ),
    ),
    CapSpec(
        "belief",
        "belief",
        build_belief,
        negative_check=neg_belief,
        gaps=(
            "read-only: assess_confidence on the task statement; no outcome update path exists in the registry executor",
        ),
    ),
    CapSpec("artifact_gate", "gates", build_gate("artifact_gate"), negative_check=neg_gate),
    CapSpec("claim_gate", "gates", build_gate("claim_gate"), negative_check=neg_gate),
    CapSpec("delivery_gate", "gates", build_gate("delivery_gate"), negative_check=neg_gate),
    CapSpec("acceptance_check", "gates", build_acceptance, negative_check=neg_acceptance),
    CapSpec("pregate", "pregate", build_pregate, negative_check=neg_pregate),
    CapSpec("forecast_gate", "forecast_gate", build_forecast, negative_check=neg_forecast),
    CapSpec(
        "plan_quality_gate",
        "plan_quality_gate",
        build_plan_quality,
        negative_check=neg_plan_quality,
    ),
    CapSpec("sandbox", "sandbox", build_sandbox, negative_check=neg_sandbox),
    CapSpec(
        "harness_preflight_sensor",
        "harness_preflight_sensor",
        build_harness_sensor,
        negative_check=neg_harness_sensor,
        gaps=(
            "pending_capabilities/selected_capabilities are not in the UnifiedRuntime capability_context, so the sensor evaluates empty lists and passes vacuously",
        ),
    ),
    CapSpec(
        "committee",
        "committee",
        build_committee,
        policies=(POLICY_PRODUCTION, POLICY_LOCAL_MODEL, POLICY_COMMITTEE_FLAG),
        negative_check=neg_committee,
        gaps=(
            "the controller is off unless NEXUS_USE_COMMITTEE=1; without committee_verify_commands the global VerifierRegistry is empty by default, so no verdict is recorded and the receipt fails",
        ),
    ),
    CapSpec(
        "xray",
        "xray",
        build_xray,
        negative_check=neg_xray,
        hard_coded=('"nexus/services/capability_registry.py"',),
        gaps=(
            "scan target is hard-coded to <project_root>/nexus/services/capability_registry.py regardless of the task",
        ),
    ),
    CapSpec("metabolism", "metabolism", build_metabolism, negative_check=neg_metabolism),
    CapSpec("meta_opt", "meta_opt", build_meta_opt, negative_check=neg_meta_opt),
    CapSpec(
        "local_model_executor",
        "repair",
        build_local_stage("local_model_executor"),
        policies=(POLICY_LOCAL_MODEL,),
        needs_model=True,
        gaps=(
            "without Local-stage proof the registry invoker falls back to a fixture provider (_FixtureLocalProvider returns canned text); the real path is the Local stage",
        ),
    ),
    CapSpec(
        "repair_loop",
        "repair",
        build_local_stage("repair_loop"),
        policies=(POLICY_LOCAL_MODEL,),
        needs_model=True,
    ),
]
# 2026-10-13 extension: the 22 planner nodes the first audit did not cover.
_SPEC_LIST += [
    CapSpec(
        "semantic_failure_sensor",
        "semantic_failure_sensor",
        build_semantic_failure_sensor,
        negative_check=neg_semantic_failure_sensor,
        gaps=(
            "find_similar_bugs runs on Path('.') (the process cwd), not the workspace_root, with the whole task statement (oracle contract included) as the traceback; the outcome keeps only hit_count/top_hit_type, so the matched fix template never reaches a consumer",
        ),
    ),
    CapSpec(
        "bdd_acceptance_skill",
        "gates",
        build_bdd_acceptance,
        negative_check=neg_bdd_acceptance,
        gaps=("delegates to _exec_acceptance_check; no BDD scenario of its own is evaluated",),
    ),
    CapSpec(
        "jit_validation",
        "jit_validation",
        build_jit,
        negative_check=neg_jit,
        probe=probe_jit,
        callee_hard_coded=(("nexus.core.jit_tool_injector:JITToolInjector.apply_mask", "Mock"),),
        gaps=(
            "JITToolInjector.apply_mask is a self-declared mock: it matches only the Chinese keywords 測試/核驗/具現/修復 and otherwise returns all_tools[:5]; the tool catalog (jit_all_tools) must be supplied by the request; since 2026-10-13 the receipt says so (simulated=True, mask_kind=keyword_mock, claim_boundary.claim=SIMULATED)",
        ),
    ),
    CapSpec(
        "semantic_searcher",
        "lancedb",
        build_semantic_searcher,
        negative_check=neg_hits,
        gaps=(
            "full-text search over the workspace knowledge 'policy' table (same store as lancedb); no embedding is computed (sentence_transformers is not installed in this venv)",
        ),
    ),
    CapSpec(
        "prompt_compression",
        None,
        build_prompt_compression,
        negative_check=neg_prompt_compression,
        gaps=(
            "runtime-owned invoker (nexus_runtime.kernel.capabilities.build_prompt_compression_capability_invoker), not the Nexus executor _exec_prompt_compression; when selected it always replaces the online prompt with a JSON blob of prompt + capability results, so a short prompt becomes longer",
        ),
    ),
    CapSpec(
        "asi_constraint_extractor",
        "asi_constraint_extractor",
        build_asi,
        negative_check=neg_asi,
        gaps=(
            "records must be supplied in the request (asi_failure_records); nothing in the runtime feeds the ASI ledger to it",
        ),
    ),
    CapSpec(
        "architecture_scout",
        "architecture_scout",
        build_architecture_scout,
        negative_check=neg_architecture_scout,
        gaps=(
            "fixed 2026-10-13 (group D): plateau comes from nexus.research.flow.runtime_decision.detect_plateau over the request's asi_failure_records; nothing in nexus run feeds that ledger to the node yet (the research flow feeds its own HistorySignalStore ledger)",
        ),
    ),
    CapSpec(
        "formal_report",
        "formal_report",
        build_formal_report,
        negative_check=neg_formal_report,
        gaps=(
            "judge votes, verification rows and route receipts must be supplied in the request; the runtime does not feed its own receipts",
        ),
    ),
    CapSpec(
        "learn_mode",
        "learn_mode",
        build_learn_mode,
        negative_check=neg_learn_counts("claims_count"),
        probe=probe_learn_mode,
        gaps=(
            "fixed 2026-10-13: the executor reads the project learn store LearnModeService(<workspace_root>) like the learn:* CLI (was a fresh empty <cwd>/.nexus/runtime/<task_id>); gate_passed is still 'report built', the claim count is in the result",
        ),
    ),
    CapSpec(
        "learn_phase_slo",
        "learn_phase_slo",
        build_learn_phase_slo,
        negative_check=neg_learn_counts("phase_slo_pass"),
        probe=probe_learn_phase_slo,
        gaps=(
            "fixed 2026-10-13: reads the project phase ledger with the CLI window (300; was an empty per-task run_root with window=1); gate_passed means the report was built, phase_slo_pass is in the result",
        ),
    ),
    CapSpec(
        "entropy_guard_v2",
        "entropy_guard_v2",
        build_entropy_guard_v2,
        negative_check=neg_entropy_guard_v2,
        gaps=(
            "planner node since nexus-runtime #198 (pin 68e86ed); enabled only on an explicit request (route_features.output_entropy_audit or 'entropy audit'); veto = a credential-like segment above 4.1 bits/char (calibrated on this repository, see nexus/services/entropy_v2.py); whole-text entropy is reported only",
        ),
    ),
    CapSpec(
        "file_lock",
        "file_lock",
        build_file_lock,
        negative_check=neg_file_lock,
        probe=probe_file_lock,
        gaps=(
            "fixed 2026-10-13: one registry per workspace (.nexus/multi_agent/locks/file_locks.json) keyed by file, holder = task id, flock-guarded; a second task is BLOCKED (FILE_LOCK_HELD_BY_OTHER_TASK), same-task re-lock is idempotent; since #2041 the mainchain entry releases the task's locks on completion (release_task_locks), the 1800 s TTL is only the backstop",
        ),
    ),
    CapSpec(
        "direct_mode",
        None,
        build_control_plane("Update target.py to round totals"),
        not_executable="control_plane_reference",
        gaps=(
            "execution contract physical_callable=None; executor key direct_master_loop is not in EXECUTOR_REGISTRY. nexus run uses nexus.engine.direct_mode.evaluate_direct_mode_completion outside the planner node; since group D the receipt says NOT_EXECUTABLE:control_plane_reference",
        ),
    ),
    CapSpec(
        "msa_router",
        None,
        build_control_plane("Update target.py to round totals"),
        not_executable="control_plane_reference",
        gaps=(
            "execution contract physical_callable=None; no msa_router key in EXECUTOR_REGISTRY; since group D the receipt says NOT_EXECUTABLE:control_plane_reference (an executor is an MSA design task, not a wiring fix)",
        ),
    ),
    CapSpec(
        "research_control_plane",
        None,
        build_control_plane("Update target.py to round totals"),
        not_executable="control_plane_reference",
        gaps=(
            "execution contract physical_callable=None; no research_control_plane key in EXECUTOR_REGISTRY (real code nexus/research/experiment_scheduler.py is reachable only via the research:run CLI); since group D the receipt says NOT_EXECUTABLE:control_plane_reference",
        ),
    ),
    CapSpec(
        "judge_panel",
        "judge_panel",
        build_judge_panel,
        policies=(POLICY_PRODUCTION, POLICY_LOCAL_MODEL),
        needs_model=True,
        hard_coded=('id="c0"',),
        negative_check=neg_judge_panel,
        gaps=(
            "fixed 2026-10-13 (group D): ranks the request's candidate_pool (codeintel.judge_panel_candidates) with OllamaJudgeProvider (Workforce local_first.classification worker, M5 tunnel) under NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; no provider at production default; nexus run does not yet feed a candidate pool to the node",
        ),
    ),
    CapSpec(
        "external_doc_scout",
        None,
        build_external_doc_scout,
        policies=(POLICY_PRODUCTION, POLICY_EXTERNAL_FLAG),
        not_executable="no_live_connector",
        gaps=(
            "execution contract physical_callable=None; the EXECUTOR_REGISTRY entry is an auth gate with nothing behind it; since group D the planner-node invoker never calls it and the receipt says NOT_EXECUTABLE:no_live_connector",
        ),
    ),
    CapSpec(
        "learn_scheduler",
        None,
        build_learn_scheduler,
        negative_check=neg_learn_scheduler,
        gaps=(
            "fixed 2026-10-13: learn:phase-policy --project-root <workspace_root> (the checkout only supplies the CLI script), and the phase policy reads the real summary schema (phase_slo_pass_rate; it read a never-written overall_pass_rate key, so readiness was always 0%); alerts are still written under the cwd",
        ),
    ),
    CapSpec(
        "registry_sync",
        None,
        build_registry_sync,
        policies=(POLICY_PRODUCTION, POLICY_EXTERNAL_FLAG),
        gaps=(
            "fixed 2026-10-13: the executor uses pull_from_peer_checked; a connection error is BLOCKED (REGISTRY_PEER_UNAVAILABLE:<error class>) with peer_contacted=False (pull_from_peer still returns [] for legacy callers); no live mTLS peer in the fixture, so there is no positive run",
        ),
    ),
]
SPECS: dict[str, CapSpec] = {spec.cap: spec for spec in _SPEC_LIST}


# ------------------------------------------------------------- route smoke probe


def smoke_probe(work_root: Path) -> dict[str, Any]:
    """Does scripts/ops/capability_route_smoke.py reject receipts whose capabilities are simulated?

    Feeds the smoke's own row validator a synthetic with-Nexus row whose receipts carry
    ``claim_boundary.simulated=true`` for every capability.  Also greps the validator modules for
    any read of ``simulated`` / ``claim_boundary``.
    """
    from scripts.ops import capability_route_smoke as smoke

    receipts = [
        {
            "name": name,
            "capability": name,
            "selected": True,
            "invoked": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "public_claim_safe": True,
            "evidence_refs": [f"synthetic:{name}"],
            "claim_boundary": {
                "simulated": True,
                "claim_eligible": False,
                "public_claim_allowed": False,
            },
        }
        for name in (
            "autoreason",
            "ddtree",
            "ultra_review",
            "research",
            "lancedb",
            "swarm",
            "drone",
            "nightshift",
        )
    ]
    row = {
        "mode": "with_nexus",
        "task_id": "synthetic-simulated-row",
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "route_decision_schema_version": "synthetic.v1",
        "route_decision_selected_count": len(receipts),
        "route_decision_invoked_count": len(receipts),
        "route_decision_evidence_count": len(receipts),
        "route_decision_outcome_count": len(receipts),
        "capability_receipts": receipts,
        "expected_capability_receipt_coverage": {
            "expected": [r["name"] for r in receipts],
            "public_safe": [r["name"] for r in receipts],
            "missing": [],
            "all_public_safe": True,
        },
    }
    work_root.mkdir(parents=True, exist_ok=True)
    path = work_root / "synthetic_with_nexus.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    summary = smoke.summarize_jsonl(path)
    modules = [
        REPO_ROOT / "scripts/ops/capability_route_smoke.py",
        REPO_ROOT / "nexus/engine/capability_receipt_policy.py",
        REPO_ROOT / "scripts/bench/gemini_nexus_report.py",
    ]
    readers: dict[str, int] = {}
    for module in modules:
        text = module.read_text(encoding="utf-8") if module.is_file() else ""
        readers[str(module.relative_to(REPO_ROOT))] = len(re.findall(r"simulated", text))
    return {
        "synthetic_row_failures": summary.get("failures", []),
        "passes_on_simulated_receipts": not summary.get("failures"),
        "mentions_of_simulated_in_validators": readers,
        "note": "row validator checked status/semantic_status/coverage/route_decision counts only; claim_boundary.simulated is never read",
    }


# ------------------------------------------------------------------------ outputs


def git_head() -> str:
    try:
        return subprocess.run(  # nosec B603 B607 - fixed git argv
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def archived_skip_observation(cap: str) -> str:
    """Skip reason the production invoker returns for an archived planner node ('' if none)."""
    from nexus.services import capability_registry as registry

    if cap not in registry.ARCHIVED_CAPABILITY_REASONS:
        return ""
    if cap not in set(registry.list_planner_capability_names()):
        return ""
    invoker = registry.build_default_mainchain_invokers().get(cap)
    if invoker is None:
        return ""
    result = dict(invoker({"task_id": f"wiring-retiring-{cap}"}) or {})
    return str(result.get("skip_reason") or "")


def retiring_row(cap: str, note: str) -> dict[str, Any]:
    verdict, reason = classify_verdict({"retiring": note})
    row: dict[str, Any] = {
        "capability": cap,
        "verdict": verdict,
        "verdict_reason": reason,
        "executor": {},
        "gaps": ["owned by the archive PR; not executed by this audit"],
    }
    try:
        observed = archived_skip_observation(cap)
    except Exception as exc:  # noqa: BLE001 - recorded, never hidden
        observed = f"observation_error:{type(exc).__name__}"
    if observed:
        row["archived_skip_reason"] = observed
        row["gaps"] = [f"archived: the production invoker returns an explicit skip ({observed})"]
    return row


def _short(text: Any, limit: int) -> str:
    value = str(text).replace("|", "/").replace("\n", " ")
    return value if len(value) <= limit else value[: limit - 3] + "..."


def markdown_table(rows: list[Mapping[str, Any]]) -> str:
    header = (
        "| capability | verdict | executor-level verdict (product path blocked) | production default, selected but untriggered "
        "| selected without forcing (production defaults) "
        "| executor (function @ file:line) | reached via | switches needed | receipt_claims_simulated |"
    )
    lines = [header, "|---|---|---|---|---|---|---|---|---|"]
    for row in rows:
        ex = row.get("executor") or {}
        where = (
            f"{ex.get('function')} @ {ex.get('file')}:{ex.get('line')}"
            if ex.get("function")
            else "-"
        )
        switches = row.get("policy_switches_needed") or {}
        policy = ",".join(f"{k}={v}" for k, v in switches.items()) or "none"
        if row.get("trigger_switch"):
            policy += "; route.escalate_triggered=True"
        untriggered = row.get("untriggered_production_default") or {}
        natural = row.get("production_default_selection") or {}
        if not natural:
            natural_text = "-"
        elif natural.get("selected_without_forcing"):
            natural_text = "yes: " + ",".join(natural.get("reasons") or [])
        else:
            natural_text = (
                f"no ({natural.get('state')}"
                + (
                    "; rule input dropped by seam: "
                    + ",".join(natural.get("trigger_route_keys_dropped_by_seam") or [])
                    if natural.get("trigger_route_keys_dropped_by_seam")
                    else ""
                )
                + ("; " + ",".join(natural.get("reasons") or []) if natural.get("reasons") else "")
                + ")"
            )
        lines.append(
            "| {cap} | {verdict} | {execlvl} | {untrig} | {natural} | {where} | {via} | {policy} | {sim} |".format(
                cap=row.get("capability"),
                verdict=_short(row.get("verdict"), 120),
                execlvl=_short(row.get("executor_level_verdict") or "-", 80),
                untrig=_short(
                    untriggered.get("skip_reason") or untriggered.get("status") or "-", 40
                ),
                natural=_short(natural_text, 110),
                where=_short(where, 90),
                via=(ex.get("reached_via") or "-").split(" (")[0],
                policy=_short(policy, 80),
                sim=row.get("receipt_claims_simulated"),
            )
        )
    lines += ["", "| capability | verdict reason | failed assertions / notes |", "|---|---|---|"]
    for row in rows:
        failed = [c["name"] for c in row.get("checks", []) if not c.get("passed")]
        notes = ("failed: " + ", ".join(failed)) if failed else ""
        lines.append(
            f"| {row.get('capability')} | {_short(row.get('verdict_reason'), 140)} | {_short(notes, 160)} |"
        )
    return "\n".join(lines)


def run_audit(
    only: list[str] | None, out_root: Path, *, allow_model: bool, smoke_summary: Path | None
) -> dict[str, Any]:
    stamp = utc_stamp()
    out_dir = out_root / stamp
    work_root = out_dir / "workspaces"
    (out_dir / "receipts").mkdir(parents=True, exist_ok=True)
    work_root.mkdir(parents=True, exist_ok=True)
    model = probe_model() if allow_model else {"available": False, "reason": "--no-model"}
    rows: list[dict[str, Any]] = []
    for spec in _SPEC_LIST:
        if only and spec.cap not in only:
            continue
        started = time.monotonic()
        try:
            row = audit_capability(spec, work_root, out_dir, model, allow_model=allow_model)
        except Exception as exc:  # noqa: BLE001 - the harness must never hide a capability
            row = {
                "capability": spec.cap,
                "verdict": BLOCKED_PREFIX + f"audit_harness_error:{type(exc).__name__}:{exc}"[:200],
                "verdict_reason": "audit_harness_error",
                "executor": {},
            }
        row["audit_seconds"] = round(time.monotonic() - started, 2)
        (out_dir / "receipts" / f"{spec.cap}.json").write_text(
            json.dumps(row, indent=2, default=str), encoding="utf-8"
        )
        rows.append(row)
    for cap, note in RETIRING_CAPABILITIES.items():
        if only and cap not in only:
            continue
        rows.append(retiring_row(cap, note))
    executor_only: dict[str, Any] = {}
    if not only or "executor_only" in only:
        keys = executor_only_keys()
        eo_rows: list[dict[str, Any]] = []
        for key in sorted(EXECUTOR_ONLY):
            try:
                eo_rows.append(audit_executor_only(key, work_root))
            except Exception as exc:  # noqa: BLE001 - never hide a key
                eo_rows.append({
                    "executor_key": key,
                    "verdict": UNREACHABLE_NO_PLANNER_NODE,
                    "kind": EXECUTOR_ONLY[key]["kind"],
                    "does": EXECUTOR_ONLY[key]["does"],
                    "audit_error": f"{type(exc).__name__}: {exc}"[:300],
                })
        eo_verdicts: dict[str, int] = {}
        for eo_row in eo_rows:
            eo_verdicts[str(eo_row.get("verdict"))] = (
                eo_verdicts.get(str(eo_row.get("verdict")), 0) + 1
            )
        executor_only = {
            "keys": keys,
            "rows": eo_rows,
            "verdict_counts": eo_verdicts,
            "kind_counts": {
                kind: sum(1 for r in eo_rows if r.get("kind") == kind)
                for kind in sorted({str(r.get("kind")) for r in eo_rows})
            },
        }
    matrix: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_head": git_head(),
        "model_probe": model,
        "policies": {
            p.name: {"env": dict(p.env), "note": p.note}
            for p in (
                POLICY_PRODUCTION,
                POLICY_LOCAL_MODEL,
                POLICY_EXTERNAL_FLAG,
                POLICY_COMMITTEE_FLAG,
            )
        },
        "forcing_knob": "route-oracle line 'Expected capability receipts: <node>' in task_statement via plan_canonical_task_bundle",
        "online_channel": "deterministic no-model stand-in; Workforce binding from WorkforcePolicyLoader.resolve_route('fast_bounded_implementation')",
        "claim_boundary_note": "receipt_claims_simulated is derived by the runtime from execution evidence (nexus-runtime #187); REAL_UNATTESTED = executor ran and the artifact assertion passed but the producer still reports simulated=true",
        "rows": rows,
        "verdict_counts": {},
        "executor_only": executor_only,
    }
    counts: dict[str, int] = {}
    for row in rows:
        counts[verdict_bucket(row["verdict"])] = counts.get(verdict_bucket(row["verdict"]), 0) + 1
    matrix["verdict_counts"] = counts
    if not only:
        try:
            matrix["route_smoke_probe"] = smoke_probe(work_root / "smoke_probe")
        except Exception as exc:  # noqa: BLE001
            matrix["route_smoke_probe"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
        if smoke_summary and smoke_summary.is_file():
            payload = read_json(smoke_summary)
            matrix["route_smoke_run"] = {
                "summary_path": str(smoke_summary),
                "passed": payload.get("passed"),
                "suites": [
                    {
                        "suite": s.get("suite"),
                        "tasks": s.get("tasks"),
                        "failures": len(s.get("failures", [])),
                    }
                    for s in payload.get("suites", [])
                ],
            }
    (out_dir / "matrix.json").write_text(
        json.dumps(matrix, indent=2, default=str), encoding="utf-8"
    )
    table = markdown_table(rows)
    if executor_only.get("rows"):
        table += "\n\n" + executor_only_table(executor_only["rows"])
    (out_dir / "matrix.md").write_text(table + "\n", encoding="utf-8")
    matrix["_out_dir"] = str(out_dir)
    matrix["_table"] = table
    return matrix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capability wiring audit (planner -> registry -> executor)."
    )
    parser.add_argument(
        "--only",
        default="",
        help="comma-separated capability ids ('executor_only' = the executor-registry keys with no planner node)",
    )
    parser.add_argument("--out-root", default="artifacts/runtime/wiring_audit")
    parser.add_argument(
        "--no-model",
        action="store_true",
        help="skip model-dependent capabilities (MODEL_UNAVAILABLE)",
    )
    parser.add_argument("--list", action="store_true", help="list audited capability ids and exit")
    parser.add_argument(
        "--smoke-summary", default="", help="capability_route_smoke summary json to embed"
    )
    args = parser.parse_args(argv)
    if args.list:
        print("\n".join([*SPECS, *RETIRING_CAPABILITIES, "executor_only"]))
        return 0
    only = [item.strip() for item in args.only.split(",") if item.strip()] or None
    out_root = Path(args.out_root)
    if not out_root.is_absolute():
        out_root = REPO_ROOT / out_root
    matrix = run_audit(
        only,
        out_root,
        allow_model=not args.no_model,
        smoke_summary=Path(args.smoke_summary) if args.smoke_summary else None,
    )
    print(matrix["_table"])
    print(f"\nverdict counts: {json.dumps(matrix['verdict_counts'], sort_keys=True)}")
    print(f"matrix: {matrix['_out_dir']}/matrix.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
