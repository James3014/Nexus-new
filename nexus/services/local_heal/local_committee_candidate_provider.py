from __future__ import annotations

import hashlib
import os
from typing import Any
from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
from nexus.services.local_heal.local_model_provider import (
    LocalModelProvider,
    LocalModelProviderRequest,
)
from nexus.services.local_heal.role_contract import ROLE_CONTRACT, ModelRole, MODEL_ROLE_ALIASES
from nexus.services.local_heal.backend_resource_policy import DEFAULT_POLICIES, ResourcePolicy


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
                    f"Provide the replacement code inside a REPLACE block exactly like this:\n"
                    f"<<<<<<< REPLACE\n"
                    f"[replacement code goes here]\n"
                    f">>>>>>> REPLACE\n\n"
                    f"Do not include any other text, explanation, markdown formatting, or markdown code fences outside the REPLACE block."
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
            )
            
            prov_resp = provider.generate(prov_req)
            
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
