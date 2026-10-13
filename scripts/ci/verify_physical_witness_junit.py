#!/usr/bin/env python3
"""Fail-closed verifier for the DSH Seatbelt physical witness (#1607).

The two physical Seatbelt tests in ``tests/ops/test_nexus_dsh_linked_worktree.py``
are not collected where Seatbelt cannot run, so a Linux pytest run is green
without any confinement evidence. This verifier is the only thing that turns a
macOS pytest run into a physical-witness receipt:

* ``preflight`` proves the host can produce the witness: darwin, the physical
  ``/usr/bin/sandbox-exec`` (the one the tests resolve via ``PATH``), and a live
  canary in which Seatbelt denies an out-of-temp write and leaves it unchanged.
* ``verify`` repeats the preflight, binds the exact clean Git subject, and
  requires a fresh JUnit report in which exactly the expected two physical
  nodes PASSED with zero skips, errors or failures for the file.

Nothing is inferred from runner prose; every missing or ambiguous fact fails.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET  # nosec B405 - parses this job's own pytest report
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCHEMA = "nexus.dsh_seatbelt_physical_witness.v1"
CLAIM_CEILING = (
    "PHYSICAL_SEATBELT_WITNESS_FOR_EXACT_HEAD_ONLY; not required-check registration, "
    "merge, release, or installed-runtime truth"
)
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
TEST_FILE = "tests/ops/test_nexus_dsh_linked_worktree.py"
TEST_CLASSNAME = "tests.ops.test_nexus_dsh_linked_worktree"
WITNESS_DECORATOR = "physical_seatbelt_witness"
EXPECTED_WITNESSES = (
    "test_linked_worktree_git_restore_is_physically_denied_under_workspace_write",
    "test_standalone_clone_allows_exact_git_metadata_ops_and_denies_parent_and_siblings",
)
SUBJECT_FILES = {
    "test_file": TEST_FILE,
    "conftest": "tests/ops/conftest.py",
    "dsh_workflow": "scripts/ops/nexus-dsh-workflow",
    "verifier": "scripts/ci/verify_physical_witness_junit.py",
    "ci_workflow": ".github/workflows/pytest.yml",
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DENIED = "Operation not permitted"


class WitnessError(Exception):
    """A fail-closed rejection with a stable reason code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _real(path: str | Path) -> Path:
    return Path(os.path.realpath(path))


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def host_temp_roots(env: dict[str, str] | None = None) -> tuple[Path, ...]:
    env = os.environ if env is None else env
    # Roots the canary victim must stay outside of; nothing is written here.
    roots = ["/tmp", "/private/tmp", "/var/folders", "/private/var/folders"]  # nosec B108
    roots.append(tempfile.gettempdir())
    if env.get("TMPDIR"):
        roots.append(env["TMPDIR"])
    return tuple(dict.fromkeys(_real(root) for root in roots))


