"""Step 0 guards for splitting the two orchestrator big files (Issue #2434).

``nexus/orchestrator/self_hosted_task_service.py`` (SHTS) and
``nexus/orchestrator/unified_mcp_gateway.py`` (GW) are being split into
``*_parts`` packages behind facades that keep the original module paths.  These
tests pin what the facades must keep exposing while code moves:

* the import / patch-target name surface used by importers and tests;
* the class member tables (name, ``inspect.getattr_static`` kind, signature) of
  ``SelfHostedTaskService`` and ``UnifiedMCPGateway`` (JSON fixture);
* ``UnifiedMCPGateway.tool_specs`` and the ``ACTION_CONTRACT_TOP_LEVEL_CONSTANTS``
  stay direct members of the GW file, because ``_action_contract_digest`` hashes
  only that file's AST;
* every ``*_parts`` module is imported eagerly enough to be frozen into the
  gateway's ``RUNTIME_SOURCE_PATHS`` (freshness drift detection);
* no test patches ``facade.X`` while a part module calls ``X`` by bare name (such a
  patch would silently stop taking effect), unless allowlisted.

Regenerate the member-table fixture after an intentional class change with::

    python tests/architecture/test_bigfile_split_surface.py --write
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
import subprocess
import sys
import warnings
from pathlib import Path
from types import ModuleType
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = REPO_ROOT / "nexus" / "orchestrator"
TESTS_ROOT = REPO_ROOT / "tests"
SHTS_MODULE = "nexus.orchestrator.self_hosted_task_service"
GW_MODULE = "nexus.orchestrator.unified_mcp_gateway"
SHTS_SOURCE = ORCHESTRATOR / "self_hosted_task_service.py"
GW_SOURCE = ORCHESTRATOR / "unified_mcp_gateway.py"
PARTS_DIRS: dict[str, Path] = {
    SHTS_MODULE: ORCHESTRATOR / "self_hosted_task_service_parts",
    GW_MODULE: ORCHESTRATOR / "unified_mcp_gateway_parts",
}
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bigfile_split_class_tables.json"
CLASSES: tuple[tuple[str, str], ...] = (
    (SHTS_MODULE, "SelfHostedTaskService"),
    (GW_MODULE, "UnifiedMCPGateway"),
)

# Names non-test importers, tests and module-path patches use on the SHTS facade.
SHTS_SURFACE: tuple[str, ...] = (
    # non-test importers
    "CANONICAL_SOURCE_ROOT",
    "SelfHostedTaskService",
    "resolve_contract_identity",
    "resolve_lifecycle_identity",
    "validate_task_card_binding",
    "resolve_canonical_target_roots",
    "validate_workforce_dispatch_binding",
    "DEFAULT_MAXIMUM_ATTEMPTS_PER_TASK",
    "_retry_request",
    "_workforce_dispatch_inputs",
    "_recover_pre_provider_cli_envelope_drift",
    "build_canonical_dispatch_envelope",
    "canonical_request_hash",
    "CandidateVerifier",
    "WorktreeManager",
    "SelfHostedDevelopmentController",
    "TERMINAL_STATUSES",
    "DURABLE_SELF_HOSTED_STATUSES",
    "INVALID_STATE_STATUSES",
    # test imports
    "_LEGACY_V1_NEGATIVE_OMISSION_SET",
    "_terminal_retry_inherited_worktree_time_allowed",
    "_terminal_retry_pre_provider_state_allowed",
    "_terminal_retry_verifier_static_failure_allowed",
    "_validate_project_entry_authority_binding",
    "_validated_action_request",
    "resolve_execution_lane",
    "check_fast_lane_eligible",
    "validate_lifecycle_revision",
    "_fail_to_pass_blocked",
    "mutation_domains_conflict",
    "_sha256_json",
    # module-path patch targets
    "ControlledIntegrationManager",
    "_temporary_state_roots",
    "CandidateCommitter",
    "time",
    "NexusEventBus",
    "evaluate_runtime_workforce_admission",
    "_terminal_retry_released_lease_proof",
    "_repository_root_from_git",
)

# Names scripts, tests and module-path patches use on the GW facade.
GW_SURFACE: tuple[str, ...] = (
    "UnifiedMCPGateway",
    "GatewayInputError",
    "PUBLIC_TOOL_NAMES",
    "TOOL_MANIFEST_REVISION",
    "FULL_TOOL_SCHEMA_HASH",
    "PERMISSION_POLICY",
    "PERMISSION_POLICY_HASH",
    "PERMISSION_POLICY_REVISION",
    "LIFECYCLE_REVISION",
    "LIFECYCLE_STATE_SCHEMA_REVISION",
    "TASK_CONTRACT_REVISION",
    "GATEWAY_NAME",
    "GATEWAY_VERSION",
    "PUBLIC_APP_NAME",
    "SERVER_INSTANCE_ID",
    "SERVER_STARTED_AT",
    "SERVER_REPO_HEAD_AT_START",
    "LOADED_SOURCE_ROOT",
    "FRESHNESS_SEMANTICS_REVISION",
    "RUNTIME_SOURCE_PATHS",
    "ACTION_CONTRACT_TOP_LEVEL_CONSTANTS",
    "ACTION_CONTRACT_SHA256_AT_START",
    "PERMISSION_ENFORCEMENT_SHA256_AT_START",
    "_compile_agy_command",
    "_action_contract_digest",
    "_action_contract_fingerprint",
    "_evaluate_freshness",
    "_evaluate_upstream_freshness",
    "_hash_source_paths",
    "_permission_enforcement_fingerprint",
    "_default_observe_upstream_main",
    "MAX_SEARCH_FILE_BYTES",
    "MAX_SEARCH_LINE_BYTES",
    "MAX_SEARCH_RESULTS",
    "_bounded_rg_matches",
    "_display_search_path",
    "_git_ls_files",
    "_python_literal_search",
    "_run_rg_literal_search",
    "_terminate_and_reap_search_process",
    "gateway_core_provenance",
    "observe_github_issue",
    # module-path patch targets
    "_git",
    "CANONICAL_SOURCE_ROOT",
    "CONTROLLER_IS_SEPARATE",
    "CONTROLLER_BINDING_PROBLEM",
    "bound_controller_problem",
    "resolve_registered_provider_executable",
    "get_account_pool_manager",
    "CrossProcessLeaseCoordinator",
    "pre_action_guard",
    "_receipt_only_main_movement",
    "evaluate_execution_readiness",
    "_resolve_github_cli",
    "build_canonical_planner_admission",
    "authorize_durable_standing_grant_effect",
    "_gateway_recovery_manager",
    "execute_canonical_product_task",
    "apply_learning_policy_effect",
)

ACTION_CONTRACT_CONSTANTS = frozenset({
    "PERMISSION_POLICY",
    "PERMISSION_POLICY_REVISION",
    "TASK_CONTRACT_REVISION",
    "LIFECYCLE_REVISION",
    "LIFECYCLE_STATE_SCHEMA_REVISION",
})

# (test file relative to the repo root, facade module, patched name) triples that are
# known to patch ``facade.X`` while a part calls ``X`` by bare name, and whose patch
# was verified to still take effect (for example because the test also patches the
# part module).  Add an entry only together with that verification.
STALE_PATCH_ALLOWLIST: frozenset[tuple[str, str, str]] = frozenset()

_PATCH_CALLEES = frozenset({"setattr", "delattr", "patch", "object"})


def _import(name: str) -> ModuleType:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return importlib.import_module(name)


# ---------------------------------------------------------------------------
# member tables


def _annotation_text(annotation: Any) -> str:
    if isinstance(annotation, str):
        return annotation
    return str(getattr(annotation, "__qualname__", None) or repr(annotation))


def _default_text(default: Any) -> str:
    if isinstance(default, (set, frozenset)):
        return f"{type(default).__name__}({sorted(repr(item) for item in default)})"
    return repr(default)


def _signature_text(value: Any) -> str:
    signature = inspect.signature(value)
    rendered: list[str] = []
    for parameter in signature.parameters.values():
        text = f"{parameter.kind.name}:{parameter.name}"
        if parameter.annotation is not inspect.Parameter.empty:
            text += f": {_annotation_text(parameter.annotation)}"
        if parameter.default is not inspect.Parameter.empty:
            text += f" = {_default_text(parameter.default)}"
        rendered.append(text)
    returned = ""
    if signature.return_annotation is not inspect.Signature.empty:
        returned = f" -> {_annotation_text(signature.return_annotation)}"
    return f"({', '.join(rendered)}){returned}"


def _member_table(cls: type) -> dict[str, dict[str, str | None]]:
    """Every attribute the class or its non-object bases define (mixins included)."""

    names = {name for klass in cls.__mro__ if klass is not object for name in vars(klass)}
    table: dict[str, dict[str, str | None]] = {}
    for name in sorted(names):
        if name.startswith("__") and name != "__init__":
            continue
        static = inspect.getattr_static(cls, name)
        signature: str | None = None
        if isinstance(static, property):
            signature = _signature_text(static.fget) if static.fget is not None else None
        elif isinstance(static, (staticmethod, classmethod)) or inspect.isfunction(static):
            signature = _signature_text(getattr(cls, name))
        table[name] = {"kind": type(static).__name__, "signature": signature}
    return table


def _current_tables() -> dict[str, dict[str, dict[str, str | None]]]:
    return {
        f"{module}:{qualname}": _member_table(getattr(_import(module), qualname))
        for module, qualname in CLASSES
    }


def _write_fixture() -> None:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "nexus.bigfile_split_class_tables.v1",
        "regenerate": "python tests/architecture/test_bigfile_split_surface.py --write",
        "classes": _current_tables(),
    }
    FIXTURE.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# AST helpers


def _top_level_assigned(tree: ast.Module) -> set[str]:
    assigned: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        assigned.update(target.id for target in targets if isinstance(target, ast.Name))
    return assigned


def _top_level_bound(tree: ast.Module) -> set[str]:
    bound = _top_level_assigned(tree)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
    return bound


def _part_files(facade: str) -> list[Path]:
    directory = PARTS_DIRS[facade]
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.rglob("*.py") if "__pycache__" not in path.parts)


def _bare_global_uses(source: str) -> set[str]:
    """Top-level names of a part module that the part itself loads by bare name."""

    tree = ast.parse(source)
    loads = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    return loads & _top_level_bound(tree)


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return f"{head}.{node.attr}" if head else None
    return None


def _facade_aliases(tree: ast.AST, facades: tuple[str, ...]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in facades and alias.asname:
                    aliases[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for alias in node.names:
                full = f"{node.module}.{alias.name}"
                if full in facades:
                    aliases[alias.asname or alias.name] = full
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            callee = _dotted(node.value.func) or ""
            args = node.value.args
            if (
                callee.split(".")[-1] == "import_module"
                and args
                and isinstance(args[0], ast.Constant)
                and args[0].value in facades
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        aliases[target.id] = str(args[0].value)
    return aliases


def _patched_names(source: str, facades: tuple[str, ...]) -> set[tuple[str, str]]:
    """``(facade, name)`` pairs a test source patches as module attributes."""

    tree = ast.parse(source)
    aliases = _facade_aliases(tree, facades)
    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        callee = _dotted(node.func) or ""
        if callee.split(".")[-1] not in _PATCH_CALLEES:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            for facade in facades:
                if first.value.startswith(f"{facade}."):
                    found.add((facade, first.value[len(facade) + 1 :].split(".")[0]))
            continue
        target = _dotted(first)
        facade = aliases.get(target or "") or (target if target in facades else None)
        if facade is None or len(node.args) < 2:
            continue
        second = node.args[1]
        if isinstance(second, ast.Constant) and isinstance(second.value, str):
            found.add((facade, second.value))
    return found


def _stale_patches(
    test_sources: dict[str, str], part_sources: dict[str, dict[str, str]]
) -> list[tuple[str, str, str, str]]:
    """``(test, facade, name, part)`` where ``facade.name`` is patched but a part of that
    facade loads ``name`` by bare name, so the patch cannot reach the part."""

    bare = {
        facade: {part: _bare_global_uses(source) for part, source in parts.items()}
        for facade, parts in part_sources.items()
    }
    facades = tuple(part_sources)
    stale: list[tuple[str, str, str, str]] = []
    for test, source in sorted(test_sources.items()):
        for facade, name in sorted(_patched_names(source, facades)):
            for part, names in sorted(bare.get(facade, {}).items()):
                if name in names and (test, facade, name) not in STALE_PATCH_ALLOWLIST:
                    stale.append((test, facade, name, part))
    return stale


def _test_sources() -> dict[str, str]:
    sources: dict[str, str] = {}
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "self_hosted_task_service" in text or "unified_mcp_gateway" in text:
            sources[path.relative_to(REPO_ROOT).as_posix()] = text
    return sources


# ---------------------------------------------------------------------------
# tests


def test_shts_facade_name_surface_is_frozen() -> None:
    service = _import(SHTS_MODULE)
    missing = [name for name in SHTS_SURFACE if not hasattr(service, name)]
    assert missing == []
    worktree_manager = _import("nexus.orchestrator.worktree_manager")
    assert service.mutation_domains_conflict is worktree_manager.mutation_domains_conflict


def test_gateway_facade_name_surface_is_frozen() -> None:
    gateway = _import(GW_MODULE)
    missing = [name for name in GW_SURFACE if not hasattr(gateway, name)]
    assert missing == []
    assert gateway.PUBLIC_TOOL_NAMES == tuple(
        spec["name"] for spec in gateway.UnifiedMCPGateway.tool_specs()
    )


def test_class_member_tables_match_snapshot() -> None:
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))["classes"]
    current = _current_tables()
    assert sorted(current) == sorted(expected)
    for key in sorted(expected):
        removed = sorted(set(expected[key]) - set(current[key]))
        added = sorted(set(current[key]) - set(expected[key]))
        changed = sorted(
            name
            for name in set(expected[key]) & set(current[key])
            if expected[key][name] != current[key][name]
        )
        assert (removed, added, changed) == ([], [], []), (
            f"{key} member table drifted (removed, added, changed); if intentional run "
            "`python tests/architecture/test_bigfile_split_surface.py --write`"
        )


def test_member_table_snapshot_is_not_vacuous() -> None:
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))["classes"]
    service = expected[f"{SHTS_MODULE}:SelfHostedTaskService"]
    gateway = expected[f"{GW_MODULE}:UnifiedMCPGateway"]
    assert service["integrate_approved"]["kind"] == "function"
    assert service["__init__"]["signature"]
    assert gateway["tool_specs"]["kind"] == "staticmethod"
    assert gateway["_candidate_integrate"]["kind"] == "function"
    assert len(service) > 100 and len(gateway) > 50


def test_action_contract_members_stay_direct_members_of_gateway_file() -> None:
    gateway = _import(GW_MODULE)
    assert set(gateway.ACTION_CONTRACT_TOP_LEVEL_CONSTANTS) == ACTION_CONTRACT_CONSTANTS
    source = GW_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert ACTION_CONTRACT_CONSTANTS <= _top_level_assigned(tree)
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "UnifiedMCPGateway"
    ]
    assert len(classes) == 1
    direct = {
        member.name
        for member in classes[0].body
        if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "tool_specs" in direct
    assert "tool_specs" in vars(gateway.UnifiedMCPGateway)
    assert gateway._action_contract_digest(source)
    for path in _part_files(GW_MODULE):
        part_tree = ast.parse(path.read_text(encoding="utf-8"))
        assert _top_level_assigned(part_tree).isdisjoint(ACTION_CONTRACT_CONSTANTS), path
        defined = {
            node.name
            for node in ast.walk(part_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert "tool_specs" not in defined, path


def test_every_part_module_is_frozen_into_gateway_runtime_source_paths() -> None:
    probe = (
        "import json, warnings\n"
        "warnings.simplefilter('ignore')\n"
        f"import {GW_MODULE} as gateway\n"
        "print(json.dumps([str(path.resolve()) for path in gateway.RUNTIME_SOURCE_PATHS]))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    frozen = set(json.loads(completed.stdout.strip().splitlines()[-1]))
    # Non-vacuous today: both facades are themselves frozen at gateway start.
    assert str(GW_SOURCE.resolve()) in frozen
    assert str(SHTS_SOURCE.resolve()) in frozen
    missing = [
        path.relative_to(REPO_ROOT).as_posix()
        for facade in PARTS_DIRS
        for path in _part_files(facade)
        if str(path.resolve()) not in frozen
    ]
    assert missing == [], "part modules must be imported eagerly at facade top level"


def test_no_stale_facade_patches_against_part_modules() -> None:
    part_sources = {
        facade: {
            path.relative_to(REPO_ROOT).as_posix(): path.read_text(encoding="utf-8")
            for path in _part_files(facade)
        }
        for facade in PARTS_DIRS
    }
    assert _stale_patches(_test_sources(), part_sources) == []


def test_stale_patch_scanner_sees_current_patch_targets() -> None:
    patched: set[tuple[str, str]] = set()
    for source in _test_sources().values():
        patched |= _patched_names(source, tuple(PARTS_DIRS))
    assert (GW_MODULE, "_git") in patched
    assert (GW_MODULE, "_run_rg_literal_search") in patched
    assert (SHTS_MODULE, "WorktreeManager") in patched
    assert (SHTS_MODULE, "CANONICAL_SOURCE_ROOT") in patched


def test_stale_patch_guard_detects_bare_name_call_in_part() -> None:
    test_source = (
        "import nexus.orchestrator.unified_mcp_gateway as gateway_module\n"
        "from nexus.orchestrator import self_hosted_task_service as svc\n"
        "def test_x(monkeypatch):\n"
        "    monkeypatch.setattr(gateway_module, '_terminate', lambda: None)\n"
        "    monkeypatch.setattr('nexus.orchestrator.self_hosted_task_service.WorktreeManager', 1)\n"
        "    monkeypatch.setattr(svc, 'time', 2)\n"
    )
    part_sources = {
        GW_MODULE: {
            "gw_parts/search.py": "def _terminate():\n    pass\n\ndef run():\n    _terminate()\n"
        },
        SHTS_MODULE: {
            "shts_parts/late.py": (
                "import importlib\nimport time\n"
                "def _svc():\n    return importlib.import_module('x')\n"
                "def go():\n    _svc().WorktreeManager()\n    return time.time()\n"
            )
        },
    }
    stale = _stale_patches({"tests/test_x.py": test_source}, part_sources)
    assert stale == [
        ("tests/test_x.py", SHTS_MODULE, "time", "shts_parts/late.py"),
        ("tests/test_x.py", GW_MODULE, "_terminate", "gw_parts/search.py"),
    ]


def test_stale_patch_allowlist_entries_are_well_formed() -> None:
    for test, facade, name in STALE_PATCH_ALLOWLIST:
        assert (REPO_ROOT / test).is_file(), test
        assert facade in PARTS_DIRS, facade
        assert name.isidentifier(), name


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT))
    if sys.argv[1:] == ["--write"]:
        _write_fixture()
        print(FIXTURE)
    else:
        raise SystemExit("usage: python tests/architecture/test_bigfile_split_surface.py --write")
