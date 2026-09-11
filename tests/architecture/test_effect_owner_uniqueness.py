"""Architectural regression coverage for effect-owner uniqueness across critical Nexus physical effects.

Issue #947:
Proves that each critical physical effect has exactly one canonical physical sink,
while permitting multiple compatibility callers that delegate to that sink.
Fails loudly if a synthetic or real second physical implementation is introduced,
naming the conflicting symbols and files in the failure message.

This test is pure regression verification:
- Test/report only; NO runtime routing authority.
- Generated inventory reports only label entries: CANONICAL, COMPATIBILITY_ONLY, RETIRED.
- Classification is strictly SINGLE_EFFECT_OWNER.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

# Allowed entry classifications per Issue #947 Acceptance Criteria
EntryLabel = Literal["CANONICAL", "COMPATIBILITY_ONLY", "RETIRED"]
Classification = Literal["SINGLE_EFFECT_OWNER"]


@dataclass(frozen=True)
class EffectSink:
    module_path: str  # Relative to repo root, e.g. "nexus/orchestrator/github_completion_loop.py"
    class_name: str | None  # None for module-level functions
    symbol_name: str  # Function or method name
    label: EntryLabel = "CANONICAL"


@dataclass(frozen=True)
class EffectCaller:
    module_path: str
    class_name: str | None
    symbol_name: str
    label: EntryLabel = "COMPATIBILITY_ONLY"


@dataclass(frozen=True)
class ProtectedEffectSpec:
    effect_id: str
    description: str
    canonical_sink: EffectSink
    allowed_callers: tuple[EffectCaller, ...]
    classification: Classification = "SINGLE_EFFECT_OWNER"


# Registry of critical physical effects and their canonical sinks
PROTECTED_EFFECT_SPECS: tuple[ProtectedEffectSpec, ...] = (
    ProtectedEffectSpec(
        effect_id="protected_github_merge",
        description="Protected GitHub PR merge CAS execution core",
        canonical_sink=EffectSink(
            module_path="nexus/orchestrator/github_completion_loop.py",
            class_name="GitHubCompletionPort",
            symbol_name="cas_merge",
            label="CANONICAL",
        ),
        allowed_callers=(
            EffectCaller(
                module_path="nexus/orchestrator/github_completion_loop.py",
                class_name="GitHubCompletionLoop",
                symbol_name="reconcile_and_advance",
                label="COMPATIBILITY_ONLY",
            ),
        ),
        classification="SINGLE_EFFECT_OWNER",
    ),
    ProtectedEffectSpec(
        effect_id="candidate_integration",
        description="Local candidate integration into git-tracked branch",
        canonical_sink=EffectSink(
            module_path="nexus/orchestrator/self_hosted_task_service.py",
            class_name="SelfHostedTaskService",
            symbol_name="integrate_approved",
            label="CANONICAL",
        ),
        allowed_callers=(
            EffectCaller(
                module_path="nexus/orchestrator/unified_mcp_gateway.py",
                class_name="UnifiedMCPGateway",
                symbol_name="_candidate_integrate",
                label="COMPATIBILITY_ONLY",
            ),
            EffectCaller(
                module_path="nexus/orchestrator/self_hosted_mcp.py",
                class_name="SelfHostedMCP",
                symbol_name="_call_tool",
                label="COMPATIBILITY_ONLY",
            ),
        ),
        classification="SINGLE_EFFECT_OWNER",
    ),
    ProtectedEffectSpec(
        effect_id="gateway_durable_deployment_recovery",
        description="Gateway durable deployment and recovery manager seam",
        canonical_sink=EffectSink(
            module_path="scripts/ops/mcp_gateway_durable.py",
            class_name=None,
            symbol_name="manage_gateway",
            label="CANONICAL",
        ),
        allowed_callers=(
            EffectCaller(
                module_path="scripts/ops/mcp_gateway_durable.py",
                class_name=None,
                symbol_name="dispatch_gateway_cli",
                label="COMPATIBILITY_ONLY",
            ),
            EffectCaller(
                module_path="scripts/ops/mcp_gateway_durable.py",
                class_name=None,
                symbol_name="main",
                label="COMPATIBILITY_ONLY",
            ),
        ),
        classification="SINGLE_EFFECT_OWNER",
    ),
    ProtectedEffectSpec(
        effect_id="standing_grant_transition",
        description="Standing grant task card authority transition CAS sink",
        canonical_sink=EffectSink(
            module_path="nexus/orchestrator/standing_grant_store.py",
            class_name=None,
            symbol_name="_write_transition_file",
            label="CANONICAL",
        ),
        allowed_callers=(
            EffectCaller(
                module_path="nexus/orchestrator/standing_grant_store.py",
                class_name=None,
                symbol_name="switch_task_card_authority",
                label="COMPATIBILITY_ONLY",
            ),
            EffectCaller(
                module_path="nexus/orchestrator/standing_grant_store.py",
                class_name=None,
                symbol_name="restore_task_card_authority",
                label="COMPATIBILITY_ONLY",
            ),
        ),
        classification="SINGLE_EFFECT_OWNER",
    ),
)


def _find_symbol_in_ast(
    tree: ast.AST,
    *,
    class_name: str | None,
    symbol_name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Locate a function or method definition in an AST tree."""
    if class_name is None:
        for node in tree.body if hasattr(tree, "body") else []:
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == symbol_name
            ):
                return node
        return None

    # Search within the specified class
    for node in tree.body if hasattr(tree, "body") else []:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == symbol_name
                ):
                    return item
    return None


