#!/usr/bin/env python3
"""Local, read-mostly pre-push check for Nexus-new pull requests (#1916).

Runs the ceremony checks that most often fail a PR in CI, before the push:

1. ``bindings``: PR body ``NEXUS_CORE_ISSUE`` marker, ``Closes #N`` and the
   ``NEXUS_ISSUE_INTENT_V1`` block, using the trusted gate's own validators.
2. ``merge_lane``: lane blocks are retired (#2006/#2286), so no block is PASS;
   a block that is present is still validated by the trusted lane gate.
   Preflight never mints a lane binding or hash.
3. ``issue``: the bound Issue is open and carries the evidence-universe marker
   that the pinned ``nexus-certify markers --check`` expects. ``nexus-certify``
   is resolved at the ref Nexus-new pins (``nexus-certify-ref``), never from
   whatever happens to be on PATH; a certify failure is a FAIL, not a SKIP.
4. ``freshness``: Core's rule (nexus-core 9942db7 ``_resolve_base_and_head``):
   the head has exactly one merge-base with the base tip, else
   ``BASE_REF_NOT_ANCESTOR``. A head merely behind the tip is INFO here.
5. ``dependency_contract``: the trusted controller's dependency-contract check.
6. ``git_identity``: the unprivileged executor's Git identity check: one
   merge-base, and main must not have moved over the gate-oracle surface or
   the PR's own paths since it (``MAIN_MOVED_OVER_GATE_SURFACE``).
7. ``static_ruff`` / ``static_pyright`` / ``static_bandit``: the exact-base
   regression comparison on changed files, printing the new findings.

Every check reports PASS, FAIL, INFO or SKIP with a one-line fix. Exit status is 1
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
INFO = "INFO"

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
MAIN_MOVED_OVER_GATE_SURFACE = "MAIN_MOVED_OVER_GATE_SURFACE"
GOLDEN_CORPUS_UNVERIFIABLE = "GOLDEN_CORPUS_UNVERIFIABLE"
MERGE_LANE_BINDING_MISSING = "MERGE_LANE_BINDING_MISSING"
LANE_BLOCKS_RETIRED_NOTE = "lane blocks retired (#2006/#2286)"
STATIC_NEW_REGRESSION = "NEW_REGRESSION"
STATIC_TOOL_MISSING = "STATIC_TOOL_MISSING"

TRUSTED_LANE_GATE_PATH = "scripts/ops/trusted_merge_lane_gate.py"
TRUSTED_ANCHOR_PATH = "scripts/ops/trusted_deletion_anchor.py"
TOOL_GATE_PATH = "scripts/ops/exact_base_tool_gate.py"
# Where Nexus-new pins nexus-core (the Core gates and the certify build).
CERTIFY_PIN_WORKFLOW = ".github/workflows/nexus-core-issue-completion.yml"
CERTIFY_PIN_RE = re.compile(r"nexus-certify-ref:\s*[\"']?([0-9a-f]{40})[\"']?\s*$", re.MULTILINE)
TRUSTED_UNIVERSE_RE = re.compile(
    r"^\s*evidence-universe:\s*[\"']?trusted-config[\"']?\s*$", re.MULTILINE
)
CERTIFY_REPO_URL = "git+https://github.com/James3014/nexus-core"
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")

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
    "fix or remove the NEXUS_MERGE_LANE_V1 block (lane blocks are retired, "
    "#2006/#2286); preflight never mints it."
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
    author: str | None = None


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
    if "NEXUS_MERGE_LANE_V1" not in ctx.body:
        return CheckResult(
            name,
            PASS,
            LANE_BLOCKS_RETIRED_NOTE,
            "no NEXUS_MERGE_LANE_V1 block; lane blocks retired (#2006/#2286)",
            data={"present": False},
        )
    try:
        gate = _load_trusted_module(ctx, TRUSTED_LANE_GATE_PATH)
    except PreflightError as exc:
        return CheckResult(name, SKIP, detail=str(exc), fix="fetch the base ref and rerun")
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
            **_author_user(ctx.author),
        },
        # No sender: preflight cannot speak for the Owner, so a rebind that
        # needs the Owner as event sender is reported as unverifiable.
    }
    try:
        result = gate.validate_event(event, repo_root=ctx.repo)
    except gate.LaneBindingError as exc:
        code = str(exc).split(":", 1)[0]
        if code == "PULL_REQUEST_AUTHOR_REQUIRED":
            return CheckResult(
                name,
                SKIP,
                code,
                "inline lane bindings are checked against the PR author; author unknown",
                "pass --author LOGIN (e.g. James3014 or app/james3014-nexus-agent) or --pr N",
                {"present": True, "parses": True},
            )
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


def _author_user(author: str | None) -> dict[str, Any]:
    """Project a gh-style author login into the event's ``pull_request.user``."""
    if not author:
        return {}
    is_app = author.startswith("app/") or author.endswith("[bot]")
    login = author.removeprefix("app/") + "[bot]" if author.startswith("app/") else author
    return {"user": {"login": login, "type": "Bot" if is_app else "User"}}


