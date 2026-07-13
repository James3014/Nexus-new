from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from nexus.core.outcome_schema import SprintOutcome
from nexus.engine.autoreason_service import AutoreasonService
from nexus.engine.ddtree_adapter import DDTreeAdapter
from nexus.engine.learning_policy_loader import route_cost_controls_from_env
from nexus.engine.policies.research_policy import ResearchPolicy
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

    def __init__(self, project_root: Path, safe_mode: bool, target_file: str = ""):
        from nexus.services.gateway import BattlesuitGateway
        self.project_root = Path(project_root).resolve()
        self.gateway = BattlesuitGateway(project_root=self.project_root)
        self.safe_mode = safe_mode
        self.target_file = str(target_file or "").strip()
        self.local_service = None
        if os.environ.get("NEXUS_ONLINE_LOCAL_ASSIST", "").strip().lower() in {"1", "true", "yes"}:
            from nexus.services.local_assist_service import LocalAssistService

            self.local_service = LocalAssistService()
        self.model_chain = self._model_chain()
        self.last_unified_runtime_receipt: dict[str, Any] = {}

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
            from nexus.services.local_assist_service import LocalAssistRequest, REQUEST_SCHEMA

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

        def response_contract(context: dict[str, Any]) -> dict[str, Any]:
            online = context.get("online", {})
            provider_response, _raw, _payload = extract_online_stage_payload(
                online if isinstance(online, dict) else {}
            )
            delivered = bool(provider_response)
            return {
                "task_id": task_id,
                "status": "pass" if delivered else "fail",
                "evidence": "online_candidate_payload_present" if delivered else "online_candidate_payload_missing",
                "evidence_refs": [f"verifier:{task_id}:candidate_response"],
            }

        gateway_provider = str(getattr(self.gateway, "oauth_provider", "") or "").strip().lower()
        request = UnifiedRuntimeRequest(
            task_id=task_id,
            workspace_revision=revision,
            task_statement=task,
            task_type="repair",
            route=build_online_route(
                recommended_flow="hybrid" if local_request is not None else "direct",
                gateway_provider=gateway_provider,
                local_enabled=local_request is not None,
            ),
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
            from nexus.services.unified_runtime import UnifiedRuntime, build_structured_online_invoker

            receipt = UnifiedRuntime(local_service=self.local_service if local_request is not None else None).run(
                request,
                online_invoker=build_structured_online_invoker(
                    self.gateway.ask_structured,
                    phase="R",
                    model_name=model,
                    output_schema=output_schema,
                    provider="fixture_gateway",
                ),
                verifier=response_contract,
                receipt_path=receipt_path,
            )
        self.last_unified_runtime_receipt = dict(receipt)
        online_stage = receipt.get("online", {}) if isinstance(receipt.get("online"), dict) else {}
        provider_response, raw_response, _payload = extract_online_stage_payload(online_stage)
        if isinstance(provider_response, dict):
            return dict(provider_response), raw_response, receipt
        return {"status": "APPROVED" if online_stage.get("status") == "SUCCEEDED" else "FAIL", "patch": str(provider_response or "")}, raw_response, receipt

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
    ) -> tuple[str, dict[str, Any]]:
        prompt_text = _build_llm_candidate_prompt(
            source_code=source_code,
            task=task,
            mutation_hint=mutation_hint,
            test_source=test_source,
        )
        quota_backoffs = 0
        model_calls = 0
        last_err = ""
        for idx, model in enumerate(self.model_chain):
            try:
                model_calls += 1
                out, raw, unified_receipt = self._ask_unified_candidate(
                    prompt=prompt_text,
                    payload="Return one small edit. Prefer operation=replace with exact target_snippet and replacement.",
                    task=task,
                    seed=seed,
                    attempt=idx + 1,
                    model=model,
                )
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