def _find_all_sinks_matching(
    root_dir: Path,
    search_paths: list[str],
    symbol_name: str,
) -> list[tuple[str, str | None, str]]:
    """Scan search paths for any definition matching symbol_name.
    Returns a list of (file_relative_path, class_name_or_None, symbol_name).
    """
    found: list[tuple[str, str | None, str]] = []
    for rel_path in search_paths:
        full_path = root_dir / rel_path if not Path(rel_path).is_absolute() else Path(rel_path)
        if not full_path.is_file():
            continue
        try:
            tree = ast.parse(full_path.read_text(encoding="utf-8"), filename=str(full_path))
        except Exception:
            continue

        for node in tree.body:
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == symbol_name
            ):
                found.append((rel_path, None, symbol_name))
            elif isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if (
                        isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and sub.name == symbol_name
                    ):
                        found.append((rel_path, node.name, symbol_name))
    return found


def _caller_delegates_to_sink(
    caller_node: ast.AST,
    canonical_sink_name: str,
    authorized_delegators: set[str],
) -> bool:
    """Check if caller calls the canonical sink directly or through an authorized delegator."""
    for child in ast.walk(caller_node):
        if isinstance(child, ast.Call):
            func = child.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name == canonical_sink_name or (name and name in authorized_delegators):
                return True
    return False


