from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from typing import Any, Mapping

from nexus.services.local_heal.local_model_provider import (
    LocalModelProvider,
    LocalModelProviderRequest,
    InertLocalModelProvider,
    OllamaLocalModelProvider,
    InjectedLocalModelProvider,
    RecordingLocalModelProvider,
    AuthorityBoundLocalModelProvider,
)
from nexus.services.local_heal.local_model_armor_receipt_gate import validate_local_model_armor_metadata
def _inject_ledger_state(raw_meta: dict[str, Any], provider: Any) -> None:
    summary = getattr(provider, "ledger_summary", None)
    if isinstance(summary, dict):
        raw_meta["llm_call_ledger"] = summary
        ledger = getattr(provider, "ledger", [])
        raw_meta["llm_call_ledger_records"] = [
            r.to_dict() if hasattr(r, "to_dict") else dict(r)
            for r in ledger
        ] if hasattr(ledger, "__iter__") else []
from nexus.services.local_heal.local_armor_attempt_receipt import build_local_armor_attempt_receipt
from nexus.services.local_heal.local_model_capability_context import LocalModelCapabilityContext, CapabilityExecutionResult
from nexus.services.local_heal.local_assist_receipts import build_local_assist_telemetry_from_executor_meta
from nexus.services.local_heal.candidate_isolation_gate import (
    CandidateIsolationReceipt,
    candidate_isolation_to_hybrid_route,
)
from nexus.services.local_heal.isolated_workspace_apply import (
    IsolatedApplyRequest,
    run_isolated_workspace_apply,
)
from nexus.services.local_heal.isolated_verifier import (
    IsolatedVerifierRequest,
    run_isolated_verifier,
)


@dataclass(frozen=True)
class LocalModelExecutorRequest:
    task_id: str
    problem_statement: str
    repo_root: str
    target_file: str
    selected_capabilities: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    receipt_context: dict[str, Any] = field(default_factory=dict)
    route_context: dict[str, Any] = field(default_factory=dict)
    model_name: str = ""
    dry_run: bool = True
    mutation_allowed: bool = False
    verifier_allowed: bool = False
    execution_topology: str = "single_local_model"


@dataclass(frozen=True)
class LocalModelExecutorResponse:
    invoked: bool
    local_model_called: bool
    candidate_patch: str
    candidate_hash: str
    reasoning_summary: str
    raw_model_metadata: dict[str, Any]
    provider: str
    model_name: str
    error: str
    timeout: bool
    evidence_refs: tuple[str, ...]
    cascade_stages_run: tuple[str, ...] = ()


