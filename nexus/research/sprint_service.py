from __future__ import annotations

import contextvars
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import warnings
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, cast

from nexus.core.outcome_schema import SprintOutcome
from nexus.engine.autoreason_service import AutoreasonService
from nexus.engine.ddtree_adapter import DDTreeAdapter
from nexus.engine.learning_policy_loader import route_cost_controls_from_env
from nexus.engine.policies.research_policy import ResearchPolicy
from nexus.research import bench_treatment_lane as _bench_lane
from nexus.research.candidate_pool_policy import decide_candidate_pool_policy
from nexus.research.day_shift_optimizer import DayShiftOptimizer
from nexus.research.local_sprint_mutator import (
    generate_local_companion_edits,
)
from nexus.research.swarm_broker import SwarmBroker

from .runtime.runtime_resilience import (
    RetryParams,
    classify_infra_block,
    compute_time_budget,
    get_retry_delay,
)

BENCH_WORKFORCE_BINDINGS_ENV = "NEXUS_BENCH_WORKFORCE_BINDINGS_JSON"


def _bench_workforce_bindings_from_env() -> dict[str, Any] | None:
    """Return the lane-declared Workforce bindings (channel -> binding), or None.

    The A/B lane (scripts/bench/agy_provider.py) declares the identity it runs
    (provider + exact model) and the controls it physically supplies. The mapping is only
    forwarded to the runtime; Workforce Admission still decides ALLOW/BLOCK. A malformed
    value is ignored so admission fails closed with its own reason.
    """
    raw = str(os.environ.get(BENCH_WORKFORCE_BINDINGS_ENV, "") or "").strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) and value else None


def _truncate_redundant_tests(test_source: str, task_desc: str) -> str:
    """
    🧬 動態測試程式碼裁剪 (Test Snippet Truncation)
    在 test_source 中，僅保留與當前 task_desc 相關的測試函數，
    其餘無關測試函數以 ... 代替，大幅節省 In-Context Token。
    """
    lines = test_source.splitlines()
    if len(lines) <= 80:
        return test_source
        
    import re
    test_func_pattern = re.compile(r"^( {0,4})def (test_[A-Za-z0-9_]+)\b")
    task_desc_lower = task_desc.lower()
    
    test_funcs: list[dict[str, Any]] = []
    current_func: dict[str, Any] | None = None
    
    for idx, line in enumerate(lines):
        match = test_func_pattern.match(line)
        if match:
            if current_func:
                current_func["end"] = idx
                test_funcs.append(current_func)
            indent = len(match.group(1))
            name = match.group(2)
            current_func = {"name": name, "start": idx, "end": len(lines), "indent": indent}
        elif current_func and line.strip() and not line.startswith(" " * (current_func["indent"] + 1)):
            if not line.startswith(" ") and not line.startswith(")") and not line.startswith("]"):
                current_func["end"] = idx
                test_funcs.append(current_func)
                current_func = None
                
    if current_func:
        test_funcs.append(current_func)
        
    to_keep_indices: set[int] = set()
    matched_any = False
    
    for func in test_funcs:
        func_name_lower = func["name"].lower()
        words = [w for w in func_name_lower.split("_") if len(w) > 3]
        if func_name_lower in task_desc_lower or (words and any(w in task_desc_lower for w in words)):
            matched_any = True
            for i in range(func["start"], func["end"]):
                to_keep_indices.add(i)
                
    if not matched_any:
        return test_source
        
    new_lines: list[str] = []
    in_truncated_block = False
    first_test_start = test_funcs[0]["start"] if test_funcs else len(lines)
    
    for i in range(first_test_start):
        new_lines.append(lines[i])
        
    for idx in range(first_test_start, len(lines)):
        if idx in to_keep_indices:
            new_lines.append(lines[idx])
            in_truncated_block = False
        else:
            if not in_truncated_block:
                new_lines.append("    # ... [Nexus: Truncated other passing tests to save 70% Token cost] ...")
                in_truncated_block = True
                
    return "\n".join(new_lines) + "\n"


def _compile_candidate_or_warning(code: str, filename: str) -> str:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", SyntaxWarning)
        compile(code, filename, "exec")
    for warning in caught:
        if issubclass(warning.category, SyntaxWarning):
            return str(warning.message)
    return ""


def guard_syntax_rejection(code: str) -> str:
    """The semantic guard's syntax rejection for ``code`` ("" when it compiles cleanly)."""
    try:
        syntax_warning = _compile_candidate_or_warning(code, "<semantic_guard>")
    except SyntaxError as exc:
        return f"syntax_error: {exc}"
    if syntax_warning:
        return f"syntax_warning: {syntax_warning}"
    return ""


def executor_syntax_rejection(code: str, filename: str) -> str:
    """The in-place executor's syntax rejection for ``code`` ("" when it compiles cleanly)."""
    try:
        syntax_warning = _compile_candidate_or_warning(code, filename)
    except SyntaxError as exc:
        return f"syntax_error:{exc.msg}"
    if syntax_warning:
        return f"syntax_warning:{syntax_warning}"
    return ""


def syntax_rejection_lines(code: str, filename: str = "candidate.py") -> set[str]:
    """Every syntax rejection text the sprint can put into a failure tail for ``code``.

    The bench prompt audit allows exactly these lines in a later treatment round (shared helper,
    so the audit and the product can never drift apart).
    """
    return {line for line in (guard_syntax_rejection(code), executor_syntax_rejection(code, filename)) if line}


def visible_timeout_line_re(python: str, visible_test_arg: str | None = None) -> "re.Pattern[str]":
    """``str(subprocess.TimeoutExpired)`` of the sprint's visible test run, bound EXACTLY (PR-3).

    ``python`` is the interpreter the product process runs with (its ``sys.executable``, which
    the bench runner chose when it launched the product); nothing about it is pattern-matched.
    Counted lane: the seam's confined argv ``[python, -I, -m, pytest, -q, --maxfail=1,
    *PINNED_PYTEST_ARGS]``. In-place form (``sprint_pytest_cmd``): ``[python, -m, pytest, -q,
    --maxfail=1, --, <visible test as the product received it>]``. Only the seconds vary.
    Without an interpreter the pattern matches nothing.
    """
    from nexus.services.post_candidate_seam import PINNED_PYTEST_ARGS

    if not python:
        return re.compile(r"(?!)")
    forms = [str([python, "-I", "-m", "pytest", "-q", "--maxfail=1", *PINNED_PYTEST_ARGS])]
    if visible_test_arg:
        forms.append(str([python, "-m", "pytest", "-q", "--maxfail=1", "--", visible_test_arg]))
    alternatives = "|".join(re.escape(" ".join(f"Command '{form}'".split())) for form in forms)
    return re.compile(rf"^(?:{alternatives}) timed out after [0-9]+(?:\.[0-9]+)? seconds$")


@dataclass
class SprintConfig:
    task: str
    target_file: str
    test_file: Optional[str] = None
    candidate_count: int = 3
    max_rounds: int = 5
    timeout_sec: int = 60
    safe_mode: bool = True
    stage1_max_parallel: int = 1
    stage1_timeout_sec: int = 20
    llm_mode: bool = False
    enable_autoreason_executor: bool | None = None
    enable_ddtree_executor: bool | None = None
    ddtree_max_candidates: int = 2
    distant_scout_plan: dict[str, Any] = field(default_factory=dict)
    # "online" (gateway provider) or "local" (Workforce-admitted ollama worker, armored lane).
    llm_channel: str = "online"
    # Verified candidates to collect before safe mode may stop early (1 = stop at first pass).
    min_candidate_pool: int = 1
    # Task signals from the flow's route decision, forwarded to the mainchain planner
    # (see ``planner_route_signals``); empty keeps the bare online route.
    route_signals: dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateEval:
    seed: int
    score: float
    cost: float = 1.0
    hint: str = ""
    error: str = ""
    stdout: str = ""
    candidate_code: str = ""
    source: str = "local"
    elapsed_sec: float = 0.0


# Task signals forwarded from the flow's route decision onto the mainchain request route.
# ``route_features`` is the only route field the canonical planning seam projects into the
# CapabilityPlanner (``CanonicalTaskContext.route_features``); ``should_research`` stays on
# the request route where the escalate gate reads it.  ``recommended_flow`` / ``escalate``
# are deliberately absent: they are escalation switches, not task evidence.
PLANNER_ROUTE_SIGNAL_KEYS: tuple[str, ...] = ("should_research", "route_features")
# Mirrors the canonical seam's fail-closed key rule (nexus_runtime canonical_execution
# ``_forbidden_context_key``): such keys are selection/authority inputs, not task facts, and
# the seam rejects the whole request when one is present.
_CANONICAL_FORBIDDEN_EXACT = frozenset(
    {
        "capability_stack",
        "execution_topology",
        "fallback_provider",
        "preferred_provider",
        "selected_capabilities",
        "selected_route",
        "isolated_target",
        "target",
        "target_id",
        "target_path",
        "target_ref",
        "target_worktree",
    }
)
_CANONICAL_FORBIDDEN_FRAGMENTS = ("lane", "lifecycle", "model", "provider", "route", "worker", "world")