def verify_effect_owner_uniqueness(
    spec: ProtectedEffectSpec,
    *,
    repo_root: Path,
    candidate_modules: list[str] | None = None,
) -> dict[str, Any]:
    """Verify that a protected effect has exactly one canonical sink and all callers delegate."""
    # 1. Verify canonical sink exists
    sink_file = repo_root / spec.canonical_sink.module_path
    if not sink_file.is_file():
        raise AssertionError(
            f"CANONICAL_SINK_MISSING: Canonical sink module not found for '{spec.effect_id}': "
            f"file '{spec.canonical_sink.module_path}' does not exist"
        )

    try:
        tree = ast.parse(sink_file.read_text(encoding="utf-8"), filename=str(sink_file))
    except Exception as exc:
        raise AssertionError(
            f"CANONICAL_SINK_UNPARSEABLE: Failed to parse '{spec.canonical_sink.module_path}': {exc}"
        ) from exc

    sink_node = _find_symbol_in_ast(
        tree,
        class_name=spec.canonical_sink.class_name,
        symbol_name=spec.canonical_sink.symbol_name,
    )
    if sink_node is None:
        target = (
            f"{spec.canonical_sink.class_name}.{spec.canonical_sink.symbol_name}"
            if spec.canonical_sink.class_name
            else spec.canonical_sink.symbol_name
        )
        raise AssertionError(
            f"CANONICAL_SINK_SYMBOL_NOT_FOUND: Symbol '{target}' missing in '{spec.canonical_sink.module_path}'. "
            "Renames/refactors must deliberately update the effect specification."
        )

    # 2. Check for duplicate sink implementations across candidate modules
    if candidate_modules is None:
        candidate_modules = [
            "nexus/orchestrator/github_completion_loop.py",
            "nexus/orchestrator/self_hosted_task_service.py",
            "nexus/orchestrator/unified_mcp_gateway.py",
            "nexus/orchestrator/standing_grant_store.py",
            "scripts/ops/mcp_gateway_durable.py",
        ]

    matched_sinks = _find_all_sinks_matching(
        repo_root, candidate_modules, spec.canonical_sink.symbol_name
    )

    # Filter out the declared canonical sink
    duplicates = [
        s
        for s in matched_sinks
        if not (s[0] == spec.canonical_sink.module_path and s[1] == spec.canonical_sink.class_name)
    ]
    if duplicates:
        conflict_list = [f"{d[0]}:{d[1] + '.' if d[1] else ''}{d[2]}" for d in duplicates]
        canonical_id = f"{spec.canonical_sink.module_path}:{spec.canonical_sink.class_name + '.' if spec.canonical_sink.class_name else ''}{spec.canonical_sink.symbol_name}"
        raise AssertionError(
            f"DUPLICATE_EFFECT_SINK_DETECTED: Protected effect '{spec.effect_id}' violates SINGLE_EFFECT_OWNER! "
            f"Canonical sink is '{canonical_id}', but conflicting implementations found: {conflict_list}"
        )

    # 3. Verify allowed callers delegate to the canonical sink
    authorized_names = {c.symbol_name for c in spec.allowed_callers}
    for caller in spec.allowed_callers:
        caller_file = repo_root / caller.module_path
        if not caller_file.is_file():
            continue
        try:
            caller_tree = ast.parse(
                caller_file.read_text(encoding="utf-8"), filename=str(caller_file)
            )
        except Exception as exc:
            raise AssertionError(f"CALLER_UNPARSEABLE: {caller.module_path}: {exc}") from exc

        caller_node = _find_symbol_in_ast(
            caller_tree,
            class_name=caller.class_name,
            symbol_name=caller.symbol_name,
        )
        if caller_node is not None:
            delegates = _caller_delegates_to_sink(
                caller_node,
                canonical_sink_name=spec.canonical_sink.symbol_name,
                authorized_delegators=authorized_names,
            )
            if not delegates:
                caller_id = f"{caller.module_path}:{caller.class_name + '.' if caller.class_name else ''}{caller.symbol_name}"
                raise AssertionError(
                    f"UNDELEGATED_CALLER_DETECTED: Caller '{caller_id}' does not delegate to canonical sink "
                    f"'{spec.canonical_sink.symbol_name}'."
                )

    return {
        "effect_id": spec.effect_id,
        "classification": spec.classification,
        "canonical_sink": f"{spec.canonical_sink.module_path}:{spec.canonical_sink.class_name + '.' if spec.canonical_sink.class_name else ''}{spec.canonical_sink.symbol_name}",
        "allowed_callers": [
            f"{c.module_path}:{c.class_name + '.' if c.class_name else ''}{c.symbol_name}"
            for c in spec.allowed_callers
        ],
        "status": "VERIFIED_SINGLE_EFFECT_OWNER",
    }


def generate_effect_inventory_report() -> dict[str, Any]:
    """Generate a machine-readable inventory report adhering strictly to Issue #947 schema."""
    allowed_labels = {"CANONICAL", "COMPATIBILITY_ONLY", "RETIRED"}
    entries: list[dict[str, Any]] = []

    for spec in PROTECTED_EFFECT_SPECS:
        # Canonical sink entry
        sink_label = spec.canonical_sink.label
        if sink_label not in allowed_labels:
            raise ValueError(f"Invalid label {sink_label!r} for canonical sink")
        entries.append({
            "effect_id": spec.effect_id,
            "target": f"{spec.canonical_sink.module_path}:{spec.canonical_sink.class_name + '.' if spec.canonical_sink.class_name else ''}{spec.canonical_sink.symbol_name}",
            "role": "canonical_sink",
            "label": sink_label,
            "classification": spec.classification,
        })

        # Allowed callers entries
        for caller in spec.allowed_callers:
            caller_label = caller.label
            if caller_label not in allowed_labels:
                raise ValueError(f"Invalid label {caller_label!r} for caller")
            entries.append({
                "effect_id": spec.effect_id,
                "target": f"{caller.module_path}:{caller.class_name + '.' if caller.class_name else ''}{caller.symbol_name}",
                "role": "allowed_caller",
                "label": caller_label,
                "classification": spec.classification,
            })

    return {
        "schema": "nexus.architecture_effect_owner_inventory.v1",
        "effect_count": len(PROTECTED_EFFECT_SPECS),
        "classification": "SINGLE_EFFECT_OWNER",
        "entries": entries,
    }


