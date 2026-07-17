"""cloud_with_local_assist runtime stages + economics receipt fields.

Does not introduce a new topology string or planner. Consumes planner-owned
signal_snapshot and an explicit CloudAgentAdapter dependency.

Live evidence rules:
- FakeCloud / shadow / fixture transport cannot claim live hybrid success.
- Missing candidate identity or hash mismatch → BLOCK.
- Provider timeout → infra-invalid classification.
- Missing provider tokens → UNAVAILABLE (never estimated-as-measured).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Mapping

from nexus.services.cloud_agent_contract import (
    CloudAgentAdapter,
    CloudAgentRequest,
    InjectedCloudAgentAdapter,
    invoke_cloud_agent,
)

HYBRID_ECONOMICS_SCHEMA = "nexus.hybrid_cloud_assist.economics.v1"
DEFAULT_CLOUD_TIMEOUT_SEC = 60.0
MIN_CLOUD_TIMEOUT_SEC = 30.0
MAX_CLOUD_TIMEOUT_SEC = 90.0

UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class HybridStageResult:
    status: str
    live_evidence_allowed: bool
    block_reason: str
    stages: dict[str, Any]
    economics: dict[str, Any]
    cloud_payload: dict[str, Any]
    candidate_patch: str
    candidate_identity: str
    selected_hash_matches_applied: bool
    semantic_correctness_passed: bool
    hidden_verifier_passed: bool
    error: str = ""
    infra_invalid: bool = False

    def to_meta(self) -> dict[str, Any]:
        meta = {
            "execution_topology": "cloud_with_local_assist",
            "hybrid_stage_status": self.status,
            "live_evidence_allowed": self.live_evidence_allowed,
            "live_evidence_block_reason": self.block_reason,
            "p3_shadow_route": not self.live_evidence_allowed,
            "hybrid_stages": self.stages,
            "hybrid_economics": self.economics,
            "cloud_payload": self.cloud_payload,
            "candidate_identity": self.candidate_identity,
            "selected_hash_matches_applied": self.selected_hash_matches_applied,
            "semantic_correctness_passed": self.semantic_correctness_passed,
            "hidden_verifier_passed": self.hidden_verifier_passed,
            "infra_invalid": self.infra_invalid,
            "error": self.error,
            **self.economics,
        }
        # RC-2: additive receipt_base (parent=run_anchor; legacy fields retained)
        try:
            from nexus.evidence.receipt_base import stamp_r2_hybrid_meta

            return stamp_r2_hybrid_meta(meta)
        except Exception as exc:  # noqa: BLE001
            meta["receipt_base_error"] = str(exc)[:200]
            meta["public_claim_allowed"] = False
            return meta


def clamp_timeout_sec(value: float | int | None) -> float:
    try:
        timeout = float(value if value is not None else DEFAULT_CLOUD_TIMEOUT_SEC)
    except (TypeError, ValueError):
        timeout = DEFAULT_CLOUD_TIMEOUT_SEC
    return max(MIN_CLOUD_TIMEOUT_SEC, min(MAX_CLOUD_TIMEOUT_SEC, timeout))


def _token_field(usage: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in usage and usage[key] is not None:
            try:
                return int(usage[key])
            except (TypeError, ValueError):
                return UNAVAILABLE
    return UNAVAILABLE


def build_hybrid_economics(
    *,
    online_provider: str,
    online_model: str,
    online_call_count: int,
    usage: Mapping[str, Any] | None,
    local_call_count: int,
    local_tokens: Any,
    prompt_chars_before: int,
    prompt_chars_after: int,
    cloud_retry_avoided: Any,
    assist_stages_activated: list[str],
    quota_before: Any,
    quota_after: Any,
    wall_time_sec: float,
    semantic_correctness_passed: bool,
    selected_hash_matches_applied: bool,
    hidden_verifier_passed: bool,
) -> dict[str, Any]:
    usage = usage or {}
    # cloud_retry_avoided must be measured (int) or UNAVAILABLE — never invented.
    if cloud_retry_avoided is None or cloud_retry_avoided is UNAVAILABLE:
        retry_field: Any = UNAVAILABLE
    else:
        try:
            retry_field = int(cloud_retry_avoided)
        except (TypeError, ValueError):
            retry_field = UNAVAILABLE
    return {
        "schema": HYBRID_ECONOMICS_SCHEMA,
        "online_provider": online_provider or "",
        "online_model": online_model or "",
        "online_call_count": int(online_call_count),
        "online_input_tokens": _token_field(usage, "input_tokens", "prompt_tokens", "input"),
        "online_output_tokens": _token_field(usage, "output_tokens", "completion_tokens", "output"),
        "local_call_count": int(local_call_count),
        "local_tokens": local_tokens if local_tokens is not None else UNAVAILABLE,
        "prompt_chars_before": int(prompt_chars_before),
        "prompt_chars_after": int(prompt_chars_after),
        "compact_chars_delta": int(prompt_chars_before) - int(prompt_chars_after),
        "cloud_retry_avoided": retry_field,
        "assist_stages_activated": list(assist_stages_activated),
        "quota_before": quota_before if quota_before is not None else UNAVAILABLE,
        "quota_after": quota_after if quota_after is not None else UNAVAILABLE,
        "wall_time_sec": float(wall_time_sec),
        "semantic_correctness_passed": bool(semantic_correctness_passed),
        "selected_hash_matches_applied": bool(selected_hash_matches_applied),
        "hidden_verifier_passed": bool(hidden_verifier_passed),
        "public_claim_allowed": False,
        "monetary_estimate_allowed": False,
    }


def resolve_cloud_adapter(route_context: Mapping[str, Any] | None) -> tuple[CloudAgentAdapter | None, str]:
    """Resolve explicit CloudAgentAdapter from route_context.

    Returns (adapter, source_label). Fake is never auto-promoted to live.
    """
    ctx = dict(route_context or {})
    adapter = ctx.get("cloud_agent_adapter") or ctx.get("cloud_adapter")
    if adapter is not None:
        if not isinstance(adapter, CloudAgentAdapter):
            return None, "invalid_cloud_adapter_type"
        return adapter, "route_context_injection"
    if bool(ctx.get("allow_fake_cloud")):
        # Explicit test-only shadow path — caller must not claim live.
        return None, "allow_fake_cloud"
    return None, "cloud_adapter_missing"


def is_fake_or_shadow_adapter(adapter: CloudAgentAdapter | None, *, allow_fake: bool) -> bool:
    if adapter is None:
        return True
    if allow_fake:
        return True
    provider = str(getattr(adapter, "provider", "") or "").lower()
    if provider in {"fake", "fake_cloud", "fixture", "shadow", "injected", "controlled-cloud"}:
        return True
    # Any InjectedCloudAgentAdapter is fixture transport — never live-admissible,
    # even if a subclass flips is_real_provider for unit convenience.
    if isinstance(adapter, InjectedCloudAgentAdapter):
        return True
    # Registered print CLI / subprocess adapters mark is_real_provider=True.
    return not bool(getattr(adapter, "is_real_provider", False))

def run_hybrid_cloud_assist_stages(
    *,
    task_id: str,
    workspace_revision: str,
    problem_statement: str,
    target_file: str,
    stage1_diagnosis: Mapping[str, Any],
    route_context: Mapping[str, Any] | None,
    local_assist_enabled: bool = True,
    live_admission: bool = True,
    candidate_applied_hash: str = "",
) -> HybridStageResult:
    """Execute Local diagnosis → Online candidate → Local cheap verifier.

    local_assist_enabled=False is the single OFF switch: skip local stages after
    diagnosis compaction metadata only, still require cloud adapter for online path.
    """
    started = time.monotonic()
    ctx = dict(route_context or {})
    signal = ctx.get("signal_snapshot") if isinstance(ctx.get("signal_snapshot"), Mapping) else {}
    online_provider = str(ctx.get("online_provider") or signal.get("online_provider") or signal.get("provider") or "")
    online_model = str(ctx.get("online_model") or signal.get("online_model") or signal.get("executor_model") or "")
    timeout_sec = clamp_timeout_sec(ctx.get("cloud_timeout_sec") or signal.get("cloud_timeout_sec"))
    allow_fake = bool(ctx.get("allow_fake_cloud")) and not live_admission

    compact_prompt = str(stage1_diagnosis.get("stage1_compact_prompt") or "")
    prompt_before = max(len(problem_statement), len(compact_prompt))
    prompt_after = len(compact_prompt) if compact_prompt else len(problem_statement)
    stages_activated: list[str] = ["stage1_local_diagnosis"]
    stages: dict[str, Any] = {
        "stage1_local_diagnosis": {
            "invoked": bool(stage1_diagnosis.get("stage1_diagnosis_performed")),
            "physical": True,
            "summary": stage1_diagnosis.get("stage1_diagnosis_summary", ""),
            "compact_prompt": compact_prompt,
        }
    }

    adapter, adapter_source = resolve_cloud_adapter(ctx)
    if adapter is None and allow_fake:
        # Shadow-only synthetic path — never live-admissible (no FakeCloud import cycle).
        stages_activated.append("stage2_cloud_candidate_fake")
        stages["stage2_cloud_candidate"] = {
            "invoked": False,
            "provider": "fake_cloud",
            "provider_call_confirmed": False,
            "real_cloud_call": False,
            "adapter_source": adapter_source,
            "blocked": True,
            "block_reason": "fake_cloud_provider",
        }
        economics = build_hybrid_economics(
            online_provider="fake_cloud",
            online_model="",
            online_call_count=0,
            usage={},
            local_call_count=1 if local_assist_enabled else 0,
            local_tokens=UNAVAILABLE,
            prompt_chars_before=prompt_before,
            prompt_chars_after=prompt_after,
            cloud_retry_avoided=UNAVAILABLE,
            assist_stages_activated=stages_activated,
            quota_before=ctx.get("quota_before"),
            quota_after=ctx.get("quota_after"),
            wall_time_sec=time.monotonic() - started,
            semantic_correctness_passed=False,
            selected_hash_matches_applied=False,
            hidden_verifier_passed=False,
        )
        return HybridStageResult(
            status="BLOCKED_FAKE_CLOUD",
            live_evidence_allowed=False,
            block_reason="fake_cloud_provider",
            stages=stages,
            economics=economics,
            cloud_payload={"provider": "fake_cloud", "error": "fake_cloud_provider"},
            candidate_patch="",
            candidate_identity="",
            selected_hash_matches_applied=False,
            semantic_correctness_passed=False,
            hidden_verifier_passed=False,
            error="fake_cloud_provider",
        )

    if adapter is None:
        economics = build_hybrid_economics(
            online_provider=online_provider,
            online_model=online_model,
            online_call_count=0,
            usage={},
            local_call_count=1 if local_assist_enabled else 0,
            local_tokens=UNAVAILABLE,
            prompt_chars_before=prompt_before,
            prompt_chars_after=prompt_after,
            cloud_retry_avoided=UNAVAILABLE,
            assist_stages_activated=stages_activated,
            quota_before=ctx.get("quota_before"),
            quota_after=ctx.get("quota_after"),
            wall_time_sec=time.monotonic() - started,
            semantic_correctness_passed=False,
            selected_hash_matches_applied=False,
            hidden_verifier_passed=False,
        )
        return HybridStageResult(
            status="BLOCKED_CLOUD_ADAPTER_MISSING",
            live_evidence_allowed=False,
            block_reason="cloud_adapter_missing",
            stages=stages,
            economics=economics,
            cloud_payload={},
            candidate_patch="",
            candidate_identity="",
            selected_hash_matches_applied=False,
            semantic_correctness_passed=False,
            hidden_verifier_passed=False,
            error="cloud_adapter_missing",
        )

    if is_fake_or_shadow_adapter(adapter, allow_fake=allow_fake) and live_admission:
        economics = build_hybrid_economics(
            online_provider=str(getattr(adapter, "provider", "")),
            online_model=str(getattr(adapter, "model", "") or online_model),
            online_call_count=0,
            usage={},
            local_call_count=1 if local_assist_enabled else 0,
            local_tokens=UNAVAILABLE,
            prompt_chars_before=prompt_before,
            prompt_chars_after=prompt_after,
            cloud_retry_avoided=UNAVAILABLE,
            assist_stages_activated=stages_activated + ["stage2_blocked_non_live"],
            quota_before=ctx.get("quota_before"),
            quota_after=ctx.get("quota_after"),
            wall_time_sec=time.monotonic() - started,
            semantic_correctness_passed=False,
            selected_hash_matches_applied=False,
            hidden_verifier_passed=False,
        )
        return HybridStageResult(
            status="BLOCKED_NON_LIVE_PROVIDER",
            live_evidence_allowed=False,
            block_reason="fake_or_shadow_provider",
            stages={
                **stages,
                "stage2_cloud_candidate": {
                    "invoked": False,
                    "blocked": True,
                    "block_reason": "fake_or_shadow_provider",
                    "provider": getattr(adapter, "provider", ""),
                },
            },
            economics=economics,
            cloud_payload={},
            candidate_patch="",
            candidate_identity="",
            selected_hash_matches_applied=False,
            semantic_correctness_passed=False,
            hidden_verifier_passed=False,
            error="fake_or_shadow_provider",
        )

    # Apply timeout bound on subprocess adapters when present.
    if hasattr(adapter, "timeout_sec"):
        try:
            adapter.timeout_sec = timeout_sec  # type: ignore[attr-defined]
        except Exception:
            pass

    if not online_provider:
        online_provider = str(getattr(adapter, "provider", "") or "provider-neutral")
    if not online_model:
        online_model = str(getattr(adapter, "model", "") or "unspecified")

    cloud_request = CloudAgentRequest(
        task_id=task_id,
        workspace_revision=workspace_revision or "workspace-revision-missing",
        bounded_context=compact_prompt or problem_statement[:500],
        local_diagnosis=str(stage1_diagnosis.get("stage1_diagnosis_summary") or "local_diagnosis"),
        semantic_assertions=tuple(ctx.get("semantic_assertions") or ()),
        target_files=(target_file or "target.py",),
        allowed_mutation_scope=tuple(ctx.get("allowed_mutation_scope") or (target_file or "target.py",)),
        provider=online_provider,
        model=online_model,
    )

    stages_activated.append("stage2_cloud_candidate")
    cloud = invoke_cloud_agent(adapter, cloud_request)
    stages["stage2_cloud_candidate"] = {
        "invoked": bool(cloud.get("provider_call_confirmed")),
        "provider_call_confirmed": bool(cloud.get("provider_call_confirmed")),
        "real_cloud_call": bool(cloud.get("real_cloud_call")),
        "provider": cloud.get("provider"),
        "model": cloud.get("model"),
        "response_identity": cloud.get("response_identity"),
        "error": cloud.get("error", ""),
        "adapter_source": adapter_source,
        "timeout_sec": timeout_sec,
    }

    error = str(cloud.get("error") or "")
    if error == "provider_timeout":
        economics = build_hybrid_economics(
            online_provider=str(cloud.get("provider") or online_provider),
            online_model=str(cloud.get("model") or online_model),
            online_call_count=1 if cloud.get("provider_call_confirmed") else 0,
            usage=cloud.get("usage") if isinstance(cloud.get("usage"), Mapping) else {},
            local_call_count=1 if local_assist_enabled else 0,
            local_tokens=UNAVAILABLE,
            prompt_chars_before=prompt_before,
            prompt_chars_after=prompt_after,
            cloud_retry_avoided=UNAVAILABLE,
            assist_stages_activated=stages_activated,
            quota_before=ctx.get("quota_before"),
            quota_after=ctx.get("quota_after"),
            wall_time_sec=time.monotonic() - started,
            semantic_correctness_passed=False,
            selected_hash_matches_applied=False,
            hidden_verifier_passed=False,
        )
        return HybridStageResult(
            status="INFRA_INVALID_TIMEOUT",
            live_evidence_allowed=False,
            block_reason="provider_timeout",
            stages=stages,
            economics=economics,
            cloud_payload=cloud,
            candidate_patch="",
            candidate_identity="",
            selected_hash_matches_applied=False,
            semantic_correctness_passed=False,
            hidden_verifier_passed=False,
            error="provider_timeout",
            infra_invalid=True,
        )

    candidate_patch = str(cloud.get("candidate_payload") or "")
    candidate_identity = str(cloud.get("response_identity") or "")
    if candidate_patch and not candidate_identity:
        economics = build_hybrid_economics(
            online_provider=str(cloud.get("provider") or online_provider),
            online_model=str(cloud.get("model") or online_model),
            online_call_count=1,
            usage=cloud.get("usage") if isinstance(cloud.get("usage"), Mapping) else {},
            local_call_count=1 if local_assist_enabled else 0,
            local_tokens=UNAVAILABLE,
            prompt_chars_before=prompt_before,
            prompt_chars_after=prompt_after,
            cloud_retry_avoided=UNAVAILABLE,
            assist_stages_activated=stages_activated,
            quota_before=ctx.get("quota_before"),
            quota_after=ctx.get("quota_after"),
            wall_time_sec=time.monotonic() - started,
            semantic_correctness_passed=False,
            selected_hash_matches_applied=False,
            hidden_verifier_passed=False,
        )
        return HybridStageResult(
            status="BLOCKED_CANDIDATE_IDENTITY_MISSING",
            live_evidence_allowed=False,
            block_reason="candidate_identity_missing",
            stages=stages,
            economics=economics,
            cloud_payload=cloud,
            candidate_patch="",
            candidate_identity="",
            selected_hash_matches_applied=False,
            semantic_correctness_passed=False,
            hidden_verifier_passed=False,
            error="candidate_identity_missing",
        )

    # cloud_retry_avoided is only measurable from paired ON/OFF online_call_count
    # deltas (harness). Single-run stage never invents a retry-avoidance win.
    cloud_retry_avoided: Any = UNAVAILABLE
    if ctx.get("measured_cloud_retry_avoided") is not None:
        try:
            cloud_retry_avoided = int(ctx["measured_cloud_retry_avoided"])
        except (TypeError, ValueError):
            cloud_retry_avoided = UNAVAILABLE

    hidden_verifier_passed = False
    # Cheap verifier is structural only — never promotes semantic_correctness_passed.
    semantic_ok = bool(ctx.get("semantic_correctness_passed") is True)
    if local_assist_enabled and candidate_patch:
        stages_activated.append("stage3_local_cheap_verifier")
        destructive = any(token in candidate_patch for token in ("rm -rf", "DROP TABLE", "os.system("))
        structural_ok = (not destructive) and len(candidate_patch.strip()) >= 10
        hidden_verifier_passed = structural_ok
        stages["stage3_local_cheap_verifier"] = {
            "invoked": True,
            "physical": True,
            "passed": hidden_verifier_passed,
            "verifier_kind": "structural_cheap",
            "reason": "" if hidden_verifier_passed else "cheap_verifier_failed",
            "semantic_correctness_claimed": False,
        }
    elif not local_assist_enabled:
        stages["stage3_local_cheap_verifier"] = {
            "invoked": False,
            "skipped": True,
            "reason": "local_assist_stages_disabled",
        }
    else:
        stages["stage3_local_cheap_verifier"] = {
            "invoked": False,
            "skipped": True,
            "reason": "no_candidate_payload",
        }

    selected_hash = hashlib.sha256(candidate_patch.encode("utf-8")).hexdigest() if candidate_patch else ""
    applied = str(candidate_applied_hash or selected_hash)
    hash_match = bool(selected_hash) and selected_hash == applied
    if candidate_patch and candidate_applied_hash and not hash_match:
        economics = build_hybrid_economics(
            online_provider=str(cloud.get("provider") or online_provider),
            online_model=str(cloud.get("model") or online_model),
            online_call_count=1,
            usage=cloud.get("usage") if isinstance(cloud.get("usage"), Mapping) else {},
            local_call_count=1 + (1 if local_assist_enabled else 0),
            local_tokens=UNAVAILABLE,
            prompt_chars_before=prompt_before,
            prompt_chars_after=prompt_after,
            cloud_retry_avoided=cloud_retry_avoided,
            assist_stages_activated=stages_activated,
            quota_before=ctx.get("quota_before"),
            quota_after=ctx.get("quota_after"),
            wall_time_sec=time.monotonic() - started,
            semantic_correctness_passed=False,
            selected_hash_matches_applied=False,
            hidden_verifier_passed=hidden_verifier_passed,
        )
        return HybridStageResult(
            status="BLOCKED_HASH_MISMATCH",
            live_evidence_allowed=False,
            block_reason="selected_hash_mismatch_applied",
            stages=stages,
            economics=economics,
            cloud_payload=cloud,
            candidate_patch=candidate_patch,
            candidate_identity=candidate_identity,
            selected_hash_matches_applied=False,
            semantic_correctness_passed=False,
            hidden_verifier_passed=hidden_verifier_passed,
            error="selected_hash_mismatch_applied",
        )

    # Live evidence requires real provider, confirmed call, non-empty candidate + identity.
    # Empty candidate must never be live_evidence_allowed (even if provider_call_confirmed).
    has_live_candidate = bool(str(candidate_patch or "").strip()) and bool(str(candidate_identity or "").strip())
    live_ok = (
        bool(cloud.get("real_cloud_call"))
        and bool(cloud.get("provider_call_confirmed"))
        and not error
        and has_live_candidate
        and not is_fake_or_shadow_adapter(adapter, allow_fake=False)
        and live_admission
    )
    if bool(cloud.get("provider_call_confirmed")) and not has_live_candidate and not error:
        error = "candidate_empty_or_identity_missing"
    status = "CLOUD_CANDIDATE_VERIFIED" if live_ok and hidden_verifier_passed else (
        "CLOUD_CANDIDATE_DELIVERED" if live_ok else "CLOUD_PATH_INCOMPLETE"
    )
    if not live_ok and not error:
        error = str(cloud.get("error") or "cloud_path_incomplete")

    economics = build_hybrid_economics(
        online_provider=str(cloud.get("provider") or online_provider),
        online_model=str(cloud.get("model") or online_model),
        online_call_count=1 if cloud.get("provider_call_confirmed") else 0,
        usage=cloud.get("usage") if isinstance(cloud.get("usage"), Mapping) else {},
        local_call_count=(1 if stage1_diagnosis.get("stage1_diagnosis_performed") else 0)
        + (1 if local_assist_enabled and "stage3_local_cheap_verifier" in stages_activated else 0),
        local_tokens=UNAVAILABLE,
        prompt_chars_before=prompt_before,
        prompt_chars_after=prompt_after,
        cloud_retry_avoided=cloud_retry_avoided,
        assist_stages_activated=stages_activated,
        quota_before=ctx.get("quota_before"),
        quota_after=ctx.get("quota_after"),
        wall_time_sec=time.monotonic() - started,
        semantic_correctness_passed=semantic_ok,
        selected_hash_matches_applied=hash_match if candidate_patch else False,
        hidden_verifier_passed=hidden_verifier_passed,
    )
    return HybridStageResult(
        status=status,
        live_evidence_allowed=live_ok,
        block_reason="" if live_ok else (error or "cloud_path_incomplete"),
        stages=stages,
        economics=economics,
        cloud_payload=cloud,
        candidate_patch=candidate_patch,
        candidate_identity=candidate_identity,
        selected_hash_matches_applied=hash_match if candidate_patch else False,
        semantic_correctness_passed=semantic_ok,
        hidden_verifier_passed=hidden_verifier_passed,
        error=error,
    )
