#!/usr/bin/env python3
"""Run provider-free, portable checks for a Nexus checkout.

The doctor only inspects repository setup and the local Python environment.  It
never loads secret values, invokes provider CLIs, accesses the network, or
claims runtime/release readiness.  Optional provider *presence* is reported as
an unverified hint separate from the core verdict.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

MIN_SUPPORTED_PYTHON = (3, 10)
MAX_SUPPORTED_PYTHON = (4, 0)
PINNED_PYTHON = None
CORE_FILES = ("pyproject.toml", "uv.lock", "scripts/engine/nexus_cli.py")
# These are imports used by the current CLI/source, not provider SDKs.
CORE_MODULES = ("pydantic", "yaml", "anyio", "click")
PROVIDER_VARS = (
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "JINA_API_KEY",
    "NEXUS_GEMINI_MODEL_NAME",
    "OPENAI_API_KEY",
)
PROVIDER_TOOLS = ("gemini", "node")


def _check(name: str, passed: bool, reason: str, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"name": name, "passed": passed, "reason": reason}
    result.update(extra)
    return result


def check_python(version_info: tuple[int, int, int] | None = None) -> dict[str, Any]:
    current = version_info or (
        sys.version_info.major,
        sys.version_info.minor,
        sys.version_info.micro,
    )
    major_minor = current[:2]
    supported = MIN_SUPPORTED_PYTHON <= major_minor < MAX_SUPPORTED_PYTHON
    version = ".".join(str(part) for part in current)
    return _check(
        "python",
        supported,
        "supported" if supported else "unsupported_python",
        version=version,
        supported_range=">=3.10,<4.0",
        pinned=None,
        pinned_match=None,
        guidance="" if supported else "Use a Python version supported by pyproject.toml.",
    )


def _cache_candidate(repo_root: Path) -> Path:
    configured = os.environ.get("UV_CACHE_DIR")
    return Path(configured).expanduser() if configured else repo_root / ".tmp" / "uv-cache"


def check_cache(repo_root: Path) -> dict[str, Any]:
    configured = os.environ.get("UV_CACHE_DIR")
    cache = _cache_candidate(repo_root)
    if configured and not cache.is_absolute():
        return _check(
            "uv_cache",
            False,
            "cache_path_not_absolute",
            guidance="Set UV_CACHE_DIR to an absolute project-local or temporary directory.",
        )
    try:
        resolved = cache.resolve()
        repo = repo_root.resolve()
        in_project = resolved == repo or repo in resolved.parents
        temp_roots = {Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve()}
        in_temp = any(resolved == root or root in resolved.parents for root in temp_roots)
    except OSError:
        return _check("uv_cache", False, "cache_path_unresolvable")
    if not configured and not in_project:
        return _check(
            "uv_cache",
            False,
            "project_cache_symlink_escape",
            guidance="Use a project-local .tmp/uv-cache directory.",
        )
    if configured and not (in_project or in_temp):
        return _check(
            "uv_cache",
            False,
            "cache_location_not_allowed",
            guidance="Use a project-local or temporary UV_CACHE_DIR.",
        )
    try:
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="doctor-", dir=cache, delete=True):
            pass
    except (OSError, ValueError):
        return _check(
            "uv_cache",
            False,
            "cache_unwritable",
            guidance="Use a writable project-local or temporary cache directory.",
        )
    return _check(
        "uv_cache", True, "writable", location="environment" if configured else "project_local"
    )


def check_core(repo_root: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for relative in CORE_FILES:
        present = (repo_root / relative).is_file()
        checks.append(
            _check(f"core_file:{relative}", present, "present" if present else "missing_core_file")
        )
    for module in CORE_MODULES:
        present = importlib.util.find_spec(module) is not None
        checks.append(
            _check(
                f"core_dependency:{module}",
                present,
                "importable" if present else "missing_core_dependency",
            )
        )
    return checks


def check_provider() -> dict[str, Any]:
    tools = {tool: shutil.which(tool) is not None for tool in PROVIDER_TOOLS}
    variables = {name: bool(os.environ.get(name)) for name in PROVIDER_VARS}
    detected = any(tools.values()) or any(variables.values())
    return {
        "status": "optional_configured_unverified" if detected else "optional_missing",
        "required_for_core": False,
        "tools": tools,
        "variables_present": variables,
        "reason": "provider_presence_only_no_auth_probe" if detected else "provider_not_detected",
    }


def build_report(
    repo_root: Path | str | None = None, *, python_version: tuple[int, int, int] | None = None
) -> dict[str, Any]:
    root = Path(repo_root or Path(__file__).resolve().parents[2]).resolve()
    checks = [check_python(python_version), check_cache(root), *check_core(root)]
    core_ready = all(item["passed"] for item in checks)
    return {
        "schema": "nexus_repo_doctor_v1",
        "core": {"status": "ready" if core_ready else "blocked", "checks": checks},
        "provider": check_provider(),
        "claim": "bounded provider-free repository setup diagnostics only; no runtime or release claim",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("json", "human"), default="human")
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)
    report = build_report(args.repo_root)
    if args.format == "json":
        print(json.dumps(report, sort_keys=True))
    else:
        print(f"core: {report['core']['status']}")
        for check in report["core"]["checks"]:
            print(f"- {check['name']}: {'PASS' if check['passed'] else 'FAIL'} ({check['reason']})")
        print(f"provider: {report['provider']['status']} (optional for core)")
        print(report["claim"])
    return 0 if report["core"]["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