def check_sandbox_binary(path: str = SANDBOX_EXEC, *, which: Callable = shutil.which) -> dict:
    """The tests run ``sandbox-exec`` from PATH; it must be the physical system binary."""
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise WitnessError("SANDBOX_EXEC_MISSING", f"{path}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise WitnessError("SANDBOX_EXEC_NOT_REGULAR_FILE", path)
    if not info.st_mode & 0o111:
        raise WitnessError("SANDBOX_EXEC_NOT_EXECUTABLE", path)
    if info.st_uid != 0:
        raise WitnessError("SANDBOX_EXEC_NOT_ROOT_OWNED", f"{path} uid={info.st_uid}")
    resolved = which("sandbox-exec")
    if resolved is None or _real(resolved) != _real(path):
        raise WitnessError("SANDBOX_EXEC_PATH_SHADOWED", f"PATH resolves to {resolved!r}")
    return {
        "path": path,
        "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "size": info.st_size,
    }


def _canary_profile(workspace: Path) -> str:
    return (
        "(version 1) (allow default) (deny file-write*) "
        '(allow file-write* (literal "/dev/null")) '
        f'(allow file-write* (subpath "{workspace}"))'
    )


def run_seatbelt_canary(
    sandbox_exec: str,
    canary_parent: Path,
    *,
    temp_roots: tuple[Path, ...] | None = None,
) -> dict:
    """Seatbelt must allow a workspace write and deny an out-of-temp sibling write."""
    temp_roots = host_temp_roots() if temp_roots is None else temp_roots
    canary_parent.mkdir(parents=True, exist_ok=True)
    root = _real(tempfile.mkdtemp(prefix="canary-", dir=canary_parent))
    try:
        if any(_within(root, temp) for temp in temp_roots):
            raise WitnessError("CANARY_ROOT_UNDER_TEMP_GRANT", str(root))
        workspace = root / "workspace"
        workspace.mkdir()
        victim = root / "victim.txt"
        victim.write_bytes(b"canary\n")
        allowed = workspace / "allowed.txt"

        def sandboxed(script: str, target: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    sandbox_exec,
                    "-p",
                    _canary_profile(workspace),
                    "/bin/sh",
                    "-c",
                    script,
                    "sh",
                    str(target),
                ],
                cwd=workspace,
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )

        allow = sandboxed('printf ok > "$1"', allowed)
        if allow.returncode != 0 or not allowed.is_file() or allowed.read_bytes() != b"ok":
            raise WitnessError(
                "CANARY_WORKSPACE_WRITE_NOT_ALLOWED",
                f"rc={allow.returncode} stderr={allow.stderr.strip()[:200]!r}",
            )
        deny = sandboxed('printf x >> "$1"', victim)
        if victim.read_bytes() != b"canary\n":
            raise WitnessError("CANARY_OUT_OF_TEMP_WRITE_NOT_DENIED", "victim changed")
        if deny.returncode == 0 or DENIED not in deny.stderr:
            raise WitnessError(
                "CANARY_OUT_OF_TEMP_WRITE_NOT_DENIED",
                f"rc={deny.returncode} stderr={deny.stderr.strip()[:200]!r}",
            )
        return {
            "victim_outside_temp": True,
            "workspace_write_returncode": allow.returncode,
            "denied_write_returncode": deny.returncode,
            "denied_write_stderr": deny.stderr.strip()[:200],
            "victim_unchanged": True,
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def preflight(
    *,
    sys_platform: str,
    canary_parent: Path,
    sandbox_exec: str = SANDBOX_EXEC,
    binary_check: Callable[[str], dict] = check_sandbox_binary,
    canary: Callable[[str, Path], dict] = run_seatbelt_canary,
) -> dict:
    if sys_platform != "darwin":
        raise WitnessError("NOT_DARWIN", sys_platform)
    binary = binary_check(sandbox_exec)
    return {"sandbox_exec": binary, "canary": canary(sandbox_exec, canary_parent)}


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise WitnessError(
            "GIT_IDENTITY_UNAVAILABLE", f"git {' '.join(args)}: {proc.stderr.strip()}"
        )
    return proc.stdout.strip()


def git_subject(repo: Path, expected_head: str) -> dict:
    if not SHA_RE.match(expected_head or ""):
        raise WitnessError("EXPECTED_HEAD_SHA_INVALID", repr(expected_head))
    head = _git(repo, "rev-parse", "HEAD")
    if head != expected_head:
        raise WitnessError("HEAD_SHA_MISMATCH", f"{head} != {expected_head}")
    if _git(repo, "status", "--porcelain", "--untracked-files=all"):
        raise WitnessError("WORKTREE_DIRTY", "exact head checkout has local changes")
    blobs = {}
    for key, rel in SUBJECT_FILES.items():
        committed = _git(repo, "rev-parse", f"HEAD:{rel}")
        on_disk = _git(repo, "hash-object", "--", rel)
        if committed != on_disk:
            raise WitnessError("SUBJECT_FILE_DRIFT", rel)
        blobs[key] = {"path": rel, "blob": committed}
    return {"head_sha": head, "head_tree": _git(repo, "rev-parse", "HEAD^{tree}"), "blobs": blobs}


def declared_witnesses(test_source: str) -> tuple[set[str], set[str]]:
    """Return (all top-level test functions, those decorated as physical witnesses)."""
    tree = ast.parse(test_source)
    tests: set[str] = set()
    witnesses: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test_"
        ):
            tests.add(node.name)
            for deco in node.decorator_list:
                target = deco.func if isinstance(deco, ast.Call) else deco
                if isinstance(target, ast.Name) and target.id == WITNESS_DECORATOR:
                    witnesses.add(node.name)
    return tests, witnesses