# ==============================================================================
# PYTEST TEST CASES
# ==============================================================================


def test_each_protected_effect_has_single_canonical_sink():
    """AC1: Prove each critical protected effect resolves to exactly one canonical physical sink."""
    repo_root = Path(__file__).resolve().parents[2]
    for spec in PROTECTED_EFFECT_SPECS:
        result = verify_effect_owner_uniqueness(spec, repo_root=repo_root)
        assert result["status"] == "VERIFIED_SINGLE_EFFECT_OWNER"
        assert result["classification"] == "SINGLE_EFFECT_OWNER"


def test_synthetic_duplicate_merge_sink_fails(tmp_path):
    """AC2 & AC4: Adding a synthetic second merge implementation makes the test fail and names conflicting symbols."""
    fake_code = "class FakeMergeAdapter:\n    def cas_merge(self, **kwargs):\n        pass\n"
    fake_file = tmp_path / "fake_merge.py"
    fake_file.write_text(fake_code, encoding="utf-8")

    spec = PROTECTED_EFFECT_SPECS[0]  # protected_github_merge
    repo_root = Path(__file__).resolve().parents[2]

    try:
        verify_effect_owner_uniqueness(
            spec,
            repo_root=repo_root,
            candidate_modules=[spec.canonical_sink.module_path, str(fake_file)],
        )
        assert False, "Verification should have failed on duplicate merge sink"
    except AssertionError as exc:
        msg = str(exc)
        assert "DUPLICATE_EFFECT_SINK_DETECTED" in msg
        assert "FakeMergeAdapter.cas_merge" in msg
        assert "protected_github_merge" in msg


def test_synthetic_duplicate_integration_sink_fails(tmp_path):
    """AC2 & AC4: Adding a synthetic second candidate integration sink fails and names the conflict."""
    fake_code = "class RogueTaskHost:\n    def integrate_approved(self, **kwargs):\n        pass\n"
    fake_file = tmp_path / "rogue_integration.py"
    fake_file.write_text(fake_code, encoding="utf-8")

    spec = PROTECTED_EFFECT_SPECS[1]  # candidate_integration
    repo_root = Path(__file__).resolve().parents[2]

    try:
        verify_effect_owner_uniqueness(
            spec,
            repo_root=repo_root,
            candidate_modules=[spec.canonical_sink.module_path, str(fake_file)],
        )
        assert False, "Verification should have failed on duplicate integration sink"
    except AssertionError as exc:
        msg = str(exc)
        assert "DUPLICATE_EFFECT_SINK_DETECTED" in msg
        assert "RogueTaskHost.integrate_approved" in msg
        assert "candidate_integration" in msg


def test_synthetic_duplicate_gateway_recovery_fails(tmp_path):
    """AC2 & AC4: Adding a synthetic second gateway recovery manager seam fails and names the conflict."""
    fake_code = "def manage_gateway(action, **kwargs):\n    return {'duplicate': True}\n"
    fake_file = tmp_path / "rogue_gateway.py"
    fake_file.write_text(fake_code, encoding="utf-8")

    spec = PROTECTED_EFFECT_SPECS[2]  # gateway_durable_deployment_recovery
    repo_root = Path(__file__).resolve().parents[2]

    try:
        verify_effect_owner_uniqueness(
            spec,
            repo_root=repo_root,
            candidate_modules=[spec.canonical_sink.module_path, str(fake_file)],
        )
        assert False, "Verification should have failed on duplicate gateway recovery seam"
    except AssertionError as exc:
        msg = str(exc)
        assert "DUPLICATE_EFFECT_SINK_DETECTED" in msg
        assert "manage_gateway" in msg
        assert "gateway_durable_deployment_recovery" in msg