def _canonical_fact_key_allowed(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized not in _CANONICAL_FORBIDDEN_EXACT and not any(
        fragment in normalized for fragment in _CANONICAL_FORBIDDEN_FRAGMENTS
    )


def _canonical_fact_tree(value: Any, depth: int = 0) -> Any:
    """JSON-only copy with canonical-forbidden keys dropped (bounded depth/width)."""

    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    if depth >= 3:
        return None
    if isinstance(value, Mapping):
        return {
            str(k): _canonical_fact_tree(v, depth + 1)
            for k, v in list(value.items())[:64]
            if isinstance(k, str) and _canonical_fact_key_allowed(k)
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_fact_tree(v, depth + 1) for v in list(value)[:32]]
    return None


def _gate_inputs_enabled() -> bool:
    from nexus.research.gate_inputs import gate_inputs_enabled

    return gate_inputs_enabled()


def _gate_inputs_active_for_lane() -> bool:
    """Feed the gate inputs?  Non-strict: the switch.  Strict: the switch AND runtime support for
    receipt-only evidence (otherwise design A: the strict lane sends nothing)."""
    if not _symmetric_prompt_mode():
        return _gate_inputs_enabled()
    from nexus.research.gate_inputs import gate_inputs_env_error, runtime_supports_receipt_only

    # Strict lane: an invalid switch never fails the with-Nexus arm (the counted runner refuses
    # to start on it); it means "not fed", like an older runtime.
    if gate_inputs_env_error() or not _gate_inputs_enabled():
        return False
    return runtime_supports_receipt_only()


def planner_route_signals(route: Mapping[str, Any] | None) -> dict[str, Any]:
    """Bounded copy of the flow route's task signals for the mainchain request route."""

    if not isinstance(route, Mapping):
        return {}
    out: dict[str, Any] = {}
    if "should_research" in route:
        out["should_research"] = bool(route.get("should_research"))
    features = route.get("route_features")
    if isinstance(features, Mapping):
        out["route_features"] = _canonical_fact_tree(features)
    return out


class LLMCandidateError(RuntimeError):
    def __init__(self, category: str, metadata: dict[str, Any]):
        super().__init__(category)
        self.metadata = metadata


@dataclass
class SprintResult:
    status: str
    reason: str
    target_file: str
    winner_source: str
    final_score: float
    elapsed_sec: float
    attempt_count: int
    model_calls: int
    quota_backoffs: int
    test_timeouts: int
    total_tokens: int = 0
    token_capture_status: str = "not_applicable_local_only"
    gateway_stats_present: bool = False
    gateway_usage_metadata_present: bool = False
    gateway_token_source: str = "missing"
    gateway_error_category: str = ""
    gateway_prompt_chars: int = 0
    gateway_payload_chars: int = 0
    gateway_total_chars: int = 0
    gateway_timeout_sec: int = 0
    gateway_total_sec: float = 0.0
    gateway_invocation_build_sec: float = 0.0
    gateway_process_sec: float = 0.0
    gateway_provider_wait_sec: float = 0.0
    gateway_parse_sec: float = 0.0
    executor_selected: str = ""
    executor_forced_inplace: bool = False
    executor_init_sec: float = 0.0
    model_name: str = ""
    model_patch_generated: bool = False
    fallback_used: bool = False
    error_codes: list[str] = field(default_factory=list)
    rejection_summary: dict[str, int] = field(default_factory=dict)
    learning_trace: dict[str, Any] = field(default_factory=dict)
    codeintel_context: dict[str, Any] = field(default_factory=dict)
    unified_runtime_receipts: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[CandidateEval] = field(default_factory=list)
    pytest_cmd: list[str] = field(default_factory=list)
    promotable: bool = False
    patch: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates"] = [asdict(c) for c in self.candidates]
        return payload


class LLMCandidateGenerator:
    source = "llm"

    def __init__(
        self,
        project_root: Path,
        safe_mode: bool,
        target_file: str = "",
        route_signals: Mapping[str, Any] | None = None,
    ):
        from nexus.services.gateway import BattlesuitGateway
        self.project_root = Path(project_root).resolve()
        self.gateway = BattlesuitGateway(project_root=self.project_root)
        self.safe_mode = safe_mode
        self.target_file = str(target_file or "").strip()
        self.local_service = None
        if os.environ.get("NEXUS_ONLINE_LOCAL_ASSIST", "").strip().lower() in {"1", "true", "yes"} and not _symmetric_prompt_mode():
            from nexus.services.local_assist_service import LocalAssistService

            self.local_service = LocalAssistService()
        self.model_chain = self._model_chain()
        self.last_unified_runtime_receipt: dict[str, Any] = {}
        self.route_signals = planner_route_signals(route_signals)
        # Visible-test evaluator bound by run_hyper_sprint (the sprint's own candidate executor,
        # whose pytest command names only the visible test file).  When set, the runtime
        # verifier stage applies the online candidate, runs the visible test and reports the
        # outcome plus the candidate sha256; the hidden test is never run here.
        self.visible_verifier: Callable[[str, int], CandidateEval] | None = None
        # Set instead of visible_verifier when the sprint's visible-test target is not a single
        # regular, non-hidden test file: the verifier then fails closed without running anything.
        self.visible_test_target_invalid: str = ""
        # Why no visible_verifier was bound (e.g. confinement unavailable); reported verbatim.
        self.visible_verifier_unbound_reason: str = ""
        # Visible test file of the sprint task (bound by run_hyper_sprint).  The runtime's
        # preflight gates get their inputs from it (wiring PR-4, nexus.research.gate_inputs).
        self.gate_input_test_file: str = ""
        # Target file for the gate inputs when the caller (the flow's baseline path) does not
        # give the generator a target_file; never used for the Local assist request.
        self.gate_input_target_file: str = ""

    def _workspace_revision(self) -> str:
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self.project_root),
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    def _ask_unified_candidate(
        self,
        *,
        prompt: str,
        payload: str,
        task: str,
        seed: int,
        attempt: int,
        model: str,
        source_code: str = "",
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        from nexus.services.unified_runtime import UnifiedRuntimeRequest

        output_schema = {
            "status": "APPROVED | FAIL",
            "operation": "replace | append | full_patch",
            "target_snippet": "Exact existing text to replace",
            "replacement": "New text",
            "patch": "Optional full target file content fallback",
        }
        ask_unified = getattr(self.gateway, "ask_unified", None)
        revision = self._workspace_revision()
        if not revision:
            revision = f"fixture-{hashlib.sha256(str(self.project_root).encode()).hexdigest()[:12]}"

        task_id = (
            f"sprint-{hashlib.sha256(task.encode('utf-8')).hexdigest()[:12]}"
            f"-s{seed}-a{attempt}"
        )
        local_request = None
        if self.local_service is not None and self.target_file and not Path(self.target_file).is_absolute():
            from nexus.services.local_assist_service import REQUEST_SCHEMA, LocalAssistRequest

            local_request = LocalAssistRequest(
                schema=REQUEST_SCHEMA,
                task_id=task_id,
                parent_task_id=task_id,
                workspace_root=str(self.project_root),
                workspace_revision=revision,
                task_statement=task,
                action="advisor",
                allowed_files=(self.target_file,),
                target_file=self.target_file,
                target_symbol="",
                evidence_refs=(f"sprint:{task_id}:local_request",),
            )

        from nexus.services.unified_runtime import build_online_route, extract_online_stage_payload

        def response_contract(context: Mapping[str, Any]) -> dict[str, Any]:
            online = context.get("online", {})
            online_map = online if isinstance(online, dict) else {}
            provider_response, _raw, _payload = extract_online_stage_payload(online_map)
            delivered = bool(provider_response)
            verdict: dict[str, Any] = {
                "task_id": task_id,
                "status": "pass" if delivered else "fail",
                "evidence": "online_candidate_payload_present" if delivered else "online_candidate_payload_missing",
                "evidence_refs": [f"verifier:{task_id}:candidate_response"],
            }
            if delivered and self.visible_verifier is None and self.visible_test_target_invalid:
                verdict.update({
                    "status": "fail",
                    "gate_passed": False,
                    # Nothing ran: not observed by the runtime's replan logic.
                    "invoked": False,
                    "evidence_refs": [],
                    "verifier_status": VISIBLE_TEST_TARGET_INVALID,
                    "evidence": f"{VISIBLE_TEST_TARGET_INVALID}:{self.visible_test_target_invalid}",
                    "visible_test_passed": False,
                })
                return verdict
            if not delivered:
                # No payload, nothing tested: not observed (no trusted failure, no replan).
                verdict.update({"invoked": False, "evidence_refs": [], "gate_passed": False})
                return verdict
            if self.visible_verifier is None:
                # No visible-test evaluator bound: the payload arrived but nothing was tested.
                # Never "pass" -- the runtime records the verifier stage as not succeeded.
                verdict.update({
                    "status": VERIFIER_STATUS_NO_VERIFIER,
                    # Nothing was tested: not invoked and no evidence ref, so the runtime's
                    # replan logic sees verifier_not_observed (untrusted, no replan).
                    "invoked": False,
                    "evidence_refs": [],
                    "gate_passed": False,
                    "evidence": "online_candidate_payload_present:no_visible_test_run",
                    "visible_test_passed": False,
                    "verifier_unbound_reason": self.visible_verifier_unbound_reason
                    or "visible_verifier_not_bound",
                })
                return verdict
            return _visible_test_verdict(
                verdict,
                context=context,
                candidate_out=_candidate_out_from_online_stage(online_map),
                source_code=source_code,
                visible_verifier=self.visible_verifier,
                seed=seed,
            )

        gateway_provider = str(getattr(self.gateway, "oauth_provider", "") or "").strip().lower()
        route = build_online_route(
            recommended_flow="hybrid" if local_request is not None else "direct",
            gateway_provider=gateway_provider,
            local_enabled=local_request is not None,
        )
        bench_bindings = _bench_workforce_bindings_from_env()
        if bench_bindings is not None:
            route["workforce_bindings"] = bench_bindings
        for key, value in self.route_signals.items():
            route.setdefault(key, value)
        # The sprint candidate is the with-Nexus product path: the gateway derives
        # run_mainchain(with_nexus_armor=...) from this flag, and without it the online
        # candidate ran armor-off (host-default invokers, no prompt armor).
        route.setdefault("with_nexus_armor", True)
        gate_codeintel: dict[str, Any] = {}
        # Strict (symmetric) lane: fed only when the pinned runtime honours
        # route["receipt_only_capabilities"] (nexus-runtime #217): it then seals the fed gates
        # receipt-only and keeps them out of [NEXUS MODEL CONTEXT], so the prompt does not change.
        # On an older runtime the strict lane falls back to design A (no inputs), because that
        # block would otherwise carry the passing gates' evidence ids and payloads.
        if _gate_inputs_active_for_lane():
            from nexus.research.gate_inputs import sprint_gate_inputs

            # Wiring PR-4: the preflight gates' inputs from the sprint's own task contract
            # (visible test only).  workspace_root also goes on the route, where the memory
            # invoker reads it; neither channel is rendered into the model prompt.
            gate_inputs = sprint_gate_inputs(
                repo_root=self.project_root,
                task=task,
                target_file=self.gate_input_target_file or self.target_file,
                test_file=self.gate_input_test_file,
                registered_test_file=self.gate_input_test_file,
                source_code=source_code,
                route=route,
            )
            gate_codeintel = dict(gate_inputs["codeintel"])
            route.setdefault("workspace_root", gate_inputs["workspace_root"])
        if _symmetric_prompt_mode():
            # Contract B (nexus-runtime #217): a runtime that knows this key hides these
            # capabilities' evidence from every model-facing projection at the source; the
            # pinned runtime ignores unknown route keys (tested).
            from nexus.research.gate_inputs import fed_capability_names

            route["receipt_only_capabilities"] = sorted(fed_capability_names())
        request = UnifiedRuntimeRequest(
            task_id=task_id,
            workspace_revision=revision,
            task_statement=task,
            task_type="repair",
            route=route,
            codeintel=gate_codeintel,
            online_prompt=prompt,
            online_payload=payload,
            online_phase="R",
            online_model_name=model,
            online_output_schema=output_schema,
            local_enabled=local_request is not None,
            local_request=local_request,
            evidence_refs=(f"sprint:{task_id}:request",),
        )
        receipt_path = self.project_root / ".nexus" / "reports" / "unified_runtime" / f"{task_id}.json"
        if callable(ask_unified):
            receipt = ask_unified(
                request,
                local_service=self.local_service if local_request is not None else None,
                verifier=response_contract,
                receipt_path=receipt_path,
            )
        else:
            from nexus.services.mainchain_entry import run_mainchain
            from nexus.services.unified_runtime import build_structured_online_invoker

            receipt = run_mainchain(
                request,
                online_invoker=build_structured_online_invoker(
                    self.gateway.ask_structured,
                    phase="R",
                    model_name=model,
                    output_schema=output_schema,
                    provider="fixture_gateway",
                ),
                local_service=self.local_service if local_request is not None else None,
                verifier=response_contract,
                receipt_path=receipt_path,
                with_nexus_armor=True,
            )
        unified: dict[str, Any] = dict(receipt) if isinstance(receipt, Mapping) else {}
        self.last_unified_runtime_receipt = unified
        raw_online = unified.get("online")
        online_stage: dict[str, Any] = dict(raw_online) if isinstance(raw_online, Mapping) else {}
        _provider_response, raw_response, _payload = extract_online_stage_payload(online_stage)
        return _candidate_out_from_online_stage(online_stage), raw_response, unified

    def _model_chain(self) -> list[str]:
        override = str(os.environ.get("NEXUS_GEMINI_MODEL_NAME", "") or "").strip()
        if override:
            return [override]
        return ["gemini-3-flash-preview"] if self.safe_mode else ["gemini-3-flash-preview", "gemini-3.1-pro-preview"]

    def generate(
        self,
        *,
        source_code: str,
        task: str,
        mutation_hint: str,
        seed: int,
        test_source: str = "",
        codeintel_block: str = "",
    ) -> tuple[str, dict[str, Any]]:
        prompt_text = _build_llm_candidate_prompt(
            source_code=source_code,
            task=task,
            mutation_hint=mutation_hint,
            test_source=test_source,
            codeintel_block=codeintel_block,
        )
        quota_backoffs = 0
        model_calls = 0
        last_err = ""
        for idx, model in enumerate(self.model_chain):
            try:
                model_calls += 1
                out, raw, unified_receipt = self._ask_unified_candidate(
                    prompt=prompt_text,
                    payload=_candidate_payload_instruction(),
                    task=task,
                    seed=seed,
                    attempt=idx + 1,
                    model=model,
                    source_code=source_code,
                )
                skipped_reason = _online_call_skipped_reason(unified_receipt)
                if skipped_reason:
                    # No provider process started (e.g. Workforce admission ESCALATE): not a model call.
                    model_calls -= 1
                status = str(out.get("status", "")).upper() if isinstance(out, dict) else ""
                code, edit_error = _candidate_code_from_llm_output(source_code, out if isinstance(out, dict) else {})
                tokens_used = 0
                token_capture_status = "unknown"
                if isinstance(out, dict):
                    try:
                        tokens_used = int(out.get("tokens_used", 0) or 0)
                    except (TypeError, ValueError):
                        tokens_used = 0
                    token_capture_status = str(out.get("token_capture_status", "unknown") or "unknown")
                metadata = {
                    "source": self.source,
                    "model_calls": model_calls,
                    "model_call_skipped_reason": skipped_reason,
                    "quota_backoffs": quota_backoffs,
                    "tokens_used": tokens_used,
                    "token_capture_status": token_capture_status,
                    "gateway_stats_present": bool(out.get("gateway_stats_present", False)) if isinstance(out, dict) else False,
                    "gateway_usage_metadata_present": bool(out.get("gateway_usage_metadata_present", False)) if isinstance(out, dict) else False,
                    "gateway_token_source": str(out.get("gateway_token_source") or "missing") if isinstance(out, dict) else "missing",
                    "gateway_error_category": str(out.get("error_category") or "") if isinstance(out, dict) else "",
                    "gateway_prompt_chars": int(out.get("gateway_prompt_chars", 0) or 0) if isinstance(out, dict) else 0,
                    "gateway_payload_chars": int(out.get("gateway_payload_chars", 0) or 0) if isinstance(out, dict) else 0,
                    "gateway_total_chars": int(out.get("gateway_total_chars", 0) or 0) if isinstance(out, dict) else 0,
                    "gateway_timeout_sec": int(out.get("gateway_timeout_sec", 0) or 0) if isinstance(out, dict) else 0,
                    "gateway_total_sec": float(out.get("gateway_total_sec", 0.0) or 0.0) if isinstance(out, dict) else 0.0,
                    "gateway_invocation_build_sec": float(out.get("gateway_invocation_build_sec", 0.0) or 0.0) if isinstance(out, dict) else 0.0,
                    "gateway_process_sec": float(out.get("gateway_process_sec", 0.0) or 0.0) if isinstance(out, dict) else 0.0,
                    "gateway_provider_wait_sec": float(out.get("gateway_provider_wait_sec", 0.0) or 0.0) if isinstance(out, dict) else 0.0,
                    "gateway_parse_sec": float(out.get("gateway_parse_sec", 0.0) or 0.0) if isinstance(out, dict) else 0.0,
                    "model_name": model,
                    "model_patch_generated": False,
                    "llm_edit_protocol": str(out.get("operation") or "legacy_patch") if isinstance(out, dict) else "invalid",
                    "candidate_response_path": str(out.get("candidate_response_path") or "") if isinstance(out, dict) else "",
                    "unified_runtime_receipt": unified_receipt,
                    "unified_runtime_status": str(unified_receipt.get("terminal_status") or unified_receipt.get("status") or ""),
                    "unified_runtime_claim_boundary": dict(unified_receipt.get("claim_boundary") or {}),
                }
                if status == "FAIL" or not code:
                    category = str(out.get("error_category", edit_error or "llm_no_patch") if isinstance(out, dict) else "llm_no_patch")
                    raise LLMCandidateError(category, metadata)
                if tokens_used <= 0 and model_calls > 0:
                    tokens_used = _estimate_tokens(prompt_text) + _estimate_tokens(str(code))
                    token_capture_status = "estimated"
                metadata["tokens_used"] = tokens_used
                metadata["token_capture_status"] = token_capture_status
                metadata["model_patch_generated"] = True
                return code, metadata
            except Exception as exc:  # noqa: BLE001
                err = str(exc).lower()
                last_err = str(exc)
                infra_code = classify_infra_block(err)
                if infra_code == "infra_blocked:quota":
                    quota_backoffs += 1
                    delay = get_retry_delay(RetryParams(attempt=quota_backoffs, max_retries=3))
                    time.sleep(delay)
                    continue
                if idx < len(self.model_chain) - 1:
                    continue
                raise
        raise RuntimeError(last_err or "all_models_failed")


LOCAL_CANDIDATE_MODEL_ENVS = ("NEXUS_LOCAL_MODEL_EXECUTOR_MODEL", "NEXUS_LOCAL_MODEL_NAME")


def _local_online_channel_disabled(_context: Mapping[str, Any]) -> Mapping[str, Any]:
    raise RuntimeError("online_channel_disabled_for_local_sprint_candidate")


class LocalArmorCandidateGenerator:
    """Model candidates from the Workforce-admitted local worker, through the armored local lane.

    Each candidate is one ``verified-subtask`` LocalAssist request run by ``run_mainchain`` on a
    local-only route: Workforce Admission resolves the ollama worker (local channel,
    ``bounded_code_candidate``), the local model edits an isolated World C copy, and the patch is
    applied and verified in an isolated workspace. The sprint then re-scores the delivered file
    with its own pytest command. Nothing is called when the model or the worker is unbound.
    """

    source = "llm_local_armor"

    def __init__(
        self,
        project_root: Path,
        *,
        target_file: str,
        test_file: str | None,
        verifier_command: tuple[str, ...] | None = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.target_file = str(target_file or "").strip()
        self.test_file = str(test_file or "").strip()
        # Explicit verifier (e.g. (python, "repro.py")); default is pytest on the test file.
        self.verifier_command = tuple(str(item) for item in verifier_command or ())
        self.model = next(
            (str(os.environ.get(name) or "").strip() for name in LOCAL_CANDIDATE_MODEL_ENVS if str(os.environ.get(name) or "").strip()),
            "",
        )
        self.model_chain = [self.model] if self.model else []

    def _worker_binding(self) -> dict[str, Any] | None:
        from nexus.services.model_workforce_policy import WorkforcePolicyLoader

        for worker in WorkforcePolicyLoader().load().workers.values():
            if (
                worker.provider == "ollama"
                and worker.model == self.model
                and "bounded_code_candidate" in worker.roles
            ):
                return {"worker_id": worker.worker_id, "controls": list(worker.requires)}
        return None

    def _fail(self, category: str, **extra: Any) -> LLMCandidateError:
        metadata = {
            "source": self.source,
            "model_calls": int(extra.pop("model_calls", 0) or 0),
            "model_name": self.model,
            "tokens_used": 0,
            "token_capture_status": "not_captured_local_lane",
            **extra,
        }
        return LLMCandidateError(category, metadata)

    def generate(
        self,
        *,
        source_code: str,
        task: str,
        mutation_hint: str,
        seed: int,
        test_source: str = "",
        codeintel_block: str = "",
    ) -> tuple[str, dict[str, Any]]:
        if not self.model:
            raise self._fail("local_model_unbound")
        if not self.target_file or Path(self.target_file).is_absolute():
            raise self._fail("local_target_must_be_relative")
        if self.verifier_command:
            verifier_command = self.verifier_command
        elif self.test_file and (self.project_root / self.test_file).is_file():
            verifier_command = (sys.executable, "-m", "pytest", "-q", self.test_file)
        else:
            # The armored lane verifies every candidate; without a focused test there is no verifier.
            raise self._fail("local_channel_requires_test_file")
        worker = self._worker_binding()
        if worker is None:
            raise self._fail("local_worker_not_registered")

        from nexus.services.local_assist_service import (
            REQUEST_SCHEMA,
            LocalAssistRequest,
            LocalAssistService,
            build_planner_snapshot,
        )
        from nexus.services.mainchain_entry import run_mainchain
        from nexus.services.runtime_compat import UnifiedRuntimeRequest

        digest = hashlib.sha256(
            f"{task}\n{self.target_file}\n{self.project_root}".encode("utf-8")
        ).hexdigest()[:12]
        task_id = f"sprint-local-{digest}-s{int(seed)}"
        statement = task if not mutation_hint else f"{task}\n\nCandidate focus: {mutation_hint}"
        snapshot = build_planner_snapshot(
            task_statement=statement, model=self.model, topology="localheal_pipeline"
        )
        snapshot.update({"model_call_allowed": True, "mutation_allowed": True, "verifier_allowed": True})
        local_request = LocalAssistRequest(
            schema=REQUEST_SCHEMA,
            task_id=task_id,
            parent_task_id=task_id,
            workspace_root=str(self.project_root),
            workspace_revision=f"sprint-{digest}",
            task_statement=statement,
            action="verified-subtask",
            allowed_files=(self.target_file,),
            target_file=self.target_file,
            target_symbol="",
            evidence_refs=(f"sprint:{task_id}:local_request",),
            verifier_command=verifier_command,
            time_budget=240.0,
            requested_role="candidate",
            planner_snapshot=snapshot,
        )
        route = {
            "recommended_flow": "local_only",
            "online_policy": "deny",
            "workspace_root": str(self.project_root),
            "workforce_admission_enabled": True,
            "workforce_bindings": {"local": worker},
            "route_features": {"deterministic_verifier_available": True},
        }
        request = UnifiedRuntimeRequest(
            task_id=task_id,
            workspace_revision=f"sprint-{digest}",
            task_statement=statement,
            task_type="repair",
            route=route,
            online_enabled=False,
            local_enabled=True,
            local_request=local_request,
            canonical_context={"execution_world": "local_armor"},
        )
        receipt_path = self.project_root / ".nexus" / "reports" / "unified_runtime" / f"{task_id}.json"
        receipt = dict(
            run_mainchain(
                request,
                online_invoker=_local_online_channel_disabled,
                local_service=LocalAssistService(),
                receipt_path=receipt_path,
                with_nexus_armor=True,
            )
        )
        raw_local = receipt.get("local")
        local_stage: dict[str, Any] = dict(raw_local) if isinstance(raw_local, Mapping) else {}
        raw_response = local_stage.get("response")
        response: dict[str, Any] = dict(raw_response) if isinstance(raw_response, Mapping) else {}
        raw_summary = response.get("candidate_summary")
        summary: dict[str, Any] = dict(raw_summary) if isinstance(raw_summary, Mapping) else {}
        raw_verifier = response.get("verifier_summary")
        verifier_summary: dict[str, Any] = dict(raw_verifier) if isinstance(raw_verifier, Mapping) else {}
        model_calls = int(response.get("model_call_count", 0) or 0)
        evidence = {
            "unified_runtime_receipt": receipt,
            "unified_runtime_status": str(receipt.get("terminal_status") or ""),
            "unified_runtime_receipt_path": str(receipt_path),
            "local_task_id": task_id,
            "local_worker_id": str(worker.get("worker_id") or ""),
            "local_candidate_hash": str(summary.get("selected_candidate_hash") or ""),
            "local_isolated_workspace": str(summary.get("isolated_workspace") or ""),
            "local_verifier_status": str(verifier_summary.get("verifier_status") or ""),
        }
        isolated = Path(str(summary.get("isolated_workspace") or ""))
        delivered = (
            str(local_stage.get("status") or "") == "SUCCEEDED"
            and response.get("output_delivered") is True
            and summary.get("patch_apply_status") == "applied"
            and summary.get("selected_candidate_hash_matches_applied") is True
            and isolated.is_dir()
            and (isolated / self.target_file).is_file()
        )
        if not delivered:
            raise self._fail(
                str(response.get("fallback_reason") or local_stage.get("reason") or "local_candidate_not_delivered"),
                model_calls=model_calls,
                **evidence,
            )
        code = (isolated / self.target_file).read_text(encoding="utf-8")
        return code, {
            "source": self.source,
            "model_calls": model_calls,
            "quota_backoffs": 0,
            "tokens_used": 0,
            "token_capture_status": "not_captured_local_lane",
            "model_name": self.model,
            "model_patch_generated": code != source_code,
            "llm_edit_protocol": "local_armor_verified_subtask",
            **evidence,
        }


def _estimate_tokens(text: str) -> int:
    # Fallback estimate when gateway does not return token usage.
    return max(1, len(text) // 4)


_OPERATION_PAYLOAD_KEYS = frozenset({"operation", "target_snippet", "replacement", "patch"})
_OPERATION_EDIT_KEYS = ("operation", "target_snippet", "replacement", "patch", "explanation")
# Gateway telemetry a structured candidate response may carry (read by generate()).
_STRUCTURED_TELEMETRY_KEYS = (
    "tokens_used",
    "token_capture_status",
    "error_category",
    "gateway_stats_present",
    "gateway_usage_metadata_present",
    "gateway_token_source",
    "gateway_prompt_chars",
    "gateway_payload_chars",
    "gateway_total_chars",
    "gateway_timeout_sec",
    "gateway_total_sec",
    "gateway_invocation_build_sec",
    "gateway_process_sec",
    "gateway_provider_wait_sec",
    "gateway_parse_sec",
)
_JSON_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*\n(.*?)\n?```\s*$", re.DOTALL)


def _parse_operation_payload(text: str) -> Optional[dict[str, Any]]:
    """Return the edit-operation JSON object a text-only provider sent, else None.

    Text transports (agy) return the model's JSON answer as plain text. Only an object
    that carries the requested edit keys counts; anything else stays whole-file text.
    """
    body = str(text or "").strip()
    fence = _JSON_FENCE_RE.match(body)
    if fence:
        body = fence.group(1).strip()
    if not body.startswith("{"):
        return None
    try:
        parsed = json.loads(body)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict) or not (_OPERATION_PAYLOAD_KEYS & parsed.keys()):
        return None
    if "operation" in parsed and not isinstance(parsed["operation"], str):
        return None
    return parsed


def _candidate_code_from_llm_output(source_code: str, out: dict[str, Any]) -> tuple[Optional[str], str]:
    patch = out.get("patch")
    if isinstance(patch, str) and patch.strip():
        return patch, ""

    operation = str(out.get("operation") or "replace").strip().lower()
    if operation == "full_patch":
        replacement = out.get("replacement")
        if isinstance(replacement, str) and replacement.strip():
            return replacement, ""
        return None, "llm_missing_full_patch"
    if operation not in {"replace", "append"}:
        return None, "llm_invalid_edit_operation"

    replacement = out.get("replacement")
    if not isinstance(replacement, str):
        return None, "llm_missing_replacement"

    if operation == "append":
        separator = "" if source_code.endswith("\n") or not source_code else "\n"
        return f"{source_code}{separator}{replacement}", ""

    target = out.get("target_snippet")
    if not isinstance(target, str) or not target:
        return None, "llm_missing_target_snippet"
    if source_code.count(target) != 1:
        return None, "llm_target_snippet_not_unique"
    return source_code.replace(target, replacement, 1), ""


def _candidate_out_from_online_stage(online_stage: Mapping[str, Any]) -> dict[str, Any]:
    """The candidate edit payload carried by a UnifiedRuntime online stage."""
    from nexus.services.unified_runtime import extract_online_stage_payload

    provider_response, _raw, _payload = extract_online_stage_payload(dict(online_stage))
    stage_status = "APPROVED" if online_stage.get("status") == "SUCCEEDED" else "FAIL"
    if isinstance(provider_response, dict):
        # Whitelisted edit + gateway telemetry keys only; status comes from the stage
        # (tighten-only: a structured FAIL stays FAIL), like the text path.
        structured = {
            key: provider_response[key]
            for key in (*_OPERATION_EDIT_KEYS, *_STRUCTURED_TELEMETRY_KEYS)
            if key in provider_response
        }
        own_status = str(provider_response.get("status") or "").strip().upper()
        structured["status"] = "FAIL" if own_status == "FAIL" else stage_status
        structured["candidate_response_path"] = "structured"
        return structured
    parsed = _parse_operation_payload(str(provider_response or ""))
    if parsed is not None:
        # Model text is untrusted: keep only the edit keys; status and path come from code.
        operation = {key: parsed[key] for key in _OPERATION_EDIT_KEYS if key in parsed}
        operation["status"] = stage_status
        operation["candidate_response_path"] = "operation_json"
        return operation
    # Not an edit-operation payload: keep the legacy whole-file fallback.
    return {"status": stage_status, "patch": str(provider_response or ""), "candidate_response_path": "whole_file_text"}


VISIBLE_TEST_TARGET_INVALID = "visible_test_target_invalid"
VERIFIER_STATUS_NO_VERIFIER = "no_verifier"
VISIBLE_TEST_CONFINEMENT_UNAVAILABLE = "visible_test_confinement_unavailable"
CONFINE_VISIBLE_TEST_ENV = "NEXUS_CONFINE_VISIBLE_TEST"


def confined_visible_evaluator(executor: Any) -> Callable[..., CandidateEval] | None:
    """The executor's confined visible-test entry point, or None.

    Explicit contract: the runtime verifier executes model-produced code only through an
    executor method ``evaluate_candidate_confined(*, seed, hint, code, source)`` (implemented
    for ``InPlaceSprintExecutor`` by #2211, routed to its confined runner) and only with the
    opt-in ``NEXUS_CONFINE_VISIBLE_TEST=1``.  Plain ``evaluate_candidate`` is never used by the
    verifier.
    """
    if os.environ.get(CONFINE_VISIBLE_TEST_ENV, "").strip() != "1":
        return None
    method = getattr(executor, "evaluate_candidate_confined", None)
    return cast("Callable[..., CandidateEval]", method) if callable(method) else None


def _symlinked_component(repo_root: Path, relative: Path) -> bool:
    """True when any directory between ``repo_root`` and ``relative`` is a symlink."""
    current = Path(repo_root)
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            return True
    return False


_HIDDEN_TEST_STEMS = frozenset({"hidden", "test_hidden", "hidden_test", "hidden_tests"})
_HIDDEN_TEST_DIRS = frozenset({"hidden", "test_hidden", "hidden_tests", "hidden_test"})


def _names_hidden_test(candidate: Path) -> bool:
    """A hidden-verifier file or a file inside a hidden-test directory.

    Basename ``test_hidden*`` / ``hidden_test*`` or stem exactly a hidden name; a directory
    component exactly ``hidden``/``test_hidden``/``hidden_tests``/``hidden_test`` (case-
    insensitive).  Not a substring match: task ids such as ``nexus-value-hidden-001`` are
    ordinary directories.
    """
    name = candidate.name.lower()
    if name.startswith(("test_hidden", "hidden_test")) or Path(name).stem in _HIDDEN_TEST_STEMS:
        return True
    return any(part.lower() in _HIDDEN_TEST_DIRS for part in candidate.parts[:-1])


def repo_relative_path(repo_root: Path, raw: str) -> tuple[str, str]:
    """``(repo-relative path, error)`` for a task file given relative or as an in-repo absolute path.

    The counted A/B runner passes ``--target-file/--test-file`` as absolute paths.  An absolute
    path is accepted only when it lies lexically inside ``repo_root`` (as given or resolved)
    and no component between the repo root and the file is a symlink; it is then returned
    relative.  Anything outside the repo is refused (``path_outside_repo``).
    """
    text = str(raw or "").strip()
    if not text:
        return "", ""  # empty stays empty; callers report it as missing
    candidate = Path(text)
    if not candidate.is_absolute():
        return text, ""
    absolute = Path(os.path.abspath(candidate))
    root = Path(repo_root)
    relative: Path | None = None
    for base in (Path(os.path.abspath(root)), root.resolve()):
        try:
            relative = absolute.relative_to(base)
            break
        except ValueError:
            continue
    if relative is None or not relative.parts:
        return "", "path_outside_repo"
    if _symlinked_component(root, relative) or (root / relative).is_symlink():
        return "", "path_has_symlink"
    try:
        (root / relative).resolve().relative_to(root.resolve())
    except ValueError:
        return "", "path_outside_repo"
    return relative.as_posix(), ""


def visible_test_target_error(repo_root: Path, test_file: str) -> str:
    """Why ``test_file`` cannot be the runtime verifier's only test target ("" when it can).

    The verifier runs exactly one explicit, visible test file: never an empty target (pytest
    would collect the current directory), a directory, a symlink, a path outside the repo or a
    hidden test (``_names_hidden_test``).
    """
    raw = str(test_file or "").strip()
    if not raw:
        return "missing_test_file"
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        return "test_file_not_repo_relative"
    if any(part.startswith("-") for part in candidate.parts):
        return "test_file_option_like"
    if _names_hidden_test(candidate):
        return "hidden_test_target"
    if candidate.suffix != ".py":
        return "test_file_not_python"
    path = Path(repo_root) / candidate
    if path.is_symlink() or _symlinked_component(Path(repo_root), candidate):
        return "test_file_is_symlink"
    if not path.is_file():
        return "test_file_not_regular_file"
    try:
        path.resolve().relative_to(Path(repo_root).resolve())
    except ValueError:
        return "test_file_outside_repo"
    return ""


def sprint_pytest_cmd(test_file: str | None) -> list[str]:
    """The sprint's candidate pytest command (one test file target when given)."""
    # ``--`` ends pytest options, so a test path is never parsed as one.
    return [sys.executable, "-m", "pytest", "-q", "--maxfail=1"] + (
        ["--", test_file] if test_file else []
    )


def visible_test_pytest_cmd(test_file: str) -> list[str]:
    """The runtime verifier's pytest command: exactly the sprint's command for that one file.

    Identical flags (``--maxfail=1``) keep a memoized verifier evaluation byte-identical to the
    sprint's own run, so the self-heal ``[FAILURE]`` tail does not depend on a memo hit.
    """
    return sprint_pytest_cmd(str(test_file))


def _visible_test_verdict(
    verdict: dict[str, Any],
    *,
    context: Mapping[str, Any],
    candidate_out: Mapping[str, Any],
    source_code: str,
    visible_verifier: Callable[[str, int], CandidateEval],
    seed: int,
) -> dict[str, Any]:
    """Runtime verifier proof: the visible-test outcome of the online candidate and its sha256.

    The postflight artifact/claim/delivery gates (online_nexus_context.evaluate_postflight_gate)
    bind ``verifier_status``, ``verifier_artifact`` (``sha256:<candidate>``), the verifier
    ``source_hash`` (the runtime's sealed evidence-bundle hash this candidate was produced
    against), ``task_id`` and ``attempt_id``.  Only the visible test runs; a failing visible test,
    an unappliable edit or an evaluator error is ``verifier_status=fail``.
    """
    out = dict(verdict)
    task_id = str(out.get("task_id") or "")
    attempt = context.get("execution_attempt")
    attempt_id = str(attempt.get("attempt_id") or "") if isinstance(attempt, Mapping) else ""
    source_hash = str(context.get("source_hash") or "")
    if source_hash:
        out["source_hash"] = source_hash
    if attempt_id:
        out["attempt_id"] = attempt_id
    out["invoked"] = True
    code, edit_error = _candidate_code_from_llm_output(source_code, dict(candidate_out))
    if not code:
        out.update({
            "status": "fail",
            "gate_passed": False,
            # The edit did not apply, so no test ran: not observed by the runtime replan logic.
            "invoked": False,
            "evidence_refs": [],
            "verifier_status": "fail",
            "evidence": f"visible_test_not_run:{edit_error or 'no_candidate_code'}",
            "visible_test_passed": False,
        })
        return out
    candidate_sha = hashlib.sha256(code.encode("utf-8")).hexdigest()
    try:
        evaluation = visible_verifier(code, seed)
        passed = float(evaluation.score) >= 1.0 and not str(evaluation.error or "")
        error = str(evaluation.error or "")[:200]
    except Exception as exc:  # noqa: BLE001 - an evaluator error is never a pass
        # The evaluator itself failed, so no test result exists: not observed (no trusted
        # verifier failure, no replan), never pass.
        out.update({
            "status": "fail",
            "gate_passed": False,
            "invoked": False,
            "evidence_refs": [],
            "verifier_status": "error",
            "evidence": "visible_test_not_run:visible_verifier_error",
            "visible_test_passed": False,
            "visible_test_error": f"visible_verifier_error:{type(exc).__name__}",
        })
        return out
    out.update({
        "status": "pass" if passed else "fail",
        "gate_passed": passed,
        "verifier_status": "pass" if passed else "fail",
        "verifier_artifact": f"sha256:{candidate_sha}",
        "candidate_hash": candidate_sha,
        "visible_test_passed": passed,
        "evidence": "visible_test_passed" if passed else "visible_test_failed",
        "evidence_refs": [
            *list(out.get("evidence_refs") or []),
            f"verifier:{task_id}:visible_test",
            f"candidate:sha256:{candidate_sha}",
        ],
    })
    if error:
        out["visible_test_error"] = error
    return out


def _online_call_skipped_reason(unified_receipt: Mapping[str, Any] | None) -> str:
    """Reason the online stage made no provider call, or "" when a call happened/unknown."""
    raw_online = unified_receipt.get("online") if isinstance(unified_receipt, Mapping) else None
    if not isinstance(raw_online, Mapping) or raw_online.get("invoked") is not False:
        return ""
    online: Mapping[str, Any] = raw_online
    raw_response = online.get("response")
    response: Mapping[str, Any] = raw_response if isinstance(raw_response, Mapping) else {}
    try:
        calls = int(online.get("provider_call_count", response.get("provider_call_count", 0)) or 0)
    except (TypeError, ValueError):
        return ""
    if calls:
        return ""
    raw_trace = online.get("context_trace")
    trace: Mapping[str, Any] = raw_trace if isinstance(raw_trace, Mapping) else {}
    authority = trace.get("gateway_invocation_authority")
    if isinstance(authority, Mapping) and str(authority.get("admission_overall_decision") or "") == "ESCALATE":
        return "admission_escalated"
    return str(online.get("reason") or response.get("error") or "online_not_invoked")


def _build_value_task_contract(*, source_code: str, task: str, test_source: str = "") -> str:
    combined = f"{task}\n{source_code}\n{test_source}".lower()
    rules: list[str] = []
    # Only generic engineering rules belong here. Fixture-specific rules (exact return values,
    # defaults, or field semantics a hidden verifier checks) are answer hints the bare arm never
    # gets, so they were removed (online A/B R2, 2026-10-14).
    if "artifact" in combined or "claim" in combined:
        rules.append("Preserve exact canonical field names from source/tests; do not invent plural or renamed fields.")
    if "phase" in combined or "evidence" in combined or "reason" in combined:
        rules.append("Use the canonical phase fields 'status', 'evidence', and 'reason' exactly when they appear in source/tests.")
    if "strict" in combined or "canonical" in combined or "config" in combined:
        rules.append("LanceDB/context rule: follow the canonical config/doc contract over older examples.")
    if not rules:
        return ""
    return "[NEXUS VALUE CONTRACT]\n" + "\n".join(f"- {rule}" for rule in rules) + "\n"


# One output instruction for both A/B arms in symmetric mode (the operation form #2101 parses):
# the with-Nexus arm gets it as the gateway payload, the bare arm at the end of its prompt.
SYMMETRIC_EDIT_INSTRUCTION = (
    "Return ONLY JSON for one edit with keys status, operation, target_snippet, replacement. "
    "Use operation=replace; target_snippet must be copied exactly from the current source and occur "
    "there once; replacement is the new text for it."
)


def _candidate_payload_instruction() -> str:
    if _symmetric_prompt_mode():
        return SYMMETRIC_EDIT_INSTRUCTION
    return "Return one small edit. Prefer operation=replace with exact target_snippet and replacement."


def _build_llm_candidate_prompt(
    *, source_code: str, task: str, mutation_hint: str, test_source: str = "", codeintel_block: str = ""
) -> str:
    compact = os.environ.get("NEXUS_GATEWAY_COMPACT_PROMPT", "").strip().lower() in {"1", "true", "yes"}
    contract_block = (
        ""
        if _symmetric_prompt_mode()
        else _build_value_task_contract(source_code=source_code, task=task, test_source=test_source)
    )
    contract_block += codeintel_block
    test_block = f"\nTests:\n{test_source}" if test_source else ""
    if _symmetric_prompt_mode():
        # The output instruction travels once, as the payload (SYMMETRIC_EDIT_INSTRUCTION); a second,
        # conflicting "prefer patch" instruction here would differ from the bare arm.
        # Candidate strategy hints ("Pivot: assume a race condition…") are keyword-picked guidance the
        # bare arm never gets; in symmetric mode every candidate is the plain baseline attempt.
        return f"Task: {task}\nHint: baseline\n{contract_block}Source:\n{source_code}{test_block}"
    if compact:
        return (
            "Return JSON. Prefer patch=<full updated target file>. "
            "If patch is not used, use operation=replace with exact target_snippet and replacement.\n"
            f"Task: {task}\n"
            f"Hint: {mutation_hint}\n"
            f"{contract_block}"
            f"Source:\n{source_code}"
            f"{test_block}"
        )
    full_test_block = f"\n[CURRENT TESTS]\n{test_source}\n" if test_source else ""
    return (
        "You are executing Stage 1 of a Hyper-Sprint (Gladiator mode).\n"
        f"Task: {task}\n"
        f"Strategy/Hint for this candidate: {mutation_hint}\n\n"
        f"{contract_block}"
        f"[CURRENT SOURCE]\n{source_code}\n\n"
        f"{full_test_block}"
        "Return ONLY JSON for one minimal edit: status, operation, target_snippet, replacement. "
        "Prefer patch with the full updated target file when hidden verifier repair is likely. "
        "Use operation=replace only when the target_snippet is exact and unique."
    )


def _resolve_token_capture_status(*, total_tokens: int, model_calls: int, statuses: set[str]) -> str:
    normalized = {str(item or "").strip().lower() for item in statuses}
    if total_tokens > 0:
        if normalized & {"measured", "ok"}:
            return "measured"
        if "estimated" in normalized:
            return "estimated"
        return "measured"
    if model_calls > 0 and normalized & {"unknown", "ok"}:
        return "missing_gateway_stats"
    return "missing" if model_calls > 0 else "not_applicable_local_only"


def _resolve_gateway_token_source(sources: set[str]) -> str:
    normalized = {str(source or "missing").strip().lower() for source in sources}
    if "stats" in normalized:
        return "stats"
    if "usage_metadata" in normalized:
        return "usage_metadata"
    return "missing"


def _is_model_owned_source(source: str) -> bool:
    normalized = str(source or "").strip().lower()
    return normalized.startswith(("llm", "model", "nexus_llm"))


def _candidate_summaries(items: list[CandidateEval], *, max_text: int = 1200) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for item in items:
        summaries.append(
            {
                "seed": item.seed,
                "score": item.score,
                "source": item.source,
                "hint": item.hint,
                "error": item.error,
                "stdout_tail": item.stdout[-max_text:] if item.stdout else "",
                "candidate_len": len(item.candidate_code or ""),
                "candidate_head": (item.candidate_code or "")[:max_text],
                "elapsed_sec": item.elapsed_sec,
            }
        )
    return summaries


def _candidate_id(item: CandidateEval) -> str:
    return f"{item.source}:{item.seed}"


def _candidate_payloads(items: list[CandidateEval]) -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": _candidate_id(item),
            "summary": item.hint,
            "score": item.score,
            "evidence_refs": [item.stdout[-400:]] if item.stdout else [],
        }
        for item in items
    ]


def _resolve_executor_flag(value: bool | None, env_name: str) -> bool:
    if value is not None:
        return bool(value)
    return os.environ.get(env_name, "").strip().lower() in {"1", "true", "yes", "on"}


def _select_candidate_with_routing_layers(
    candidates: list[CandidateEval],
    *,
    task: str,
    learning_trace: dict[str, Any],
    enable_autoreason_executor: bool | None = None,
    enable_ddtree_executor: bool | None = None,
    ddtree_max_candidates: int = 2,
) -> tuple[CandidateEval, list[CandidateEval]]:
    active = list(candidates)
    ddtree_enabled = _resolve_executor_flag(enable_ddtree_executor, "NEXUS_DDTREE_EXECUTOR")
    autoreason_enabled = _resolve_executor_flag(enable_autoreason_executor, "NEXUS_AUTOREASON_EXECUTOR")
    if ddtree_enabled:
        max_candidates = max(1, int(ddtree_max_candidates or 2))
        ddtree = DDTreeAdapter().plan(
            _candidate_payloads(active),
            task_desc=task,
            enabled=True,
            max_candidates=max_candidates,
        )
        learning_trace["ddtree"] = ddtree
        selected_ids = set(ddtree.get("selected_candidate_ids", []) or [])
        if selected_ids:
            active = [item for item in active if _candidate_id(item) in selected_ids] or active
    else:
        learning_trace["ddtree"] = {"enabled": False, "eligible": len(active) > 2, "reason": "feature_flag_disabled"}

    if autoreason_enabled:
        autoreason = AutoreasonService().run(_candidate_payloads(active), task_desc=task)
        autoreason["enabled"] = True
        learning_trace["autoreason"] = autoreason
        winner = str(autoreason.get("winner") or "")
        score_winner = max(active, key=lambda c: c.score)
        for item in active:
            if _candidate_id(item) == winner:
                if score_winner.score >= 1.0 and item.score < score_winner.score:
                    autoreason["winner_overridden_by_score_guard"] = True
                    autoreason["score_guard_winner"] = _candidate_id(score_winner)
                    autoreason["score_guard_reason"] = "verified_candidate_must_not_be_overridden_by_lower_score"
                    return score_winner, active
                if item.score >= 1.0 and not _is_model_owned_source(item.source):
                    # A verified model answer is the delivery; a local candidate with the same
                    # score must not replace it (online A/B R2, gov-002 local_hidden_shadow).
                    model_best = max(
                        (c for c in active if _is_model_owned_source(c.source)),
                        key=lambda c: c.score,
                        default=None,
                    )
                    if model_best is not None and model_best.score >= item.score:
                        autoreason["winner_overridden_by_model_delivery_guard"] = True
                        autoreason["score_guard_winner"] = _candidate_id(model_best)
                        autoreason["score_guard_reason"] = "verified_model_candidate_preferred_over_equal_local"
                        return model_best, active
                return item, active
    else:
        learning_trace["autoreason"] = {"enabled": False, "status": "DISABLED", "reason": "feature_flag_disabled"}
    return max(active, key=lambda c: c.score), active


class LocalCandidateGenerator:
    source = "local"

    def generate(self, source_code: str, task: str, mutation_hint: str, seed: int) -> tuple[str, dict[str, Any]]:
        from .local_sprint_mutator import generate_local_candidate
        code = generate_local_candidate(source_code, task, mutation_hint, seed)
        return code, {
            "source": self.source,
            "model_calls": 0,
            "quota_backoffs": 0,
            "tokens_used": 0,
            "token_capture_status": "not_applicable_local_only",
        }


class SprintExecutor:
    def __init__(self, repo_root: Path, scope_files: list[str], pytest_cmd: list[str], timeout_sec: int, task: str):
        self.repo_root = repo_root
        self.scope_files = scope_files
        self.pytest_cmd = pytest_cmd
        self.timeout_sec = timeout_sec
        self.task = task
        self.broker = SwarmBroker(repo_root)

    def evaluate_candidate(self, *, seed: int, hint: str, code: str, source: str) -> CandidateEval:
        target_rel = self.scope_files[0]
        if Path(target_rel).is_absolute():
            direct_executor = InPlaceSprintExecutor(
                repo_root=self.repo_root,
                target_file=target_rel,
                pytest_cmd=self.pytest_cmd,
                timeout_sec=self.timeout_sec,
            )
            return direct_executor.evaluate_candidate(seed=seed, hint=hint, code=code, source=source)

        # Swarm handling (Executor-specific) with timing instrumentation
        start_create = time.time()
        swarm_dir = self.broker.acquire(timeout_sec=self.timeout_sec)
        create_elapsed = time.time() - start_create

        if not swarm_dir:
            return CandidateEval(seed=seed, score=0.0, hint=hint, error="broker_timeout", source=source)

        try:
            if swarm_dir.resolve() == self.repo_root.resolve():
                swarm_executor = InPlaceSprintExecutor(
                    repo_root=self.repo_root,
                    target_file=target_rel,
                    pytest_cmd=self.pytest_cmd,
                    timeout_sec=self.timeout_sec,
                    task=self.task,
                )
                return swarm_executor.evaluate_candidate(seed=seed, hint=hint, code=code, source=source)

            start_sync = time.time()
            self.broker.sync_scope(swarm_dir, scope_files=self.scope_files)
            sync_elapsed = time.time() - start_sync

            # Use evaluator but on swarm_dir
            start_test = time.time()
            swarm_executor = InPlaceSprintExecutor(
                repo_root=swarm_dir,
                target_file=target_rel,
                pytest_cmd=self.pytest_cmd,
                timeout_sec=self.timeout_sec,
                task=self.task,
            )
            res = swarm_executor.evaluate_candidate(seed=seed, hint=hint, code=code, source=source)
            test_elapsed = time.time() - start_test

            # Record detailed timings in hint or extra (here we use CandidateEval which we'll ensure has enough fields)
            return CandidateEval(
                seed=res.seed,
                score=res.score,
                hint=f"{res.hint} | create:{create_elapsed:.2f}s sync:{sync_elapsed:.2f}s test:{test_elapsed:.2f}s",
                stdout=res.stdout,
                error=res.error,
                candidate_code=res.candidate_code,
                source=res.source,
                elapsed_sec=res.elapsed_sec
            )
        finally:
            self.broker.release(swarm_dir)

class InPlaceSprintExecutor:
    """
    Fast local executor for local-first mode.
    Applies candidate code in-place, runs scoped tests, then restores the original file.
    """

    def __init__(self, repo_root: Path, target_file: str, pytest_cmd: list[str], timeout_sec: int, task: str = ""):
        self.repo_root = repo_root
        self.target_file = target_file
        self.pytest_cmd = pytest_cmd
        self.timeout_sec = timeout_sec
        self.task = task

    def _evaluate_confined(self, **kwargs: Any) -> CandidateEval | None:
        return _inplace_evaluate_confined(self, **kwargs)

    def evaluate_candidate(self, *, seed: int, hint: str, code: str, source: str) -> CandidateEval:
        return self._evaluate(seed=seed, hint=hint, code=code, source=source, confined_only=False)

    def evaluate_candidate_confined(self, *, seed: int, hint: str, code: str, source: str) -> CandidateEval:
        """Same contract as ``evaluate_candidate`` but ALWAYS on a confined scratch copy: never
        writes the workspace; without an OS barrier it refuses (``confinement_unavailable``).
        Used by the runtime visible verifier (#2212), which runs before the seam's file_lock."""
        return self._evaluate(seed=seed, hint=hint, code=code, source=source, confined_only=True)

    def _evaluate(self, *, seed: int, hint: str, code: str, source: str, confined_only: bool) -> CandidateEval:
        from nexus.services import post_candidate_seam as seam

        start = time.time()
        target_path = self.repo_root / self.target_file
        companion_edits = generate_local_companion_edits(self.repo_root, target_path, self.task, hint, seed)
        # PR-2 seam: the lock on the target AND every companion is taken FIRST and held for the
        # whole evaluation (acquire is the check; no separate "held by another?" pre-check),
        # covering the in-place write, the test run and the restore.
        release = seam.hold_target_lock(
            self.repo_root, self.target_file, [path for path in companion_edits if path != target_path]
        )
        if release is None:
            if confined_only:
                # The runtime verifier (#2212) memoises evaluations and replays them after the
                # lock is released: a denial must never be a cacheable CandidateEval. Stop the
                # whole sprint attempt instead (caught by run_hyper_sprint, no delivery).
                raise _SprintLockDenied(lock_denied_in="runtime_verifier")
            # Another task holds the target or a companion: nothing is applied or run.
            return CandidateEval(
                seed=seed, score=0.0, hint=hint, error="file_lock_denied", candidate_code=code, source=source,
                elapsed_sec=round(time.time() - start, 4),
            )
        restored_files: dict[Path, str | None] = {}
        lock_release: list[Any] = [release]
        try:
            # Inside the try: any failure from here on still releases the lock (finally).
            original = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
            if code == original:
                return CandidateEval(
                    seed=seed,
                    score=0.2,
                    hint=hint,
                    error="no_change_candidate",
                    candidate_code=code,
                    source=source,
                    elapsed_sec=round(time.time() - start, 4),
                )
            if target_path.suffix == ".py":
                syntax_rejection = executor_syntax_rejection(code, str(target_path))
                if syntax_rejection:
                    return CandidateEval(
                        seed=seed,
                        score=0.0,
                        hint=hint,
                        error=syntax_rejection,
                        candidate_code=code,
                        source=source,
                        elapsed_sec=round(time.time() - start, 4),
                    )
            confined = self._evaluate_confined(
                seed=seed,
                hint=hint,
                code=code,
                source=source,
                original=original,
                start=start,
                companions=[path for path in companion_edits if path != target_path],
                force=confined_only,
            )
            if confined is not None:
                return confined
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(code, encoding="utf-8")
            restored_files[target_path] = original
            for extra_path, extra_code in companion_edits.items():
                if extra_path == target_path:
                    continue
                restored_files[extra_path] = extra_path.read_text(encoding="utf-8") if extra_path.exists() else None
                extra_path.parent.mkdir(parents=True, exist_ok=True)
                extra_path.write_text(extra_code, encoding="utf-8")
            res = subprocess.run(
                self.pytest_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                cwd=self.repo_root,
            )
            return CandidateEval(
                seed=seed,
                score=1.0 if res.returncode == 0 else 0.4,
                hint=hint,
                stdout=res.stdout,
                candidate_code=code,
                source=source,
                elapsed_sec=round(time.time() - start, 4),
            )
        except subprocess.TimeoutExpired as exc:
            return CandidateEval(
                seed=seed,
                score=0.0,
                hint=hint,
                error=str(exc),
                candidate_code=code,
                source=source,
                elapsed_sec=round(time.time() - start, 4),
            )
        except Exception as exc:  # noqa: BLE001
            return CandidateEval(
                seed=seed,
                score=0.0,
                hint=hint,
                error=str(exc),
                candidate_code=code,
                source=source,
                elapsed_sec=round(time.time() - start, 4),
            )
        finally:
            try:
                for path, original_text in restored_files.items():
                    if original_text is None:
                        if path.exists():
                            path.unlink()
                    else:
                        path.write_text(original_text, encoding="utf-8")
            finally:
                for release in lock_release:
                    release()


def _inplace_evaluate_confined(
    executor: "InPlaceSprintExecutor",
    *,
    seed: int,
    hint: str,
    code: str,
    source: str,
    original: str,
    start: float,
    companions: list[Path] | None = None,
    force: bool = False,
) -> CandidateEval | None:
    """Strict/counted lane: the visible test runs on a scratch copy inside the OS confinement,
    never in the workspace (None when confinement is not requested). Companion edits outside the
    target cannot be reproduced in the copy: refused (``confinement_unavailable:multi_file``)."""
    from nexus.services import post_candidate_seam as seam

    if not force and not seam.confine_visible_test_enabled():
        return None
    if companions:
        return CandidateEval(
            seed=seed, score=0.0, hint=hint, error=f"{seam.CONFINEMENT_UNAVAILABLE}:multi_file:{len(companions)}",
            candidate_code=code, source=source, elapsed_sec=round(time.time() - start, 4),
        )
    test_arg = str(executor.pytest_cmd[-1]) if executor.pytest_cmd else ""
    if not test_arg.endswith(".py"):
        return CandidateEval(
            seed=seed, score=0.0, hint=hint, error=seam.CONFINEMENT_UNAVAILABLE + ":no_visible_test",
            candidate_code=code, source=source, elapsed_sec=round(time.time() - start, 4),
        )
    test_path = Path(test_arg) if Path(test_arg).is_absolute() else executor.repo_root / test_arg
    try:
        completed, executed = seam.run_visible_test_confined(
            target_path=executor.repo_root / executor.target_file,
            visible_test_path=test_path,
            original_code=original,
            candidate_code=code,
            timeout_sec=executor.timeout_sec,
            workspace_root=executor.repo_root,
        )
    except subprocess.TimeoutExpired as exc:
        return CandidateEval(
            seed=seed, score=0.0, hint=hint, error=str(exc), candidate_code=code, source=source,
            elapsed_sec=round(time.time() - start, 4),
        )
    if not executed:
        return CandidateEval(
            seed=seed, score=0.0, hint=hint, error=str(completed.stderr)[:300], candidate_code=code, source=source,
            elapsed_sec=round(time.time() - start, 4),
        )
    return CandidateEval(
        seed=seed, score=1.0 if completed.returncode == 0 else 0.4, hint=hint, stdout=completed.stdout,
        candidate_code=code, source=source, elapsed_sec=round(time.time() - start, 4),
    )


def promote_patch_to_branch(*, repo_root: Path, target_file: str, patch_code: str, score: float, run_id: str) -> str:
    branch_name = f"hyper-sprint/{run_id}"
    subprocess.run(["git", "checkout", "-b", branch_name], cwd=repo_root, check=True, capture_output=True)
    (repo_root / target_file).write_text(patch_code, encoding="utf-8")
    subprocess.run(["git", "add", target_file], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"opt(dayshift): optimize {target_file} (score: {score})"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return branch_name


def write_sprint_report(*, repo_root: Path, result: SprintResult, report_file: str) -> Path:
    report_path = (repo_root / report_file).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return report_path


def _symmetric_prompt_mode() -> bool:
    """Like-for-like A/B mode (``NEXUS_SYMMETRIC_PROMPT``): the model sees what the bare arm sees.

    Visible tests are included, no CodeIntel/historical hints are injected, and learning stores are
    neither read nor written, so nothing carries over between trials (symmetry inventory S4-S6).
    """

    return os.environ.get("NEXUS_SYMMETRIC_PROMPT", "").strip().lower() in {"1", "true", "yes"}


class _SprintLockDenied(BaseException):
    """The target lock was refused: the sprint attempt short-circuits without any delivery.

    A BaseException on purpose: the candidate loop's broad ``except Exception`` handlers must not
    turn it into an ordinary failed candidate (which would let self-heal/rescue continue)."""

    def __init__(self, **state: Any) -> None:
        super().__init__("file_lock_denied")
        self.state = state


# Metering for a lock denial raised from deep inside the sprint (the confined executor): the
# running sprint registers a reader of its counters so the denied result still reports the
# model calls / tokens spent so far (scoring already excludes the pair).
_SPRINT_METER: contextvars.ContextVar[Callable[[], dict[str, Any]] | None] = contextvars.ContextVar(
    "nexus_sprint_meter", default=None
)


def _lock_denied_result(config: SprintConfig, state: Mapping[str, Any]) -> SprintResult:
    learning_trace = dict(state.get("learning_trace") or {})
    learning_trace["file_lock_denied"] = True
    return SprintResult(
        status="FAILED",
        reason="file_lock_denied",
        target_file=config.target_file,
        winner_source="file_lock_denied",
        final_score=0.0,
        elapsed_sec=float(state.get("elapsed_sec") or 0.0),
        attempt_count=0,
        model_calls=int(state.get("model_calls") or 0),
        quota_backoffs=0,
        test_timeouts=0,
        total_tokens=int(state.get("total_tokens") or 0),
        model_name=str(state.get("model_name") or ""),
        model_patch_generated=False,
        error_codes=["file_lock_denied"],
        learning_trace=learning_trace,
        unified_runtime_receipts=list(state.get("unified_runtime_receipts") or []),
        patch="",
    )


def _sprint_seam_task_id(repo_root: Path, config: SprintConfig) -> str:
    key = f"{Path(repo_root).resolve()}|{config.target_file}|{config.task}"
    return "auto-flow-sprint:" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _sprint_lock_denied(
    meta: Mapping[str, Any] | None, *, repo_root: Path, config: SprintConfig, learning_trace: dict[str, Any]
) -> bool:
    """PR-2 seam: lock the target before the first model candidate is written (runtime-selected
    only); True when the lock was not granted (the candidate must not be written)."""
    from nexus.services import post_candidate_seam as seam

    stages = learning_trace.setdefault("post_candidate_seam_pre_stages", [])
    if not stages:
        unified = meta.get("unified_runtime_receipt") if isinstance(meta, Mapping) else None
        _lock_task, new_stages = seam.lock_target_if_selected(
            unified_receipt=unified if isinstance(unified, Mapping) else None,
            task_id=seam.seam_holder_id(repo_root, config.target_file),
            workspace_root=repo_root,
            target_file=config.target_file,
        )
        stages.extend(new_stages)
    return seam.lock_denied(stages)


def _apply_sprint_post_candidate_seam(
    result: SprintResult,
    *,
    repo_root: Path,
    config: SprintConfig,
    original_code: str | None,
    released: Mapping[str, list[str]],
) -> None:
    """PR-2 seam after the sprint chose its candidate: sandbox/ultra_review on a scratch copy of
    the model candidate; stages are appended as a UnifiedRuntime-shaped receipt (never changes
    the outcome)."""
    from nexus.services import post_candidate_seam as seam

    pre = list(result.learning_trace.pop("post_candidate_seam_pre_stages", []) or [])
    unified = next(
        (
            item
            for item in reversed(result.unified_runtime_receipts)
            if isinstance(item, dict)
            and isinstance(item.get("capabilities"), list)
            and item.get("receipt_kind") != seam.POST_CANDIDATE_RECEIPT_KIND
        ),
        None,
    )
    task_id = _sprint_seam_task_id(repo_root, config)
    post = None
    try:
        if (
            original_code is not None
            and config.test_file
            and result.patch
            and _is_model_owned_source(result.winner_source)
            and not seam.lock_denied(pre)
        ):
            post = seam.run_seam_for_candidate(
                workspace_root=repo_root,
                task_id=task_id,
                unified_receipt=unified,
                target_path=Path(repo_root) / config.target_file,
                visible_test_path=Path(repo_root) / config.test_file,
                original_code=original_code,
                candidate_code=result.patch,
            )
    except Exception as exc:  # noqa: BLE001 - the seam never breaks the row
        result.learning_trace["post_candidate_seam_error"] = f"{type(exc).__name__}: {exc}"[:300]
    merged = seam.merge_seam_receipts(task_id=task_id, pre_stages=pre, post_receipt=post, released=released)
    if merged is not None:
        result.unified_runtime_receipts.append(merged)
        result.learning_trace["post_candidate_seam"] = [str(stage.get("name")) for stage in merged["capabilities"]]
        if seam.lock_denied(pre):
            result.learning_trace["file_lock_denied"] = True


def run_hyper_sprint(*, repo_root: Path, config: SprintConfig) -> SprintResult:
    """Hyper sprint with the PR-2 post-candidate seam around it (file_lock released after the row)."""
    target = Path(repo_root) / config.target_file
    original_code = target.read_text(encoding="utf-8") if target.is_file() else None
    from nexus.services.post_candidate_seam import seam_holder_id

    lock_task = seam_holder_id(repo_root, config.target_file)
    released: dict[str, list[str]] = {}
    try:
        meter_token = _SPRINT_METER.set(None)
        try:
            result = _run_hyper_sprint_core(repo_root=repo_root, config=config)
        except _SprintLockDenied as denied:
            meter = _SPRINT_METER.get()
            counts: dict[str, Any] = meter() if meter is not None else {}
            result = _lock_denied_result(config, {**counts, **denied.state})
        finally:
            _SPRINT_METER.reset(meter_token)
    finally:
        from nexus.services.post_candidate_seam import release_target_lock

        released = release_target_lock(lock_task)
    _apply_sprint_post_candidate_seam(
        result, repo_root=repo_root, config=config, original_code=original_code, released=released
    )
    return result


def _run_hyper_sprint_core(*, repo_root: Path, config: SprintConfig) -> SprintResult:
    start = time.time()
    policy = ResearchPolicy()
    scope_files = [config.target_file] + ([config.test_file] if config.test_file else [])
    _effective_timeout = compute_time_budget(config.timeout_sec)
    pytest_cmd = sprint_pytest_cmd(config.test_file)

    target_path = repo_root / config.target_file
    source_code = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    test_path = repo_root / config.test_file if config.test_file else None
    test_source = test_path.read_text(encoding="utf-8") if test_path and test_path.exists() and test_path.is_file() else ""
    hidden_verifier_mode = os.environ.get("NEXUS_VALUE_HIDDEN_VERIFIER", "").strip().lower() in {"1", "true", "yes"}
    model_required_execution_mode = os.environ.get("NEXUS_MODEL_REQUIRED_EXECUTION_MODE", "").strip().lower()
    model_required_final_delivery = (
        model_required_execution_mode.startswith("model_participation")
        or os.environ.get("NEXUS_REQUIRE_MODEL_PARTICIPATION", "").strip().lower() in {"1", "true", "yes"}
    )
    symmetric_prompt = _symmetric_prompt_mode()
    initial_test_source = (
        test_source if symmetric_prompt else ("" if hidden_verifier_mode and not model_required_final_delivery else test_source)
    )
    if initial_test_source and not symmetric_prompt:
        # P2-1: the bare arm gets the whole visible test, so symmetric mode never truncates it.
        initial_test_source = _truncate_redundant_tests(initial_test_source, config.task)
    llm_mode_effective = bool(config.llm_mode)
    learn_slo_guard = {
        "phase_slo_pass": False,
        "required_done_ratio": 0.0,
        "active": False,
        "reason": "",
    }
    try:
        from nexus.research.learn_mode import LearnModeService

        learn_slo = LearnModeService(repo_root).read_phase_slo_summary()
        required_done_ratio = float((learn_slo.get("global", {}) or {}).get("required_done_ratio", 0.0) or 0.0)
        phase_slo_pass = bool(learn_slo.get("phase_slo_pass", False))
        learn_slo_guard["phase_slo_pass"] = phase_slo_pass
        learn_slo_guard["required_done_ratio"] = required_done_ratio
        force_llm_for_benchmark = os.environ.get("NEXUS_FORCE_LLM_DESPITE_LEARN_SLO", "").strip().lower() in {"1", "true", "yes"}
        if llm_mode_effective and (not phase_slo_pass or required_done_ratio < 0.95) and not force_llm_for_benchmark:
            llm_mode_effective = False
            learn_slo_guard["active"] = True
            learn_slo_guard["reason"] = "learn_phase_slo_not_ready"
        elif llm_mode_effective and force_llm_for_benchmark and (not phase_slo_pass or required_done_ratio < 0.95):
            learn_slo_guard["active"] = True
            learn_slo_guard["reason"] = "benchmark_force_llm_despite_learn_slo"
    except Exception as exc:  # noqa: BLE001
        learn_slo_guard["reason"] = f"learn_slo_read_error:{exc}"

    codeintel_block = ""
    codeintel_status: dict[str, Any] = {"status": "skipped_local_only"}
    if llm_mode_effective and symmetric_prompt:
        codeintel_status = {"status": "skipped_symmetric_prompt"}
    elif llm_mode_effective:
        from nexus.research.flow.codeintel_context import sprint_codeintel_block

        codeintel_block, codeintel_status = sprint_codeintel_block(repo_root, target_file=config.target_file)

    llm_channel = str(config.llm_channel or "online").strip().lower()
    if llm_channel not in {"online", "local"}:
        raise ValueError(f"unsupported_llm_channel:{llm_channel}")
    llm_generator: Optional[LLMCandidateGenerator | LocalArmorCandidateGenerator] = None
    if llm_mode_effective and llm_channel == "local":
        llm_generator = LocalArmorCandidateGenerator(
            repo_root, target_file=config.target_file, test_file=config.test_file
        )
    elif llm_mode_effective:
        llm_generator = LLMCandidateGenerator(
            repo_root,
            config.safe_mode,
            target_file=config.target_file,
            route_signals=config.route_signals,
        )
    local_generator = LocalCandidateGenerator()
    # Local-first fast path: avoid heavy swarm sync when no external LLM is used.
    force_inplace_executor = os.environ.get("NEXUS_FORCE_INPLACE_EXECUTOR", "").strip().lower() in {"1", "true", "yes"}
    enable_local_swarm_executor = os.environ.get("NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR", "").strip().lower() in {"1", "true", "yes"}
    executor_init_start = time.monotonic()
    # The local channel already isolates every model candidate (World C + isolated apply), so the
    # sprint scores it in place instead of waiting on a swarm worktree.
    if (
        (llm_mode_effective and llm_channel != "local") or enable_local_swarm_executor
    ) and not force_inplace_executor:
        executor_selected = "swarm"
        executor = SprintExecutor(
            repo_root,
            scope_files=scope_files,
            pytest_cmd=pytest_cmd,
            timeout_sec=config.stage1_timeout_sec,
            task=config.task,
        )
    else:
        executor_selected = "inplace"
        executor = InPlaceSprintExecutor(
            repo_root=repo_root,
            target_file=config.target_file,
            pytest_cmd=pytest_cmd,
            timeout_sec=config.stage1_timeout_sec,
            task=config.task,
        )
    executor_init_sec = round(time.monotonic() - executor_init_start, 4)
    # Runtime verifier proof (wiring plan PR-1): the online candidate's verifier stage runs the
    # sprint's own visible-test evaluation (pytest_cmd names only config.test_file) and binds the
    # candidate sha256, so the runtime postflight gates evaluate real evidence.  The evaluation
    # is memoized per (candidate sha256, hint, seed) and reused by the sprint, so the visible
    # test still runs once per candidate.
    visible_verifier_binding: dict[str, Any] = {"hint": "", "seed": 0}
    visible_eval_memo: dict[tuple[str, str, int], CandidateEval] = {}

    # The counted runner passes absolute in-repo paths: normalise before the target check.
    visible_test_rel, visible_rel_error = repo_relative_path(repo_root, config.test_file or "")
    visible_target_error = visible_rel_error or visible_test_target_error(
        repo_root, visible_test_rel
    )
    # The sprint's own executor: with a valid target its command is exactly
    # visible_test_pytest_cmd(test_file) (one explicit file, same flags), so a memo hit and a
    # miss produce the same evaluation.
    if not visible_target_error and getattr(executor, "pytest_cmd", None) != visible_test_pytest_cmd(
        config.test_file or ""
    ):
        visible_target_error = "sprint_pytest_cmd_mismatch"
    confined_evaluate = confined_visible_evaluator(executor)
    # With the confined contract active, every candidate evaluation in this sprint (memo miss,
    # self-heal repair, local/preflight/shadow/support/fallback) goes through the confined
    # entry point; there is no fallback to plain evaluate_candidate.
    sprint_evaluate: Callable[..., CandidateEval] = (
        confined_evaluate if confined_evaluate is not None else executor.evaluate_candidate
    )

    def _runtime_visible_verifier(code: str, _seed: int) -> CandidateEval:
        hint_now = str(visible_verifier_binding["hint"])
        seed_now = int(visible_verifier_binding["seed"])
        if confined_evaluate is None:  # bound only when the confined method exists
            raise RuntimeError("visible_verifier_without_confined_evaluator")
        evaluation = confined_evaluate(seed=seed_now, hint=hint_now, code=code, source="llm")
        visible_eval_memo[(hashlib.sha256(code.encode("utf-8")).hexdigest(), hint_now, seed_now)] = evaluation
        return evaluation

    def _evaluate_candidate(*, seed: int, hint: str, code: str, source: str) -> CandidateEval:
        cached = visible_eval_memo.pop((hashlib.sha256(code.encode("utf-8")).hexdigest(), hint, seed), None)
        visible_eval_memo.clear()
        if cached is not None:
            return replace(cached, source=source)
        return sprint_evaluate(seed=seed, hint=hint, code=code, source=source)

    if llm_generator is not None and hasattr(llm_generator, "gate_input_test_file"):
        setattr(llm_generator, "gate_input_test_file", visible_test_rel)
    if llm_generator is not None and hasattr(llm_generator, "visible_verifier"):
        # Only the online generator has the seam (tests may substitute the generator class).
        if visible_target_error:
            setattr(llm_generator, "visible_test_target_invalid", visible_target_error)
        elif confined_evaluate is None:
            # Model code is never executed by the verifier without confinement (#2211).
            setattr(
                llm_generator,
                "visible_verifier_unbound_reason",
                VISIBLE_TEST_CONFINEMENT_UNAVAILABLE,
            )
        else:
            setattr(llm_generator, "visible_verifier", _runtime_visible_verifier)

    candidates: list[CandidateEval] = []
    routing_autoreason_enabled = _resolve_executor_flag(config.enable_autoreason_executor, "NEXUS_AUTOREASON_EXECUTOR")
    routing_ddtree_enabled = _resolve_executor_flag(config.enable_ddtree_executor, "NEXUS_DDTREE_EXECUTOR")
    route_cost_controls = route_cost_controls_from_env()
    candidate_pool_policy = decide_candidate_pool_policy(
        autoreason_enabled=routing_autoreason_enabled,
        ddtree_enabled=routing_ddtree_enabled,
        llm_mode=llm_mode_effective,
        candidate_count=config.candidate_count,
        ddtree_max_candidates=config.ddtree_max_candidates,
        route_cost_controls=route_cost_controls,
    )
    routing_min_pool = 1
    if routing_ddtree_enabled and config.candidate_count > config.ddtree_max_candidates:
        routing_min_pool = min(config.candidate_count, config.ddtree_max_candidates + 1)
    elif routing_autoreason_enabled and config.candidate_count > 1:
        routing_min_pool = 2
    routing_min_pool = max(routing_min_pool, min(config.candidate_count, max(1, int(config.min_candidate_pool or 1))))
    model_calls = 0
    model_names: set[str] = set()
    model_patch_generated = False
    fallback_used = False
    total_tokens = 0
    token_capture_statuses: set[str] = set()
    gateway_stats_present = False
    gateway_usage_metadata_present = False
    gateway_token_sources: set[str] = set()
    gateway_error_categories: set[str] = set()
    gateway_prompt_chars = 0
    gateway_payload_chars = 0
    gateway_total_chars = 0
    gateway_timeout_sec = 0
    gateway_total_sec = 0.0
    gateway_invocation_build_sec = 0.0
    gateway_process_sec = 0.0
    gateway_provider_wait_sec = 0.0
    gateway_parse_sec = 0.0
    unified_runtime_receipts: list[dict[str, Any]] = []
    quota_backoffs = 0
    test_timeouts = 0
    error_codes: list[str] = []
    learning_trace: dict[str, Any] = {
        "retrieval_hits": 0,
        "retrieval_hints": [],
        "mempalace_verified": False,
        "memory_written": False,
        "arweave_tx_id": None,
        "learn_slo_guard": learn_slo_guard,
        "llm_channel": llm_channel,
        "llm_mode_requested": bool(config.llm_mode),
        "llm_mode_effective": llm_mode_effective,
        "executor": {
            "selected": executor_selected,
            "forced_inplace": force_inplace_executor,
            "enable_local_swarm_executor": enable_local_swarm_executor,
            "init_sec": executor_init_sec,
        },
        "candidate_pool_policy": {
            "enabled": candidate_pool_policy.enabled,
            "local_support_candidates": candidate_pool_policy.local_support_candidates,
            "local_support_score_cap": candidate_pool_policy.local_support_score_cap,
            "reason_codes": list(candidate_pool_policy.reason_codes),
        },
    }
    distant_plan = config.distant_scout_plan if isinstance(config.distant_scout_plan, dict) else {}
    if distant_plan:
        learning_trace["distant_scout_execution"] = {
            "status": str(distant_plan.get("status") or ""),
            "recommended_family": str(distant_plan.get("recommended_family") or ""),
            "forbidden_families": list(distant_plan.get("forbidden_families", []) or []),
            "target_boundary": str(distant_plan.get("target_boundary") or ""),
            "applied": str(distant_plan.get("status") or "") == "READY",
        }

    def _apply_distant_scout_hint(hint: str) -> str:
        scout = learning_trace.get("distant_scout_execution")
        if not isinstance(scout, dict) or not scout.get("applied"):
            return hint
        forbidden = ",".join(str(item) for item in scout.get("forbidden_families", []) if str(item).strip())
        return "\n".join(
            item
            for item in (
                hint,
                f"distant_scout_recommended_family={scout.get('recommended_family', '')}",
                f"distant_scout_forbidden_families={forbidden}",
                f"distant_scout_target_boundary={scout.get('target_boundary', '')}",
            )
            if str(item).strip()
        )

    # Learning loop (retrieve): pull recent hints before candidate generation.
    historical_hints: list[str] = []
    try:
        from nexus.research.findings_memory import FindingsMemoryStore

        store = FindingsMemoryStore(repo_root)
        if symmetric_prompt:
            raise RuntimeError("retrieval_skipped_symmetric_prompt")
        hits = store.search(config.task, scope="both")
        learning_trace["retrieval_hits"] = len(hits)
        for h in hits:
            historical_hints.extend(h.retrieval_hints)
        historical_hints = list(dict.fromkeys(historical_hints))[:3]
        learning_trace["retrieval_hints"] = historical_hints
    except Exception as exc:  # noqa: BLE001
        learning_trace["retrieval_error"] = str(exc)
        store = None

    def _semantic_guard(source: str, candidate: str, task: str, source_label: str = "llm") -> tuple[bool, str]:
        if candidate.strip() == source.strip():
            return False, "no_change_candidate"
        
        # R7: Strict rejection for invalid AST/syntax
        syntax_rejection = guard_syntax_rejection(candidate)
        if syntax_rejection:
            return False, syntax_rejection

        src_lines = {ln.strip() for ln in source.splitlines() if ln.strip()}
        cand_lines = {ln.strip() for ln in candidate.splitlines() if ln.strip()}
        added_lines = cand_lines - src_lines
        if hidden_verifier_mode and added_lines and all(
            line.startswith("# Structural placeholder") or line.startswith("_NEXUS_TASK_SENTINEL")
            for line in added_lines
        ):
            return False, "semantic_guard_placeholder_only"
        changed_count = len(cand_lines - src_lines)
        task_l = task.lower()
        feature_words = ("implement", "add", "create", "introduce", "support", "enable")
        
        is_feature = any(w in task_l for w in feature_words)
        _is_refactor = "refactor" in task_l
        is_contract_repair = any(
            word in task_l
            for word in (
                "artifact",
                "claim",
                "evidence",
                "phase",
                "override",
                "invariant",
                "canonical",
                "contract",
            )
        )
        
        if changed_count < 1:
            return False, "semantic_guard_zero_delta"

        # R9.1: Context-aware delta requirement
        is_trusted_local = str(source_label).lower() == "local"
        
        # If it's a feature from LLM, require at least 2 lines of change to reduce low-quality hallucinations
        if is_feature and not is_contract_repair and not is_trusted_local and changed_count < 2:
            return False, "semantic_guard_low_delta_feature"
            
        return True, ""

    def _build_rejection_summary(items: list[CandidateEval], codes: list[str]) -> dict[str, int]:
        summary: dict[str, int] = {}
        for c in items:
            if c.error:
                key = c.error
                if c.error.startswith("syntax_error:"):
                    key = "syntax_error"
                elif c.error.startswith("syntax_warning:"):
                    key = "semantic_guard_syntax_warning"
                elif "timed out" in c.error.lower():
                    key = "test_timeout"
                elif "quota" in c.error.lower() or "429" in c.error.lower():
                    key = "quota"
            elif c.score < 1.0:
                key = "pytest_failed"
            else:
                continue
            summary[key] = summary.get(key, 0) + 1
        for code in codes:
            summary[code] = summary.get(code, 0) + 1
        return summary

    def _classify_failure(reason: str, codes: list[str], summary: dict[str, int]) -> str:
        reason_l = str(reason or "").lower()
        normalized_codes = [str(c).lower() for c in (codes or [])]
        if "time_budget_exceeded" in normalized_codes or "time_budget_exceeded" in reason_l:
            return "time_budget_exceeded"
        if "hyper_run_timeout" in normalized_codes or "hyper_run_timeout" in reason_l:
            return "hyper_run_timeout"
        if "stage1_no_passing_candidate" in normalized_codes:
            return "stage1_no_passing_candidate"
        if "stage1_failed" in normalized_codes:
            return "stage1_failed"
        if any(k in normalized_codes for k in ["quota", "429", "capacity"]):
            return "quota_or_capacity"
        if summary.get("syntax_error", 0) > 0:
            return "syntax_error"
        if summary.get("pytest_failed", 0) > 0:
            return "pytest_failed"
        if reason_l and reason_l != "success":
            return reason_l
        return "unknown_failure"

    def _corrective_action_for(failure_class: str) -> str:
        if "timeout" in failure_class:
            return "increase_timeout_or_reduce_scope"
        if failure_class in {"stage1_failed", "stage1_no_passing_candidate"}:
            return "improve_stage1_candidate_generation"
        if failure_class == "quota_or_capacity":
            return "fallback_to_local_or_reduce_llm_load"
        if failure_class == "syntax_error":
            return "strengthen_candidate_syntax_guard"
        if failure_class == "pytest_failed":
            return "tighten_test_aligned_patching"
        if failure_class == "time_budget_exceeded":
            return "reduce_trials_or_raise_wall_time_budget"
        return "review_failure_trace_and_refine_strategy"

    def _record_llm_meta(meta: dict[str, Any]) -> None:
        nonlocal model_calls, model_patch_generated, total_tokens, gateway_stats_present
        nonlocal gateway_usage_metadata_present, gateway_prompt_chars, gateway_payload_chars
        nonlocal gateway_total_chars, gateway_timeout_sec, quota_backoffs
        nonlocal gateway_total_sec, gateway_invocation_build_sec, gateway_process_sec
        nonlocal gateway_provider_wait_sec, gateway_parse_sec, unified_runtime_receipts
        model_calls += int(meta.get("model_calls", 0) or 0)
        if str(meta.get("model_name", "") or ""):
            model_names.add(str(meta.get("model_name")))
        if bool(meta.get("model_patch_generated", False)):
            model_patch_generated = True
        total_tokens += int(meta.get("tokens_used", 0) or 0)
        token_capture_statuses.add(str(meta.get("token_capture_status", "unknown") or "unknown"))
        gateway_stats_present = gateway_stats_present or bool(meta.get("gateway_stats_present", False))
        gateway_usage_metadata_present = gateway_usage_metadata_present or bool(meta.get("gateway_usage_metadata_present", False))
        gateway_token_sources.add(str(meta.get("gateway_token_source") or "missing"))
        if meta.get("gateway_error_category"):
            gateway_error_categories.add(str(meta.get("gateway_error_category")))
        gateway_prompt_chars = max(gateway_prompt_chars, int(meta.get("gateway_prompt_chars", 0) or 0))
        gateway_payload_chars = max(gateway_payload_chars, int(meta.get("gateway_payload_chars", 0) or 0))
        gateway_total_chars = max(gateway_total_chars, int(meta.get("gateway_total_chars", 0) or 0))
        gateway_timeout_sec = max(gateway_timeout_sec, int(meta.get("gateway_timeout_sec", 0) or 0))
        gateway_total_sec += float(meta.get("gateway_total_sec", 0.0) or 0.0)
        gateway_invocation_build_sec += float(meta.get("gateway_invocation_build_sec", 0.0) or 0.0)
        gateway_process_sec += float(meta.get("gateway_process_sec", 0.0) or 0.0)
        gateway_provider_wait_sec += float(meta.get("gateway_provider_wait_sec", 0.0) or 0.0)
        gateway_parse_sec += float(meta.get("gateway_parse_sec", 0.0) or 0.0)
        quota_backoffs += int(meta.get("quota_backoffs", 0) or 0)
        receipt = meta.get("unified_runtime_receipt")
        if isinstance(receipt, dict):
            unified_runtime_receipts.append(receipt)

    def _persist_learning(
        *,
        status: str,
        reason: str,
        winner_source: str,
        final_score: float,
        summary: dict[str, int],
        codes: list[str],
    ) -> None:
        # Learning loop (govern + write): MemPalace verify -> Findings write (LanceDB sync via repository).
        if symmetric_prompt:
            # No state may carry over to the next trial in the like-for-like A/B (S5).
            learning_trace["learning_write_skipped"] = "symmetric_prompt"
            return
        try:
            from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore
            from nexus.services.mem_palace import MemPalace

            local_store = store or FindingsMemoryStore(repo_root)
            failure_class = _classify_failure(reason, codes, summary) if status != "SUCCESS" else "none"
            corrective_action = _corrective_action_for(failure_class)
            card = FindingsCard(
                kind="episodes",
                title=f"Hyper-Sprint {status}: {Path(config.target_file).name}",
                task_id=f"hs-{int(time.time())}",
                tags=["hyper_sprint", status.lower(), winner_source],
                retrieval_hints=learning_trace.get("retrieval_hints", []),
                confidence="high" if status == "SUCCESS" else "medium",
                body=(
                    f"Task: {config.task}\n"
                    f"Target: {config.target_file}\n"
                    f"Status: {status}\n"
                    f"Reason: {reason}\n"
                    f"Score: {final_score}\n"
                    f"Error Codes: {codes}\n"
                    f"Rejection Summary: {summary}\n"
                ),
                extra={
                    "winner_source": winner_source,
                    "attempt_count": len(candidates),
                    "error_codes": codes,
                    "rejection_summary": summary,
                    "failure_class": failure_class,
                    "target_file": config.target_file,
                    "task_signature": config.task,
                    "corrective_action": corrective_action,
                    "timestamp": datetime.now().isoformat(),
                },
            )
            palace = MemPalace(str(repo_root))
            clean = palace.verify([card.to_dict()])
            if not clean:
                learning_trace["mempalace_verified"] = False
                learning_trace["memory_rejected"] = True
                return
            learning_trace["mempalace_verified"] = True
            clean_card = FindingsCard.from_dict(clean[0])
            local_store.write(clean_card)
            learning_trace["memory_written"] = True
            tx_id = palace.trigger_arweave_distillation(clean[0])
            learning_trace["arweave_tx_id"] = tx_id
        except Exception as exc:  # noqa: BLE001
            learning_trace["memory_error"] = str(exc)
        try:
            from nexus.research.learn_mode import LearnModeService

            learn_bridge = LearnModeService(repo_root).sync_phase_learning_closure(
                topic=config.task,
                metrics={
                    "coverage": 1.0 if status == "SUCCESS" else 0.5,
                    "self_question_pass_rate": 1.0 if status == "SUCCESS" else 0.4,
                    "citation_valid_ratio": 1.0 if status == "SUCCESS" else 0.8,
                    "stale_claims_count": 0,
                    "conflict_count": int(summary.get("semantic_guard_low_delta_feature", 0)),
                },
                phase_status={
                    "P": "SUCCESS",
                    "X": "SUCCESS" if learning_trace.get("retrieval_hits", 0) > 0 else "PARTIAL",
                    "D": "SUCCESS",
                    "R": "SUCCESS" if status == "SUCCESS" else "FAILED",
                    "A": "SUCCESS" if "semantic_guard" not in codes else "PARTIAL",
                    "C": "SUCCESS" if learning_trace.get("mempalace_verified") else "PARTIAL",
                },
            )
            learning_trace["learn_phase_bridge"] = {
                "status": learn_bridge.get("status", "UNKNOWN"),
                "entries_written": learn_bridge.get("entries_written", 0),
            }
        except Exception as exc:  # noqa: BLE001
            learning_trace["learn_phase_bridge_error"] = str(exc)

    def _finalize_unified_receipt(
        *,
        winner_seed: int | None,
        final_score: float,
        terminal_status: str,
        receipt_kind: str = "sprint",
    ) -> dict[str, Any] | None:
        """Close the selected Online receipt with observed final gates only."""
        selected_index: int | None = None
        for index in range(len(unified_runtime_receipts) - 1, -1, -1):
            candidate = unified_runtime_receipts[index]
            task_id = str(candidate.get("task_id", "")) if isinstance(candidate, dict) else ""
            if receipt_kind == "dayshift" and task_id.startswith("dayshift-"):
                selected_index = index
                break
            if receipt_kind == "sprint" and winner_seed is not None and f"-s{winner_seed}-" in task_id:
                selected_index = index
                break
        if selected_index is None:
            return None
        selected = unified_runtime_receipts[selected_index]
        learning_bridge = learning_trace.get("learn_phase_bridge", {})
        learning_passed = bool(
            learning_trace.get("memory_written")
            or (isinstance(learning_bridge, dict) and str(learning_bridge.get("status", "")).upper() in {"SUCCESS", "SUCCEEDED", "PASS"})
        )
        task_id = str(selected.get("task_id", ""))
        verifier_passed = terminal_status == "SUCCESS" and final_score >= 1.0
        from nexus.services.unified_runtime import UnifiedRuntime

        finalized = UnifiedRuntime().finalize_receipt(
            selected,
            verifier={
                "task_id": task_id,
                "status": "pass" if verifier_passed else "fail",
                "invoked": True,
                "gate_passed": verifier_passed,
                "evidence": "sprint_stage1_candidate_score",
                "evidence_refs": [f"verifier:{task_id}:stage1"],
                "outcome_contributed": verifier_passed,
            },
            learning={
                "task_id": task_id,
                "status": "pass" if learning_passed else "fail",
                "invoked": True,
                "gate_passed": learning_passed,
                "evidence": "sprint_learning_closure",
                "evidence_refs": [f"learning:{task_id}:closure"],
                "outcome_contributed": learning_passed,
            },
            outcome={"score": final_score, "value_measured": True},
            receipt_path=selected.get("receipt_path"),
        )
        unified_runtime_receipts[selected_index] = finalized
        return finalized

    def _meter() -> dict[str, Any]:
        return {
            "model_calls": model_calls,
            "total_tokens": total_tokens,
            "model_name": ",".join(sorted(model_names)),
            "learning_trace": learning_trace,
            "unified_runtime_receipts": list(unified_runtime_receipts),
            "elapsed_sec": round(time.time() - start, 4),
        }

    _SPRINT_METER.set(_meter)
    for idx in range(max(1, config.candidate_count)):
        if idx > 0 and _bench_lane.treatment_lane_active() and not _bench_lane.treatment_round_allowed(learning_trace, f"candidate_{idx}", model_calls):
            # PR-3: one row deadline and one call budget cover every round of the row.
            break
        hint = policy.get_mutation_hint(
            idx % max(1, config.candidate_count),
            task_desc=config.task,
            historical_hints=historical_hints,
        )
        hint = _apply_distant_scout_hint(hint)
        used_source = "local"
        ev_recorded = False
        try:
            if llm_generator is not None:
                try:
                    visible_verifier_binding.update({"hint": hint, "seed": idx})
                    candidate_code, meta = llm_generator.generate(
                        source_code=source_code,
                        task=config.task,
                        mutation_hint=hint,
                        seed=idx,
                        test_source=initial_test_source,
                        codeintel_block=codeintel_block,
                    )
                    used_source = str(meta.get("source", "llm"))
                    if _symmetric_prompt_mode() and isinstance(candidate_code, str) and candidate_code:
                        # L2: identity of the raw model candidate, before any post-processing; the
                        # flow delivers it only if the final patch is byte-identical.
                        learning_trace.setdefault(
                            "model_candidate_sha256",
                            hashlib.sha256(candidate_code.encode("utf-8")).hexdigest(),
                        )
                    if _symmetric_prompt_mode():
                        # PR-3: every model call in order (first + final binding); a call that
                        # yielded no model candidate is a placeholder, never a candidate.
                        if isinstance(candidate_code, str) and candidate_code and _bench_lane.is_stage1_model_source(used_source):
                            _bench_lane.record_model_candidate(learning_trace, candidate_code, used_source)
                        else:
                            _bench_lane.record_failed_model_call(learning_trace)
                except Exception as llm_exc:  # noqa: BLE001
                    if _symmetric_prompt_mode():
                        _bench_lane.record_failed_model_call(learning_trace)
                    fallback_used = True
                    failure_meta = getattr(llm_exc, "metadata", {})
                    failure_meta = failure_meta if isinstance(failure_meta, dict) else {}
                    failure_receipt = failure_meta.get("unified_runtime_receipt")
                    if isinstance(failure_receipt, dict):
                        unified_runtime_receipts.append(failure_receipt)
                    meta_model_calls = int(failure_meta.get("model_calls", 0) or 0)
                    # A generator that refused before any provider call reports model_calls=0.
                    model_calls += meta_model_calls if (meta_model_calls > 0 or "model_calls" in failure_meta) else 1
                    meta_model_name = str(failure_meta.get("model_name") or "")
                    if meta_model_name:
                        model_names.add(meta_model_name)
                    elif llm_generator is not None and getattr(llm_generator, "model_chain", None):
                        model_names.add(str(llm_generator.model_chain[0]))
                    err = str(llm_exc).lower()
                    infra_code = classify_infra_block(err)
                    if failure_meta:
                        total_tokens += int(failure_meta.get("tokens_used", 0) or 0)
                        token_capture_statuses.add(str(failure_meta.get("token_capture_status", "unknown") or "unknown"))
                        gateway_stats_present = gateway_stats_present or bool(failure_meta.get("gateway_stats_present", False))
                        gateway_usage_metadata_present = gateway_usage_metadata_present or bool(failure_meta.get("gateway_usage_metadata_present", False))
                        gateway_token_sources.add(str(failure_meta.get("gateway_token_source") or "missing"))
                        if failure_meta.get("gateway_error_category"):
                            gateway_error_categories.add(str(failure_meta.get("gateway_error_category")))
                        gateway_prompt_chars = max(gateway_prompt_chars, int(failure_meta.get("gateway_prompt_chars", 0) or 0))
                        gateway_payload_chars = max(gateway_payload_chars, int(failure_meta.get("gateway_payload_chars", 0) or 0))
                        gateway_total_chars = max(gateway_total_chars, int(failure_meta.get("gateway_total_chars", 0) or 0))
                        gateway_timeout_sec = max(gateway_timeout_sec, int(failure_meta.get("gateway_timeout_sec", 0) or 0))
                        gateway_total_sec += float(failure_meta.get("gateway_total_sec", 0.0) or 0.0)
                        gateway_invocation_build_sec += float(failure_meta.get("gateway_invocation_build_sec", 0.0) or 0.0)
                        gateway_process_sec += float(failure_meta.get("gateway_process_sec", 0.0) or 0.0)
                        gateway_provider_wait_sec += float(failure_meta.get("gateway_provider_wait_sec", 0.0) or 0.0)
                        gateway_parse_sec += float(failure_meta.get("gateway_parse_sec", 0.0) or 0.0)
                    if infra_code != "infra_blocked:quota":
                        if not failure_meta or int(failure_meta.get("tokens_used", 0) or 0) <= 0:
                            total_tokens += _estimate_tokens(
                                _build_llm_candidate_prompt(
                                    source_code=source_code,
                                    task=config.task,
                                    mutation_hint=hint,
                                    test_source=initial_test_source,
                                    codeintel_block=codeintel_block,
                                )
                            )
                            token_capture_statuses.add("estimated")
                    if any(p in err for p in ["quota", "429", "rate limit", "resource exhausted", "capacity"]):
                        quota_backoffs += 1
                        error_codes.append("quota")
                        error_codes.append("llm_fallback_local")
                    else:
                        error_codes.append("llm_error")
                    candidate_code, meta = local_generator.generate(
                        source_code=source_code,
                        task=config.task,
                        mutation_hint=hint,
                        seed=idx,
                    )
                    used_source = str(meta.get("source", "local"))
            else:
                candidate_code, meta = local_generator.generate(
                    source_code=source_code,
                    task=config.task,
                    mutation_hint=hint,
                    seed=idx,
                )
                used_source = str(meta.get("source", "local"))

            _record_llm_meta(meta)
            if used_source.startswith("local") and llm_generator is not None:
                fallback_used = True
            guard_ok, guard_reason = _semantic_guard(source_code, candidate_code, config.task, used_source)
            if not guard_ok:
                ev = CandidateEval(seed=idx, score=0.0, hint=hint, error=guard_reason, candidate_code=candidate_code, source=used_source)
                error_codes.append("semantic_guard")
            else:
                if used_source.startswith("llm") and _sprint_lock_denied(
                    meta, repo_root=repo_root, config=config, learning_trace=learning_trace
                ):
                    # Another task holds the target: the whole attempt stops here (no evaluation,
                    # no self-heal, no rescue, no delivery).
                    raise _SprintLockDenied(
                        model_calls=model_calls,
                        total_tokens=total_tokens,
                        model_name=",".join(sorted(model_names)),
                        learning_trace=learning_trace,
                        unified_runtime_receipts=list(unified_runtime_receipts),
                        elapsed_sec=round(time.time() - start, 4),
                    )
                else:
                    ev = _evaluate_candidate(seed=idx, hint=hint, code=candidate_code, source=used_source)
            if (
                candidate_pool_policy.enabled
                and idx == 0
                and llm_generator is not None
                and used_source.startswith("llm")
                and ev.score >= 1.0
            ):
                for support_idx in range(candidate_pool_policy.local_support_candidates):
                    support_seed = idx + 8000 + support_idx
                    support_code, support_meta = local_generator.generate(
                        source_code=source_code,
                        task=config.task,
                        mutation_hint=f"{hint}\nddtree_local_support_pool",
                        seed=support_seed,
                    )
                    support_source = str(support_meta.get("source") or "local")
                    if support_source == "local":
                        support_source = "local_ddtree_support"
                    support_guard_ok, support_guard_reason = _semantic_guard(
                        source_code,
                        support_code,
                        config.task,
                        support_source,
                    )
                    if support_guard_ok:
                        support_ev = sprint_evaluate(
                            seed=support_seed,
                            hint=f"{hint} | ddtree_local_support_pool",
                            code=support_code,
                            source=support_source,
                        )
                        support_ev.score = min(
                            support_ev.score,
                            candidate_pool_policy.local_support_score_cap,
                        )
                    else:
                        support_ev = CandidateEval(
                            seed=support_seed,
                            score=0.0,
                            hint=f"{hint} | ddtree_local_support_pool",
                            error=support_guard_reason,
                            candidate_code=support_code,
                            source=support_source,
                        )
                    candidates.append(support_ev)
            self_heal_enabled = (
                os.environ.get("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "1").strip().lower() not in {"0", "false", "no"}
                # L2: symmetric mode itself means one model call, except in the bench treatment
                # lane (PR-3), where the visible-test self-heal is the treatment being measured.
                and (not _symmetric_prompt_mode() or _bench_lane.treatment_lane_active())
            )
            if (
                self_heal_enabled
                and llm_generator is not None
                and (used_source.startswith("llm") or model_required_final_delivery)
                and ev.score < 1.0
                and "quota" not in error_codes
                # PR-3: the treatment lane repairs only a model candidate, never a local fallback.
                and (not _bench_lane.treatment_lane_active() or _bench_lane.is_stage1_model_source(used_source))
                and (not _bench_lane.treatment_lane_active() or _bench_lane.treatment_round_allowed(learning_trace, "self_heal", model_calls))
            ):
                candidates.append(ev)
                ev_recorded = True
                failure_tail = (ev.error or ev.stdout or "")[-1200:]
                local_support_block = ""
                # PR-3: a local candidate is never shown to the model in the audited A/B prompt.
                if model_required_final_delivery and not _symmetric_prompt_mode():
                    try:
                        support_code, support_meta = local_generator.generate(
                            source_code=source_code,
                            task=config.task,
                            mutation_hint=f"{hint}\nmodel_required_local_support_hint",
                            seed=idx + 9000,
                        )
                        support_source = str(support_meta.get("source", "local_support_hint"))
                        support_guard_ok, _support_guard_reason = _semantic_guard(
                            source_code, support_code, config.task, support_source
                        )
                        if support_guard_ok and support_code.strip() and support_code != candidate_code:
                            fallback_used = True
                            error_codes.append("model_required_local_support_hint")
                            local_support_block = (
                                "\n[NEXUS LOCAL SUPPORT CANDIDATE]\n"
                                "This candidate is support evidence only, not final delivery. "
                                "Use it to produce a model-owned corrected patch if it satisfies the visible contract.\n"
                                f"{support_code}\n"
                            )
                    except Exception:  # noqa: BLE001
                        error_codes.append("model_required_local_support_hint_failed")
                heal_call_recorded = False
                repair_task = (
                    f"{config.task}\n\n"
                    "Previous candidate failed verification. "
                    "Repair the candidate using the failure evidence below.\n"
                    f"[FAILURE]\n{failure_tail}\n"
                    f"{local_support_block}"
                )
                try:
                    visible_verifier_binding.update(
                        {"hint": f"{hint} | self_heal_after_pytest_failed", "seed": idx + 10000}
                    )
                    repair_code, repair_meta = llm_generator.generate(
                        source_code=candidate_code,
                        task=repair_task,
                        mutation_hint=f"{hint}\nself_heal_after_pytest_failed",
                        seed=idx + 10000,
                        test_source=test_source,
                        codeintel_block=codeintel_block,
                    )
                    _record_llm_meta(repair_meta)
                    heal_call_recorded = True
                    if _symmetric_prompt_mode():
                        if isinstance(repair_code, str) and repair_code:
                            _bench_lane.record_model_candidate(learning_trace, repair_code, "llm_self_heal")
                        else:
                            _bench_lane.record_failed_model_call(learning_trace, "llm_self_heal_failed")
                    repair_guard_ok, repair_guard_reason = _semantic_guard(candidate_code, repair_code, config.task, "llm_self_heal")
                    if repair_guard_ok:
                        repair_ev = _evaluate_candidate(
                            seed=idx + 10000,
                            hint=f"{hint} | self_heal_after_pytest_failed",
                            code=repair_code,
                            source="llm_self_heal",
                        )
                    else:
                        repair_ev = CandidateEval(
                            seed=idx + 10000,
                            score=0.0,
                            hint=f"{hint} | self_heal_after_pytest_failed",
                            error=repair_guard_reason,
                            candidate_code=repair_code,
                            source="llm_self_heal",
                        )
                    candidates.append(repair_ev)
                    error_codes.append("llm_self_heal_attempted")
                    if repair_ev.score >= 1.0:
                        ev = repair_ev
                except Exception as heal_exc:  # noqa: BLE001
                    if _symmetric_prompt_mode() and not heal_call_recorded:
                        _bench_lane.record_failed_model_call(learning_trace, "llm_self_heal_failed")
                        # PR-3: a failed repair call still counts (call budget, calls and tokens
                        # reconciled with the prompt capture).
                        heal_meta = getattr(heal_exc, "metadata", {})
                        heal_meta = dict(heal_meta) if isinstance(heal_meta, dict) else {}
                        heal_meta["model_calls"] = (
                            int(heal_meta.get("model_calls", 0) or 0) if "model_calls" in heal_meta else 1
                        )
                        _record_llm_meta(heal_meta)
                    error_codes.append("llm_self_heal_failed")
                    candidates.append(
                        CandidateEval(
                            seed=idx + 10000,
                            score=0.0,
                            hint=f"{hint} | self_heal_after_pytest_failed",
                            error=str(heal_exc),
                            source="llm_self_heal",
                        )
                    )
            if (
                llm_generator is not None
                and used_source.startswith("llm")
                and ev.score < 1.0
                and "quota" not in error_codes
            ):
                if not ev_recorded:
                    candidates.append(ev)
                    ev_recorded = True
                local_code, local_meta = local_generator.generate(
                    source_code=source_code,
                    task=config.task,
                    mutation_hint=hint,
                    seed=idx + 1000,
                )
                local_source = str(local_meta.get("source", "local_guard_fallback"))
                fallback_used = True
                local_guard_ok, local_guard_reason = _semantic_guard(source_code, local_code, config.task, local_source)
                if local_guard_ok:
                    local_ev = sprint_evaluate(
                        seed=idx + 1000,
                        hint=f"{hint} | local_guard_fallback",
                        code=local_code,
                        source=local_source,
                    )
                else:
                    local_ev = CandidateEval(
                        seed=idx + 1000,
                        score=0.0,
                        hint=f"{hint} | local_guard_fallback",
                        error=local_guard_reason,
                        candidate_code=local_code,
                        source=local_source,
                    )
                candidates.append(local_ev)
                if local_ev.score >= 1.0:
                    ev = local_ev
        except Exception as exc:  # noqa: BLE001
            ev = CandidateEval(seed=idx, score=0.0, hint=hint, error=str(exc), source=used_source)
        if "timed out" in (ev.error or "").lower():
            test_timeouts += 1
            error_codes.append("test_timeout")
        if "quota" in (ev.error or "").lower() or "429" in (ev.error or "").lower():
            error_codes.append("quota")
        if not ev_recorded:
            candidates.append(ev)
        if config.safe_mode and ev.score >= 1.0 and len(candidates) >= routing_min_pool:
            break

        if config.safe_mode:
            time.sleep(1.0)

# R1.1: Emergency Fallback Valve - Ensure we match baseline if all else fails
    has_success = any(c.score >= 1.0 for c in candidates)
    if not has_success:
        # Perform one last verified local run as "local" source. This remains active even
        # after a failed local fallback so bounded LLM runs do not under-sample simple fixes.
        code, meta = local_generator.generate(source_code=source_code, task=config.task, mutation_hint="emergency_baseline_match", seed=999)
        if code != source_code:
            guard_ok, _ = _semantic_guard(source_code, code, config.task, meta.get("source", "local"))
            if guard_ok:
                ev = sprint_evaluate(seed=999, hint="emergency_fallback", code=code, source=meta.get("source", "local"))
                candidates.append(ev)

    if not candidates:
        return SprintResult(
            codeintel_context=codeintel_status,
            status="FAILED",
            reason=SprintOutcome.GENERATION_FAIL.value,
            target_file=config.target_file,
            winner_source="unknown",
            final_score=0.0,
            elapsed_sec=round(time.time() - start, 4),
            attempt_count=0,
            model_calls=model_calls,
            quota_backoffs=quota_backoffs,
            test_timeouts=test_timeouts,
            total_tokens=total_tokens,
            token_capture_status=_resolve_token_capture_status(
                total_tokens=total_tokens,
                model_calls=model_calls,
                statuses=token_capture_statuses,
            ),
            gateway_stats_present=gateway_stats_present,
            gateway_usage_metadata_present=gateway_usage_metadata_present,
            gateway_token_source=_resolve_gateway_token_source(gateway_token_sources),
            gateway_error_category=",".join(sorted(gateway_error_categories)),
            gateway_prompt_chars=gateway_prompt_chars,
            gateway_payload_chars=gateway_payload_chars,
            gateway_total_chars=gateway_total_chars,
            gateway_timeout_sec=gateway_timeout_sec,
            gateway_total_sec=round(gateway_total_sec, 4),
            gateway_invocation_build_sec=round(gateway_invocation_build_sec, 4),
            gateway_process_sec=round(gateway_process_sec, 4),
            gateway_provider_wait_sec=round(gateway_provider_wait_sec, 4),
            gateway_parse_sec=round(gateway_parse_sec, 4),
            executor_selected=executor_selected,
            executor_forced_inplace=force_inplace_executor,
            executor_init_sec=executor_init_sec,
            model_name=",".join(sorted(model_names)),
            model_patch_generated=model_patch_generated,
            fallback_used=fallback_used,
            error_codes=sorted(set(error_codes)),
            rejection_summary={},
            learning_trace=learning_trace,
            candidates=candidates,
            pytest_cmd=pytest_cmd,
            unified_runtime_receipts=unified_runtime_receipts,
        )

    best, routed_candidates = _select_candidate_with_routing_layers(
        candidates,
        task=config.task,
        learning_trace=learning_trace,
        enable_autoreason_executor=config.enable_autoreason_executor,
        enable_ddtree_executor=config.enable_ddtree_executor,
        ddtree_max_candidates=config.ddtree_max_candidates,
    )
    candidates = routed_candidates
    # A run with a model never delivers a locally generated candidate (the strict lane already
    # required this; #2339 removed the benchmark-keyed local fast paths from every lane).
    if (model_required_final_delivery or llm_generator is not None) and not _is_model_owned_source(best.source):
        model_candidates = [item for item in candidates if _is_model_owned_source(item.source)]
        best_model = max(model_candidates, key=lambda item: item.score, default=None)
        local_support_code = "model_required_local_support_not_delivery" if best.score >= 1.0 else ""
        final_codes = sorted(
            set(
                error_codes
                + ["model_required_model_delivery_failed"]
                + ([local_support_code] if local_support_code else [])
            )
        )
        rejection_summary = _build_rejection_summary(candidates, final_codes)
        _persist_learning(
            status="FAILED",
            reason="model_required_model_delivery_failed",
            winner_source=best_model.source if best_model is not None else "model_required_no_model_candidate",
            final_score=best_model.score if best_model is not None else 0.0,
            summary=rejection_summary,
            codes=final_codes,
        )
        _finalize_unified_receipt(
            winner_seed=best_model.seed if best_model is not None else best.seed,
            final_score=best_model.score if best_model is not None else best.score,
            terminal_status="FAILED",
        )
        return SprintResult(
            codeintel_context=codeintel_status,
            status="FAILED",
            reason="model_required_model_delivery_failed",
            target_file=config.target_file,
            winner_source=best_model.source if best_model is not None else "model_required_no_model_candidate",
            final_score=best_model.score if best_model is not None else 0.0,
            elapsed_sec=round(time.time() - start, 4),
            attempt_count=len(candidates),
            model_calls=model_calls,
            quota_backoffs=quota_backoffs,
            test_timeouts=test_timeouts,
            total_tokens=total_tokens,
            token_capture_status=_resolve_token_capture_status(
                total_tokens=total_tokens,
                model_calls=model_calls,
                statuses=token_capture_statuses,
            ),
            gateway_stats_present=gateway_stats_present,
            gateway_usage_metadata_present=gateway_usage_metadata_present,
            gateway_token_source=_resolve_gateway_token_source(gateway_token_sources),
            gateway_error_category=",".join(sorted(gateway_error_categories)),
            gateway_prompt_chars=gateway_prompt_chars,
            gateway_payload_chars=gateway_payload_chars,
            gateway_total_chars=gateway_total_chars,
            gateway_timeout_sec=gateway_timeout_sec,
            gateway_total_sec=round(gateway_total_sec, 4),
            gateway_invocation_build_sec=round(gateway_invocation_build_sec, 4),
            gateway_process_sec=round(gateway_process_sec, 4),
            gateway_provider_wait_sec=round(gateway_provider_wait_sec, 4),
            gateway_parse_sec=round(gateway_parse_sec, 4),
            executor_selected=executor_selected,
            executor_forced_inplace=force_inplace_executor,
            executor_init_sec=executor_init_sec,
            model_name=",".join(sorted(model_names)),
            model_patch_generated=model_patch_generated,
            fallback_used=fallback_used,
            error_codes=final_codes,
            rejection_summary=rejection_summary,
            learning_trace=learning_trace,
            candidates=candidates,
            pytest_cmd=pytest_cmd,
            unified_runtime_receipts=unified_runtime_receipts,
            patch=best_model.candidate_code if best_model is not None else "",
        )
    if best.score < 1.0:
        final_codes = sorted(set(error_codes + [SprintOutcome.STAGE1_FAILED.value]))
        rejection_summary = _build_rejection_summary(candidates, final_codes)
        _persist_learning(
            status="FAILED",
            reason=SprintOutcome.STAGE1_NO_PASSING_CANDIDATE.value,
            winner_source=best.source,
            final_score=best.score,
            summary=rejection_summary,
            codes=final_codes,
        )
        _finalize_unified_receipt(
            winner_seed=best.seed,
            final_score=best.score,
            terminal_status="FAILED",
        )
        return SprintResult(
            codeintel_context=codeintel_status,
            status="FAILED",
            reason=SprintOutcome.STAGE1_NO_PASSING_CANDIDATE.value,
            target_file=config.target_file,
            winner_source=best.source,
            final_score=best.score,
            elapsed_sec=round(time.time() - start, 4),
            attempt_count=len(candidates),
            model_calls=model_calls,
            quota_backoffs=quota_backoffs,
            test_timeouts=test_timeouts,
            total_tokens=total_tokens,
            token_capture_status=_resolve_token_capture_status(
                total_tokens=total_tokens,
                model_calls=model_calls,
                statuses=token_capture_statuses,
            ),
            gateway_stats_present=gateway_stats_present,
            gateway_usage_metadata_present=gateway_usage_metadata_present,
            gateway_token_source=_resolve_gateway_token_source(gateway_token_sources),
            gateway_error_category=",".join(sorted(gateway_error_categories)),
            gateway_prompt_chars=gateway_prompt_chars,
            gateway_payload_chars=gateway_payload_chars,
            gateway_total_chars=gateway_total_chars,
            gateway_timeout_sec=gateway_timeout_sec,
            gateway_total_sec=round(gateway_total_sec, 4),
            gateway_invocation_build_sec=round(gateway_invocation_build_sec, 4),
            gateway_process_sec=round(gateway_process_sec, 4),
            gateway_provider_wait_sec=round(gateway_provider_wait_sec, 4),
            gateway_parse_sec=round(gateway_parse_sec, 4),
            executor_selected=executor_selected,
            executor_forced_inplace=force_inplace_executor,
            executor_init_sec=executor_init_sec,
            model_name=",".join(sorted(model_names)),
            model_patch_generated=model_patch_generated,
            fallback_used=fallback_used,
            error_codes=final_codes,
            rejection_summary=rejection_summary,
            learning_trace=learning_trace,
            candidates=candidates,
            pytest_cmd=pytest_cmd,
            unified_runtime_receipts=unified_runtime_receipts,
            patch=best.candidate_code,
        )

    final_score = best.score
    final_patch = best.candidate_code or source_code
    final_reason = "stage1_pass"
    disable_dayshift = (
        os.environ.get("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "").strip().lower() in {"1", "true", "yes"}
        or _symmetric_prompt_mode()  # L2: no stage-2 rewrite of the model candidate in the A/B
    )
    # Stage 2 is optional enhancement only. Core success must not depend on external quota.
    if llm_mode_effective and llm_channel == "local":
        # DayShiftOptimizer scores with online gateway models; the local channel stops at stage 1.
        final_reason = "stage1_pass_local_channel"
    elif llm_mode_effective and "quota" not in error_codes and not disable_dayshift:
        swarm_dir = SwarmBroker(repo_root).acquire(timeout_sec=config.timeout_sec)
        if swarm_dir:
            try:
                optimizer = DayShiftOptimizer(
                    project_root=repo_root,
                    swarm_dir=swarm_dir,
                    target_file=config.target_file,
                    task_desc=config.task,
                    max_rounds=config.max_rounds,
                    convergence_patience=2,
                    test_timeout_sec=config.timeout_sec,
                    use_llm_scoring=not config.safe_mode,
                    min_round_delay_sec=1.5 if config.safe_mode else 0.2,
                    model_name="gemini-3-flash-preview" if config.safe_mode else "gemini-3.1-pro-preview",
                    fallback_model_name="gemini-3.1-pro-preview" if config.safe_mode else "gemini-3-flash-preview",
                )
                result = optimizer.optimize()
                unified_runtime_receipts.extend(
                    item for item in result.get("unified_runtime_receipts", []) if isinstance(item, dict)
                )
                if result.get("status") == "SUCCESS":
                    final_score = float(result.get("score", final_score))
                    final_patch = str(result.get("patch", final_patch))
                    final_reason = "dayshift_improved"
                else:
                    final_reason = "dayshift_no_improve"
            finally:
                SwarmBroker(repo_root).release(swarm_dir)
    elif llm_mode_effective and "quota" in error_codes:
        final_reason = "dayshift_skipped_due_quota_fallback"
    elif llm_mode_effective and disable_dayshift:
        final_reason = "dayshift_skipped_by_benchmark_budget"
    elif config.llm_mode and not llm_mode_effective:
        error_codes.append("learn_slo_block")
        final_reason = "dayshift_skipped_due_learn_slo_guard"

    final_codes = sorted(set(error_codes))
    rejection_summary = _build_rejection_summary(candidates, error_codes)
    _persist_learning(
        status="SUCCESS",
        reason=final_reason,
        winner_source=best.source,
        final_score=final_score,
        summary=rejection_summary,
        codes=final_codes,
    )
    _finalize_unified_receipt(
        winner_seed=best.seed,
        final_score=final_score,
        terminal_status="SUCCESS",
        receipt_kind="dayshift" if final_reason == "dayshift_improved" else "sprint",
    )
    return SprintResult(
        codeintel_context=codeintel_status,
        status="SUCCESS",
        reason=final_reason,
        target_file=config.target_file,
        winner_source=best.source,
        final_score=final_score,
        elapsed_sec=round(time.time() - start, 4),
        attempt_count=len(candidates),
        model_calls=model_calls,
        quota_backoffs=quota_backoffs,
        test_timeouts=test_timeouts,
        total_tokens=total_tokens,
        token_capture_status=_resolve_token_capture_status(
            total_tokens=total_tokens,
            model_calls=model_calls,
            statuses=token_capture_statuses,
        ),
        gateway_stats_present=gateway_stats_present,
        gateway_usage_metadata_present=gateway_usage_metadata_present,
        gateway_token_source=_resolve_gateway_token_source(gateway_token_sources),
        gateway_error_category=",".join(sorted(gateway_error_categories)),
        gateway_prompt_chars=gateway_prompt_chars,
        gateway_payload_chars=gateway_payload_chars,
        gateway_total_chars=gateway_total_chars,
        gateway_timeout_sec=gateway_timeout_sec,
        gateway_total_sec=round(gateway_total_sec, 4),
        gateway_invocation_build_sec=round(gateway_invocation_build_sec, 4),
        gateway_process_sec=round(gateway_process_sec, 4),
        gateway_provider_wait_sec=round(gateway_provider_wait_sec, 4),
        gateway_parse_sec=round(gateway_parse_sec, 4),
        executor_selected=executor_selected,
        executor_forced_inplace=force_inplace_executor,
        executor_init_sec=executor_init_sec,
        model_name=",".join(sorted(model_names)),
        model_patch_generated=model_patch_generated,
        fallback_used=fallback_used,
        error_codes=final_codes,
        rejection_summary=rejection_summary,
        learning_trace=learning_trace,
        candidates=candidates,
        pytest_cmd=pytest_cmd,
        unified_runtime_receipts=unified_runtime_receipts,
        promotable=final_score >= 0.9,
        patch=final_patch,
    )
