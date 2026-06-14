from pathlib import Path
from typing import List, Callable

class ReasoningRouter:
    """
    🛡️ Dynamic Reasoning Router
    Decouples domain-specific rules for selecting LLM reasoning modes.
    Modes: FAST (deterministic), INTUITIVE (light LLM), ALGEBRAIC (heavy reasoning)
    """
    def __init__(self, default_mode: str = "INTUITIVE"):
        self.default_mode = default_mode
        self._rules: List[Callable[[str, Path], str | None]] = []
        
        # Rule 1: Simple bug fixes → FAST (deterministic extraction, no LLM)
        # Covers: import errors, missing imports, simple typos, naming issues
        self.register_rule(
            lambda stmt, path: "FAST" if any(
                kw in stmt.lower()
                for kw in [
                    "add import", "missing import", "import error",
                    "fix typo", "rename", "add ", "remove ",
                    "missing ", "unused ",
                ]
            ) and len(stmt) < 200 else None
        )
        
        # Rule 2: Algebraic/scientific domains → ALGEBRAIC
        self.register_rule(
            lambda stmt, path: "ALGEBRAIC" if any(
                kw in stmt.lower() or kw in str(path).lower() 
                for kw in ["astropy", "sympy", "numpy", "scipy"]
            ) else None
        )

    def register_rule(self, rule: Callable[[str, Path], str | None]) -> None:
        """Register a custom routing rule."""
        self._rules.append(rule)

    def route(self, problem_statement: str, repo_dir: Path) -> str:
        """Evaluate rules in order to decide the reasoning mode."""
        for rule in self._rules:
            mode = rule(problem_statement, repo_dir)
            if mode:
                return mode
        return self.default_mode
