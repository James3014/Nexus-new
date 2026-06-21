"""G1: Agentless-Style Candidate Pipeline

Bounded candidate generation with:
- top-k semantic anchors
- 3-5 candidates per anchor
- parser filter
- patch apply filter
- verifier filter
- compliance filter
- deterministic selection
No model self-rating.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class CandidateStage(Enum):
    GENERATED = "generated"
    PARSER_PASSED = "parser_passed"
    PATCH_APPLIED = "patch_applied"
    VERIFIER_PASSED = "verifier_passed"
    COMPLIANCE_PASSED = "compliance_passed"
    SELECTED = "selected"
    REJECTED = "rejected"


@dataclass
class PipelineCandidate:
    """Candidate flowing through the Agentless pipeline."""
    candidate_id: str
    anchor_id: str
    anchor_symbol: str
    replacement: str
    replacement_hash: str
    stage: CandidateStage
    rejection_reason: str = ""
    verifier_output: str = ""
    patch_diff: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Result of Agentless candidate pipeline."""
    task_id: str
    candidates: list[PipelineCandidate]
    selected: PipelineCandidate | None
    stage_counts: dict[str, int]
    status: str


class AgentlessCandidatePipeline:
    """Bounded candidate pipeline inspired by Agentless."""

    def __init__(
        self,
        *,
        max_anchors: int = 3,
        max_candidates_per_anchor: int = 3,
        parser_filter: Callable[[str, str], tuple[bool, str]] | None = None,
        patch_filter: Callable[[str, str, str], tuple[bool, str]] | None = None,
        verifier_filter: Callable[[str], tuple[bool, str]] | None = None,
        compliance_filter: Callable[[dict], tuple[bool, str]] | None = None,
    ):
        self.max_anchors = max_anchors
        self.max_candidates_per_anchor = max_candidates_per_anchor
        self.parser_filter = parser_filter or self._default_parser_filter
        self.patch_filter = patch_filter or self._default_patch_filter
        self.verifier_filter = verifier_filter or self._default_verifier_filter
        self.compliance_filter = compliance_filter or self._default_compliance_filter

    def run(
        self,
        *,
        task_id: str,
        anchors: list[dict],  # [{id, symbol, source_text, score}]
        generate_fn: Callable[[str, str, str], str],
        apply_fn: Callable[[str, str, str], tuple[bool, str, str]] | None = None,
        verify_fn: Callable[[str], tuple[bool, str]] | None = None,
        compliance_fn: Callable[[dict], tuple[bool, str]] | None = None,
    ) -> PipelineResult:
        """Run the Agentless candidate pipeline."""
        candidates = []
        seen_hashes = set()

        # Sort anchors by score descending, take top-k
        sorted_anchors = sorted(anchors, key=lambda a: a.get("score", 0), reverse=True)[:self.max_anchors]

        for anchor in sorted_anchors:
            anchor_id = anchor["id"]
            anchor_symbol = anchor["symbol"]
            anchor_text = anchor["source_text"]

            for i in range(self.max_candidates_per_anchor):
                candidate_id = f"g1_{anchor_id}_v{i+1}"

                # Stage 1: Generate
                replacement = generate_fn(anchor_text, anchor_symbol, candidate_id)
                if not replacement:
                    candidates.append(PipelineCandidate(
                        candidate_id=candidate_id,
                        anchor_id=anchor_id,
                        anchor_symbol=anchor_symbol,
                        replacement="",
                        replacement_hash="",
                        stage=CandidateStage.REJECTED,
                        rejection_reason="empty_response",
                    ))
                    continue

                # Check duplicate
                rep_hash = hashlib.sha256(replacement.strip().encode()).hexdigest()[:16]
                if rep_hash in seen_hashes:
                    candidates.append(PipelineCandidate(
                        candidate_id=candidate_id,
                        anchor_id=anchor_id,
                        anchor_symbol=anchor_symbol,
                        replacement=replacement,
                        replacement_hash=rep_hash,
                        stage=CandidateStage.REJECTED,
                        rejection_reason="duplicate",
                    ))
                    continue
                seen_hashes.add(rep_hash)

                # Stage 2: Parser filter
                parser_ok, parser_reason = self.parser_filter(replacement, anchor_text)
                if not parser_ok:
                    candidates.append(PipelineCandidate(
                        candidate_id=candidate_id,
                        anchor_id=anchor_id,
                        anchor_symbol=anchor_symbol,
                        replacement=replacement,
                        replacement_hash=rep_hash,
                        stage=CandidateStage.REJECTED,
                        rejection_reason=f"parser:{parser_reason}",
                    ))
                    continue

                # Stage 3: Patch apply filter
                if apply_fn:
                    apply_ok, apply_reason, diff = apply_fn(replacement, anchor_text, anchor_id)
                    if not apply_ok:
                        candidates.append(PipelineCandidate(
                            candidate_id=candidate_id,
                            anchor_id=anchor_id,
                            anchor_symbol=anchor_symbol,
                            replacement=replacement,
                            replacement_hash=rep_hash,
                            stage=CandidateStage.REJECTED,
                            rejection_reason=f"patch:{apply_reason}",
                        ))
                        continue
                else:
                    diff = ""

                # Stage 4: Verifier filter
                if verify_fn:
                    verify_ok, verify_output = verify_fn(replacement)
                    if not verify_ok:
                        candidates.append(PipelineCandidate(
                            candidate_id=candidate_id,
                            anchor_id=anchor_id,
                            anchor_symbol=anchor_symbol,
                            replacement=replacement,
                            replacement_hash=rep_hash,
                            stage=CandidateStage.REJECTED,
                            rejection_reason=f"verifier:{verify_output[:100]}",
                            verifier_output=verify_output,
                            patch_diff=diff,
                        ))
                        continue
                else:
                    verify_output = "no_verifier"

                # Stage 5: Compliance filter
                compliance_payload = {
                    "task_id": task_id,
                    "anchor_id": anchor_id,
                    "replacement": replacement,
                    "verifier_output": verify_output,
                }
                if compliance_fn:
                    comply_ok, comply_reason = compliance_fn(compliance_payload)
                    if not comply_ok:
                        candidates.append(PipelineCandidate(
                            candidate_id=candidate_id,
                            anchor_id=anchor_id,
                            anchor_symbol=anchor_symbol,
                            replacement=replacement,
                            replacement_hash=rep_hash,
                            stage=CandidateStage.REJECTED,
                            rejection_reason=f"compliance:{comply_reason}",
                            verifier_output=verify_output,
                            patch_diff=diff,
                        ))
                        continue

                # All filters passed — candidate is selected
                selected = PipelineCandidate(
                    candidate_id=candidate_id,
                    anchor_id=anchor_id,
                    anchor_symbol=anchor_symbol,
                    replacement=replacement,
                    replacement_hash=rep_hash,
                    stage=CandidateStage.SELECTED,
                    verifier_output=verify_output,
                    patch_diff=diff,
                )
                candidates.append(selected)

                # Stop after first selection (deterministic) — break both loops
                return PipelineResult(
                    task_id=task_id,
                    candidates=candidates,
                    selected=selected,
                    stage_counts={"selected": 1, "rejected": len(candidates) - 1},
                    status="G1_PIPELINE_SUCCESS",
                )

        # Determine status
        selected = next((c for c in candidates if c.stage == CandidateStage.SELECTED), None)
        stage_counts = {}
        for c in candidates:
            stage_counts[c.stage.value] = stage_counts.get(c.stage.value, 0) + 1

        if selected:
            status = "G1_PIPELINE_SUCCESS"
        elif stage_counts.get("rejected", 0) == len(candidates):
            status = "G1_ALL_REJECTED"
        else:
            status = "G1_NO_SELECTION"

        return PipelineResult(
            task_id=task_id,
            candidates=candidates,
            selected=selected,
            stage_counts=stage_counts,
            status=status,
        )

    @staticmethod
    def _default_parser_filter(replacement: str, anchor: str) -> tuple[bool, str]:
        """Default parser: reject prose, markdown, empty."""
        stripped = replacement.strip()
        if not stripped:
            return False, "empty"
        if stripped.startswith("```"):
            return False, "markdown_fence"
        # Check first line for prose
        first_line = stripped.splitlines()[0] if stripped else ""
        prose_starters = ["here", "this", "the", "note", "see", "fix", "patch"]
        if any(first_line.lower().startswith(p) for p in prose_starters):
            return False, "prose"
        return True, ""

    @staticmethod
    def _default_patch_filter(replacement: str, anchor: str, anchor_id: str) -> tuple[bool, str, str]:
        """Default patch: just return diff placeholder."""
        return True, "", f"diff for {anchor_id}"

    @staticmethod
    def _default_verifier_filter(replacement: str) -> tuple[bool, str]:
        """Default verifier: always pass (no verifier)."""
        return True, "no_verifier"

    @staticmethod
    def _default_compliance_filter(payload: dict) -> tuple[bool, str]:
        """Default compliance: always pass."""
        return True, ""
