#!/usr/bin/env python3
"""Run a cache-independent pytest closure and emit a revision-bound manifest.

The manifest is evidence, not lifecycle authority.  It records the exact
repository revision, collection result, nodeids, and JUnit outcome so a stale
pytest cache or a moving checkout cannot be mistaken for a current result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence


SCHEMA = "nexus.fresh_suite_manifest.v1"
_NODEID_RE = re.compile(r"^\S+::\S+$")
Runner = Callable[..., subprocess.CompletedProcess[str]]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _run(command: Sequence[str], *, cwd: Path, runner: Runner) -> subprocess.CompletedProcess[str]:
    return runner(
        list(command),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _git_value(repo_root: Path, args: Sequence[str], *, runner: Runner) -> str:
    result = _run(["git", *args], cwd=repo_root, runner=runner)
    if result.returncode != 0:
        raise RuntimeError(f"git command failed: git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def _parse_nodeids(output: str) -> list[str]:
    """Extract nodeids from pytest's ``-qq --collect-only`` output."""

    return sorted({line.strip() for line in output.splitlines() if _NODEID_RE.match(line.strip())})


def _junit_root(path: Path) -> ET.Element:
    if not path.exists():
        raise RuntimeError(f"pytest did not produce JUnit XML: {path}")
    try:
        return ET.parse(path).getroot()
    except ImportError as exc:
        raise RuntimeError(f"XML parser unavailable: {exc}") from exc
    except ET.ParseError as exc:
        raise RuntimeError(f"invalid pytest JUnit XML: {exc}") from exc


def _junit_outcomes(path: Path) -> dict[str, Any]:
    try:
        root = _junit_root(path)
    except RuntimeError as exc:
        # Some system Python builds ship a broken expat dylib while the
        # project venv remains healthy. JUnit is deliberately simple enough
        # for this conservative fallback; malformed XML still fails closed.
        if not str(exc).startswith("XML parser unavailable:"):
            raise
        return _junit_outcomes_without_expat(path)
    cases = list(root.iter("testcase"))
    counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    failures: list[str] = []
    for case in cases:
        name = str(case.attrib.get("name") or "<unnamed>")
        if case.find("failure") is not None:
            counts["failed"] += 1
            failures.append(f"{name}:failure")
        elif case.find("error") is not None:
            counts["error"] += 1
            failures.append(f"{name}:error")
        elif case.find("skipped") is not None:
            counts["skipped"] += 1
        else:
            counts["passed"] += 1
    domain = "none" if not failures else _sha256_text("\n".join(sorted(failures)))[:16]
    return {"testcase_count": len(cases), **counts, "failure_domain_fingerprint": domain}


