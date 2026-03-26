import re
import sys
from typing import Dict, Any, List, Optional

class L6AuditError(Exception):
    """Raised when L6 Audit fails validation."""
    pass

class L6AuditParser:
    """Parses and validates the [L6_AUDIT] block from Nexus output."""
    
    # Required keys in the audit block
    REQUIRED_KEYS = [
        "backward_compat_risk",
        "blast_radius",
        "stakeholders",
        "prod_artifacts",
        "trade_offs"
    ]

    @staticmethod
    def parse(content: str) -> Dict[str, Any]:
        """Extracts the [L6_AUDIT] block and parses its fields."""
        match = re.search(r"\[L6_AUDIT\](.*?)(?=\n\[|\n#|\Z)", content, re.DOTALL)
        if not match:
            return {}
        
        block = match.group(1).strip()
        data = {}
        
        # Parse simple key-value pairs
        # Expected format: - key: value
        lines = block.split('\n')
        curr_key = None
        
        for line in lines:
            line = line.strip()
            if line.startswith("- "):
                parts = line[2:].split(':', 1)
                if len(parts) == 2:
                    curr_key = parts[0].strip().lower()
                    data[curr_key] = parts[1].strip()
                else:
                    # In case of sub-bullets or multi-line (simple approach)
                    pass
        
        return data

    @classmethod
    def validate(cls, audit_data: Dict[str, Any], content: str):
        """Validates the logic and presence of the audit block."""
        if not audit_data:
            raise L6AuditError("Missing [L6_AUDIT] block in output.")

        # 1. Check required top-level keys
        for key in cls.REQUIRED_KEYS:
            if key not in audit_data:
                raise L6AuditError(f"Missing required [L6_AUDIT] field: {key}")

        # 2. Logic: High risk or Trade-offs MUST mention human approval in the text
        risk = audit_data.get("backward_compat_risk", "").lower()
        trade_offs = audit_data.get("trade_offs", "").lower()
        
        needs_approval = "requires human approval" in content.lower()
        
        if ("high" in risk or "none" not in trade_offs) and not needs_approval:
            raise L6AuditError(
                "High risk or Trade-offs detected without mandatory 'requires human approval' tag."
            )
            
        # 3. Artifact checking
        artifacts = audit_data.get("prod_artifacts", "").lower()
        valid_artifacts = ["rollback", "stress_test", "blue_green", "blue_green_deploy"]
        if not any(art in artifacts for art in valid_artifacts):
            raise L6AuditError(
                "Invalid prod_artifacts. Must specify at least one of: rollback, stress_test, blue_green"
            )

    @staticmethod
    def check_consistency(audit_data: Dict[str, Any], pub_api_diff: List[str]):
        """Cross-checks the audit data against the actual AST diff."""
        risk = audit_data.get("backward_compat_risk", "").lower()
        
        if pub_api_diff and ("low" in risk or "none" in risk):
            diff_summary = "\n".join(pub_api_diff)
            raise L6AuditError(
                f"L6 CROSS-CHECK FAILURE: Audit claims Low/None risk, but AST Diff detected breaking changes:\n{diff_summary}"
            )

if __name__ == "__main__":
    # Self-test block
    test_content = """
[L6_AUDIT]
- backward_compat_risk: Low
- blast_radius: Local
- stakeholders: None
- prod_artifacts: rollback
- trade_offs: None
    """
    try:
        data = L6AuditParser.parse(test_content)
        print(f"Parsed Data: {data}")
        L6AuditParser.validate(data, test_content)
        print("Validation Passed.")
    except Exception as e:
        print(f"Validation Failed: {e}")
        sys.exit(1)
