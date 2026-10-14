import os
from collections import defaultdict
from typing import List, Optional, Dict, Any
from nexus.committee.registry import CandidateRegistry
from nexus.committee.adapter import ProposerAdapter
from nexus.verifiers.registry import VerifierRegistry
from nexus.verifiers.packs.registry import PackRegistry
from nexus.verifiers.contracts import VerifierVerdict
from nexus.selection.calibrator import ConfidenceCalibrator
from nexus.selection.decision_policy import DecisionPolicy
from nexus.feedback.router import FeedbackRouter
from nexus.retry_policy.policy import RetryPolicy
from nexus.search.sampler import AdaptiveResampler, directive_to_dict
from nexus.committee.models import CommitteeReceipt
from nexus.committee.oracle_touch_guard import patch_violations, rejection_verdict
from nexus.selection.contracts import SelectionVerdict

class CommitteeControllerV263:
    """
    🎮 [NEXUS v26.7] 資料流精修版控制器
    職責: 透過明確的 Bounded Contexts 驅動解題管線，消除特殊分支。
    """
    def __init__(self, task_id: str, domains: List[str] = None, verifiers: Optional[List[Any]] = None):
        self.enabled = os.getenv("NEXUS_USE_COMMITTEE", "0") == "1"
        self.packs_enabled = os.getenv("NEXUS_USE_PACKS", "0") == "1"
        self.task_id = task_id
        self.domains = domains or ["astropy"]
        
        self.registry = CandidateRegistry(task_id)
        self.adapter = ProposerAdapter()
        self.calibrator = ConfidenceCalibrator()
        self.decision_policy = DecisionPolicy()
        self.last_candidate_evidence_collection: Dict[str, Any] = {}
        self.resampler = AdaptiveResampler()
        self.last_retry_directive: Dict[str, Any] = {}
        # Explicit per-call verifiers (e.g. PatchExecutionVerifier); None keeps the global registry.
        self.verifiers = list(verifiers) if verifiers is not None else None

    @staticmethod
    def _proposer(p: Dict[str, Any]) -> str:
        # "proposer_id" is the canonical-context-safe name; "model" stays for in-process callers.
        return str(p.get("proposer_id") or p.get("model") or "")

    def process_proposals(self, raw_proposals: List[Dict[str, Any]]) -> CommitteeReceipt:
        if not self.enabled:
            return self._fallback_receipt(raw_proposals)

        # 1. Ingress
        for p in raw_proposals:
            candidate = self.adapter.create_candidate(self.task_id, self._proposer(p), p["attempt"], p["raw_label"], p.get("artifacts", []))
            self.registry.register(candidate)
        
        candidates = self.registry.get_all()
        all_verdicts = []

        # 1b. Test/oracle guard (fail closed, before verification and selection): a candidate
        # whose patch modifies a test or oracle file is never verified, scored or selected.
        guard_verdicts = []
        guarded_ids = set()
        for c in candidates:
            reasons = patch_violations(c.artifact_refs[0] if c.artifact_refs else "")
            if reasons:
                guarded_ids.add(c.candidate_id)
                guard_verdicts.append(rejection_verdict(c.candidate_id, reasons))

        # 2. Verification
        for c in candidates:
            if c.candidate_id in guarded_ids:
                continue
            patch = c.artifact_refs[0] if c.artifact_refs else ''
            # Pack 驗證
            if self.packs_enabled:
                for pack in PackRegistry.get_enabled_packs(self.domains):
                    all_verdicts.extend(pack.evaluate_all(c.candidate_id, patch))
            # 基礎驗證 (Fallback if no pack)
            if self.verifiers is not None:
                for v in self.verifiers:
                    all_verdicts.append(v.evaluate(c.candidate_id, patch))
            elif not all_verdicts:
                for v in VerifierRegistry.get_all_verifiers():
                    all_verdicts.append(v.evaluate(c.candidate_id, patch))
            
        # 3. Calibration & Decision over the eligible candidates only: a guarded candidate is not
        # scored, so it neither wins nor hands another candidate an artificial gap (with one
        # eligible candidate left the abstention policy abstains, as for a single proposal).
        if guarded_ids and len(guarded_ids) == len(candidates):
            selection_res = SelectionVerdict(
                winner_id=None,
                confidence=0.0,
                gap=0.0,
                abstained=True,
                reason="ALL_CANDIDATES_MODIFY_TEST_OR_ORACLE",
                failure_bucket="test_or_oracle_modified",
            )
        else:
            calibrated_data = self.calibrator.calibrate(all_verdicts, 0.7)
            selection_res = self.decision_policy.evaluate_and_decide(calibrated_data, calibrated_data["calibrated_confidence"])
            if selection_res.winner_id in guarded_ids:  # defensive: never select a guarded one
                selection_res = SelectionVerdict(
                    winner_id=None,
                    confidence=0.0,
                    gap=0.0,
                    abstained=True,
                    reason="GUARDED_CANDIDATE_SELECTED",
                    failure_bucket="test_or_oracle_modified",
                )
        all_verdicts = guard_verdicts + all_verdicts

        # 4. Feedback & Retry (Decoupled Data-Flow)
        self.last_retry_directive = {}
        if selection_res.abstained:
            # Stage 1: Map (Mapper)
            patterns = FeedbackRouter.map_verdicts(all_verdicts)
            # Stage 2: Decide (Decider)
            retry_action = RetryPolicy.decide(patterns, len(candidates))
            # Stage 3: Resample — verifier feedback first, then bucket / diversity.
            directive = self.resampler.evaluate_and_decide(
                failure_bucket=selection_res.failure_bucket,
                candidate_contents=[c.artifact_refs[0] if c.artifact_refs else "" for c in candidates],
                current_k=len(candidates),
                feedback_action=retry_action,
                pattern_codes=[p.pattern_code for p in patterns],
            )
            self.last_retry_directive = directive_to_dict(directive)

            if directive.should_retry:
                print(f"🔄 [Feedback] Action: {directive.mode} | Params: {directive.modified_params}")
        
        receipt = CommitteeReceipt(
            task_id=self.task_id,
            k=len(candidates),
            candidates=candidates,
            verdicts=all_verdicts,
            winner_id=selection_res.winner_id,
            failure_bucket=selection_res.failure_bucket,
            abstain_reason=(
                selection_res.reason
                if selection_res.failure_bucket == "test_or_oracle_modified"
                else None
            ),
            confidence=selection_res.confidence,
            verifier_gap=selection_res.gap,
            total_cost=len(candidates) * 0.05
        )

        # Research-only sidecar. Committee critics are weaker than isolated
        # execution tests, so these rows are preserved for analysis but marked
        # CRITIC_AGGREGATE and are not training-eligible by default.
        try:
            import hashlib as _hashlib

            from nexus.research.clm_system_one.candidate_evidence_collector import (
                collect_candidate_group,
            )

            verdicts_by_candidate: Dict[str, list[VerifierVerdict]] = defaultdict(list)
            for verdict in all_verdicts:
                verdicts_by_candidate[str(verdict.candidate_id)].append(verdict)

            collection_candidates = []
            for candidate in candidates:
                candidate_verdicts = verdicts_by_candidate.get(candidate.candidate_id, [])
                if candidate_verdicts:
                    aggregate_status = (
                        "pass" if all(v.passed for v in candidate_verdicts) else "fail"
                    )
                else:
                    aggregate_status = "unknown"
                evidence_rows = []
                for verdict in candidate_verdicts:
                    evidence_rows.append(
                        {
                            "verifier_name": verdict.verifier_name,
                            "passed": bool(verdict.passed),
                            "score": float(verdict.score),
                            "evidence_refs": [
                                {
                                    "source_file": ref.source_file,
                                    "line_number": ref.line_number,
                                    "snippet_sha256": _hashlib.sha256(
                                        str(ref.snippet or "").encode("utf-8")
                                    ).hexdigest(),
                                }
                                for ref in verdict.evidence_refs
                            ],
                            "failure_tags": [
                                {"code": tag.code, "description": tag.description}
                                for tag in verdict.failure_tags
                            ],
                        }
                    )
                payload = candidate.artifact_refs[0] if candidate.artifact_refs else ""
                collection_candidates.append(
                    {
                        "candidate_id": candidate.candidate_id,
                        "candidate_model": candidate.source_model,
                        "candidate_source": "committee_v263",
                        "candidate_payload": payload,
                        "candidate_payload_sha256": "",
                        "candidate_state_hash": "",
                        "verifier_status": aggregate_status,
                        "label_quality": "CRITIC_AGGREGATE",
                        "verifier_evidence": {
                            "verdicts": evidence_rows,
                        },
                        "failure_reason_codes": sorted(
                            {
                                tag.code
                                for verdict in candidate_verdicts
                                for tag in verdict.failure_tags
                            }
                        ),
                        "selected": candidate.candidate_id == receipt.winner_id,
                    }
                )
            collection = collect_candidate_group(
                repo_root=os.getcwd(),
                task_id=self.task_id,
                attempt_id="committee",
                collector_source="committee_v263",
                contract_identity={
                    "task_id": self.task_id,
                    "domains": list(self.domains),
                    "policy_version": receipt.policy_version,
                },
                verifier_identity={
                    "kind": "committee_critic_set",
                    "verifier_names": sorted(
                        {verdict.verifier_name for verdict in all_verdicts}
                    ),
                    "packs_enabled": bool(self.packs_enabled),
                    "domains": list(self.domains),
                },
                candidates=collection_candidates,
                winner_id=receipt.winner_id or "",
            )
            self.last_candidate_evidence_collection = collection.to_dict()
        except Exception as exc:
            self.last_candidate_evidence_collection = {
                "schema": "nexus.clm_candidate_evidence_collection.v1",
                "status": "ERROR",
                "error_type": type(exc).__name__,
            }

        return receipt

    def _fallback_receipt(self, raw_proposals):
        p = raw_proposals[0]
        candidate = self.adapter.create_candidate(self.task_id, self._proposer(p), p['attempt'], p['raw_label'], [])
        return CommitteeReceipt(self.task_id, 1, [candidate], [], candidate.candidate_id, 'feature_disabled_fallback')