def compute_capability_usage(
    *,
    selected_capabilities: tuple[str, ...] | list[str],
    metadata: Mapping[str, Any] | None = None,
    local_model_called: bool = False,
    route_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Causal used/not-used separation — never copy selected into used.

    Returns selected_capabilities, selected_capabilities_used, capability_usage_status.
    """
    selected = [str(c) for c in (selected_capabilities or ()) if str(c)]
    meta = dict(metadata or {})
    route = dict(route_context or {})
    status: dict[str, str] = {}
    used: list[str] = []

    def _mark(name: str, used_flag: bool, reason: str) -> None:
        if used_flag:
            status[name] = "used"
            if name not in used:
                used.append(name)
        else:
            status[name] = reason or "selected_not_consumed"

    # Bundle payloads injected into problem/route (from LocalAssist assembly).
    injected_payloads = route.get("consumed_evidence_ids") or meta.get("consumed_evidence_ids") or []
    evidence_section = str(route.get("capability_evidence_prompt_section") or "")
    evidence_ctx = route.get("capability_evidence_context") if isinstance(route.get("capability_evidence_context"), Mapping) else {}
    payload_caps = set()
    for ent in (evidence_ctx.get("entries") or []) if isinstance(evidence_ctx, Mapping) else []:
        if isinstance(ent, Mapping) and ent.get("has_consumer_payload") and ent.get("consumer_payload"):
            payload_caps.add(str(ent.get("name") or ""))
    for p in evidence_ctx.get("consumer_payloads") or [] if isinstance(evidence_ctx, Mapping) else []:
        if isinstance(p, Mapping) and p.get("capability"):
            payload_caps.add(str(p.get("capability")))
    # Markers in problem statement / evidence section.
    for cap in ("codeintel", "memory", "belief", "lancedb", "semantic_searcher"):
        if f"{cap}:payload" in evidence_section or f"{cap}:result" in evidence_section:
            payload_caps.add(cap)

    gate_results = meta.get("gate_results") if isinstance(meta.get("gate_results"), Mapping) else {}
    ddtree_result = meta.get("ddtree_result") if isinstance(meta.get("ddtree_result"), Mapping) else {}
    autoreason_result = meta.get("autoreason_result") if isinstance(meta.get("autoreason_result"), Mapping) else {}

    for cap in selected:
        if cap == "local_model_executor":
            _mark(cap, bool(local_model_called or meta.get("local_model_called")), "selected_not_consumed")
        elif cap == "memory":
            attempted = bool(meta.get("memory_retrieval_attempted"))
            prompt_included = bool(
                meta.get("memory_prompt_included")
                or (isinstance(meta.get("memory_trace"), Mapping) and meta["memory_trace"].get("prompt_included"))
                or meta.get("prompt_included")
            )
            # Shared evidence payload injection also counts as real Local consumption.
            payload_injected = cap in payload_caps or "memory:payload" in evidence_section or "memory:result" in evidence_section
            _mark(cap, (attempted and prompt_included) or payload_injected, "selected_not_consumed")
        elif cap in {"codeintel", "belief", "lancedb", "semantic_searcher"}:
            _mark(cap, cap in payload_caps, "selected_not_consumed")
        elif cap == "ddtree":
            invoked = bool(meta.get("ddtree_invoked") or (ddtree_result or {}).get("invoked"))
            _mark(cap, invoked, "selected_not_consumed")
        elif cap == "autoreason":
            invoked = bool(meta.get("autoreason_invoked") or (autoreason_result or {}).get("invoked"))
            _mark(cap, invoked, "selected_not_consumed")
        elif cap in {"artifact_gate", "claim_gate", "delivery_gate"}:
            gate = gate_results.get(cap) if isinstance(gate_results.get(cap), Mapping) else {}
            invoked = bool(
                meta.get(f"{cap}_invoked")
                or (gate.get("invoked") if gate else False)
            )
            _mark(cap, invoked, "selected_not_consumed")
        elif cap in {"repair_loop", "sandbox"}:
            actual = bool(
                meta.get("localheal_pipeline_actual_execution")
                or meta.get(f"{cap}_invoked")
                or meta.get(f"{cap}_gate_passed")
            )
            avail_only = bool(meta.get("localheal_pipeline_availability_only"))
            ok = actual and not avail_only and not bool(meta.get(f"{cap}_failed"))
            # Explicit failure marker
            if meta.get("repair_loop_status") in {"FAILED", "failed", "BLOCKED"}:
                ok = False
            _mark(cap, ok, "selected_not_consumed" if not actual else "failed_not_used")
        else:
            # Unknown selected: never auto-used
            _mark(cap, False, "selected_not_consumed")

    return {
        "selected_capabilities": list(selected),
        "selected_capabilities_used": list(used),
        "capability_usage_status": status,
    }


def _attach_local_armor_attempt_receipt(
    request: LocalModelExecutorRequest,
    raw_meta: dict[str, Any],
    *,
    local_model_called: bool,
    provider: str,
    model_name: str,
    evidence_refs: tuple[str, ...],
) -> dict[str, Any]:
    planner_snapshot = {}
    if isinstance(request.route_context, dict):
        signal_snapshot = request.route_context.get("signal_snapshot", {})
        if isinstance(signal_snapshot, dict):
            planner_snapshot = dict(signal_snapshot)
        for key in (
            "local_armor_execution_profile",
            "execution_profile",
            "profile_selected",
            "routing_tier",
            "difficulty",
        ):
            value = request.route_context.get(key)
            if value not in (None, "", []):
                planner_snapshot[key] = value
    raw_meta["local_armor_attempt_receipt"] = build_local_armor_attempt_receipt(
        task_id=request.task_id,
        metadata=raw_meta,
        local_model_called=local_model_called,
        evidence_refs=evidence_refs,
        provider=provider,
        model_name=model_name,
        planner_snapshot=planner_snapshot,
    )
    return raw_meta


def _resolve_execution_topology(request: LocalModelExecutorRequest) -> str:
    """Resolve execution topology strictly from planner-owned signal_snapshot.

    Resolution order:
    1. request.route_context["signal_snapshot"]["execution_topology"] (planner-owned)
    No fallbacks allowed. Missing or empty => raises ValueError.
    """
    route_ctx = request.route_context if isinstance(request.route_context, dict) else {}
    signal_snapshot = route_ctx.get("signal_snapshot")
    if not isinstance(signal_snapshot, dict):
        raise ValueError("Missing signal_snapshot in route_context")

    topology = signal_snapshot.get("execution_topology")
    if not topology:
        raise ValueError("Missing execution_topology in signal_snapshot")

    if "protocol_mode" not in signal_snapshot:
        raise ValueError("Missing protocol_mode in signal_snapshot")

    if topology not in ("local_committee_only", "local_cascade"):
        if "executor_model" not in signal_snapshot:
            raise ValueError("Missing executor_model in signal_snapshot")

    return str(topology)


def _project_pipeline_patch_to_target_file(unified_diff: str, target_file: str) -> tuple[str, dict[str, Any]]:
    """Keep only the target file section from a multi-file unified diff."""
    if not unified_diff.strip():
        return "", {"protocol_used": "pipeline_result", "normalized": False}

    target_norm = os.path.normpath(target_file)
    lines = unified_diff.splitlines()
    projected_sections: list[list[str]] = []
    current_section: list[str] = []
    current_target: str | None = None
    dropped_files: list[str] = []

    def _flush() -> None:
        nonlocal current_section, current_target
        if not current_section:
            return
        if current_target == target_norm:
            projected_sections.append(current_section[:])
        elif current_target:
            dropped_files.append(current_target)
        current_section = []
        current_target = None

    for line in lines:
        if line.startswith("--- a/"):
            _flush()
            current_target = os.path.normpath(line[len("--- a/"):].strip())
            current_section = [line]
            continue
        if current_section:
            current_section.append(line)
    _flush()

    projected_diff = "\n".join("\n".join(section) for section in projected_sections).strip()
    return projected_diff, {
        "protocol_used": "pipeline_result",
        "normalized": projected_diff != unified_diff.strip(),
        "target_file_only": True,
        "dropped_files": dropped_files,
    }


def _extract_old_new_text_from_unified_diff(unified_diff: str) -> tuple[str, str]:
    old_lines: list[str] = []
    new_lines: list[str] = []
    for line in unified_diff.splitlines(keepends=True):
        if line.startswith(("--- ", "+++ ", "@@")):
            continue
        if line.startswith("-"):
            old_lines.append(line[1:] if line[1:].endswith("\n") else line[1:] + "\n")
        elif line.startswith("+"):
            new_lines.append(line[1:] if line[1:].endswith("\n") else line[1:] + "\n")
        elif line.startswith(" "):
            shared = line[1:] if line[1:].endswith("\n") else line[1:] + "\n"
            old_lines.append(shared)
            new_lines.append(shared)
    return "".join(old_lines), "".join(new_lines)


def _build_unified_diff_from_search_and_replacement(
    request: LocalModelExecutorRequest,
    target_file: str,
    search_text: str,
    replacement_text: str,
    original_source_text: Optional[str] = None,
) -> str:
    import difflib
    import re as _re
    from pathlib import Path as _Path

    _anchor_line = 1
    if search_text and str(search_text).strip():
        try:
            if original_source_text is not None:
                _lines = original_source_text.splitlines()
            else:
                _fp = _Path(request.repo_root) / target_file if request.repo_root else _Path(target_file)
                _lines = _fp.read_text(encoding="utf-8").splitlines() if _fp.exists() else []

            if _lines:
                _search_first = str(search_text).strip().splitlines()[0].strip()
                for _i, _l in enumerate(_lines, 1):
                    if _search_first in _l:
                        _anchor_line = _i
                        break

            # C6BD: git pre-image fallback — search_text not in current source
            if _anchor_line == 1 and request.repo_root and target_file:
                from nexus.experimental.c6bd_preimage_retry import resolve_anchor_from_preimage
                _anchor_line = resolve_anchor_from_preimage(
                    repo_root=request.repo_root,
                    target_file=target_file,
                    search_text=str(search_text),
                    current_anchor=_anchor_line,
                )
        except Exception:
            pass

    search_lines = str(search_text).splitlines(keepends=True)
    replace_lines = str(replacement_text).splitlines(keepends=True)
    search_lines = [l if l.endswith("\n") else l + "\n" for l in search_lines]
    replace_lines = [l if l.endswith("\n") else l + "\n" for l in replace_lines]

    diff_gen = difflib.unified_diff(
        search_lines,
        replace_lines,
        fromfile=f"a/{target_file}",
        tofile=f"b/{target_file}",
        lineterm="\n",
    )

    adjusted_lines: list[str] = []
    for line in diff_gen:
        if line.startswith("@@"):
            m = _re.match(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@(.*)", line)
            if m:
                old_start = int(m.group(1))
                old_len = int(m.group(2))
                new_start = int(m.group(3))
                new_len = int(m.group(4))
                extra = m.group(5)
                adj_old = _anchor_line + old_start - 1
                adj_new = _anchor_line + new_start - 1 if new_start > 0 else _anchor_line
                line = f"@@ -{adj_old},{old_len} +{adj_new},{new_len} @@{extra}\n"
        adjusted_lines.append(line)
    return "".join(adjusted_lines)


def _reanchor_pipeline_patch_to_locked_search(
    request: LocalModelExecutorRequest,
    locked_search: str,
    projected_patch: str,
    original_source_text: Optional[str] = None,
) -> tuple[str, dict[str, Any]]:
    if not projected_patch.strip() or not locked_search.strip():
        return projected_patch, {"pipeline_locked_search_reanchored": False}

    old_text, new_text = _extract_old_new_text_from_unified_diff(projected_patch)
    if not old_text.strip() or not new_text.strip():
        return projected_patch, {"pipeline_locked_search_reanchored": False}

    if old_text.strip() == locked_search.strip():
        return projected_patch, {"pipeline_locked_search_reanchored": False}

    if original_source_text is not None:
        current_exists = True
        current_text = original_source_text
    else:
        current_exists, current_text = _read_text_snapshot(
            os.path.join(request.repo_root, request.target_file) if request.repo_root and request.target_file else ""
        )

    if not current_exists or locked_search.strip() not in current_text:
        return projected_patch, {"pipeline_locked_search_reanchored": False}

    rebuilt = _build_unified_diff_from_search_and_replacement(
        request,
        request.target_file,
        locked_search,
        new_text,
        original_source_text=original_source_text,
    ).strip()
    if not rebuilt:
        return projected_patch, {"pipeline_locked_search_reanchored": False}

    return rebuilt, {
        "protocol_used": "pipeline_result_locked_search_reanchored",
        "normalized": True,
        "pipeline_locked_search_reanchored": True,
        "pipeline_locked_search_reanchor_reason": "preimage_mismatch_current_source",
    }



def _unwrap_outer_markdown_fence(candidate_patch: str) -> tuple[str, dict[str, Any]]:
    stripped = candidate_patch.strip()
    if not stripped.startswith("```"):
        return candidate_patch, {"outer_markdown_fence_unwrapped": False}

    lines = stripped.splitlines()
    if len(lines) < 3 or not lines[-1].strip().startswith("```"):
        return candidate_patch, {"outer_markdown_fence_unwrapped": False}

    inner = "\n".join(lines[1:-1]).strip()
    if not inner:
        return candidate_patch, {"outer_markdown_fence_unwrapped": False}

    return inner, {
        "outer_markdown_fence_unwrapped": True,
        "normalized": True,
    }


def _unwrap_markdown_fence_inside_replace_block(candidate_patch: str) -> tuple[str, dict[str, Any]]:
    replace_start = "<<<<<<< REPLACE"
    replace_end = ">>>>>>> REPLACE"
    if replace_start not in candidate_patch or replace_end not in candidate_patch:
        return candidate_patch, {"replace_block_markdown_fence_unwrapped": False}

    start_idx = candidate_patch.find(replace_start)
    content_start = start_idx + len(replace_start)
    end_idx = candidate_patch.find(replace_end, content_start)
    if end_idx == -1:
        return candidate_patch, {"replace_block_markdown_fence_unwrapped": False}

    replacement = candidate_patch[content_start:end_idx]
    stripped = replacement.strip()
    if not stripped.startswith("```"):
        return candidate_patch, {"replace_block_markdown_fence_unwrapped": False}

    lines = stripped.splitlines()
    if len(lines) < 3 or not lines[-1].strip().startswith("```"):
        return candidate_patch, {"replace_block_markdown_fence_unwrapped": False}

    inner = "\n".join(lines[1:-1]).strip()
    if not inner:
        return candidate_patch, {"replace_block_markdown_fence_unwrapped": False}

    rebuilt = (
        candidate_patch[:content_start]
        + "\n"
        + inner
        + "\n"
        + candidate_patch[end_idx:]
    )
    return rebuilt, {
        "replace_block_markdown_fence_unwrapped": True,
        "normalized": True,
    }


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_text_snapshot(path: str) -> tuple[bool, str]:
    if not path or not os.path.exists(path):
        return False, ""
    with open(path, "r", encoding="utf-8") as f:
        return True, f.read()


def _truncate_excerpt(text: str, limit: int = 400) -> str:
    return (text or "")[:limit]


def _extract_projected_patch_header(unified_diff: str) -> str:
    header_lines: list[str] = []
    for line in unified_diff.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            header_lines.append(line)
            if len(header_lines) == 2:
                break
    return "\n".join(header_lines)


def _extract_projected_patch_paths(unified_diff: str) -> tuple[str, str]:
    old_path = ""
    new_path = ""
    for line in unified_diff.splitlines():
        if not old_path and line.startswith("--- a/"):
            old_path = os.path.normpath(line[len("--- a/"):].strip())
        elif not new_path and line.startswith("+++ b/"):
            new_path = os.path.normpath(line[len("+++ b/"):].strip())
        if old_path and new_path:
            break
    return old_path, new_path


def _extract_search_excerpt_from_projected_patch(unified_diff: str) -> str:
    search_lines: list[str] = []
    inside_hunk = False
    for line in unified_diff.splitlines():
        if line.startswith("@@"):
            inside_hunk = True
            continue
        if not inside_hunk:
            continue
        if line.startswith(("--- ", "+++ ")):
            continue
        if line.startswith((" ", "-")):
            search_lines.append(line[1:])
    return "\n".join(search_lines).strip()


def _classify_apply_failure_root_cause(
    *,
    target_file: str,
    projected_patch: str,
    apply_error: str,
    current_source_text: str,
    target_file_hash_before_apply: str,
    target_file_hash_after_restore: str,
    target_file_hash_at_apply: str,
) -> str:
    from nexus.experimental.forensic_apply_mismatch import classify_apply_failure_root_cause
    return classify_apply_failure_root_cause(
        target_file=target_file,
        projected_patch=projected_patch,
        apply_error=apply_error,
        current_source_text=current_source_text,
        target_file_hash_before_apply=target_file_hash_before_apply,
        target_file_hash_after_restore=target_file_hash_after_restore,
        target_file_hash_at_apply=target_file_hash_at_apply,
    )


def forensic_apply_mismatch(
    *,
    apply_error: str,
    locked_search: str,
    source_text: str,
    target_file: str = "",
) -> str:
    from nexus.experimental.forensic_apply_mismatch import forensic_apply_mismatch as _impl
    return _impl(
        apply_error=apply_error,
        locked_search=locked_search,
        source_text=source_text,
        target_file=target_file,
    )


def build_local_model_provider_from_signal_snapshot(
    route_context: Mapping[str, Any],
    injected_fn_key: str,
) -> LocalModelProvider:
    """Factory to instantiate provider specified strictly by planner contract signal_snapshot.

    No route selection or fallback allowed. Missing required fields fails closed.
    """
    signal_snapshot = route_context.get("signal_snapshot", {}) if isinstance(route_context, dict) else {}
    if not isinstance(signal_snapshot, dict):
        return InertLocalModelProvider()

    if "model_call_allowed" not in signal_snapshot:
        raise ValueError("Missing model_call_allowed in signal_snapshot")
    call_allowed = bool(signal_snapshot["model_call_allowed"])

    if not call_allowed:
        return InertLocalModelProvider()

    injected_fn = route_context.get(injected_fn_key)
    if injected_fn is not None:
        return InjectedLocalModelProvider(injected_fn)

    provider_type = signal_snapshot.get("executor_provider")
    model_name = signal_snapshot.get("executor_model")

    if not provider_type or not model_name:
        raise ValueError("Missing executor_provider or executor_model in signal_snapshot")

    provider_type = provider_type.lower()
    model_name = model_name.strip()

    if provider_type == "ollama" and model_name:
        return OllamaLocalModelProvider()

    return InertLocalModelProvider()



def compute_patch_lifecycle_state(
    pipeline_final_patch_len: int,
    pipeline_result_projected: bool,
    candidate_isolation_attempted: bool,
    isolated_apply_status: str,
    hash_match: bool,
    applied_patch_hash: str,
    selected_candidate_hash: str,
    verifier_result: str,
    solved: bool,
) -> str:
    """Derive mutually exclusive patch lifecycle state from existing execution results.

    Must not trigger execution, invoke provider, invoke verifier, or invoke isolated apply.
    Fails closed on missing data.
    """
    if pipeline_final_patch_len == 0:
        return "patch_absent"

    if not pipeline_result_projected:
        return "patch_present_not_projected"

    if not candidate_isolation_attempted:
        return "patch_projected_not_isolated"

    if isolated_apply_status != "applied":
        return "isolation_attempted_apply_failed"

    if not hash_match:
        return "isolation_applied_hash_mismatch"

    if verifier_result != "pass" or not solved:
        return "isolation_applied_hash_match_verifier_failed"

    if not applied_patch_hash or not selected_candidate_hash:
        return "isolation_applied_hash_mismatch"

    if applied_patch_hash != selected_candidate_hash:
        return "isolation_applied_hash_mismatch"

    return "verifier_passed"


def _summarize_committee_retry_truth(
    candidates: list[dict[str, Any]],
    winner: dict[str, Any] | None,
) -> tuple[bool, str, dict[str, Any]]:
    if not candidates:
        return False, "provider_not_called", {}
    if winner is not None:
        return True, "success", {}

    apply_statuses = {str(c.get("apply_status", "") or "") for c in candidates}
    rejection_reasons = {str(c.get("rejection_reason", "") or "") for c in candidates}

    if "format_rejected" in apply_statuses:
        return True, "committee_candidates_format_rejected", {}
    if "empty_patch" in apply_statuses:
        return True, "committee_candidates_empty_patch", {}
    if any(r == "winner_already_selected" for r in rejection_reasons):
        return True, "committee_winner_selected", {}

    # Committee no-winner: project classification
    try:
        from nexus.services.local_heal.committee_no_winner_classifier import classify_committee_no_winner
        classification = classify_committee_no_winner(
            candidates=candidates,
            winner=winner,
            verifier_evidence_passed=False,
            verifier_evidence_fields="",
        )
        projection = {
            "committee_no_winner_failure_class": classification.failure_class,
            "committee_no_winner_classification_available": classification.classification_available,
            "committee_no_winner_evidence": classification.evidence,
            "committee_no_winner_verifier_evidence_passed": classification.verifier_evidence_passed,
            "committee_no_winner_verifier_evidence_fields": classification.verifier_evidence_fields,
        }
    except Exception:
        projection = {
            "committee_no_winner_failure_class": "UNKNOWN_NEEDS_INSTRUMENTATION",
            "committee_no_winner_classification_available": False,
            "committee_no_winner_evidence": "classifier error",
        }
    return True, "committee_no_winner", projection


def compute_failure_class(
    output_len: int,
    provider_error: str,
    failure_reason: str,
    parse_error_kind: str,
    patch_lifecycle_state: str,
    verifier_result: str,
    solved: bool,
    contains_markdown_fence: bool,
    pipeline_failure_reason: str,
) -> tuple[str, str]:
    """Deterministic failure classifier from existing execution metadata.

    Returns (failure_class, unknown_reason).
    Classification only — must not parse/transform model output or change execution.
    """
    _reason = failure_reason or pipeline_failure_reason or ""

    # Priority 1: provider error
    if provider_error and provider_error.strip():
        return "provider_error", ""

    # Priority 2: parse failures that consumed model output
    # Must come before output_len check: a parse error explains why output_len is 0
    if parse_error_kind and parse_error_kind != "none" and parse_error_kind not in ("VALID_SEARCH_REPLACE", "FENCED_SEARCH_REPLACE"):
        return f"parse_failed:{parse_error_kind}", ""

    # Priority 3: terminal patch lifecycle states must override earlier pipeline
    # parsing failures once a real candidate has been projected/applied.
    if patch_lifecycle_state == "isolation_attempted_apply_failed":
        return "patch_apply_failed", ""
    if patch_lifecycle_state == "isolation_applied_hash_mismatch":
        return "hash_mismatch", ""
    if patch_lifecycle_state == "isolation_applied_hash_match_verifier_failed":
        return "verification_failed", ""

    # Priority 4: pipeline failure reasons (deterministic from existing telemetry)
    upper_reason = _reason.upper()
    upper_parse = (parse_error_kind or "").upper()

    if "NO_BLOCKS_FOUND" in upper_reason:
        return "no_blocks_found", ""
    if "SEARCH_MISMATCH" in upper_reason:
        return "search_mismatch", ""
    if "REPLACE_SYNTAX_ERROR" in upper_reason or "SYNTAX_ERROR" in upper_reason:
        return "replace_syntax_error", ""

    # Priority 5: fenced output
    if "REPLACEMENT_MARKDOWN_FENCE" in upper_parse or contains_markdown_fence:
        return "fenced_output", ""

    # Priority 6: refusal
    if "REFUSAL" in upper_parse or "REFUSAL" in upper_reason:
        return "refusal", ""

    # Priority 7: verifier passed
    if verifier_result == "pass" and solved:
        return "verifier_passed", ""

    # Priority 8: verifier failed with patch present (semantic wrong patch)
    if verifier_result == "fail" and patch_lifecycle_state not in ("patch_absent", ""):
        return "semantic_wrong_patch", ""

    # Fallback: unknown with reason
    unknown_reason = ""
    if output_len > 0:
        unknown_reason = f"output_len={output_len}"
        if _reason:
            unknown_reason += f" pipeline_failure_reason={_reason}"
        if upper_parse:
            unknown_reason += f" parse_error_kind={parse_error_kind}"
    return "unknown_with_reason", unknown_reason


def compute_verifier_failure_evidence(
    verifier_result: str,
    verifier_error: str,
    exit_code: int | None,
    stdout_tail: str,
    stderr_tail: str,
    verifier_command: tuple[str, ...],
    failure_class: str,
    patch_lifecycle_state: str,
) -> dict[str, str | bool]:
    """Capture bounded verifier failure evidence for downstream semantic retry.

    Must not change verifier behavior, trigger retry, alter patch content,
    or alter candidate isolation. Evidence capture only.
    """
    evidence_available = False
    failure_kind = ""
    stdout_excerpt = ""
    stderr_excerpt = ""
    cmd_hash = ""
    retry_ready = False

    if verifier_result == "fail":
        stdout_excerpt = (stdout_tail or "")[:1000]
        stderr_excerpt = (stderr_tail or "")[:1000]
        cmd_hash = hashlib.sha256(
            " ".join(verifier_command).encode("utf-8")
        ).hexdigest()[:16] if verifier_command else ""

        if verifier_error and "timeout" in verifier_error.lower():
            failure_kind = "timeout"
        elif exit_code is not None and exit_code != 0:
            combined = (stdout_excerpt + stderr_excerpt).lower()
            if "assert" in combined or "assertionerror" in combined or "assertion error" in combined:
                failure_kind = "assertion_failure"
            elif "traceback" in combined or "exception" in combined or "error" in combined:
                failure_kind = "exception"
            else:
                failure_kind = "nonzero_exit"
        elif not verifier_command:
            failure_kind = "missing_verifier_command"
        else:
            failure_kind = "unknown_verifier_failure"

        evidence_available = bool(
            stdout_excerpt
            or stderr_excerpt
            or verifier_error
            or (exit_code is not None and exit_code != 0)
        )

    retry_ready = (
        failure_class in ("verification_failed", "semantic_wrong_patch")
        and patch_lifecycle_state in (
            "isolation_applied_hash_match_verifier_failed",
            "isolation_applied_hash_mismatch",
        )
        and evidence_available
    )

    return {
        "verifier_failure_evidence_available": evidence_available,
        "verifier_failure_kind": failure_kind,
        "verifier_stdout_excerpt": stdout_excerpt,
        "verifier_stderr_excerpt": stderr_excerpt,
        "verifier_exit_code": exit_code if exit_code is not None else "",
        "verifier_command_hash": cmd_hash,
        "semantic_retry_evidence_ready": retry_ready,
        # C15-3B: Metadata for prompt evidence injection tracking
        "semantic_retry_verifier_evidence_injected": False,
        "semantic_retry_verifier_evidence_fields": "",
        "semantic_retry_prompt_evidence_hash": "",
    }


LOCAL_MODEL_INVOCATION_AUTHORITY_SCHEMA = "nexus.local_model_invocation_authority.v1"


def _request_local_model_authority(
    request: LocalModelExecutorRequest,
) -> Mapping[str, Any] | Any | None:
    route_context = request.route_context
    signal_snapshot = (
        route_context.get("signal_snapshot")
        if isinstance(route_context, Mapping)
        else None
    )
    if not isinstance(signal_snapshot, Mapping):
        return None
    if "local_model_invocation_authority" not in signal_snapshot:
        return None
    return signal_snapshot["local_model_invocation_authority"]


def _governed_failure_response(
    request: LocalModelExecutorRequest,
    *,
    authority: Any,
    reason: str,
    actual_provider: str = "",
    actual_model: str = "",
    model_binding_mode: str = "",
) -> LocalModelExecutorResponse:
    empty_hash = hashlib.sha256(b"").hexdigest()
    raw_metadata = {
        "error": reason,
        "reason": reason,
        "local_model_invocation_authority": authority,
        "actual_provider": actual_provider,
        "actual_model": actual_model,
        "model_binding_mode": model_binding_mode,
        "provider_call_count": 0,
        "ledger_count": 0,
    }
    return LocalModelExecutorResponse(
        invoked=False,
        local_model_called=False,
        candidate_patch="",
        candidate_hash=empty_hash,
        reasoning_summary=reason,
        raw_model_metadata=raw_metadata,
        provider="none",
        model_name="",
        error=reason,
        timeout=False,
        evidence_refs=request.evidence_refs,
    )


def _provider_identity(provider: Any, attribute: str) -> str:
    try:
        value = getattr(provider, attribute, "")
    except Exception:
        return ""
    return value if isinstance(value, str) else ""


def _provider_name_for_metadata(provider: Any) -> str:
    identity = _provider_identity(provider, "provider_identity")
    if identity:
        return identity
    # Legacy fallback is retained only for the explicit built-in Ollama type.
    return "ollama" if isinstance(provider, OllamaLocalModelProvider) else "injected"


def _validate_local_model_authority(
    request: LocalModelExecutorRequest,
    authority: Any,
) -> tuple[str, str, str]:
    if not isinstance(authority, Mapping):
        return "local_model_invocation_authority_malformed", "", ""
    if authority.get("schema") != LOCAL_MODEL_INVOCATION_AUTHORITY_SCHEMA:
        return "local_model_invocation_authority_schema_mismatch", "", ""
    if authority.get("status") != "ALLOW":
        return "local_model_invocation_authority_status_not_allow", "", ""
    if authority.get("gate_passed") is not True:
        return "local_model_invocation_authority_gate_not_passed", "", ""

    resolved_provider = authority.get("resolved_provider")
    resolved_model = authority.get("resolved_model")
    if not isinstance(resolved_provider, str) or not resolved_provider.strip():
        return "local_model_invocation_authority_provider_missing", "", ""
    if not isinstance(resolved_model, str) or not resolved_model.strip():
        return "local_model_invocation_authority_model_missing", "", ""

    route_context = request.route_context
    signal_snapshot = route_context.get("signal_snapshot") if isinstance(route_context, Mapping) else None
    if not isinstance(signal_snapshot, Mapping):
        return "local_model_invocation_authority_signal_snapshot_missing", "", ""
    if request.model_name != resolved_model:
        return "local_model_request_model_mismatch", resolved_provider, resolved_model
    if (
        signal_snapshot.get("executor_provider") != resolved_provider
        or signal_snapshot.get("executor_model") != resolved_model
    ):
        return "local_model_signal_identity_mismatch", resolved_provider, resolved_model

    execution_topology = signal_snapshot.get("execution_topology")
    committee_enabled = (
        signal_snapshot.get("local_committee_enabled") is True
        or signal_snapshot.get("use_committee") is True
    )
    if execution_topology in {"local_committee_only", "local_cascade"} or committee_enabled:
        return "local_model_committee_authority_required", resolved_provider, resolved_model
    return "", resolved_provider, resolved_model


def _prepare_governed_provider(
    request: LocalModelExecutorRequest,
    *,
    authority: Any,
    provider: LocalModelProvider | None,
) -> tuple[LocalModelProvider | None, AuthorityBoundLocalModelProvider | None, str]:
    reason, resolved_provider, resolved_model = _validate_local_model_authority(request, authority)
    if reason:
        return None, None, reason

    if provider is None:
        try:
            provider = build_local_model_provider_from_signal_snapshot(
                request.route_context,
                "candidate_generate_fn",
            )
        except ValueError as exc:
            return None, None, str(exc)

    actual_provider = _provider_identity(provider, "provider_identity")
    if not actual_provider:
        return None, None, "local_model_provider_identity_missing"
    if actual_provider != resolved_provider:
        return None, None, "local_model_provider_identity_mismatch"

    actual_model = _provider_identity(provider, "model_identity")
    binding_mode = _provider_identity(provider, "model_binding_mode") or "untagged"
    if binding_mode != "request_bound" and actual_model != resolved_model:
        reason = (
            "local_model_provider_model_identity_missing"
            if not actual_model
            else "local_model_provider_model_mismatch"
        )
        return None, None, reason

    if isinstance(provider, AuthorityBoundLocalModelProvider):
        guarded = provider
    else:
        if not isinstance(provider, RecordingLocalModelProvider):
            provider = RecordingLocalModelProvider(provider)
        guarded = AuthorityBoundLocalModelProvider(provider, resolved_model=resolved_model)
    return guarded, guarded, ""


def _stamp_governed_response(
    request: LocalModelExecutorRequest,
    response: LocalModelExecutorResponse,
    *,
    authority: Any,
    provider: LocalModelProvider | None,
    guard: AuthorityBoundLocalModelProvider | None,
) -> LocalModelExecutorResponse:
    raw_metadata = response.raw_model_metadata if isinstance(response.raw_model_metadata, dict) else {}
    actual_provider = _provider_identity(provider, "provider_identity") if provider is not None else ""
    actual_model = ""
    binding_mode = _provider_identity(provider, "model_binding_mode") if provider is not None else ""
    if guard is not None:
        actual_model = guard.actual_model
    if not actual_model and provider is not None:
        actual_model = _provider_identity(provider, "model_identity")
    if not actual_model and binding_mode == "request_bound":
        actual_model = str(authority.get("resolved_model") or "") if isinstance(authority, Mapping) else ""

    raw_metadata["local_model_invocation_authority"] = authority
    raw_metadata["actual_provider"] = actual_provider
    raw_metadata["actual_model"] = actual_model
    raw_metadata["model_binding_mode"] = binding_mode
    if guard is not None:
        _inject_ledger_state(raw_metadata, guard)
    ledger_summary = raw_metadata.get("llm_call_ledger")
    provider_call_count = (
        int(ledger_summary.get("total_calls", 0))
        if isinstance(ledger_summary, Mapping)
        else (guard.ledger_count if guard is not None else 0)
    )
    raw_metadata["provider_call_count"] = provider_call_count
    raw_metadata["ledger_count"] = provider_call_count

    failure_reason = guard.sticky_failure_reason if guard is not None else ""
    admitted_model = authority.get("resolved_model") if isinstance(authority, Mapping) else ""
    if (
        not failure_reason
        and (response.local_model_called or response.model_name)
        and response.model_name != admitted_model
    ):
        failure_reason = "local_model_response_model_mismatch"
    if failure_reason:
        raw_metadata["error"] = failure_reason
        raw_metadata["reason"] = failure_reason
        return _governed_failure_response(
            request,
            authority=authority,
            reason=failure_reason,
            actual_provider=actual_provider,
            actual_model=actual_model,
            model_binding_mode=binding_mode,
        )

    return response


class LocalModelExecutor:
    @staticmethod
    def run(request: LocalModelExecutorRequest, *, provider: LocalModelProvider | None = None) -> LocalModelExecutorResponse:
        authority = _request_local_model_authority(request)
        guard: AuthorityBoundLocalModelProvider | None = None
        governed_provider = provider
        if authority is not None:
            governed_provider, guard, authority_error = _prepare_governed_provider(
                request,
                authority=authority,
                provider=provider,
            )
            if authority_error:
                resp = _governed_failure_response(
                    request,
                    authority=authority,
                    reason=authority_error,
                    actual_provider=_provider_identity(provider, "provider_identity") if provider is not None else "",
                    actual_model=_provider_identity(provider, "model_identity") if provider is not None else "",
                    model_binding_mode=_provider_identity(provider, "model_binding_mode") if provider is not None else "",
                )
            else:
                resp = LocalModelExecutor._run_impl(request, provider=governed_provider)
            resp = _stamp_governed_response(
                request,
                resp,
                authority=authority,
                provider=governed_provider,
                guard=guard,
            )
        else:
            resp = LocalModelExecutor._run_impl(request, provider=provider)
        if resp and hasattr(resp, "raw_model_metadata") and isinstance(resp.raw_model_metadata, dict):
            defaults = {
                "semantic_retry_client_reused": False,
                "semantic_retry_client_class": "",
                "semantic_retry_prompt_len": 0,
                "semantic_retry_prompt_hash": "",
                "semantic_retry_prompt_has_verifier_evidence": False,
                "semantic_retry_raw_response_len": 0,
                "semantic_retry_raw_response_excerpt": "",
                "semantic_retry_response_is_none": True,
                "semantic_retry_response_empty": True,
                "semantic_retry_response_type": "NoneType",
                "semantic_retry_output_class": "",
                "semantic_retry_parser_error_kind": "",
                "semantic_retry_status": "",
                "semantic_retry_failure_reason": "",
                "semantic_retry_invocation_source": "none",
            }
            for k, v in defaults.items():
                if k not in resp.raw_model_metadata:
                    resp.raw_model_metadata[k] = v
            # RC-2: additive receipt_base (parent=run_anchor_hash; no final R3 cycle)
            try:
                from nexus.evidence.receipt_base import stamp_r1_local_response

                stamp_r1_local_response(resp, request=request)
            except Exception as exc:  # noqa: BLE001 — never break executor on projection
                resp.raw_model_metadata["receipt_base_error"] = str(exc)[:200]
                resp.raw_model_metadata["public_claim_allowed"] = False
        return resp

    @staticmethod
    def _run_impl(request: LocalModelExecutorRequest, *, provider: LocalModelProvider | None = None) -> LocalModelExecutorResponse:
        empty_hash = hashlib.sha256(b"").hexdigest()

        try:
            execution_topology = _resolve_execution_topology(request)
        except ValueError as e:
            return LocalModelExecutorResponse(
                invoked=False,
                local_model_called=False,
                candidate_patch="",
                candidate_hash=empty_hash,
                reasoning_summary="fail_closed_missing_topology",
                raw_model_metadata={"error": str(e)},
                provider="none",
                model_name="",
                error=str(e),
                timeout=False,
                evidence_refs=request.evidence_refs,
            )

        from nexus.services.local_heal.local_armor_execution_profile import (
            build_profile_controls,
            resolve_local_armor_profile,
        )
        profile_route_context = request.route_context if isinstance(request.route_context, dict) else {}
        initial_profile = resolve_local_armor_profile(profile_route_context)
        profile_route_context["local_armor_execution_profile"] = initial_profile.profile
        profile_route_context["local_armor_controls"] = {
            "profile": initial_profile.profile,
            "reason": initial_profile.reason,
            "planning_llm_allowed": initial_profile.planning_llm_allowed,
            "spec_gen_allowed": initial_profile.spec_gen_allowed,
            "candidate_cap": initial_profile.candidate_cap,
            "semantic_retry_cap": initial_profile.semantic_retry_cap,
            "committee_allowed": initial_profile.committee_allowed,
            "autoreason_allowed": initial_profile.autoreason_allowed,
            "ddtree_allowed": initial_profile.ddtree_allowed,
            "escalation_allowed": initial_profile.escalation_allowed,
        }
        profile_attempts = [initial_profile.profile]
        profile_escalation_reasons: list[str] = []

        def record_profile_state(raw_meta: dict[str, Any]) -> dict[str, Any]:
            final_profile = str(
                profile_route_context.get("local_armor_execution_profile", initial_profile.profile)
                or initial_profile.profile
            )
            raw_meta["initial_execution_profile"] = initial_profile.profile
            raw_meta["final_execution_profile"] = final_profile
            raw_meta["profile_attempts"] = list(profile_attempts)
            raw_meta["profile_escalation_count"] = len(profile_escalation_reasons)
            raw_meta["profile_escalation_reasons"] = list(profile_escalation_reasons)
            raw_meta["profile_transition_history"] = list(dict.fromkeys(profile_attempts))
            return raw_meta

        # 1. Handle Dry Run
        if request.dry_run:
            from nexus.services.local_heal.p3_route_skeleton import compute_p3_route_skeleton, p3_skeleton_to_dict
            from nexus.services.local_heal.p3_local_diagnosis import compute_p3_local_diagnosis, p3_diagnosis_to_dict
            from nexus.services.local_heal.p3_dry_run_receipt import compute_p3_dry_run_receipt, p3_dry_run_receipt_to_dict
            _p3_skeleton_request = {
                "task_id": request.task_id,
                "difficulty": request.route_context.get("difficulty", "") if isinstance(request.route_context, dict) else "",
                "route_context": request.route_context if isinstance(request.route_context, dict) else {},
            }
            _p3_skeleton = compute_p3_route_skeleton(_p3_skeleton_request)
            _p3_diag_request = {
                "task_id": request.task_id,
            }
            _p3_diag = compute_p3_local_diagnosis(
                request_metadata=_p3_diag_request,
                p3_skeleton={"p3_task_difficulty": _p3_skeleton.task_difficulty},
            )
            _p3_dry_run_receipt = compute_p3_dry_run_receipt(
                route_metadata={"p3_intended_topology": _p3_skeleton.intended_topology, "p3_task_difficulty": _p3_skeleton.task_difficulty},
                diagnosis_metadata=p3_diagnosis_to_dict(_p3_diag),
                guard_state=_p3_skeleton.intended_topology and "env_guarded_dry_run" or "shadow_only",
                env_guard_override=False,
            )
            return LocalModelExecutorResponse(
                invoked=False,
                local_model_called=False,
                candidate_patch="",
                candidate_hash=empty_hash,
                reasoning_summary="dry_run_active",
                raw_model_metadata={"dry_run": True, "execution_topology": execution_topology, **p3_skeleton_to_dict(_p3_skeleton), **p3_diagnosis_to_dict(_p3_diag), **p3_dry_run_receipt_to_dict(_p3_dry_run_receipt)},
                provider="none",
                model_name="",
                error="dry_run",
                timeout=False,
                evidence_refs=request.evidence_refs,
            )

        # 2. Build Provider
        if provider is None:
            try:
                provider = build_local_model_provider_from_signal_snapshot(
                    request.route_context,
                    "candidate_generate_fn"
                )
            except ValueError as e:
                return LocalModelExecutorResponse(
                    invoked=False,
                    local_model_called=False,
                    candidate_patch="",
                    candidate_hash=empty_hash,
                    reasoning_summary="fail_closed_missing_provider_or_model",
                    raw_model_metadata={"error": str(e)},
                    provider="none",
                    model_name="",
                    error=str(e),
                    timeout=False,
                    evidence_refs=request.evidence_refs,
                )

        # 3. Check Provider Availability
        if isinstance(provider, InertLocalModelProvider):
            return LocalModelExecutorResponse(
                invoked=True,
                local_model_called=False,
                candidate_patch="",
                candidate_hash=empty_hash,
                reasoning_summary="provider_unavailable",
                raw_model_metadata={},
                provider="inert",
                model_name="",
                error="provider_unavailable",
                timeout=False,
                evidence_refs=request.evidence_refs,
            )

        # N30R-V3 Phase 2: Wrap active provider in RecordingLocalModelProvider for authoritative ledger
        if not isinstance(provider, (RecordingLocalModelProvider, AuthorityBoundLocalModelProvider)):
            provider = RecordingLocalModelProvider(provider)

        # 4. Handle Active Memory Retrieval if enabled
        selected_caps = request.selected_capabilities
        lessons = []
        memory_adapter_metadata: dict[str, Any] = {}
        memory_trace: dict[str, Any] = {}
        memory_retrieval_attempted = False
        if "memory" in selected_caps:
            memory_retrieval_attempted = True
            try:
                from nexus.services.local_heal.memory_retrieval_adapter import MemoryRetrievalAdapter
                from nexus.services.local_heal.memory_trace import build_memory_trace_from_adapter
                adapter = MemoryRetrievalAdapter(enabled=True)
                lessons = adapter.retrieve_reranked(
                    query_text=request.problem_statement,
                    anchor_symbol=request.route_context.get("target_symbol") or "",
                    anchor_file=request.target_file,
                    limit=3,
                    max_chars=800,
                    task_id=request.task_id
                )
                adapter.last_metadata["prompt_included"] = bool(lessons)
                memory_adapter_metadata = dict(adapter.last_metadata)
                memory_trace = build_memory_trace_from_adapter(
                    memory_adapter_metadata,
                    query_text=request.problem_statement,
                ).to_dict()
            except Exception:
                memory_adapter_metadata = {
                    "enabled": True,
                    "status": "retrieval_failed",
                    "failure_reason": "executor_memory_retrieval_failed",
                    "no_memory_match": True,
                    "prompt_included": False,
                    "selected_ids": [],
                    "memory_evidence_ids": [],
                    "retrieval_sources": [],
                    "source_errors": {"executor": "memory_retrieval_failed"},
                    "source_counts": {},
                    "accepted": 0,
                    "query_text_hash": hashlib.sha256(request.problem_statement.encode("utf-8")).hexdigest()[:16] if request.problem_statement else "",
                }
                memory_trace = {
                    "available": True,
                    "trace_status": "TRACE_MISSING",
                    "retrieval_source": "",
                    "retrieval_sources": [],
                    "query_text_hash": memory_adapter_metadata["query_text_hash"],
                    "retrieved_count": 0,
                    "selected_ids": [],
                    "memory_evidence_ids": [],
                    "provenance_count": 0,
                    "rerank_mode": True,
                    "anchor_symbol": request.route_context.get("target_symbol") or "",
                    "anchor_file": request.target_file,
                    "no_memory_match": True,
                    "rejected_without_provenance": 0,
                    "evidence_packet_included": None,
                    "prompt_included": False,
                    "verifier_status": "NOT_MEASURED",
                    "learning_closure_id": "",
                    "findings_card_id": "",
                    "influence_status": "NOT_MEASURED",
                    "source_contract": "MEMORY_RETRIEVAL_ADAPTER",
                    "internal_only": True,
                    "shadow_ranking": {},
                    "primary_selected_id": "",
                }

        memory_context = ""
        if lessons:
            memory_context = "\n\n=== RELEVANT HISTORICAL LESSONS ===\n"
            for idx, lesson in enumerate(lessons, 1):
                content = ""
                if hasattr(lesson, "summary"):
                    content = lesson.summary
                elif hasattr(lesson, "content"):
                    content = lesson.content
                else:
                    content = str(lesson)
                memory_context += f"Lesson {idx}: {content}\n"
            memory_context += "====================================\n"
        if memory_retrieval_attempted and memory_adapter_metadata:
            memory_adapter_metadata["prompt_included"] = bool(memory_context)
            memory_trace["prompt_included"] = bool(memory_context)
            memory_trace["retrieved_count"] = int(memory_adapter_metadata.get("accepted", len(lessons)) or 0)
            memory_trace["selected_ids"] = list(memory_adapter_metadata.get("selected_ids", []) or [])
            memory_trace["memory_evidence_ids"] = list(memory_adapter_metadata.get("memory_evidence_ids", []) or [])

        memory_runtime_meta = {
            "memory_retrieval_attempted": memory_retrieval_attempted,
            "memory_prompt_included": bool(memory_context),
            "memory_trace_status": str(memory_trace.get("trace_status", "NOT_USED") or "NOT_USED"),
            "memory_query_text_hash": str(memory_adapter_metadata.get("query_text_hash", "") or ""),
            "memory_selected_ids": list(memory_adapter_metadata.get("selected_ids", []) or []),
            "memory_selected_count": len(memory_adapter_metadata.get("selected_ids", []) or []),
            "memory_retrieved_count": int(memory_adapter_metadata.get("accepted", len(lessons)) or 0),
            "memory_retrieval_sources": list(memory_adapter_metadata.get("retrieval_sources", []) or []),
            "memory_source_errors": dict(memory_adapter_metadata.get("source_errors", {}) or {}),
            "memory_source_counts": dict(memory_adapter_metadata.get("source_counts", {}) or {}),
            "memory_backend_receipts": list(
                memory_adapter_metadata.get("retrieval_backend_receipts", []) or []
            ),
            "memory_lancedb_query_attempted": any(
                receipt.get("backend") == "lancedb"
                and receipt.get("query_attempted")
                for receipt in memory_adapter_metadata.get(
                    "retrieval_backend_receipts", []
                ) or []
            ),
            "memory_lancedb_query_succeeded": any(
                receipt.get("backend") == "lancedb"
                and receipt.get("query_succeeded")
                for receipt in memory_adapter_metadata.get(
                    "retrieval_backend_receipts", []
                ) or []
            ),
            "memory_primary_selected_id": str(memory_adapter_metadata.get("primary_selected_id", "") or ""),
            "memory_no_match": bool(memory_adapter_metadata.get("no_memory_match", not lessons)),
            "memory_trace": dict(memory_trace or {}),
        }

        # 5. Source Anchor Context
        target_file = request.target_file
        target_symbol = request.route_context.get("target_symbol") or ""
        locked_search = request.route_context.get("locked_search") or ""

        source_anchor_hash = ""
        source_anchor_present = False
        source_anchor_source = "none"

        if locked_search and str(locked_search).strip():
            locked_text = locked_search if isinstance(locked_search, str) else str(locked_search)
            source_anchor_hash = hashlib.sha256(locked_text.encode("utf-8")).hexdigest()
            source_anchor_present = True
            source_anchor_source = "locked_search"
        elif target_file and target_symbol:
            try:
                from nexus.services.local_heal.local_model_source_anchor import build_local_model_source_anchor
                anchor = build_local_model_source_anchor(
                    source_root=request.repo_root,
                    target_file=target_file,
                    target_symbol=target_symbol,
                    locked_search="",
                )
                if anchor.span_hash:
                    source_anchor_hash = anchor.span_hash
                    source_anchor_present = True
                    source_anchor_source = anchor.canonical_span_source or "ast_boundary"
            except Exception:
                source_anchor_present = False
                source_anchor_source = "localizer_failed"

        # 6. Failure Feedback Context
        failure_feedback_present = False
        failure_feedback_text = ""
        route_ctx = request.route_context if isinstance(request.route_context, dict) else {}
        previous_failure = (
            route_ctx.get("previous_failure")
            or route_ctx.get("failure_reason")
            or route_ctx.get("verifier_failure")
            or route_ctx.get("verifier_output")
            or ""
        )
        if previous_failure and str(previous_failure).strip():
            try:
                from nexus.services.local_heal.failure_feedback_builder import build_failure_feedback
                failure_feedback_text = build_failure_feedback(
                    task_id=request.task_id,
                    failure_class=str(route_ctx.get("failure_class", "unknown")),
                    target_file=target_file,
                    target_symbol=target_symbol,
                    locked_search=locked_search,
                    previous_block_reason=str(previous_failure),
                    verifier_status=str(route_ctx.get("verifier_status", "fail")),
                    stdout_tail=str(route_ctx.get("stdout_tail", "")),
                    stderr_tail=str(route_ctx.get("stderr_tail", "")),
                )
                failure_feedback_present = True
            except Exception:
                failure_feedback_present = False

        # C6: Read provider_timeout_sec from signal_snapshot (planner-owned)
        _signal_snap_early = request.route_context.get("signal_snapshot", {}) if isinstance(request.route_context, dict) else {}
        provider_timeout_sec: float = float(_signal_snap_early.get("provider_timeout_sec", 120.0))

        # 7. Build capability context (shared across all topologies)
        cap_ctx_meta = {
            "profile_attempts": list(profile_attempts),
        }
        cap_ctx = LocalModelCapabilityContext(
            task_id=request.task_id,
            source_root=request.repo_root,
            problem_statement=request.problem_statement,
            target_file=target_file,
            target_symbol=target_symbol,
            selected_capabilities=selected_caps,
            execution_topology=execution_topology,
            evidence_refs=request.evidence_refs,
            source_anchor={"present": source_anchor_present, "source": source_anchor_source, "hash": source_anchor_hash},
            failure_feedback=failure_feedback_text,
            verifier_command=tuple(request.route_context.get("verifier_command", []) or []),
            candidate_pool=[],
            route_context=request.route_context,
            local_model_metadata=cap_ctx_meta,
            provider=provider,
        )

        # 8. Handle Execution Topology Branching
        if execution_topology == "local_committee_only":
            signal_snapshot = request.route_context.get("signal_snapshot", {}) if isinstance(request.route_context, dict) else {}
            protocol_mode = signal_snapshot["protocol_mode"]

            # Build enhanced problem statement with source anchor + failure feedback
            enhanced_problem = request.problem_statement
            if source_anchor_present:
                enhanced_problem += f"\n\nSource Anchor (target: {target_file}:{target_symbol}, hash: {source_anchor_hash[:16]}...)"
            if locked_search:
                enhanced_problem += f"\nLocked Search Span:\n```\n{locked_search}\n```"
            if failure_feedback_present and failure_feedback_text:
                enhanced_problem += f"\n\n{failure_feedback_text}"
            enhanced_problem += memory_context

            # C6AX: D-phase committee diagnosis — bridge D/A into local_committee_only path.
            # Construct minimal HealContext so CommitteeOrchestrator.diagnose_with_committee()
            # can read gate flags + diagnosis_models from signal_snapshot.
            # No-op (returns None) when diagnosis_committee_enabled is absent → fail-closed.
            from nexus.services.local_heal.context import HealContext as _DAHealContext, OperationalContext as _DAOpCtx, GovernanceContext as _DAGovCtx
            from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator as _DAOrchCls
            from pathlib import Path as _DAPath
            _da_op = _DAOpCtx(
                instance_id=request.task_id,
                repo_dir=_DAPath(str(getattr(request, "source_root", "/tmp"))),
                problem_statement=enhanced_problem,
                route_context=request.route_context,
            )
            _da_ctx = _DAHealContext(op=_da_op, gov=_DAGovCtx())
            _da_orch = _DAOrchCls.__new__(_DAOrchCls)
            _diagnosis_result = _da_orch.diagnose_with_committee(_da_ctx)
            _diagnosis_committee_invoked = bool(getattr(_da_op, "_diagnosis_committee_invoked", False))
            _diagnosis_committee_selected_model = str(getattr(_da_op, "_diagnosis_committee_selected_model", ""))
            # Record D/A telemetry into signal_snapshot so it flows to finalized row
            if isinstance(signal_snapshot, dict):
                signal_snapshot["diagnosis_committee_invoked"] = _diagnosis_committee_invoked
                signal_snapshot["diagnosis_committee_selected_model"] = _diagnosis_committee_selected_model

            # C6AY: Inject D-phase diagnosis guidance into candidate generation prompt.
            # Fail-closed: empty/malformed diagnosis does not pollute prompt.
            enhanced_problem, _diagnosis_guidance_injected, _diagnosis_guidance_hash = _inject_diagnosis_guidance(
                enhanced_problem, _diagnosis_result
            )
            if isinstance(signal_snapshot, dict):
                signal_snapshot["diagnosis_guidance_injected"] = _diagnosis_guidance_injected
                signal_snapshot["diagnosis_guidance_hash"] = _diagnosis_guidance_hash

            from nexus.services.local_heal.local_committee_candidate_provider import LocalCommitteeCandidateProvider
            from nexus.services.local_heal.candidate_decision_adapter import CandidateDecisionAdapter

            attempt_id_val = f"attempt-{len(profile_attempts)}" if profile_attempts else "attempt-1"
            execution_profile_val = profile_attempts[-1] if profile_attempts else "FULL"
            candidates = LocalCommitteeCandidateProvider.generate_committee_candidates(
                task_id=request.task_id,
                problem_statement=enhanced_problem,
                target_file=request.target_file,
                target_symbol=target_symbol,
                locked_search=locked_search,
                evidence_refs=request.evidence_refs,
                provider=provider,
                protocol_mode=protocol_mode,
                route_context=request.route_context,
                attempt_id=attempt_id_val,
                execution_profile=execution_profile_val,
            )

            # Update cap_ctx with candidates for this topology
            cap_ctx.candidate_pool = candidates
            cap_ctx.problem_statement = enhanced_problem

            decision = CandidateDecisionAdapter.select_candidate(
                candidates,
                selected_capabilities=selected_caps,
                ctx=cap_ctx,
            )

            # Local model is called if at least one candidate wasn't blocked/abstained
            local_model_called = any(not c.abstained for c in candidates)

            selected_patch = decision.selected_candidate_patch

            # C6AX: A-phase committee audit — audit the winner patch via CommitteeOrchestrator.
            # No-op (returns None) when audit_committee_enabled is absent → fail-closed.
            _da_op.final_patch = selected_patch
            _audit_result = _da_orch.audit_with_committee(_da_ctx)
            _audit_committee_invoked = bool(getattr(_da_op, "_audit_committee_invoked", False))
            _audit_committee_selected_model = str(getattr(_da_op, "_audit_committee_selected_model", ""))
            if isinstance(signal_snapshot, dict):
                signal_snapshot["audit_committee_invoked"] = _audit_committee_invoked
                signal_snapshot["audit_committee_selected_model"] = _audit_committee_selected_model

            patch_meta = {}
            retry_available = False
            retry_not_invoked_reason = ""
            mutation_allowed = bool(request.mutation_allowed or signal_snapshot.get("mutation_allowed", False))
            verifier_allowed = bool(request.verifier_allowed or signal_snapshot.get("verifier_allowed", False))
            verifier_command = tuple(request.route_context.get("verifier_command", []) or [])
            candidate_isolation_attempted = False
            candidate_isolated = False
            applied_patch_hash = ""
            hash_match = False
            isolated_apply_status = ""
            isolated_apply_error = ""
            applied_patch_hash_source = ""
            isolated_verifier_status = "not_run"
            isolated_verifier_error = ""
            isolated_verifier_stdout_tail = ""
            isolated_verifier_stderr_tail = ""
            isolated_verifier_exit_code = None
            hybrid_route = None
            if selected_patch.strip():
                selected_patch, patch_meta = _normalize_candidate_patch(request, locked_search, selected_patch)
                selected_hash = hashlib.sha256(selected_patch.encode("utf-8")).hexdigest() if selected_patch.strip() else empty_hash
            else:
                selected_hash = empty_hash

            # A5/B5: Wire parse failure into retry/feedback seam
            protocol_parse_failed = patch_meta.get("protocol_parse_failed", False)
            error_kind = patch_meta.get("error_kind", "")
            error_message = patch_meta.get("error_message", "")
            pipeline_retry_delegated = False
            delegated_retry_failure_reason = ""
            delegated_retry_final_patch_len = 0
            delegated_retry_output_class = ""
            delegated_retry_parser_error_kind = ""
            delegated_retry_status = ""
            delegated_retry_output_excerpt = ""
            if protocol_parse_failed:
                try:
                    from nexus.services.local_heal.failure_feedback_builder import build_failure_feedback
                    fence_feedback = build_failure_feedback(
                        task_id=request.task_id,
                        failure_class=error_kind or "PROTOCOL_PARSE_FAILED",
                        target_file=request.target_file,
                        target_symbol=target_symbol,
                        locked_search=locked_search,
                        previous_block_reason=error_kind or "protocol_parse_failed",
                        verifier_status="fail",
                    )
                    retry_available = True

                    # B5: Delegate retry to pipeline/orchestrator
                    if error_kind in {"REPLACEMENT_MARKDOWN_FENCE", "REPLACEMENT_PROSE_CONTAMINATION"} and provider is not None:
                        try:
                            from nexus.services.local_heal.pipeline import HealPipeline, HealContext as LegacyHealContext
                            from nexus.services.local_heal.corrector import SelfCorrector
                            from nexus.services.local_heal.errors import PatchError, PatchErrorKind
                            from pathlib import Path as _Path

                            def _provider_generate(system_prompt_or_req, user_prompt=None, model=None, timeout=None, options=None, api_type=None, **kwargs):
                                from nexus.services.local_heal.local_model_provider import LocalModelProviderRequest
                                if user_prompt is not None:
                                    prompt = (
                                        f"[SYSTEM]\n{system_prompt_or_req}\n\n"
                                        f"[USER]\n{user_prompt}"
                                    )
                                    model_name = model or kwargs.get("model", "")
                                else:
                                    prompt = getattr(system_prompt_or_req, "prompt", "") or str(system_prompt_or_req)
                                    model_name = getattr(system_prompt_or_req, "model_name", "") or model or kwargs.get("model", "")
                                _MODEL_ALIASES = {"qwen2.5-coder:7b": "qwen2.5-coder:7b-instruct"}
                                if model_name in _MODEL_ALIASES:
                                    model_name = _MODEL_ALIASES[model_name]
                                current_attempt_id = f"attempt-{len(profile_attempts)}" if profile_attempts else "attempt-1"
                                current_execution_profile = profile_attempts[-1] if profile_attempts else "FULL"
                                prov_req = LocalModelProviderRequest(
                                    task_id=request.task_id,
                                    prompt=prompt,
                                    evidence_refs=request.evidence_refs,
                                    model_name=model_name,
                                    timeout_sec=provider_timeout_sec,
                                    options=_opts,
                                    api_type=api_type or "generate",
                                    phase=kwargs.get("phase", "retry"),
                                    attempt_id=kwargs.get("attempt_id", current_attempt_id),
                                    execution_profile=kwargs.get("execution_profile", current_execution_profile),
                                )
                                prov_resp = provider.generate(prov_req)
                                return prov_resp.output_text or ""

                            pipeline = HealPipeline(ollama_generate_fn=_provider_generate)
                            route_ctx = request.route_context if isinstance(request.route_context, dict) else {}
                            route_ctx = dict(route_ctx)
                            route_ctx.setdefault("target_file", request.target_file)
                            route_ctx.setdefault("target_symbol", target_symbol)
                            repro_script = str(route_ctx.get("repro_script", "") or "")
                            python_executable = str(route_ctx.get("python_executable", "") or "")
                            retry_kind = getattr(PatchErrorKind, error_kind, PatchErrorKind.NO_BLOCKS_FOUND)
                            retry_prompt = SelfCorrector().build_retry_prompt(
                                original_user_prompt=request.problem_statement,
                                error=PatchError(kind=retry_kind, message=error_message or error_kind),
                                targeted_files=request.target_file,
                            )
                            heal_ctx = LegacyHealContext(
                                instance_id=request.task_id,
                                repo_dir=_Path(request.repo_root),
                                problem_statement=request.problem_statement,
                                user_prompt=retry_prompt,
                                attempt=2,
                                repro_script=repro_script,
                                skip_reproduction=not bool(repro_script),
                                failure_reason=error_kind,
                                route_context=route_ctx,
                                python_executable=python_executable,
                                max_tries=2,
                            )
                            result_ctx = pipeline.run(heal_ctx)
                            delegated_retry_failure_reason = str(getattr(result_ctx, "failure_reason", "") or "")
                            delegated_retry_final_patch_len = len(getattr(result_ctx, "final_patch", "") or "")
                            retry_model_decisions = list(getattr(result_ctx, "model_decisions", []) or [])
                            patch_retry_decisions = [
                                d for d in retry_model_decisions
                                if isinstance(d, dict) and d.get("phase") == "patch"
                            ]
                            if patch_retry_decisions:
                                last_retry = patch_retry_decisions[-1]
                                delegated_retry_output_class = str(last_retry.get("output_class", "") or "")
                                delegated_retry_parser_error_kind = str(last_retry.get("parser_error_kind", "") or "")
                                delegated_retry_status = str(last_retry.get("status", "") or "")
                                delegated_retry_output_excerpt = str(last_retry.get("output_excerpt", "") or "")[:500]
                            if getattr(result_ctx, "final_patch", ""):
                                selected_patch = result_ctx.final_patch
                                selected_hash = hashlib.sha256(selected_patch.encode("utf-8")).hexdigest()
                                pipeline_retry_delegated = True
                        except Exception:
                            pipeline_retry_delegated = False

                except Exception:
                    retry_available = False
                    retry_not_invoked_reason = "feedback_builder_unavailable"

            if selected_patch.strip():
                candidate_isolation_attempted = True
                _apply_search_text = str(locked_search) if locked_search else ""
                apply_receipt = run_isolated_workspace_apply(
                    IsolatedApplyRequest(
                        task_id=request.task_id,
                        source_root=request.repo_root,
                        target_file=target_file,
                        unified_diff=selected_patch,
                        selected_candidate_hash=selected_hash,
                        mutation_allowed=mutation_allowed,
                        search_text=_apply_search_text,
                    )
                )
                isolated_apply_status = apply_receipt.patch_apply_status
                isolated_apply_error = apply_receipt.patch_apply_error
                candidate_isolated = apply_receipt.candidate_output_isolated
                applied_patch_hash = apply_receipt.applied_patch_hash
                applied_patch_hash_source = apply_receipt.applied_patch_hash_source
                hash_match = apply_receipt.selected_candidate_hash_matches_applied
                if isolated_apply_status == "applied" and applied_patch_hash:
                    selected_hash = applied_patch_hash
                    hash_match = True


                verifier_receipt = run_isolated_verifier(
                    IsolatedVerifierRequest(
                        task_id=request.task_id,
                        workspace_path=apply_receipt.workspace_path or request.repo_root,
                        verifier_command=verifier_command,
                        verifier_allowed=verifier_allowed,
                    )
                )
                isolated_verifier_status = verifier_receipt.verifier_status
                isolated_verifier_error = verifier_receipt.verifier_error
                isolated_verifier_stdout_tail = verifier_receipt.stdout_tail
                isolated_verifier_stderr_tail = verifier_receipt.stderr_tail
                isolated_verifier_exit_code = verifier_receipt.exit_code

                isolation_receipt = CandidateIsolationReceipt(
                    candidate_id=decision.selected_candidate_id or f"{request.task_id}#committee-candidate",
                    selected_candidate_hash=selected_hash,
                    applied_patch_hash=applied_patch_hash,
                    selected_candidate_hash_matches_applied=hash_match,
                    candidate_output_isolated=candidate_isolated,
                    verifier_result=isolated_verifier_status,
                    evidence_refs=decision.decision_evidence_refs or request.evidence_refs,
                    local_model_called=local_model_called,
                    mutation_allowed=mutation_allowed,
                    # P2-3: Anchor fields
                    candidate_target_file=request.target_file,
                    candidate_target_symbol=request.route_context.get("target_symbol", "") if isinstance(request.route_context, dict) else "",
                )
                hybrid_route = candidate_isolation_to_hybrid_route(isolation_receipt)

            provider_name = _provider_name_for_metadata(provider)

            # Resolve selected model name or fallback to "committee"
            selected_model = ""
            for c in candidates:
                if c.candidate_id == decision.selected_candidate_id:
                    selected_model = c.model
                    break
            if not selected_model:
                selected_model = "committee"

            # Run gate executors for selected gate capabilities
            gate_results: dict[str, CapabilityExecutionResult] = {}
            for gate_name in ("artifact_gate", "claim_gate", "delivery_gate"):
                if gate_name in selected_caps:
                    from nexus.services.local_heal.local_model_capability_executors import (
                        ArtifactGateLocalExecutor, ClaimGateLocalExecutor, DeliveryGateLocalExecutor,
                    )
                    gate_executors = {
                        "artifact_gate": ArtifactGateLocalExecutor,
                        "claim_gate": ClaimGateLocalExecutor,
                        "delivery_gate": DeliveryGateLocalExecutor,
                    }
                    gate_results[gate_name] = gate_executors[gate_name]().execute(cap_ctx)

            ddtree_invoked = decision.ddtree_result.invoked if decision.ddtree_result else False
            autoreason_invoked = decision.autoreason_result.invoked if decision.autoreason_result else False

            # Build candidate telemetry details
            committee_candidates_info = []
            for c in candidates:
                c_hash = c.candidate_patch_hash if hasattr(c, "candidate_patch_hash") else getattr(c, "patch_sha256", "")
                is_selected = (decision.selected_candidate_id == c.candidate_id)
                c_applied_hash = applied_patch_hash if is_selected and isolated_apply_status == "applied" else ""
                c_hash_match = hash_match if is_selected else False

                # Determine rejection reason
                c_rejection_reason = ""
                if is_selected:
                    if isolated_verifier_status == "pass":
                        c_rejection_reason = ""
                    elif isolated_verifier_status == "fail":
                        c_rejection_reason = "verifier_failed"
                    elif isolated_apply_status != "applied":
                        if not selected_patch.strip():
                            c_rejection_reason = "patch_empty"
                        else:
                            c_rejection_reason = f"apply_failed: {isolated_apply_status}"
                else:
                    if isolated_verifier_status == "pass":
                        c_rejection_reason = "winner_already_selected"
                    else:
                        c_rejection_reason = "not_selected"

                committee_candidates_info.append({
                    "candidate_id": c.candidate_id,
                    "role": c.role,
                    "expected_model": c.model,
                    "invoked_model": c.model,
                    "provider_called": True,
                    "invoked": not bool(getattr(c, "abstained", False)),
                    "candidate_hash": c_hash,
                    "raw_candidate_hash": c_hash,
                    "selected_candidate_hash": selected_hash if is_selected else "",
                    "applied_patch_hash": c_applied_hash,
                    "selected_candidate_hash_matches_applied": c_hash_match,
                    "selected_hash_source": "applied_git_diff" if is_selected and hash_match else "none",
                    "applied_patch_hash_source": applied_patch_hash_source if is_selected else "none",
                    "apply_status": isolated_apply_status if is_selected else "none",
                    "isolated_verifier_result": isolated_verifier_status if is_selected else "none",
                    "selected": is_selected,
                    "winner": is_selected,
                    "rejection_reason": c_rejection_reason,
                    "evidence_present": bool(getattr(c, "evidence_refs", ()) or request.evidence_refs),
                    "gate_passed": bool(
                        is_selected
                        and isolated_apply_status == "applied"
                        and isolated_verifier_status == "pass"
                        and c_hash_match
                    ),
                    "outcome_contributed": bool(
                        is_selected
                        and isolated_apply_status == "applied"
                        and isolated_verifier_status == "pass"
                        and c_hash_match
                    ),
                })

            # Calculate counts and retrieve raw hash for provenance tracking
            proposers = [c for c in candidates if c.role != "judge"]
            judges = [c for c in candidates if c.role == "judge"]

            raw_cand_hash = ""
            selected_cand_obj = next((c for c in candidates if c.candidate_id == decision.selected_candidate_id), None)
            if selected_cand_obj:
                raw_cand_hash = selected_cand_obj.candidate_patch_hash if hasattr(selected_cand_obj, "candidate_patch_hash") else getattr(selected_cand_obj, "patch_sha256", "")

            raw_meta = {
                "execution_topology": "local_committee_only",
                "committee_candidate_count": len(candidates),
                "proposer_candidate_count": len(proposers),
                "judge_count": len(judges),
                "raw_candidate_hash": raw_cand_hash,
                "selected_hash_source": "applied_git_diff" if hash_match else "unaligned",
                "candidate_hash_matches_applied": hash_match,
                "committee_candidates": committee_candidates_info,
                "selected_candidate_id": decision.selected_candidate_id,
                "selected_by": decision.selected_by,
                "final_authority": decision.final_authority,
                **memory_runtime_meta,
                "protocol_normalization": patch_meta,
                "source_anchor_present": source_anchor_present,
                "source_anchor_source": source_anchor_source,
                "source_anchor_hash": source_anchor_hash[:16] if source_anchor_hash else "",
                "source_anchor_missing": not source_anchor_present,
                "localization_missing": (not source_anchor_present and source_anchor_source == "localizer_failed"),
                "target_file": target_file,
                "target_symbol": target_symbol,
                "locked_search_present": bool(locked_search.strip()),
                "failure_feedback_present": failure_feedback_present,
                "protocol_mode": "anchored_edit",
                "ddtree_invoked": ddtree_invoked,
                "autoreason_invoked": autoreason_invoked,
                "ddtree_result": decision.ddtree_result.to_receipt_dict() if decision.ddtree_result else None,
                "autoreason_result": decision.autoreason_result.to_receipt_dict() if decision.autoreason_result else None,
                "artifact_gate_invoked": gate_results.get("artifact_gate", CapabilityExecutionResult(name="artifact_gate", selected=False, invoked=False, gate_passed=False, outcome_contributed=False, evidence_present=False)).invoked,
                "claim_gate_invoked": gate_results.get("claim_gate", CapabilityExecutionResult(name="claim_gate", selected=False, invoked=False, gate_passed=False, outcome_contributed=False, evidence_present=False)).invoked,
                "delivery_gate_invoked": gate_results.get("delivery_gate", CapabilityExecutionResult(name="delivery_gate", selected=False, invoked=False, gate_passed=False, outcome_contributed=False, evidence_present=False)).invoked,
                "artifact_gate_passed": gate_results.get("artifact_gate", CapabilityExecutionResult(name="artifact_gate", selected=False, invoked=False, gate_passed=False, outcome_contributed=False, evidence_present=False)).gate_passed,
                "claim_gate_passed": gate_results.get("claim_gate", CapabilityExecutionResult(name="claim_gate", selected=False, invoked=False, gate_passed=False, outcome_contributed=False, evidence_present=False)).gate_passed,
                "delivery_gate_passed": gate_results.get("delivery_gate", CapabilityExecutionResult(name="delivery_gate", selected=False, invoked=False, gate_passed=False, outcome_contributed=False, evidence_present=False)).gate_passed,
                "gate_results": {k: v.to_receipt_dict() for k, v in gate_results.items()},
                "protocol_parse_failed": protocol_parse_failed,
                "protocol_parse_error_kind": error_kind,
                "retry_available": retry_available,
                "retry_not_invoked_reason": retry_not_invoked_reason,
                "pipeline_retry_delegated": pipeline_retry_delegated,
                "delegated_retry_failure_reason": delegated_retry_failure_reason,
                "delegated_retry_final_patch_len": delegated_retry_final_patch_len,
                "delegated_retry_output_class": delegated_retry_output_class,
                "delegated_retry_parser_error_kind": delegated_retry_parser_error_kind,
                "delegated_retry_status": delegated_retry_status,
                "delegated_retry_output_excerpt": delegated_retry_output_excerpt,
                "candidate_hash_empty": selected_hash == empty_hash,
                "candidate_isolation_attempted": candidate_isolation_attempted,
                "candidate_isolated": candidate_isolated,
                "candidate_output_isolated": candidate_isolated,
                "selected_candidate_hash": selected_hash if selected_hash != empty_hash else "",
                "applied_patch_hash": applied_patch_hash,
                "hash_match": hash_match,
                "selected_candidate_hash_matches_applied": hash_match,
                "isolated_apply_status": isolated_apply_status,
                "isolated_apply_error": isolated_apply_error,
                "applied_patch_hash_source": applied_patch_hash_source,
                "isolated_verifier_status": isolated_verifier_status,
                "isolated_verifier_error": isolated_verifier_error,
                "verifier_result": isolated_verifier_status,
                "mutation_allowed": mutation_allowed,
                "verifier_allowed": verifier_allowed,
            }
            _usage = compute_capability_usage(
                selected_capabilities=selected_caps,
                metadata=raw_meta,
                local_model_called=True,
                route_context=request.route_context if isinstance(request.route_context, dict) else {},
            )
            raw_meta.update(_usage)
            cap_ctx.local_model_metadata = raw_meta
            if hybrid_route is not None:
                raw_meta["hybrid_route"] = hybrid_route.to_dict()
                raw_meta["route_mode"] = hybrid_route.route_mode.value
                raw_meta["authority"] = hybrid_route.authority.value
            # N30R-V3 Phase 1: Populate profile fields in committee path too
            record_profile_state(raw_meta)
            raw_meta["committee_candidates_info"] = committee_candidates_info
            _inject_ledger_state(raw_meta, provider)
            armor_ok, armor_miss = validate_local_model_armor_metadata(raw_meta)
            raw_meta["armor_receipt_complete"] = armor_ok
            raw_meta["armor_receipt_missing_fields"] = armor_miss
            local_assist_telemetry = build_local_assist_telemetry_from_executor_meta(raw_meta)
            raw_meta["local_assist_telemetry"] = local_assist_telemetry.to_dict()
            # P3-A: Attach route skeleton metadata (shadow-only, no runtime behavior change)
            from nexus.services.local_heal.p3_route_skeleton import compute_p3_route_skeleton, p3_skeleton_to_dict
            _p3_skeleton_request = {
                "task_id": request.task_id,
                "difficulty": request.route_context.get("difficulty", "") if isinstance(request.route_context, dict) else "",
                "route_context": request.route_context if isinstance(request.route_context, dict) else {},
            }
            _p3_skeleton = compute_p3_route_skeleton(_p3_skeleton_request)
            raw_meta.update(p3_skeleton_to_dict(_p3_skeleton))
            raw_meta["solved"] = bool(
                hybrid_route is not None
                and hybrid_route.route_mode.value == "local_only_executed"
            )
            raw_meta["patch_lifecycle_state"] = compute_patch_lifecycle_state(
                pipeline_final_patch_len=len(selected_patch) if selected_patch.strip() else 0,
                pipeline_result_projected=bool(selected_patch.strip()),
                candidate_isolation_attempted=candidate_isolation_attempted,
                isolated_apply_status=isolated_apply_status,
                hash_match=hash_match,
                applied_patch_hash=applied_patch_hash,
                selected_candidate_hash=selected_hash if selected_hash != empty_hash else "",
                verifier_result=isolated_verifier_status,
                solved=raw_meta["solved"],
            )
            fc, ur = compute_failure_class(
                output_len=len(selected_patch) if selected_patch else 0,
                provider_error="",
                failure_reason="",
                parse_error_kind=error_kind,
                patch_lifecycle_state=raw_meta["patch_lifecycle_state"],
                verifier_result=isolated_verifier_status,
                solved=raw_meta["solved"],
                contains_markdown_fence=bool(patch_meta.get("outer_markdown_fence_unwrapped")),
                pipeline_failure_reason="",
            )
            raw_meta["failure_class"] = fc
            raw_meta["unknown_reason"] = ur
            vfe = compute_verifier_failure_evidence(
                verifier_result=isolated_verifier_status,
                verifier_error=isolated_verifier_error,
                exit_code=isolated_verifier_exit_code,
                stdout_tail=isolated_verifier_stdout_tail,
                stderr_tail=isolated_verifier_stderr_tail,
                verifier_command=verifier_command,
                failure_class=fc,
                patch_lifecycle_state=raw_meta["patch_lifecycle_state"],
            )
            raw_meta.update(vfe)
            # C15-3E: Verifier receipt presence fields
            raw_meta["verifier_stdout_tail_present"] = bool(isolated_verifier_stdout_tail)
            raw_meta["verifier_stderr_tail_present"] = bool(isolated_verifier_stderr_tail)
            raw_meta["verifier_error_present"] = bool(isolated_verifier_error)
            raw_meta["verifier_receipt_exit_code_present"] = isolated_verifier_exit_code is not None
            # P2-F: Store hash_match on route_context for orchestrator fallback
            if isinstance(request.route_context, dict):
                request.route_context["candidate_hash_matches_applied"] = hash_match
            raw_meta = _attach_local_armor_attempt_receipt(
                request,
                raw_meta,
                local_model_called=local_model_called,
                provider=provider_name,
                model_name=selected_model,
                evidence_refs=tuple(decision.decision_evidence_refs or request.evidence_refs),
            )

            return LocalModelExecutorResponse(
                invoked=True,
                local_model_called=local_model_called,
                candidate_patch=selected_patch,
                candidate_hash=selected_hash,
                reasoning_summary=f"selected_by_{decision.selected_by}",
                raw_model_metadata=raw_meta,
                provider=provider_name,
                model_name=selected_model,
                error="",
                timeout=False,
                evidence_refs=decision.decision_evidence_refs or request.evidence_refs,
            )

        # 8. LocalHeal Pipeline topology
        if execution_topology == "localheal_pipeline":
            from nexus.services.local_heal.local_model_capability_executors import (
                LocalHealPipelineCapabilityExecutor,
                DDTreeLocalExecutor,
                AutoreasonLocalExecutor,
                ArtifactGateLocalExecutor,
                ClaimGateLocalExecutor,
                DeliveryGateLocalExecutor,
            )

            original_target_content = None
            original_target_exists = False
            original_target_path = ""
            if request.repo_root and target_file:
                original_target_path = os.path.join(request.repo_root, target_file)
                if os.path.exists(original_target_path):
                    original_target_exists = True
                    with open(original_target_path, "r", encoding="utf-8") as f:
                        original_target_content = f.read()

            # Execute repair_loop (localheal pipeline bridge)
            repair_exec = LocalHealPipelineCapabilityExecutor().execute(cap_ctx)

            # Execute ddtree/autoreason/gates for this topology
            ddtree_exec = DDTreeLocalExecutor().execute(cap_ctx)
            autoreason_exec = AutoreasonLocalExecutor().execute(cap_ctx)
            artifact_exec = ArtifactGateLocalExecutor().execute(cap_ctx)
            claim_exec = ClaimGateLocalExecutor().execute(cap_ctx)
            delivery_exec = DeliveryGateLocalExecutor().execute(cap_ctx)

            # B3: Check if pipeline produced a result
            pipeline_final_patch = repair_exec.telemetries.get("pipeline_final_patch", "")
            pipeline_solve_eligible = repair_exec.telemetries.get("pipeline_solve_eligible", False)
            pipeline_failure_reason = repair_exec.telemetries.get("pipeline_failure_reason", "")
            first_attempt_patch_hash = repair_exec.telemetries.get("first_attempt_patch_hash", "")
            signal_snapshot = request.route_context.get("signal_snapshot", {}) if isinstance(request.route_context, dict) else {}
            mutation_allowed = bool(request.mutation_allowed or signal_snapshot.get("mutation_allowed", False))
            verifier_allowed = bool(request.verifier_allowed or signal_snapshot.get("verifier_allowed", False))
            verifier_command = tuple(request.route_context.get("verifier_command", []) or [])

            pipeline_final_patch_len = len(pipeline_final_patch) if pipeline_final_patch else 0
            pipeline_result_projected = False
            candidate_isolation_attempted = False
            candidate_isolated = False
            selected_candidate_hash = ""
            applied_patch_hash = ""
            hash_match = False
            candidate_patch = ""
            candidate_hash = empty_hash
            patch_meta = {}
            isolated_apply_status = ""
            isolated_apply_error = ""
            applied_patch_hash_source = ""
            isolated_verifier_status = "not_run"
            isolated_verifier_error = ""
            isolated_verifier_stdout_tail = ""
            isolated_verifier_stderr_tail = ""
            isolated_verifier_exit_code = None
            hybrid_route = None
            candidate_hash_empty = (candidate_hash == empty_hash)
            retry_available = False
            retry_not_invoked_reason = ""
            pipeline_retry_delegated = False
            delegated_retry_failure_reason = ""
            delegated_retry_final_patch_len = 0
            delegated_retry_output_class = ""
            delegated_retry_parser_error_kind = ""
            delegated_retry_status = ""
            delegated_retry_output_excerpt = ""
            # C15-3T: stage telemetry to distinguish first_patch_empty vs semantic_retry_empty vs provider_not_called
            delegated_retry_stage = "not_invoked"
            delegated_retry_provider_called = False
            # C15-3U: observability fields for delegated retry provider calls
            delegated_retry_provider_prompt_len = 0
            delegated_retry_provider_prompt_hash = ""
            delegated_retry_provider_model_name = ""
            delegated_retry_provider_response_is_none = False
            delegated_retry_provider_response_empty = False
            delegated_retry_provider_response_len = 0
            delegated_retry_provider_response_type = ""
            delegated_retry_provider_call_error = ""
            target_file_hash_before_apply = ""
            target_file_hash_after_restore = ""
            target_file_hash_at_apply = ""
            apply_source_text_at_apply = ""

            if pipeline_final_patch and pipeline_final_patch.strip():
                candidate_patch, patch_meta = _project_pipeline_patch_to_target_file(
                    pipeline_final_patch,
                    target_file,
                )
                candidate_patch, reanchor_meta = _reanchor_pipeline_patch_to_locked_search(
                    request,
                    locked_search,
                    candidate_patch,
                    original_source_text=original_target_content,
                )
                patch_meta = {
                    **patch_meta,
                    **reanchor_meta,
                    "normalized": bool(
                        patch_meta.get("normalized", False)
                        or reanchor_meta.get("normalized", False)
                    ),
                }
                pipeline_result_projected = True
                if candidate_patch.strip():
                    candidate_hash = hashlib.sha256(candidate_patch.encode("utf-8")).hexdigest()
                    candidate_isolation_attempted = True

                if candidate_isolation_attempted and original_target_path:
                    before_exists, before_text = _read_text_snapshot(original_target_path)
                    if before_exists or os.path.exists(original_target_path):
                        target_file_hash_before_apply = _sha256_text(before_text)
                    if original_target_exists:
                        os.makedirs(os.path.dirname(original_target_path), exist_ok=True)
                        with open(original_target_path, "w", encoding="utf-8") as f:
                            f.write(original_target_content or "")
                    elif os.path.exists(original_target_path):
                        os.remove(original_target_path)
                    after_exists, after_text = _read_text_snapshot(original_target_path)
                    if after_exists or not original_target_exists:
                        target_file_hash_after_restore = _sha256_text(after_text)
                    at_apply_exists, at_apply_text = _read_text_snapshot(original_target_path)
                    apply_source_text_at_apply = at_apply_text
                    if at_apply_exists or not original_target_exists:
                        target_file_hash_at_apply = _sha256_text(at_apply_text)

                if candidate_isolation_attempted:
                    _apply_search_text = str(locked_search) if locked_search else ""
                    apply_receipt = run_isolated_workspace_apply(
                        IsolatedApplyRequest(
                            task_id=request.task_id,
                            source_root=request.repo_root,
                            target_file=target_file,
                            unified_diff=candidate_patch,
                            selected_candidate_hash=candidate_hash,
                            mutation_allowed=mutation_allowed,
                            search_text=_apply_search_text,
                        )
                    )
                    isolated_apply_status = apply_receipt.patch_apply_status
                    isolated_apply_error = apply_receipt.patch_apply_error
                    candidate_isolated = apply_receipt.candidate_output_isolated
                    selected_candidate_hash = candidate_hash
                    applied_patch_hash = apply_receipt.applied_patch_hash
                    applied_patch_hash_source = apply_receipt.applied_patch_hash_source
                    hash_match = apply_receipt.selected_candidate_hash_matches_applied

                    verifier_receipt = run_isolated_verifier(
                        IsolatedVerifierRequest(
                            task_id=request.task_id,
                            workspace_path=apply_receipt.workspace_path or request.repo_root,
                            verifier_command=verifier_command,
                            verifier_allowed=verifier_allowed,
                        )
                    )
                    isolated_verifier_status = verifier_receipt.verifier_status
                    isolated_verifier_error = verifier_receipt.verifier_error
                    isolated_verifier_stdout_tail = verifier_receipt.stdout_tail
                    isolated_verifier_stderr_tail = verifier_receipt.stderr_tail
                    isolated_verifier_exit_code = verifier_receipt.exit_code

                    isolation_receipt = CandidateIsolationReceipt(
                        candidate_id=f"{request.task_id}#pipeline-candidate",
                        selected_candidate_hash=selected_candidate_hash,
                        applied_patch_hash=applied_patch_hash,
                        selected_candidate_hash_matches_applied=hash_match,
                        candidate_output_isolated=candidate_isolated,
                        verifier_result=isolated_verifier_status,
                        evidence_refs=request.evidence_refs,
                        local_model_called=bool(
                            repair_exec.telemetries.get("model_called", False)
                            or repair_exec.telemetries.get("patch_synthesis_model_called", False)
                        ),
                        mutation_allowed=mutation_allowed,
                        # P2-3: Anchor fields
                        candidate_target_file=request.target_file,
                        candidate_target_symbol=request.route_context.get("target_symbol", "") if isinstance(request.route_context, dict) else "",
                    )
                    hybrid_route = candidate_isolation_to_hybrid_route(isolation_receipt)
                    candidate_hash_empty = (candidate_hash == empty_hash)

            raw_meta = {
                "execution_topology": "localheal_pipeline",
                "protocol_mode": "anchored_edit",
                "candidate_hash_matches_applied": hash_match,
                "source_anchor_present": source_anchor_present,
                "source_anchor_source": source_anchor_source,
                "source_anchor_hash": source_anchor_hash[:16] if source_anchor_hash else "",
                "source_anchor_missing": not source_anchor_present,
                "localization_missing": (not source_anchor_present and source_anchor_source == "localizer_failed"),
                "target_file": target_file,
                "target_symbol": target_symbol,
                "locked_search_present": bool(locked_search.strip()),
                "failure_feedback_present": failure_feedback_present,
                "final_authority": "NexusVerifier",
                **memory_runtime_meta,
                "protocol_normalization": patch_meta,
                "ddtree_invoked": ddtree_exec.invoked,
                "autoreason_invoked": autoreason_exec.invoked,
                "artifact_gate_invoked": artifact_exec.invoked,
                "claim_gate_invoked": claim_exec.invoked,
                "delivery_gate_invoked": delivery_exec.invoked,
                **{k: v for k, v in repair_exec.telemetries.items()},
                "gate_results": {
                    "artifact_gate": artifact_exec.to_receipt_dict(),
                    "claim_gate": claim_exec.to_receipt_dict(),
                    "delivery_gate": delivery_exec.to_receipt_dict(),
                },
                "pipeline_result_projected": pipeline_result_projected,
                "pipeline_final_patch": pipeline_final_patch,
                "pipeline_final_patch_len": pipeline_final_patch_len,
                "pipeline_solve_eligible": pipeline_solve_eligible,
                "pipeline_failure_reason": pipeline_failure_reason,
                "localheal_pipeline_run_called": repair_exec.telemetries.get("localheal_pipeline_run_called", False),
                "localheal_pipeline_run_success": repair_exec.telemetries.get("localheal_pipeline_run_success", False),
                "orchestrator_run_reachable": repair_exec.telemetries.get("orchestrator_run_reachable", False),
                "candidate_hash_empty": candidate_hash_empty,
                "candidate_isolation_attempted": candidate_isolation_attempted,
                "candidate_isolated": candidate_isolated,
                "candidate_output_isolated": candidate_isolated,
                "selected_candidate_hash": selected_candidate_hash,
                "applied_patch_hash": applied_patch_hash,
                "hash_match": hash_match,
                "first_attempt_patch_hash": first_attempt_patch_hash,
                "selected_candidate_hash_matches_applied": hash_match,
                "isolated_apply_status": isolated_apply_status,
                "isolated_apply_error": isolated_apply_error,
                "applied_patch_hash_source": applied_patch_hash_source,
                "isolated_verifier_status": isolated_verifier_status,
                "isolated_verifier_error": isolated_verifier_error,
                "verifier_result": isolated_verifier_status,
                "mutation_allowed": mutation_allowed,
                "verifier_allowed": verifier_allowed,
            }
            _usage = compute_capability_usage(
                selected_capabilities=selected_caps,
                metadata=raw_meta,
                local_model_called=bool(
                    repair_exec.telemetries.get("model_called", False)
                    or repair_exec.telemetries.get("patch_synthesis_model_called", False)
                ),
                route_context=request.route_context if isinstance(request.route_context, dict) else {},
            )
            raw_meta.update(_usage)
            cap_ctx.local_model_metadata = raw_meta
            if hybrid_route is not None:
                raw_meta["hybrid_route"] = hybrid_route.to_dict()
                raw_meta["route_mode"] = hybrid_route.route_mode.value
                raw_meta["authority"] = hybrid_route.authority.value
            raw_meta["ddtree_result"] = ddtree_exec.to_receipt_dict()
            raw_meta["autoreason_result"] = autoreason_exec.to_receipt_dict()
            _inject_ledger_state(raw_meta, provider)
            armor_ok, armor_miss = validate_local_model_armor_metadata(raw_meta)
            raw_meta["armor_receipt_complete"] = armor_ok
            raw_meta["armor_receipt_missing_fields"] = armor_miss

            provider_name = _provider_name_for_metadata(provider)
            local_assist_telemetry = build_local_assist_telemetry_from_executor_meta(raw_meta)
            raw_meta["local_assist_telemetry"] = local_assist_telemetry.to_dict()
            # P3-A: Attach route skeleton metadata (shadow-only, no runtime behavior change)
            from nexus.services.local_heal.p3_route_skeleton import compute_p3_route_skeleton, p3_skeleton_to_dict
            _p3_skeleton_request = {
                "task_id": request.task_id,
                "difficulty": request.route_context.get("difficulty", "") if isinstance(request.route_context, dict) else "",
                "route_context": request.route_context if isinstance(request.route_context, dict) else {},
            }
            _p3_skeleton = compute_p3_route_skeleton(_p3_skeleton_request)
            raw_meta.update(p3_skeleton_to_dict(_p3_skeleton))

            raw_meta["solved"] = bool(
                pipeline_solve_eligible
                and hybrid_route is not None
                and hybrid_route.route_mode.value == "local_only_executed"
            )

            # C14: Downstream receipt truth — distinguish execution shell from model output
            raw_meta["executor_shell_reached"] = True
            raw_meta["actual_model_output_len"] = repair_exec.telemetries.get("patch_synthesis_output_len", 0)
            raw_meta["actual_model_name_used"] = repair_exec.telemetries.get("patch_synthesis_model_name", "")
            raw_meta["actual_provider_invoked"] = repair_exec.telemetries.get("provider_invoked", False)
            raw_meta["actual_model_called"] = repair_exec.telemetries.get("patch_synthesis_model_called", False)
            # Why model call didn't produce patch (if applicable)
            no_reason = ""
            if not pipeline_final_patch:
                if not raw_meta["actual_model_called"]:
                    no_reason = "model_not_called"
                elif raw_meta["actual_model_output_len"] == 0:
                    no_reason = "model_empty_output"
                elif "SEARCH_MISMATCH" in pipeline_failure_reason:
                    no_reason = "search_mismatch"
                elif "NO_BLOCKS_FOUND" in pipeline_failure_reason:
                    no_reason = "no_blocks_found"
                elif "REFUSAL" in pipeline_failure_reason:
                    no_reason = "model_refusal"
                elif "REPLACEMENT_MARKDOWN_FENCE" in pipeline_failure_reason:
                    no_reason = "fenced_output"
                else:
                    no_reason = "protocol_adherence_failure"
            raw_meta["no_model_call_reason"] = no_reason
            raw_meta["no_patch_reason"] = no_reason

            raw_meta["patch_lifecycle_state"] = compute_patch_lifecycle_state(
                pipeline_final_patch_len=pipeline_final_patch_len,
                pipeline_result_projected=pipeline_result_projected,
                candidate_isolation_attempted=candidate_isolation_attempted,
                isolated_apply_status=isolated_apply_status,
                hash_match=hash_match,
                applied_patch_hash=applied_patch_hash,
                selected_candidate_hash=selected_candidate_hash,
                verifier_result=isolated_verifier_status,
                solved=raw_meta["solved"],
            )

            # C15-3K: Apply failure diagnostics
            apply_failure_stage = "none"
            apply_failure_reason = ""
            apply_failure_error_excerpt = ""
            apply_failure_patch_len = 0
            apply_failure_patch_hash = ""
            apply_failure_projected = pipeline_result_projected
            apply_failure_selected_candidate_hash = selected_candidate_hash
            apply_failure_target_file = target_file
            apply_failure_search_excerpt = ""
            apply_failure_current_source_excerpt = ""
            apply_failure_projected_patch_excerpt = ""
            apply_failure_projection_header = ""
            apply_failure_original_header = ""
            apply_failure_root_cause = ""

            if raw_meta["patch_lifecycle_state"] == "isolation_attempted_apply_failed":
                apply_failure_stage = "isolated_apply"
                apply_failure_reason = isolated_apply_error or "patch_apply_failed"
                apply_failure_error_excerpt = (isolated_apply_error or "")[:500]
                apply_failure_patch_len = pipeline_final_patch_len
                apply_failure_patch_hash = selected_candidate_hash if selected_candidate_hash else ""
                apply_failure_search_excerpt = _truncate_excerpt(
                    _extract_search_excerpt_from_projected_patch(candidate_patch)
                )
                apply_failure_current_source_excerpt = _truncate_excerpt(apply_source_text_at_apply)
                apply_failure_projected_patch_excerpt = _truncate_excerpt(candidate_patch)
                apply_failure_projection_header = _extract_projected_patch_header(candidate_patch)
                apply_failure_original_header = (
                    f"--- a/{os.path.normpath(target_file)}\n+++ b/{os.path.normpath(target_file)}"
                    if target_file
                    else ""
                )
                apply_failure_root_cause = _classify_apply_failure_root_cause(
                    target_file=target_file,
                    projected_patch=candidate_patch,
                    apply_error=isolated_apply_error,
                    current_source_text=apply_source_text_at_apply,
                    target_file_hash_before_apply=target_file_hash_before_apply,
                    target_file_hash_after_restore=target_file_hash_after_restore,
                    target_file_hash_at_apply=target_file_hash_at_apply,
                )
            elif raw_meta["patch_lifecycle_state"] == "patch_present_not_projected":
                apply_failure_stage = "projection"
                apply_failure_reason = "patch_present_not_projected"
            elif raw_meta["patch_lifecycle_state"] == "patch_projected_not_isolated":
                apply_failure_stage = "isolated_apply"
                apply_failure_reason = "candidate_isolation_not_attempted"

            raw_meta["apply_failure_stage"] = apply_failure_stage
            raw_meta["apply_failure_reason"] = apply_failure_reason
            raw_meta["apply_failure_error_excerpt"] = apply_failure_error_excerpt
            raw_meta["apply_failure_patch_len"] = apply_failure_patch_len
            raw_meta["apply_failure_patch_hash"] = apply_failure_patch_hash
            raw_meta["apply_failure_projected"] = apply_failure_projected
            raw_meta["apply_failure_selected_candidate_hash"] = apply_failure_selected_candidate_hash
            raw_meta["apply_failure_target_file"] = apply_failure_target_file
            raw_meta["apply_failure_search_excerpt"] = apply_failure_search_excerpt
            raw_meta["apply_failure_current_source_excerpt"] = apply_failure_current_source_excerpt
            raw_meta["apply_failure_projected_patch_excerpt"] = apply_failure_projected_patch_excerpt
            raw_meta["apply_failure_target_file_hash_before_apply"] = target_file_hash_before_apply
            raw_meta["apply_failure_target_file_hash_after_restore"] = target_file_hash_after_restore
            raw_meta["apply_failure_target_file_hash_at_apply"] = target_file_hash_at_apply
            raw_meta["apply_failure_projection_header"] = apply_failure_projection_header
            raw_meta["apply_failure_original_header"] = apply_failure_original_header
            raw_meta["apply_failure_root_cause"] = apply_failure_root_cause

            fc, ur = compute_failure_class(
                output_len=raw_meta.get("actual_model_output_len", 0),
                provider_error=repair_exec.telemetries.get("patch_synthesis_provider_error", ""),
                failure_reason=pipeline_failure_reason,
                parse_error_kind=repair_exec.telemetries.get("output_class", ""),
                patch_lifecycle_state=raw_meta["patch_lifecycle_state"],
                verifier_result=isolated_verifier_status,
                solved=raw_meta["solved"],
                contains_markdown_fence=bool(repair_exec.telemetries.get("contains_markdown_fence", False)),
                pipeline_failure_reason=pipeline_failure_reason,
            )
            raw_meta["failure_class"] = fc
            raw_meta["unknown_reason"] = ur
            vfe = compute_verifier_failure_evidence(
                verifier_result=isolated_verifier_status,
                verifier_error=isolated_verifier_error,
                exit_code=isolated_verifier_exit_code,
                stdout_tail=isolated_verifier_stdout_tail,
                stderr_tail=isolated_verifier_stderr_tail,
                verifier_command=verifier_command,
                failure_class=fc,
                patch_lifecycle_state=raw_meta["patch_lifecycle_state"],
            )
            raw_meta.update(vfe)
            # C15-3E: Verifier receipt presence fields
            raw_meta["verifier_stdout_tail_present"] = bool(isolated_verifier_stdout_tail)
            raw_meta["verifier_stderr_tail_present"] = bool(isolated_verifier_stderr_tail)
            raw_meta["verifier_error_present"] = bool(isolated_verifier_error)
            raw_meta["verifier_receipt_exit_code_present"] = isolated_verifier_exit_code is not None

            # C15-3K: Retry eligibility diagnostics (after evidence computation)
            retry_eligibility_checked = True
            retry_eligible = False
            retry_not_invoked_reason = "none"

            # LITE has no semantic retry budget. A failed verifier may escalate
            # exactly once to STANDARD, and the transition is receipt-visible.
            current_profile = str(profile_route_context.get("local_armor_execution_profile", "STANDARD"))
            controls = profile_route_context.get("local_armor_controls", {}) or {}
            retry_cap = int(controls.get("semantic_retry_cap", 1) or 0)
            if retry_cap == 0 and not raw_meta["solved"]:
                if current_profile == "LITE" and bool(controls.get("escalation_allowed", True)):
                    escalated = build_profile_controls(
                        "STANDARD",
                        "escalated_from_lite_on_verification_failure",
                        initial_profile.planner_routing_tier,
                    )
                    profile_route_context["local_armor_execution_profile"] = escalated.profile
                    profile_route_context["local_armor_controls"] = {
                        "profile": escalated.profile,
                        "reason": escalated.reason,
                        "planning_llm_allowed": escalated.planning_llm_allowed,
                        "spec_gen_allowed": escalated.spec_gen_allowed,
                        "candidate_cap": escalated.candidate_cap,
                        "semantic_retry_cap": escalated.semantic_retry_cap,
                        "committee_allowed": escalated.committee_allowed,
                        "autoreason_allowed": escalated.autoreason_allowed,
                        "ddtree_allowed": escalated.ddtree_allowed,
                        "escalation_allowed": escalated.escalation_allowed,
                    }
                    profile_attempts.append("STANDARD")
                    profile_escalation_reasons.append("lite_to_standard_on_verification_failure")
                    retry_cap = escalated.semantic_retry_cap
                else:
                    retry_not_invoked_reason = "lite_profile_no_retry_cap_exhausted"

            if raw_meta["solved"]:
                retry_eligible = False
                retry_not_invoked_reason = "already_solved"
            elif provider is None:
                retry_eligible = False
                retry_not_invoked_reason = "delegated_consumer_unavailable"
            elif raw_meta["patch_lifecycle_state"] in ("isolation_attempted_apply_failed",):
                retry_eligible = False
                retry_not_invoked_reason = "patch_apply_failed"
            elif raw_meta["patch_lifecycle_state"] == "isolation_applied_hash_mismatch":
                retry_eligible = False
                retry_not_invoked_reason = "hash_mismatch"
            elif not raw_meta["semantic_retry_evidence_ready"]:
                retry_eligible = False
                retry_not_invoked_reason = "semantic_retry_evidence_not_ready"
            elif raw_meta["failure_class"] not in ("verification_failed", "semantic_wrong_patch"):
                retry_eligible = False
                retry_not_invoked_reason = "failure_class_not_retryable"
            elif not candidate_isolated:
                retry_eligible = False
                retry_not_invoked_reason = "candidate_not_isolated"
            else:
                retry_eligible = True
                retry_not_invoked_reason = "none"

            raw_meta["retry_eligibility_checked"] = retry_eligibility_checked
            raw_meta["retry_eligible"] = retry_eligible
            raw_meta["retry_not_invoked_reason"] = retry_not_invoked_reason

            if (
                provider is not None
                and raw_meta["semantic_retry_evidence_ready"]
                and raw_meta["failure_class"] in ("verification_failed", "semantic_wrong_patch")
                and candidate_isolated
                and hash_match
                and retry_cap > 0
            ):
                retry_available = True
                try:
                    from nexus.services.local_heal.pipeline import HealPipeline, HealContext as LegacyHealContext
                    from nexus.services.local_heal.corrector import SelfCorrector
                    from nexus.services.local_heal.errors import PatchError, PatchErrorKind
                    from pathlib import Path as _Path

                    _dr_route_ctx = request.route_context if isinstance(request.route_context, dict) else {}
                    _dr_signal = _dr_route_ctx.get("signal_snapshot", {}) if isinstance(_dr_route_ctx, dict) else {}
                    _dr_requested_model = str(_dr_signal.get("executor_model", "") or "") if isinstance(_dr_signal, dict) else ""
                    _dr_candidate_models = list(_dr_signal.get("delegated_retry_candidate_models", []) or []) if isinstance(_dr_signal, dict) else []

                    def _provider_generate(system_prompt_or_req, user_prompt=None, model=None, timeout=None, options=None, api_type=None, **kwargs):
                        nonlocal delegated_retry_provider_called
                        nonlocal delegated_retry_provider_prompt_len, delegated_retry_provider_prompt_hash
                        nonlocal delegated_retry_provider_model_name
                        nonlocal delegated_retry_provider_response_is_none, delegated_retry_provider_response_empty
                        nonlocal delegated_retry_provider_response_len, delegated_retry_provider_response_type
                        nonlocal delegated_retry_provider_call_error
                        from nexus.services.local_heal.local_model_provider import LocalModelProviderRequest
                        if user_prompt is not None:
                            prompt = (
                                f"[SYSTEM]\n{system_prompt_or_req}\n\n"
                                f"[USER]\n{user_prompt}"
                            )
                            model_name = model or kwargs.get("model", "")
                        else:
                            prompt = getattr(system_prompt_or_req, "prompt", "") or str(system_prompt_or_req)
                            model_name = getattr(system_prompt_or_req, "model_name", "") or model or kwargs.get("model", "")

                        _MODEL_ALIASES = {"qwen2.5-coder:7b": "qwen2.5-coder:7b-instruct"}
                        if model_name in _MODEL_ALIASES:
                            model_name = _MODEL_ALIASES[model_name]

                        if _dr_requested_model and model_name != _dr_requested_model:
                            _dr_resolved = _dr_requested_model
                            if _dr_resolved in _MODEL_ALIASES:
                                _dr_resolved = _MODEL_ALIASES[_dr_resolved]
                            model_name = _dr_resolved

                        delegated_retry_provider_called = True
                        delegated_retry_provider_prompt_len = len(prompt) if prompt else 0
                        delegated_retry_provider_prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16] if prompt else ""
                        delegated_retry_provider_model_name = model_name or ""

                        try:
                            _opts = options or kwargs.get("options")
                            current_attempt_id = f"attempt-{len(profile_attempts)}" if profile_attempts else "attempt-1"
                            current_execution_profile = profile_attempts[-1] if profile_attempts else "STANDARD"
                            prov_req = LocalModelProviderRequest(
                                task_id=request.task_id,
                                prompt=prompt,
                                evidence_refs=request.evidence_refs,
                                model_name=model_name,
                                timeout_sec=provider_timeout_sec,
                                options=_opts,
                                api_type=api_type or "generate",
                                phase=kwargs.get("phase", "retry"),
                                attempt_id=kwargs.get("attempt_id", current_attempt_id),
                                execution_profile=kwargs.get("execution_profile", current_execution_profile),
                            )
                            prov_resp = provider.generate(prov_req)
                            delegated_retry_provider_response_is_none = prov_resp is None
                            if prov_resp is not None:
                                output_text = prov_resp.output_text or ""
                                delegated_retry_provider_response_empty = not output_text
                                delegated_retry_provider_response_len = len(output_text)
                                delegated_retry_provider_response_type = type(prov_resp).__name__
                                if prov_resp.error:
                                    delegated_retry_provider_call_error = prov_resp.error
                            else:
                                output_text = ""
                                delegated_retry_provider_response_empty = True
                                delegated_retry_provider_response_len = 0
                                delegated_retry_provider_response_type = "NoneType"
                            return output_text
                        except Exception as e:
                            delegated_retry_provider_call_error = f"{type(e).__name__}: {str(e)}"
                            delegated_retry_provider_response_is_none = True
                            delegated_retry_provider_response_empty = True
                            delegated_retry_provider_response_len = 0
                            delegated_retry_provider_response_type = "Exception"
                            raise e

                    pipeline = HealPipeline(ollama_generate_fn=_provider_generate)
                    route_ctx = request.route_context if isinstance(request.route_context, dict) else {}
                    route_ctx = dict(route_ctx)
                    route_ctx.setdefault("target_file", request.target_file)
                    route_ctx.setdefault("target_symbol", target_symbol)
                    route_ctx["semantic_retry_seed"] = {
                        "verifier_failure_evidence_available": raw_meta["verifier_failure_evidence_available"],
                        "semantic_retry_evidence_ready": raw_meta["semantic_retry_evidence_ready"],
                        "failure_class": raw_meta["failure_class"],
                        "verifier_failure_kind": raw_meta["verifier_failure_kind"],
                        "verifier_stdout_excerpt": raw_meta["verifier_stdout_excerpt"],
                        "verifier_stderr_excerpt": raw_meta["verifier_stderr_excerpt"],
                        "verifier_exit_code": raw_meta["verifier_exit_code"],
                        "verifier_command_hash": raw_meta["verifier_command_hash"],
                    }
                    repro_script = str(route_ctx.get("repro_script", "") or "")
                    python_executable = str(route_ctx.get("python_executable", "") or "")
                    # C15-5C: inject verifier stdout/stderr into PatchError.message
                    # so committee models receive concrete failure evidence, not just exit code.
                    # N1: Assertion-grounded signals extraction
                    _dr_verifier_stdout = str(raw_meta.get("verifier_stdout_excerpt", "") or "")
                    _dr_verifier_stderr = str(raw_meta.get("verifier_stderr_excerpt", "") or "")
                    _dr_failure_kind = str(raw_meta.get("verifier_failure_kind", "") or "")
                    _dr_patch_error_msg = f"Verifier failed with exit code {raw_meta['verifier_exit_code']}"
                    if _dr_verifier_stdout:
                        _dr_patch_error_msg += f"\n### VERIFIER STDOUT\n{_dr_verifier_stdout}"
                    if _dr_verifier_stderr:
                        _dr_patch_error_msg += f"\n### VERIFIER STDERR\n{_dr_verifier_stderr}"
                    if _dr_failure_kind == "assertion_failure" and _dr_verifier_stdout:
                        _dr_assertion_lines = []
                        for _line in _dr_verifier_stdout.split("\n"):
                            if "assert" in _line.lower() or "AssertionError" in _line or "FAIL" in _line:
                                _dr_assertion_lines.append(_line.strip())
                        if _dr_assertion_lines:
                            _dr_patch_error_msg += "\n### ASSERTION-GROUNDED FAILURE SIGNALS\n" + "\n".join(_dr_assertion_lines) + "\n\nThe assertion above is the GROUND TRUTH: your patch must make this assertion pass. Do NOT change the test — fix the source code."
                    retry_prompt = SelfCorrector().build_retry_prompt(
                        original_user_prompt=request.problem_statement,
                        error=PatchError(
                            kind=PatchErrorKind.LOGIC_REGRESSION,
                            message=_dr_patch_error_msg,
                        ),
                        targeted_files=request.target_file,
                    )

                    # C15-5D: 讀取磁碟上的當前檔案內容以預填 _dr_localized_files。
                    # 這可以繞過委員會小模型的 LocalizationPhase，避免其定位失敗，
                    # 同時確保 PatchSynthesisPhase 的 Prompt Context 拿到的是磁碟最新狀態，而非舊版 locked_search。
                    # C15-5H fix: 必須使用 LocalizedFile 而非 raw tuple，否則 PatchSynthesisPhase.run()
                    # 在 loc_file.path 時會丟 AttributeError（LocalizationPhase skip 後不做轉換）。
                    _locked_search_for_dr = str(route_ctx.get("locked_search") or "")
                    _dr_localized_files: list = []
                    if request.target_file:
                        _target_full_path = _Path(request.repo_root) / request.target_file
                        if _target_full_path.exists():
                            try:
                                from nexus.services.local_heal.interface import LocalizedFile as _LocalizedFile
                                _current_content = _target_full_path.read_text(encoding="utf-8", errors="replace")
                                _dr_localized_files = [_LocalizedFile(path=request.target_file, content=_current_content)]
                            except Exception:
                                pass


                    _dr_committee_winner = None
                    _dr_committee_candidate_count = 0
                    _dr_committee_candidates_list = []
                    import sys as _dbg
                    import json as _json
                    print(f"[C15-5C] candidate_models={_dr_candidate_models} len={len(_dr_candidate_models)}", file=_dbg.stderr)
                    if len(_dr_candidate_models) > 1:
                        _dr_committee_candidate_count = len(_dr_candidate_models)
                        for idx, _dr_cand_model in enumerate(_dr_candidate_models, start=1):
                            _dr_cand_resolved = _dr_cand_model
                            import re as _re
                            _safe_model_slug = _re.sub(r'[^a-zA-Z0-9]', '-', _dr_cand_model.lower())
                            _safe_model_slug = _re.sub(r'-+', '-', _safe_model_slug).strip('-')
                            _cand_id = f"{request.task_id}#delegated-retry-{idx:02d}-{_safe_model_slug}"

                            # Explicitly capture current context before closure definition
                            current_attempt_id = f"attempt-{len(profile_attempts)}" if profile_attempts else "attempt-1"
                            current_execution_profile = profile_attempts[-1] if profile_attempts else "FULL"

                            def _make_committee_provider(_model_name):
                                def _cp_gen(system_prompt_or_req, user_prompt=None, model=None, timeout=None, options=None, api_type=None, **kwargs):
                                    from nexus.services.local_heal.local_model_provider import LocalModelProviderRequest
                                    if user_prompt is not None:
                                        prompt = f"[SYSTEM]\n{system_prompt_or_req}\n\n[USER]\n{user_prompt}"
                                    else:
                                        prompt = getattr(system_prompt_or_req, "prompt", "") or str(system_prompt_or_req)
                                    _resolved_model = _model_name
                                    _MODEL_ALIASES = {"qwen2.5-coder:7b": "qwen2.5-coder:7b-instruct"}
                                    if _resolved_model in _MODEL_ALIASES:
                                        _resolved_model = _MODEL_ALIASES[_resolved_model]
                                    _opts = options or kwargs.get("options")
                                    prov_req = LocalModelProviderRequest(
                                        task_id=request.task_id,
                                        prompt=prompt,
                                        evidence_refs=request.evidence_refs,
                                        model_name=_resolved_model,
                                        timeout_sec=provider_timeout_sec,
                                        options=_opts,
                                        phase=kwargs.get("phase", "retry"), # 這是 retry phase
                                        attempt_id=kwargs.get("attempt_id", current_attempt_id),
                                        execution_profile=kwargs.get("execution_profile", current_execution_profile),
                                    )
                                    prov_resp = provider.generate(prov_req)
                                    out = prov_resp.output_text or ""
                                    print(f"[C15-5C] _cp_gen model={_model_name} resolved={_resolved_model} prompt_len={len(prompt)} out_len={len(out)} err={prov_resp.error}", file=_dbg.stderr)
                                    return out
                                return _cp_gen

                            _cp_pipeline = HealPipeline(ollama_generate_fn=_make_committee_provider(_dr_cand_resolved))
                            _cp_route_ctx = dict(route_ctx)
                            _cp_route_ctx["semantic_retry_seed"] = route_ctx.get("semantic_retry_seed", {})
                            _cp_heal_ctx = LegacyHealContext(
                                instance_id=f"{request.task_id}#committee-{_dr_cand_resolved}",
                                repo_dir=_Path(request.repo_root),
                                problem_statement=request.problem_statement,
                                user_prompt=retry_prompt, attempt=1,
                                repro_script=repro_script,
                                skip_reproduction=not bool(repro_script),
                                failure_reason=raw_meta["failure_class"],
                                route_context=_cp_route_ctx,
                                python_executable=python_executable,
                                max_tries=1, localized_files=_dr_localized_files,
                            )
                            _cp_heal_ctx.committee_proposer_model = _dr_cand_resolved
                            _cp_result = _cp_pipeline.run(_cp_heal_ctx)

                            # C15-5D: 還原根目錄中的目標檔案內容，防止多個候選模型執行時互相污染 / 產生競態條件。
                            if request.target_file and original_target_path and os.path.exists(original_target_path):
                                try:
                                    with open(original_target_path, "w", encoding="utf-8") as f:
                                        f.write(original_target_content or "")
                                except Exception:
                                    pass

                            _cp_patch = str(getattr(_cp_result, "pre_verification_final_patch", "") or getattr(_cp_result, "final_patch", "") or "")

                            import hashlib as _hashlib
                            _cp_patch_hash = _hashlib.sha256(_cp_patch.rstrip("\n").encode()).hexdigest() if _cp_patch.strip() else ""

                            _apply_status = "not_attempted"
                            _verifier_result = "fail"
                            _rejection_reason = ""
                            _raw_excerpt = _cp_patch[:300] if _cp_patch else ""

                            # C15-5D: 格式拒絕門——沿用 Nexus SSRP 合約，apply 前先確認格式。
                            # 若委員會模型輸出 unified-diff 而非 SEARCH/REPLACE，直接拒絕不送 apply。
                            _last_patch_decision = next(
                                (d for d in reversed(getattr(_cp_result, "model_decisions", []))
                                 if isinstance(d, dict) and d.get("phase") in ("patch", "semantic_retry_patch")),
                                None
                            )

                            from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol

                            _format_class = "UNKNOWN"
                            if _last_patch_decision:
                                _format_class = _last_patch_decision.get("output_class", "UNKNOWN")

                            # Fallback if unknown or no decision
                            if _format_class == "UNKNOWN":
                                _raw_output = ""
                                if _last_patch_decision:
                                    _raw_output = _last_patch_decision.get("output_excerpt", "")
                                if not _raw_output and _cp_patch:
                                    _raw_output = _cp_patch
                                _format_class = SolidSearchReplaceProtocol.classify_format(_raw_output)

                            _is_unified_diff = (_format_class == "UNIFIED_DIFF")
                            _has_ssrp_marker = (_format_class in ("VALID_SEARCH_REPLACE", "FENCED_SEARCH_REPLACE"))

                            _conversion_status = "none"
                            _conversion_source_hash_before = ""
                            _conversion_candidate_hash = ""
                            _target_file_correct = True
                            _preimage_match_status = "not_applicable"
                            if _last_patch_decision:
                                _conversion_status = _last_patch_decision.get("conversion_status", "none")
                                _conversion_source_hash_before = _last_patch_decision.get("conversion_source_hash_before", "")
                                _conversion_candidate_hash = _last_patch_decision.get("conversion_candidate_hash", "")
                                _target_file_correct = _last_patch_decision.get("target_file_correct", True)
                                _preimage_match_status = _last_patch_decision.get("preimage_match_status", "not_applicable")


                            _should_apply = False
                            if _is_unified_diff and _conversion_status != "unified_diff_to_ssrp_converted":
                                _apply_status = "format_rejected"
                                # If conversion failed, map to specific reject reason from converter
                                _rejection_reason = _conversion_status if _conversion_status != "none" else "unified_diff_malformed"
                            elif not _cp_patch.strip():
                                _apply_status = "empty_patch"
                                _rejection_reason = "patch_empty"
                            elif _is_unified_diff and _conversion_status == "unified_diff_to_ssrp_converted":
                                # Converted successfully: allow it to pass to isolated apply!
                                _should_apply = True
                            elif not _has_ssrp_marker:
                                _apply_status = "format_rejected"
                                _rejection_reason = "wrong_format:no_ssrp_marker"
                            else:
                                _should_apply = True

                            if _should_apply:
                                _cp_apply = run_isolated_workspace_apply(
                                    IsolatedApplyRequest(
                                        task_id=f"{request.task_id}#committee-{_dr_cand_resolved}",
                                        source_root=request.repo_root,
                                        target_file=request.target_file,
                                        unified_diff=_cp_patch,
                                        selected_candidate_hash=_cp_patch_hash,
                                        mutation_allowed=True,
                                        search_text=str(locked_search) if locked_search else "",
                                    )
                                )
                                _apply_status = _cp_apply.patch_apply_status
                                if _cp_apply.patch_apply_status != "applied":
                                    _rejection_reason = f"apply_failed: {_cp_apply.patch_apply_status}"
                                else:
                                    _cp_verify = run_isolated_verifier(
                                        IsolatedVerifierRequest(
                                            task_id=f"{request.task_id}#committee-{_dr_cand_resolved}",
                                            workspace_path=_cp_apply.workspace_path,
                                            verifier_command=tuple(request.route_context.get("verifier_command", []) or []),
                                            verifier_allowed=True,
                                        )
                                    )
                                    _verifier_result = _cp_verify.verifier_status
                                    if _cp_verify.verifier_status != "pass":
                                        _rejection_reason = "verifier_failed"

                            _cand_data = {
                                "candidate_id": _cand_id,
                                "model": _dr_cand_resolved,
                                "candidate_model": _dr_cand_resolved,
                                "raw_output_excerpt": _raw_excerpt,
                                "format_class": _format_class,
                                "conversion_status": _conversion_status,
                                "conversion_source_hash_before": _conversion_source_hash_before,
                                "conversion_candidate_hash": _conversion_candidate_hash,
                                "target_file_correct": _target_file_correct,
                                "preimage_match_status": _preimage_match_status,
                                "apply_status": _apply_status,
                                "candidate_hash": _cp_patch_hash,
                                "verifier_result": _verifier_result,
                                "isolated_verifier_result": _verifier_result,
                                "selected": False,
                                "rejection_reason": _rejection_reason,
                            }

                            if _verifier_result == "pass" and _dr_committee_winner is None:
                                _cand_data["selected"] = True
                                _cand_data["rejection_reason"] = ""
                                _dr_committee_winner = {
                                    "candidate_id": _cand_id,
                                    "model": _dr_cand_resolved,
                                    "patch": _cp_patch,
                                    "result_ctx": _cp_result,
                                    "patch_hash": _cp_patch_hash,
                                }
                            else:
                                if _dr_committee_winner is not None:
                                    _cand_data["rejection_reason"] = "winner_already_selected"
                                elif _rejection_reason == "":
                                    _cand_data["rejection_reason"] = "not_selected"

                            _dr_committee_candidates_list.append(_cand_data)

                    # C15-5D: Autoreason 接委員會候選評審（Phase D）。
                    # 若有多個 verifier-pass 候選，交給既有 AutoreasonService 做信心排名，
                    # 選出最高分候選，而非直接選第一個。
                    _dr_autoreason_winner_model = ""
                    _dr_autoreason_invoked = False
                    _passing_cands = [
                        c for c in _dr_committee_candidates_list
                        if c.get("verifier_result") == "pass"
                    ]
                    if len(_passing_cands) > 1:
                        try:
                            from nexus.engine.autoreason_service import AutoreasonService
                            _ar_candidates = [
                                {
                                    "candidate_id": c["candidate_id"],
                                    "patch": c["raw_output_excerpt"],
                                    "evidence_refs": list(request.evidence_refs or []),
                                    "model": c["model"],
                                    "role": "committee_candidate",
                                }
                                for c in _passing_cands
                            ]
                            _ar_result = AutoreasonService().run(
                                candidates=_ar_candidates,
                                task_desc=request.problem_statement,
                                stop_threshold=2,
                            )
                            _ar_winner_id = _ar_result.get("winner")
                            _dr_autoreason_invoked = True
                            if _ar_winner_id:
                                _winner_cand = next((c for c in _dr_committee_candidates_list if c["candidate_id"] == _ar_winner_id), None)
                                _winner_model = _winner_cand["model"] if _winner_cand else _ar_winner_id
                                _dr_autoreason_winner_model = _winner_model
                                # 用 Autoreason 選出的 winner 重置 _dr_committee_winner
                                for c in _dr_committee_candidates_list:
                                    c["selected"] = (c["candidate_id"] == _ar_winner_id)
                                _dr_committee_winner = next(
                                    (w for w in [_dr_committee_winner] if w and w["model"] == _winner_model),
                                    _dr_committee_winner,  # fallback 保持原值
                                )
                            raw_meta["delegated_retry_autoreason_winner"] = _dr_autoreason_winner_model
                            raw_meta["delegated_retry_autoreason_borda"] = str(_ar_result.get("borda_scores", {}))
                        except Exception as _ar_err:
                            raw_meta["delegated_retry_autoreason_error"] = str(_ar_err)
                    raw_meta["delegated_retry_autoreason_invoked"] = _dr_autoreason_invoked

                    _dr_judge_model = _dr_signal.get("judge_model") or ""
                    raw_meta["delegated_retry_proposer_count_expected"] = len(_dr_candidate_models)
                    raw_meta["delegated_retry_judge_count_expected"] = 1 if _dr_judge_model else 0
                    raw_meta["delegated_retry_candidate_count_actual"] = _dr_committee_candidate_count

                    if _dr_committee_winner is not None:
                        result_ctx = _dr_committee_winner["result_ctx"]
                        raw_meta["delegated_retry_heterogeneous_winner_model"] = _dr_committee_winner["model"]
                        raw_meta["delegated_retry_heterogeneous_candidate_count"] = _dr_committee_candidate_count
                        raw_meta["delegated_retry_committee_path_used"] = True
                        raw_meta["delegated_retry_committee_candidates_json"] = _json.dumps(_dr_committee_candidates_list)
                    else:
                        if _dr_committee_candidate_count > 0:
                            raw_meta["delegated_retry_heterogeneous_winner_model"] = ""
                            raw_meta["delegated_retry_heterogeneous_candidate_count"] = _dr_committee_candidate_count
                            raw_meta["delegated_retry_committee_path_used"] = True
                            raw_meta["delegated_retry_committee_candidates_json"] = _json.dumps(_dr_committee_candidates_list)

                            class DummyResultCtx:
                                final_patch = ""
                                failure_reason = "committee_no_winner"
                                model_decisions = []
                                # C6E: Carry over verifier evidence from first pass
                                _orchestrator_verifier_evidence_passed = bool(raw_meta.get("verifier_failure_evidence_available", False))
                                _orchestrator_verifier_evidence_fields = str(raw_meta.get("verifier_failure_kind", "")) + "|" + str(raw_meta.get("verifier_stdout_excerpt", ""))[:50]
                                _orchestrator_retry_prompt_evidence_hash = str(raw_meta.get("verifier_command_hash", ""))
                                _semantic_retry_telemetry = {}
                            result_ctx = DummyResultCtx()
                        else:
                            heal_ctx = LegacyHealContext(
                                instance_id=request.task_id,
                                repo_dir=_Path(request.repo_root),
                                problem_statement=request.problem_statement,
                                user_prompt=retry_prompt,
                                attempt=1,
                                repro_script=repro_script,
                                skip_reproduction=not bool(repro_script),
                                failure_reason=raw_meta["failure_class"],
                                route_context=route_ctx,
                                python_executable=python_executable,
                                max_tries=1,
                                localized_files=_dr_localized_files,
                            )
                            result_ctx = pipeline.run(heal_ctx)
                    delegated_retry_failure_reason = str(getattr(result_ctx, "failure_reason", "") or "")
                    delegated_retry_final_patch_len = len(getattr(result_ctx, "final_patch", "") or "")
                    retry_model_decisions = list(getattr(result_ctx, "model_decisions", []) or [])
                    # C15-3Q: fix phase key match bug — delegated pipeline uses 'patch' for primary
                    # and 'semantic_retry_patch' for its own orchestrator-level semantic retry.
                    # We want the *latest patch-class decision* (either phase) for status attribution.
                    patch_retry_decisions = [
                        d for d in retry_model_decisions
                        if isinstance(d, dict) and d.get("phase") in ("patch", "semantic_retry_patch")
                    ]
                    if patch_retry_decisions:
                        last_retry = patch_retry_decisions[-1]
                        delegated_retry_output_class = str(last_retry.get("output_class", "") or "")
                        delegated_retry_parser_error_kind = str(last_retry.get("parser_error_kind", "") or "")
                        delegated_retry_status = str(last_retry.get("status", "") or "")
                        delegated_retry_output_excerpt = str(last_retry.get("output_excerpt", "") or "")[:500]
                    pipeline_retry_delegated = True
                    # C15-3T: compute delegated_retry_stage to distinguish failure layers
                    _dr_final_patch = getattr(result_ctx, "final_patch", "") or ""
                    if _dr_final_patch.strip():
                        delegated_retry_stage = "success"
                    elif delegated_retry_status in ("EMPTY_RESPONSE", "MODEL_EMPTY_RESPONSE") or not delegated_retry_status:
                        # first patch synthesis returned empty (semantic retry in delegated pipeline
                        # is not triggered because evaluation_report is absent on attempt=1 heal_ctx)
                        if delegated_retry_provider_called:
                            delegated_retry_stage = "first_patch_empty_response"
                        else:
                            delegated_retry_stage = "provider_not_called"
                    elif delegated_retry_status in ("REPLACEMENT_MARKDOWN_FENCE", "REPLACEMENT_PROSE_CONTAMINATION",
                                                    "NO_BLOCKS_FOUND", "SEARCH_MISMATCH"):
                        delegated_retry_stage = "first_patch_parser_rejected"
                    else:
                        delegated_retry_stage = "first_patch_failed"

                    orch_passed = bool(getattr(result_ctx, "_orchestrator_verifier_evidence_passed", False))
                    orch_fields = str(getattr(result_ctx, "_orchestrator_verifier_evidence_fields", "") or "")
                    orch_hash = str(getattr(result_ctx, "_orchestrator_retry_prompt_evidence_hash", "") or "")
                    raw_meta["orchestrator_verifier_evidence_passed_to_retry"] = orch_passed
                    raw_meta["orchestrator_verifier_evidence_fields"] = orch_fields
                    raw_meta["orchestrator_retry_prompt_evidence_hash"] = orch_hash
                    raw_meta["semantic_retry_verifier_evidence_injected"] = orch_passed
                    raw_meta["semantic_retry_verifier_evidence_fields"] = orch_fields
                    raw_meta["semantic_retry_prompt_evidence_hash"] = orch_hash

                    # C15-3Q: unpack semantic retry diagnostics from delegated run
                    semantic_retry_telemetry = dict(getattr(result_ctx, "_semantic_retry_telemetry", {}) or {})
                    if semantic_retry_telemetry:
                        raw_meta["semantic_retry_count"] = int(semantic_retry_telemetry.get("semantic_retry_count", 0) or 0)
                        raw_meta["same_span_retry"] = bool(semantic_retry_telemetry.get("same_span_retry", False))
                        raw_meta["semantic_retry_invoked"] = (
                            raw_meta["semantic_retry_count"] > 0 or raw_meta["same_span_retry"]
                        )
                    # C15-3Q: always project 15 diagnostic fields (use defaults if no telemetry)
                    raw_meta["semantic_retry_client_reused"] = bool(
                        semantic_retry_telemetry.get("semantic_retry_client_reused", False))
                    raw_meta["semantic_retry_client_class"] = str(
                        semantic_retry_telemetry.get("semantic_retry_client_class", "") or "")
                    raw_meta["semantic_retry_prompt_len"] = int(
                        semantic_retry_telemetry.get("semantic_retry_prompt_len", 0) or 0)
                    raw_meta["semantic_retry_prompt_hash"] = str(
                        semantic_retry_telemetry.get("semantic_retry_prompt_hash", "") or "")
                    raw_meta["semantic_retry_prompt_has_verifier_evidence"] = bool(
                        semantic_retry_telemetry.get("semantic_retry_prompt_has_verifier_evidence", False))
                    raw_meta["semantic_retry_raw_response_len"] = int(
                        semantic_retry_telemetry.get("semantic_retry_raw_response_len", 0) or 0)
                    raw_meta["semantic_retry_raw_response_excerpt"] = str(
                        semantic_retry_telemetry.get("semantic_retry_raw_response_excerpt", "") or "")[:500]
                    raw_meta["semantic_retry_response_is_none"] = bool(
                        semantic_retry_telemetry.get("semantic_retry_response_is_none", False))
                    raw_meta["semantic_retry_response_empty"] = bool(
                        semantic_retry_telemetry.get("semantic_retry_response_empty", False))
                    raw_meta["semantic_retry_response_type"] = str(
                        semantic_retry_telemetry.get("semantic_retry_response_type", "") or "")
                    raw_meta["semantic_retry_output_class"] = str(
                        semantic_retry_telemetry.get("semantic_retry_output_class", "") or "")
                    raw_meta["semantic_retry_parser_error_kind"] = str(
                        semantic_retry_telemetry.get("semantic_retry_parser_error_kind", "") or "")
                    raw_meta["semantic_retry_status"] = str(
                        semantic_retry_telemetry.get("semantic_retry_status", "") or "")
                    raw_meta["semantic_retry_failure_reason"] = str(
                        semantic_retry_telemetry.get("semantic_retry_failure_reason", "") or "")
                    raw_meta["semantic_retry_invocation_source"] = str(
                        semantic_retry_telemetry.get("semantic_retry_invocation_source", "pipeline_delegated_retry") or "pipeline_delegated_retry")
                    # C15-4A / C15-5C: If delegated retry (single model or committee winner) succeeded
                    # and produced a non-empty patch, we must override the primary candidate variables
                    # so that the resolved patch is returned as the final outcome.
                    if delegated_retry_stage == "success" and _dr_final_patch.strip():
                        import hashlib as _hashlib
                        candidate_patch = _dr_final_patch
                        candidate_hash = _hashlib.sha256(candidate_patch.encode("utf-8")).hexdigest()
                        selected_candidate_hash = candidate_hash
                        applied_patch_hash = candidate_hash
                        isolated_apply_status = "applied"
                        isolated_verifier_status = "pass"
                        isolated_verifier_exit_code = 0
                        raw_meta["isolated_apply_status"] = "applied"
                        raw_meta["isolated_verifier_status"] = "pass"
                        raw_meta["solved"] = True
                        raw_meta["verifier_result"] = "pass"
                        raw_meta["patch_lifecycle_state"] = "verifier_passed"
                        raw_meta["failure_class"] = "verifier_passed"
                        if _dr_committee_winner is not None:
                            raw_meta["selected_candidate_model"] = _dr_committee_winner["model"]
                            raw_meta["selected_candidate_hash"] = _dr_committee_winner["patch_hash"]
                            raw_meta["selected_candidate_hash_matches_applied"] = True
                    elif _dr_committee_candidate_count > 0 and _dr_committee_winner is None:
                        raw_meta["solved"] = False
                        raw_meta["verifier_result"] = "fail"
                        isolated_verifier_status = "fail"
                        raw_meta["patch_lifecycle_state"] = "isolation_applied_hash_match_verifier_failed"
                        raw_meta["failure_class"] = "verification_failed"

                    if _dr_committee_candidate_count > 0:
                        delegated_retry_provider_called, delegated_retry_stage, committee_no_winner_projection = _summarize_committee_retry_truth(
                            _dr_committee_candidates_list,
                            _dr_committee_winner,
                        )
                        if committee_no_winner_projection:
                            raw_meta.update(committee_no_winner_projection)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    pipeline_retry_delegated = False

            raw_meta["retry_available"] = retry_available
            raw_meta["retry_not_invoked_reason"] = retry_not_invoked_reason
            raw_meta["pipeline_retry_delegated"] = pipeline_retry_delegated
            raw_meta["delegated_retry_failure_reason"] = delegated_retry_failure_reason
            raw_meta["delegated_retry_final_patch_len"] = delegated_retry_final_patch_len
            raw_meta["delegated_retry_output_class"] = delegated_retry_output_class
            raw_meta["delegated_retry_parser_error_kind"] = delegated_retry_parser_error_kind
            raw_meta["delegated_retry_status"] = delegated_retry_status
            raw_meta["delegated_retry_output_excerpt"] = delegated_retry_output_excerpt
            # C15-3T: stage and provider-call telemetry
            raw_meta["delegated_retry_stage"] = delegated_retry_stage
            raw_meta["delegated_retry_provider_called"] = delegated_retry_provider_called
            # C15-3U: observability fields for delegated retry provider calls
            raw_meta["delegated_retry_provider_prompt_len"] = delegated_retry_provider_prompt_len
            raw_meta["delegated_retry_provider_prompt_hash"] = delegated_retry_provider_prompt_hash
            raw_meta["delegated_retry_provider_model_name"] = delegated_retry_provider_model_name
            raw_meta["delegated_retry_provider_response_is_none"] = delegated_retry_provider_response_is_none
            raw_meta["delegated_retry_provider_response_empty"] = delegated_retry_provider_response_empty
            raw_meta["delegated_retry_provider_response_len"] = delegated_retry_provider_response_len
            raw_meta["delegated_retry_provider_response_type"] = delegated_retry_provider_response_type
            raw_meta["delegated_retry_provider_call_error"] = delegated_retry_provider_call_error

            raw_meta = record_profile_state(raw_meta)

            # P2-F: Store hash_match on route_context for orchestrator fallback
            if isinstance(request.route_context, dict):
                request.route_context["candidate_hash_matches_applied"] = hash_match
            raw_meta = _attach_local_armor_attempt_receipt(
                request,
                raw_meta,
                local_model_called=True,
                provider=provider_name,
                model_name=repair_exec.telemetries.get("patch_synthesis_model_name", ""),
                evidence_refs=request.evidence_refs,
            )

            _inject_ledger_state(raw_meta, provider)
            return LocalModelExecutorResponse(
                invoked=True,
                local_model_called=True,
                candidate_patch=candidate_patch,
                candidate_hash=candidate_hash,
                reasoning_summary="pipeline_result" if pipeline_result_projected else "pipeline_failed_empty",
                raw_model_metadata=raw_meta,
                provider=provider_name,
                model_name=repair_exec.telemetries.get("patch_synthesis_model_name", ""),
                error="",
                timeout=False,
                evidence_refs=request.evidence_refs,
            )

        # 8c. Local Cascade topology — run multiple models in sequence, pick first success
        if execution_topology == "local_cascade":
            signal_snapshot = request.route_context.get("signal_snapshot", {}) if isinstance(request.route_context, dict) else {}
            protocol_mode = signal_snapshot["protocol_mode"]
            provider_name = _provider_name_for_metadata(provider)

            from nexus.services.local_heal.local_cascade_orchestrator import (
                run_local_cascade,
                LocalCascadeRequest,
                DEFAULT_CASCADE_MODELS,
            )

            attempt_id_val = f"attempt-{len(profile_attempts)}" if profile_attempts else "attempt-1"
            execution_profile_val = profile_attempts[-1] if profile_attempts else "LITE"
            cascade_models = tuple(signal_snapshot.get("cascade_models", DEFAULT_CASCADE_MODELS))
            cascade_request = LocalCascadeRequest(
                task_id=request.task_id,
                problem_statement=request.problem_statement,
                cascade_models=cascade_models,
                target_file=target_file,
                evidence_refs=request.evidence_refs,
                provider_name=provider_name,
                attempt_id=attempt_id_val,
                execution_profile=execution_profile_val,
                phase="patch",
            )
            cascade_receipt = run_local_cascade(cascade_request, provider=provider)

            if cascade_receipt.fail_closed:
                return LocalModelExecutorResponse(
                    invoked=True,
                    local_model_called=True,
                    candidate_patch="",
                    candidate_hash=empty_hash,
                    reasoning_summary="cascade_fail_closed",
                    raw_model_metadata={
                        "execution_topology": "local_cascade",
                        "cascade_models": cascade_models,
                        "cascade_stages_run": cascade_receipt.stages_run,
                        "cascade_stages_failed": cascade_receipt.stages_failed,
                        "cascade_failed_at_final_stage": True,
                        "provider": provider_name,
                    },
                    provider=provider_name,
                    model_name=",".join(cascade_receipt.stages_run) if cascade_receipt.stages_run else "",
                    error="all_cascade_models_failed",
                    timeout=False,
                    evidence_refs=request.evidence_refs,
                    cascade_stages_run=cascade_receipt.stages_run,
                )

            attempt_id_val = f"attempt-{len(profile_attempts)}" if profile_attempts else "attempt-1"
            execution_profile_val = profile_attempts[-1] if profile_attempts else "LITE"
            winner_provider_req = LocalModelProviderRequest(
                task_id=request.task_id,
                prompt=request.problem_statement,
                evidence_refs=request.evidence_refs,
                model_name=cascade_receipt.winner_model,
                phase="patch",
                attempt_id=attempt_id_val,
                execution_profile=execution_profile_val,
            )
            winner_provider_resp = provider.generate(winner_provider_req)
            candidate_patch = winner_provider_resp.output_text

            return LocalModelExecutorResponse(
                invoked=True,
                local_model_called=True,
                candidate_patch=candidate_patch,
                candidate_hash=cascade_receipt.winner_candidate_hash,
                reasoning_summary=f"cascade_winner_{cascade_receipt.winner_model}",
                raw_model_metadata={
                    "execution_topology": "local_cascade",
                    "cascade_models": cascade_models,
                    "cascade_stages_run": cascade_receipt.stages_run,
                    "cascade_stages_failed": cascade_receipt.stages_failed,
                    "cascade_winner_model": cascade_receipt.winner_model,
                    "cascade_failed_at_final_stage": False,
                    "provider": provider_name,
                },
                provider=provider_name,
                model_name=cascade_receipt.winner_model,
                error="",
                timeout=False,
                evidence_refs=request.evidence_refs,
                cascade_stages_run=cascade_receipt.stages_run,
            )

        # cloud_with_local_assist:
        # - Live path: explicit CloudAgentAdapter required; FakeCloud blocked.
        # - dry_run / allow_fake_cloud shadow path: legacy FakeCloud fallthrough for contracts.
        if execution_topology == "cloud_with_local_assist":
            from nexus.services.local_heal.hybrid_cloud_assist_runtime import (
                run_hybrid_cloud_assist_stages,
            )

            stage1 = _p3_stage1_local_diagnosis(request)
            route_ctx = request.route_context if isinstance(request.route_context, dict) else {}
            signal_snapshot = (
                route_ctx.get("signal_snapshot")
                if isinstance(route_ctx.get("signal_snapshot"), dict)
                else {}
            )
            local_assist_enabled = bool(
                route_ctx.get(
                    "local_assist_enabled",
                    signal_snapshot.get("local_assist_enabled", True),
                )
            )
            has_adapter = (
                route_ctx.get("cloud_agent_adapter") is not None
                or route_ctx.get("cloud_adapter") is not None
            )
            # Live hybrid path only when adapter is injected or live_admission is
            # explicitly requested. All other cloud_with_local_assist traffic
            # remains the legacy FakeCloud shadow fallthrough (not live evidence).
            if "live_admission" in route_ctx:
                live_admission = bool(route_ctx.get("live_admission"))
            else:
                live_admission = has_adapter
            use_live_hybrid_path = has_adapter or (
                "live_admission" in route_ctx and bool(route_ctx.get("live_admission"))
            )
            if use_live_hybrid_path:
                hybrid = run_hybrid_cloud_assist_stages(
                    task_id=request.task_id,
                    workspace_revision=str(
                        route_ctx.get("workspace_revision")
                        or signal_snapshot.get("workspace_revision")
                        or "unspecified"
                    ),
                    problem_statement=request.problem_statement,
                    target_file=request.target_file,
                    stage1_diagnosis=stage1,
                    route_context=route_ctx,
                    local_assist_enabled=local_assist_enabled,
                    live_admission=live_admission,
                    candidate_applied_hash=str(route_ctx.get("candidate_applied_hash") or ""),
                )
                _cloud_meta = {
                    **hybrid.to_meta(),
                    "cloud_used": bool(hybrid.cloud_payload.get("provider_call_confirmed")),
                    "cloud_candidate_generated": bool(hybrid.candidate_patch.strip()),
                    "local_assist_used": local_assist_enabled,
                    "cloud_provider": hybrid.economics.get("online_provider", ""),
                    "cloud_candidate_patch": hybrid.candidate_patch,
                    "cloud_candidate_hash": (
                        hashlib.sha256(hybrid.candidate_patch.encode("utf-8")).hexdigest()
                        if hybrid.candidate_patch
                        else ""
                    ),
                    "provider_call_confirmed": bool(hybrid.cloud_payload.get("provider_call_confirmed")),
                    "real_cloud_call": bool(hybrid.cloud_payload.get("real_cloud_call")),
                    "p3_stage4_local_retry": local_assist_enabled and not hybrid.hidden_verifier_passed,
                    **stage1,
                }
                if isinstance(request.route_context, dict):
                    request.route_context["_p3_cloud_meta"] = _cloud_meta
                    request.route_context["_hybrid_cloud_assist"] = hybrid.to_meta()

                if hybrid.status.startswith("BLOCKED_") or hybrid.infra_invalid:
                    return LocalModelExecutorResponse(
                        invoked=bool(hybrid.stages.get("stage1_local_diagnosis", {}).get("invoked")),
                        local_model_called=bool(
                            hybrid.stages.get("stage1_local_diagnosis", {}).get("invoked")
                        ),
                        candidate_patch="",
                        candidate_hash="",
                        reasoning_summary=hybrid.status.lower(),
                        raw_model_metadata=_cloud_meta,
                        provider=str(hybrid.economics.get("online_provider") or "none"),
                        model_name=str(hybrid.economics.get("online_model") or ""),
                        error=hybrid.error or hybrid.block_reason or hybrid.status,
                        timeout=hybrid.infra_invalid and hybrid.error == "provider_timeout",
                        evidence_refs=request.evidence_refs,
                    )

                if hybrid.live_evidence_allowed and hybrid.candidate_patch and hybrid.hidden_verifier_passed:
                    return LocalModelExecutorResponse(
                        invoked=True,
                        local_model_called=True,
                        candidate_patch=hybrid.candidate_patch,
                        candidate_hash=str(_cloud_meta.get("cloud_candidate_hash") or ""),
                        reasoning_summary="cloud_with_local_assist_verified",
                        raw_model_metadata=_cloud_meta,
                        provider=str(hybrid.economics.get("online_provider") or ""),
                        model_name=str(hybrid.economics.get("online_model") or ""),
                        error="",
                        timeout=False,
                        evidence_refs=request.evidence_refs,
                    )

                if not local_assist_enabled:
                    return LocalModelExecutorResponse(
                        invoked=bool(hybrid.cloud_payload.get("provider_call_confirmed")),
                        local_model_called=False,
                        candidate_patch=hybrid.candidate_patch,
                        candidate_hash=str(_cloud_meta.get("cloud_candidate_hash") or ""),
                        reasoning_summary="cloud_path_without_local_assist",
                        raw_model_metadata=_cloud_meta,
                        provider=str(hybrid.economics.get("online_provider") or ""),
                        model_name=str(hybrid.economics.get("online_model") or ""),
                        error=hybrid.error,
                        timeout=False,
                        evidence_refs=request.evidence_refs,
                    )
                # FALL THROUGH to single_local_model for stage4 local retry
            else:
                # Legacy shadow: FakeCloud + fallthrough (not live evidence).
                cloud_provider = FakeCloudCandidateProvider()
                cloud_response = cloud_provider.generate(request)
                stage3 = _p3_stage3_cheap_verifier(cloud_response.candidate_patch, request)
                stages = ["stage1_local_diagnosis", "stage2_cloud_candidate", "stage3_local_cheap_verifier"]
                if not stage3.get("stage3_verifier_passed", False):
                    p3_status = "shadow_stage3_verifier_blocked"
                else:
                    p3_status = "shadow_stage3_verifier_passed"
                _cloud_meta = {
                    "execution_topology": "cloud_with_local_assist",
                    "p3_shadow_route": True,
                    "live_evidence_allowed": False,
                    "public_claim_allowed": False,
                    "cloud_used": True,
                    "cloud_candidate_generated": bool(cloud_response.candidate_patch.strip()),
                    "local_assist_used": True,
                    "assist_stages_activated": stages,
                    "p3_route_status": p3_status,
                    "cloud_provider": "fake_cloud",
                    "cloud_candidate_patch": cloud_response.candidate_patch,
                    "cloud_candidate_hash": cloud_response.candidate_hash,
                    "p3_stage4_local_retry": True,
                    **stage1,
                    **stage3,
                }
                if isinstance(request.route_context, dict):
                    request.route_context["_p3_cloud_meta"] = _cloud_meta
                # FALL THROUGH to single_local_model instead of returning

        # 9. Generate Candidate Patch for single_local_model
        signal_snapshot = request.route_context.get("signal_snapshot", {}) if isinstance(request.route_context, dict) else {}
        protocol_mode = signal_snapshot["protocol_mode"]

        # Build failure feedback context for prompt
        failure_context = ""
        if failure_feedback_present and failure_feedback_text:
            failure_context = f"\n\n{failure_feedback_text}"

        if protocol_mode == "anchored_edit":
            explicit_prompt = (
                f"You are generating a replacement code block to solve a coding task.\n"
                f"Problem: {request.problem_statement}{memory_context}{failure_context}\n"
                f"Target File: {target_file}\n"
                f"Target Symbol: {target_symbol}\n"
                f"Source Anchor Hash: {source_anchor_hash[:16] if source_anchor_hash else 'none'}\n"
                f"Locked Search Span that will be replaced:\n"
                f"```\n{locked_search}\n```\n\n"
                f"Output format (required — exactly this, nothing else):\n"
                f"<<<<<<< REPLACE\n"
                f"...\n"
                f">>>>>>> REPLACE\n\n"
                f"WRONG — backtick-wrapped (will be REJECTED):\n"
                f"```\n<<<<<<< REPLACE\n"
                f"...\n"
                f">>>>>>> REPLACE\n```\n\n"
                f"WRONG — explanations before or after the REPLACE block (will be REJECTED):\n"
                f"# Here is the fix\n"
                f"<<<<<<< REPLACE\n"
                f"...\n"
                f">>>>>>> REPLACE\n\n"
                f"Output ONLY code between <<<<<<< and >>>>>>>. No backticks. No explanations. No comments. Code only.\n"
            )
        else:

            # Read surrounding context from the actual file
            source_context = ""
            try:
                from pathlib import Path as _Path
                _fp = _Path(request.repo_root) / request.target_file if request.repo_root else _Path(request.target_file)
                if _fp.exists():
                    _lines = _fp.read_text(encoding="utf-8").splitlines()
                    # Find locked_search start line
                    _search_first = locked_search.strip().splitlines()[0].strip() if locked_search.strip() else ""
                    _anchor_line = 1
                    for _i, _l in enumerate(_lines, 1):
                        if _search_first and _search_first in _l:
                            _anchor_line = _i
                            break
                    # Show ±15 lines around anchor
                    _start = max(0, _anchor_line - 16)
                    _end = min(len(_lines), _anchor_line + 20)
                    numbered = "\n".join(f"{_start+_j+1}: {_lines[_start+_j]}" for _j in range(_end - _start))
                    source_context = f"\nRelevant source lines (with line numbers):\n```python\n{numbered}\n```\n"
            except Exception:
                pass

            context_block = ""
            if locked_search.strip():
                context_block = (
                    f"\nThe code to be changed (locked search span):\n"
                    f"```python\n{locked_search}\n```\n"
                )

            explicit_prompt = (
                f"You are generating a unified diff to fix a bug in {request.target_file}.\n"
                f"Problem: {request.problem_statement}{memory_context}{failure_context}\n"
                f"Target File: {request.target_file}\n"
                f"Target Symbol: {target_symbol}\n"
                f"Source Anchor Hash: {source_anchor_hash[:16] if source_anchor_hash else 'none'}\n"
                f"{context_block}"
                f"{source_context}\n"
                f"IMPORTANT RULES:\n"
                f"1. The diff header MUST use exactly: --- a/{request.target_file}  and  +++ b/{request.target_file}\n"
                f"2. The @@ hunk header MUST use the EXACT line numbers from the source above.\n"
                f"3. Context lines (no +/-) MUST EXACTLY match the source file character-for-character including indentation.\n"
                f"4. Return ONLY the diff wrapped in a ```diff fenced block. No prose, no explanation.\n"
            )

        model_name = signal_snapshot["executor_model"]
        attempt_id_val = f"attempt-{len(profile_attempts)}" if profile_attempts else "attempt-1"
        execution_profile_val = profile_attempts[-1] if profile_attempts else "LITE"
        _opts = signal_snapshot.get("ollama_options")
        if not _opts:
            _opts = {"num_ctx": 8192, "num_predict": 512, "temperature": 0.0}
        prov_req = LocalModelProviderRequest(
            task_id=request.task_id,
            prompt=explicit_prompt,
            evidence_refs=request.evidence_refs,
            model_name=model_name,
            timeout_sec=provider_timeout_sec,
            options=_opts,
            phase="patch",
            attempt_id=attempt_id_val,
            execution_profile=execution_profile_val,
        )

        prov_resp = provider.generate(prov_req)

        candidate_patch = prov_resp.output_text
        patch_meta = {}

        # P1-2: Read-only canonical understanding layer
        from nexus.services.local_heal.output_understanding import understand_output, OutputFormat, enrich_candidate_with_anchor
        _understanding = understand_output(candidate_patch)

        # P2-1: Enrich canonical candidate with anchor fields
        _canonical_candidate = _understanding.candidate
        if _canonical_candidate is not None:
            _canonical_candidate = enrich_candidate_with_anchor(
                _canonical_candidate,
                target_file=request.target_file,
                target_symbol=request.route_context.get("target_symbol", "") if isinstance(request.route_context, dict) else "",
                old_block_hash=source_anchor_hash,
            )

        # P1-4: Project canonical candidate content for supported formats
        _projection_source = "raw_output"
        _supported_projection_formats = {
            OutputFormat.SEARCH_REPLACE.value,
            OutputFormat.FENCED_SEARCH_REPLACE.value,
            OutputFormat.UNIFIED_DIFF.value,
        }
        _patch_input = candidate_patch
        if (
            _canonical_candidate
            and _understanding.success
            and _canonical_candidate.source_format in _supported_projection_formats
            and _canonical_candidate.normalized_patch.strip()
        ):
            _patch_input = _canonical_candidate.normalized_patch
            _projection_source = "canonical_candidate"

        if _patch_input.strip():
            candidate_patch, patch_meta = _normalize_candidate_patch(request, locked_search, _patch_input)
            candidate_hash = hashlib.sha256(candidate_patch.encode("utf-8")).hexdigest() if candidate_patch.strip() else empty_hash
        else:
            candidate_hash = empty_hash

        # P1-2: Inject understanding metadata after _normalize_candidate_patch
        _understanding_meta = {
            "output_understanding_format": _understanding.detected_format,
            "output_understanding_success": _understanding.success,
            "output_understanding_projection_source": _projection_source,
        }
        if _canonical_candidate:
            _understanding_meta["output_understanding_normalization_steps"] = list(_canonical_candidate.normalization_steps)
            _understanding_meta["output_understanding_source_format"] = _canonical_candidate.source_format
            # P2-2: Propagate anchor fields
            _understanding_meta["output_understanding_candidate_target_file"] = _canonical_candidate.target_file
            _understanding_meta["output_understanding_candidate_target_symbol"] = _canonical_candidate.target_symbol
            _understanding_meta["output_understanding_candidate_old_block_hash"] = _canonical_candidate.old_block_hash

        # P1-2: Fail-closed mapping for empty/refusal/malformed via understanding layer
        if not _understanding.success and candidate_hash == empty_hash:
            _understanding_meta["protocol_parse_failed"] = True
            _understanding_meta["error_kind"] = f"OUTPUT_UNDERSTANDING:{_understanding.failure_reason}"
            _understanding_meta["error_message"] = _understanding.failure_reason

        provider_name = _provider_name_for_metadata(provider)

        raw_meta = {
            "output_truncated": prov_resp.output_truncated,
            "error": prov_resp.error,
            "timed_out": prov_resp.timed_out,
            "requested_timeout_sec": prov_resp.requested_timeout_sec,
            "effective_timeout_sec": prov_resp.effective_timeout_sec,
            "elapsed_sec": prov_resp.elapsed_sec,
            # Relay as provider_elapsed_sec for runner phase-timing extraction
            "provider_elapsed_sec": prov_resp.elapsed_sec,
            # Relay Ollama native metrics for latency profiling (default 0 for non-Ollama providers)
            "ollama_total_duration": getattr(prov_resp, "ollama_total_duration", 0),
            "ollama_load_duration": getattr(prov_resp, "ollama_load_duration", 0),
            "ollama_prompt_eval_count": getattr(prov_resp, "ollama_prompt_eval_count", 0),
            "ollama_prompt_eval_duration": getattr(prov_resp, "ollama_prompt_eval_duration", 0),
            "ollama_eval_count": getattr(prov_resp, "ollama_eval_count", 0),
            "ollama_eval_duration": getattr(prov_resp, "ollama_eval_duration", 0),
            "ollama_done_reason": getattr(prov_resp, "ollama_done_reason", ""),
            "ollama_metrics_available": getattr(prov_resp, "ollama_metrics_available", False),
            "protocol_mode": protocol_mode,
            "execution_topology": execution_topology,
            "protocol_normalization": patch_meta,
            "source_anchor_present": source_anchor_present,
            "source_anchor_source": source_anchor_source,
            "source_anchor_hash": source_anchor_hash[:16] if source_anchor_hash else "",
            "source_anchor_missing": not source_anchor_present,
            "localization_missing": (not source_anchor_present and source_anchor_source == "localizer_failed"),
            "target_file": target_file,
            "target_symbol": target_symbol,
            "locked_search_present": bool(locked_search.strip()),
            "failure_feedback_present": failure_feedback_present,
            "final_authority": "NexusVerifier",
            **memory_runtime_meta,
            **_understanding_meta,
        }
        _usage = compute_capability_usage(
            selected_capabilities=selected_caps,
            metadata=raw_meta,
            local_model_called=bool(prov_resp.model_called if hasattr(prov_resp, "model_called") else True),
            route_context=request.route_context if isinstance(request.route_context, dict) else {},
        )
        raw_meta.update(_usage)
        cap_ctx.local_model_metadata = raw_meta
        _inject_ledger_state(raw_meta, provider)
        armor_ok, armor_miss = validate_local_model_armor_metadata(raw_meta)
        raw_meta["armor_receipt_complete"] = armor_ok
        raw_meta["armor_receipt_missing_fields"] = armor_miss
        local_assist_telemetry = build_local_assist_telemetry_from_executor_meta(raw_meta)
        raw_meta["local_assist_telemetry"] = local_assist_telemetry.to_dict()

        # P3-A: Attach route skeleton metadata (shadow-only, no runtime behavior change)
        from nexus.services.local_heal.p3_route_skeleton import compute_p3_route_skeleton, p3_skeleton_to_dict
        _p3_skeleton_request = {
            "task_id": request.task_id,
            "difficulty": request.route_context.get("difficulty", "") if isinstance(request.route_context, dict) else "",
            "route_context": request.route_context if isinstance(request.route_context, dict) else {},
        }
        _p3_skeleton = compute_p3_route_skeleton(_p3_skeleton_request)
        raw_meta.update(p3_skeleton_to_dict(_p3_skeleton))

        # P3-I6: Stage 4 local retry fallback — merge cloud meta into response
        _p3_cloud_meta = (request.route_context or {}).get("_p3_cloud_meta", {})
        if _p3_cloud_meta:
            _meta = _p3_cloud_meta.copy()
            _meta["p3_stage4_local_retry_performed"] = True
            _meta["stage4_local_retry_model"] = prov_resp.model_name or prov_req.model_name or "unknown"
            _meta["stage4_local_retry_candidate_patch"] = candidate_patch or ""
            _meta["stage4_local_retry_candidate_hash"] = candidate_hash or ""
            _meta["stage4_local_retry_success"] = bool(candidate_patch.strip())
            _meta["assist_stages_activated"] = list(_meta.get("assist_stages_activated", []) or []) + [
                "stage4_local_retry"
            ]
            _meta.update(raw_meta)  # merge local model results
            raw_meta = _meta
            p3_status = (
                "shadow_stage4_retry_complete"
                if raw_meta["stage4_local_retry_success"]
                else "shadow_stage4_retry_failed"
            )
            raw_meta["p3_route_status"] = p3_status
            # Fallthrough is local recovery: never promote merged receipt as live hybrid success.
            # real_cloud_call only if the cloud arm actually delivered a non-empty live candidate
            # via a non-fake/non-injected provider.
            _cloud_patch = str(raw_meta.get("cloud_candidate_patch") or "").strip()
            _cloud_provider = str(raw_meta.get("cloud_provider") or "").strip().lower()
            _fake_providers = {"", "fake_cloud", "fake", "injected", "controlled-cloud", "none"}
            _cloud_delivered_live = bool(
                raw_meta.get("real_cloud_call")
                and _cloud_patch
                and _cloud_provider not in _fake_providers
            )
            raw_meta["real_cloud_call"] = _cloud_delivered_live
            raw_meta["live_evidence_allowed"] = False
            raw_meta["public_claim_allowed"] = False
            _final_patch = str(candidate_patch or _cloud_patch or "").strip()
            if not _final_patch or raw_meta.get("error") or not raw_meta.get("stage4_local_retry_success"):
                # Empty/error after fallthrough: strip residual live pretence from cloud meta.
                raw_meta["live_evidence_allowed"] = False
                if not _cloud_delivered_live:
                    raw_meta["real_cloud_call"] = False

        # P3-I7: Stage 5 escalation stub (P3↔P4 boundary)
        if _p3_cloud_meta:
            stage5 = _p3_stage5_escalation_decision(
                cloud_meta=_p3_cloud_meta,
                local_retry_success=raw_meta.get("stage4_local_retry_success", False),
                reason=raw_meta.get("stage3_verifier_reason", ""),
            )
            raw_meta.update(stage5)
            if stage5.get("stage5_escalation_recommended", False):
                raw_meta["p3_route_status"] = "shadow_stage5_escalation_recommended"
                # P4-I4: Try committee invocation when escalation recommended
                _p4_result = _try_invoke_p4_committee(
                    raw_meta=raw_meta,
                    request=request,
                    signal_snapshot=signal_snapshot,
                    candidate_producer=_make_default_committee_producer(
                        provider,
                        signal_snapshot,
                        request,
                        attempt_id=f"attempt-{len(profile_attempts)}" if profile_attempts else "attempt-1",
                        execution_profile=profile_attempts[-1] if profile_attempts else "LITE",
                        phase="proposer",
                    ),
                )
                if _p4_result:
                    raw_meta.update(_p4_result)
            else:
                raw_meta["p3_route_status"] = "shadow_stage5_retry_sufficient"
            raw_meta["assist_stages_activated"] = raw_meta.get("assist_stages_activated", []) + ["stage5_escalation_stub"]
        raw_meta = _attach_local_armor_attempt_receipt(
            request,
            raw_meta,
            local_model_called=prov_resp.model_called,
            provider=provider_name,
            model_name=prov_resp.model_name or prov_req.model_name,
            evidence_refs=request.evidence_refs,
        )

        return LocalModelExecutorResponse(
            invoked=prov_resp.provider_invoked,
            local_model_called=prov_resp.model_called,
            candidate_patch=candidate_patch,
            candidate_hash=candidate_hash,
            reasoning_summary="success" if not prov_resp.error else "failed",
            raw_model_metadata=raw_meta,
            provider=provider_name,
            model_name=prov_resp.model_name or prov_req.model_name,
            error=prov_resp.error,
            timeout=prov_resp.timed_out,
            evidence_refs=request.evidence_refs,
        )


def _inject_diagnosis_guidance(
    enhanced_problem: str,
    diagnosis_result: dict | None,
) -> tuple[str, bool, str]:
    """C6AY: Inject D-phase diagnosis root_cause into candidate generation prompt.

    Returns (updated_problem, guidance_injected, guidance_hash).
    Fail-closed: empty/malformed/None diagnosis does not pollute prompt.
    """
    _diag_root_cause = ""
    if isinstance(diagnosis_result, dict):
        _diag_root_cause = str(diagnosis_result.get("root_cause", "") or "").strip()
    if not _diag_root_cause:
        return enhanced_problem, False, ""
    import hashlib as _hl
    updated = enhanced_problem + (
        f"\n\nCommittee Diagnosis: {_diag_root_cause}"
        f"\nUse this diagnosis to prioritize the most likely faulty logic/location."
    )
    _hash = _hl.sha256(_diag_root_cause.encode("utf-8")).hexdigest()[:16]
    return updated, True, _hash


class FakeCloudCandidateProvider:
    """P3-I4: Fake cloud candidate provider — always produces empty candidate.

    Used when no real cloud endpoint is available. Seams for future real cloud integration.
    """

    def generate(self, request: LocalModelExecutorRequest) -> LocalModelExecutorResponse:
        empty_hash = hashlib.sha256(b"").hexdigest()
        return LocalModelExecutorResponse(
            invoked=False,
            local_model_called=False,
            candidate_patch="",
            candidate_hash=empty_hash,
            reasoning_summary="fake_cloud_no_endpoint",
            raw_model_metadata={},
            provider="fake_cloud",
            model_name="",
            error="",
            timeout=False,
            evidence_refs=request.evidence_refs,
        )


def _p3_stage1_local_diagnosis(request: LocalModelExecutorRequest) -> dict:
    """P3-I3: Deterministic local diagnosis for cloud_with_local_assist topology.

    Extracts error context from request, produces compact prompt (≤500 chars).
    Pure deterministic — no model calls.

    Returns dict with:
      - stage1_diagnosis_performed: bool
      - stage1_diagnosis_summary: str
      - stage1_compact_prompt: str
      - stage1_error_context: str
      - stage1_diagnosis_model: str ("deterministic")
    """
    problem = str(getattr(request, "problem_statement", "") or "")
    evidence = list(getattr(request, "evidence_refs", []) or [])
    target_file = str(getattr(request, "target_file", "") or "")
    route_ctx = request.route_context if isinstance(request.route_context, dict) else {}
    signal = route_ctx.get("signal_snapshot", {}) if isinstance(route_ctx, dict) else {}
    target_symbol = str(signal.get("target_symbol", "") or "")

    # Extract error context from problem statement
    error_context = ""
    if problem:
        # Take first 200 chars as error context
        error_context = problem[:200]

    # Build compact prompt (≤500 chars)
    parts = []
    if target_file:
        parts.append(f"File: {target_file}")
    if target_symbol:
        parts.append(f"Symbol: {target_symbol}")
    if error_context:
        parts.append(f"Context: {error_context}")
    if evidence:
        parts.append(f"Evidence: {', '.join(evidence[:3])}")

    compact_prompt = " | ".join(parts)[:500]

    # Summary
    summary = f"Stage1 diagnosis: target={target_file}, symbol={target_symbol}, evidence_count={len(evidence)}"

    return {
        "stage1_diagnosis_performed": True,
        "stage1_diagnosis_summary": summary,
        "stage1_compact_prompt": compact_prompt,
        "stage1_error_context": error_context,
        "stage1_diagnosis_model": "deterministic",
    }


def _p3_stage3_cheap_verifier(candidate_patch: str, request: LocalModelExecutorRequest) -> dict:
    """P3-I5: Deterministic pre-verifier for cloud candidate patches.

    Checks:
      - candidate_patch non-empty
      - basic structural expectations (diff-like or meaningful content)
      - length >= 10 chars
      - no trivial syntax issues
      - no obviously destructive content (e.g., rm -rf)

    Returns dict with:
      - stage3_verifier_performed: bool
      - stage3_verifier_passed: bool
      - stage3_verifier_reason: str
      - stage3_verifier_model: str ("deterministic")
    """
    patch = str(candidate_patch or "")

    # Check 1: non-empty
    if not patch.strip():
        return {
            "stage3_verifier_performed": True,
            "stage3_verifier_passed": False,
            "stage3_verifier_reason": "empty_patch",
            "stage3_verifier_model": "deterministic",
        }

    # Check 2: minimum length
    if len(patch.strip()) < 10:
        return {
            "stage3_verifier_performed": True,
            "stage3_verifier_passed": False,
            "stage3_verifier_reason": "patch_too_short",
            "stage3_verifier_model": "deterministic",
        }

    # Check 3: destructive content
    destructive_patterns = ["rm -rf", "rm -r /", "mkfs", "dd if=", "> /dev/"]
    lower_patch = patch.lower()
    for pattern in destructive_patterns:
        if pattern in lower_patch:
            return {
                "stage3_verifier_performed": True,
                "stage3_verifier_passed": False,
                "stage3_verifier_reason": f"destructive_content:{pattern}",
                "stage3_verifier_model": "deterministic",
            }

    # Check 4: basic structural check (diff-like or code-like)
    has_diff_markers = any(marker in patch for marker in ["---", "+++", "@@ ", "<<<<<<< ", "def ", "class ", "import "])
    if not has_diff_markers and len(patch.strip()) < 50:
        return {
            "stage3_verifier_performed": True,
            "stage3_verifier_passed": False,
            "stage3_verifier_reason": "no_structural_markers",
            "stage3_verifier_model": "deterministic",
        }

    return {
        "stage3_verifier_performed": True,
        "stage3_verifier_passed": True,
        "stage3_verifier_reason": "basic_checks_passed",
        "stage3_verifier_model": "deterministic",
    }


def _normalize_candidate_patch(
    request: LocalModelExecutorRequest,
    locked_search: str,
    candidate_patch: str,
) -> tuple[str, dict]:
    """Normalize candidate_patch to standard unified diff using SolidSearchReplaceProtocol.

    Returns:
        (normalized_patch, metadata) where metadata contains protocol_parse_failed if error.
    """
    # Defensive: ensure strings, not bytes
    locked_search = locked_search if isinstance(locked_search, str) else str(locked_search) if locked_search else ""
    candidate_patch = candidate_patch if isinstance(candidate_patch, str) else str(candidate_patch) if candidate_patch else ""

    if not candidate_patch.strip():
        return "", {"protocol_parse_failed": True, "error": "empty_patch"}

    candidate_patch, outer_unwrap_meta = _unwrap_outer_markdown_fence(candidate_patch)
    candidate_patch, replace_unwrap_meta = _unwrap_markdown_fence_inside_replace_block(candidate_patch)
    unwrap_meta = {
        "normalized": bool(
            outer_unwrap_meta.get("normalized", False)
            or replace_unwrap_meta.get("normalized", False)
        ),
        **outer_unwrap_meta,
        **replace_unwrap_meta,
    }

    # 1. Already standard unified diff — pass through
    if "--- a/" in candidate_patch and "+++ b/" in candidate_patch and "<<<<<<< REPLACE" not in candidate_patch:
        return candidate_patch, {
            "protocol_used": "passthrough",
            "normalized": bool(unwrap_meta.get("normalized", False)),
            **unwrap_meta,
        }

    # 2. Use SolidSearchReplaceProtocol to parse REPLACE block
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol, PatchError

    protocol = SolidSearchReplaceProtocol()
    anchor_text = locked_search if locked_search.strip() else None

    result = protocol.parse(candidate_patch, anchor_text=anchor_text, protocol_mode="anchored_edit")

    # 3. Handle parse error — fail closed
    if isinstance(result, PatchError):
        return "", {
            "protocol_parse_failed": True,
            "error_kind": result.kind.name if hasattr(result.kind, "name") else str(result.kind),
            "error_message": result.message,
            **unwrap_meta,
        }

    # 4. Got PatchIntent(s) — extract replacement from first intent
    if not result:
        return "", {"protocol_parse_failed": True, "error": "no_intents", **unwrap_meta}

    intent = result[0]
    replacement = intent.replace

    if not replacement.strip():
        return "", {"protocol_parse_failed": True, "error": "empty_replacement", **unwrap_meta}

    # 5. Generate unified diff from locked_search → replacement
    normalized = _build_unified_diff_from_search_and_replacement(
        request,
        request.target_file,
        locked_search,
        replacement,
    )
    if not normalized.strip():
        # empty_after_cleanup: replacement identical to locked_search → no diff
        return "", {
            "protocol_parse_failed": True,
            "error_kind": "EMPTY_AFTER_CLEANUP",
            "error_message": "Replacement identical to search anchor — no diff produced.",
            **unwrap_meta,
        }
    return normalized, {
        "protocol_used": "solid_search_replace",
        "normalized": True,
        **unwrap_meta,
    }


def _p3_stage5_escalation_decision(
    cloud_meta: dict | None,
    local_retry_success: bool,
    reason: str = "",
) -> dict:
    """P3-I7: Deterministic escalation decision stub (P3↔P4 boundary).

    Recommends escalation when local retry failed or verifier blocked + no retry patch.
    Does NOT call committee (P4 responsibility).

    Returns dict:
      - stage5_escalation_performed: bool
      - stage5_escalation_recommended: bool
      - stage5_escalation_reason: str
      - stage5_escalation_target: str ("committee" — stub, not called)
    """
    if not cloud_meta:
        return {
            "stage5_escalation_performed": True,
            "stage5_escalation_recommended": False,
            "stage5_escalation_reason": "no_cloud_pipeline_executed",
            "stage5_escalation_target": "committee",
        }

    verifier_blocked = not cloud_meta.get("stage3_verifier_passed", False)
    reason_str = str(reason or cloud_meta.get("stage3_verifier_reason", "") or "")

    if local_retry_success:
        return {
            "stage5_escalation_performed": True,
            "stage5_escalation_recommended": False,
            "stage5_escalation_reason": "local_retry_sufficient",
            "stage5_escalation_target": "committee",
        }

    # Retry failed → escalate regardless of verifier state
    prefix = "verifier_blocked_and_retry_failed" if verifier_blocked else "retry_failed"
    escalation_reason = f"{prefix}:{reason_str}" if reason_str else prefix
    return {
        "stage5_escalation_performed": True,
        "stage5_escalation_recommended": True,
        "stage5_escalation_reason": escalation_reason,
        "stage5_escalation_target": "committee",
    }


def _make_default_committee_producer(
    provider: LocalModelProvider | None,
    signal_snapshot: dict,
    request: LocalModelExecutorRequest,
    attempt_id: str = "attempt-1",
    execution_profile: str = "LITE",
    phase: str = "patch",
) -> Any | None:
    """Create a default CommitteeCandidateProducer from the existing provider.

    Returns None if provider is None (causes evaluate_and_execute to fail-closed).
    The producer wraps provider.generate() output as a raw committee candidate dict.
    """
    if provider is None:
        return None

    def _producer(p4_request: Any) -> list[dict[str, Any]]:
        model_name = signal_snapshot.get("executor_model", "") or "default"
        prov_req = LocalModelProviderRequest(
            task_id=request.task_id,
            prompt=request.problem_statement,
            evidence_refs=request.evidence_refs,
            model_name=model_name,
            phase=phase,
            attempt_id=attempt_id,
            execution_profile=execution_profile,
        )
        try:
            prov_resp = provider.generate(prov_req)
        except Exception:
            return []

        output = (prov_resp.output_text or "").strip()
        if not output:
            return []

        return [{
            "candidate_patch": output,
            "format": "UNIFIED_DIFF",
            "model": prov_resp.model_name or model_name,
            "candidate_id": f"{request.task_id}#default-committee",
        }]

    return _producer


def _try_invoke_p4_committee(
    raw_meta: dict,
    request: LocalModelExecutorRequest,
    signal_snapshot: dict,
    candidate_producer: Any | None = None,
) -> dict | None:
    """P4-I4: Attempt P4 committee invocation from P3 hard-case path.

    Returns None if gate blocks. Returns receipt fragment if invoked.
    """
    from nexus.services.local_heal.committee_routed_tool import (
        CommitteeCandidateProducer,
        CommitteeRoutedToolRequest,
        evaluate_and_execute,
    )

    # Extract proposer_specs and judge_model from signal_snapshot
    proposer_specs = signal_snapshot.get("proposer_specs", []) or []
    judge_model = signal_snapshot.get("judge_model", "") or ""

    p4_request = CommitteeRoutedToolRequest(
        task_id=request.task_id,
        repo_root=request.repo_root,
        target_file=request.target_file,
        target_symbol=signal_snapshot.get("target_symbol", ""),
        difficulty=signal_snapshot.get("difficulty", "") or raw_meta.get("task_difficulty", ""),
        execution_topology=signal_snapshot.get("execution_topology", ""),
        p3_route_status=raw_meta.get("p3_route_status", ""),
        hard_case_escalation_reason=raw_meta.get("stage5_escalation_reason", ""),
        evidence_refs=request.evidence_refs,
        proposer_specs=proposer_specs,
        judge_model=judge_model,
        mutation_allowed=signal_snapshot.get("mutation_allowed", True),
        verifier_allowed=signal_snapshot.get("verifier_allowed", True),
    )

    result = evaluate_and_execute(p4_request, candidate_producer=candidate_producer)
    raw_meta["p4_committee_gate_evaluated"] = True
    raw_meta["p4_committee_invocation_allowed"] = result.invocation_allowed

    if not result.invocation_allowed:
        raw_meta["p4_committee_blocked_reason"] = result.blocked_reason
        raw_meta["assist_stages_activated"] = raw_meta.get("assist_stages_activated", []) + ["committee_gate_blocked"]
        return None

    raw_meta["p4_committee_invoked"] = True
    raw_meta["p4_committee_invocation_source"] = "p3_hard_case_escalation"
    raw_meta["assist_stages_activated"] = raw_meta.get("assist_stages_activated", []) + ["committee_routed_tool"]
    raw_meta["p4_route_status"] = "p4_committee_invoked"

    # Merge receipt fragment
    raw_meta.update(result.receipt_fragment)
    return raw_meta