def test_synthetic_duplicate_standing_grant_transition_fails(tmp_path):
    """AC2 & AC4: Adding a synthetic second standing grant transition sink fails and names the conflict."""
    fake_code = "def _write_transition_file(path, payload):\n    pass\n"
    fake_file = tmp_path / "rogue_transition.py"
    fake_file.write_text(fake_code, encoding="utf-8")

    spec = PROTECTED_EFFECT_SPECS[3]  # standing_grant_transition
    repo_root = Path(__file__).resolve().parents[2]

    try:
        verify_effect_owner_uniqueness(
            spec,
            repo_root=repo_root,
            candidate_modules=[spec.canonical_sink.module_path, str(fake_file)],
        )
        assert False, "Verification should have failed on duplicate transition sink"
    except AssertionError as exc:
        msg = str(exc)
        assert "DUPLICATE_EFFECT_SINK_DETECTED" in msg
        assert "_write_transition_file" in msg
        assert "standing_grant_transition" in msg


def test_rename_or_missing_sink_fails_loudly():
    """AC4: Renaming/missing a canonical sink fails loudly and demands explicit inventory update."""
    broken_spec = ProtectedEffectSpec(
        effect_id="protected_github_merge",
        description="test",
        canonical_sink=EffectSink(
            module_path="nexus/orchestrator/github_completion_loop.py",
            class_name="GitHubCompletionPort",
            symbol_name="nonexistent_merge_sink",
        ),
        allowed_callers=(),
    )
    repo_root = Path(__file__).resolve().parents[2]
    try:
        verify_effect_owner_uniqueness(broken_spec, repo_root=repo_root)
        assert False, "Expected failure when canonical sink is missing"
    except AssertionError as exc:
        assert "CANONICAL_SINK_SYMBOL_NOT_FOUND" in str(exc)
        assert "nonexistent_merge_sink" in str(exc)


def test_inventory_report_labels_strict_conformance():
    """AC5: Generated inventory report only labels CANONICAL, COMPATIBILITY_ONLY, RETIRED."""
    report = generate_effect_inventory_report()
    assert report["schema"] == "nexus.architecture_effect_owner_inventory.v1"
    assert report["classification"] == "SINGLE_EFFECT_OWNER"
    assert report["effect_count"] == 4

    valid_labels = {"CANONICAL", "COMPATIBILITY_ONLY", "RETIRED"}
    for entry in report["entries"]:
        assert entry["label"] in valid_labels
        assert entry["classification"] == "SINGLE_EFFECT_OWNER"
        assert ":" in entry["target"]


def test_undelegated_caller_fails(tmp_path):
    """AC3 & AC4: A caller that re-implements physical logic instead of delegating to canonical sink fails loudly."""
    fake_caller_code = (
        "class RogueCaller:\n"
        "    def rogue_call(self):\n"
        "        return 'direct_bypass_without_calling_canonical_sink'\n"
    )
    fake_caller_file = tmp_path / "rogue_caller.py"
    fake_caller_file.write_text(fake_caller_code, encoding="utf-8")

    spec = ProtectedEffectSpec(
        effect_id="protected_github_merge",
        description="test undelegated caller",
        canonical_sink=EffectSink(
            module_path="nexus/orchestrator/github_completion_loop.py",
            class_name="GitHubCompletionPort",
            symbol_name="cas_merge",
        ),
        allowed_callers=(
            EffectCaller(
                module_path=str(fake_caller_file),
                class_name="RogueCaller",
                symbol_name="rogue_call",
            ),
        ),
    )
    repo_root = Path(__file__).resolve().parents[2]
    try:
        verify_effect_owner_uniqueness(spec, repo_root=repo_root)
        assert False, "Expected failure when caller does not delegate"
    except AssertionError as exc:
        assert "UNDELEGATED_CALLER_DETECTED" in str(exc)
        assert "RogueCaller.rogue_call" in str(exc)
        assert "cas_merge" in str(exc)
