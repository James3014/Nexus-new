#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Tuple, Any


class NexusEvidenceGuard:
    """
    🕵️ Nexus v25.7 終極一致性對抗護衛 (Interlocked)
    紅隊修正：禁止私自發起 subprocess，必須透過受控 Git Hub。
    """

    def __init__(self, project_root: Path, git_hub: Any = None):
        self.project_root = project_root
        self.git_hub = git_hub
        self.evidence_path = project_root / ".nexus" / "state" / "nexus_physical_evidence.json"

    def audit_claim(self, claim_summary: str, task_id: str) -> Tuple[bool, str]:
        if not self.evidence_path.exists():
            return False, "🛑 [REJECTED] Missing evidence package."

        try:
            with open(self.evidence_path, "r") as f:
                evidence = json.load(f)
        except Exception:
            return False, "🛑 [REJECTED] Evidence corrupted."

        issues = []
        if evidence.get("task_id") != task_id:
            issues.append(f"Task ID Mismatch: {evidence.get('task_id')} != {task_id}")

        # Always enforce physical + semantic checks for PASS claims.
        diff = ""
        if self.git_hub:
            _, diff = self.git_hub.get_changes("staged")

        if not diff or not diff.strip():
            issues.append("Empty Change Set: No valid diff detected for PASS claim.")
        else:
            keywords = [w.lower() for w in task_id.split() if len(w) > 3]
            if keywords and not any(k in diff.lower() for k in keywords):
                issues.append(f"Semantic Drift: Diff does not relate to task keywords {keywords}")

        if issues:
            return False, "\n".join(issues)
        return True, "✅ [VERIFIED-v25.7]"
