#!/usr/bin/env python3
"""Local, read-mostly pre-push check for Nexus-new pull requests (#1916).

Runs the ceremony checks that most often fail a PR in CI, before the push:

1. ``bindings``: PR body ``NEXUS_CORE_ISSUE`` marker, ``Closes #N`` and the
   ``NEXUS_ISSUE_INTENT_V1`` block, using the trusted gate's own validators.
2. ``merge_lane``: whether a ``NEXUS_MERGE_LANE_V1`` block is present and passes
   the trusted lane gate. Preflight never mints a lane binding or hash.
3. ``issue``: the bound Issue is open and carries the evidence-universe marker
   that ``nexus-certify markers`` currently expects.
4. ``freshness``: the head descends from the base ref tip (Core and the trusted
   executor both require it).
5. ``dependency_contract``: the trusted controller's dependency-contract check.
6. ``git_identity``: the unprivileged executor's Git identity check.
7. ``static_ruff`` / ``static_pyright`` / ``static_bandit``: the exact-base
   regression comparison on changed files, printing the new findings.

Every check reports PASS, FAIL or SKIP with a one-line fix. Exit status is 1
when any check FAILs, otherwise 0. The gate code itself is never modified:
validators are loaded from the base ref's copy of the trusted scripts (the
same "default branch" copy CI runs) and the static comparison is classified
by the base ref's ``scripts/ops/exact_base_tool_gate.py``.

This tool holds no authority. A PASS here predicts CI; it is not a verdict.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
from types import ModuleType
from typing import Any

SCHEMA = "nexus.pr_preflight.v1"

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

# Reason codes. The Core names mirror nexus-core PR #246
# (product/clients/gate_diagnostics.py); keep them here so they are easy to
# update when that PR lands or renames a code.
PR_MISSING_CORE_ISSUE_BINDING = "PR_MISSING_CORE_ISSUE_BINDING"
ISSUE_NOT_OPEN = "ISSUE_NOT_OPEN"
NEXUS_CERTIFY_UNAVAILABLE = "NEXUS_CERTIFY_UNAVAILABLE"
ISSUE_MISSING_EVIDENCE_UNIVERSE = "ISSUE_MISSING_EVIDENCE_UNIVERSE"
ISSUE_EVIDENCE_UNIVERSE_STALE = "ISSUE_EVIDENCE_UNIVERSE_STALE"
ISSUE_EVIDENCE_UNIVERSE_BINDING_MALFORMED = "ISSUE_EVIDENCE_UNIVERSE_BINDING_MALFORMED"
BASE_REF_NOT_ANCESTOR = "BASE_REF_NOT_ANCESTOR"
# Local codes for gates whose CI message has no stable reason code.
DEPENDENCY_CONTRACT_DRIFT = "DEPENDENCY_CONTRACT_DRIFT"
EXECUTOR_GIT_IDENTITY_MISMATCH = "EXECUTOR_GIT_IDENTITY_MISMATCH"
MERGE_LANE_BINDING_MISSING = "MERGE_LANE_BINDING_MISSING"
STATIC_NEW_REGRESSION = "NEW_REGRESSION"

TRUSTED_LANE_GATE_PATH = "scripts/ops/trusted_merge_lane_gate.py"
TRUSTED_ANCHOR_PATH = "scripts/ops/trusted_deletion_anchor.py"
TOOL_GATE_PATH = "scripts/ops/exact_base_tool_gate.py"

# Source of truth: nexus-core .github/actions/issue-gate/action.yml ("resolve"
# step). The gate requires exactly one match of this pattern in the PR body.
CORE_ISSUE_MARKER_RE = re.compile(r"<!--\s*NEXUS_CORE_ISSUE:\s*([1-9][0-9]*)\s*-->")
# Source of truth: nexus-core product/clients/issue_golden_path.py
# (_issue_evidence_universe_marker).
EVIDENCE_PREFIX = "<!-- NEXUS_CORE_EVIDENCE_UNIVERSE: "
EVIDENCE_SUFFIX = " -->"
SHA256_VALUE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# Source of truth: .github/workflows/{lint,typecheck,security}.yml, steps
# "Decide cheap exact-base impact" and "Resolve exact revisions and worktree".
# tests/ops/test_pr_preflight.py asserts these strings still appear in the
# workflows so a workflow edit cannot silently drift from preflight.
PY_SCOPE = ("nexus/*.py", "nexus/**/*.py", "scripts/ops/*.py", "scripts/ops/**/*.py")
STATIC_TOOLS: dict[str, dict[str, Any]] = {
    "ruff": {
        "workflow": ".github/workflows/lint.yml",
        "trigger_files": ("pyproject.toml", "ruff.toml", "uv.lock"),
        "config_files": ("pyproject.toml", "ruff.toml"),
        "scope": ("*.py",),
        "fallback": None,
    },
    "pyright": {
        "workflow": ".github/workflows/typecheck.yml",
        "trigger_files": ("pyproject.toml", "pyrightconfig.json", "uv.lock"),
        "config_files": ("pyproject.toml", "pyrightconfig.json", "uv.lock"),
        "scope": PY_SCOPE,
        "fallback": "nexus/core",
    },
    "bandit": {
        "workflow": ".github/workflows/security.yml",
        "trigger_files": ("pyproject.toml", ".bandit", "bandit.yaml", "uv.lock"),
        "config_files": ("pyproject.toml", ".bandit", "bandit.yaml"),
        "scope": PY_SCOPE,
        "fallback": "nexus/core",
    },
}

LANE_FIX = (
    "the Owner/authority path adds NEXUS_MERGE_LANE_V1 (#1749/#1817); preflight "
    "never mints it. Pass --lane-owner-pending to record that this is intended."
)


@dataclass
class CheckResult:
    check: str
    status: str
    code: str = ""
    detail: str = ""
    fix: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class PreflightError(RuntimeError):
    pass


@dataclass
class Context:
    repo: Path
    base_ref: str
    base_sha: str
    head_sha: str
    repository: str
    body: str | None
    title: str | None
    pr_number: int | None
    issue_number: int | None
    issue_json: dict[str, Any] | None
    nexus_certify: str | None
    tools_venv: Path
    lane_owner_pending: bool
    module_cache: dict[str, ModuleType] = field(default_factory=dict)


# --------------------------------------------------------------------------
# small helpers


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if check and proc.returncode != 0:
        raise PreflightError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def _git_bytes(repo: Path, *args: str) -> bytes | None:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    return proc.stdout if proc.returncode == 0 else None


def _load_trusted_module(ctx: Context, path: str) -> ModuleType:
    """Import the base ref's copy of a trusted gate script (what CI runs)."""
    if path in ctx.module_cache:
        return ctx.module_cache[path]
    source = _git_bytes(ctx.repo, "show", f"{ctx.base_sha}:{path}")
    if source is None:
        raise PreflightError(f"{path} is not present at base {ctx.base_sha[:12]}")
    directory = Path(tempfile.mkdtemp(prefix="nexus-pr-preflight-mod-"))
    target = directory / Path(path).name
    target.write_bytes(source)
    name = f"_preflight_trusted_{Path(path).stem}"
    spec = importlib.util.spec_from_file_location(name, target)
    if spec is None or spec.loader is None:
        raise PreflightError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    ctx.module_cache[path] = module
    return module


