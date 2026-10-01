from __future__ import annotations

import hashlib
from typing import Any

from nexus.services.local_heal.backend_resource_policy import DEFAULT_POLICIES, ResourcePolicy
from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
from nexus.services.local_heal.local_model_provider import (
    LocalModelProvider,
    LocalModelProviderRequest,
)

# Lazy module-level references for trajectory telemetry — patchable by tests.
# These are resolved once at import time; if the research package is unavailable
# the attributes are left as None and telemetry is skipped entirely (fail-open).
try:
    from nexus.research.clm_system_one.trajectory_continuity import (
        bind_trajectory_step_result,
        resolve_research_evidence_root,
        seal_trajectory_step,
    )
except Exception:  # pragma: no cover
    resolve_research_evidence_root = None  # type: ignore[assignment]
    seal_trajectory_step = None  # type: ignore[assignment]
    bind_trajectory_step_result = None  # type: ignore[assignment]


def stable_committee_trajectory_id(
    *,
    task_id: str,
    attempt_id: str,
    member_index: int,
    model_name: str,
) -> str:
    """Derive a stable, collision-safe trajectory_id for a committee member.

    The key components are:
    - task_id: bound to this specific task
    - attempt_id: bound to this generation attempt
    - member_index: the original 1-based index in the full committee list
      (judge at index 1, proposers at 2..N) — stable across retries
    - model_name: the model identity

    Hash-derived to guarantee no collision across different (task, attempt,
    index, model) combinations even if individual components share prefixes.
    """
    key = f"{task_id}\x00{attempt_id}\x00{member_index}\x00{model_name}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"lc-traj-{digest}"


