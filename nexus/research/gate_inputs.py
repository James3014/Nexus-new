"""Gate inputs for the sprint's UnifiedRuntime request (wiring PR-4).

The preflight gates (pregate, harness_preflight_sensor, plan_quality_gate, mempalace_gate,
memory, codeintel) refuse with a missing-input code when the request carries no inputs.  The
sprint already knows every input they need from its own task contract: the task statement,
the target file, and the visible test with the exact pytest command the sprint runs on it.
This module derives those inputs (never from a hidden test) and records where each came from.

Inputs travel through the existing request objects only: ``request.codeintel`` (the keys the
registry invoker already reads, same shapes as ``nexus/engine/canonical_task_seam.py``) and
``route["workspace_root"]``.  None of these keys is rendered into the model prompt: the
CodeIntel prompt summary reads other fields, and the strict lane withholds the gates'
verdicts from the evidence block (``online_nexus_context``).
"""

from __future__ import annotations

import ast
import functools
import hashlib
import os
import re
import shlex
from pathlib import Path
from typing import Any, Mapping

GATE_INPUTS_ENV = "NEXUS_SPRINT_GATE_INPUTS"
GATE_INPUT_PROVENANCE_KEY = "gate_input_provenance"
MEMPALACE_TENANT = "sprint-task-contract"
MEMPALACE_ARTIFACT_TYPE = "sprint_task_contract"
VERIFY_TIMEOUT_SEC = 60
# Capabilities whose missing inputs this module supplies.  In the strict (symmetric) lane their
# verdicts are withheld from the model prompt (online_nexus_context).
FED_CAPABILITIES: frozenset[str] = frozenset({
    "pregate",
    "harness_preflight_sensor",
    "plan_quality_gate",
    "mempalace_gate",
    "memory",
    "codeintel",
})
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Fields ``compact_codeintel_for_prompt`` renders into ``[NEXUS CODEINTEL SUMMARY]`` (and the
# planner reads ``impact_report_present``): never part of the gate inputs.
FORBIDDEN_CODEINTEL_KEYS: frozenset[str] = frozenset({
    "scan_report_present",
    "impact_report_present",
    "risk_score",
    "risk_reason",
    "impacted_files_count",
    "impacted_symbols_count",
    "dci_evidence_count",
    "dci_locator_report_path",
})


def fed_capability_names() -> frozenset[str]:
    """``FED_CAPABILITIES`` plus every executor-registry alias (e.g. ``mempalace``)."""

    from nexus.services.capability_registry import EXECUTOR_REGISTRY_ALIASES

    return FED_CAPABILITIES | frozenset(
        EXECUTOR_REGISTRY_ALIASES[name]
        for name in FED_CAPABILITIES
        if name in EXECUTOR_REGISTRY_ALIASES
    )


def pregate_verify_argv(root: Path, test_file: str) -> list[str]:
    """pregate's pinned pytest invocation of exactly one visible test file.

    No configuration is discovered from the workspace: ``-c os.devnull`` (no pytest.ini /
    pyproject / setup.cfg, so no ``addopts`` or ``testpaths`` can add the hidden test),
    ``--noconftest`` (no conftest.py hooks), ``--rootdir`` pinned to the test's directory and
    no cache.  ``--`` ends the options before the single test path.
    """

    import sys

    rootdir = (Path(root) / test_file).parent
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--maxfail=1",
        "-p",
        "no:cacheprovider",
        "--noconftest",
        "-c",
        os.devnull,
        f"--rootdir={rootdir}",
        "--",
        test_file,
    ]


def _repo_regular_file(root: Path, relative: str) -> bool:
    """A repo-relative regular file: no absolute/``..`` path, no symlink in any component,
    resolving inside ``root``."""

    candidate = Path(relative)
    if not relative or candidate.is_absolute() or ".." in candidate.parts:
        return False
    current = root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            return False
    try:
        current.resolve().relative_to(root)
    except ValueError:
        return False
    return current.is_file()


RECEIPT_ONLY_ROUTE_KEY = "receipt_only_capabilities"