def _core_issue_markers(body: str) -> list[str]:
    return CORE_ISSUE_MARKER_RE.findall(body)


def parse_evidence_marker(body: str) -> tuple[str | None, bool, int]:
    """Return (value, malformed, count) for NEXUS_CORE_EVIDENCE_UNIVERSE lines."""
    matches: list[str] = []
    malformed = False
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("<!--") or "NEXUS_CORE_EVIDENCE_UNIVERSE" not in stripped:
            continue
        if not (stripped.startswith(EVIDENCE_PREFIX) and stripped.endswith(EVIDENCE_SUFFIX)):
            malformed = True
            continue
        value = stripped[len(EVIDENCE_PREFIX) : -len(EVIDENCE_SUFFIX)]
        if not SHA256_VALUE_RE.fullmatch(value):
            malformed = True
            continue
        matches.append(value)
    if malformed or len(matches) > 1:
        return None, True, len(matches)
    return (matches[0] if matches else None), False, len(matches)


def suggested_blocks(issue: int) -> dict[str, str]:
    """Paste-ready, authority-free body bindings for one Issue the PR closes."""
    intent = json.dumps([{"issue": issue, "on_merge": "CLOSE"}])
    return {
        "closes": f"Closes #{issue}.",
        "core_issue": f"<!-- NEXUS_CORE_ISSUE: {issue} -->",
        "issue_intent": f"<!-- NEXUS_ISSUE_INTENT_V1\n{intent}\nNEXUS_ISSUE_INTENT_V1 -->",
    }


# --------------------------------------------------------------------------
# checks