class LocalCommitteeCandidateProvider:
    @staticmethod
    def generate_committee_candidates(
        *,
        task_id: str,
        problem_statement: str,
        target_file: str,
        target_symbol: str,
        locked_search: str,
        evidence_refs: tuple[str, ...],
        provider: LocalModelProvider,
        protocol_mode: str,
        route_context: dict[str, Any] | None = None,
        attempt_id: str = "attempt-1",
        execution_profile: str = "FULL",
        repo_root: str = "",
        source_revision: str = "",
    ) -> list[CandidateEnvelope]:
        # 1. Define committee members, roles and protocols.
        signal_snapshot = route_context.get("signal_snapshot", {}) if isinstance(route_context, dict) else {}
        proposer_specs = signal_snapshot.get("proposer_specs")
        if proposer_specs is None:
            raise ValueError("Missing proposer_specs in signal_snapshot for local_committee topology")
            
        judge_model = signal_snapshot.get("judge_model")
        if not judge_model:
            raise ValueError("Missing judge_model in signal_snapshot for local_committee topology")
        proposer_specs = list(proposer_specs)
        if len(proposer_specs) < 2:
            raise ValueError("local_committee topology requires at least two proposer_specs")

        seen_models: set[str] = set()
        for spec in proposer_specs:
            role = spec.get("role")
            if not role:
                raise ValueError("Missing proposer spec role in signal_snapshot")
            model_name = spec.get("model")
            if not model_name:
                raise ValueError("Missing proposer spec model in signal_snapshot")
            if model_name == judge_model:
                raise ValueError("judge_model must not also appear in proposer_specs")
            if model_name in seen_models:
                raise ValueError("Duplicate proposer model in signal_snapshot")
            seen_models.add(model_name)
            
        committee_models = [
            (judge_model, "judge", "none")
        ]
        for spec in proposer_specs:
            role = spec["role"]
            model_name = spec["model"]
            role_name = f"{role}_proposer"
            committee_models.append((model_name, role_name, protocol_mode))
        
        envelopes = []
        anchor_hash = hashlib.sha256(locked_search.encode("utf-8")).hexdigest() if locked_search else ""
        
        # Resolve telemetry context once — absent = no telemetry attempted.
        _telem_enabled = bool(repo_root) and resolve_research_evidence_root is not None
        _evidence_root = None
        if _telem_enabled:
            try:
                _evidence_root = resolve_research_evidence_root(repo_root)  # type: ignore[misc]
            except Exception:
                _telem_enabled = False

        import re
        for idx, (model_name, role, patch_protocol) in enumerate(committee_models, 1):
            # Create a safe model slug (lowercase, replace non-alphanumeric chars with hyphens)
            safe_model_slug = re.sub(r'[^a-zA-Z0-9]', '-', model_name.lower())
            safe_model_slug = re.sub(r'-+', '-', safe_model_slug).strip('-')

            # 2. Check resource policies
            policy = DEFAULT_POLICIES.get(model_name)
            blocked = False
            risk_flags = []
            
            if policy is not None:
                if policy.resource_policy == ResourcePolicy.FORBIDDEN:
                    blocked = True
                    risk_flags.append("resource_policy_forbidden")
            
            if blocked:
                env = CandidateEnvelope(
                    candidate_id=f"{task_id}-{role}-{idx:02d}-{safe_model_slug}-blocked",
                    task_id=task_id,
                    source="local",
                    model=model_name,
                    role=role,
                    patch_protocol=patch_protocol,
                    target_file=target_file,
                    target_symbol=target_symbol,
                    source_anchor_hash=anchor_hash,
                    candidate_patch_hash=hashlib.sha256(b"").hexdigest(),
                    evidence_refs=evidence_refs,
                    risk_flags=tuple(risk_flags),
                    abstained=True,
                    candidate_patch="",
                )
                envelopes.append(env)
                continue

            # 3. Construct prompt based on role
            if role == "judge":
                prompt = (
                    f"You are a judge evaluating a coding task.\n"
                    f"Problem: {problem_statement}\n"
                    f"Target File: {target_file}\n"
                    f"Target Symbol: {target_symbol}\n"
                    f"Locked Search Span:\n"
                    f"```\n{locked_search}\n```\n\n"
                    f"Please analyze the problem and provide a brief ranking or classification. Do not generate a patch."
                )
            elif patch_protocol == "anchored_edit":
                prompt = (
                    f"You are generating a replacement code block to solve a coding task.\n"
                    f"Problem: {problem_statement}\n"
                    f"Target File: {target_file}\n"
                    f"Target Symbol: {target_symbol}\n"
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
                    f"Output ONLY code between <<<<<<< and >>>>>>>. No backticks. No explanations. No comments. Code only."
                )
            else:
                prompt = (
                    f"You are generating a git diff to solve a coding task.\n"
                    f"Problem: {problem_statement}\n"
                    f"Target File: {target_file}\n"
                    f"Target Symbol: {target_symbol}\n"
                    f"Locked Search Span:\n"
                    f"```\n{locked_search}\n```\n\n"
                    f"Provide standard unified diff output."
                )
                
            prov_req = LocalModelProviderRequest(
                task_id=task_id,
                prompt=prompt,
                evidence_refs=evidence_refs,
                model_name=model_name,
                phase="judge" if role == "judge" else "proposer",
                attempt_id=attempt_id,
                execution_profile=execution_profile,
            )

            # 4. Pre-action trajectory capture for non-judge proposers (fail-open).
            _traj_step_ref = None
            _is_proposer = role != "judge"
            if _is_proposer and _telem_enabled and _evidence_root is not None and seal_trajectory_step is not None:
                try:
                    _traj_id = stable_committee_trajectory_id(
                        task_id=task_id,
                        attempt_id=attempt_id,
                        member_index=idx,
                        model_name=model_name,
                    )
                    _traj_step_ref = seal_trajectory_step(  # type: ignore[misc]
                        evidence_root=_evidence_root,
                        task_id=task_id,
                        trajectory_id=_traj_id,
                        attempt_id=attempt_id,
                        candidate_id=None,  # not yet known before generate
                        step_index=0,
                        source_revision=source_revision,
                        base_source_revision=source_revision,
                        pre_action_state={
                            "task_objective": problem_statement,
                            "target_file": target_file,
                            "evidence_refs": [str(r) for r in (evidence_refs or [])],
                            "phase": "proposer",
                        },
                        action_type="local_committee_generate",
                        action_payload={
                            "model_name": model_name,
                            "role": role,
                            "patch_protocol": patch_protocol,
                            "attempt_id": attempt_id,
                            "execution_profile": execution_profile,
                        },
                    )
                except Exception:
                    # Telemetry must never affect candidate generation.
                    _traj_step_ref = None

            # 5. Invoke provider — wrap with trajectory result binding.
            try:
                prov_resp = provider.generate(prov_req)
            except Exception as _gen_exc:
                # Bind exception result for the sealed step, then re-raise.
                if _traj_step_ref is not None and bind_trajectory_step_result is not None:
                    try:
                        bind_trajectory_step_result(  # type: ignore[misc]
                            evidence_root=_evidence_root,
                            step_ref=_traj_step_ref,
                            action_result={
                                "response_type": "Exception",
                                "exception_type": type(_gen_exc).__name__,
                                "error": str(_gen_exc),
                            },
                        )
                    except Exception:
                        pass
                raise

            # Bind success result for the sealed step.
            if _traj_step_ref is not None and bind_trajectory_step_result is not None:
                try:
                    bind_trajectory_step_result(  # type: ignore[misc]
                        evidence_root=_evidence_root,
                        step_ref=_traj_step_ref,
                        action_result={
                            "response_type": type(prov_resp).__name__,
                            "output_text": prov_resp.output_text or "",
                            "error": str(prov_resp.error or ""),
                        },
                    )
                except Exception:
                    pass

            if prov_resp.error:
                env = CandidateEnvelope(
                    candidate_id=f"{task_id}-{role}-{idx:02d}-{safe_model_slug}-error",
                    task_id=task_id,
                    source="local",
                    model=model_name,
                    role=role,
                    patch_protocol=patch_protocol,
                    target_file=target_file,
                    target_symbol=target_symbol,
                    source_anchor_hash=anchor_hash,
                    candidate_patch_hash=hashlib.sha256(b"").hexdigest(),
                    evidence_refs=evidence_refs,
                    risk_flags=(prov_resp.error,),
                    abstained=True,
                    candidate_patch="",
                )
            else:
                patch_text = prov_resp.output_text if role != "judge" else ""
                patch_hash = hashlib.sha256(patch_text.encode("utf-8")).hexdigest() if patch_text else hashlib.sha256(b"").hexdigest()
                env = CandidateEnvelope(
                    candidate_id=f"{task_id}-{role}-{idx:02d}-{safe_model_slug}-success",
                    task_id=task_id,
                    source="local",
                    model=model_name,
                    role=role,
                    patch_protocol=patch_protocol,
                    target_file=target_file,
                    target_symbol=target_symbol,
                    source_anchor_hash=anchor_hash,
                    candidate_patch_hash=patch_hash,
                    evidence_refs=evidence_refs,
                    risk_flags=(),
                    abstained=False,
                    candidate_patch=patch_text,
                )
            envelopes.append(env)
            
        return envelopes
