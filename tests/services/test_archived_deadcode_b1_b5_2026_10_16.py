"""Guard for the 2026-10-16 dead-code retirement (batches B1 and B5, Issue #2340).

See ARCHIVED_2026-10-16_deadcode_b1_b5.md. The modules below were physically
deleted after an Owner decision. These tests fail if one comes back, or if code
under nexus/ starts importing or naming one again, so re-adding is deliberate.
"""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NEXUS_ROOT = REPO_ROOT / "nexus"

RETIRED_MODULES = (
    # B1: local_assist_* canaries/gates
    "nexus.services.local_assist_advisor_canary",
    "nexus.services.local_assist_bounded_dispatch",
    "nexus.services.local_assist_candidate_canary",
    "nexus.services.local_assist_contribution",
    "nexus.services.local_assist_default_policy",
    "nexus.services.local_assist_preflight",
    "nexus.services.local_assist_value_matrix",
    "nexus.services.local_assist_verified_canary",
    # B5: reach.resolvers
    "nexus.services.reach.resolvers",
    "nexus.services.reach.resolvers.yt_dlp",
)

RETIRED_PATHS = (
    "nexus/services/local_assist_advisor_canary.py",
    "nexus/services/local_assist_bounded_dispatch.py",
    "nexus/services/local_assist_candidate_canary.py",
    "nexus/services/local_assist_contribution.py",
    "nexus/services/local_assist_default_policy.py",
    "nexus/services/local_assist_preflight.py",
    "nexus/services/local_assist_value_matrix.py",
    "nexus/services/local_assist_verified_canary.py",
    "nexus/services/reach/resolvers/__init__.py",
    "nexus/services/reach/resolvers/yt_dlp.py",
    "nexus/services/reach/resolvers",
)


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(REPO_ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imported_modules(path: Path, tree: ast.AST) -> set[str]:
    """Absolute dotted names a module imports (relative imports resolved)."""
    module = _module_name(path)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = package.split(".")
                if node.level > 1:
                    anchor = anchor[: len(anchor) - (node.level - 1)]
                base = ".".join(anchor + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names)
    return names


def _is_retired(name: str) -> bool:
    return any(name == retired or name.startswith(retired + ".") for retired in RETIRED_MODULES)


@pytest.mark.parametrize("relpath", RETIRED_PATHS)
def test_retired_deadcode_b1_b5_path_absent(relpath: str) -> None:
    assert not (REPO_ROOT / relpath).exists(), f"{relpath} was retired (Issue #2340)"


@pytest.mark.parametrize("module", RETIRED_MODULES)
def test_retired_deadcode_b1_b5_module_not_importable(module: str) -> None:
    try:
        spec = importlib.util.find_spec(module)
    except ModuleNotFoundError:
        spec = None
    assert spec is None, f"{module} was retired (Issue #2340) but is importable again"


def test_retired_deadcode_b1_b5_not_imported_from_nexus() -> None:
    offenders: list[str] = []
    for path in sorted(NEXUS_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hits = sorted(name for name in _imported_modules(path, tree) if _is_retired(name))
        offenders.extend(f"{path.relative_to(REPO_ROOT)}: {name}" for name in hits)
    assert offenders == []


def test_retired_deadcode_b1_b5_not_named_in_nexus_sources() -> None:
    pattern = re.compile(
        "|".join(
            [rf"{re.escape(name)}\b" for name in RETIRED_MODULES]
            + [rf"{re.escape(name.replace('.', '/'))}\b" for name in RETIRED_MODULES]
        )
    )
    offenders: list[str] = []
    for path in sorted(NEXUS_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".json", ".toml", ".yaml", ".yml"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {match.group(0)}")
    assert offenders == []


def test_retired_deadcode_b1_b5_guard_detects_import() -> None:
    """The import scan is not vacuous: it flags each import form of a retired module."""
    sample = REPO_ROOT / "nexus" / "services" / "sample.py"
    for source in (
        "import nexus.services.local_assist_preflight\n",
        "from nexus.services import local_assist_value_matrix\n",
        "from .local_assist_bounded_dispatch import run\n",
        "from .reach.resolvers.yt_dlp import fetch_transcript\n",
    ):
        names = _imported_modules(sample, ast.parse(source))
        assert any(_is_retired(name) for name in names), source
    assert not any(
        _is_retired(name)
        for name in _imported_modules(sample, ast.parse("from .local_assist_closeout import x\n"))
    )