def _parse_time(value: str | None, code: str) -> datetime:
    if not value:
        raise WitnessError(code, "missing timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise WitnessError(code, value) from exc
    if parsed.tzinfo is None:
        raise WitnessError(code, f"timestamp without timezone: {value}")
    return parsed


def verify_junit(
    junit_bytes: bytes,
    test_source: str,
    *,
    not_before: str,
    hostname: str,
    now: datetime | None = None,
) -> dict:
    expected = set(EXPECTED_WITNESSES)
    tests, witnesses = declared_witnesses(test_source)
    if witnesses != expected:
        raise WitnessError("WITNESS_DECLARATION_MISMATCH", f"source declares {sorted(witnesses)}")
    try:
        root = ET.fromstring(junit_bytes)  # nosec B314 - this job's own pytest report
    except ET.ParseError as exc:
        raise WitnessError("JUNIT_UNPARSEABLE", str(exc)) from exc
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if root.tag not in {"testsuite", "testsuites"} or len(suites) != 1:
        raise WitnessError("JUNIT_SUITE_AMBIGUOUS", f"{len(suites)} testsuite elements")
    suite = suites[0]
    if suite.get("hostname") != hostname:
        raise WitnessError("JUNIT_HOST_MISMATCH", f"{suite.get('hostname')!r} != {hostname!r}")
    started = _parse_time(suite.get("timestamp"), "JUNIT_TIMESTAMP_INVALID")
    lower = _parse_time(not_before, "NOT_BEFORE_INVALID")
    upper = now or datetime.now(timezone.utc)
    if not lower <= started <= upper:
        raise WitnessError("JUNIT_NOT_FRESH", f"{started.isoformat()} outside [{lower}, {upper}]")

    cases = list(suite.iter("testcase"))
    foreign = sorted({case.get("classname", "") for case in cases} - {TEST_CLASSNAME})
    if foreign:
        raise WitnessError("JUNIT_FOREIGN_TESTCASES", ", ".join(foreign))
    names = Counter(case.get("name", "") for case in cases)
    duplicates = sorted(name for name, count in names.items() if count > 1)
    if duplicates:
        raise WitnessError("JUNIT_DUPLICATE_TESTCASE", ", ".join(duplicates))
    base_names = {name.split("[", 1)[0] for name in names}
    if base_names != tests:
        missing = sorted(tests - base_names)
        extra = sorted(base_names - tests)
        raise WitnessError("JUNIT_COLLECTION_MISMATCH", f"missing={missing} extra={extra}")
    for name in expected:
        if names.get(name) != 1 or any(n != name and n.split("[", 1)[0] == name for n in names):
            raise WitnessError("WITNESS_NODE_AMBIGUOUS", name)

    outcomes = []
    for case in cases:
        bad = [child.tag for child in case if child.tag in {"skipped", "error", "failure"}]
        if bad:
            raise WitnessError(f"JUNIT_TESTCASE_{bad[0].upper()}", case.get("name", ""))
        if case.get("name") in expected:
            outcomes.append({
                "node_id": f"{TEST_FILE}::{case.get('name')}",
                "outcome": "passed",
                "time": case.get("time"),
            })
    for attr in ("errors", "failures", "skipped"):
        if suite.get(attr) != "0":
            raise WitnessError("JUNIT_SUITE_NOT_CLEAN", f"{attr}={suite.get(attr)!r}")
    if suite.get("tests") != str(len(cases)):
        raise WitnessError(
            "JUNIT_SUITE_COUNT_MISMATCH", f"tests={suite.get('tests')!r} cases={len(cases)}"
        )
    return {
        "sha256": hashlib.sha256(junit_bytes).hexdigest(),
        "timestamp": started.isoformat(),
        "hostname": hostname,
        "testcases": len(cases),
        "witnesses": sorted(outcomes, key=lambda item: item["node_id"]),
    }


def github_context(env: dict[str, str]) -> dict:
    """Identity of a GitHub-hosted macOS run; any missing or self-hosted field fails."""
    required = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_OS": "macOS",
        "RUNNER_ENVIRONMENT": "github-hosted",
    }
    for key, value in required.items():
        if env.get(key) != value:
            raise WitnessError("GITHUB_HOSTED_CONTEXT_MISSING", f"{key}={env.get(key)!r}")
    fields = {
        "repository": "GITHUB_REPOSITORY",
        "workflow_ref": "GITHUB_WORKFLOW_REF",
        "job": "GITHUB_JOB",
        "event_name": "GITHUB_EVENT_NAME",
        "ref": "GITHUB_REF",
        "run_id": "GITHUB_RUN_ID",
        "run_attempt": "GITHUB_RUN_ATTEMPT",
        "runner_name": "RUNNER_NAME",
        "runner_os": "RUNNER_OS",
        "runner_arch": "RUNNER_ARCH",
        "runner_environment": "RUNNER_ENVIRONMENT",
        "image_os": "ImageOS",
        "image_version": "ImageVersion",
    }
    context = {name: env.get(key) for name, key in fields.items()}
    missing = sorted(name for name, value in context.items() if not value)
    if missing:
        raise WitnessError("GITHUB_HOSTED_CONTEXT_MISSING", ", ".join(missing))
    if not (context["run_id"].isdigit() and context["run_attempt"].isdigit()):
        raise WitnessError(
            "GITHUB_RUN_IDENTITY_INVALID", f"{context['run_id']}/{context['run_attempt']}"
        )
    return context


