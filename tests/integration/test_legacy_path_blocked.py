import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# The sanctioned seam: raw model text is parsed only inside these modules.
SANCTIONED_MODULES = frozenset({
    "nexus/contracts/model_output_json.py",
    "nexus/engine/semantic_adapter.py",
    "nexus/engine/governance_bridge.py",
})

# A value is "model output" when its name says it is a model response
# (identifier tokens split on "_"), when it is one of the conventional raw
# model-text names, or when it is read from the generation field of a model
# server envelope. Taint then propagates through assignments in the scope.
MODEL_OUTPUT_NAME_TOKENS = frozenset({"response", "completion", "completions", "llm"})
MODEL_OUTPUT_NAMES = frozenset({
    "model_output",
    "raw_output",
    "raw_model_output",
    "output_text",
    "generated_text",
})
MODEL_OUTPUT_KEYS = frozenset({"response", "generated_text"})

# Call sites that match the model-output heuristic but parse something that is
# NOT model text. Key: (path, enclosing qualname, unparsed json.load(s) argument).
# Each entry must still match a real call site (stale entries fail the test).
NON_MODEL_JSON_PARSE_ALLOWLIST = {
    # HTTP envelope: Gemini generateContent body; model text is then read from candidates[].parts[].text.
    ("nexus/pilot_cli/gemini_client.py", "compress_long_gemini_answer", "response.text"),
    ("nexus/pilot_cli/gemini_client.py", "chat_via_gemini_api", "response.text"),
    # HTTP envelope: Ollama /api/embeddings body (embedding vector only).
    ("nexus/services/memory_repository.py", "OllamaEmbeddingProvider.embed", "response.read()"),
    # HTTP envelope: Ollama /api/generate body; result["response"] is used as plain text, never json-parsed.
    ("nexus/services/memory_repository.py", "MemoryRepository.compress_to_aaak", "response.read()"),
    # HTTP envelope: Ollama /api/embeddings body (embedding vector only).
    ("nexus/core/vector_rag.py", "VectorRAG._get_embedding", "response.read()"),
    # HTTP envelope: localhost JSON POST helper used for the embedding server.
    (
        "nexus/services/local_heal/lesson_embedding.py",
        "post_local_json",
        "response.read().decode('utf-8')",
    ),
    # HTTP envelope: Ollama /api/tags inventory probe (model names only).
    (
        "nexus/services/local_heal/targeted_fallback.py",
        "TargetedFallbackGate.should_fallback",
        "response.read().decode('utf-8')",
    ),
    # HTTP envelope: Ollama /api/chat body (#1985); the model text in message.content
    # is parsed separately by _parse_json_object.
    ("nexus/engine/llm_judge_providers.py", "OllamaJudgeProvider._chat", "raw"),
    # Deep copy of the Core verifier's coverage block (#2247): a json round-trip of a
    # Mapping from the Core host response, not model output.
    ("nexus/orchestrator/ambient_core.py", "build_core_verdict", "json.dumps(raw_coverage)"),
    # HTTP envelope: JEV structured-answer API body (answers/usage), schema-checked field by field below.
    ("nexus/research/hybrid_replication_live.py", "_jev_request", "response.read()"),
    # File read: local_assist response.json receipt written by the executor, not raw model text.
    (
        "nexus/services/product_capability_canary_runner.py",
        "run_production_canary",
        "response_path.read_text(encoding='utf-8')",
    ),
    # Measurement: the Apple FM structured-JSON probe scores whether the model emits strict JSON;
    # a bare json.loads is the measurement itself (a sanctioned lenient parse would hide failures).
    (
        "nexus/calibration/provider_adoption/apple_fm_adapter.py",
        "AppleFMCandidateAdapter._run_structured_json_probe.semantic_validator",
        "output_text",
    ),
    # MCP JSON-RPC envelope: Serena tool-result text read via read_response(); a tool result, not model text.
    ("nexus/services/mcp_delegator.py", "MCPDelegator.delegate_mcp", "text"),
}


def _name_tokens(identifier: str) -> set[str]:
    return {token for token in identifier.lower().split("_") if token}


def _json_aliases(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Return (names bound to the json module, names bound to json.load/json.loads)."""
    modules: set[str] = set()
    functions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "json":
                    modules.add(alias.asname or "json")
        elif isinstance(node, ast.ImportFrom) and node.module == "json":
            for alias in node.names:
                if alias.name in {"load", "loads"}:
                    functions.add(alias.asname or alias.name)
    return modules, functions


def _is_json_parse_call(node: ast.AST, modules: set[str], functions: set[str]) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in {"load", "loads"}:
        return isinstance(func.value, ast.Name) and func.value.id in modules
    return isinstance(func, ast.Name) and func.id in functions


def _scope_nodes(scope: ast.AST):
    """Yield nodes of one scope without descending into nested defs/classes/lambdas."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _is_model_output_name(identifier: str) -> bool:
    return identifier in MODEL_OUTPUT_NAMES or bool(
        _name_tokens(identifier) & MODEL_OUTPUT_NAME_TOKENS
    )


def _references_model_output(expr: ast.AST, tainted: set[str]) -> bool:
    for node in ast.walk(expr):
        if isinstance(node, ast.Name) and (node.id in tainted or _is_model_output_name(node.id)):
            return True
        if isinstance(node, ast.Attribute) and _is_model_output_name(node.attr):
            return True
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in MODEL_OUTPUT_KEYS
        ):
            return True
    return False