def check_bindings(ctx: Context) -> CheckResult:
    name = "bindings"
    if ctx.body is None:
        return CheckResult(name, SKIP, detail="no PR body", fix="pass --body-file FILE or --pr N")
    markers = _core_issue_markers(ctx.body)
    issue = ctx.issue_number or (int(markers[0]) if len(markers) == 1 else None)
    blocks = suggested_blocks(issue) if issue else {}
    if len(markers) != 1:
        return CheckResult(
            name,
            FAIL,
            PR_MISSING_CORE_ISSUE_BINDING,
            f"PR body has {len(markers)} NEXUS_CORE_ISSUE markers; the Core gate needs exactly one",
            "add exactly one '<!-- NEXUS_CORE_ISSUE: N -->' line (see --print-blocks)",
            {"suggested_blocks": blocks},
        )
    try:
        gate = _load_trusted_module(ctx, TRUSTED_LANE_GATE_PATH)
    except PreflightError as exc:
        return CheckResult(name, SKIP, detail=str(exc), fix="fetch the base ref and rerun")
    try:
        intent = gate.validate_issue_closure_intent(ctx.body)
        messages = gate._candidate_commit_messages(
            ctx.repo, base_sha=ctx.base_sha, head_sha=ctx.head_sha
        )
        gate.validate_final_merge_intent_binding(
            pr_body=ctx.body,
            pr_number=ctx.pr_number or 1,
            head_sha=ctx.head_sha,
            base_sha=ctx.base_sha,
            expected_pr_number=ctx.pr_number or 1,
            expected_head_sha=ctx.head_sha,
            expected_base_sha=ctx.base_sha,
            merge_method="squash",
            commit_title=ctx.title,
            commit_message=messages,
        )
    except gate.LaneBindingError as exc:
        code = str(exc).split(":", 1)[0]
        return CheckResult(
            name,
            FAIL,
            code,
            str(exc)[:400],
            "make 'Closes #N' prose, commit messages and NEXUS_ISSUE_INTENT_V1 agree",
            {"suggested_blocks": blocks},
        )
    closes = [i["issue_number"] for i in intent["intents"] if i["on_merge"] == "CLOSE"]
    detail = f"NEXUS_CORE_ISSUE: {markers[0]}; intents={intent['intents']}"
    if int(markers[0]) not in {i["issue_number"] for i in intent["intents"]}:
        detail += " (bound Issue has no NEXUS_ISSUE_INTENT_V1 entry; CI allows this)"
    return CheckResult(name, PASS, detail=detail, data={"closes": closes})


def check_merge_lane(ctx: Context) -> CheckResult:
    name = "merge_lane"
    if ctx.body is None:
        return CheckResult(name, SKIP, detail="no PR body", fix="pass --body-file FILE or --pr N")
    try:
        gate = _load_trusted_module(ctx, TRUSTED_LANE_GATE_PATH)
    except PreflightError as exc:
        return CheckResult(name, SKIP, detail=str(exc), fix="fetch the base ref and rerun")
    present = gate.START_MARKER in ctx.body or gate.END_MARKER in ctx.body
    if not present:
        status = SKIP if ctx.lane_owner_pending else FAIL
        return CheckResult(
            name,
            status,
            MERGE_LANE_BINDING_MISSING,
            "no NEXUS_MERGE_LANE_V1 block; the Trusted controller will BLOCK until one is added",
            LANE_FIX,
            {"present": False},
        )
    try:
        gate.extract_binding(ctx.body)
    except gate.LaneBindingError as exc:
        return CheckResult(
            name,
            FAIL,
            str(exc),
            "NEXUS_MERGE_LANE_V1 block does not parse",
            LANE_FIX,
            {"present": True, "parses": False},
        )
    event = {
        "event_name": "pull_request_target",
        "repository": {"full_name": ctx.repository},
        "pull_request": {
            "number": ctx.pr_number or gate.ENFORCEMENT_START_PR_NUMBER + 1_000_000,
            "base": {"sha": ctx.base_sha},
            "head": {"sha": ctx.head_sha},
            "body": ctx.body,
            "title": ctx.title,
        },
        # No sender: preflight cannot speak for the Owner, so a rebind that
        # needs the Owner as event sender is reported as unverifiable.
    }
    try:
        result = gate.validate_event(event, repo_root=ctx.repo)
    except gate.LaneBindingError as exc:
        code = str(exc).split(":", 1)[0]
        if code == "OWNER_LANE_REBIND_SENDER_NOT_OWNER":
            return CheckResult(
                name,
                SKIP,
                code,
                "rebind needs the Owner as event sender; not checkable locally",
                "the Owner pushes or edits the PR",
                {"present": True, "parses": True},
            )
        return CheckResult(
            name,
            FAIL,
            code,
            f"trusted lane gate BLOCK: {exc}"[:400],
            LANE_FIX,
            {"present": True, "parses": True},
        )
    return CheckResult(
        name,
        PASS,
        detail=f"lane gate PASS ({result.get('reason')})",
        data={"present": True, "parses": True},
    )


