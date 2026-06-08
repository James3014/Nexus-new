import json
from typing import Dict, Any, Optional

class AuditRejectionReceipt:
    HARD_REJECT_CLASSES = {"test_regression_risk", "semantic_incomplete", "api_breakage", "security_risk", "syntax_error"}
    def __init__(self, data: Dict[str, Any]):
        self.rejection_class = data.get("rejection_class", "unknown")
        self.minimal_counterexample = data.get("minimal_counterexample", "")
        self.repair_constraint = data.get("repair_constraint", "")
        self.forbidden_repeat_signature = data.get("forbidden_repeat_signature", "")
        self.raw_data = data
    def is_hard_reject(self): return self.rejection_class.lower() in self.HARD_REJECT_CLASSES
    def to_json(self): return json.dumps(self.raw_data, ensure_ascii=False)
    @classmethod
    def from_json(cls, s): return cls(json.loads(s))
    def format_as_constraint_prompt(self):
        return f"### [Previous Round Audit Feedback]\n- REJECTION CLASS: {self.rejection_class}\n- COUNTEREXAMPLE: {self.minimal_counterexample}\n- CONSTRAINT: {self.repair_constraint}\n"
