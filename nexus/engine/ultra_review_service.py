from __future__ import annotations

import functools
import hashlib
import hmac
import json
import os
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from nexus.engine.sandboxed_lane import (  # noqa: F401 - re-exported for callers and tests
    _OS_SANDBOX_PROBE,
    GIT_ENV_ALLOWLIST,
    GIT_SAFE_CONFIG,
    SANDBOX_DENIED_HOME_PATHS,
    SANDBOX_ENV_ALLOWLIST,
    SANDBOX_FORBIDDEN_READ_ROOTS,
    SANDBOX_SYSTEM_READ_LITERALS,
    SANDBOX_SYSTEM_READ_SUBPATHS,
    SBPL_SAFE_PATH,
    SYMLINK_MODE,
    UNSAFE_PATCH_SUMMARY,
    SandboxError,
    build_sandbox_profile,
    checked_read_roots,
    diff_policy_violations,
    git_safe_env,
    in_tree,
    interpreter_read_roots,
    lstat_walk_violations,
    os_sandbox_available,
    run_confined,
    scrubbed_env,
    tool_read_roots,
    unsafe_summary_lines,
    write_no_follow,
)
from nexus.engine.sandboxed_lane import sbpl_path as _lane_sbpl_path

_T = TypeVar("_T")

DEFAULT_FLEET_LANES = ("security_sentry", "logic_breaker", "ghost_regression")
SCHEMA_VERSION = "ultra-review.v1"
# Default ghost-regression pytest timeout (one real mapped test file takes ~76 s, #2623);
# override per service (``test_timeout_sec``) or with ULTRA_TEST_TIMEOUT_ENV.
GHOST_REGRESSION_TIMEOUT_SEC = 300
ULTRA_TEST_TIMEOUT_ENV = "NEXUS_ULTRA_REVIEW_TEST_TIMEOUT_SEC"
# Per-test outcomes come from pytest's junit XML (xunit1 keeps the ``file`` attribute), never
# from parsing terminal text; reports larger than this are treated as unparseable.
JUNIT_MAX_BYTES = 20_000_000
# The ghost re-run executes PR-controlled code in the same process as pytest, so that code
# can write a fake junit report and then ``os._exit`` (#2644). The re-run is therefore started
# through this trusted ``-c`` bootstrap: it reads a fresh per-run key from stdin (then points
# fd 0 at /dev/null), and an in-memory pytest plugin, run after the junit writer at session
# finish, signs ``{exit status, junit sha256}`` with HMAC-SHA256 into a witness file. The
# reviewer accepts a report only when the MAC, the exit code and the junit hash all match.
# A report written outside pytest's own session finish, or a run that exits before it, has
# no valid witness. This defends only against code that does NOT read the key: the key lives
# in this same process, and code under review can recover it from the interpreter (gc /
# closures of the witness plugin) and sign a forged report, or rewrite pytest's own reports.
# The real fix is collecting results outside the tested process (#2644 stays open for it).
GHOST_PYTEST_BOOTSTRAP = """
import hashlib, hmac, json, os, sys
def _arm():
    key = bytes.fromhex(sys.stdin.readline().strip())
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, 0)
    os.close(null)
    junit, witness, args = sys.argv[2], sys.argv[3], sys.argv[4:]
    import pytest
    class _GhostWitness:
        @pytest.hookimpl(trylast=True)
        def pytest_sessionfinish(self, session, exitstatus):
            try:
                with open(junit, "rb") as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()
            except OSError:
                digest = ""
            payload = json.dumps({"exitstatus": int(exitstatus), "junit_sha256": digest}, sort_keys=True)
            mac = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
            fd = os.open(witness, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "w") as fh:
                json.dump({"payload": payload, "mac": mac}, fh)
    return pytest, _GhostWitness(), args
_pytest, _witness, _args = _arm()
del _arm
sys.exit(int(_pytest.main(_args, plugins=[_witness])))
"""
GHOST_WITNESS_MAX_BYTES = 4096
# A ghost run that hits its time budget is retried once with this many times the budget
# before it is reported INCONCLUSIVE_TIMEOUT: under heavy host load a real regression
# otherwise escapes as "inconclusive" (#2650, live witness of #2623).
GHOST_TIMEOUT_RETRY_FACTOR = 2
# Sandbox capability probes (#2650): run once per review, only when a head failure has no
# base result. A failed probe means "this sandbox cannot run such a test", never a regression.
ENV_PROBE_TIMEOUT_SEC = 30
# git's own error text when the object store lacks history a test asks for (the sandbox mirror
# git dir holds only the reviewed commit, by design since #2650). Matched only in the junit
# failure text of a head-failing test that has NO base result (#2665, P7). Only git's CLI
# message form counts: a ``fatal:``/``error:`` line, either at the start of a line or as the
# start of a captured ``stderr = '...'`` value (how pytest shows a failed subprocess.run's
# locals, the #535 shape); the same words in prose or an assertion message do not.
GIT_HISTORY_UNAVAILABLE_RE = re.compile(
    r"(?:^[ \t]*|\bstderr\s*=\s*b?['\"])(?:fatal|error): (?:git [a-z][a-z-]*: )?"
    r"(?:bad object [0-9a-f]{7,64}\b"
    r"|could not get object info"
    r"|bad revision '[^'\n]*'"
    r"|ambiguous argument '[^'\n]*': unknown revision or path not in the working tree"
    r"|[^\n'\"]*\bshallow\b)",
    re.MULTILINE,
)
ENV_PROBE_TMPDIR_WRITE = "import os, tempfile\nfd, path = tempfile.mkstemp()\nos.close(fd)\nos.unlink(path)\n"
# ``ModuleNotFoundError`` text in a pytest collection-error report (#2650).
MODULE_NOT_FOUND_RE = re.compile(r"ModuleNotFoundError: No module named '([A-Za-z_][A-Za-z0-9_.]*)'")
TOP_LEVEL_MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FIND_SPEC_PROBE = "import importlib.util, sys\nsys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)\n"


def _normalized_dist(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name.strip()).lower()


def _requirement_name(spec: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", spec or "")
    return _normalized_dist(match.group(1)) if match else ""


def _declared_names_from_requirements(text: str) -> set[str]:
    names: set[str] = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = _requirement_name(line)
        if name:
            names.add(name)
    return names


def _declared_names_from_pyproject(text: str) -> set[str]:
    """Normalized distribution names (and ``canonical-namespace`` values) a pyproject declares."""
    import tomllib

    try:
        doc = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return set()
    names: set[str] = set()
    specs: list[Any] = []
    raw_project = doc.get("project")
    project: dict[str, Any] = raw_project if isinstance(raw_project, dict) else {}
    specs.extend(project.get("dependencies") or [])
    optional = project.get("optional-dependencies")
    if isinstance(optional, dict):
        for group in optional.values():
            specs.extend(group or [])
    groups = doc.get("dependency-groups")
    if isinstance(groups, dict):
        for group in groups.values():
            specs.extend(group or [])
    for spec in specs:
        if isinstance(spec, str):
            name = _requirement_name(spec)
            if name:
                names.add(name)
    raw_tool = doc.get("tool")
    tool: dict[str, Any] = raw_tool if isinstance(raw_tool, dict) else {}
    raw_poetry = tool.get("poetry")
    poetry: dict[str, Any] = raw_poetry if isinstance(raw_poetry, dict) else {}
    for key in ("dependencies", "dev-dependencies"):
        declared = poetry.get(key)
        if isinstance(declared, dict):
            names.update(_normalized_dist(str(name)) for name in declared if str(name).lower() != "python")
    for section in tool.values():
        if isinstance(section, dict) and isinstance(section.get("canonical-namespace"), str):
            names.add(_normalized_dist(section["canonical-namespace"]))
    return names
LOGIC_BREAKER_TIMEOUT_SEC = 15
TEST_DIR_BY_SOURCE_DIR = {
    "app": "tests/app",
    "core": "tests/core",
    "delivery": "tests/delivery",
    "engine": "tests/engine",
    "health": "tests/health",
    "orchestrator": "tests/orchestrator",
    "research": "tests/research",
    "services": "tests/services",
}
SECURITY_PATTERNS = (
    # One whole quoted literal (same quote both ends, >= 8 non-quote non-space chars) assigned
    # to an identifier that ENDS with a credential keyword (so token_capture_status does not
    # match); never spans two literals (#2336, #2665).
    (
        "secret_literal",
        re.compile(
            r"(?i)\b\w*(?:api[_-]?key|access[_-]?key|secret(?:[_-]?key)?|token|password|passwd)"
            r"\s*=\s*(['\"])(?P<v>[^'\"\s]{8,})\1"
        ),
    ),
    ("shell_true_subprocess", re.compile(r"subprocess\.(run|Popen|call|check_output)\([^#\n]*shell\s*=\s*True")),
    ("unsafe_delete", re.compile(r"shutil\.rmtree\([^#\n]*(ignore_errors\s*=\s*True|force|/tmp|\*)")),
)
# secret_literal values that are marker words, not credentials (e.g. SECRET_OUT_OF_SCOPE_MARKER).
SECRET_MARKER_VALUE = re.compile(r"^[A-Z]+(?:_[A-Z]+)+$")
SECURITY_REPRO_TIMEOUT_SEC = 10
RUNTIME_ARTIFACT_PREFIXES = (
    ".nexus/reports/",
    ".nexus-swarm-",
)
BENCHMARK_ONLY_ENV_VARS = (
    "NEXUS_LLM_CANDIDATE_CAP",
)
ULTRA_REUSE_WORKTREE_ENV = "NEXUS_ULTRA_REUSE_WORKTREE"
ULTRA_SKIP_GHOST_ENV = "NEXUS_ULTRA_SKIP_GHOST_REGRESSION"
TOOL_CHECK_TIMEOUT_SEC = 60
# Static-analysis rules that are noise for a diff review (asserts, subprocess import,
# argument-list subprocess calls, partial executable paths, non-crypto random).
BANDIT_IGNORED_TESTS = frozenset({"B101", "B311", "B404", "B603", "B607"})
RUFF_SECURITY_IGNORED_CODES = frozenset({"S101", "S311", "S404", "S603", "S607"})
# Hardcoded-password heuristics: reported at low severity (as bandit rates B105-B107), so they
# never block on their own (#2665).
RUFF_LOW_SEVERITY_CODES = frozenset({"S105", "S106", "S107"})
# yaml.load is flagged (B506/S506) unless the Loader is one of these safe loaders (#2665).
YAML_LOAD_RULE_NUMBERS = frozenset({"B506", "S506"})
YAML_SAFE_LOADERS = frozenset({"BaseLoader", "SafeLoader", "CSafeLoader"})
# pyflakes/pycodestyle subset that means the changed code cannot run as written:
# syntax errors, invalid comparisons/statements, undefined names.
RUFF_LOGIC_SELECT = "E9,F63,F7,F82"
SECURITY_BLOCKING_SEVERITIES = frozenset({"medium", "high", "critical"})
REVIEW_MODE = "review"
# Set in the ghost-regression pytest environment: a review started from inside a review's
# test run (a test that reviews "."), would review the sandbox again; refuse instead.
ULTRA_REVIEW_NESTED_ENV = "NEXUS_ULTRA_REVIEW_IN_PROGRESS"
# Files whose change alters how the ghost-regression test run itself behaves.
# .pytest.ini / pytest.toml / .pytest.toml are pytest 9 config files (#2665 review).
TEST_HARNESS_FILES = (
    "conftest.py",
    "pytest.ini",
    "tox.ini",
    "setup.cfg",
    "pyproject.toml",
    "sitecustomize.py",
    "usercustomize.py",
    ".pytest.ini",
    "pytest.toml",
    ".pytest.toml",
)
# Shared config files: flagged only when their pytest/coverage configuration changes between
# the base ref and the head (a parse error on either side is still flagged). The other
# TEST_HARNESS_FILES are always flagged (#2665).
TEST_HARNESS_SECTION_SCOPED_FILES = ("pyproject.toml", "setup.cfg", "tox.ini")
DRY_RUN_MODE = "dry-run"


def _security_pattern_matches(rule_id: str, pattern: re.Pattern[str], content: str) -> bool:
    """True when ``pattern`` matches ``content``; a secret_literal whose value is an
    UPPER_SNAKE marker word is not a credential and does not count (#2665)."""
    if rule_id != "secret_literal":
        return pattern.search(content) is not None
    return any(
        not SECRET_MARKER_VALUE.match(match.group("v")) for match in pattern.finditer(content)
    )


def _pytest_config_sections(name: str, text: str) -> dict[str, Any]:
    """The pytest/coverage-relevant part of a shared config file (#2665).

    pyproject.toml: every ``tool.pytest*`` table plus ``project.entry-points.pytest11``.
    setup.cfg / tox.ini: the ``[tool:pytest]``, ``[pytest]`` and ``[coverage:*]`` sections.
    Raises ``ValueError`` when the text does not parse, so the caller fails closed.
    """
    if name == "pyproject.toml":
        import tomllib

        try:
            doc = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"toml_parse_error: {exc}") from exc
        tool = doc.get("tool")
        project = doc.get("project")
        entry_points = project.get("entry-points") if isinstance(project, dict) else None
        pytest_tables = (
            {k: v for k, v in tool.items() if str(k).startswith("pytest")}
            if isinstance(tool, dict)
            else {}
        )
        return {
            "tool": pytest_tables,
            "pytest11": entry_points.get("pytest11") if isinstance(entry_points, dict) else None,
        }
    # pytest's own ini parser: keys are case-sensitive and [DEFAULT] is an ordinary section,
    # exactly as pytest reads them (configparser would lowercase keys and merge DEFAULT).
    import iniconfig

    try:
        parsed = iniconfig.IniConfig(name, data=text)
    except iniconfig.ParseError as exc:
        raise ValueError(f"ini_parse_error: {exc}") from exc
    return {
        section.name: dict(section.items())
        for section in parsed
        if section.name in ("tool:pytest", "pytest") or section.name.startswith("coverage:")
    }


def _diff_file_states(diff_text: str) -> dict[str, str]:
    """``{path: "added" | "deleted"}`` for files the diff creates or deletes."""
    states: dict[str, str] = {}
    current = ""
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            parsed = re.match(r"^diff --git a/(.*) b/(.*)$", line)
            current = parsed.group(2) if parsed else ""
            continue
        if current and line.startswith("new file mode "):
            states[current] = "added"
        elif current and line.startswith("deleted file mode "):
            states[current] = "deleted"
    return states


def _yaml_load_uses_safe_loader(source: str, line: int) -> bool:
    """True only when every ``load``/``load_all`` call spanning ``line`` passes ``Loader=`` one
    of YAML_SAFE_LOADERS (bare or as ``yaml.<Name>``) and the file does not rebind that name;
    anything unparsable or ambiguous stays flagged (#2665)."""
    import ast

    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    rebound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            from_yaml = isinstance(node, ast.ImportFrom) and node.module == "yaml"
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                original = alias.name if isinstance(node, ast.ImportFrom) else top
                bound = alias.asname or original
                if bound != original or (isinstance(node, ast.ImportFrom) and not from_yaml):
                    rebound.add(bound)
            if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
                if not from_yaml:
                    return False  # a star import can bind any loader name
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            rebound.add(node.id)
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and isinstance(node.value, ast.Name)
            and node.value.id == "yaml"
        ):
            return False  # yaml.<X>Loader = ... patches the module for every later import
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("setattr", "delattr", "globals", "vars", "locals", "__import__")
        ):
            return False  # dynamic rebinding the AST cannot follow
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            rebound.add(node.name)
        elif isinstance(node, ast.arg):
            rebound.add(node.arg)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and node.lineno <= line <= (node.end_lineno or node.lineno)
        and (
            (isinstance(node.func, ast.Attribute) and node.func.attr in ("load", "load_all"))
            or (isinstance(node.func, ast.Name) and node.func.id in ("load", "load_all"))
        )
    ]
    if not calls:
        return False
    for call in calls:
        loader = next((kw.value for kw in call.keywords if kw.arg == "Loader"), None)
        positional = call.args
        starred = any(isinstance(arg, ast.Starred) for arg in positional)
        if loader is None and len(positional) >= 2 and not starred:
            loader = call.args[1]
        if isinstance(loader, ast.Attribute):
            safe = (
                loader.attr in YAML_SAFE_LOADERS
                and isinstance(loader.value, ast.Name)
                and loader.value.id == "yaml"
                and "yaml" not in rebound
            )
        elif isinstance(loader, ast.Name):
            safe = loader.id in YAML_SAFE_LOADERS and loader.id not in rebound
        else:
            safe = False
        if not safe:
            return False
    return True


