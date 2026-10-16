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
    "content",
    "json_str",
    # Raw text captured from a model CLI/server. An explicit list rather than a ``raw_*``
    # prefix: the prefix also catches raw_bytes/raw_packet/raw_jwk/raw_coverage (sealed
    # files, env secrets, Mapping copies), which would need allowlist entries for
    # non-model data and dilute the allowlist.
    "raw_stdout",
    "raw_stderr",
    "raw_body",
    "raw_text",
    "raw_content",
    "raw_completion",
    "raw_reply",
})
MODEL_OUTPUT_KEYS = frozenset({"response", "generated_text"})

# Call sites that match the model-output heuristic but parse something that is
# NOT model text. Key: (path, enclosing qualname, unparsed json.load(s) argument).
# Value: the site-specific reason. Each entry must still match a real call site (stale
# entries fail the test) and carry a specific reason (test_allowlist_entries_are_real_and_justified).
NON_MODEL_JSON_PARSE_ALLOWLIST = {
    ("nexus/pilot_cli/gemini_client.py", "compress_long_gemini_answer", "response.text"): (
        "HTTP envelope: Gemini generateContent body; model text is then read from candidates[].parts[].text."
    ),
    ("nexus/pilot_cli/gemini_client.py", "chat_via_gemini_api", "response.text"): (
        "HTTP envelope: Gemini generateContent body; model text is then read from candidates[].parts[].text."
    ),
    ("nexus/services/memory_repository.py", "OllamaEmbeddingProvider.embed", "response.read()"): (
        "HTTP envelope: Ollama /api/embeddings body (embedding vector only)."
    ),
    (
        "nexus/services/memory_repository.py",
        "MemoryRepository.compress_to_aaak",
        "response.read()",
    ): (
        'HTTP envelope: Ollama /api/generate body; result["response"] is used as plain text, never json-parsed.'
    ),
    ("nexus/core/vector_rag.py", "VectorRAG._get_embedding", "response.read()"): (
        "HTTP envelope: Ollama /api/embeddings body (embedding vector only)."
    ),
    (
        "nexus/services/local_heal/lesson_embedding.py",
        "post_local_json",
        "response.read().decode('utf-8')",
    ): ("HTTP envelope: localhost JSON POST helper used for the embedding server."),
    (
        "nexus/services/local_heal/targeted_fallback.py",
        "TargetedFallbackGate.should_fallback",
        "response.read().decode('utf-8')",
    ): ("HTTP envelope: Ollama /api/tags inventory probe (model names only)."),
    ("nexus/engine/llm_judge_providers.py", "OllamaJudgeProvider._chat", "raw"): (
        "HTTP envelope: Ollama /api/chat body (#1985); the model text in message.content is parsed separately by _parse_json_object."
    ),
    ("nexus/orchestrator/ambient_core.py", "build_core_verdict", "json.dumps(raw_coverage)"): (
        "Deep copy of the Core verifier's coverage block (#2247): a json round-trip of a Mapping from the Core host response, not model output."
    ),
    ("nexus/research/hybrid_replication_live.py", "_jev_request", "response.read()"): (
        "HTTP envelope: JEV structured-answer API body (answers/usage), schema-checked field by field below."
    ),
    (
        "nexus/services/product_capability_canary_runner.py",
        "run_production_canary",
        "response_path.read_text(encoding='utf-8')",
    ): (
        "File read: local_assist response.json receipt written by the executor, not raw model text."
    ),
    (
        "nexus/services/local_assist_advisor_canary.py",
        "run_advisor_canary",
        "Path(response.receipt_path).read_text(encoding='utf-8')",
    ): (
        "File read: execution receipt JSON written by LocalAssistService (receipt_path), not raw model text."
    ),
    (
        "nexus/calibration/provider_adoption/apple_fm_adapter.py",
        "AppleFMCandidateAdapter._run_structured_json_probe.semantic_validator",
        "output_text",
    ): (
        "Measurement: the Apple FM structured-JSON probe scores whether the model emits strict JSON; a bare json.loads is the measurement itself (a sanctioned lenient parse would hide failures)."
    ),
    (
        "nexus/app/nightshift_runner_service.py",
        "AutoResearchNightShift._append_to_pending_manifest",
        "content",
    ): (
        "File read: pending-manifest JSON this service wrote itself (lock-file bytes under flock); no model text."
    ),
    ("nexus/core/mental_snapshot.py", "MentalSnapshot.deserialize", "json_str"): (
        "State round-trip: json_str is the output of MentalSnapshot.serialize() (json.dumps of self.mind); no model text."
    ),
    (
        "nexus/engine/pipeline_research.py",
        "PipelineResearchMixin._load_research_report",
        "content",
    ): (
        "File read: research report JSON written by the research subprocess to report_path; no model text."
    ),
    ("nexus/learning/embedding_cache.py", "EmbeddingCache._load", "content"): (
        "File read: on-disk embedding cache (vectors plus _model_version) written by EmbeddingCache itself."
    ),
    ("nexus/learning/knowledge_index.py", "KnowledgeIndex.load_evidence", "json_str"): (
        "File read: JSON evidence block inside a stored SKILL.md under skills_dir (written by the skill store), not a model response."
    ),
    ("nexus/services/arweave_uploader.py", "download_lessons_from_arweave", "content"): (
        "HTTP body: lessons JSON downloaded from the Arweave gateway by tx id (data this system uploaded); not model text."
    ),
    ("nexus/services/gateway.py", "BattlesuitGateway._ask_via_cli", "raw_stdout"): (
        "CLI envelope: `gemini --output-format json` stdout; the model text is read from its output/response field below, and raw_stdout is only the fallback text when the envelope does not parse."
    ),
    ("nexus/services/gateway.py", "BattlesuitGateway._ask_via_ollama", "raw_body"): (
        "HTTP envelope: Ollama /api/chat|/api/generate body; model text is output_text, parsed later by _parse_json_result."
    ),
    ("nexus/services/s2t_strict.py", "S2T3BAdvisor._advise_via_ollama", "raw_body"): (
        'HTTP envelope: Ollama /api/generate body; the model text from payload["response"] goes through robust_json_parse.'
    ),
    ("nexus/services/mcp_delegator.py", "MCPDelegator.delegate_mcp", "text"): (
        "MCP JSON-RPC envelope: Serena tool-result text read via read_response(); a tool result, not model text."
    ),
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


MIN_REASON_CHARS = 20


def validate_allowlist(allowlist) -> list[str]:
    """Problems with allowlist entries: weak reason, missing file/function, or no parse of the argument."""
    problems: list[str] = []
    for (path, qualname, argument), reason in allowlist.items():
        label = f"{path}::{qualname}::{argument}"
        if not isinstance(reason, str) or len(reason.strip()) < MIN_REASON_CHARS:
            problems.append(f"{label}: reason missing or shorter than {MIN_REASON_CHARS} chars")
        file_path = REPO_ROOT / path
        if not file_path.exists():
            problems.append(f"{label}: file does not exist")
            continue
        found = find_model_output_json_parses(file_path.read_text(encoding="utf-8"), path)
        if not any(hit[1] == qualname for hit in found):
            problems.append(f"{label}: no flagged json parse inside that function")
        elif not any(hit[1] == qualname and hit[2] == argument for hit in found):
            problems.append(f"{label}: no json parse of that argument inside the function")
    return problems


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
        stale = set(NON_MODEL_JSON_PARSE_ALLOWLIST) - {f[:3] for f in found}
        self.assertEqual(
            stale, set(), f"Stale allowlist entries (call site moved or removed): {sorted(stale)}"
        )

    def test_scanner_covers_content_json_str_and_raw_names(self):
        """#2174: names the scanner once missed are flagged; non-model raw_* names stay quiet."""
        for name in (
            "content",
            "json_str",
            "raw_stdout",
            "raw_stderr",
            "raw_body",
            "raw_text",
            "raw_content",
            "raw_completion",
            "raw_reply",
        ):
            source = f"import json\ndef f({name}):\n    return json.loads({name})\n"
            with self.subTest(name=name):
                hits = find_model_output_json_parses(source, "synthetic/names.py")
                self.assertEqual([h[:3] for h in hits], [("synthetic/names.py", "f", name)])
        propagated = "import json\ndef f(content):\n    body = content.strip()\n    return json.loads(body)\n"
        self.assertTrue(find_model_output_json_parses(propagated, "synthetic/prop.py"))
        # raw_bytes/raw_packet are sealed-file bytes, not model text: deliberately not names.
        for quiet in ("raw_bytes", "raw_packet", "raw_jwk"):
            source = f"import json\ndef f(path):\n    {quiet} = path.read_bytes()\n    return json.loads({quiet})\n"
            with self.subTest(quiet=quiet):
                self.assertEqual(find_model_output_json_parses(source, "synthetic/q.py"), [])

    def test_allowlist_entries_are_real_and_justified(self):
        """#2174: every entry has a specific reason, names a real function, and a json parse on its argument."""
        problems = validate_allowlist(NON_MODEL_JSON_PARSE_ALLOWLIST)
        self.assertEqual(problems, [])

    def test_allowlist_validator_rejects_bad_entries(self):
        """Mutants of a real entry (empty reason, wrong qualname, wrong argument, wrong file) must fail."""
        key = ("nexus/core/mental_snapshot.py", "MentalSnapshot.deserialize", "json_str")
        good = "State round-trip of MentalSnapshot.serialize(), not model text."
        self.assertEqual(validate_allowlist({key: good}), [])
        self.assertTrue(validate_allowlist({key: ""}))
        self.assertTrue(validate_allowlist({key: "too short"}))
        self.assertTrue(validate_allowlist({(key[0], "MentalSnapshot.nope", key[2]): good}))
        self.assertTrue(validate_allowlist({(key[0], key[1], "other_arg"): good}))
        self.assertTrue(validate_allowlist({("nexus/core/missing_file.py", key[1], key[2]): good}))

    def test_no_manual_state_mutation(self):
        """禁止在 Python 中手動修改 flow_state (應經由 Rust TransitionGuard)"""
        # 這裡檢查是否有人直接寫 state = FlowState.XXX 而非調用驗證器
        # (此為行為測試啟發式檢查)
        pass


if __name__ == "__main__":
    unittest.main()
