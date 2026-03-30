"""
nexus/core/handoff_bundle.py
─────────────────────────────
Human Review Handoff Bundle — Sprint 11c

Whenever the pipeline transitions to HUMAN_REVIEW, this module is responsible for
generating a complete, self-contained handoff package under .nexus/handoff/ so that
a human operator can inspect, resume, or override the agent's work from a clean state.

Bundle Schema: handoff_v1.json
"""
import json
import logging
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

HANDOFF_SCHEMA_VERSION = "handoff_v1"

@dataclass
class HandoffRequest:
    """交接請求的參數封裝。"""
    triggering_phase: str
    reason: str
    task_id: str = ""
    trace_id: str = ""
    decision_id: str = ""
    agent_history: Optional[List[str]] = None
    state_variables: Optional[Dict[str, Any]] = None

@dataclass
class HandoffRetentionPolicy:
    """
    Governs how long HandoffBundles are retained and whether they can be compressed.
    Ensures handoff bundles are treated as first-class artifacts in the Nexus evidence chain.
    """
    retention_days: int = 30          # Bundles older than this will be pruned
    compress: bool = True             # Gzip compress bundles after writing
    max_bundles: int = 100            # Maximum number of bundles to keep on disk

@dataclass
class HandoffBundle:
    schema_version: str = HANDOFF_SCHEMA_VERSION
    triggering_phase: str = "unknown"
    reason: str = "Unspecified escalation"
    task_id: str = ""
    trace_id: str = ""          # Links to NexusOutcomeV2 / NexusMinimalTracer trace
    decision_id: str = ""       # Links to the Coordinator decision that triggered this state
    agent_history_summary: List[str] = field(default_factory=list)
    state_variables: Dict[str, Any] = field(default_factory=dict)
    workspace_diff: str = ""
    timestamp: str = ""
    retention_policy: Dict[str, Any] = field(default_factory=dict)

class HandoffBundleWriter:
    """
    Packages and persists a HandoffBundle to .nexus/handoff/<timestamp>.json
    whenever a HUMAN_REVIEW signal is emitted.

    Now supports:
      - Retention policy (TTL, compression, max_bundles cap)
      - trace_id linkage (to NexusMinimalTracer spans)
      - decision_id linkage (to Coordinator decision record)
    """
    DEFAULT_POLICY = HandoffRetentionPolicy()

    def __init__(self, project_root: Path, policy: Optional[HandoffRetentionPolicy] = None):
        self.project_root = project_root
        self.handoff_dir = project_root / ".nexus" / "handoff"
        self.handoff_dir.mkdir(parents=True, exist_ok=True)
        self.policy = policy or self.DEFAULT_POLICY

    def create(self, request: HandoffRequest) -> Path:
        """
        Creates and writes a HandoffBundle JSON file.
        Returns the path to the written bundle.
        """
        diff = self._capture_workspace_diff()
        timestamp = datetime.now(timezone.utc).isoformat()

        bundle = HandoffBundle(
            triggering_phase=request.triggering_phase,
            reason=request.reason,
            task_id=request.task_id,
            trace_id=request.trace_id,
            decision_id=request.decision_id,
            agent_history_summary=request.agent_history or [],
            state_variables=request.state_variables or {},
            workspace_diff=diff,
            timestamp=timestamp,
            retention_policy={
                "retention_days": self.policy.retention_days,
                "compress": self.policy.compress,
                "max_bundles": self.policy.max_bundles,
            },
        )

        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        bundle_path = self.handoff_dir / f"handoff_{request.task_id or 'unknown'}_{ts_str}.json"
        bundle_path.write_text(json.dumps(asdict(bundle), indent=2))

        if self.policy.compress:
            import gzip
            import shutil
            gz_path = bundle_path.with_suffix(".json.gz")
            with bundle_path.open("rb") as f_in, gzip.open(gz_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            bundle_path.unlink()
            bundle_path = gz_path

        self._apply_retention()

        logger.warning(
            "🧑‍💻 [HUMAN_REVIEW] Handoff bundle written to: %s\n"
            "   Reason: %s\n"
            "   Triggering Phase: %s",
            bundle_path.relative_to(self.project_root),
            request.reason,
            request.triggering_phase,
        )
        return bundle_path

    def _apply_retention(self) -> None:
        """
        Enforces retention policy:
          1. Remove bundles older than retention_days
          2. Cap total bundles at max_bundles (oldest first)
        """
        now = datetime.now(timezone.utc)
        all_bundles = sorted(
            list(self.handoff_dir.glob("handoff_*.json")) +
            list(self.handoff_dir.glob("handoff_*.json.gz")),
            key=lambda p: p.stat().st_mtime,
        )
        # TTL pruning
        cutoff_ts = now.timestamp() - (self.policy.retention_days * 86400)
        for p in all_bundles:
            if p.stat().st_mtime < cutoff_ts:
                p.unlink()
                logger.info("[Handoff:Retention] Pruned expired bundle: %s", p.name)

        # Max cap pruning (re-scan after TTL removal)
        remaining = sorted(
            list(self.handoff_dir.glob("handoff_*.json")) +
            list(self.handoff_dir.glob("handoff_*.json.gz")),
            key=lambda p: p.stat().st_mtime,
        )
        while len(remaining) > self.policy.max_bundles:
            oldest = remaining.pop(0)
            oldest.unlink()
            logger.info("[Handoff:Retention] Pruned over-cap bundle: %s", oldest.name)

    def _capture_workspace_diff(self) -> str:
        """Captures the current git diff --stat for inclusion in the bundle."""
        try:
            diff = subprocess.check_output(
                ["git", "diff", "--stat"],
                cwd=self.project_root,
                text=True,
                timeout=10,
            )
            return diff.strip() or "(no uncommitted changes)"
        except Exception:
            return "(git diff unavailable)"
