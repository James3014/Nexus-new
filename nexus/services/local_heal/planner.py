import inspect
import json
import re
from typing import Any, Dict

from nexus.services.local_heal.llm_client import ILLMClient, OllamaLLMClient

class Planner:
    def __init__(self, ollama_generate_fn: Any = None, llm_client: ILLMClient | None = None):
        if llm_client:
            self.llm_client = llm_client
        elif ollama_generate_fn:
            self.llm_client = OllamaLLMClient(ollama_generate_fn)
        else:
            self.llm_client = None

    def _generate(
        self,
        system: str,
        prompt: str,
        *,
        model_name: str | None = None,
        timeout_seconds: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        if not self.llm_client:
            return ""
        return self.llm_client.generate(
            system_prompt=system,
            user_prompt=prompt,
            model=model_name or "qwen2.5-coder:7b",
            timeout=timeout_seconds,
            options=options
        )

    def create_plan(
        self,
        problem: str,
        evidence: str,
        *,
        model_name: str | None = None,
        timeout_seconds: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict:
        if not self.llm_client:
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