@functools.lru_cache(maxsize=1)
def runtime_supports_receipt_only() -> bool:
    """True when the installed nexus-runtime honours the strict-lane receipt-only declaration.

    Feature-detected on the runtime's own contract (nexus-runtime #217):
    ``capability_evidence_bundle.RECEIPT_ONLY_ROUTE_KEY == "receipt_only_capabilities"``,
    ``CONSUMER_VISIBILITY_RECEIPT_ONLY == "receipt_only"`` and a callable
    ``receipt_only_capability_names``.  Any import or contract mismatch means an older pin.

    The names alone do not prove the runtime acts on the declaration, so the detection is
    also behavioural (``_receipt_only_projection_hides_declared_entry``): one in-memory
    bundle through the runtime's own route resolution, bundle sealing and Online model
    context projection.  Any exception there also means no support (fail closed).
    """

    import importlib

    try:
        bundle = importlib.import_module(
            "nexus_runtime.planning.services.capability_evidence_bundle"
        )
    except Exception:  # noqa: BLE001 - older/absent runtime: no receipt-only support
        return False
    if not (
        getattr(bundle, "RECEIPT_ONLY_ROUTE_KEY", None) == RECEIPT_ONLY_ROUTE_KEY
        and getattr(bundle, "CONSUMER_VISIBILITY_RECEIPT_ONLY", None) == "receipt_only"
        and callable(getattr(bundle, "receipt_only_capability_names", None))
    ):
        return False
    try:
        return _receipt_only_projection_hides_declared_entry(bundle)
    except Exception:  # noqa: BLE001 - any runtime error: treat as no support
        return False


_PROBE_HIDDEN = "memory"
_PROBE_VISIBLE = "receipt_only_probe_visible"


def _receipt_only_projection_hides_declared_entry(bundle: Any) -> bool:
    """Run the runtime's projection on a two-entry bundle; True only when the entry the
    route declares receipt-only is sealed ``receipt_only`` and absent from the Online
    model-context package while the undeclared entry is present (no network, no
    subprocess, in-memory only).  Both entries carry a ``consumer_payload`` with a distinct
    sentinel: the declared entry's evidence id AND payload sentinel must be absent, the
    undeclared entry's present (positive control).  Pure and cached by the caller
    (``lru_cache``); tests that patch the runtime call ``.cache_clear()``.

    The declaration is resolved through ``unified_runtime.resolve_receipt_only_capabilities``,
    the name the runtime itself calls when it seals a request's bundle.
    """

    import importlib
    import json

    unified = importlib.import_module("nexus_runtime.kernel.unified_runtime")
    projection = importlib.import_module("nexus_runtime.task_context.consumer_projection")
    declared, invalid = unified.resolve_receipt_only_capabilities({
        RECEIPT_ONLY_ROUTE_KEY: [_PROBE_HIDDEN]
    })
    if invalid is not None:
        return False
    names = [_PROBE_HIDDEN, _PROBE_VISIBLE]
    ref = "ev_receipt_only_probe_{}".format
    sentinel = {
        _PROBE_HIDDEN: "receipt-only-probe-hidden-payload-7f3c",
        _PROBE_VISIBLE: "receipt-only-probe-visible-payload-2b9e",
    }
    results = {
        name: {
            "invoked": True,
            "status": "SUCCEEDED",
            "evidence_refs": [ref(name)],
            "physical_callable": f"receipt_only_probe.{name}",
            "consumer_payload": {"result": sentinel[name], "summary": sentinel[name]},
        }
        for name in names
    }
    plan_hash = _sha256("receipt-only-probe-plan")
    sealed = bundle.build_capability_evidence_bundle(
        task_id="receipt-only-probe",
        workspace_revision="receipt-only-probe-rev",
        task_statement="receipt-only probe",
        plan_payload={},
        plan_hash=plan_hash,
        planner_decision_id="receipt-only-probe-decision",
        capability_results=results,
        selected_capabilities=names,
        receipt_only_capabilities=declared,
    )
    visibility = {e.get("name"): e.get("consumer_visibility") for e in sealed["entries"]}
    if visibility != {_PROBE_HIDDEN: "receipt_only", _PROBE_VISIBLE: None}:
        return False
    package = projection.build_online_context_package({
        "task_id": "receipt-only-probe",
        "workspace_revision": "receipt-only-probe-rev",
        "task_statement": "receipt-only probe",
        "planner_decision_id": "receipt-only-probe-decision",
        "planner": {"plan_hash": plan_hash, "selected_capabilities": names},
        "capability_evidence_bundle": sealed,
    })
    text = json.dumps(package, sort_keys=True, default=str)
    # Positive control: the projection did render evidence and payload, just not the
    # declared entry's.
    return (
        ref(_PROBE_VISIBLE) in text
        and sentinel[_PROBE_VISIBLE] in text
        and ref(_PROBE_HIDDEN) not in text
        and sentinel[_PROBE_HIDDEN] not in text
    )


