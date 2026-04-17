import re
import json
from pathlib import Path
from typing import Tuple, Dict, Any

class SafetyClassifier:
    """🛡️ Nexus Safety Classifier: Risk-aware command evaluation."""
    
    def __init__(self, project_root: Path):
        self.root = project_root
        self.policy_path = project_root / "configs" / "ask_policy.yaml"
        self.load_policy()

    def load_policy(self):
        import yaml
        if self.policy_path.exists():
            self.policy = yaml.safe_load(self.policy_path.read_text(encoding="utf-8"))
        else:
            self.policy = {}

    def classify(self, command: str) -> Tuple[str, float, str]:
        """
        Classifies a command's risk level.
        Returns: (Level, Score, Reason)
        Levels: SAFE, CAUTION, DANGEROUS
        """
        # 1. Destructive Pattern Check (Regex-based) - HARD BLOCK
        for p in self.policy.get("destructive_patterns", []):
            if re.search(p, command):
                return "DANGEROUS", 1.0, f"Matched destructive pattern: {p}"

        # 2. Credential/Sensitive Data Check
        for p in self.policy.get("credential_patterns", []):
            if re.search(p, command):
                return "DANGEROUS", 0.9, f"Matched sensitive pattern: {p}"

        # 3. Safe Allowlist (Implicitly safe read commands)
        safe_commands = ["git status", "ls ", "cat ", "grep ", "find ", "uv run scripts/engine/nexus_cli.py nexus status"]
        if any(command.startswith(sc) for sc in safe_commands):
            return "SAFE", 0.1, "Common read-only command"

        # 4. Contextual Analysis (Placeholder for LLM-based logic)
        # In a real v24 implementation, we might call back to Gemini for a 100ms risk check.
        return "CAUTION", 0.5, "Unknown command type, requires cautious execution"

    def is_auto_approvable(self, command: str) -> bool:
        level, score, _ = self.classify(command)
        return level == "SAFE" or (level == "CAUTION" and score < 0.4)
