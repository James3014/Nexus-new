#!/usr/bin/env python3
"""Portable, secrets-free checks for the repository's core setup.

The doctor deliberately does not load ``.env`` (or any other secret file),
perform network calls, or require provider CLIs.  Provider readiness is
reported separately from the core setup verdict.
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

PINNED_PYTHON = (3, 12)
MIN_SUPPORTED_PYTHON = (3, 12)
MAX_SUPPORTED_PYTHON = (3, 15)
CORE_FILES = ("pyproject.toml", "uv.lock", "scripts/engine/nexus_cli.py")
CORE_MODULES = ("pydantic", "yaml", "anyio", "typer")
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
    version = ".".join(str(part) for part in current)
    supported = MIN_SUPPORTED_PYTHON <= major_minor < MAX_SUPPORTED_PYTHON
    pinned = major_minor == PINNED_PYTHON
    return _check(
        "python",
        supported,
        ("supported_pinned" if pinned else "supported_non_pinned")
        if supported
        else "unsupported_python",
        version=version,
        supported_range=">=3.12,<3.15",
        pinned="3.12",
        pinned_match=pinned,
        guidance=(
            "Recreate the project environment with Python 3.12 for CI parity."
            if supported and not pinned
            else ""
        ),
    )


def _cache_candidate(repo_root: Path) -> Path:
    configured = os.environ.get("UV_CACHE_DIR")
    if configured:
        return Path(configured).expanduser()
    return repo_root / ".tmp" / "uv-cache"


def check_cache(repo_root: Path) -> dict[str, Any]:
    cache = _cache_candidate(repo_root)
    configured = os.environ.get("UV_CACHE_DIR")
    if configured and not cache.is_absolute():
        return _check(
            "uv_cache",
            False,
            "cache_path_not_absolute",
            guidance="Set UV_CACHE_DIR to an absolute project-local or /tmp directory.",
        )
    resolved_cache = cache.resolve()
    in_project = resolved_cache.is_relative_to(repo_root.resolve())
    temp_roots = {Path("/tmp").resolve(), Path(tempfile.gettempdir()).resolve()}
    in_system_temp = any(resolved_cache.is_relative_to(root) for root in temp_roots)
    if not configured and not in_project:
        return _check(
            "uv_cache",
            False,
            "project_cache_symlink_escape",
            guidance="Replace the project cache symlink with a directory inside the repository.",
        )
    if configured and resolved_cache.is_relative_to(Path.home().resolve()) and not in_project:
        return _check(
            "uv_cache",
            False,
            "home_cache_rejected",
            guidance="Use a project-local cache or UV_CACHE_DIR=/tmp/nexus-uv-cache.",
        )
    if configured and not (in_project or in_system_temp):
        return _check(
            "uv_cache",
            False,
            "cache_location_not_allowed",
            guidance="Set UV_CACHE_DIR to a project-local or system temporary directory.",
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
            guidance="Set UV_CACHE_DIR to a writable project-local or /tmp directory.",
        )
    # Do not emit home directories or arbitrary absolute paths in receipts.
    location = "environment" if os.environ.get("UV_CACHE_DIR") else "project_local"
    return _check("uv_cache", True, "writable", location=location)


def check_core(repo_root: Path) -> list[dict[str, Any]]:
    checks = []
    for relative in CORE_FILES:
        checks.append(
            _check(
                f"core_file:{relative}",
                (repo_root / relative).is_file(),
                "present" if (repo_root / relative).is_file() else "missing_core_file",
            )
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
    # Presence is intentionally boolean only; values are never read or emitted.
    variables = {name: bool(os.environ.get(name)) for name in PROVIDER_VARS}
    detected = any(tools.values()) or any(variables.values())
    return {
        "status": "optional_configured_unverified" if detected else "optional_missing",
        "required_for_core": False,
        "tools": tools,
        "variables_present": variables,
        "reason": (
            "provider_inputs_detected_without_auth_probe"
            if detected
            else "provider_tools_or_configuration_unavailable"
        ),
    }


def build_report(
    repo_root: Path | str | None = None,
    *,
    python_version: tuple[int, int, int] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root or Path(__file__).resolve().parents[2]).resolve()
    checks = [check_python(python_version), check_cache(root), *check_core(root)]
    core_ready = all(item["passed"] for item in checks)
    return {
        "schema": "nexus_repo_doctor_v1",
        "core": {"status": "ready" if core_ready else "blocked", "checks": checks},
        "provider": check_provider(),
        "claim": "bounded core setup canary only; no release claim",
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
