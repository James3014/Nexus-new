import inspect
import json
import re
from typing import Any, Dict, List

from nexus.services.local_heal.llm_client import ILLMClient, OllamaLLMClient


class DeterministicSymbolExtractor:
    """
    P0-5: Deterministic symbol extraction from issue description.
    Replaces LLM planning for symbol identification — eliminates hallucinated
    symbol names that poison BM25 localization.
    Based on: Agentless (2024), AutoCodeRover (2024) approaches.
    """

    # Patterns for Python identifiers in issue text
    _BACKTICK_IDENT = re.compile(r'`([A-Za-z_][A-Za-z0-9_.]*)`')
    _TRACEBACK_FUNC = re.compile(r'(?:in |File "[^"]+", line \d+, in )([A-Za-z_][A-Za-z0-9_]*)')
    _DOTTED_PATH = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]+)+)\b')
    _CAMEL_WORDS = re.compile(r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b')  # CamelCase class names

    # Noise tokens to filter out
    _NOISE = frozenset({
        'python', 'error', 'traceback', 'none', 'true', 'false', 'self',
        'import', 'return', 'class', 'def', 'int', 'str', 'list', 'dict',
        'tuple', 'set', 'type', 'any', 'bool', 'float', 'print',
        'django', 'auth', 'contrib', 'models', 'fields', 'db', 'utils', 'test',
        'validator', 'validators', 'username', 'user'
    })

    @classmethod
    def extract(cls, problem_statement: str, evidence: str = "") -> List[str]:
        """Extract high-confidence symbol names deterministically."""
        text = problem_statement + "\n" + evidence
        candidates = set()

        # 1. Backtick identifiers: `ClassName.method` — highest confidence
        for m in cls._BACKTICK_IDENT.finditer(text):
            raw = m.group(1)
            # Add both the dotted path and the final component
            candidates.add(raw.split(".")[-1])
            if "." in raw:
                candidates.add(raw.split(".")[0])

        # 2. Traceback function names
        for m in cls._TRACEBACK_FUNC.finditer(text):
            name = m.group(1)
            if len(name) > 2:
                candidates.add(name)

        # 3. CamelCase class names in prose
        for m in cls._CAMEL_WORDS.finditer(text):
            candidates.add(m.group(1))

        # 4. Dotted module paths (first component = likely module/class)
        for m in cls._DOTTED_PATH.finditer(text):
            parts = m.group(1).split(".")
            if len(parts) >= 2:
                candidates.add(parts[0])
                candidates.add(parts[-1])

        # Filter noise + very short tokens
        result = [
            s for s in candidates
            if s.lower() not in cls._NOISE and len(s) >= 3
        ]
        return sorted(result)[:15]  # Cap at 15 to avoid BM25 dilution


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
    ) -> "RepairPlan":
        from nexus.services.local_heal.interface import RepairPlan
        # P0-5: Always seed with deterministic symbols first (no hallucinations)
        det_symbols = DeterministicSymbolExtractor.extract(problem, evidence)

        if not self.llm_client:
            return RepairPlan(
                search_symbols=det_symbols,
                repair_strategy="Deterministic symbol extraction (no LLM).",
                violated_invariants=[]
            )

        prompt = f"""You are a software architect. Analyze the bug report and output a compact JSON repair plan.
Output ONLY valid JSON with:
1. "search_symbols": List of critical class/function names likely involved (Python identifiers only).
2. "repair_strategy": One concise sentence describing the fix.
3. "violated_invariants": List of broken invariants (or empty list).

Bug Report:
{problem[:2000]}

Reproduction Evidence:
{evidence[:1000]}

JSON Output:
"""
        response = self._generate("", prompt, model_name=model_name, timeout_seconds=timeout_seconds, options=options)
        try:
            match = re.search(r"(\{.*\})", response, re.DOTALL)
            if match:
                parsed = json.loads(match.group(1))
                # P0-5: Merge deterministic symbols with LLM symbols, dedup
                llm_syms = parsed.get("search_symbols", [])
                merged = list(dict.fromkeys(det_symbols + [s for s in llm_syms if isinstance(s, str)]))[:15]
                return RepairPlan(
                    search_symbols=merged,
                    repair_strategy=parsed.get("repair_strategy", "Apply surgical fix."),
                    violated_invariants=parsed.get("violated_invariants", [])
                )
            
            # LLM failed to produce JSON — use deterministic baseline
            return RepairPlan(
                search_symbols=det_symbols,
                repair_strategy=response[:500] if response else "Apply fix per issue description.",
                violated_invariants=[]
            )
        except Exception:
            return RepairPlan(
                search_symbols=det_symbols,
                repair_strategy="Apply fix per issue description.",
                violated_invariants=[]
            )