def _certify_pin(ctx: Context) -> tuple[str | None, str]:
    """The nexus-core commit Nexus-new pins as ``nexus-certify-ref`` (base ref copy)."""
    refs: set[str] = set()
    for rev in (ctx.base_sha, ctx.head_sha):
        text = _git(ctx.repo, "show", f"{rev}:{CERTIFY_PIN_WORKFLOW}", check=False).stdout
        refs = set(CERTIFY_PIN_RE.findall(text))
        if refs:
            break
    if len(refs) == 1:
        return next(iter(refs)), ""
    if not refs:
        return None, f"no nexus-certify-ref found in {CERTIFY_PIN_WORKFLOW}"
    return None, f"{CERTIFY_PIN_WORKFLOW} pins several nexus-certify-ref values: {sorted(refs)}"


def _trusted_config_universe(ctx: Context) -> bool:
    """True when the issue-gate workflow derives the evidence universe from trusted config."""
    for rev in (ctx.base_sha, ctx.head_sha):
        text = _git(ctx.repo, "show", f"{rev}:{CERTIFY_PIN_WORKFLOW}", check=False).stdout
        if text:
            return TRUSTED_UNIVERSE_RE.search(text) is not None
    return False


def _resolve_nexus_certify(ctx: Context) -> tuple[list[str] | None, str, str]:
    """Return (argv prefix, pinned ref or 'override', error).

    An explicit --nexus-certify / NEXUS_CERTIFY path is an override. Otherwise
    certify is run at the pinned ref through ``uvx`` (uv caches the build), so
    version skew with whatever is installed locally cannot change the verdict.
    There is deliberately no fallback to an unpinned local build.
    """
    explicit = ctx.nexus_certify or os.environ.get("NEXUS_CERTIFY")
    if explicit:
        if Path(explicit).is_file() and os.access(explicit, os.X_OK):
            return [explicit], "override", ""
        return None, "override", f"nexus-certify override {explicit} is not an executable file"
    ref, error = _certify_pin(ctx)
    if ref is None:
        return None, "", error
    uvx = shutil.which("uvx")
    if uvx is None:
        return None, ref, "uvx not found on PATH"
    return [uvx, "--from", f"{CERTIFY_REPO_URL}@{ref}", "nexus-certify"], ref, ""


# Documented `markers --check` outcomes that exit 1 with a valid JSON payload.
_CHECK_OUTCOME_STATUSES = frozenset({"MISSING", "STALE", "MALFORMED"})


def _certify_hint(ctx: Context, ref: str, issue: int) -> str:
    pin = ref if HEX40_RE.fullmatch(ref or "") else _certify_pin(ctx)[0]
    return (
        f"use the nexus-certify version pinned (nexus-certify-ref) in {CERTIFY_PIN_WORKFLOW}: "
        f"`uvx --from {CERTIFY_REPO_URL}@{pin or '<nexus-certify-ref>'} nexus-certify "
        f"markers --issue {issue} --check` (needs uv; or pass --nexus-certify PATH to an "
        "executable built at that ref)"
    )


