"""Shared modifiable scope for every arm of #2721 (package-directory level).

The scope is fixed per repository from its source layout alone, before and
independent of any task's gold patch, so it cannot leak which files the human
fix touched.  Each entry is a directory prefix (trailing ``/``) or an exact
file, at most four entries per repository (the P1 ``nexus_worker_candidate``
limit is 1-4 ``allowed_files``).  Test directories are never in scope: the
hidden tests are withheld from both arms and applied only by the scorer.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

SCOPE_VERSION = "measure-2721-scope.v1"
MAX_SCOPE_ENTRIES = 4

# repository slug (``owner/name``) -> source roots.  Derived from the top-level
# layout of each repository (where the importable package lives), never from a
# task.  Keep sorted by slug.
REPO_SCOPE: Mapping[str, tuple[str, ...]] = {
    "PyCQA/isort": ("isort/",),
    "beetbox/beets": ("beets/", "beetsplug/"),
    "conan-io/conan": ("conan/", "conans/"),
    "fsspec/filesystem_spec": ("fsspec/",),
    "getmoto/moto": ("moto/",),
    "pallets/werkzeug": ("src/werkzeug/",),
    "psf/black": ("src/black/", "src/blackd/", "src/blib2to3/"),
    "pvlib/pvlib-python": ("pvlib/",),
    "pydantic/pydantic-settings": ("pydantic_settings/",),
    "pydata/xarray": ("xarray/",),
    "pylint-dev/astroid": ("astroid/",),
    "pylint-dev/pylint": ("pylint/",),
    "pytest-dev/pytest": ("src/_pytest/", "src/pytest/", "src/py.py"),
    "scrapy/scrapy": ("scrapy/",),
    "sqlfluff/sqlfluff": ("src/sqlfluff/",),
    "sympy/sympy": ("sympy/",),
    "tobymao/sqlglot": ("sqlglot/",),
    "tox-dev/tox": ("src/tox/",),
}

_TEST_PARTS = frozenset({"tests", "test", "testing"})


def scope_for(repo: str) -> tuple[str, ...]:
    """The fixed scope of ``repo``; KeyError when the repository has none."""
    scope = tuple(REPO_SCOPE[repo])
    if not 1 <= len(scope) <= MAX_SCOPE_ENTRIES:
        raise ValueError(f"scope of {repo} must have 1-{MAX_SCOPE_ENTRIES} entries")
    return scope


def is_test_path(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    return (
        any(part in _TEST_PARTS for part in parts[:-1])
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


def in_scope(path: str, scope: Sequence[str]) -> bool:
    """Same boundary rule the Nexus contract uses (task_contract.py)."""
    return any(path == entry or (entry.endswith("/") and path.startswith(entry)) for entry in scope)


def out_of_scope(paths: Iterable[str], scope: Sequence[str]) -> list[str]:
    return sorted(path for path in paths if not in_scope(path, scope))