class UltraReviewError(SandboxError):
    """Raised when ultra-review cannot produce a trustworthy report."""


def _as_review_error(func: Callable[..., _T]) -> Callable[..., _T]:
    """Re-raise a shared ``SandboxError`` as ``UltraReviewError`` (one type for callers)."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> _T:
        try:
            return func(*args, **kwargs)
        except UltraReviewError:
            raise
        except SandboxError as exc:
            raise UltraReviewError(str(exc)) from exc

    return wrapper


def _mode_phrase(mode: str) -> str:
    """How a finding summary names the run (review mode is not a dry-run, #2623)."""
    return "ultra-review dry-run" if mode == DRY_RUN_MODE else "ultra-review review mode"


sbpl_path = _as_review_error(_lane_sbpl_path)
_write_no_follow = _as_review_error(write_no_follow)


class UltraReviewService:
    def __init__(self, project_root: Path | str, *, test_timeout_sec: float | None = None):
        self.project_root = Path(project_root).resolve()
        if test_timeout_sec is not None and test_timeout_sec <= 0:
            raise ValueError("test_timeout_sec must be positive")
        self._test_timeout_sec = test_timeout_sec

    def _ghost_timeout_sec(self) -> float:
        """Ghost-regression pytest timeout: constructor value, else the env var, else the default."""
        if self._test_timeout_sec is not None:
            return float(self._test_timeout_sec)
        raw = os.getenv(ULTRA_TEST_TIMEOUT_ENV, "").strip()
        if raw:
            try:
                value = float(raw)
            except ValueError:
                value = 0.0
            if value > 0:
                return value
        return float(GHOST_REGRESSION_TIMEOUT_SEC)

    def run(
        self,
        *,
        dry_run: bool = True,
        task: str = "",
        base_ref: str = "HEAD",
        report_path: Path | str = ".nexus/reports/ultra_review_report.json",
        sandbox_root: Path | str = ".nexus/reports/ultra_review/sandboxes",
        regression_tests: Sequence[str] = (),
        excluded_tests: Sequence[str] = (),
    ) -> dict[str, Any]:
        """``regression_tests`` adds explicit ghost-regression tests (repo-relative, must exist);
        ``excluded_tests`` removes any mapped test whose path or file name matches (e.g. a hidden
        verifier test that must never run)."""
        mode = DRY_RUN_MODE if dry_run else REVIEW_MODE
        try:
            if os.getenv(ULTRA_REVIEW_NESTED_ENV, "").strip():
                raise UltraReviewError("nested_ultra_review_refused")
            try:
                return self._run(
                    dry_run=dry_run,
                    task=task,
                    base_ref=base_ref,
                    report_path=report_path,
                    sandbox_root=sandbox_root,
                    regression_tests=tuple(regression_tests),
                    excluded_tests=tuple(excluded_tests),
                )
            finally:
                # Safety net: a worktree's own .git file is always put back (#2650).
                self._restore_pending_git_swaps()
        except (SandboxError, OSError, subprocess.SubprocessError) as exc:
            # Fail closed with a reason instead of an unhandled traceback.
            out_path = self._resolve(report_path)
            payload = {
                "schema_version": SCHEMA_VERSION,
                "run_id": "",
                "status": "BLOCKED",
                "blocked_reason": f"{type(exc).__name__}: {exc}"[:500],
                "gate_passed": False,
                "mode": mode,
                "task": task,
                "base_ref": base_ref,
                "project_root": str(self.project_root),
                "fleet": [],
                "findings": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "report_path": str(out_path),
            }
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            except OSError:
                payload["report_path"] = ""
            return payload

    def _run(
        self,
        *,
        dry_run: bool,
        task: str,
        base_ref: str,
        report_path: Path | str,
        sandbox_root: Path | str,
        regression_tests: tuple[str, ...] = (),
        excluded_tests: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        mode = DRY_RUN_MODE if dry_run else REVIEW_MODE
        run_id = self._run_id()
        sandbox_path = self._prepare_sandbox(Path(sandbox_root), run_id)
        progress_path = sandbox_path / "progress.jsonl"
        progress: list[dict[str, Any]] = []
        self._record_progress(progress, progress_path, "sandbox_prepared", sandbox_path=str(sandbox_path))
        diff_text = self._capture_diff(base_ref)
        status_text = self._capture_status()

        diff_path = sandbox_path / "changes.diff"
        diff_path.write_text(diff_text, encoding="utf-8")
        (sandbox_path / "git_status.txt").write_text(status_text, encoding="utf-8")
        changed_files = self._changed_files(diff_text)
        self._record_progress(
            progress,
            progress_path,
            "diff_captured",
            changed_files=len(changed_files),
            bytes=len(diff_text.encode("utf-8")),
        )

        regression_map = self._derive_regression_candidate_map(diff_text)
        test_candidates = self._existing_regression_candidates(regression_map)
        test_candidates, excluded_regression_tests = self._apply_explicit_regression_tests(
            test_candidates, regression_tests=regression_tests, excluded_tests=excluded_tests
        )
        execution_root, mirror_metadata = self._prepare_execution_workspace(sandbox_path, diff_path=diff_path)
        mirror_violations = self._post_apply_violations(execution_root)
        if self._neutralized_head_links:
            mirror_metadata["neutralized_head_links"] = self._neutralized_head_links[:20]
        if mirror_violations:
            # Whatever the patch parser did, the mirror now holds a link/special entry: unlink
            # them (unlink never follows), mark the mirror unusable and fail the lane below.
            for rel in mirror_violations:
                try:
                    os.unlink(execution_root / rel)
                except OSError:
                    pass
            mirror_metadata["diff_applied"] = False
            mirror_metadata["post_apply_violations"] = mirror_violations[:20]
        self._bind_sandbox(sandbox_path=sandbox_path, execution_root=execution_root)
        mirror_git: dict[str, Any] = {}
        ghost_will_run = bool(
            test_candidates
            and os_sandbox_available()
            and os.getenv(ULTRA_SKIP_GHOST_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}
        )
        if (
            ghost_will_run
            and str(mirror_metadata.get("strategy") or "").startswith("git_worktree")
            and mirror_metadata.get("diff_applied")
        ):
            mirror_git = self._give_checkout_sandbox_git_dir(execution_root, rev="HEAD", diff_path=diff_path)
        # Capability probes run once, BEFORE any lane executes candidate-derived content, so
        # code under review cannot poison them (#2650).
        self._env_probe_failures = (
            self._environment_probe(execution_root, mirror_git_ok=bool(mirror_git.get("ok")))
            if ghost_will_run
            else []
        )
        security_sentry = self._run_security_sentry(
            diff_text=diff_text,
            execution_root=execution_root,
            sandbox_path=sandbox_path,
        )
        self._record_progress(
            progress,
            progress_path,
            "security_sentry_complete",
            passed=security_sentry["passed"],
            verified_findings=security_sentry["verified_findings"],
            unverified_observations=security_sentry["unverified_observations"],
        )
        logic_breaker = self._run_logic_breaker(
            diff_path=diff_path,
            execution_root=execution_root,
            sandbox_path=sandbox_path,
            mode=mode,
            base_ref=base_ref,
        )
        for rule_id, tool, paths, summary in (
            (
                "mirror_link_or_escape",
                "post-apply-lstat-walk",
                mirror_violations,
                "Applied mirror contains a symlink/special entry not tracked by HEAD: ",
            ),
            (
                "unsafe_patch_summary",
                "git-apply-summary",
                list(mirror_metadata.get("git_summary") or []),
                "git apply --summary reports link/gitlink/rename/copy (patch refused): ",
            ),
        ):
            if not paths:
                continue
            logic_breaker["passed"] = False
            logic_breaker["findings"].append(
                {
                    "id": f"logic-breaker-{len(logic_breaker['findings']) + 1}",
                    "lane": "logic_breaker",
                    "rule_id": rule_id,
                    "tool": tool,
                    "state": "VERIFIED_FINDING",
                    "severity": "high",
                    "file": paths[0],
                    "line": 0,
                    "repro_command": "",
                    "summary": summary + ", ".join(paths[:5]),
                    "execution_cwd": str(execution_root),
                }
            )
        self._record_progress(progress, progress_path, "logic_breaker_complete", passed=logic_breaker["passed"])
        explicit_tests = tuple(
            text for text in (str(rel).strip() for rel in regression_tests) if text and text in test_candidates
        )
        try:
            ghost_regression = self._run_ghost_regression(
                test_candidates,
                execution_root=execution_root,
                base_ref=base_ref,
                sandbox_path=sandbox_path,
                explicit_tests=explicit_tests,
                mode=mode,
            )
        finally:
            mirror_git_restore = self._restore_checkout_git_file(execution_root, mirror_git)
        if mirror_git:
            ghost_regression["sandbox_git_dir"] = {
                **{k: v for k, v in mirror_git.items() if k not in ("original", "restored_result")},
                "restore": mirror_git_restore,
            }
        ghost_regression["environment_probe_failures"] = list(self._env_probe_failures)
        unmapped_paths = [str(item.get("changed_file") or "") for item in regression_map if not item.get("existing")]
        ghost_regression["uncovered_paths"] = unmapped_paths
        if (
            changed_files
            and not ghost_regression.get("executed_tests")
            and not ghost_regression.get("blocked")
            and ghost_regression.get("execution_mode") != "skipped_by_env"
        ):
            # No mapped test (mapping is Python-only): advisory, never a block on its own (#2623).
            ghost_regression["coverage"] = "UNCOVERED"
            ghost_regression["findings"].append(
                {
                    "id": f"ghost-regression-{len(ghost_regression['findings']) + 1}",
                    "lane": "ghost_regression",
                    "rule_id": "no_mapped_tests",
                    "state": "UNCOVERED",
                    "severity": "info",
                    "file": unmapped_paths[0] if unmapped_paths else "",
                    "line": 0,
                    "repro_command": "",
                    "summary": "No regression test maps to the changed paths; ghost regression did not run"
                    " (advisory): " + ", ".join(unmapped_paths[:20]),
                    "unmapped_paths": unmapped_paths,
                    "execution_cwd": str(execution_root),
                }
            )
        self._record_progress(progress, progress_path, "ghost_regression_complete", passed=ghost_regression["passed"])
        findings = [*security_sentry["findings"], *logic_breaker["findings"], *ghost_regression["findings"]]
        sub_checks_passed = bool(security_sentry["passed"] and logic_breaker["passed"] and ghost_regression["passed"])
        fleet = self._build_dry_run_fleet(test_candidates, security_sentry, logic_breaker, ghost_regression)
        out_path = self._resolve(report_path)
        self._record_progress(progress, progress_path, "report_written", report_path=str(out_path))
        lanes_blocked = [
            lane_name
            for lane_name, lane in (
                ("security_sentry", security_sentry),
                ("logic_breaker", logic_breaker),
            )
            if lane.get("unavailable_checks")
        ]
        mirror_ok = bool(mirror_metadata.get("diff_applied", False))
        blocked_reason = ""
        if not changed_files:
            blocked_reason = "no_diff_to_review"
        elif not mirror_ok:
            blocked_reason = "sandbox_mirror_diff_not_applied"
        elif lanes_blocked:
            blocked_reason = "check_tool_unavailable:" + ",".join(lanes_blocked)
        elif ghost_regression.get("blocked"):
            blocked_reason = f"ghost_regression_not_executed:{ghost_regression.get('blocked_reason')}"
        elif ghost_regression.get("execution_mode") == "skipped_by_env":
            blocked_reason = "ghost_regression_not_executed:skipped_by_env"
        elif not security_sentry.get("executed_checks") or not logic_breaker.get("executed_checks"):
            blocked_reason = "lane_not_executed"
        if dry_run:
            # Dry-run is advisory: checks execute but a clean dry-run is NOT_VERIFIED, never a pass.
            gate_passed = False
            status = "DRY_RUN_NOT_VERIFIED" if sub_checks_passed else "DRY_RUN_FAIL"
        else:
            # Review mode: the gate is the conjunction of executed lane results; fail closed when
            # there is nothing to review or a required check could not run.
            if blocked_reason:
                gate_passed = False
                status = "BLOCKED"
            elif sub_checks_passed and ghost_regression.get("inconclusive"):
                # A timeout or an unpreparable base proves nothing either way: not a pass,
                # and not a verified failure (#2623).
                gate_passed = False
                status = "INCONCLUSIVE"
            else:
                gate_passed = sub_checks_passed
                status = "PASS" if sub_checks_passed else "FAIL"
        worktree_cleanup = self._cleanup_execution_worktree(execution_root, mirror_metadata) if not dry_run else {}
        payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "status": status,
            "blocked_reason": blocked_reason if not dry_run else "",
            "gate_passed": gate_passed,
            "mode": mode,
            "worktree_cleanup": worktree_cleanup,
            "isolation": self.sandbox_isolation(),
            "task": task,
            "base_ref": base_ref,
            "project_root": str(self.project_root),
            "sandbox_path": str(sandbox_path),
            "sandbox_mirror": mirror_metadata,
            "artifacts": {
                "diff": str(diff_path),
                "git_status": str(sandbox_path / "git_status.txt"),
                "progress_log": str(progress_path),
            },
            "diff": {
                "bytes": len(diff_text.encode("utf-8")),
                "changed_files": changed_files,
                "has_worktree_delta": bool(diff_text.strip() or status_text.strip()),
            },
            "fleet": fleet,
            "findings": findings,
            "security_sentry": {k: v for k, v in security_sentry.items() if k != "findings"},
            "logic_breaker": {k: v for k, v in logic_breaker.items() if k != "findings"},
            "ghost_regression": {k: v for k, v in ghost_regression.items() if k != "findings"},
            "summary": {
                "security_verified_findings": security_sentry["verified_findings"],
                "security_unverified_observations": security_sentry["unverified_observations"],
                "logic_breaker_passed": logic_breaker["passed"],
                "ghost_regression_passed": ghost_regression["passed"],
                "executed_regression_tests": len(ghost_regression["executed_tests"]),
                "ghost_regression_inconclusive": bool(ghost_regression.get("inconclusive")),
                "pre_existing_test_failures": len(ghost_regression.get("pre_existing_failures") or []),
                "uncovered_paths": len(unmapped_paths),
                "verified_findings": sum(1 for finding in findings if finding.get("state") == "VERIFIED_FINDING"),
            },
            "progress": progress,
            "regression_candidate_map": regression_map,
            "excluded_regression_tests": excluded_regression_tests,
            "verification": {
                "verified_findings": sum(1 for finding in findings if finding.get("state") == "VERIFIED_FINDING"),
                "unverified_observations": sum(1 for finding in findings if finding.get("state") != "VERIFIED_FINDING"),
                "reproduction_required": True,
                "negative_test_execution": "executed" if test_candidates else "not_applicable_no_candidates",
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "report_path": str(out_path),
        }

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return payload

    def _record_progress(self, progress: list[dict[str, Any]], progress_path: Path, stage: str, **fields: Any) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            **fields,
        }
        progress.append(event)
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        with progress_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def _prepare_sandbox(self, sandbox_root: Path, run_id: str) -> Path:
        root = self._resolve(sandbox_root)
        root.mkdir(parents=True, exist_ok=True)
        sandbox_path = root / run_id
        sandbox_path.mkdir(parents=False, exist_ok=False)
        git_home = sandbox_path / "git-home"
        git_home.mkdir()
        self._git_home = git_home.resolve()
        (sandbox_path / "README.txt").write_text(
            "Nexus ultra-review dry-run sandbox. Contains captured diff artifacts only.\n",
            encoding="utf-8",
        )
        return sandbox_path

    def _benchmark_env_keys_removed(self) -> list[str]:
        removed: list[str] = []
        for key in BENCHMARK_ONLY_ENV_VARS:
            if key in os.environ:
                removed.append(key)
        return removed

    def _prepare_execution_workspace(self, sandbox_path: Path, *, diff_path: Path) -> tuple[Path, dict[str, Any]]:
        diff_text = diff_path.read_text(encoding="utf-8") if diff_path.exists() else ""
        violations = self._diff_policy_violations(diff_text)
        # Git's own parser is the authority on what the patch does; the hand parser above
        # is only a fast pre-filter. Unparseable or link/rename/copy patches are refused.
        violations["git_summary"] = self._unsafe_patch_summary(diff_path) if diff_text.strip() else []
        if violations["git_summary"] and not violations["symlinks"]:
            violations["symlinks"] = [line.strip() for line in violations["git_summary"]]
        if violations["symlinks"] or violations["nested_git"]:
            # Never apply a patch that creates/edits a symlink or touches a .git path: the
            # mirror stays empty, the lanes find nothing to verify and the gate fails closed.
            execution_root = sandbox_path / "worktree"
            execution_root.mkdir()
            return execution_root, {
                "strategy": "refused",
                "diff_applied": False,
                "refused_reason": "diff_creates_symlink" if violations["symlinks"] else "diff_touches_git_dir",
                "symlinks": violations["symlinks"][:20],
                "nested_git": violations["nested_git"][:20],
                "git_summary": violations["git_summary"][:20],
            }
        if os.getenv(ULTRA_REUSE_WORKTREE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
            reusable_root = self._resolve(".nexus/reports/ultra_review/reusable_worktree")
            reusable_root.mkdir(parents=True, exist_ok=True)
            execution_root = reusable_root / "worktree"
            metadata = self._prepare_reusable_git_worktree(execution_root, diff_path=diff_path, sandbox_path=sandbox_path)
            if metadata.get("strategy") == "git_worktree_reuse":
                return execution_root, metadata
        execution_root = sandbox_path / "worktree"
        metadata = self._prepare_git_worktree_mirror(execution_root, diff_path=diff_path, sandbox_path=sandbox_path)
        if metadata.get("strategy") == "git_worktree":
            return execution_root, metadata

        fallback_metadata = self._copy_execution_workspace(execution_root, sandbox_path)
        fallback_metadata["fallback_reason"] = metadata.get("fallback_reason", "")
        return execution_root, fallback_metadata

    def _prepare_reusable_git_worktree(self, execution_root: Path, *, diff_path: Path, sandbox_path: Path) -> dict[str, Any]:
        if not (execution_root / ".git").exists():
            add_cmd = ["git", "worktree", "add", "--detach", str(execution_root), "HEAD"]
            add = self._git_run(add_cmd[1:])
            if add.returncode != 0:
                return {
                    "strategy": "copytree",
                    "fallback_reason": (add.stderr or add.stdout or "reusable git worktree add failed")[-1000:],
                }
            created = True
        else:
            created = False

        reset_cmd = ["git", "reset", "--hard", "HEAD"]
        clean_cmd = ["git", "clean", "-fd"]
        reset = self._git_run(reset_cmd[1:], mirror=execution_root)
        clean = self._git_run(clean_cmd[1:], mirror=execution_root)
        if reset.returncode != 0 or clean.returncode != 0:
            return {
                "strategy": "copytree",
                "fallback_reason": (
                    reset.stderr
                    or clean.stderr
                    or reset.stdout
                    or clean.stdout
                    or "reusable git worktree reset/clean failed"
                )[-1000:],
            }

        diff_has_content = bool(diff_path.read_text(encoding="utf-8").strip()) if diff_path.exists() else False
        if diff_has_content:
            apply_cmd = ["git", "apply", "--binary", str(diff_path)]
            apply = self._git_run(apply_cmd[1:], mirror=execution_root)
            if apply.returncode != 0:
                return {
                    "strategy": "copytree",
                    "fallback_reason": (apply.stderr or apply.stdout or "reusable git apply failed")[-1000:],
                }

        untracked_overlay_count = self._overlay_untracked_files(execution_root, sandbox_path=sandbox_path)
        return {
            "strategy": "git_worktree_reuse",
            "diff_applied": True,
            "empty_diff": not diff_has_content,
            "reused": not created,
            "untracked_overlay_count": untracked_overlay_count,
        }

    def _prepare_git_worktree_mirror(self, execution_root: Path, *, diff_path: Path, sandbox_path: Path) -> dict[str, Any]:
        add_cmd = ["git", "worktree", "add", "--detach", str(execution_root), "HEAD"]
        add = self._git_run(add_cmd[1:])
        if add.returncode != 0:
            return {
                "strategy": "copytree",
                "fallback_reason": (add.stderr or add.stdout or "git worktree add failed")[-1000:],
            }

        diff_has_content = bool(diff_path.read_text(encoding="utf-8").strip()) if diff_path.exists() else False
        if not diff_has_content:
            untracked_overlay_count = self._overlay_untracked_files(execution_root, sandbox_path=sandbox_path)
            return {
                "strategy": "git_worktree",
                "diff_applied": True,
                "command": " ".join(add_cmd),
                "untracked_overlay_count": untracked_overlay_count,
                "empty_diff": True,
            }

        apply_cmd = ["git", "apply", "--index", "--binary", str(diff_path)]
        apply = self._git_run(apply_cmd[1:], mirror=execution_root)
        if apply.returncode != 0:
            apply_cmd = ["git", "apply", "--binary", str(diff_path)]
            apply = self._git_run(apply_cmd[1:], mirror=execution_root)
        if apply.returncode != 0:
            self._git_run(["worktree", "remove", "--force", str(execution_root)])
            return {
                "strategy": "copytree",
                "diff_applied": False,
                "fallback_reason": (apply.stderr or apply.stdout or "git apply failed")[-1000:],
                "command": " ".join(add_cmd),
            }

        untracked_overlay_count = self._overlay_untracked_files(execution_root, sandbox_path=sandbox_path)
        return {
            "strategy": "git_worktree",
            "diff_applied": True,
            "command": " ".join(add_cmd),
            "untracked_overlay_count": untracked_overlay_count,
        }

    def _overlay_untracked_files(self, execution_root: Path, *, sandbox_path: Path) -> int:
        ls = subprocess.run(  # noqa: S603 - argv list, no shell
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=self.project_root,
            env=self._git_env(),
            capture_output=True,
            text=False,
            check=False,
        )
        if ls.returncode != 0:
            return 0
        count = 0
        for raw in ls.stdout.split(b"\0"):
            if not raw:
                continue
            rel = raw.decode("utf-8", errors="ignore")
            if self._is_runtime_artifact_path(rel):
                continue
            source = self.project_root / rel
            target = execution_root / rel
            try:
                if source.resolve().is_relative_to(sandbox_path.resolve()):
                    continue
            except OSError:
                continue
            if source.is_symlink() or not source.is_file():
                # Never follow an untracked symlink into the sandbox (it could point at a
                # credential file outside the checkout).
                continue
            try:
                if not source.resolve().is_relative_to(self.project_root):
                    continue
            except OSError:
                continue
            if not self._target_inside(target, execution_root):
                # A PR-tracked symlinked directory (or file) at the target must not redirect
                # the overlay write outside the mirror.
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if not self._target_inside(target, execution_root):
                continue
            _write_no_follow(target, source.read_bytes())
            count += 1
        return count

    @staticmethod
    def _target_inside(target: Path, execution_root: Path) -> bool:
        """True when no existing component of ``target`` below ``execution_root`` is a symlink."""

        root = execution_root.resolve()
        try:
            rel_parts = target.relative_to(execution_root).parts
        except ValueError:
            return False
        if ".." in rel_parts:
            return False
        current = execution_root
        for part in rel_parts:
            current = current / part
            if current.is_symlink():
                return False
        parent = target.parent.resolve() if target.parent.exists() else None
        return parent is None or parent == root or root in parent.parents

    def _copy_execution_workspace(self, execution_root: Path, sandbox_path: Path) -> dict[str, Any]:
        ignored_patterns = shutil.ignore_patterns(
            ".git",
            ".venv",
            ".nexus",
            ".pytest_cache",
            "__pycache__",
            "MagicMock",
            "compliance/audit",
        )

        def ignore(path: str, names: list[str]) -> set[str]:
            ignored = set(ignored_patterns(path, names))
            # Never copy a symlink (dangling or not): following it could pull a file from
            # outside the checkout (for example a credential) into the mirror.
            ignored.update(name for name in names if os.path.islink(os.path.join(path, name)))
            current = Path(path).resolve()
            if current == self.project_root:
                try:
                    sandbox_anchor = sandbox_path.relative_to(self.project_root).parts[0]
                except ValueError:
                    sandbox_anchor = ""
                if sandbox_anchor in names:
                    ignored.add(sandbox_anchor)
            return ignored

        # Runtime-local links (for example user-specific Gemini state or an
        # unbuilt native extension) may be dangling in the source checkout.
        # They are not review inputs and must not make the fallback mirror
        # fail before the actual diff is evaluated.
        shutil.copytree(
            self.project_root,
            execution_root,
            ignore=ignore,
            # Defence in depth: symlinks are already ignored above; never dereference one.
            symlinks=True,
            ignore_dangling_symlinks=True,
        )
        return {"strategy": "copytree", "diff_applied": True}

    def _bind_sandbox(self, *, sandbox_path: Path, execution_root: Path) -> None:
        home = sandbox_path / "home"
        tmp = sandbox_path / "tmp"
        home.mkdir(parents=True, exist_ok=True)
        tmp.mkdir(parents=True, exist_ok=True)
        self._sandbox_ctx = {
            "sandbox_path": Path(sbpl_path(sandbox_path.resolve())),
            "execution_root": Path(sbpl_path(execution_root.resolve())),
            "home": Path(sbpl_path(home.resolve())),
            "tmp": Path(sbpl_path(tmp.resolve())),
        }

    def _sandbox_env(self) -> dict[str, str]:
        ctx = getattr(self, "_sandbox_ctx", None) or {}
        # PATH never resolves into the reviewed checkout, the mirror or the sandbox, so a
        # PR-supplied executable cannot shadow a tool. Every Python lane runs with -I, so
        # PYTHONPATH is not set at all (the ghost re-run gets the mirror via pytest's
        # ``pythonpath`` ini override after interpreter start-up).
        env = scrubbed_env(
            home=ctx.get("home") or "",
            tmp=ctx.get("tmp") or "",
            untrusted_roots=(self.project_root, ctx.get("execution_root"), ctx.get("sandbox_path")),
        )
        # ``python3`` inside the sandbox resolves to the reviewer's interpreter first (#2665,
        # P7), unless that interpreter itself lives in a reviewed tree.
        untrusted = (self.project_root, ctx.get("execution_root"), ctx.get("sandbox_path"))
        interpreter_bin = os.path.dirname(sys.executable)
        if os.path.isabs(interpreter_bin) and not in_tree(interpreter_bin, untrusted):
            parts = env.get("PATH", "").split(os.pathsep)
            rest = [part for part in parts if part and part != interpreter_bin]
            env["PATH"] = os.pathsep.join([interpreter_bin, *rest])
        env[ULTRA_REVIEW_NESTED_ENV] = "1"
        if ctx.get("tmp"):
            # xcrun caches into the per-user temp dir (outside the sandbox) unless told
            # otherwise; keep its cache in the sandbox tmp so git prints no cache errors (#2650).
            env["xcrun_db"] = str(Path(ctx["tmp"]) / "xcrun_db")
        return env

    @_as_review_error
    def _sandbox_profile(self) -> str:
        """SBPL policy for one lane command (see ``sandboxed_lane.build_sandbox_profile``).

        Reads: default-deny; only the sandbox/mirror, the trusted interpreter prefixes and
        fixed system locations are readable; ``$HOME`` and credential stores are denied.
        """

        ctx = getattr(self, "_sandbox_ctx", None) or {}
        if not ctx.get("execution_root") or not ctx.get("sandbox_path"):
            raise UltraReviewError("sandbox_not_bound")
        return build_sandbox_profile(
            writable=[ctx["execution_root"], ctx["sandbox_path"]],
            read_roots=self._sandbox_read_roots(),
        )

    @_as_review_error
    def _sandbox_read_roots(self) -> list[str]:
        """Readable subtrees: the sandbox (mirror included) and the trusted interpreter
        prefixes only, plus the system subpaths. No repository root, no
        ``$HOME``/``/Users``/temp tree; any such root fails closed."""

        ctx = getattr(self, "_sandbox_ctx", None) or {}
        # tool_read_roots: /usr/bin/shasum and the active developer dir, so the xcrun git shim
        # and Perl tools work inside the sandbox (#2650); validated like every other root.
        # Read-only, reviewer-built git dirs for the mirror and base checkout (#2650).
        git_roots = [str(path) for path in ctx.get("git_read_roots") or []]
        return checked_read_roots(
            [ctx["execution_root"], ctx["sandbox_path"], *interpreter_read_roots(), *tool_read_roots(), *git_roots],
            extra_forbidden=[self.project_root],
        )

    def _in_untrusted_tree(self, path: Path | str) -> bool:
        """True when ``path`` resolves into the reviewed checkout, the mirror or the sandbox."""

        ctx = getattr(self, "_sandbox_ctx", None) or {}
        return in_tree(path, (self.project_root, ctx.get("execution_root"), ctx.get("sandbox_path")))

    def _trusted_interpreter(self) -> str:
        """The reviewer's own interpreter; refused if it lives in the mirror or the sandbox."""

        ctx = getattr(self, "_sandbox_ctx", None) or {}
        interpreter = Path(sys.executable).resolve()
        for root in (ctx.get("execution_root"), ctx.get("sandbox_path")):
            if root and (interpreter == Path(root) or Path(root) in interpreter.parents):
                raise UltraReviewError("interpreter_inside_reviewed_tree")
        return sys.executable

    def sandbox_isolation(self) -> dict[str, Any]:
        contained = os_sandbox_available()
        return {
            "barrier": "macos_sandbox_exec" if contained else "none",
            "network": "denied" if contained else "not_enforced",
            "writes_confined_to": [
                str((getattr(self, "_sandbox_ctx", None) or {}).get(key) or "")
                for key in ("execution_root", "sandbox_path")
            ]
            if contained
            else [],
            "env": "allowlist:" + ",".join(SANDBOX_ENV_ALLOWLIST) + "+HOME/TMPDIR in sandbox",
            "credential_paths_read_denied": list(SANDBOX_DENIED_HOME_PATHS) if contained else [],
        }

    @_as_review_error
    def _sandboxed_run(
        self,
        cmd: list[str],
        *,
        cwd: Path,
        timeout: float,
        stdin_text: str | None = None,
        kill_process_group: bool = False,
    ) -> subprocess.CompletedProcess:
        """Run a lane command on PR-controlled content: scrubbed env, sandbox cwd, timeout,
        and (when available) an OS barrier denying network, credential reads and writes
        outside the sandbox. Never a shell; raises subprocess.TimeoutExpired on timeout."""
        argv = list(cmd)
        if not argv:
            raise UltraReviewError("empty_lane_command")
        if argv[0] == sys.executable:
            argv[0] = self._trusted_interpreter()
            if "-I" not in argv[1:2]:
                raise UltraReviewError("python_lane_not_isolated")
        ctx = getattr(self, "_sandbox_ctx", None) or {}
        return run_confined(
            argv,
            cwd=Path(cwd),
            confine_roots=(ctx.get("execution_root"), ctx.get("sandbox_path")),
            profile=self._sandbox_profile,
            env=self._sandbox_env(),
            timeout=timeout,
            stdin_text=stdin_text,
            kill_process_group=kill_process_group,
        )

    def _cleanup_execution_worktree(self, execution_root: Path, mirror_metadata: dict[str, Any]) -> dict[str, Any]:
        """Remove the per-run git worktree registration (review artifacts stay in the sandbox)."""
        strategy = str(mirror_metadata.get("strategy") or "")
        if strategy == "git_worktree":
            removed = self._git_run(["worktree", "remove", "--force", str(execution_root)])
            return {
                "strategy": strategy,
                "removed": removed.returncode == 0,
                "detail": (removed.stderr or removed.stdout or "")[-300:],
            }
        if strategy == "copytree" and execution_root.exists():
            shutil.rmtree(execution_root, ignore_errors=False)
            return {"strategy": strategy, "removed": True, "detail": ""}
        return {"strategy": strategy, "removed": False, "detail": "kept_for_reuse_or_missing"}

    def _added_lines(self, diff_text: str) -> dict[str, set[int]]:
        """New-side line numbers added by the diff, per changed file."""
        added: dict[str, set[int]] = {}
        current_file = ""
        new_line = 0
        for raw_line in diff_text.splitlines():
            if raw_line.startswith("diff --git "):
                current_file = self._path_from_diff_header(raw_line)
                new_line = 0
                continue
            if raw_line.startswith("@@"):
                parsed = re.search(r"\+(\d+)", raw_line)
                new_line = int(parsed.group(1)) - 1 if parsed else 0
                continue
            if raw_line.startswith("+++") or raw_line.startswith("---"):
                continue
            if raw_line.startswith("+"):
                new_line += 1
                if current_file:
                    added.setdefault(current_file, set()).add(new_line)
                continue
            if raw_line.startswith("-") or raw_line.startswith("\\"):
                continue
            if current_file:
                new_line += 1
        return added

    def _contained_path(self, rel: str, execution_root: Path) -> Path | None:
        """``execution_root/rel`` when it stays inside the worktree and is not a symlink."""
        root = execution_root.resolve()
        candidate = execution_root / rel
        if candidate.is_symlink():
            return None
        resolved = candidate.resolve()
        if resolved != root and root not in resolved.parents:
            return None
        return resolved

    def _uncontained_changed_files(self, diff_text: str, execution_root: Path) -> list[str]:
        # A path the diff makes a symlink is never contained, whether or not it was applied.
        symlinks = set(self._diff_policy_violations(diff_text)["symlinks"])
        return [
            rel
            for rel in self._changed_files(diff_text)
            if rel in symlinks
            or (
                ((execution_root / rel).exists() or (execution_root / rel).is_symlink() or ".." in Path(rel).parts)
                and self._contained_path(rel, execution_root) is None
            )
        ]

    def _changed_python_files(self, diff_text: str, execution_root: Path) -> list[str]:
        out: list[str] = []
        for rel in self._changed_files(diff_text):
            if not rel.endswith(".py"):
                continue
            contained = self._contained_path(rel, execution_root)
            if contained is not None and contained.is_file():
                out.append(rel)
        return out

    def _run_tool(self, cmd: list[str], *, cwd: Path) -> dict[str, Any]:
        try:
            result = self._sandboxed_run(cmd, cwd=cwd, timeout=TOOL_CHECK_TIMEOUT_SEC)
        except FileNotFoundError as exc:
            return {"available": False, "error": str(exc)[:300], "command": " ".join(cmd)}
        except subprocess.TimeoutExpired:
            return {"available": True, "timeout": True, "returncode": None, "stdout": "", "stderr": "", "command": " ".join(cmd)}
        stderr = result.stderr or ""
        if result.returncode != 0 and "No module named" in stderr:
            return {"available": False, "error": stderr.strip()[-300:], "command": " ".join(cmd)}
        return {
            "available": True,
            "timeout": False,
            "returncode": result.returncode,
            "stdout": result.stdout or "",
            "stderr": stderr,
            "command": " ".join(cmd),
        }

    def _relative_to_root(self, filename: str, execution_root: Path) -> str:
        path = Path(filename)
        if path.is_absolute():
            try:
                return path.resolve().relative_to(execution_root.resolve()).as_posix()
            except ValueError:
                return path.as_posix()
        text = path.as_posix()
        while text.startswith("./"):
            text = text[2:]
        return text

    def _bandit_findings(
        self, py_files: list[str], *, execution_root: Path, added: dict[str, set[int]]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        # Absolute paths from the sandbox dir: a PR-supplied .bandit config is not read, and
        # --ignore-nosec stops the diff from silencing its own findings.
        targets = [str((execution_root / rel).resolve()) for rel in py_files]
        cmd = [sys.executable, "-I", "-m", "bandit", "-f", "json", "-q", "--ignore-nosec", *targets]
        ctx = getattr(self, "_sandbox_ctx", None) or {}
        run = self._run_tool(cmd, cwd=Path(ctx.get("sandbox_path") or execution_root))
        if not run.get("available") or run.get("timeout"):
            return run, []
        try:
            data = json.loads(run.get("stdout") or "{}")
        except json.JSONDecodeError:
            run["available"] = False
            run["error"] = "bandit_output_not_json"
            return run, []
        findings: list[dict[str, Any]] = []
        for item in data.get("results") or []:
            test_id = str(item.get("test_id") or "")
            if test_id in BANDIT_IGNORED_TESTS:
                continue
            rel = self._relative_to_root(str(item.get("filename") or ""), execution_root)
            line = int(item.get("line_number") or 0)
            if line not in added.get(rel, set()):
                continue
            if test_id in YAML_LOAD_RULE_NUMBERS and self._safe_yaml_load_at(
                execution_root, rel, line
            ):
                continue
            findings.append(
                {
                    "lane": "security_sentry",
                    "rule_id": f"bandit:{test_id}",
                    "tool": "bandit",
                    "state": "VERIFIED_FINDING",
                    "severity": str(item.get("issue_severity") or "").lower() or "low",
                    "confidence": str(item.get("issue_confidence") or "").lower(),
                    "file": rel,
                    "line": line,
                    "repro_command": run["command"],
                    "execution_cwd": str(execution_root),
                    "summary": str(item.get("issue_text") or "")[:300],
                }
            )
        run["errors"] = list(data.get("errors") or [])[:5]
        return run, findings

    def _ruff_findings(
        self,
        py_files: list[str],
        *,
        execution_root: Path,
        added: dict[str, set[int]],
        select: str,
        lane: str,
        ignored: frozenset[str] = frozenset(),
        added_only: bool = True,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        cmd = [
            sys.executable,
            "-I",
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--isolated",
            "--ignore-noqa",
            "--select",
            select,
            "--output-format",
            "json",
            *py_files,
        ]
        run = self._run_tool(cmd, cwd=execution_root)
        if not run.get("available") or run.get("timeout"):
            return run, []
        try:
            data = json.loads(run.get("stdout") or "[]")
        except json.JSONDecodeError:
            run["available"] = False
            run["error"] = "ruff_output_not_json"
            return run, []
        findings: list[dict[str, Any]] = []
        for item in data if isinstance(data, list) else []:
            code = str(item.get("code") or "")
            if not code or code in ignored:
                continue
            rel = self._relative_to_root(str(item.get("filename") or ""), execution_root)
            line = int(((item.get("location") or {}).get("row")) or 0)
            if added_only and line not in added.get(rel, set()):
                continue
            if code in YAML_LOAD_RULE_NUMBERS and self._safe_yaml_load_at(
                execution_root, rel, line
            ):
                continue
            if lane == "security_sentry":
                severity = "low" if code in RUFF_LOW_SEVERITY_CODES else "medium"
            else:
                severity = "high"
            findings.append(
                {
                    "lane": lane,
                    "rule_id": f"ruff:{code}",
                    "tool": "ruff",
                    "state": "VERIFIED_FINDING",
                    "severity": severity,
                    "file": rel,
                    "line": line,
                    "repro_command": run["command"],
                    "execution_cwd": str(execution_root),
                    "summary": str(item.get("message") or "")[:300],
                }
            )
        return run, findings

    def _harness_changes(self, diff_text: str, *, execution_root: Path, base_ref: str) -> list[str]:
        """Changed test-harness files. conftest.py, pytest.ini and the *customize.py files always
        count; pyproject.toml / setup.cfg / tox.ini count only when their pytest/coverage
        configuration differs between ``base_ref`` (read with ``git show``, never from the
        candidate tree) and the applied head mirror. Anything unreadable or unparsable counts
        (fail closed) (#2665)."""
        states = _diff_file_states(diff_text)
        harness: list[str] = []
        for rel in self._changed_files(diff_text):
            name = Path(rel).name
            if name not in TEST_HARNESS_FILES:
                continue
            if name not in TEST_HARNESS_SECTION_SCOPED_FILES or self._harness_config_changed(
                rel,
                name,
                execution_root=execution_root,
                base_ref=base_ref,
                state=states.get(rel, ""),
            ):
                harness.append(rel)
        return harness

    def _harness_config_changed(
        self, rel: str, name: str, *, execution_root: Path, base_ref: str, state: str
    ) -> bool:
        if state == "added":
            base_text = ""
        else:
            if not base_ref or base_ref.startswith("-"):
                return True
            shown = subprocess.run(  # noqa: S603 - argv list, no shell
                ["git", "show", f"{base_ref}:{rel}"],
                cwd=self.project_root,
                env=self._git_env(),
                capture_output=True,
                check=False,
            )
            if shown.returncode != 0:
                return True
            try:
                base_text = shown.stdout.decode("utf-8")
            except UnicodeDecodeError:
                return True
        if state == "deleted":
            head_text = ""
        else:
            target = self._contained_path(rel, execution_root)
            if target is None:
                return True
            try:
                if not stat.S_ISREG(os.lstat(target).st_mode):
                    return True
                head_text = target.read_bytes().decode("utf-8")
            except (OSError, UnicodeDecodeError):
                return True
            if state != "added" and head_text == base_text:
                # The diff says this file changed, but the mirror still holds the base
                # content: the patch did not land, so nothing can be compared.
                return True
        try:
            base_sections = _pytest_config_sections(name, base_text)
            return base_sections != _pytest_config_sections(name, head_text)
        except ValueError:
            return True

    def _safe_yaml_load_at(self, execution_root: Path, rel: str, line: int) -> bool:
        """True when the flagged yaml.load at ``rel:line`` uses a safe Loader (#2665)."""
        target = self._contained_path(rel, execution_root)
        if target is None:
            return False
        try:
            if not stat.S_ISREG(os.lstat(target).st_mode):
                return False
            source = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return False
        return _yaml_load_uses_safe_loader(source, line)

    def _capture_diff(self, base_ref: str) -> str:
        return self._filter_diff(
            self._git(["diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--binary", base_ref])
        )

    def _capture_status(self) -> str:
        lines: list[str] = []
        for line in self._git(["status", "--short"]).splitlines():
            path = line[3:] if len(line) > 3 else ""
            if path.startswith('"') and " -> " not in path:
                path = path.strip('"')
            if " -> " in path:
                path = path.rsplit(" -> ", 1)[-1].strip('"')
            if path and self._is_runtime_artifact_path(path):
                continue
            lines.append(line)
        return "\n".join(lines) + ("\n" if lines else "")

    def _filter_diff(self, diff_text: str) -> str:
        chunks: list[list[str]] = []
        current: list[str] = []
        for line in diff_text.splitlines(keepends=True):
            if line.startswith("diff --git "):
                if current:
                    chunks.append(current)
                current = [line]
                continue
            if current:
                current.append(line)
            else:
                chunks.append([line])
        if current:
            chunks.append(current)

        kept: list[str] = []
        for chunk in chunks:
            header = chunk[0] if chunk else ""
            if header.startswith("diff --git "):
                path = self._path_from_diff_header(header.rstrip("\n"))
                if path and self._is_runtime_artifact_path(path):
                    continue
            kept.extend(chunk)
        return "".join(kept)

    def _derive_regression_candidate_map(self, diff_text: str) -> list[dict[str, Any]]:
        candidate_map: list[dict[str, Any]] = []
        for changed in self._changed_files(diff_text):
            path = Path(changed)
            if not path.parts:
                continue
            candidates = self._candidate_tests_for_changed_file(path)
            existing = [candidate for candidate in candidates if (self.project_root / candidate).exists()]
            candidate_map.append(
                {
                    "changed_file": changed,
                    "candidates": candidates,
                    "existing": existing,
                    "skipped": [candidate for candidate in candidates if candidate not in existing],
                    "status": "READY" if existing else "SKIPPED",
                    "skip_reason": "" if existing else "no_existing_regression_candidates",
                }
            )
        return candidate_map

    def _candidate_tests_for_changed_file(self, path: Path) -> list[str]:
        candidates: list[str] = []
        top = path.parts[0] if path.parts else ""
        if top == "nexus" and path.suffix == ".py":
            stem = path.stem
            module_dir = path.parts[1] if len(path.parts) > 1 else ""
            test_dir = TEST_DIR_BY_SOURCE_DIR.get(module_dir, f"tests/{module_dir}" if module_dir else "tests")
            candidates.extend(
                [
                    f"{test_dir}/test_{stem}.py",
                    f"tests/test_{stem}.py",
                ]
            )
        if top == "scripts" and path.suffix == ".py":
            script_area = path.parts[1] if len(path.parts) > 1 else ""
            test_dir = "tests/ops" if script_area == "ops" else "tests/engine"
            candidates.append(f"{test_dir}/test_{path.stem}.py")
        if top not in {"nexus", "scripts"} and path.suffix == ".py":
            if path.name.startswith("test_"):
                # A changed test file is its own regression candidate.
                candidates.append(path.as_posix())
            else:
                parent = path.parent.as_posix()
                candidates.extend(
                    [
                        f"tests/test_{path.stem}.py",
                        f"{parent}/test_{path.stem}.py" if parent not in ("", ".") else f"test_{path.stem}.py",
                    ]
                )

        seen: set[str] = set()
        deduped: list[str] = []
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                deduped.append(candidate)
        return deduped

    def _apply_explicit_regression_tests(
        self,
        test_candidates: list[str],
        *,
        regression_tests: Sequence[str] = (),
        excluded_tests: Sequence[str] = (),
    ) -> tuple[list[str], list[str]]:
        """Add explicit (existing, contained) tests, then drop every excluded path or file name."""
        merged = list(test_candidates)
        for rel in regression_tests:
            text = str(rel).strip()
            if text and text not in merged and self._contained_path(text, self.project_root) is not None:
                if (self.project_root / text).is_file():
                    merged.append(text)
        excluded_keys = {str(item).strip() for item in excluded_tests if str(item).strip()}
        if not excluded_keys:
            return merged, []
        kept: list[str] = []
        dropped: list[str] = []
        for rel in merged:
            if rel in excluded_keys or Path(rel).name in excluded_keys:
                dropped.append(rel)
            else:
                kept.append(rel)
        return kept, dropped

    def _existing_regression_candidates(self, regression_map: list[dict[str, Any]]) -> list[str]:
        seen: set[str] = set()
        existing: list[str] = []
        for item in regression_map:
            for candidate in item.get("existing", []):
                if candidate in seen:
                    continue
                seen.add(candidate)
                existing.append(candidate)
        return existing

    def _scan_security_observations(self, diff_text: str) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        current_file = ""
        new_line = 0
        for raw_line in diff_text.splitlines():
            if raw_line.startswith("diff --git "):
                current_file = self._path_from_diff_header(raw_line)
                new_line = 0
                continue
            if raw_line.startswith("@@"):
                parsed = re.search(r"\+(\d+)", raw_line)
                new_line = int(parsed.group(1)) - 1 if parsed else 0
                continue
            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                new_line += 1
                content = raw_line[1:]
                for rule_id, pattern in SECURITY_PATTERNS:
                    if _security_pattern_matches(rule_id, pattern, content):
                        findings.append(
                            {
                                "id": f"security-{len(findings) + 1}",
                                "lane": "security_sentry",
                                "rule_id": rule_id,
                                "state": "UNVERIFIED_OBSERVATION",
                                "severity": "high" if rule_id == "secret_literal" else "medium",
                                "file": current_file,
                                "line": new_line,
                                "repro_command": "",
                                "matched_text": content,
                                "summary": f"Dry-run security observation matched {rule_id}.",
                            }
                        )
                continue
            if raw_line.startswith("-") and not raw_line.startswith("---"):
                continue
            if current_file:
                new_line += 1
        return findings

    def _path_from_diff_header(self, line: str) -> str:
        parsed = re.match(r"^diff --git a/(.*) b/(.*)$", line)
        if parsed:
            return parsed.group(2)
        parts = line.split()
        if len(parts) < 4:
            return ""
        path = parts[3]
        return path[2:] if path.startswith("b/") else path

    def _derive_regression_candidates(self, diff_text: str) -> list[str]:
        return self._existing_regression_candidates(self._derive_regression_candidate_map(diff_text))

    def _build_dry_run_fleet(
        self,
        test_candidates: list[str],
        security_sentry: dict[str, Any] | None = None,
        logic_breaker: dict[str, Any] | None = None,
        ghost_regression: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        security_sentry = security_sentry or {
            "passed": True,
            "findings": [],
            "verified_findings": 0,
            "unverified_observations": 0,
        }
        logic_breaker = logic_breaker or {
            "passed": True,
            "repro_script": "",
            "repro_command": "",
        }
        ghost_regression = ghost_regression or {
            "passed": True,
            "executed_tests": [],
            "failed_tests": [],
            "skipped_tests": [],
        }
        ghost_status = "SKIPPED"
        if test_candidates:
            ghost_status = "PASS" if bool(ghost_regression.get("passed", False)) else "FAIL"
            if ghost_status == "PASS" and ghost_regression.get("inconclusive"):
                ghost_status = "INCONCLUSIVE"
        logic_status = "PASS" if bool(logic_breaker.get("passed", False)) else "FAIL"
        return [
            {
                "lane": "security_sentry",
                "status": "PASS" if security_sentry.get("passed", True) else "FAIL",
                "planned_checks": ["diff-pattern-scan", "bandit", "ruff-security"],
                "executed_checks": security_sentry.get("executed_checks", []),
                "unavailable_checks": security_sentry.get("unavailable_checks", []),
                "unverified_observations": security_sentry.get("unverified_observations", 0),
                "verified_findings": security_sentry.get("verified_findings", 0),
            },
            {
                "lane": "logic_breaker",
                "status": logic_status,
                "planned_checks": ["ultra_logic_repro.py", "py_compile", "ruff-correctness"],
                "executed_checks": logic_breaker.get("executed_checks", ["ultra_logic_repro.py"]),
                "unavailable_checks": logic_breaker.get("unavailable_checks", []),
                "repro_script": logic_breaker.get("repro_script", ""),
                "verified_findings": len(logic_breaker.get("findings", []) or [])
                if logic_breaker.get("findings") is not None
                else (0 if logic_breaker.get("passed", True) else 1),
            },
            {
                "lane": "ghost_regression",
                "status": ghost_status,
                "planned_checks": test_candidates,
                "executed_checks": ghost_regression.get("executed_tests", []),
                "failed_checks": ghost_regression.get("failed_tests", []),
                "skipped_checks": ghost_regression.get("skipped_tests", []),
                "skip_reason": "" if test_candidates else "no_existing_regression_candidates",
                "pre_existing_failures": ghost_regression.get("pre_existing_failures", []),
                "inconclusive_checks": ghost_regression.get("inconclusive_tests", []),
                "verified_findings": len(ghost_regression.get("failed_tests", [])),
            },
        ]

    def _run_security_sentry(self, *, diff_text: str, execution_root: Path, sandbox_path: Path) -> dict[str, Any]:
        observations = self._scan_security_observations(diff_text)
        findings: list[dict[str, Any]] = []
        executed_checks: list[str] = ["diff-pattern-scan"]
        unavailable_checks: list[dict[str, Any]] = []
        tool_runs: dict[str, Any] = {}
        verified_count = 0
        unverified_count = 0

        for index, observation in enumerate(observations, start=1):
            script_name = f"ultra_security_repro_{index}.py"
            script_path = sandbox_path / script_name
            expected = str(observation.get("matched_text", ""))
            script_path.write_text(
                "\n".join(
                    [
                        "from pathlib import Path",
                        "",
                        f"expected = {expected!r}",
                        f"target = Path({str(observation.get('file', ''))!r})",
                        "# The smell must be present in the sandbox tree the diff was applied to,",
                        "# not merely in the diff text.",
                        "if target.is_symlink() or not target.is_file():",
                        "    raise SystemExit('changed file missing from sandbox mirror')",
                        "if expected not in target.read_text(encoding='utf-8', errors='replace'):",
                        "    raise SystemExit('security observation not reproduced')",
                        "print('security_repro_ok')",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            _write_no_follow(execution_root / "changes.diff", self._resolve(sandbox_path / "changes.diff").read_bytes())
            cmd = [sys.executable, "-I", str(script_path)]
            executed_checks.append(script_name)
            timeout = False
            try:
                result = self._sandboxed_run(cmd, cwd=execution_root, timeout=SECURITY_REPRO_TIMEOUT_SEC)
                reproduced = result.returncode == 0
                stdout_tail = (result.stdout or "")[-2000:]
                stderr_tail = (result.stderr or "")[-2000:]
            except subprocess.TimeoutExpired as exc:
                reproduced = False
                timeout = True
                stdout_tail = str(exc.output or "")[-2000:]
                stderr_tail = str(exc.stderr or "")[-2000:]
            finding = dict(observation)
            finding.update(
                {
                    "repro_command": " ".join(cmd),
                    "execution_cwd": str(execution_root),
                    "stdout_tail": stdout_tail,
                    "stderr_tail": stderr_tail,
                    "timeout_sec": SECURITY_REPRO_TIMEOUT_SEC,
                    "timeout": timeout,
                }
            )
            if reproduced:
                finding["state"] = "VERIFIED_FINDING"
                finding["summary"] = f"Security Sentry reproduced {finding['rule_id']} from diff evidence."
                verified_count += 1
            else:
                finding["state"] = "UNVERIFIED_OBSERVATION"
                finding["summary"] = f"Security Sentry observed {finding['rule_id']} but repro did not confirm it."
                unverified_count += 1
            findings.append(finding)

        py_files = self._changed_python_files(diff_text, execution_root)
        added = self._added_lines(diff_text)
        tool_findings: list[dict[str, Any]] = []
        if py_files:
            for check_name, runner in (
                ("bandit", lambda: self._bandit_findings(py_files, execution_root=execution_root, added=added)),
                (
                    "ruff-security",
                    lambda: self._ruff_findings(
                        py_files,
                        execution_root=execution_root,
                        added=added,
                        select="S",
                        lane="security_sentry",
                        ignored=RUFF_SECURITY_IGNORED_CODES,
                    ),
                ),
            ):
                run, found = runner()
                tool_runs[check_name] = {
                    key: run.get(key)
                    for key in ("available", "timeout", "returncode", "command", "error", "errors")
                    if key in run
                }
                if not run.get("available") or run.get("timeout"):
                    unavailable_checks.append({"check": check_name, **tool_runs[check_name]})
                    continue
                executed_checks.append(check_name)
                tool_findings.extend(found)
        # ruff's S-rules mirror bandit's B-rules: keep one finding per file/line/rule number.
        seen_keys: dict[tuple[str, int, str], dict[str, Any]] = {}
        for finding in tool_findings:
            number = re.sub(r"\D", "", str(finding["rule_id"]).split(":", 1)[-1])
            key = (str(finding["file"]), int(finding["line"]), number)
            if key in seen_keys:
                seen_keys[key].setdefault("corroborated_by", []).append(finding["rule_id"])
                continue
            seen_keys[key] = finding
            finding["id"] = f"security-{len(findings) + 1}"
            findings.append(finding)
        blocking = [
            finding
            for finding in findings
            if finding.get("state") == "VERIFIED_FINDING"
            and str(finding.get("severity") or "").lower() in SECURITY_BLOCKING_SEVERITIES
        ]
        verified_count = sum(1 for finding in findings if finding.get("state") == "VERIFIED_FINDING")
        return {
            "passed": not blocking and not unavailable_checks,
            "executed_checks": executed_checks,
            "unavailable_checks": unavailable_checks,
            "tool_runs": tool_runs,
            "scanned_python_files": py_files,
            "blocking_findings": len(blocking),
            "verified_findings": verified_count,
            "unverified_observations": unverified_count,
            "timeout_sec": SECURITY_REPRO_TIMEOUT_SEC,
            "execution_mode": "sandbox_mirror",
            "execution_cwd": str(execution_root),
            "dependency_mode": "active_venv",
            "findings": findings,
        }

    def _run_logic_breaker(
        self,
        *,
        diff_path: Path,
        execution_root: Path,
        sandbox_path: Path,
        mode: str = DRY_RUN_MODE,
        base_ref: str = "",
    ) -> dict[str, Any]:
        repro_script = sandbox_path / "ultra_logic_repro.py"
        mirror_diff_path = execution_root / ".nexus_ultra_changes.diff"
        _write_no_follow(mirror_diff_path, Path(diff_path).read_bytes())
        repro_script.write_text(
            "\n".join(
                [
                    "import re",
                    "from pathlib import Path",
                    "",
                    "diff_path = Path('.nexus_ultra_changes.diff')",
                    "if not diff_path.exists():",
                    "    raise SystemExit('missing diff artifact')",
                    "diff_text = diff_path.read_text(encoding='utf-8')",
                    "deleted_files = set()",
                    "current_changed = None",
                    "for line in diff_text.splitlines():",
                    "    if line.startswith('diff --git '):",
                    "        parsed = re.match(r'^diff --git a/(.*) b/(.*)$', line)",
                    "        if not parsed:",
                    "            raise SystemExit(f'malformed diff header: {line}')",
                    "        current_changed = parsed.group(2)",
                    "        continue",
                    "    if current_changed and line.startswith('deleted file mode '):",
                    "        deleted_files.add(current_changed)",
                    "for line in diff_text.splitlines():",
                    "    if not line.startswith('diff --git '):",
                    "        continue",
                    "    parsed = re.match(r'^diff --git a/(.*) b/(.*)$', line)",
                    "    changed = parsed.group(2)",
                    "    if changed and changed not in deleted_files and not Path(changed).exists():",
                    "        raise SystemExit(f'changed file missing from sandbox mirror: {changed}')",
                    "print('logic_repro_ok')",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        cmd = [sys.executable, "-I", str(repro_script)]
        timeout = False
        try:
            result = self._sandboxed_run(cmd, cwd=execution_root, timeout=LOGIC_BREAKER_TIMEOUT_SEC)
            passed = result.returncode == 0
            stdout_tail = (result.stdout or "")[-2000:]
            stderr_tail = (result.stderr or "")[-2000:]
            rule_id = "logic_repro_failed"
            summary = f"Logic Breaker deterministic repro failed in {_mode_phrase(mode)}."
        except subprocess.TimeoutExpired as exc:
            passed = False
            timeout = True
            stdout_tail = str(exc.output or "")[-2000:]
            stderr_tail = str(exc.stderr or "")[-2000:]
            rule_id = "logic_repro_timeout"
            summary = f"Logic Breaker deterministic repro timed out in {_mode_phrase(mode)}."

        findings = []
        executed_checks = ["ultra_logic_repro.py"]
        unavailable_checks: list[dict[str, Any]] = []
        if not passed:
            findings.append(
                {
                    "id": "logic-breaker-1",
                    "lane": "logic_breaker",
                    "rule_id": rule_id,
                    "state": "VERIFIED_FINDING",
                    "severity": "high",
                    "file": "",
                    "line": 0,
                    "repro_command": " ".join(cmd),
                    "summary": summary,
                    "execution_cwd": str(execution_root),
                    "stdout_tail": stdout_tail,
                    "stderr_tail": stderr_tail,
                }
            )

        diff_text = diff_path.read_text(encoding="utf-8") if diff_path.exists() else ""
        uncontained = self._uncontained_changed_files(diff_text, execution_root)
        executed_checks.append("path-containment")
        if uncontained:
            findings.append(
                {
                    "id": f"logic-breaker-{len(findings) + 1}",
                    "lane": "logic_breaker",
                    "rule_id": "path_outside_worktree",
                    "tool": "path-containment",
                    "state": "VERIFIED_FINDING",
                    "severity": "high",
                    "file": uncontained[0],
                    "line": 0,
                    "repro_command": "",
                    "summary": "Changed path is a symlink or resolves outside the sandbox worktree: "
                    + ", ".join(uncontained[:5]),
                    "execution_cwd": str(execution_root),
                }
            )
        # Part of path containment: a symlink or .git path in the diff is never contained.
        violations = self._diff_policy_violations(diff_text)
        for rule_id, paths, summary in (
            ("symlink_in_diff", violations["symlinks"], "Diff creates or edits a symlink (patch refused): "),
            ("nested_git_in_diff", violations["nested_git"], "Diff touches a .git path (patch refused): "),
        ):
            if paths:
                findings.append(
                    {
                        "id": f"logic-breaker-{len(findings) + 1}",
                        "lane": "logic_breaker",
                        "rule_id": rule_id,
                        "tool": "diff-policy",
                        "state": "VERIFIED_FINDING",
                        "severity": "high",
                        "file": paths[0],
                        "line": 0,
                        "repro_command": "",
                        "summary": summary + ", ".join(paths[:5]),
                        "execution_cwd": str(execution_root),
                    }
                )
        harness = self._harness_changes(diff_text, execution_root=execution_root, base_ref=base_ref)
        executed_checks.append("test-harness-guard")
        if harness:
            # A diff that edits the test harness can make the ghost re-run report green
            # without running the tests honestly; a human must review it.
            findings.append(
                {
                    "id": f"logic-breaker-{len(findings) + 1}",
                    "lane": "logic_breaker",
                    "rule_id": "test_harness_modified",
                    "tool": "test-harness-guard",
                    "state": "VERIFIED_FINDING",
                    "severity": "high",
                    "file": harness[0],
                    "line": 0,
                    "repro_command": "",
                    "summary": "Diff changes test-harness configuration: " + ", ".join(harness[:5]),
                    "execution_cwd": str(execution_root),
                }
            )
        py_files = self._changed_python_files(diff_text, execution_root)
        if py_files:
            compile_cmd = [sys.executable, "-I", "-m", "py_compile", *py_files]
            compiled = self._run_tool(compile_cmd, cwd=execution_root)
            executed_checks.append("py_compile")
            if compiled.get("timeout") or compiled.get("returncode") not in (0, None):
                findings.append(
                    {
                        "id": f"logic-breaker-{len(findings) + 1}",
                        "lane": "logic_breaker",
                        "rule_id": "py_compile_failed",
                        "tool": "py_compile",
                        "state": "VERIFIED_FINDING",
                        "severity": "high",
                        "file": "",
                        "line": 0,
                        "repro_command": compiled.get("command", ""),
                        "summary": "Changed Python file does not compile.",
                        "execution_cwd": str(execution_root),
                        "stderr_tail": str(compiled.get("stderr") or "")[-2000:],
                    }
                )
            run, found = self._ruff_findings(
                py_files,
                execution_root=execution_root,
                added=self._added_lines(diff_text),
                select=RUFF_LOGIC_SELECT,
                lane="logic_breaker",
            )
            if not run.get("available") or run.get("timeout"):
                unavailable_checks.append(
                    {"check": "ruff-correctness", "command": run.get("command"), "error": run.get("error", "timeout")}
                )
            else:
                executed_checks.append("ruff-correctness")
                for finding in found:
                    finding["id"] = f"logic-breaker-{len(findings) + 1}"
                    findings.append(finding)
        passed = bool(passed and not findings and not unavailable_checks)

        return {
            "passed": passed,
            "executed_checks": executed_checks,
            "unavailable_checks": unavailable_checks,
            "scanned_python_files": py_files,
            "repro_script": str(repro_script),
            "repro_command": " ".join(cmd),
            "execution_mode": "sandbox_mirror",
            "execution_cwd": str(execution_root),
            "timeout": timeout,
            "timeout_sec": LOGIC_BREAKER_TIMEOUT_SEC,
            "dependency_mode": "active_venv",
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "findings": findings,
        }

    def _run_ghost_regression(
        self,
        test_candidates: list[str],
        *,
        execution_root: Path,
        base_ref: str = "HEAD",
        sandbox_path: Path | None = None,
        explicit_tests: Sequence[str] = (),
        mode: str = DRY_RUN_MODE,
    ) -> dict[str, Any]:
        timeout_sec = self._ghost_timeout_sec()
        if os.getenv(ULTRA_SKIP_GHOST_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
            return {
                "passed": True,
                "executed_tests": [],
                "failed_tests": [],
                "skipped_tests": list(test_candidates),
                "findings": [],
                "execution_mode": "skipped_by_env",
                "timeout_sec": timeout_sec,
                "dependency_mode": "active_venv",
                "sanitized_env": self._benchmark_env_keys_removed(),
                "execution_cwd": str(execution_root),
                "timeout": False,
            }
        if not test_candidates:
            return {
                "passed": True,
                "executed_tests": [],
                "failed_tests": [],
                "skipped_tests": [],
                "findings": [],
                "execution_mode": "sandbox_mirror",
                "execution_cwd": str(execution_root),
                "timeout": False,
                "timeout_sec": timeout_sec,
                "dependency_mode": "active_venv",
                "pytest_stdout_tail": "",
                "pytest_stderr_tail": "",
            }

        head_report = self._new_ghost_report(sandbox_path or execution_root, "head")
        cmd = self._ghost_pytest_cmd(execution_root, test_candidates, head_report["junit"], head_report["witness"])
        sanitized_env = [key for key in BENCHMARK_ONLY_ENV_VARS if key in os.environ]
        test_candidates = [
            rel for rel in test_candidates if self._contained_path(rel, execution_root) is not None
        ]
        if not os_sandbox_available():
            # The re-run imports and executes PR-controlled code: without an OS barrier it
            # does not run at all, and the lane fails closed.
            return {
                "passed": False,
                "blocked": True,
                "blocked_reason": "no_os_barrier",
                "executed_tests": [],
                "failed_tests": [],
                "skipped_tests": list(test_candidates),
                "findings": [],
                "execution_mode": "refused_uncontained",
                "execution_cwd": str(execution_root),
                "timeout": False,
                "timeout_sec": timeout_sec,
                "dependency_mode": "active_venv",
                "sanitized_env": sanitized_env,
                "isolation": self.sandbox_isolation(),
                "pytest_stdout_tail": "",
                "pytest_stderr_tail": "",
            }
        phrase = _mode_phrase(mode)
        timeout = False
        passed = False
        head_returncode: int | None = None
        head_check: dict[str, Any] = {"verified": False, "reason": "not_run", "junit_bytes": None}
        head_retried = False
        try:
            try:
                result = self._run_witnessed(cmd, head_report, cwd=execution_root, timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                # One retry with a longer budget before calling it inconclusive (#2650).
                head_retried = True
                head_report = self._new_ghost_report(sandbox_path or execution_root, "head-retry")
                cmd = self._ghost_pytest_cmd(
                    execution_root, test_candidates, head_report["junit"], head_report["witness"]
                )
                result = self._run_witnessed(
                    cmd, head_report, cwd=execution_root, timeout=timeout_sec * GHOST_TIMEOUT_RETRY_FACTOR
                )
            head_returncode = result.returncode
            head_check = self._verify_ghost_report(head_report, result.returncode)
            passed = result.returncode == 0 and head_check["verified"]
            stdout_tail = (result.stdout or "")[-2000:]
            stderr_tail = (result.stderr or "")[-2000:]
        except subprocess.TimeoutExpired as exc:
            timeout = True
            stdout_tail = str(exc.output or "")[-2000:]
            stderr_tail = str(exc.stderr or "")[-2000:]

        findings: list[dict[str, Any]] = []
        regressions: list[str] = []
        pre_existing: list[str] = []
        inconclusive_tests: list[str] = []
        inconclusive_env: list[dict[str, str]] = []
        base_comparison: dict[str, Any] = {}

        def add_finding(rule_id: str, state: str, severity: str, summary: str, tests: list[str]) -> None:
            findings.append(
                {
                    "id": f"ghost-regression-{len(findings) + 1}",
                    "lane": "ghost_regression",
                    "rule_id": rule_id,
                    "state": state,
                    "severity": severity,
                    "file": "",
                    "line": 0,
                    "repro_command": self._display_cmd(cmd),
                    "summary": summary,
                    "tests": tests[:50],
                    "execution_cwd": str(execution_root),
                    "stdout_tail": stdout_tail,
                    "stderr_tail": stderr_tail,
                }
            )

        if timeout:
            # Our own time budget ran out: nothing about the change is proven (#2623).
            inconclusive_tests = list(test_candidates)
            add_finding(
                "regression_test_timeout",
                "INCONCLUSIVE_TIMEOUT",
                "info",
                f"Ghost regression candidate timed out after {timeout_sec:g}s and again after"
                f" {timeout_sec * GHOST_TIMEOUT_RETRY_FACTOR:g}s in {phrase} (inconclusive, not a finding).",
                inconclusive_tests,
            )
        elif head_returncode == 0 and not head_check["verified"]:
            # Exit 0 without a valid witness: pytest never finished its own session (e.g. an
            # ``os._exit(0)`` in the code under test) or its report was replaced. Not a pass (#2644).
            inconclusive_tests = list(test_candidates)
            add_finding(
                "pytest_report_unverified",
                "INCONCLUSIVE",
                "info",
                f"Ghost regression run exited 0 but its pytest report is unverified ({head_check['reason']})"
                f" in {phrase}: not a pass.",
                inconclusive_tests,
            )
        elif not passed:
            # Base comparison only for an ordinary "some tests failed" run (exit 1) with a
            # verified, parseable report; an interrupted/crashed/usage-error run, or one whose
            # report is unverified (#2644), stays a regression.
            head_outcomes = (
                self._junit_outcomes_from_bytes(head_check["junit_bytes"])
                if head_returncode == 1 and head_check["verified"]
                else None
            )
            failed_ids = (
                [test_id for test_id, state in head_outcomes.items() if state in ("failed", "error_file")]
                if head_outcomes is not None
                else []
            )
            regressions, comparable = self._attribute_head_failures(failed_ids, test_candidates, explicit_tests)
            if comparable:
                # Only base-pass -> head-fail counts against the change: re-run the failing
                # mapped tests on an isolated checkout of the base.
                base_comparison = self._compare_failures_on_base(
                    comparable,
                    base_ref=base_ref,
                    sandbox_path=sandbox_path,
                    timeout_sec=timeout_sec,
                    head_collection_modules=self._junit_collection_error_modules(head_check["junit_bytes"]),
                    head_failure_texts=self._junit_failure_texts(head_check["junit_bytes"]),
                    execution_root=execution_root,
                )
                regressions.extend(base_comparison.pop("regressions"))
                cleanup = base_comparison.get("base_cleanup") or {}
                if cleanup and not cleanup.get("removed"):
                    add_finding(
                        "base_worktree_cleanup_failed",
                        "UNVERIFIED_OBSERVATION",
                        "info",
                        "Temporary base worktree could not be removed: " + str(cleanup.get("detail") or ""),
                        [],
                    )
                pre_existing = base_comparison.pop("pre_existing")
                inconclusive_tests = base_comparison.pop("inconclusive")
                inconclusive_env = base_comparison.pop("inconclusive_env")
            if regressions:
                add_finding(
                    "regression_test_failed",
                    "VERIFIED_FINDING",
                    "high",
                    f"Ghost regression candidate failed in {phrase}: " + ", ".join(regressions[:10]),
                    regressions,
                )
            if pre_existing:
                add_finding(
                    "pre_existing_test_failure",
                    "PRE_EXISTING_FAILURE",
                    "info",
                    f"Mapped test fails on base and head alike in {phrase} (not introduced by the change): "
                    + ", ".join(pre_existing[:10]),
                    pre_existing,
                )
            if inconclusive_env:
                # The test has no base result and this sandbox cannot run it (a dependency the
                # reviewer's interpreter lacks, or a failed capability probe): not evidence
                # against the change (#2650). A test that passes on base never lands here.
                add_finding(
                    "environment_unavailable",
                    "INCONCLUSIVE_ENV",
                    "info",
                    f"Mapped test fails on head, has no base result and cannot run in this sandbox in {phrase}: "
                    + ", ".join(f"{item['test']} ({item['reason']})" for item in inconclusive_env[:10]),
                    [item["test"] for item in inconclusive_env],
                )
            if inconclusive_tests:
                timed_out = bool(base_comparison.get("timeout"))
                add_finding(
                    "regression_test_timeout" if timed_out else "base_comparison_unavailable",
                    "INCONCLUSIVE_TIMEOUT" if timed_out else "INCONCLUSIVE",
                    "info",
                    f"Mapped test fails on head but its base result is unknown in {phrase} "
                    f"({base_comparison.get('reason') or 'base unavailable'}): " + ", ".join(inconclusive_tests[:10]),
                    inconclusive_tests,
                )
        return {
            "passed": not regressions,
            "inconclusive": bool(inconclusive_tests or inconclusive_env),
            "executed_tests": list(test_candidates),
            "failed_tests": regressions,
            "pre_existing_failures": pre_existing,
            "inconclusive_tests": inconclusive_tests,
            "inconclusive_env_tests": inconclusive_env,
            "head_retried_after_timeout": head_retried,
            "base_comparison": base_comparison,
            "skipped_tests": [],
            "findings": findings,
            "execution_mode": "sandbox_mirror",
            "execution_cwd": str(execution_root),
            "timeout": timeout,
            "timeout_sec": timeout_sec,
            "dependency_mode": "active_venv",
            "sanitized_env": sanitized_env,
            "isolation": self.sandbox_isolation(),
            "pytest_stdout_tail": stdout_tail,
            "pytest_stderr_tail": stderr_tail,
            "head_report": {"verified": head_check["verified"], "reason": head_check["reason"]},
        }

    @staticmethod
    def _display_cmd(cmd: Sequence[str]) -> str:
        return " ".join("<ghost-pytest-bootstrap>" if part == GHOST_PYTEST_BOOTSTRAP else part for part in cmd)

    @staticmethod
    def _new_ghost_report(parent: Path, label: str) -> dict[str, Any]:
        """A fresh, unguessable report dir created by the reviewer, plus the per-run HMAC key.
        The dir's identity is recorded so a swapped dir is detected after the run."""
        report_dir = parent / f"ghost-{label}-report-{secrets.token_hex(8)}"
        os.mkdir(report_dir, 0o700)
        info = os.lstat(report_dir)
        return {
            "dir": report_dir,
            "junit": report_dir / "junit.xml",
            "witness": report_dir / "witness.json",
            "key": secrets.token_bytes(32),
            "dir_identity": (info.st_dev, info.st_ino),
            "started": 0.0,
        }

    def _run_witnessed(
        self, cmd: list[str], report: dict[str, Any], *, cwd: Path, timeout: float
    ) -> subprocess.CompletedProcess:
        report["started"] = datetime.now(timezone.utc).timestamp()
        # The ghost re-run is the lane whose stalled descendants outlived a timeout (#2650).
        return self._sandboxed_run(
            cmd, cwd=cwd, timeout=timeout, stdin_text=report["key"].hex() + "\n", kill_process_group=True
        )

    @staticmethod
    def _verify_ghost_report(report: dict[str, Any], returncode: int) -> dict[str, Any]:
        """``{"verified", "reason", "junit_bytes"}`` for one witnessed pytest run (#2644).

        Verified only when the report dir is still the one the reviewer created, the witness and
        junit files are regular files owned by this user and written after the run started, the
        witness MAC matches this run's key, its exit status equals the process exit code and its
        junit hash equals the junit bytes returned (read once, so a later rewrite cannot race)."""

        def fail(reason: str) -> dict[str, Any]:
            return {"verified": False, "reason": reason, "junit_bytes": None}

        uid = os.getuid() if hasattr(os, "getuid") else None
        started = float(report.get("started") or 0.0)

        def regular_file(path: Path, max_bytes: int) -> bytes | None:
            info = os.lstat(path)
            if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
                return None
            if uid is not None and info.st_uid != uid:
                return None
            if info.st_mtime < started - 2:
                return None
            return path.read_bytes()

        try:
            dir_info = os.lstat(report["dir"])
            if not stat.S_ISDIR(dir_info.st_mode) or (dir_info.st_dev, dir_info.st_ino) != report["dir_identity"]:
                return fail("report_dir_replaced")
            witness = regular_file(report["witness"], GHOST_WITNESS_MAX_BYTES)
            if witness is None:
                return fail("witness_not_regular")
            doc = json.loads(witness)
            payload, mac = doc["payload"], doc["mac"]
            if not isinstance(payload, str) or not isinstance(mac, str):
                return fail("witness_malformed")
        except FileNotFoundError:
            return fail("witness_missing")
        except (OSError, ValueError, KeyError, TypeError):
            return fail("witness_unreadable")
        expected = hmac.new(report["key"], payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, mac):
            return fail("witness_mac_mismatch")
        try:
            fields = json.loads(payload)
        except ValueError:
            return fail("witness_malformed")
        if not isinstance(fields, dict) or fields.get("exitstatus") != returncode:
            return fail("exit_code_mismatch")
        try:
            junit = regular_file(report["junit"], JUNIT_MAX_BYTES)
        except OSError:
            return fail("junit_missing")
        if junit is None:
            return fail("junit_not_regular")
        if not hmac.compare_digest(hashlib.sha256(junit).hexdigest(), str(fields.get("junit_sha256") or "")):
            return fail("junit_hash_mismatch")
        return {"verified": True, "reason": "", "junit_bytes": junit}

    @staticmethod
    def _ghost_pytest_cmd(root: Path, tests: Sequence[str], junit_path: Path, witness_path: Path) -> list[str]:
        # rootdir pins conftest discovery to the checkout under test (the sandbox may sit inside
        # the reviewed repo); no cache dir is written into it. -I: no PYTHONPATH, user site or
        # cwd at start-up, so a PR sitecustomize/.pth never loads; the checkout is put on
        # sys.path by pytest's ``pythonpath`` ini override. Per-test outcomes are read from the
        # junit XML (xunit1 records each test's file), accepted only with a valid witness
        # (GHOST_PYTEST_BOOTSTRAP, #2644). ``pytest`` after the bootstrap is a label only.
        return [
            sys.executable,
            "-I",
            "-c",
            GHOST_PYTEST_BOOTSTRAP,
            "pytest",
            sbpl_path(junit_path),
            sbpl_path(witness_path),
            "-q",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(root),
            "-o",
            # pytest shlex-splits a ``paths`` ini value: quote it so a root with a space
            # (``~/Library/Application Support``) stays one sys.path entry (#2665).
            f"pythonpath={shlex.quote(sbpl_path(root))}",
            "-o",
            "junit_family=xunit1",
            # A file that fails to import is reported (error_file) and the other files still
            # run, instead of the whole session aborting with exit 2 (#2650).
            "--continue-on-collection-errors",
            f"--junitxml={sbpl_path(junit_path)}",
            *tests,
        ]

    @staticmethod
    def _junit_outcomes(junit_path: Path) -> dict[str, str] | None:
        """``_junit_outcomes_from_bytes`` of a report file (None when missing or not regular)."""
        try:
            info = os.lstat(junit_path)
            if not stat.S_ISREG(info.st_mode) or info.st_size > JUNIT_MAX_BYTES:
                return None
            data = junit_path.read_bytes()
        except OSError:
            return None
        return UltraReviewService._junit_outcomes_from_bytes(data)

    @staticmethod
    def _junit_outcomes_from_bytes(data: bytes | None) -> dict[str, str] | None:
        """``{test id: passed|failed|skipped|error_file}`` from a pytest junit XML, or None when
        the report is missing, oversized, unparseable or names a test without a file.

        The id is ``file::[Class::]name`` rebuilt from the xunit1 ``file``/``classname``/``name``
        attributes, so parametrized names (``test_p[a - b]``) stay whole. A file-level
        collection error (empty classname, dotted module as name) is keyed by the file path
        with state ``error_file``."""
        import xml.etree.ElementTree as ET  # noqa: S405  # nosec B405 - DTD/entities rejected below

        if data is None or len(data) > JUNIT_MAX_BYTES:
            return None
        try:
            # Written by PR-controlled test code: refuse any DTD/entity declaration (entity
            # expansion), the only XML feature that makes the stdlib parser unsafe here.
            if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
                return None
            root = ET.fromstring(data)  # noqa: S314  # nosec B314 - DTD/entities rejected above
        except (OSError, ET.ParseError):
            return None
        outcomes: dict[str, str] = {}
        for case in root.iter("testcase"):
            classname = str(case.get("classname") or "")
            name = str(case.get("name") or "")
            file = str(case.get("file") or "").replace("\\", "/")
            failed = case.find("failure") is not None or case.find("error") is not None
            if not classname:
                if not name or not failed:
                    return None
                test_id = file or name.replace(".", "/") + ".py"
                state = "error_file"
            else:
                if not file or not name:
                    return None
                module = file[:-3].replace("/", ".") if file.endswith(".py") else file
                if classname != module and not classname.startswith(module + "."):
                    return None
                parts = [file, *[p for p in classname[len(module) :].split(".") if p], name]
                test_id = "::".join(parts)
                if failed:
                    state = "failed"
                elif case.find("skipped") is not None:
                    state = "skipped"
                else:
                    state = "passed"
            if outcomes.get(test_id) in ("failed", "error_file"):
                continue  # a teardown error after a pass still counts as a failure
            outcomes[test_id] = state
        return outcomes

    @staticmethod
    def _junit_failure_texts(data: bytes | None) -> dict[str, str]:
        """``{test id: failure/error message + text}`` for failed test cases, ids built exactly
        as ``_junit_outcomes_from_bytes`` builds them; ``{}`` for any report it would refuse."""
        import xml.etree.ElementTree as ET  # noqa: S405  # nosec B405 - DTD/entities rejected below

        if UltraReviewService._junit_outcomes_from_bytes(data) is None or data is None:
            return {}
        try:
            # DTD/entities were rejected by the _junit_outcomes_from_bytes call above.
            root = ET.fromstring(data)  # noqa: S314  # nosec B314
        except ET.ParseError:
            return {}
        texts: dict[str, str] = {}
        for case in root.iter("testcase"):
            classname = str(case.get("classname") or "")
            name = str(case.get("name") or "")
            file = str(case.get("file") or "").replace("\\", "/")
            if not classname:
                continue
            module = file[:-3].replace("/", ".") if file.endswith(".py") else file
            nested = [p for p in classname[len(module) :].split(".") if p]
            test_id = "::".join([file, *nested, name])
            parts = [
                f"{node.get('message') or ''}\n{node.text or ''}"
                for node in (*case.findall("failure"), *case.findall("error"))
            ]
            if parts:
                texts[test_id] = (texts.get(test_id, "") + "\n".join(parts))[-20000:]
        return texts

    @staticmethod
    def _attribute_head_failures(
        failed_ids: list[str], test_candidates: list[str], explicit_tests: Sequence[str]
    ) -> tuple[list[str], list[str]]:
        """Split head failures into (regressions now, ids to compare on base).

        Fail closed: a failing run with no parseable ids, an id outside the candidate files, or
        an explicit caller-required test (``regression_tests``) is a regression outright; only
        mapped tests get the base comparison."""
        if not failed_ids:
            return list(test_candidates), []
        candidates = set(test_candidates)
        explicit = set(explicit_tests)
        regressions: list[str] = []
        comparable: list[str] = []
        for test_id in failed_ids:
            path = test_id.split("::", 1)[0]
            if path in candidates and path not in explicit:
                comparable.append(test_id)
            else:
                regressions.append(test_id)
        return regressions, comparable

    def _compare_failures_on_base(
        self,
        failed_ids: list[str],
        *,
        base_ref: str,
        sandbox_path: Path | None,
        timeout_sec: float,
        head_collection_modules: dict[str, str] | None = None,
        execution_root: Path | None = None,
        head_failure_texts: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Re-run the files of head-failing mapped tests on a detached worktree of ``base_ref``.

        Per id, from the base junit report: failed on base too -> pre-existing; passed on base
        -> regression; absent on base (a failing test the change added) -> regression, unless
        this sandbox cannot run it (#2650: a collection-time ``ModuleNotFoundError`` for a module
        neither tree provides and the reviewer's interpreter cannot import, or a failed sandbox
        capability probe) -> inconclusive_env; skipped on base, a file-level collection error on
        base, an unknown base result (timeout, exit other than 0/1, unparseable report) or an
        unpreparable base -> inconclusive."""
        outcome: dict[str, Any] = {
            "base_ref": base_ref,
            "regressions": [],
            "pre_existing": [],
            "inconclusive": [],
            "inconclusive_env": [],
            "reason": "",
            "timeout": False,
        }
        modules = dict(head_collection_modules or {})
        failure_texts = dict(head_failure_texts or {})

        def file_of(test_id: str) -> str:
            return test_id.split("::", 1)[0]

        def absent_on_base(test_id: str) -> None:
            reason = self._environment_reason(
                test_id,
                modules,
                execution_root=execution_root,
                base_ref=base_ref,
                failure_text=failure_texts.get(test_id, ""),
            )
            if reason:
                outcome["inconclusive_env"].append({"test": test_id, "reason": reason})
            else:
                outcome["regressions"].append(test_id)

        if sandbox_path is None or not base_ref or base_ref.startswith("-"):
            outcome["inconclusive"] = list(failed_ids)
            outcome["reason"] = "base_ref_unusable"
            return outcome
        base_root = sandbox_path / "base_worktree"
        add = self._git_run(["worktree", "add", "--detach", str(base_root), base_ref])
        if add.returncode != 0:
            outcome["inconclusive"] = list(failed_ids)
            outcome["reason"] = "base_worktree_unavailable: " + (add.stderr or add.stdout or "")[-300:].strip()
            return outcome
        base_git: dict[str, Any] = {}
        try:
            violations = self._neutralize_base_links(base_root)
            if violations:
                outcome["inconclusive"] = list(failed_ids)
                outcome["reason"] = "base_tree_special_entries: " + ", ".join(violations[:5])
                return outcome
            files = sorted({file_of(test_id) for test_id in failed_ids})
            present = [
                rel for rel in files if self._contained_path(rel, base_root) is not None and (base_root / rel).is_file()
            ]
            remaining = [test_id for test_id in failed_ids if file_of(test_id) in present]
            for test_id in failed_ids:
                if file_of(test_id) not in present:
                    absent_on_base(test_id)
            if not remaining:
                return outcome
            # Same git capability on base as on head, so a git-using test is judged alike (#2650).
            base_git = self._give_checkout_sandbox_git_dir(base_root, rev=base_ref)
            base_report = self._new_ghost_report(sandbox_path, "base")
            cmd = self._ghost_pytest_cmd(base_root, present, base_report["junit"], base_report["witness"])
            try:
                try:
                    result = self._run_witnessed(cmd, base_report, cwd=base_root, timeout=timeout_sec)
                except subprocess.TimeoutExpired:
                    outcome["base_retried_after_timeout"] = True
                    base_report = self._new_ghost_report(sandbox_path, "base-retry")
                    cmd = self._ghost_pytest_cmd(base_root, present, base_report["junit"], base_report["witness"])
                    result = self._run_witnessed(
                        cmd, base_report, cwd=base_root, timeout=timeout_sec * GHOST_TIMEOUT_RETRY_FACTOR
                    )
            except subprocess.TimeoutExpired:
                outcome["repro_command"] = self._display_cmd(cmd)
                outcome["inconclusive"] = remaining
                outcome["reason"] = f"base_run_timeout_{timeout_sec * GHOST_TIMEOUT_RETRY_FACTOR:g}s"
                outcome["timeout"] = True
                return outcome
            outcome["repro_command"] = self._display_cmd(cmd)
            outcome["base_returncode"] = result.returncode
            base_check = self._verify_ghost_report(base_report, result.returncode)
            base_outcomes = (
                self._junit_outcomes_from_bytes(base_check["junit_bytes"])
                if result.returncode in (0, 1) and base_check["verified"]
                else None
            )
            if base_outcomes is None:
                outcome["inconclusive"] = remaining
                outcome["reason"] = (
                    f"base_report_unverified_{base_check['reason']}"
                    if result.returncode in (0, 1) and not base_check["verified"]
                    else f"base_result_unknown_exit_{result.returncode}"
                )
                return outcome
            reasons: set[str] = set()
            for test_id in remaining:
                if base_outcomes.get(file_of(test_id)) == "error_file":
                    # The file does not even collect on base: it cannot excuse head failures.
                    outcome["inconclusive"].append(test_id)
                    reasons.add("base_file_collection_error")
                    continue
                state = base_outcomes.get(test_id)
                if state == "failed":
                    outcome["pre_existing"].append(test_id)
                elif state == "passed":
                    outcome["regressions"].append(test_id)
                elif state is None:
                    prefix = file_of(test_id) + "::"
                    if test_id == file_of(test_id) and any(
                        key.startswith(prefix) and value == "passed" for key, value in base_outcomes.items()
                    ):
                        # The file no longer collects on head but its tests pass on base:
                        # base pass -> head fail, whatever the import error says.
                        outcome["regressions"].append(test_id)
                    else:
                        absent_on_base(test_id)
                else:
                    outcome["inconclusive"].append(test_id)
                    reasons.add(f"base_{state}")
            outcome["reason"] = ",".join(sorted(reasons))
            return outcome
        finally:
            restore = self._restore_checkout_git_file(base_root, base_git)
            if base_git:
                outcome["base_git_dir"] = {
                    **{k: v for k, v in base_git.items() if k not in ("original", "restored_result")},
                    "restore": restore,
                }
            removed = self._git_run(["worktree", "remove", "--force", str(base_root)])
            outcome["base_cleanup"] = {
                "removed": removed.returncode == 0,
                "detail": (removed.stderr or removed.stdout or "")[-300:].strip(),
            }

    def _environment_reason(
        self,
        test_id: str,
        modules: dict[str, str],
        *,
        execution_root: Path | None,
        base_ref: str,
        failure_text: str = "",
    ) -> str:
        """Why a head failure with no base result cannot be judged here, or ``""`` (#2650).

        ``dependency_unavailable:<module>`` when the file failed to collect with a
        ``ModuleNotFoundError`` for a top-level module that the tree DECLARES as an external
        dependency (pyproject / requirements), that neither the head nor the base tree provides
        and that the reviewer's interpreter cannot import. A forgotten or misspelled module is not
        declared, so it stays a regression. ``environment_probe_failed:<probes>`` when a sandbox
        capability probe, run before any candidate code, failed. ``git_history_unavailable`` when
        the test's own junit failure text carries git's missing-object error (the sandbox git
        dir holds one commit, #2665). Only ever called for a test with no base result, so a
        base pass -> head fail never reaches here and stays a regression."""
        module = modules.get(test_id) or ""
        if module and execution_root is not None and self._dependency_unavailable(
            module, execution_root, base_ref, test_file=test_id.split("::", 1)[0]
        ):
            return "dependency_unavailable:" + module.split(".", 1)[0]
        if failure_text and GIT_HISTORY_UNAVAILABLE_RE.search(failure_text):
            return "git_history_unavailable"
        failed = list(getattr(self, "_env_probe_failures", None) or [])
        if failed:
            return "environment_probe_failed:" + ",".join(failed)
        return ""

    def _dependency_unavailable(self, module: str, execution_root: Path, base_ref: str, *, test_file: str = "") -> bool:
        top = module.split(".", 1)[0]
        if not TOP_LEVEL_MODULE_RE.fullmatch(top):
            return False
        if not self._declared_external_dependency(top, execution_root, test_file):
            return False  # not declared anywhere: a forgotten or misspelled module is the change's
        candidates = (top, f"{top}.py", f"src/{top}", f"src/{top}.py")
        for rel in candidates:
            if os.path.lexists(execution_root / rel):
                return False  # the head tree provides it: an import break is the change's
            if base_ref and not base_ref.startswith("-"):
                shown = self._git_run(["cat-file", "-e", f"{base_ref}:{rel}"])
                if shown.returncode == 0:
                    return False  # the base tree provides it: moved or deleted by the change
        try:
            probe = subprocess.run(  # noqa: S603 - trusted interpreter, fixed code, name validated
                [sys.executable, "-I", "-c", FIND_SPEC_PROBE, top],
                cwd=self._git_home if getattr(self, "_git_home", None) else None,
                capture_output=True,
                text=True,
                timeout=ENV_PROBE_TIMEOUT_SEC,
                check=False,
                env={key: os.environ[key] for key in SANDBOX_ENV_ALLOWLIST if key in os.environ},
            )
        except (OSError, subprocess.SubprocessError):
            return False
        # Importable by the reviewer yet missing in the run: not a dependency gap, keep it.
        return probe.returncode == 1

    def _declared_external_dependency(self, top: str, execution_root: Path, test_file: str) -> bool:
        """True when a ``pyproject.toml`` or ``requirements*.txt`` at the tree root or in a
        directory containing ``test_file`` declares a distribution whose normalized name is
        ``top`` (``langchain-core`` -> ``langchain_core``), or a ``[tool.*] canonical-namespace``
        equal to ``top`` (a vendored sibling package)."""
        wanted = top.lower()
        dirs: list[Path] = [execution_root]
        rel_parent = Path(test_file).parent if test_file else Path()
        current = execution_root
        for part in rel_parent.parts:
            if part in ("", ".", ".."):
                break
            current = current / part
            dirs.append(current)
        for directory in dirs:
            if self._contained_path(str(directory.relative_to(execution_root)) or ".", execution_root) is None:
                continue
            files = [directory / "pyproject.toml", *sorted(directory.glob("requirements*.txt"))]
            for path in files:
                if path.is_symlink() or not path.is_file():
                    continue
                try:
                    if path.stat().st_size > 1_000_000:
                        continue
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                names = _declared_names_from_pyproject(text) if path.name == "pyproject.toml" else _declared_names_from_requirements(text)
                if wanted in names:
                    return True
        return False

    def _environment_probe(self, execution_root: Path, *, mirror_git_ok: bool) -> list[str]:
        """Names of the sandbox capability probes that fail. Run once per review, before any
        candidate code. The mirror git probe only applies when the mirror was given a git dir;
        a copytree mirror has no ``.git`` by design, so that probe is not applicable there."""
        probes: list[tuple[str, list[str]]] = [("git_version", ["git", "--version"])]
        if mirror_git_ok:
            probes.append(("git_rev_parse_mirror", ["git", "-C", str(execution_root), "rev-parse", "HEAD"]))
            # ``git status`` needs the iconv tables (#2665, P6); --no-optional-locks keeps the
            # probe from writing the index.
            probes.append(
                (
                    "git_status_mirror",
                    [
                        "git",
                        "--no-optional-locks",
                        "-C",
                        str(execution_root),
                        "status",
                        "--porcelain",
                    ],
                )
            )
        probes.append(("tmpdir_write", [sys.executable, "-I", "-c", ENV_PROBE_TMPDIR_WRITE]))
        failed: list[str] = []
        for name, cmd in probes:
            try:
                ok = self._sandboxed_run(cmd, cwd=execution_root, timeout=ENV_PROBE_TIMEOUT_SEC).returncode == 0
            except (subprocess.TimeoutExpired, OSError, SandboxError):
                ok = False
            if not ok:
                failed.append(name)
        return failed

    @staticmethod
    def _junit_collection_error_modules(data: bytes | None) -> dict[str, str]:
        """``{file: module}`` for file-level collection errors whose last
        ``ModuleNotFoundError`` names ``module`` (same keys as ``_junit_outcomes_from_bytes``)."""
        import xml.etree.ElementTree as ET  # noqa: S405  # nosec B405 - DTD/entities rejected below

        if data is None or len(data) > JUNIT_MAX_BYTES or b"<!DOCTYPE" in data or b"<!ENTITY" in data:
            return {}
        try:
            root = ET.fromstring(data)  # noqa: S314  # nosec B314 - DTD/entities rejected above
        except ET.ParseError:
            return {}
        found: dict[str, str] = {}
        for case in root.iter("testcase"):
            if case.get("classname"):
                continue
            name = str(case.get("name") or "")
            file = str(case.get("file") or "").replace("\\", "/")
            text = "".join(
                str(element.get("message") or "") + "\n" + (element.text or "")
                for element in (case.find("error"), case.find("failure"))
                if element is not None
            )
            matches = MODULE_NOT_FOUND_RE.findall(text)
            if name and matches:
                found[file or name.replace(".", "/") + ".py"] = matches[-1]
        return found

    def _give_checkout_sandbox_git_dir(
        self, checkout: Path, *, rev: str, diff_path: Path | None = None
    ) -> dict[str, Any]:
        """Point a review worktree at a self-contained, read-only git dir (#2650).

        A ``git worktree``'s admin dir lives in the reviewed repository's ``.git``, which the
        sandbox cannot (and must not) read, so ``git rev-parse HEAD`` in the mirror fails under
        test. The reviewer builds a fresh git dir with ``tempfile.mkdtemp`` (exclusive, random
        name, mode 0700) OUTSIDE every sandbox-writable tree: init without templates, a depth-1
        fetch of the exact sha of ``rev`` from the repository, a detached ``HEAD`` and an index of
        that commit (plus ``diff_path`` staged with ``apply --cached``, matching the mirror). No
        step reads the worktree, so no clean filter, attribute or config planted by code under
        review is ever consulted, and ``core.attributesFile`` is ``/dev/null`` throughout. The
        sandbox gets the dir as a read root only (never writable). The checkout's ``.git`` file
        is then swapped to it; ``_restore_checkout_git_file`` puts the original back and deletes
        the dir. Returns ``{"ok": False, ...}`` on any failure, leaving the checkout untouched."""
        try:
            self._mirror_git_dir(checkout)
            original = (checkout / ".git").read_text(encoding="utf-8")
        except (UltraReviewError, OSError) as exc:
            return {"ok": False, "detail": f"not_a_review_worktree:{exc}"}
        sha_run = self._git_run(["rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}"])
        sha = (sha_run.stdout or "").strip()
        if sha_run.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40,64}", sha):
            return {"ok": False, "detail": "rev_unresolved"}
        git_dir = Path(tempfile.mkdtemp(prefix="nexus-ultra-gitdir-")).resolve()
        ctx = getattr(self, "_sandbox_ctx", None) or {}
        if in_tree(git_dir, (self.project_root, ctx.get("execution_root"), ctx.get("sandbox_path"))):
            shutil.rmtree(git_dir, ignore_errors=True)
            return {"ok": False, "detail": "git_dir_inside_reviewed_tree"}
        gd = str(git_dir)
        safe = ["--git-dir", gd, "-c", "core.attributesFile=/dev/null"]
        steps = (
            ("init", [*safe, "init", "-q", "--template="]),
            ("config", [*safe, "config", "core.bare", "false"]),
            (
                "fetch",
                # A fixed local path and an exact sha; the file transport is enabled for this
                # one call only (GIT_SAFE_CONFIG sets protocol.allow=never).
                [*safe, "-c", "protocol.file.allow=always", "fetch", "-q", "--no-tags", "--depth=1",
                 str(self.project_root), sha],
            ),
            ("read_tree", [*safe, "read-tree", sha]),
        )
        for label, step in steps:
            done = self._git_run(step)
            if done.returncode != 0:
                shutil.rmtree(git_dir, ignore_errors=True)
                return {"ok": False, "detail": f"{label}:" + (done.stderr or done.stdout or "")[-200:].strip()}
            if label == "fetch":
                # Detached HEAD at the fetched commit, in the git dir the reviewer just created.
                try:
                    _write_no_follow(git_dir / "HEAD", f"{sha}\n".encode())
                except (OSError, SandboxError) as exc:
                    shutil.rmtree(git_dir, ignore_errors=True)
                    return {"ok": False, "detail": f"head:{exc}"}
        staged = False
        if diff_path is not None and diff_path.is_file() and diff_path.read_text(encoding="utf-8").strip():
            staged = self._git_run([*safe, "apply", "--cached", "--binary", str(diff_path)]).returncode == 0
        try:
            _write_no_follow(checkout / ".git", f"gitdir: {gd}\n".encode())
        except (OSError, SandboxError) as exc:
            shutil.rmtree(git_dir, ignore_errors=True)
            return {"ok": False, "detail": f"swap_failed:{exc}"}
        if ctx:
            ctx.setdefault("git_read_roots", []).append(git_dir)
        swap = {"ok": True, "git_dir": gd, "head": sha, "diff_staged": staged, "original": original}
        self.__dict__.setdefault("_pending_git_swaps", []).append((checkout, swap))
        return swap

    def _restore_checkout_git_file(self, checkout: Path, swap: dict[str, Any]) -> dict[str, Any]:
        """Undo ``_give_checkout_sandbox_git_dir``: the original ``.git`` file back (whatever the
        sandboxed run left there), the git dir removed and dropped from the read roots."""
        if not swap or not swap.get("ok") or swap.get("restored_result") is not None:
            return dict(swap.get("restored_result") or {}) if swap else {}
        dot_git = checkout / ".git"
        detail = ""
        try:
            if dot_git.is_dir() and not dot_git.is_symlink():
                shutil.rmtree(dot_git)
            _write_no_follow(dot_git, str(swap["original"]).encode())
            restored = True
        except (OSError, SandboxError) as exc:
            restored, detail = False, str(exc)[:200]
        git_dir = Path(str(swap["git_dir"]))
        shutil.rmtree(git_dir, ignore_errors=True)
        ctx = getattr(self, "_sandbox_ctx", None) or {}
        roots = ctx.get("git_read_roots") or []
        if git_dir in roots:
            roots.remove(git_dir)
        pending = self.__dict__.get("_pending_git_swaps") or []
        self._pending_git_swaps = [item for item in pending if item[1] is not swap]
        swap["restored_result"] = {"restored": restored, "detail": detail}
        return dict(swap["restored_result"])

    def _restore_pending_git_swaps(self) -> None:
        for checkout, swap in list(self.__dict__.get("_pending_git_swaps") or []):
            self._restore_checkout_git_file(checkout, swap)

    @staticmethod
    def _neutralize_base_links(base_root: Path) -> list[str]:
        """lstat-walk the base checkout: unlink symlinks resolving outside it; return any other
        non-regular entry (the base run is then inconclusive)."""
        root = base_root.resolve()

        def accept_symlink(path: Path, rel: str) -> bool:
            resolved = path.resolve()
            if resolved != root and root not in resolved.parents:
                os.unlink(path)
            return True

        return [rel for rel in lstat_walk_violations(base_root, on_symlink=accept_symlink) if rel != ".git"]

    def _changed_files(self, diff_text: str) -> list[str]:
        files: list[str] = []
        for line in diff_text.splitlines():
            if not line.startswith("diff --git "):
                continue
            path = self._path_from_diff_header(line)
            if path and not self._is_runtime_artifact_path(path):
                files.append(path)
        return files

    def _is_runtime_artifact_path(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return any(normalized.startswith(prefix) for prefix in RUNTIME_ARTIFACT_PREFIXES)

    def _resolve(self, path: Path | str) -> Path:
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return (self.project_root / path_obj).resolve()

    def _git_env(self, *, git_dir: Path | None = None, work_tree: Path | None = None) -> dict[str, str]:
        """Environment for every review git call: no system/global config, no inherited GIT_*.

        ``HOME`` is the sandbox home (empty, review-owned) so no user config is read; with an
        explicit ``git_dir`` git never discovers a ``.git`` the PR content might add.
        """

        home = getattr(self, "_git_home", None)
        if home is None:
            home = Path(tempfile.mkdtemp(prefix="nexus-ultra-git-home-")).resolve()
            self._git_home = home
        # Every filter driver the repository config defines is blanked, so an in-tree
        # .gitattributes cannot select a driver that runs a command on checkout/apply.
        base = {key: os.environ[key] for key in GIT_ENV_ALLOWLIST if key in os.environ}
        base.update({"HOME": str(home), "XDG_CONFIG_HOME": str(home), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        return git_safe_env(
            home=home,
            filter_drivers=self._configured_filter_drivers(base),
            git_dir=git_dir,
            work_tree=work_tree,
        )

    def _configured_filter_drivers(self, base_env: dict[str, str]) -> list[str]:
        cached = getattr(self, "_filter_drivers", None)
        if cached is not None:
            return cached
        listed = subprocess.run(  # noqa: S603 - argv list, no shell; reads config only
            ["git", "config", "--name-only", "--get-regexp", r"^filter\."],
            cwd=self.project_root,
            env=base_env,
            capture_output=True,
            text=True,
            check=False,
        )
        names = sorted(
            {
                line[len("filter.") : line.rfind(".")]
                for line in (listed.stdout or "").splitlines()
                if line.startswith("filter.") and line.count(".") >= 2
            }
        )
        self._filter_drivers = names
        return names

    def _git_run(
        self, args: list[str], *, cwd: Path | None = None, mirror: Path | None = None
    ) -> subprocess.CompletedProcess:
        """Run git with GIT_SAFE_CONFIG. ``mirror`` runs it in the per-run worktree with the
        git dir pinned (validated) instead of discovered from PR-controlled content."""

        if mirror is not None:
            git_dir = self._mirror_git_dir(mirror)
            return subprocess.run(  # noqa: S603 - argv list, no shell
                ["git", *args],
                cwd=mirror,
                env=self._git_env(git_dir=git_dir, work_tree=mirror),
                capture_output=True,
                text=True,
                check=False,
            )
        return subprocess.run(  # noqa: S603 - argv list, no shell
            ["git", *args],
            cwd=cwd or self.project_root,
            env=self._git_env(),
            capture_output=True,
            text=True,
            check=False,
        )

    def _mirror_git_dir(self, execution_root: Path) -> Path:
        """The worktree git dir written by our own ``git worktree add``, validated: ``.git``
        must be a regular file (not a symlink/dir) naming a dir under this repo's
        ``worktrees/`` admin area."""

        dot_git = execution_root / ".git"
        try:
            info = os.lstat(dot_git)
        except OSError as exc:
            raise UltraReviewError("mirror_git_dir_missing") from exc
        if not stat.S_ISREG(info.st_mode):
            raise UltraReviewError("mirror_git_dir_not_regular_file")
        text = dot_git.read_text(encoding="utf-8").strip()
        if not text.startswith("gitdir: "):
            raise UltraReviewError("mirror_git_dir_unparseable")
        git_dir = Path(text[len("gitdir: ") :])
        if not git_dir.is_absolute():
            git_dir = (execution_root / git_dir).resolve()
        common = self._git(["rev-parse", "--path-format=absolute", "--git-common-dir"]).strip()
        admin = Path(common).resolve() / "worktrees"
        if admin not in git_dir.resolve().parents:
            raise UltraReviewError("mirror_git_dir_outside_repository")
        return git_dir.resolve()

    def _unsafe_patch_summary(self, diff_path: Path) -> list[str]:
        """``git apply --summary`` lines (git's parser) that create/delete/re-mode a symlink or
        gitlink, or rename/copy a path; ``["patch_unparseable"]`` when git rejects the patch."""

        # Run at the repository top: from a subdirectory git apply silently skips paths
        # outside it, which would hide exactly the entries this check exists to see.
        summary = self._git_run(["apply", "--summary", "--numstat", str(diff_path)], cwd=self.project_root)
        if summary.returncode != 0:
            return ["patch_unparseable"]
        return unsafe_summary_lines(summary.stdout or "")

    def _post_apply_violations(self, execution_root: Path) -> list[str]:
        """Authoritative containment check after the patch is applied: lstat-walk the mirror
        (never following links). Any non-regular, non-directory entry fails, except a symlink
        HEAD already tracks with the identical target (not patch-introduced): kept when it
        resolves inside the mirror, unlinked when it points outside. Returns the offending
        relative paths."""

        root = execution_root.resolve()
        self._neutralized_head_links: list[str] = []
        head_links: dict[str, str] | None = None

        def accept_symlink(path: Path, rel: str) -> bool:
            nonlocal head_links
            if head_links is None:
                head_links = self._head_symlink_targets()
            target = os.readlink(path)
            if head_links.get(rel) != target:
                return False
            resolved = path.resolve()
            if resolved != root and root not in resolved.parents:
                # Already in HEAD (not introduced by the patch) but pointing outside:
                # removed from the mirror so nothing can read through it.
                os.unlink(path)
                self._neutralized_head_links.append(rel)
            return True

        return [
            rel for rel in lstat_walk_violations(execution_root, on_symlink=accept_symlink) if rel != ".git"
        ]

    def _head_symlink_targets(self) -> dict[str, str]:
        listed = subprocess.run(  # noqa: S603 - argv list, no shell
            ["git", "ls-tree", "-r", "-z", "HEAD"],
            cwd=self.project_root,
            env=self._git_env(),
            capture_output=True,
            check=False,
        )
        links: dict[str, str] = {}
        for record in (listed.stdout or b"").split(b"\0"):
            if not record.startswith(SYMLINK_MODE.encode() + b" "):
                continue
            meta, _, raw_path = record.partition(b"\t")
            sha = meta.split()[-1].decode("ascii", errors="ignore")
            blob = subprocess.run(  # noqa: S603 - argv list, no shell
                ["git", "cat-file", "blob", sha],
                cwd=self.project_root,
                env=self._git_env(),
                capture_output=True,
                check=False,
            )
            if blob.returncode == 0:
                links[raw_path.decode("utf-8", errors="surrogateescape")] = blob.stdout.decode(
                    "utf-8", errors="surrogateescape"
                )
        return links

    @staticmethod
    def _diff_policy_violations(diff_text: str) -> dict[str, list[str]]:
        """Paths the diff makes (or keeps) symlinks, and paths with a ``.git`` component."""

        return diff_policy_violations(diff_text)

    def _git(self, args: list[str]) -> str:
        result = self._git_run(args)
        if result.returncode != 0:
            raise UltraReviewError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout

    def _run_id(self) -> str:
        return "ultra-review-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
