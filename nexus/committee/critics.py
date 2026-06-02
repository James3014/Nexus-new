from typing import List, Optional
from nexus.committee.models import CriticVerdict
import ast

class BaseCritic:
    def evaluate(self, candidate_id: str, content: str) -> CriticVerdict:
        raise NotImplementedError

class SyntaxCritic(BaseCritic):
    """🛠️ Task T4: Syntax Critic"""
    def evaluate(self, candidate_id: str, content: str) -> CriticVerdict:
        try:
            ast.parse(content)
            return CriticVerdict("syntax", candidate_id, True, 1.0, "AST_PARSE_OK")
        except SyntaxError as e:
            return CriticVerdict("syntax", candidate_id, False, 0.0, f"SYNTAX_ERROR: {str(e)}", "SYNTAX_INVALID")

class ContractCritic(BaseCritic):
    """🛠️ Task T5: Contract Critic"""
    def evaluate(self, candidate_id: str, payload: dict) -> CriticVerdict:
        required = ["root_cause", "target_modules"]
        missing = [f for f in required if f not in payload]
        if not missing:
            return CriticVerdict("contract", candidate_id, True, 1.0, "CONTRACT_SATISFIED")
        return CriticVerdict("contract", candidate_id, False, 0.0, f"MISSING_FIELDS: {missing}", "CONTRACT_VIOLATION")
