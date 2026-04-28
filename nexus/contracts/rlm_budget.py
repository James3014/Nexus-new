from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RLMBudget:
    """Hard limits for a Nexus-governed recursive reasoning loop."""

    max_iterations: int = 0
    max_llm_calls: int = 0
    max_tool_calls: int = 0
    max_output_chars: int = 0
    wall_clock_budget_sec: int = 0

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if int(value) < 0:
                raise ValueError(f"{name} must be >= 0")

    def to_dict(self) -> dict[str, int]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, int]) -> "RLMBudget":
        return cls(**payload)


@dataclass(frozen=True)
class RLMBudgetState:
    """Immutable consumption snapshot for a recursive reasoning loop."""

    budget: RLMBudget
    iterations: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    output_chars: int = 0
    wall_clock_sec: int = 0

    @classmethod
    def from_budget(cls, budget: RLMBudget) -> "RLMBudgetState":
        return cls(budget=budget)

    def consume(
        self,
        *,
        iterations: int = 0,
        llm_calls: int = 0,
        tool_calls: int = 0,
        output_chars: int = 0,
        wall_clock_sec: int = 0,
    ) -> "RLMBudgetState":
        return RLMBudgetState(
            budget=self.budget,
            iterations=self.iterations + int(iterations),
            llm_calls=self.llm_calls + int(llm_calls),
            tool_calls=self.tool_calls + int(tool_calls),
            output_chars=self.output_chars + int(output_chars),
            wall_clock_sec=self.wall_clock_sec + int(wall_clock_sec),
        )

    @property
    def exhausted_reasons(self) -> list[str]:
        checks = [
            ("max_iterations", self.budget.max_iterations, self.iterations),
            ("max_llm_calls", self.budget.max_llm_calls, self.llm_calls),
            ("max_tool_calls", self.budget.max_tool_calls, self.tool_calls),
            ("max_output_chars", self.budget.max_output_chars, self.output_chars),
            ("wall_clock_budget_sec", self.budget.wall_clock_budget_sec, self.wall_clock_sec),
        ]
        return [name for name, limit, used in checks if limit > 0 and used >= limit]

    @property
    def exhausted(self) -> bool:
        return bool(self.exhausted_reasons)

    @property
    def remaining(self) -> dict[str, int]:
        return {
            "max_iterations": self._remaining(self.budget.max_iterations, self.iterations),
            "max_llm_calls": self._remaining(self.budget.max_llm_calls, self.llm_calls),
            "max_tool_calls": self._remaining(self.budget.max_tool_calls, self.tool_calls),
            "max_output_chars": self._remaining(self.budget.max_output_chars, self.output_chars),
            "wall_clock_budget_sec": self._remaining(self.budget.wall_clock_budget_sec, self.wall_clock_sec),
        }

    @staticmethod
    def _remaining(limit: int, used: int) -> int:
        if limit <= 0:
            return 0
        return max(0, limit - used)

    def to_dict(self) -> dict[str, object]:
        return {
            "budget": self.budget.to_dict(),
            "iterations": self.iterations,
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "output_chars": self.output_chars,
            "wall_clock_sec": self.wall_clock_sec,
            "exhausted": self.exhausted,
            "exhausted_reasons": self.exhausted_reasons,
            "remaining": self.remaining,
        }