def gate_inputs_env_error() -> str:
    """ "" when ``NEXUS_SPRINT_GATE_INPUTS`` is unset, ``0`` or ``1``; else the error text."""

    try:
        gate_inputs_enabled()
    except ValueError as exc:
        return str(exc)
    return ""


def gate_inputs_enabled() -> bool:
    """``NEXUS_SPRINT_GATE_INPUTS``: unset or ``1`` = on, ``0`` = off, anything else is an error.

    Parsed fail-closed like ``NEXUS_CONFINE_VISIBLE_TEST``: a misspelling never silently means
    "on".  The switch only controls feeding the inputs; the strict-lane verdict withhold
    (``online_nexus_context.withhold_fed_gate_verdicts``) and the route-only plan-quality risk
    rule stay active regardless.
    """

    raw = os.environ.get(GATE_INPUTS_ENV)
    if raw is None or raw.strip() == "1":
        return True
    if raw.strip() == "0":
        return False
    raise ValueError(f"{GATE_INPUTS_ENV} must be 0 or 1, got {raw!r}")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def target_symbol_from_visible_test(source_code: str, test_source: str) -> str:
    """First top-level function/class of the target source that the visible test names."""

    if not source_code.strip() or not test_source.strip():
        return ""
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return ""
    referenced = set(_WORD_RE.findall(test_source))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in referenced:
                return node.name
    return ""


def _route_risk_score(route: Mapping[str, Any] | None) -> int | None:
    if not isinstance(route, Mapping):
        return None
    features = route.get("route_features")
    value = features.get("risk_score") if isinstance(features, Mapping) else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return None


