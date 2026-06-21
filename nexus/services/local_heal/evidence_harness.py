"""RRL2: Full Repair Loop Evidence Harness.

Captures complete per-task evidence bundles during local_heal repair attempts.
Does not change repair behavior - only adds observability instrumentation.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class EvidenceBundle:
    """Complete evidence bundle for a single repair attempt."""
    task_id: str
    repo: str = ""
    issue_summary: str = ""
    failing_test: str = ""
    expected_behavior: str = ""
    task_class: str = ""
    difficulty: str = ""
    timestamp: str = ""

    # Route decision
    route_selected: str = ""
    route_reason: str = ""
    judge_output: str = ""
    route_confidence: float = 0.0

    # Anchor selection
    selected_anchor: str = ""
    anchor_score: float = 0.0
    anchor_file: str = ""
    anchor_line_span: list[int] = field(default_factory=list)
    total_candidates: int = 0
    selection_reason: str = ""

    # Evidence packet
    codeintel_nodes: int = 0
    codeintel_edges: int = 0
    memory_items: int = 0
    missing_context_risks: list[str] = field(default_factory=list)
    evidence_confidence: float = 0.0

    # Memory trace
    memory_available: bool = False
    retrieval_sources: list[str] = field(default_factory=list)
    memory_selected_ids: list[str] = field(default_factory=list)
    provenance_count: int = 0
    rerank_mode: bool = False
    no_memory_match: bool = True
    influence_status: str = "NOT_MEASURED"

    # Prompt manifest
    prompt_length_chars: int = 0
    memory_section_included: bool = False
    failure_section_included: bool = False
    evidence_section_included: bool = False

    # Model output
    model_name: str = ""
    output_length_chars: int = 0
    patch_produced: bool = False
    patch_format_valid: bool = False
    abstain_detected: bool = False

    # Candidate summary
    total_candidates: int = 0
    selected_candidate_id: str = ""
    selection_method: str = ""
    arbitration_used: bool = False

    # Patch apply
    patch_applied: bool = False
    patch_len: int = 0
    apply_method: str = ""
    rollback_performed: bool = False
    apply_error: str = ""

    # Verifier
    verifier_status: str = ""
    verifier_command: str = ""
    tests_collected: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    verifier_elapsed_sec: float = 0.0

    # Receipt
    receipt_path: str = ""
    claim_eligible: bool = False
    gate_passed: bool = False
    failure_reason: str = ""

    # Bottleneck classification (auto-derived)
    final_status: str = ""
    primary_bottleneck: str = ""
    secondary_bottlenecks: list[str] = field(default_factory=list)
    confidence: str = "LOW"
    human_readable_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvidenceHarness:
    """Captures evidence bundles during local_heal repair attempts.

    Usage:
        harness = EvidenceHarness()
        bundle = harness.start_task(task_id="C_12481", repo="sympy")
        # ... during repair pipeline ...
        bundle.route_selected = "full_nexus"
        bundle.patch_produced = True
        # ... at finalize ...
        bundle.verifier_status = "PASS"
        harness.finalize(bundle, output_dir)
    """

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or Path("artifacts/runtime/rrl2_runs")
        self.bundles: list[dict[str, Any]] = []

    def start_task(
        self,
        task_id: str,
        repo: str = "",
        issue_summary: str = "",
        task_class: str = "",
        difficulty: str = "",
    ) -> EvidenceBundle:
        """Start capturing evidence for a new task."""
        bundle = EvidenceBundle(
            task_id=task_id,
            repo=repo,
            issue_summary=issue_summary,
            task_class=task_class,
            difficulty=difficulty,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        return bundle

    def classify_bottleneck(self, bundle: EvidenceBundle) -> None:
        """Auto-derive bottleneck classification from bundle state."""
        if bundle.verifier_status == "PASS":
            bundle.final_status = "SOLVED"
            bundle.primary_bottleneck = "none"
            bundle.confidence = "HIGH"
            bundle.human_readable_reason = "Repair completed successfully"
            return

        # Classify failure
        if bundle.patch_applied and bundle.verifier_status == "FAIL":
            bundle.final_status = "VERIFIER_FAIL"
            if not bundle.patch_format_valid:
                bundle.primary_bottleneck = "patch_format"
            elif bundle.memory_available and not bundle.memory_selected_ids:
                bundle.primary_bottleneck = "evidence_memory"
            else:
                bundle.primary_bottleneck = "verifier_harness"
            bundle.confidence = "MEDIUM"
        elif not bundle.patch_produced:
            bundle.final_status = "MODEL_WRONG"
            bundle.primary_bottleneck = "model_generation"
            bundle.confidence = "MEDIUM"
        elif bundle.patch_produced and not bundle.patch_applied:
            bundle.final_status = "PATCH_APPLY_FAIL"
            bundle.primary_bottleneck = "patch_apply"
            bundle.confidence = "HIGH"
        elif bundle.abstain_detected:
            bundle.final_status = "MODEL_ABSTAIN"
            bundle.primary_bottleneck = "model_generation"
            bundle.confidence = "MEDIUM"
        else:
            bundle.final_status = "INCONCLUSIVE"
            bundle.primary_bottleneck = "unknown"
            bundle.confidence = "LOW"

        bundle.human_readable_reason = f"Auto-classified: {bundle.final_status} due to {bundle.primary_bottleneck}"

    def finalize(self, bundle: EvidenceBundle, output_dir: Path | None = None) -> Path:
        """Write evidence bundle to disk and record in index."""
        self.classify_bottleneck(bundle)

        out = output_dir or self.output_dir
        task_dir = out / bundle.task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        # Write evidence bundle
        bundle_path = task_dir / "evidence_bundle.json"
        with open(bundle_path, "w") as f:
            json.dump(bundle.to_dict(), f, indent=2, default=str)

        # Write bottleneck classification separately
        bottleneck_path = task_dir / "bottleneck_classification.json"
        with open(bottleneck_path, "w") as f:
            json.dump({
                "task_id": bundle.task_id,
                "final_status": bundle.final_status,
                "primary_bottleneck": bundle.primary_bottleneck,
                "secondary_bottlenecks": bundle.secondary_bottlenecks,
                "confidence": bundle.confidence,
                "human_readable_reason": bundle.human_readable_reason,
            }, f, indent=2)

        # Record in index
        self.bundles.append(bundle.to_dict())

        return bundle_path
