"""The retired nexus-core-rs crate and its Python bridge stay deleted (#2359).

Owner decision A (2026-10-16): policies P-GATE-03 and P-FLOW-01 were retired and
nexus-core-rs/, nexus/bridge/rust_kernel.py and nexus/bridge/cutover_manager.py
were deleted. These tests make a re-add deliberate: any file under the crate
directory, either bridge module, an import of them from nexus/ or scripts/, or a
policy that names the crate again turns them red.
"""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RETIRED_TREE = "nexus-core-rs"
RETIRED_MODULES = ("nexus.bridge.rust_kernel", "nexus.bridge.cutover_manager")
RETIRED_FILES = ("nexus/bridge/rust_kernel.py", "nexus/bridge/cutover_manager.py")
# Everything the crate was made of, including manifests and data files. Cargo build
# output under target/ is ignored by .gitignore and is not checked.
SOURCE_SUFFIXES = {".rs", ".toml", ".lock", ".json", ".py", ".md", ".yaml", ".yml", ".sh"}
MANIFESTS = (
    "docs/reports/policy-manifest.v2.json",
    "docs/reports/policy-baseline-manifest.v1.json",
)
RETIRED_POLICIES = {"P-GATE-03", "P-FLOW-01"}


def _module_of(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        return [node.module] + [f"{node.module}.{alias.name}" for alias in node.names]
    if isinstance(node, ast.Call) and node.args:
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        first = node.args[0]
        if (
            name in {"import_module", "__import__"}
            and isinstance(first, ast.Constant)
            and isinstance(first.value, str)
        ):
            return [first.value]
    return []


def _imports_retired(node: ast.AST) -> bool:
    return any(
        module == retired or module.startswith(f"{retired}.")
        for module in _module_of(node)
        for retired in RETIRED_MODULES
    )


def test_retired_crate_tree_has_no_files() -> None:
    base = ROOT / RETIRED_TREE
    leftovers = [
        p.relative_to(ROOT).as_posix()
        for p in (base.rglob("*") if base.exists() else [])
        if p.is_file()
        and "target" not in p.relative_to(base).parts
        and (p.suffix in SOURCE_SUFFIXES or p.name in {"Cargo.toml", "Cargo.lock", "build.rs"})
    ]
    assert leftovers == [], "nexus-core-rs was deleted on 2026-10-16 (#2359)"


@pytest.mark.parametrize("rel", RETIRED_FILES)
def test_retired_bridge_file_is_absent(rel: str) -> None:
    assert not (ROOT / rel).exists(), rel


@pytest.mark.parametrize("module", RETIRED_MODULES)
def test_retired_bridge_module_is_not_importable(module: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)


def test_no_python_source_imports_the_retired_bridge() -> None:
    offenders: list[str] = []
    for top in ("nexus", "scripts"):
        for path in sorted((ROOT / top).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError, ValueError):
                continue
            if any(_imports_retired(node) for node in ast.walk(tree)):
                offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


@pytest.mark.parametrize("rel", MANIFESTS)
def test_policy_manifests_no_longer_name_the_crate(rel: str) -> None:
    manifest = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    assert {policy["policy_id"] for policy in manifest["policies"]}.isdisjoint(RETIRED_POLICIES)
    if rel.endswith("v2.json"):
        # The live manifest must not name the crate at all. The 2026-06-15 v1 baseline
        # freeze keeps P-CONTAM-01's historical Rust source text as written.
        # (version_history keeps historical prose such as P-CONTAM-01's #1927 rebind.)
        for policy in manifest["policies"]:
            bound = [policy.get("source_file", ""), *policy.get("test_entrypoints", [])]
            assert all(RETIRED_TREE not in str(item) for item in bound), policy["policy_id"]


@pytest.mark.parametrize(
    "src",
    [
        "import nexus.bridge.rust_kernel",
        "from nexus.bridge import cutover_manager",
        "from nexus.bridge.rust_kernel import RustKernelAdapter",
        "importlib.import_module('nexus.bridge.cutover_manager')",
    ],
)
def test_import_detector_catches_each_import_form(src: str) -> None:
    assert any(_imports_retired(node) for node in ast.walk(ast.parse(src)))