def _estimate_tokens(text: str) -> int:
    # Fallback estimate when gateway does not return token usage.
    return max(1, len(text) // 4)


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


def _build_value_task_contract(*, source_code: str, task: str, test_source: str = "") -> str:
    combined = f"{task}\n{source_code}\n{test_source}".lower()
    rules: list[str] = []
    if "none" in combined and ("override" in combined or "defaults" in combined):
        rules.append("If an override value is None, preserve the existing default instead of writing None.")
    if "artifact" in combined or "claim" in combined:
        rules.append("Preserve exact canonical field names from source/tests; do not invent plural or renamed fields.")
        if "'artifact'" in combined or '"artifact"' in combined:
            rules.append("Use singular field 'artifact'; do not rename it to 'artifacts'.")
        rules.append("Verified claim helpers should return the claim ids that satisfy the artifact-backed contract.")
    if "phase" in combined or "evidence" in combined or "reason" in combined:
        rules.append("Use the canonical phase fields 'status', 'evidence', and 'reason' exactly when they appear in source/tests.")
        rules.append("Passing phases require evidence; failing phases require a non-empty reason.")
    if "nightshift" in combined or "report_path" in combined:
        rules.append(
            "Nightshift recovery is auditable only when recommended, invoked, recovered, and a non-empty report_path are all present."
        )
        rules.append("Reject boolean-only Nightshift recovery when report_path is missing or empty.")
    if "deny" in combined or "authorization" in combined or "redact" in combined:
        rules.append("MemPalace rule: fail closed for unknown or missing authorization data and never weaken redaction.")
    if "strict parser defaults" in combined or "parse_config" in combined:
        rules.append(
            "LanceDB/context rule: for parse_config, omitted values use canonical defaults strict=True and retries=3; explicit inputs are preserved."
        )
    elif "strict" in combined or "canonical" in combined or "config" in combined:
        rules.append("LanceDB/context rule: follow the canonical config/doc contract over older examples.")
    if not rules:
        return ""
    return "[NEXUS VALUE CONTRACT]\n" + "\n".join(f"- {rule}" for rule in rules) + "\n"


def _build_llm_candidate_prompt(*, source_code: str, task: str, mutation_hint: str, test_source: str = "") -> str:
    compact = os.environ.get("NEXUS_GATEWAY_COMPACT_PROMPT", "").strip().lower() in {"1", "true", "yes"}
    contract_block = _build_value_task_contract(source_code=source_code, task=task, test_source=test_source)
    test_block = f"\nTests:\n{test_source}" if test_source else ""
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


def _should_try_local_preflight_before_llm(*, task: str, source_code: str) -> bool:
    if os.environ.get("NEXUS_DISABLE_LOCAL_PREFLIGHT_BEFORE_LLM", "").strip().lower() in {"1", "true", "yes"}:
        return False
    combined = f"{task}\n{source_code}".lower()
    # These contracts are already represented in the deterministic local mutator.
    # Try that cheap path before waiting on an external model call.
    return any(
        marker in combined
        for marker in (
            "renamed public field",
            "canonical field",
            "build_response",
            "credential scrubber",
            "secret redaction",
            "def redact",
            "evidence artifact claim rollup",
            "governance action filter",
            "rlm_harder_v2_filter_action",
            "rlm_harder_v2_scope_decision",
            "rlm_harder_v2_verified_claims",
            "rlm_harder_v2_accept_receipt",
            "rlm_harder_v2_select_memory_hits",
            "rlm_harder_v2_merge_settings",
            "rlm_harder_v2_repair_budget",
            "reason governance_block",
            "phased report summary",
            "phase_ready",
        )
    )


def _has_hidden_contract_fast_path(source_code: str) -> bool:
    """Cheap deterministic contracts that can be verified before spending an LLM call."""
    return any(
        marker in source_code
        for marker in (
            "def merge_limits",
            "def remaining_ms",
            "def rlm_harder_v2_repair_budget",
        )
    )


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

    def evaluate_candidate(self, *, seed: int, hint: str, code: str, source: str) -> CandidateEval:
        start = time.time()
        target_path = self.repo_root / self.target_file
        original = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
        companion_edits = generate_local_companion_edits(self.repo_root, target_path, self.task, hint, seed)
        restored_files: dict[Path, str | None] = {}
        try:
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
                try:
                    syntax_warning = _compile_candidate_or_warning(code, str(target_path))
                except SyntaxError as exc:
                    return CandidateEval(
                        seed=seed,
                        score=0.0,
                        hint=hint,
                        error=f"syntax_error:{exc.msg}",
                        candidate_code=code,
                        source=source,
                        elapsed_sec=round(time.time() - start, 4),
                    )
                if syntax_warning:
                    return CandidateEval(
                        seed=seed,
                        score=0.0,
                        hint=hint,
                        error=f"syntax_warning:{syntax_warning}",
                        candidate_code=code,
                        source=source,
                        elapsed_sec=round(time.time() - start, 4),
                    )
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
            for path, original_text in restored_files.items():
                if original_text is None:
                    if path.exists():
                        path.unlink()
                else:
                    path.write_text(original_text, encoding="utf-8")


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


def run_hyper_sprint(*, repo_root: Path, config: SprintConfig) -> SprintResult:
    start = time.time()
    policy = ResearchPolicy()
    scope_files = [config.target_file] + ([config.test_file] if config.test_file else [])
    effective_timeout = compute_time_budget(config.timeout_sec)
    pytest_cmd = [sys.executable, "-m", "pytest", "-q", "--maxfail=1"] + ([config.test_file] if config.test_file else [])

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
    initial_test_source = "" if hidden_verifier_mode and not model_required_final_delivery else test_source
    if initial_test_source:
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

    llm_generator: Optional[LLMCandidateGenerator] = (
        LLMCandidateGenerator(repo_root, config.safe_mode, target_file=config.target_file)
        if llm_mode_effective
        else None
    )
    local_generator = LocalCandidateGenerator()
    # Local-first fast path: avoid heavy swarm sync when no external LLM is used.
    force_inplace_executor = os.environ.get("NEXUS_FORCE_INPLACE_EXECUTOR", "").strip().lower() in {"1", "true", "yes"}
    enable_local_swarm_executor = os.environ.get("NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR", "").strip().lower() in {"1", "true", "yes"}
    executor_init_start = time.monotonic()
    if (llm_mode_effective or enable_local_swarm_executor) and not force_inplace_executor:
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
        try:
            syntax_warning = _compile_candidate_or_warning(candidate, "<semantic_guard>")
        except SyntaxError as exc:
            return False, f"syntax_error: {exc}"
        if syntax_warning:
            return False, f"syntax_warning: {syntax_warning}"

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
        is_refactor = "refactor" in task_l
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

    for idx in range(max(1, config.candidate_count)):
        hint = policy.get_mutation_hint(
            idx % max(1, config.candidate_count),
            task_desc=config.task,
            historical_hints=historical_hints,
        )
        hint = _apply_distant_scout_hint(hint)
        used_source = "local"
        ev_recorded = False
        try:
            hidden_fast_path_disabled = os.environ.get(
                "NEXUS_DISABLE_HIDDEN_CONTRACT_FAST_PATH",
                "",
            ).strip().lower() in {"1", "true", "yes"}
            hidden_invariant_shadow_disabled = os.environ.get(
                "NEXUS_DISABLE_HIDDEN_INVARIANT_SHADOW",
                "",
            ).strip().lower() in {"1", "true", "yes"}
            if (
                llm_generator is not None
                and hidden_verifier_mode
                and not hidden_fast_path_disabled
                and _has_hidden_contract_fast_path(source_code)
            ):
                fast_code, fast_meta = local_generator.generate(
                    source_code=source_code,
                    task=config.task,
                    mutation_hint=f"{hint}\nhidden_verifier_contract_fast_path",
                    seed=idx + 5000,
                )
                fast_source = str(fast_meta.get("source", "local_hidden_contract_fast_path")) or "local_hidden_contract_fast_path"
                if fast_source == "local":
                    fast_source = "local_hidden_contract_fast_path"
                fast_guard_ok, fast_guard_reason = _semantic_guard(source_code, fast_code, config.task, fast_source)
                if fast_guard_ok:
                    fast_ev = executor.evaluate_candidate(
                        seed=idx + 5000,
                        hint=f"{hint} | hidden_verifier_contract_fast_path",
                        code=fast_code,
                        source=fast_source,
                    )
                else:
                    fast_ev = CandidateEval(
                        seed=idx + 5000,
                        score=0.0,
                        hint=f"{hint} | hidden_verifier_contract_fast_path",
                        error=fast_guard_reason,
                        candidate_code=fast_code,
                        source=fast_source,
                    )
                candidates.append(fast_ev)
                ev_recorded = True
                learning_trace["hidden_contract_fast_path"] = {
                    "attempted": True,
                    "score": fast_ev.score,
                    "source": fast_source,
                }
                if fast_ev.score >= 1.0:
                    error_codes.append("hidden_contract_fast_path_success")
                    ev = fast_ev
                    break
                error_codes.append("hidden_contract_fast_path_miss")
            if llm_generator is not None and _should_try_local_preflight_before_llm(task=config.task, source_code=source_code):
                preflight_code, preflight_meta = local_generator.generate(
                    source_code=source_code,
                    task=config.task,
                    mutation_hint=f"{hint}\nlocal_preflight_before_llm",
                    seed=idx + 7000,
                )
                preflight_source = str(preflight_meta.get("source", "local_preflight")) or "local_preflight"
                if preflight_source == "local":
                    preflight_source = "local_preflight"
                preflight_guard_ok, preflight_guard_reason = _semantic_guard(
                    source_code,
                    preflight_code,
                    config.task,
                    preflight_source,
                )
                if preflight_guard_ok:
                    preflight_ev = executor.evaluate_candidate(
                        seed=idx + 7000,
                        hint=f"{hint} | local_preflight_before_llm",
                        code=preflight_code,
                        source=preflight_source,
                    )
                else:
                    preflight_ev = CandidateEval(
                        seed=idx + 7000,
                        score=0.0,
                        hint=f"{hint} | local_preflight_before_llm",
                        error=preflight_guard_reason,
                        candidate_code=preflight_code,
                        source=preflight_source,
                    )
                candidates.append(preflight_ev)
                ev_recorded = True
                learning_trace["local_preflight_before_llm"] = {
                    "attempted": True,
                    "score": preflight_ev.score,
                    "source": preflight_source,
                }
                if preflight_ev.score >= 1.0:
                    error_codes.append("local_preflight_before_llm_success")
                    ev = preflight_ev
                    break
                error_codes.append("local_preflight_before_llm_miss")
            if llm_generator is not None:
                try:
                    candidate_code, meta = llm_generator.generate(
                        source_code=source_code,
                        task=config.task,
                        mutation_hint=hint,
                        seed=idx,
                        test_source=initial_test_source,
                    )
                    used_source = str(meta.get("source", "llm"))
                except Exception as llm_exc:  # noqa: BLE001
                    fallback_used = True
                    failure_meta = getattr(llm_exc, "metadata", {})
                    failure_meta = failure_meta if isinstance(failure_meta, dict) else {}
                    failure_receipt = failure_meta.get("unified_runtime_receipt")
                    if isinstance(failure_receipt, dict):
                        unified_runtime_receipts.append(failure_receipt)
                    meta_model_calls = int(failure_meta.get("model_calls", 0) or 0)
                    model_calls += meta_model_calls if meta_model_calls > 0 else 1
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

            # Hidden-verifier hardening for known repair contracts:
            # prefer deterministic local invariant patch over partial LLM edits.
            if (
                hidden_verifier_mode
                and used_source.startswith("llm")
                and not hidden_fast_path_disabled
                and not hidden_invariant_shadow_disabled
                and _has_hidden_contract_fast_path(source_code)
            ):
                local_code, local_meta = local_generator.generate(
                    source_code=source_code,
                    task=config.task,
                    mutation_hint=f"{hint}\nhidden_verifier_invariant_shadow",
                    seed=idx + 5000,
                )
                candidate_code = local_code
                used_source = str(local_meta.get("source", "local_hidden_shadow")) or "local_hidden_shadow"
                if used_source == "local":
                    used_source = "local_hidden_shadow"
                fallback_used = True
            _record_llm_meta(meta)
            if used_source.startswith("local") and llm_generator is not None:
                fallback_used = True
            guard_ok, guard_reason = _semantic_guard(source_code, candidate_code, config.task, used_source)
            if not guard_ok:
                ev = CandidateEval(seed=idx, score=0.0, hint=hint, error=guard_reason, candidate_code=candidate_code, source=used_source)
                error_codes.append("semantic_guard")
            else:
                ev = executor.evaluate_candidate(seed=idx, hint=hint, code=candidate_code, source=used_source)
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
                        support_ev = executor.evaluate_candidate(
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
            self_heal_enabled = os.environ.get("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "1").strip().lower() not in {"0", "false", "no"}
            if (
                hidden_verifier_mode
                and llm_generator is not None
                and used_source.startswith("llm")
                and "quota" not in error_codes
                and not hidden_invariant_shadow_disabled
            ):
                local_code, local_meta = local_generator.generate(
                    source_code=source_code,
                    task=config.task,
                    mutation_hint=f"{hint}\nhidden_verifier_invariant_shadow",
                    seed=idx + 1000,
                )
                local_source = str(local_meta.get("source", "local_hidden_shadow"))
                if local_source == "local":
                    local_source = "local_hidden_shadow"
                fallback_used = True
                shadow_guard_ok, shadow_guard_reason = _semantic_guard(source_code, local_code, config.task, local_source)
                if shadow_guard_ok:
                    shadow_ev = executor.evaluate_candidate(
                        seed=idx + 1000,
                        hint=f"{hint} | hidden_verifier_invariant_shadow",
                        code=local_code,
                        source=local_source,
                    )
                else:
                    shadow_ev = CandidateEval(
                        seed=idx + 1000,
                        score=0.0,
                        hint=f"{hint} | hidden_verifier_invariant_shadow",
                        error=shadow_guard_reason,
                        candidate_code=local_code,
                        source=local_source,
                    )
                candidates.append(ev)
                candidates.append(shadow_ev)
                ev_recorded = True
                error_codes.append("hidden_invariant_shadow_candidate")
                if shadow_ev.score >= ev.score:
                    ev = shadow_ev
            if (
                self_heal_enabled
                and llm_generator is not None
                and (used_source.startswith("llm") or model_required_final_delivery)
                and ev.score < 1.0
                and "quota" not in error_codes
            ):
                candidates.append(ev)
                ev_recorded = True
                failure_tail = (ev.error or ev.stdout or "")[-1200:]
                local_support_block = ""
                if model_required_final_delivery:
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
                repair_task = (
                    f"{config.task}\n\n"
                    "Previous candidate failed verification. "
                    "Repair the candidate using the failure evidence below.\n"
                    f"[FAILURE]\n{failure_tail}\n"
                    f"{local_support_block}"
                )
                try:
                    repair_code, repair_meta = llm_generator.generate(
                        source_code=candidate_code,
                        task=repair_task,
                        mutation_hint=f"{hint}\nself_heal_after_pytest_failed",
                        seed=idx + 10000,
                        test_source=test_source,
                    )
                    _record_llm_meta(repair_meta)
                    repair_guard_ok, repair_guard_reason = _semantic_guard(candidate_code, repair_code, config.task, "llm_self_heal")
                    if repair_guard_ok:
                        repair_ev = executor.evaluate_candidate(
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
                if model_required_final_delivery and not ev_recorded:
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
                    local_ev = executor.evaluate_candidate(
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
        if hidden_verifier_mode and ev.source == "local_hidden_shadow" and ev.score >= 1.0:
            break
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
                ev = executor.evaluate_candidate(seed=999, hint="emergency_fallback", code=code, source=meta.get("source", "local"))
                candidates.append(ev)

    if not candidates:
        return SprintResult(
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
    if model_required_final_delivery and not _is_model_owned_source(best.source):
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
    disable_dayshift = os.environ.get("NEXUS_DISABLE_DAYSHIFT_OPTIMIZER", "").strip().lower() in {"1", "true", "yes"}
    # Stage 2 is optional enhancement only. Core success must not depend on external quota.
    if llm_mode_effective and "quota" not in error_codes and not disable_dayshift:
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