def default_canary_parent() -> Path:
    return Path.home() / ".cache" / "nexus-physical-witness-canary"


def build_receipt(args: argparse.Namespace, env: dict[str, str]) -> dict:
    repo = _real(args.repo_root)
    canary_parent = Path(args.canary_parent) if args.canary_parent else default_canary_parent()
    host = preflight(sys_platform=sys.platform, canary_parent=canary_parent)
    subject = git_subject(repo, args.expected_head_sha)
    if not args.command:
        raise WitnessError("COMMAND_MISSING")
    junit_path = Path(args.junit)
    if not junit_path.is_file():
        raise WitnessError("JUNIT_MISSING", str(junit_path))
    junit = verify_junit(
        junit_path.read_bytes(),
        (repo / TEST_FILE).read_text(encoding="utf-8"),
        not_before=args.not_before,
        hostname=platform.node(),
    )
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "PASS",
        "claim_ceiling": CLAIM_CEILING,
        "subject": subject,
        "execution_context": "GITHUB_HOSTED" if args.require_github_hosted else "LOCAL",
        "github": github_context(env) if args.require_github_hosted else None,
        "host": {
            "platform": sys.platform,
            "macos_version": platform.mac_ver()[0],
            "machine": platform.machine(),
            "hostname": platform.node(),
            "python": platform.python_version(),
            **host,
        },
        "command": args.command,
        "junit": junit,
    }
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    pre = sub.add_parser("preflight")
    pre.add_argument("--canary-parent")
    ver = sub.add_parser("verify")
    ver.add_argument("--repo-root", default=".")
    ver.add_argument("--expected-head-sha", required=True)
    ver.add_argument("--junit", required=True)
    ver.add_argument("--not-before", required=True)
    ver.add_argument("--command", required=True)
    ver.add_argument("--canary-parent")
    ver.add_argument("--require-github-hosted", action="store_true")
    ver.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        if args.mode == "preflight":
            parent = Path(args.canary_parent) if args.canary_parent else default_canary_parent()
            result: dict[str, Any] = {
                "schema": SCHEMA,
                "status": "PREFLIGHT_PASS",
                **preflight(sys_platform=sys.platform, canary_parent=parent),
            }
        else:
            result = build_receipt(args, dict(os.environ))
    except WitnessError as exc:
        result = {"schema": SCHEMA, "status": "FAIL", "reason_code": exc.code, "detail": exc.detail}
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.mode == "verify":
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["status"] in {"PASS", "PREFLIGHT_PASS"} else 1


if __name__ == "__main__":
    sys.exit(main())
