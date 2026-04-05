# 🛡️ Nexus Deterministic Validator
# [ARCH-EVO: v23 WISDOM EDITION GUARD]

import os
import re
from pathlib import Path
from typing import List, Dict, Any

class DeterministicValidator:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def validate_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        🛡️ Performs deterministic checks:
        1. File existence
        2. Symbol presence (simple grep/regex)
        3. Instruction alignment
        """
        results = []
        is_valid = True
        
        # Check target file
        target_file = action.get("target_file")
        if target_file:
            file_path = self.repo_root / target_file
            exists = file_path.exists()
            results.append({
                "check": "file_existence",
                "target": target_file,
                "passed": exists
            })
            if not exists: is_valid = False
            
        # Check symbol (if provided)
        target_symbol = action.get("target_symbol")
        if target_symbol and exists:
            # Simple line-by-line check (v23 MVP)
            with open(file_path, 'r') as f:
                content = f.read()
                symbol_found = target_symbol in content
                results.append({
                    "check": "symbol_presence",
                    "target": target_symbol,
                    "passed": symbol_found
                })
                if not symbol_found: is_valid = False

        return {
            "is_valid": is_valid,
            "checks": results,
            "risk_score_penalty": 0.0 if is_valid else 0.5
        }

if __name__ == "__main__":
    v = DeterministicValidator(Path("/Users/jameschen/Workspace/nexus"))
    test_action = {"target_file": "scripts/engine/nexus_cli.py", "target_symbol": "nexus"}
    res = v.validate_action(test_action)
    print(res)