def sprint_gate_inputs(
    *,
    repo_root: Path,
    task: str,
    target_file: str,
    test_file: str,
    source_code: str = "",
    route: Mapping[str, Any] | None = None,
    registered_test_file: str | None = None,
) -> dict[str, Any]:
    """Return ``{"codeintel": {...}, "workspace_root": str}`` for one sprint request.

    ``codeintel[GATE_INPUT_PROVENANCE_KEY]`` maps every supplied input to its source.  An input
    that cannot be derived honestly is omitted, so its gate keeps refusing with its
    missing-input code instead of evaluating invented data.
    """

    # Imported lazily: sprint_service imports this module.
    from nexus.research.sprint_service import repo_relative_path, visible_test_target_error

    root = Path(repo_root).resolve()
    # The counted runner passes absolute in-repo paths; normalise (outside the repo -> "").
    target = repo_relative_path(root, str(target_file or ""))[0]
    test, test_rel_error = repo_relative_path(root, str(test_file or ""))
    if registered_test_file is not None:
        registered_test_file = repo_relative_path(root, registered_test_file)[0]
    task_text = str(task or "")
    provenance: dict[str, str] = {}
    codeintel: dict[str, Any] = {"workspace_root": str(root)}
    provenance["workspace_root"] = "sprint.repo_root"

    target_path = root / target if target else None
    target_exists = bool(target) and _repo_regular_file(root, target)
    if target_exists:
        codeintel["target_file"] = target
        codeintel["search_paths"] = [target]
        provenance["target_file"] = "sprint.config.target_file"
        provenance["search_paths"] = "sprint.config.target_file"

    # Visible test only: visible_test_target_error() refuses test_hidden*, directories,
    # symlinks, option-like and out-of-repo paths, so a hidden test is never named here.
    test_error = (
        test_rel_error or visible_test_target_error(root, test) if test else "missing_test_file"
    )
    registered = str(test if registered_test_file is None else registered_test_file).strip()
    if not test_error and Path(test) != Path(registered):
        # Only the task's registered visible test (SprintConfig.test_file), never another file.
        test_error = "test_file_not_registered_visible_test"
    test_source = ""
    verify_command = ""
    if not test_error:
        test_source = (root / test).read_text(encoding="utf-8", errors="replace")
        verify_command = shlex.join(pregate_verify_argv(root, test))
        codeintel["verify_commands"] = [verify_command]
        codeintel["verify_timeout_sec"] = VERIFY_TIMEOUT_SEC
        provenance["verify_commands"] = "gate_inputs.pregate_verify_argv(config.test_file)"
        provenance["verify_timeout_sec"] = "gate_inputs.VERIFY_TIMEOUT_SEC"

    if target_exists and test_source:
        source = source_code or target_path.read_text(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        symbol = target_symbol_from_visible_test(source, test_source)
        if symbol:
            codeintel["target_symbol"] = symbol
            provenance["target_symbol"] = "visible_test_reference_to_target_definition"

    # Plan-quality context from the task contract (no planner fabrication).
    checks = {
        "task_statement_present": bool(task_text.strip()),
        "target_file_exists": target_exists,
        "visible_test_valid": not test_error,
        "verify_command_present": bool(verify_command),
    }
    codeintel["intent_pass"] = bool(
        checks["task_statement_present"] and checks["target_file_exists"]
    )
    codeintel["handoff_readiness"] = round(sum(checks.values()) / len(checks), 4)
    provenance["intent_pass"] = "task_contract:task_statement_present+target_file_exists"
    provenance["handoff_readiness"] = "task_contract:fraction_of_checks(" + ",".join(checks) + ")"
    # risk_score is read by the plan-quality invoker from the request route (route_features),
    # never copied into codeintel: the CodeIntel prompt summary renders codeintel.risk_score.
    if _route_risk_score(route) is not None:
        provenance["risk_score"] = "flow_route.route_features.risk_score"
    if target_exists:
        codeintel["target_files"] = [target]
        codeintel["deliverables"] = [target]
        provenance["target_files"] = "sprint.config.target_file"
        provenance["deliverables"] = "sprint.config.target_file"
        steps = [f"apply one model edit to {target}"]
        if verify_command:
            steps.append(f"run the visible test {test}")
        codeintel["steps"] = steps
        provenance["steps"] = "sprint.procedure(edit_target,run_visible_test)"
    if target_exists and not test_error:
        codeintel["acceptance_criteria"] = [f"visible test {test} passes"]
        codeintel["impact_map"] = {"edges": [{"source": target, "covered_by": test}]}
        provenance["acceptance_criteria"] = "task_contract.visible_test"
        provenance["impact_map"] = "task_contract.visible_test_covers_target"

    # MemPalace artifact: the task contract itself (hashes and paths, no answer text).
    if target_exists and task_text.strip():
        artifact_id = (
            "sprint-contract-"
            + _sha256("\n".join((task_text, target, test, _sha256(test_source))))[:24]
        )
        codeintel["mempalace_tenant_id"] = MEMPALACE_TENANT
        codeintel["mempalace_artifact_type"] = MEMPALACE_ARTIFACT_TYPE
        codeintel["mempalace_artifact"] = {
            "artifact_id": artifact_id,
            "task_statement_sha256": _sha256(task_text),
            "target_file": target,
            "visible_test_file": test if not test_error else "",
            "visible_test_sha256": _sha256(test_source) if test_source else "",
        }
        codeintel["mempalace_query"] = artifact_id
        for key in (
            "mempalace_tenant_id",
            "mempalace_artifact_type",
            "mempalace_artifact",
            "mempalace_query",
        ):
            provenance[key] = "task_contract.artifact"

    for key in FORBIDDEN_CODEINTEL_KEYS:
        codeintel.pop(key, None)
    codeintel[GATE_INPUT_PROVENANCE_KEY] = provenance
    return {"codeintel": codeintel, "workspace_root": str(root)}