def _bound_names(target: ast.AST) -> set[str]:
    return {node.id for node in ast.walk(target) if isinstance(node, ast.Name)}


def _tainted_names(scope: ast.AST) -> set[str]:
    """Names in this scope whose value flows from model output (fixed point over assignments)."""
    tainted: set[str] = set()
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        params = [*scope.args.posonlyargs, *scope.args.args, *scope.args.kwonlyargs]
        tainted = {arg.arg for arg in params if _is_model_output_name(arg.arg)}
    bindings: list[tuple[set[str], ast.AST]] = []
    for node in _scope_nodes(scope):
        if isinstance(node, ast.Assign):
            names = set().union(*(_bound_names(t) for t in node.targets))
            bindings.append((names, node.value))
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            bindings.append((_bound_names(node.target), node.value))
        elif isinstance(node, ast.NamedExpr):
            bindings.append((_bound_names(node.target), node.value))
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            bindings.append((_bound_names(node.target), node.iter))
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            bindings.append((_bound_names(node.optional_vars), node.context_expr))
    changed = True
    while changed:
        changed = False
        for names, value in bindings:
            if not names <= tainted and _references_model_output(value, tainted):
                tainted |= names
                changed = True
    return tainted


def find_model_output_json_parses(source: str, rel_path: str) -> list[tuple[str, str, str, int]]:
    """Return (path, qualname, argument, line) for json.load(s) applied to model-output values."""
    tree = ast.parse(source, filename=rel_path)
    modules, functions = _json_aliases(tree)
    if not modules and not functions:
        return []
    findings: list[tuple[str, str, str, int]] = []

    def visit(scope: ast.AST, qualname: str) -> None:
        tainted = _tainted_names(scope)
        for node in _scope_nodes(scope):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                visit(node, f"{qualname}.{node.name}" if qualname else node.name)
            elif _is_json_parse_call(node, modules, functions):
                call = node
                assert isinstance(call, ast.Call)
                args = [*call.args, *(kw.value for kw in call.keywords if kw.arg in {"s", "fp"})]
                if args and _references_model_output(args[0], tainted):
                    findings.append((
                        rel_path,
                        qualname or "<module>",
                        ast.unparse(args[0]),
                        call.lineno,
                    ))

    visit(tree, "")
    return findings


class TestLegacyPathBlocked(unittest.TestCase):
    """
    [NEXUS v26] TDD Phase B: Legacy Path Blocked Tests
    檢測代碼庫中是否仍殘留「模型直出完整 JSON」或「json.loads 治理判斷」的路徑。
    """

    def test_no_json_loads_on_model_response(self):
        """禁止直接對模型回應進行 json.loads (應使用 nexus.contracts.model_output_json / SemanticAdapter.parse_json_object)"""
        # Negative controls: the detector must flag model-output parses ...
        flagged_controls = {
            "direct": "import json\ndef f(model_response):\n    return json.loads(model_response)\n",
            "propagated": (
                "import json\ndef f(response):\n    cleaned = response.strip()\n    return json.loads(cleaned)\n"
            ),
            "envelope_field": "import json\ndef f(body):\n    payload = json.loads(body)\n"
            "    return json.loads(payload['response'])\n",
            "aliased": "from json import loads as parse\ndef f(raw_output):\n    return parse(raw_output)\n",
        }
        for label, source in flagged_controls.items():
            with self.subTest(control=label):
                self.assertTrue(
                    find_model_output_json_parses(source, f"synthetic/{label}.py"), label
                )
        # ... and leave plain file reads alone.
        file_read = (
            "import json\ndef f(path):\n    with open(path) as fh:\n        return json.load(fh)\n"
        )
        self.assertEqual(find_model_output_json_parses(file_read, "synthetic/file_read.py"), [])

        files_to_check = sorted(REPO_ROOT.glob("nexus/**/*.py")) + [
            REPO_ROOT / "run_1_simulator.py"
        ]
        found: list[tuple[str, str, str, int]] = []
        for file_path in files_to_check:
            rel_path = file_path.relative_to(REPO_ROOT).as_posix()
            if rel_path in SANCTIONED_MODULES or not file_path.exists():
                continue
            found.extend(
                find_model_output_json_parses(file_path.read_text(encoding="utf-8"), rel_path)
            )

        violations = [f for f in found if f[:3] not in NON_MODEL_JSON_PARSE_ALLOWLIST]
        self.assertEqual(
            violations,
            [],
            f"Legacy path detected: {violations}. Use nexus.contracts.model_output_json (SemanticAdapter.parse_json_object) instead.",
        )
        stale = NON_MODEL_JSON_PARSE_ALLOWLIST - {f[:3] for f in found}
        self.assertEqual(
            stale, set(), f"Stale allowlist entries (call site moved or removed): {sorted(stale)}"
        )

    def test_no_manual_state_mutation(self):
        """禁止在 Python 中手動修改 flow_state (應經由 Rust TransitionGuard)"""
        # 這裡檢查是否有人直接寫 state = FlowState.XXX 而非調用驗證器
        # (此為行為測試啟發式檢查)
        pass


if __name__ == "__main__":
    unittest.main()