def _resolve_nexus_certify(explicit: str | None) -> str | None:
    candidates = [explicit, os.environ.get("NEXUS_CERTIFY"), shutil.which("nexus-certify")]
    candidates.append(str(Path.home() / "workspace/nexus-core/.venv/bin/nexus-certify"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


_CORE_PIN_RE = re.compile(r"James3014/nexus-core/[^\s@]+@([0-9a-f]{40})")


_CHECK_OUTCOME_STATUSES = frozenset({"MISSING", "STALE", "MALFORMED"})


def _certify_hint(ctx: Context) -> str:
    pin = "<pin>"
    workflow = ctx.repo / ".github/workflows/nexus-core-issue-completion.yml"
    try:
        found = _CORE_PIN_RE.search(workflow.read_text(encoding="utf-8"))
    except OSError:
        found = None
    if found:
        pin = found.group(1)
    return (
        "use the nexus-certify version pinned in "
        ".github/workflows/nexus-core-issue-completion.yml, e.g. "
        f"`uvx --from git+https://github.com/James3014/nexus-core@{pin} nexus-certify`"
    )


def _expected_markers(ctx: Context, issue: int) -> tuple[dict[str, Any] | None, str]:
    tool = _resolve_nexus_certify(ctx.nexus_certify)
    if tool is None:
        return None, "nexus-certify not found"
    help_text = subprocess.run(
        [tool, "markers", "--help"], capture_output=True, text=True, check=False
    ).stdout
    command = [tool, "markers", "--repo", str(ctx.repo), "--issue", str(issue), "--json"]
    # nexus-core #246 adds a read-only `markers --check`; use it when present and
    # fall back to comparing against the plain marker output otherwise.
    if "--check" in help_text and ctx.issue_json is None:
        command.append("--check")
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict):
        output = (proc.stderr or proc.stdout).strip()[:300]
        return None, f"nexus-certify markers exited {proc.returncode}: {output}"
    if proc.returncode != 0:
        check = payload.get("issue_check")
        status = check.get("status") if isinstance(check, dict) else None
        documented = (
            proc.returncode == 1 and "--check" in command and status in _CHECK_OUTCOME_STATUSES
        )
        if not documented:
            output = (proc.stderr or proc.stdout).strip()[:300]
            return None, f"nexus-certify markers exited {proc.returncode}: {output}"
    payload["_tool"] = tool
    return payload, ""


def _fetch_issue(ctx: Context, issue: int) -> dict[str, Any]:
    if ctx.issue_json is not None:
        return ctx.issue_json
    proc = subprocess.run(
        ["gh", "issue", "view", str(issue), "-R", ctx.repository, "--json", "state,body,title"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise PreflightError(f"gh issue view {issue} failed: {proc.stderr.strip()[:200]}")
    return json.loads(proc.stdout)


def check_issue(ctx: Context) -> CheckResult:
    name = "issue"
    issue = ctx.issue_number
    if issue is None and ctx.body is not None:
        markers = _core_issue_markers(ctx.body)
        issue = int(markers[0]) if len(markers) == 1 else None
    if issue is None:
        return CheckResult(
            name,
            SKIP,
            detail="no bound Issue",
            fix="add a NEXUS_CORE_ISSUE marker or pass --issue N",
        )
    try:
        data = _fetch_issue(ctx, issue)
    except PreflightError as exc:
        return CheckResult(name, SKIP, detail=str(exc), fix="check `gh auth status`")
    if str(data.get("state", "")).upper() != "OPEN":
        return CheckResult(
            name,
            FAIL,
            ISSUE_NOT_OPEN,
            f"Issue #{issue} is {data.get('state')}",
            "reopen the Issue or bind the PR to an open Issue",
        )
    expected, error = _expected_markers(ctx, issue)
    unavailable_fix = _certify_hint(ctx)
    if expected is None:
        return CheckResult(
            name,
            FAIL,
            NEXUS_CERTIFY_UNAVAILABLE,
            f"Issue #{issue} is open; marker cannot be determined: {error}",
            unavailable_fix,
        )
    expected_line = str(expected.get("issue_marker") or "")
    marker_value = parse_evidence_marker(expected_line)[0]
    if marker_value is None:
        return CheckResult(
            name,
            FAIL,
            NEXUS_CERTIFY_UNAVAILABLE,
            "nexus-certify markers returned an empty or invalid issue_marker "
            "(expected sha256:<64 hex>)",
            unavailable_fix,
        )
    body = str(data.get("body") or "")
    value, malformed, _count = parse_evidence_marker(body)
    info = {"expected_marker": expected_line, "nexus_certify": expected.get("_tool")}
    if malformed:
        return CheckResult(
            name,
            FAIL,
            ISSUE_EVIDENCE_UNIVERSE_BINDING_MALFORMED,
            f"Issue #{issue} has a malformed or repeated NEXUS_CORE_EVIDENCE_UNIVERSE marker",
            f"keep exactly one line: {expected_line}",
            info,
        )
    if value is None:
        return CheckResult(
            name,
            FAIL,
            ISSUE_MISSING_EVIDENCE_UNIVERSE,
            f"Issue #{issue} body has no NEXUS_CORE_EVIDENCE_UNIVERSE marker",
            f"append to the Issue body: {expected_line}",
            info,
        )
    if f"{EVIDENCE_PREFIX}{value}{EVIDENCE_SUFFIX}" != expected_line:
        return CheckResult(
            name,
            FAIL,
            ISSUE_EVIDENCE_UNIVERSE_STALE,
            f"Issue #{issue} marker {value[:19]}... differs from the current config hash",
            f"replace the Issue marker with: {expected_line}",
            info,
        )
    return CheckResult(
        name, PASS, detail=f"Issue #{issue} open; evidence marker current", data=info
    )


def check_freshness(ctx: Context) -> CheckResult:
    name = "freshness"
    behind = int(_git(ctx.repo, "rev-list", "--count", f"{ctx.head_sha}..{ctx.base_sha}").stdout)
    ancestor = _git(
        ctx.repo, "merge-base", "--is-ancestor", ctx.base_sha, ctx.head_sha, check=False
    )
    data = {"behind": behind, "base_sha": ctx.base_sha}
    if ancestor.returncode == 0:
        return CheckResult(name, PASS, detail=f"head descends from {ctx.base_ref}", data=data)
    return CheckResult(
        name,
        FAIL,
        BASE_REF_NOT_ANCESTOR,
        f"branch is {behind} commit(s) behind {ctx.base_ref}; Core and the trusted executor require the tip as ancestor",
        f"git merge {ctx.base_ref} (no force-push), then push",
        data,
    )


def check_dependency_contract(ctx: Context) -> CheckResult:
    name = "dependency_contract"
    try:
        anchor = _load_trusted_module(ctx, TRUSTED_ANCHOR_PATH)
    except PreflightError as exc:
        return CheckResult(name, SKIP, detail=str(exc), fix="fetch the base ref and rerun")
    files = {}
    for label, rev in (("base", ctx.base_sha), ("head", ctx.head_sha)):
        for path in ("pyproject.toml", "uv.lock"):
            content = _git_bytes(ctx.repo, "show", f"{rev}:{path}")
            if content is None:
                return CheckResult(
                    name, FAIL, DEPENDENCY_CONTRACT_DRIFT, f"{path} missing at {label}"
                )
            files[(label, path)] = content
    changed = [p for p in ("pyproject.toml", "uv.lock") if files[("base", p)] != files[("head", p)]]
    try:
        anchor._validate_trusted_dependency_contract(
            files[("base", "pyproject.toml")],
            files[("head", "pyproject.toml")],
            files[("base", "uv.lock")],
            files[("head", "uv.lock")],
            pull_request_number=ctx.pr_number or 0,
            head_product_init_is_regular=anchor._tree_has_regular_file(
                ctx.repo, ctx.head_sha, "product/__init__.py"
            ),
        )
    except ValueError as exc:
        return CheckResult(
            name,
            FAIL,
            DEPENDENCY_CONTRACT_DRIFT,
            f"{exc}; changed: {', '.join(changed)}",
            "move the pyproject.toml/uv.lock change to its own Owner-authorized dependency-transition PR",
            {"changed": changed},
        )
    detail = (
        "matches trusted default" if not changed else f"authorized delta in {', '.join(changed)}"
    )
    return CheckResult(name, PASS, detail=detail, data={"changed": changed})


def check_git_identity(ctx: Context) -> CheckResult:
    """Replay the executor's Git identity conditions without the CI bundle.

    Source of truth: trusted_deletion_anchor._prepare_executor_git_context. The
    executor fails when the base is not an ancestor of the head, or when the
    ``tests`` tree rebuilt from the ``git archive`` extraction differs from the
    committed ``tests`` tree.
    """
    name = "git_identity"
    try:
        anchor = _load_trusted_module(ctx, TRUSTED_ANCHOR_PATH)
    except PreflightError as exc:
        return CheckResult(name, SKIP, detail=str(exc), fix="fetch the base ref and rerun")
    ancestor = _git(
        ctx.repo, "merge-base", "--is-ancestor", ctx.base_sha, ctx.head_sha, check=False
    )
    if ancestor.returncode != 0:
        return CheckResult(
            name,
            FAIL,
            EXECUTOR_GIT_IDENTITY_MISMATCH,
            f"base {ctx.base_sha[:12]} is not an ancestor of head (executor ancestry check)",
            f"git merge {ctx.base_ref} (no force-push), then push",
        )
    expected = _git(ctx.repo, "rev-parse", f"{ctx.head_sha}:tests", check=False).stdout.strip()
    if not expected:
        return CheckResult(name, SKIP, detail="head has no tests/ tree")
    archive = _git_bytes(ctx.repo, "archive", "--format=tar", ctx.head_sha)
    if archive is None:
        return CheckResult(name, SKIP, detail="git archive failed")
    with tempfile.TemporaryDirectory(prefix="nexus-pr-preflight-exec-") as tmp:
        source = Path(tmp) / "source"
        source.mkdir()
        with tarfile.open(fileobj=BytesIO(archive)) as tar:
            # Same member selection as the executor's extractall(filter=
            # _executor_archive_filter); "data" re-applies the identical filter.
            for member in tar.getmembers():
                if anchor._executor_archive_filter(member, str(source)) is not None:
                    tar.extract(member, source, filter="data")
        subprocess.run(["git", "init", "-q", str(source)], check=True, capture_output=True)
        try:
            rebuilt = anchor._extracted_test_tree(source)
        except subprocess.CalledProcessError as exc:
            return CheckResult(name, SKIP, detail=f"tests tree rebuild failed: {exc}")
    if rebuilt != expected:
        return CheckResult(
            name,
            FAIL,
            EXECUTOR_GIT_IDENTITY_MISMATCH,
            f"tests/ tree from git archive ({rebuilt[:12]}) != committed ({expected[:12]})",
            "check tests/ for export-ignore attributes, external symlinks or filtered files",
        )
    return CheckResult(name, PASS, detail="ancestry and tests/ tree reproduce")


def _changed_files(ctx: Context, spec: dict[str, Any]) -> list[str]:
    config_changed = (
        _git(
            ctx.repo,
            "diff",
            "--quiet",
            ctx.base_sha,
            ctx.head_sha,
            "--",
            *spec["config_files"],
            check=False,
        ).returncode
        != 0
    )
    if not config_changed:
        out = _git(
            ctx.repo, "diff", "--name-only", ctx.base_sha, ctx.head_sha, "--", *spec["scope"]
        ).stdout
        return sorted({p for p in out.splitlines() if p.endswith(".py")})
    paths: set[str] = set()
    for rev in (ctx.base_sha, ctx.head_sha):
        args = ["ls-tree", "-r", "--name-only", rev]
        if spec["fallback"]:
            args += ["--", spec["fallback"]]
        paths.update(p for p in _git(ctx.repo, *args).stdout.splitlines() if p.endswith(".py"))
    return sorted(paths)


def _impact_required(ctx: Context, tool: str, spec: dict[str, Any]) -> bool:
    for paths in (spec["trigger_files"], (spec["workflow"],), (TOOL_GATE_PATH,)):
        if (
            _git(
                ctx.repo, "diff", "--quiet", ctx.base_sha, ctx.head_sha, "--", *paths, check=False
            ).returncode
            != 0
        ):
            return True
    out = _git(
        ctx.repo, "diff", "--name-only", ctx.base_sha, ctx.head_sha, "--", *spec["scope"]
    ).stdout
    return bool(out.strip())


def _run_tool(tool: str, venv: Path, root: Path, files: list[str], output: Path) -> int:
    """Run one tool the way the workflow does; return the workflow's exit mapping."""
    present = [p for p in files if (root / p).is_file()]
    if not present:
        output.write_text(
            "[]\n"
            if tool == "ruff"
            else '{"generalDiagnostics":[]}\n'
            if tool == "pyright"
            else '{"results":[]}\n'
        )
        return 0
    bin_dir = venv / "bin"
    if tool == "ruff":
        check = subprocess.run(
            [str(bin_dir / "ruff"), "check", "--output-format", "json", *present],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        fmt = subprocess.run(
            [
                str(bin_dir / "ruff"),
                "format",
                "--check",
                "--preview",
                "--output-format",
                "json",
                *present,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        findings: list[Any] = []
        for proc in (check, fmt):
            findings.extend(json.loads(proc.stdout or "[]"))
        output.write_text(json.dumps(findings, indent=2) + "\n")
        if check.returncode > 1 or fmt.returncode > 1:
            return 2
        return 1 if check.returncode or fmt.returncode else 0
    if tool == "pyright":
        cmd = [
            str(bin_dir / "pyright"),
            "--pythonpath",
            str(bin_dir / "python"),
            "--outputjson",
            *present,
        ]
    else:
        cmd = [str(bin_dir / "bandit"), "-q", "-f", "json", "-ll", "-ii", *present]
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)
    output.write_text(proc.stdout)
    return proc.returncode


def _format_finding(finding: dict[str, Any]) -> str:
    return (
        f"{finding.get('path')}:{finding.get('line')}:{finding.get('column')} "
        f"{finding.get('rule_id')} {' '.join(str(finding.get('message', '')).split())[:200]}"
    )


def check_static(ctx: Context, tool: str, worktrees: dict[str, Path]) -> CheckResult:
    name = f"static_{tool}"
    spec = STATIC_TOOLS[tool]
    if not _impact_required(ctx, tool, spec):
        return CheckResult(name, PASS, detail="no exact-base impact (no in-scope change)")
    binary = ctx.tools_venv / "bin" / tool
    if not binary.is_file():
        return CheckResult(
            name,
            SKIP,
            detail=f"{binary} missing",
            fix="uv sync --frozen --all-groups --all-extras (clean venv), or pass --tools-venv",
        )
    files = _changed_files(ctx, spec)
    with tempfile.TemporaryDirectory(prefix=f"nexus-pr-preflight-{tool}-") as tmp:
        out = Path(tmp)
        base_exit = _run_tool(tool, ctx.tools_venv, worktrees["base"], files, out / "base.json")
        head_exit = _run_tool(tool, ctx.tools_venv, worktrees["head"], files, out / "head.json")
        # Classify with the base ref's gate copy, exactly as CI does (#1754).
        subprocess.run(
            [
                str(ctx.tools_venv / "bin" / "python"),
                str(worktrees["base"] / TOOL_GATE_PATH),
                "--tool",
                tool,
                "--base",
                str(out / "base.json"),
                "--head",
                str(out / "head.json"),
                "--base-root",
                str(worktrees["base"]),
                "--head-root",
                str(worktrees["head"]),
                "--base-exit-code",
                str(base_exit),
                "--head-exit-code",
                str(head_exit),
                "--output",
                str(out / "classification.json"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            report = json.loads((out / "classification.json").read_text())
        except (OSError, json.JSONDecodeError) as exc:
            return CheckResult(name, SKIP, detail=f"classifier produced no report: {exc}")
    classification = report.get("classification")
    new = [_format_finding(f) for f in report.get("new_findings", [])]
    data = {"classification": classification, "files": len(files), "new_findings": new}
    if classification == STATIC_NEW_REGRESSION:
        behind = (
            _git(
                ctx.repo, "merge-base", "--is-ancestor", ctx.base_sha, ctx.head_sha, check=False
            ).returncode
            != 0
        )
        note = " (head is behind base: some may come from newer main commits)" if behind else ""
        fix = f"fix the findings listed below (`{tool}` on the changed files)"
        if behind:
            fix = f"git merge {ctx.base_ref} first, rerun, then " + fix
        return CheckResult(
            name,
            FAIL,
            STATIC_NEW_REGRESSION,
            f"{len(new)} new {tool} finding(s) vs exact base{note}",
            fix,
            data,
        )
    if report.get("blocking"):
        return CheckResult(
            name,
            FAIL,
            str(classification),
            str(report.get("error", ""))[:300],
            f"{tool} did not produce comparable output; run it on the changed files and inspect",
            data,
        )
    return CheckResult(name, PASS, detail=f"{classification} on {len(files)} file(s)", data=data)


# --------------------------------------------------------------------------
# orchestration

CHECK_ORDER = (
    "bindings",
    "merge_lane",
    "issue",
    "freshness",
    "dependency_contract",
    "git_identity",
    "static_ruff",
    "static_pyright",
    "static_bandit",
)


def _add_worktree(repo: Path, rev: str, parent: Path, label: str) -> Path:
    path = parent / label
    _git(repo, "worktree", "add", "--detach", "--quiet", str(path), rev)
    return path


def run_checks(ctx: Context, selected: Sequence[str]) -> list[CheckResult]:
    simple: dict[str, Callable[[Context], CheckResult]] = {
        "bindings": check_bindings,
        "merge_lane": check_merge_lane,
        "issue": check_issue,
        "freshness": check_freshness,
        "dependency_contract": check_dependency_contract,
        "git_identity": check_git_identity,
    }
    results: list[CheckResult] = []
    for name in selected:
        if name in simple:
            try:
                results.append(simple[name](ctx))
            except PreflightError as exc:
                results.append(CheckResult(name, SKIP, detail=str(exc)))
    static = [n for n in selected if n.startswith("static_")]
    if static:
        parent = Path(tempfile.mkdtemp(prefix="nexus-pr-preflight-wt-"))
        worktrees: dict[str, Path] = {}
        try:
            worktrees["base"] = _add_worktree(ctx.repo, ctx.base_sha, parent, "base")
            worktrees["head"] = _add_worktree(ctx.repo, ctx.head_sha, parent, "head")
            for name in static:
                results.append(check_static(ctx, name.removeprefix("static_"), worktrees))
        finally:
            for path in worktrees.values():
                _git(ctx.repo, "worktree", "remove", "--force", str(path), check=False)
            shutil.rmtree(parent, ignore_errors=True)
    order = {name: index for index, name in enumerate(CHECK_ORDER)}
    return sorted(results, key=lambda r: order.get(r.check, 99))


def _repository_slug(repo: Path) -> str:
    url = _git(repo, "remote", "get-url", "origin", check=False).stdout.strip()
    match = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return match.group(1) if match else "James3014/Nexus-new"


def _load_pr(repository: str, number: int) -> dict[str, Any]:
    proc = subprocess.run(
        ["gh", "pr", "view", str(number), "-R", repository, "--json", "body,title,headRefOid"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise PreflightError(f"gh pr view {number} failed: {proc.stderr.strip()[:200]}")
    return json.loads(proc.stdout)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nexus-pr-preflight",
        description="Predict Nexus-new PR ceremony failures before pushing (#1916).",
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--head", default="HEAD", help="commit to check (default HEAD)")
    body = parser.add_mutually_exclusive_group()
    body.add_argument("--body-file", type=Path, help="PR body file ('-' for stdin)")
    body.add_argument("--pr", type=int, help="read body/title from this PR via gh")
    parser.add_argument("--pr-number", type=int, help="PR number for --body-file runs")
    parser.add_argument("--title", help="PR title (squash commit title)")
    parser.add_argument("--issue", type=int, help="Issue number (default: body marker)")
    parser.add_argument("--issue-json", type=Path, help="offline Issue JSON {state, body}")
    parser.add_argument("--nexus-certify", help="path to nexus-certify")
    parser.add_argument(
        "--tools-venv", type=Path, help="venv with ruff/pyright/bandit (default REPO/.venv)"
    )
    parser.add_argument("--only", help="comma-separated subset of: " + ",".join(CHECK_ORDER))
    parser.add_argument(
        "--skip-static", action="store_true", help="skip the Ruff/Pyright/Bandit runs"
    )
    parser.add_argument("--no-fetch", action="store_true", help="do not `git fetch origin` first")
    parser.add_argument(
        "--lane-owner-pending",
        action="store_true",
        help="missing lane block is intended (SKIP, not FAIL)",
    )
    parser.add_argument(
        "--print-blocks", action="store_true", help="print paste-ready body bindings"
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def _render_text(report: dict[str, Any]) -> str:
    lines = [f"nexus-pr-preflight  base={report['base_sha'][:12]}  head={report['head_sha'][:12]}"]
    for check in report["checks"]:
        code = f" [{check['code']}]" if check["code"] else ""
        lines.append(f"{check['status']:<4}  {check['check']}{code}: {check['detail']}")
        for finding in check["data"].get("new_findings", [])[:50]:
            lines.append(f"        new: {finding}")
        if check["status"] != PASS and check["fix"]:
            lines.append(f"      fix: {check['fix']}")
    if report.get("suggested_blocks"):
        lines.append("Paste-ready PR body bindings (no lane binding; that stays with the Owner):")
        lines.extend(
            "  " + line
            for block in report["suggested_blocks"].values()
            for line in block.splitlines()
        )
    lines.append(f"RESULT: {report['status']}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(_git(args.repo, "rev-parse", "--show-toplevel").stdout.strip())
    repository = _repository_slug(repo)
    if not args.no_fetch:
        _git(repo, "fetch", "--quiet", "origin", check=False)
    base_sha = _git(repo, "rev-parse", "--verify", f"{args.base_ref}^{{commit}}").stdout.strip()
    head_sha = _git(repo, "rev-parse", "--verify", f"{args.head}^{{commit}}").stdout.strip()
    body: str | None = None
    title = args.title
    pr_number = args.pr_number
    if args.pr is not None:
        pr = _load_pr(repository, args.pr)
        body, title, pr_number = pr.get("body") or "", title or pr.get("title"), args.pr
    elif args.body_file is not None:
        body = (
            sys.stdin.read()
            if str(args.body_file) == "-"
            else args.body_file.read_text(encoding="utf-8")
        )
    if title is None:
        title = _git(repo, "log", "-1", "--format=%s", head_sha).stdout.strip()
    issue_json = (
        json.loads(args.issue_json.read_text(encoding="utf-8")) if args.issue_json else None
    )
    ctx = Context(
        repo=repo,
        base_ref=args.base_ref,
        base_sha=base_sha,
        head_sha=head_sha,
        repository=repository,
        body=body,
        title=title,
        pr_number=pr_number,
        issue_number=args.issue,
        issue_json=issue_json,
        nexus_certify=args.nexus_certify,
        tools_venv=args.tools_venv or repo / ".venv",
        lane_owner_pending=args.lane_owner_pending,
    )
    selected = list(CHECK_ORDER)
    if args.only:
        wanted = {name.strip() for name in args.only.split(",")}
        unknown = wanted - set(CHECK_ORDER)
        if unknown:
            raise SystemExit(f"unknown check(s): {', '.join(sorted(unknown))}")
        selected = [name for name in CHECK_ORDER if name in wanted]
    if args.skip_static:
        selected = [name for name in selected if not name.startswith("static_")]
    results = run_checks(ctx, selected)
    status = FAIL if any(r.status == FAIL for r in results) else PASS
    issue_for_blocks = ctx.issue_number
    if issue_for_blocks is None and body is not None:
        markers = _core_issue_markers(body)
        issue_for_blocks = int(markers[0]) if len(markers) == 1 else None
    blocks: dict[str, str] = {}
    bindings = next((r for r in results if r.check == "bindings"), None)
    if issue_for_blocks and (args.print_blocks or (bindings and bindings.status == FAIL)):
        blocks = suggested_blocks(issue_for_blocks)
    report = {
        "schema": SCHEMA,
        "status": status,
        "repository": repository,
        "base_ref": args.base_ref,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "pr_number": pr_number,
        "checks": [asdict(r) for r in results],
        "suggested_blocks": blocks,
        "authority": "none: a preflight PASS predicts CI and mints no lane binding",
    }
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else _render_text(report))
    return 1 if status == FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