def _expected_markers(ctx: Context, issue: int) -> tuple[dict[str, Any] | None, str, str]:
    """Run ``nexus-certify markers``; return (payload, error, pinned ref or 'override')."""
    tool, ref, error = _resolve_nexus_certify(ctx)
    if tool is None:
        return None, f"cannot resolve nexus-certify: {error}", ref
    command = [*tool, "markers", "--repo", str(ctx.repo), "--issue", str(issue), "--json"]
    # `markers --check` exists at the pinned ref (nexus-core b245430b); it reads the live
    # Issue itself, so it is skipped for offline --issue-json runs and, for an
    # override build, when that build predates it.
    use_check = ctx.issue_json is None
    if use_check and ref == "override":
        help_text = subprocess.run(
            [*tool, "markers", "--help"], capture_output=True, text=True, check=False
        ).stdout
        use_check = "--check" in help_text
    if use_check:
        command.append("--check")
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"nexus-certify could not run: {exc}", ref
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict):
        output = (proc.stderr or proc.stdout).strip()[:300]
        return None, f"nexus-certify markers exited {proc.returncode}: {output}", ref
    if proc.returncode != 0:
        check = payload.get("issue_check")
        status = check.get("status") if isinstance(check, dict) else None
        documented = (
            proc.returncode == 1 and "--check" in command and status in _CHECK_OUTCOME_STATUSES
        )
        if not documented:
            output = (proc.stderr or proc.stdout).strip()[:300]
            return None, f"nexus-certify markers exited {proc.returncode}: {output}", ref
    payload["_tool"] = " ".join(tool)
    payload["_ref"] = ref
    return payload, "", ref


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
    if _trusted_config_universe(ctx):
        return CheckResult(
            name,
            PASS,
            detail=f"Issue #{issue} open; evidence universe derived from trusted base config",
        )
    expected, error, ref = _expected_markers(ctx, issue)
    if expected is None:
        pin_hint = f"@{ref[:12]}" if ref and ref != "override" else ""
        return CheckResult(
            name,
            FAIL,
            NEXUS_CERTIFY_UNAVAILABLE,
            f"Issue #{issue} is open; marker cannot be determined by nexus-certify{pin_hint}: "
            f"{error}",
            _certify_hint(ctx, ref, issue),
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
            _certify_hint(ctx, ref, issue),
        )
    certify_check = expected.get("issue_check")
    if isinstance(certify_check, dict) and certify_check.get("status") != "MATCH":
        status = str(certify_check.get("status"))
        codes = {
            "MISSING": ISSUE_MISSING_EVIDENCE_UNIVERSE,
            "STALE": ISSUE_EVIDENCE_UNIVERSE_STALE,
            "MALFORMED": ISSUE_EVIDENCE_UNIVERSE_BINDING_MALFORMED,
        }
        return CheckResult(
            name,
            FAIL,
            codes.get(status, NEXUS_CERTIFY_UNAVAILABLE),
            f"Issue #{issue} evidence-universe marker is {status} (nexus-certify markers --check)",
            str(certify_check.get("remediation") or f"use exactly: {expected_line}"),
            {"expected_marker": expected_line, "nexus_certify": expected.get("_tool")},
        )
    if isinstance(certify_check, dict):
        return CheckResult(
            name,
            PASS,
            detail=f"Issue #{issue} open; evidence marker current (certify @{str(ref)[:12]})",
            data={"expected_marker": expected_line, "nexus_certify": expected.get("_tool")},
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
    """Core's rule: exactly one merge-base between the base tip and the head.

    Source of truth: nexus-core 9942db7 product/clients/local_golden_path.py
    ``_resolve_base_and_head`` (``git merge-base --all``; none or several fail
    ``BASE_REF_NOT_ANCESTOR``). Merely being behind the tip satisfies Core and is
    INFO; whether main moved over gate-relevant paths is ``git_identity``'s job.
    """
    name = "freshness"
    behind = int(_git(ctx.repo, "rev-list", "--count", f"{ctx.head_sha}..{ctx.base_sha}").stdout)
    proc = _git(ctx.repo, "merge-base", "--all", ctx.base_sha, ctx.head_sha, check=False)
    bases = proc.stdout.split() if proc.returncode == 0 else []
    data = {"behind": behind, "base_sha": ctx.base_sha, "merge_bases": bases}
    if len(bases) != 1 or not HEX40_RE.fullmatch(bases[0]):
        problem = "shares no history with" if not bases else f"has {len(bases)} merge-bases with"
        return CheckResult(
            name,
            FAIL,
            BASE_REF_NOT_ANCESTOR,
            f"{ctx.base_ref} at {ctx.base_sha} {problem} HEAD {ctx.head_sha}",
            f"rebase onto {ctx.base_sha} (no criss-cross merges: Core needs a single merge-base)",
            data,
        )
    if behind == 0:
        return CheckResult(name, PASS, detail=f"head descends from {ctx.base_ref}", data=data)
    return CheckResult(
        name,
        INFO,
        detail=(
            f"behind {ctx.base_ref} by {behind} commit(s); Core accepts a single merge-base "
            "(see git_identity for whether main moved over gate or PR paths)"
        ),
        data=data,
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

    Source of truth: the base ref's trusted_deletion_anchor (what CI runs). With
    the merge-base rule (``_main_moved_overlap`` present) the executor needs
    exactly one merge-base, and the controller fails closed when main changed the
    gate-oracle surface or the PR's own paths since it. An older base copy still
    requires the base tip as an ancestor; preflight follows whichever is there.
    Both also fail when the ``tests`` tree rebuilt from the ``git archive``
    extraction differs from the committed ``tests`` tree.
    """
    name = "git_identity"
    try:
        anchor = _load_trusted_module(ctx, TRUSTED_ANCHOR_PATH)
    except PreflightError as exc:
        return CheckResult(name, SKIP, detail=str(exc), fix="fetch the base ref and rerun")
    merge_fix = f"git merge {ctx.base_ref} (no force-push), then push"
    data: dict[str, Any] = {}
    overlap_rule = getattr(anchor, "_main_moved_overlap", None)
    if overlap_rule is not None:
        proc = _git(ctx.repo, "merge-base", "--all", ctx.base_sha, ctx.head_sha, check=False)
        bases = proc.stdout.split() if proc.returncode == 0 else []
        if len(bases) != 1:
            return CheckResult(
                name,
                FAIL,
                EXECUTOR_GIT_IDENTITY_MISMATCH,
                f"base and head share {len(bases)} merge-bases (executor needs exactly one)",
                merge_fix,
                {"merge_bases": bases},
            )
        merge_base = bases[0]
        try:
            overlap = overlap_rule(ctx.repo, merge_base, ctx.base_sha, ctx.head_sha)
        except (ValueError, subprocess.CalledProcessError) as exc:
            unverifiable = str(exc).startswith(f"{GOLDEN_CORPUS_UNVERIFIABLE}:")
            remedies = getattr(anchor, "CONTROLLER_FAILURE_REMEDIES", {})
            return CheckResult(
                name,
                FAIL,
                GOLDEN_CORPUS_UNVERIFIABLE if unverifiable else EXECUTOR_GIT_IDENTITY_MISMATCH,
                f"main-moved check failed: {exc}",
                remedies.get(GOLDEN_CORPUS_UNVERIFIABLE, merge_fix) if unverifiable else merge_fix,
                {"merge_base": merge_base},
            )
        data = {"merge_base": merge_base, "overlap": overlap}
        if overlap:
            shown = ", ".join(overlap[:5]) + (" ..." if len(overlap) > 5 else "")
            return CheckResult(
                name,
                FAIL,
                MAIN_MOVED_OVER_GATE_SURFACE,
                f"main changed {len(overlap)} gate-oracle or PR path(s) since the "
                f"merge-base: {shown}",
                merge_fix,
                data,
            )
    else:
        ancestor = _git(
            ctx.repo, "merge-base", "--is-ancestor", ctx.base_sha, ctx.head_sha, check=False
        )
        if ancestor.returncode != 0:
            return CheckResult(
                name,
                FAIL,
                EXECUTOR_GIT_IDENTITY_MISMATCH,
                f"base {ctx.base_sha[:12]} is not an ancestor of head (executor ancestry "
                "check of the base ref's trusted_deletion_anchor)",
                merge_fix,
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
    rule = "single merge-base, no main overlap" if overlap_rule is not None else "ancestry"
    return CheckResult(name, PASS, detail=f"{rule} and tests/ tree reproduce", data=data)


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
            FAIL,
            STATIC_TOOL_MISSING,
            f"{binary} missing; a silent SKIP would hide regressions CI enforces",
            "run `uv sync --frozen` (or the repo's documented tool install) then rerun",
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
        [
            "gh",
            "pr",
            "view",
            str(number),
            "-R",
            repository,
            "--json",
            "body,title,headRefOid,author",
        ],
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
    parser.add_argument(
        "--author", help="PR author login (default: from --pr); inline lanes depend on it"
    )
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
        if check["status"] not in (PASS, INFO) and check["fix"]:
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
    author = args.author
    if args.pr is not None:
        pr = _load_pr(repository, args.pr)
        body, title, pr_number = pr.get("body") or "", title or pr.get("title"), args.pr
        pr_author = pr.get("author") if isinstance(pr.get("author"), dict) else {}
        author = author or pr_author.get("login")
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
        author=author,
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