def _junit_outcomes_without_expat(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    fragments = re.findall(r"<testcase\b[^>]*?/>|<testcase\b[^>]*>.*?</testcase>", text, flags=re.DOTALL)
    if not fragments:
        raise RuntimeError("invalid pytest JUnit XML: no testcase elements")
    counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    failures: list[str] = []
    for index, fragment in enumerate(fragments):
        name_match = re.search(r"\bname=[\"']([^\"']*)", fragment)
        name = name_match.group(1) if name_match else f"case-{index}"
        if re.search(r"<failure\b", fragment):
            counts["failed"] += 1
            failures.append(f"{name}:failure")
        elif re.search(r"<error\b", fragment):
            counts["error"] += 1
            failures.append(f"{name}:error")
        elif re.search(r"<skipped\b", fragment):
            counts["skipped"] += 1
        else:
            counts["passed"] += 1
    domain = "none" if not failures else _sha256_text("\n".join(sorted(failures)))[:16]
    return {"testcase_count": len(fragments), **counts, "failure_domain_fingerprint": domain}


def run_fresh_suite(
    repo_root: Path,
    pytest_args: Sequence[str],
    *,
    output_path: Path,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Collect and execute pytest with cache clearing, then write evidence."""

    root = repo_root.resolve()
    args = [str(arg) for arg in pytest_args if str(arg)]
    if not args:
        raise ValueError("at least one pytest path or nodeid is required")
    head = _git_value(root, ["rev-parse", "HEAD"], runner=runner)
    branch = _git_value(root, ["branch", "--show-current"], runner=runner)
    porcelain = _git_value(root, ["status", "--porcelain"], runner=runner)
    dirty = bool(porcelain)
    started_at = datetime.now(timezone.utc).isoformat()
    collection_command = [sys.executable, "-m", "pytest", "--cache-clear", "--collect-only", "-qq", "--disable-warnings", *args]
    collection_started = time.monotonic()
    collected = _run(collection_command, cwd=root, runner=runner)
    collection_ms = max(0, int((time.monotonic() - collection_started) * 1000))
    nodeids = _parse_nodeids(collected.stdout)

    outcome: dict[str, Any] = {"testcase_count": 0, "passed": 0, "failed": 0, "skipped": 0, "error": 0, "failure_domain_fingerprint": "none"}
    run_result: subprocess.CompletedProcess[str] | None = None
    run_ms = 0
    junit_path: Path | None = None
    if collected.returncode == 0 and nodeids:
        with tempfile.NamedTemporaryFile(prefix="nexus-fresh-suite-", suffix=".xml", delete=False) as handle:
            junit_path = Path(handle.name)
        run_command = [sys.executable, "-m", "pytest", "--cache-clear", "-q", "--disable-warnings", f"--junitxml={junit_path}", *args]
        run_started = time.monotonic()
        run_result = _run(run_command, cwd=root, runner=runner)
        run_ms = max(0, int((time.monotonic() - run_started) * 1000))
        outcome = _junit_outcomes(junit_path)

    blockers: list[str] = []
    if dirty:
        blockers.append("DIRTY_CHECKOUT")
    if collected.returncode != 0:
        blockers.append("COLLECTION_FAILED")
    if not nodeids:
        blockers.append("EMPTY_COLLECTION")
    if run_result is None:
        blockers.append("EXECUTION_NOT_STARTED")
    elif run_result.returncode != 0:
        blockers.append("TESTS_FAILED")
    if outcome["failed"] or outcome["error"]:
        blockers.append("JUNIT_FAILURES")
    status = "PASS" if not blockers else "FAIL"
    failure_material = "\n".join(
        part
        for part in (
            collected.stdout,
            collected.stderr,
            run_result.stdout if run_result else "",
            run_result.stderr if run_result else "",
        )
        if part
    )
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "artifact_authority": "evidence",
        "status": status,
        "generated_at": started_at,
        "repo_root": str(root),
        "branch": branch,
        "head": head,
        "dirty": dirty,
        "pytest_args": args,
        "collection": {
            "cache_clear": True,
            "command": collection_command,
            "exit_code": collected.returncode,
            "wall_time_ms": collection_ms,
            "nodeid_count": len(nodeids),
            "nodeids_sha256": _sha256_text("\n".join(nodeids)) if nodeids else "",
            "nodeids": nodeids,
        },
        "execution": {
            "cache_clear": True,
            "command": run_command if run_result is not None else None,
            "exit_code": run_result.returncode if run_result is not None else None,
            "wall_time_ms": run_ms,
            **outcome,
        },
        "blockers": blockers,
        "failure_domain_fingerprint": "none" if status == "PASS" else _sha256_text(failure_material or status)[:16],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    if junit_path is not None:
        junit_path.unlink(missing_ok=True)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="pytest paths/nodeids after --")
    parsed = parser.parse_args(argv)
    args = list(parsed.pytest_args)
    if args and args[0] == "--":
        args = args[1:]
    try:
        manifest = run_fresh_suite(parsed.repo_root, args, output_path=parsed.output)
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": manifest["status"], "head": manifest["head"], "dirty": manifest["dirty"], "nodeid_count": manifest["collection"]["nodeid_count"], "passed": manifest["execution"]["passed"], "failed": manifest["execution"]["failed"], "skipped": manifest["execution"]["skipped"], "failure_domain_fingerprint": manifest["failure_domain_fingerprint"], "output": str(parsed.output)}, ensure_ascii=False, sort_keys=True))
    return 0 if manifest["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
