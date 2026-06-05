import inspect
import json
import re
from typing import Any, Dict

class Planner:
    def __init__(self, ollama_generate_fn: Any = None):
        self.ollama_generate = ollama_generate_fn

    def _generate(
        self,
        system: str,
        prompt: str,
        *,
        model_name: str | None = None,
        timeout_seconds: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        if not model_name:
            return self.ollama_generate(system, prompt)
        try:
            sig = inspect.signature(self.ollama_generate)
            kwargs = {}
            if "model" in sig.parameters:
                kwargs["model"] = model_name
            if "timeout" in sig.parameters and timeout_seconds is not None:
                kwargs["timeout"] = timeout_seconds
            if "options" in sig.parameters and options is not None:
                kwargs["options"] = options
            if kwargs:
                return self.ollama_generate(system, prompt, **kwargs)
        except (TypeError, ValueError):
            pass
        return self.ollama_generate(system, prompt)

    def create_plan(
        self,
        problem: str,
        evidence: str,
        *,
        model_name: str | None = None,
        timeout_seconds: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict:
        if not self.ollama_generate:
            # Fallback for unit tests if needed
            return {
                "search_symbols": [],
                "repair_strategy": "General repair.",
                "violated_invariants": []
            }

        prompt = f"""
You are a software architect. Analyze the bug report and reproduction evidence to create a repair plan.
Output a JSON object with:
1. "search_symbols": List of critical class/function names likely involved.
2. "repair_strategy": A concise step-by-step strategy.
3. "violated_invariants": List of semantic or algebraic invariants that are broken.

Bug Report:
{problem}

Reproduction Evidence:
{evidence}

JSON Output:
"""
        response = self._generate("", prompt, model_name=model_name, timeout_seconds=timeout_seconds, options=options)
        try:
            # 提取 JSON
            match = re.search(r"(\{.*\})", response, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            return {"search_symbols": [], "repair_strategy": response, "violated_invariants": []}
        except Exception:
            return {"search_symbols": [], "repair_strategy": "Failed to parse plan", "violated_invariants": []}
