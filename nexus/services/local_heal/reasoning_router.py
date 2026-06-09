from pathlib import Path
from typing import List, Callable

class ReasoningRouter:
    """
    🛡️ Dynamic Reasoning Router
    Decouples domain-specific rules for selecting LLM reasoning modes.
    """
    def __init__(self, default_mode: str = "INTUITIVE"):
        self.default_mode = default_mode
        self._rules: List[Callable[[str, Path], str | None]] = []
        
        # Register default algebraic rule (e.g., astropy, sympy)
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
