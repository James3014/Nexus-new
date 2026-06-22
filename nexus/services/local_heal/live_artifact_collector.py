"""EVAL-SUBSTRATE-1: Live full-loop artifact capture.

Collects artifacts during local_heal execution and writes them to a structured directory.
Every artifact is labeled with artifact_source to distinguish live-runtime from fixture-backed.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class LiveArtifact:
    """Single artifact with provenance."""
    artifact_name: str
    artifact_source: str  # live_runtime | fixture_backed | reconstructed | unavailable
    created_during_run: bool = False
    source_component: str = ""
    source_timestamp: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class LiveArtifactCollector:
    """Collects live artifacts during local_heal execution."""

    def __init__(self, task_id: str, arm: str, output_dir: Path):
        self.task_id = task_id
        self.arm = arm
        self.output_dir = output_dir / task_id / arm
        self.artifacts: list[LiveArtifact] = []
        self.repair_attempt_id = task_id

    def _make_live(self, name: str, component: str, data: dict) -> LiveArtifact:
        return LiveArtifact(
            artifact_name=name,
            artifact_source="live_runtime",
            created_during_run=True,
            source_component=component,
            source_timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            data=data,
        )

    def capture_input_manifest(self, task_id: str, repo: str, issue_summary: str, task_class: str) -> LiveArtifact:
        artifact = self._make_live("input_manifest.json", "orchestrator.start_task", {
            "task_id": task_id, "repo": repo, "issue_summary": issue_summary,
            "task_class": task_class, "repair_attempt_id": self.repair_attempt_id,
        })
        self.artifacts.append(artifact)
        return artifact

    def capture_memory_trace(self, trace_data: dict) -> LiveArtifact:
        artifact = self._make_live("memory_trace.json", "orchestrator._attach_memory_influence_trace", {
            **trace_data, "repair_attempt_id": self.repair_attempt_id,
        })
        self.artifacts.append(artifact)
        return artifact

    def capture_evidence_packet(self, packet_data: dict) -> LiveArtifact:
        artifact = self._make_live("evidence_packet.json", "native_evidence_packet.build", {
            **packet_data, "repair_attempt_id": self.repair_attempt_id,
        })
        self.artifacts.append(artifact)
        return artifact

    def capture_prompt_manifest(self, prompt_data: dict) -> LiveArtifact:
        artifact = self._make_live("prompt_manifest.json", "native_prompt_builder", {
            **prompt_data, "repair_attempt_id": self.repair_attempt_id,
        })
        self.artifacts.append(artifact)
        return artifact

    def capture_model_output(self, output_data: dict) -> LiveArtifact:
        artifact = self._make_live("model_output_summary.json", "patch_synthesis", {
            **output_data, "repair_attempt_id": self.repair_attempt_id,
        })
        self.artifacts.append(artifact)
        return artifact

    def capture_patch_apply(self, apply_data: dict) -> LiveArtifact:
        artifact = self._make_live("patch_apply_result.json", "constrained_action_applier", {
            **apply_data, "repair_attempt_id": self.repair_attempt_id,
        })
        self.artifacts.append(artifact)
        return artifact

    def capture_verifier_result(self, verifier_data: dict) -> LiveArtifact:
        artifact = self._make_live("verifier_result.json", "verification_phase", {
            **verifier_data, "repair_attempt_id": self.repair_attempt_id,
        })
        self.artifacts.append(artifact)
        return artifact

    def capture_receipt(self, receipt_data: dict) -> LiveArtifact:
        artifact = self._make_live("receipt.json", "receipt_writer", {
            **receipt_data, "repair_attempt_id": self.repair_attempt_id,
        })
        self.artifacts.append(artifact)
        return artifact

    def capture_evidence_bundle(self, bundle_data: dict) -> LiveArtifact:
        artifact = self._make_live("evidence_bundle.json", "EvidenceHarness", {
            **bundle_data, "repair_attempt_id": self.repair_attempt_id,
        })
        self.artifacts.append(artifact)
        return artifact

    def capture_bottleneck(self, bottleneck_data: dict) -> LiveArtifact:
        artifact = self._make_live("bottleneck_classification.json", "EvidenceHarness.classify_bottleneck", {
            **bottleneck_data, "repair_attempt_id": self.repair_attempt_id,
        })
        self.artifacts.append(artifact)
        return artifact

    def capture_arm_result(self, result_data: dict) -> LiveArtifact:
        artifact = self._make_live("arm_result.json", "orchestrator._finalize_run", {
            **result_data, "repair_attempt_id": self.repair_attempt_id,
        })
        self.artifacts.append(artifact)
        return artifact

    def write_all(self) -> Path:
        """Write all collected artifacts to disk with metadata."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for artifact in self.artifacts:
            path = self.output_dir / artifact.artifact_name
            # Merge metadata into data for written artifact
            output = dict(artifact.data)
            output["artifact_source"] = artifact.artifact_source
            output["created_during_run"] = artifact.created_during_run
            output["source_component"] = artifact.source_component
            output["source_timestamp"] = artifact.source_timestamp
            with open(path, "w") as f:
                json.dump(output, f, indent=2, default=str)
        return self.output_dir

    def get_live_count(self) -> int:
        return sum(1 for a in self.artifacts if a.artifact_source == "live_runtime")

    def get_total_count(self) -> int:
        return len(self.artifacts)
