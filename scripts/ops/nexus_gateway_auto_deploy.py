#!/usr/bin/env python3
"""Unattended, health-gated MCP Gateway deployer that tracks published main (#2153).

Owner decision (#2153, 2026-10-14): routine Gateway updates no longer go through
the #526 governed rebind.  One cycle (run every few minutes by the LaunchAgent
``com.nexus.gateway-auto-deploy``, see ``install_nexus_gateway_auto_deploy.sh``):

0. Reconcile: if a previous cycle crashed mid-switch, the durable
   ``pending-switch.json`` journal is resolved first (finalize or roll back).
   A live plist that this deployer neither wrote nor adopted (a manual #526
   rebind) sets HOLD and records ``FOREIGN_PLIST``.
1. Trigger: fetch ``main`` into the existing Gateway bare repository
   (``gateway-direct/repository.git``, origin must be James3014/Nexus-new,
   private ref ``refs/nexus-auto-deploy/main``).  The candidate must be GitHub's
   ``main`` tip or an ancestor of it, and every required check (secret audit,
   Deletion guard, Exact-base impact gate) must be ``success`` from its bound
   GitHub Actions workflow, on the commit itself or on the head of the merged PR
   that produced it.  Any pending run, any GitHub error or any open runtime pin
   bump PR means no deploy (fail closed).  Main movement that touches only
   docs/tasks/tests/workflow paths is skipped until the Gateway lags by
   ``--max-irrelevant-lag`` commits (#1445).  Attempts back off exponentially; a
   candidate is given up after ``MAX_CANDIDATE_ATTEMPTS`` probe/rollback failures.
2. Build: ``deployments/a1-<sha>`` is a detached worktree of that bare repository
   (same layout as the #526 ``r1-<sha>`` deployments).  Each deployment gets its
   own venv ``venvs/a1-<sha>`` built by ``uv sync --frozen`` from the deployment's
   ``uv.lock``, so the shared clone's ``.venv`` is never used.  The venv lives
   outside the tree and the tree must still be clean after the build (#1939);
   a separate Controller worktree ``controllers/a1-<sha>`` at the same commit is
   exported as ``NEXUS_CANONICAL_SOURCE_ROOT`` so Task Card bind commits never
   touch the deployment (#1939).  The live Controller's bind commits (regular
   files under ``tasks/`` main did not touch) are carried byte for byte; the
   candidate's own ``bound_controller_problem`` must accept the result (else a
   fresh Controller without the carry, else the build fails), and a bind that
   lands after the carry defers the switch (``DEFERRED_CONTROLLER_MOVED``);
   durable state stays in ``~/.local/state`` (#1539).
3. Probe: start the candidate on a spare loopback port with a throwaway state
   dir (never the live self-hosted state) and require ``/health`` for the exact
   commit, the candidate's own GB-077 live identity probe, MCP ``tools/list``
   and ``nexus_gateway_status``.  On failure the live Gateway is left untouched.
3a. Quiescence (#2227): no switch while a governed task is in flight.  The
   live deployment's own lifecycle code classifies every task in the live
   self-hosted state dir (``IN_PROGRESS``/``ACTION_REQUIRED`` or unreadable =
   in flight; fail closed) before the build and again under the lock right
   before the plist write.  A deferral is ``DEFERRED_TASKS_IN_FLIGHT`` (not a
   failure); its age is kept in ``quiescence.json`` and the receipts, and after
   6 h one warning naming the tasks goes to #2227.  It never forces a switch;
   only a manual ``run --allow-in-flight`` does.
4. Switch: under the #526 manager's ledger lock, journal the previous plist,
   rewrite the ``com.nexus.mcp.gateway.direct`` plist, reload it, and probe the
   real port.  If that fails, restore the exact previous plist bytes and reload
   (automatic rollback).  HOLD and the pin-bump gate are re-checked right before
   the plist write.
5. Receipt: one JSON line per attempt in ``<state>/receipts.jsonl``; the last
   poll outcome is in ``<state>/status.json``.  ``check_gateway_source_drift.py``
   reports the last receipt.
6. Retention: keep the newest ``--keep`` ``a1-*`` deployments plus the live,
   previous and deployer-tool ones; ``r1-*`` deployments and anything reached
   through a symlink are never removed.
7. Kill switch: ``<state>/HOLD`` (``hold``/``release`` subcommands) or
   ``NEXUS_GATEWAY_AUTO_DEPLOY_HOLD=1`` pauses everything.  A failed rollback
   writes HOLD itself.  Run ``hold`` before any manual #526 rebind; afterwards
   ``adopt`` the new plist and ``release``.

The LaunchAgent runs this file from ``gateway-direct/auto-deploy-current``, a
symlink the installer points at a verified bootstrap worktree of main and that
every successful deploy moves to the new deployment once that tree's deployer
passes ``selftest`` with the LaunchAgent's own interpreter.  When main requires
a check this file cannot bind (``UNKNOWN_REQUIRED_CHECK``), the link moves
without a deploy (``DEPLOYER_SELF_UPDATED``, #2402) only if the candidate's own
deployer source knows every such name and every check this file can bind (plus
``FLOOR_CHECKS``) is green on the candidate; the next cycle's deployer then
applies the full gate, so a check-set change needs no reinstall.  It needs only the
stdlib plus the tree's ``scripts/ops/mcp_gateway_durable.py``, which stays the
single owner of the Gateway launchd effect.  The #526 governed rebind stays
available as a manual fallback.
"""

from __future__ import annotations

import argparse
import ast
import base64
import contextlib
import hashlib
import json
import math
import os
import plistlib
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Tuple

if __name__ == "__main__":
    # Run from a Nexus-new tree: the Gateway launchd effect lives in
    # scripts/ops/mcp_gateway_durable.py (single effect owner).
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Must equal nexus.contracts.gateway_deployment.LABEL / ENTRYPOINT / ENDPOINT
# (asserted by tests; not imported so this file stays standalone).
GATEWAY_LABEL = "com.nexus.mcp.gateway.direct"
ENTRYPOINT = "scripts/ops/nexus_mcp_gateway_http.py"
DEPLOYER = "scripts/ops/nexus_gateway_auto_deploy.py"
LIVE_PORT = 8766
REPOSITORY = "James3014/Nexus-new"
ORIGIN_URLS = (
    "https://github.com/James3014/Nexus-new.git",
    "https://github.com/James3014/Nexus-new",
    "git@github.com:James3014/Nexus-new.git",
)
# Every check name the deployer knows how to bind: each is accepted only from its
# own GitHub Actions workflow, so a stray workflow cannot post a success under the
# same name.  Which of these are required is read live from main's branch rules
# each cycle (#2173); a required name missing here blocks the deploy.
REQUIRED_CHECKS = {
    "Full published Git history secret audit": ".github/workflows/git-history-secret-audit.yml",
    "Deletion guard": ".github/workflows/deletion-guard.yml",
    "Exact-base impact gate": ".github/workflows/pytest.yml",
    # Required on main since 2026-10-16 (#1754 A); pull_request_target only, so it
    # binds through the merged PR head like Deletion guard (#2364).
    "Trusted impact gate (default branch)": ".github/workflows/trusted-impact-gate.yml",
    "Trusted dependency contract (default branch)": (
        ".github/workflows/trusted-dependency-contract.yml"
    ),
    # Required on main since 2026-10-17 (false-completion council K5); runs on
    # push to main, so it binds on the main commit like Exact-base impact gate.
    "Exact-base Pyright regression gate": ".github/workflows/typecheck.yml",
}
# Checks whose workflow runs only on pull_request_target (trusted default-branch
# workflow code).  A merged-PR-head run of these from a ``pull_request`` event
# would come from PR-controlled workflow code under the same path and name, so it
# never binds (#2364 review).  Push runs on main use main's own workflow files.
PR_TARGET_ONLY_CHECKS = frozenset({
    "Deletion guard",
    "Trusted impact gate (default branch)",
    "Trusted dependency contract (default branch)",
})
# Required contexts that are commit STATUSES posted only on PR heads by
# pull_request_target workflows (#2365): GitHub's ruleset enforces them at merge
# time and they never appear on main commits, so the deployer cannot re-verify
# them and does not wait for them.  Named exactly; any other name the deployer
# cannot bind still fails closed (UNKNOWN_REQUIRED_CHECK).
PR_HEAD_STATUS_CONTEXTS = frozenset({
    "Bindings preflight (default branch)",
    "Review record present (advisory)",
})
CHECK_APP = "github-actions"
DEPLOYMENT_PREFIX = "a1-"
TRACK_REF = "refs/nexus-auto-deploy/main"
RECEIPT_SCHEMA = "nexus.gateway.auto_deploy_receipt.v1"
STATUS_SCHEMA = "nexus.gateway.auto_deploy_status.v1"
JOURNAL_SCHEMA = "nexus.gateway.auto_deploy_pending_switch.v1"
HOLD_ENV = "NEXUS_GATEWAY_AUTO_DEPLOY_HOLD"
GATEWAY_PLIST_ENV = "NEXUS_GATEWAY_PLIST"
TOKEN_ENV = "NEXUS_MCP_GATEWAY_TOKEN"
# Paths that cannot change Gateway behaviour; anything else counts as relevant.
IRRELEVANT_PREFIXES = ("tasks/", "docs/", "tests/", ".github/", "archives/", "artifacts/")
IRRELEVANT_SUFFIXES = (".md",)
# A candidate that keeps failing the probe or the live switch is given up after
# this many attempts; a build that writes into its own tree is given up at once.
MAX_CANDIDATE_ATTEMPTS = 3
RETRYABLE_REJECTIONS = ("REJECTED_PROBE", "ROLLED_BACK")
FAILED_OUTCOMES = (
    "REJECTED_PROBE",
    "REJECTED_BUILD",
    "ROLLED_BACK",
    "ROLLBACK_FAILED",
    "BUILD_FAILED",
    "BLOCKED_NO_ROLLBACK",
    "BLOCKED_MANAGER_BUSY",
    "FOREIGN_PLIST",
    "JOURNAL_CORRUPT",
    "RECONCILE_FAILED",
)
MAX_BACKOFF_SECONDS = 6 * 60 * 60
# Task quiescence (#2227): a switch moves the Controller HEAD, which every
# non-terminal governed task is bound to, so no switch while one is in flight.
DEFERRED_OUTCOME = "DEFERRED_TASKS_IN_FLIGHT"
# The live Controller gained a bind after the carry (#1939): retried next cycle.
CONTROLLER_MOVED_OUTCOME = "DEFERRED_CONTROLLER_MOVED"
# Task action states (SelfHostedTaskService._task_action_envelope) that a
# switch would break; TERMINAL and FINAL_BLOCK tasks are not executing.
IN_FLIGHT_ACTION_STATES = ("IN_PROGRESS", "ACTION_REQUIRED")
# Deferral never ends in an automatic switch; after this long the Issue below
# gets one loud warning per deferral episode naming the blocking tasks.
QUIESCENCE_WARN_AFTER_SECONDS = 6 * 60 * 60
QUIESCENCE_REWARN_SECONDS = 24 * 60 * 60
# A new candidate re-arms the warning at most hourly (no comment per merge).
QUIESCENCE_REARM_MIN_SECONDS = 60 * 60
QUIESCENCE_ALERT_ISSUE = 2227
QUIESCENCE_CLASSIFY_TIMEOUT_SECONDS = 120
# Degraded Controller (#2230 F2): a Gateway that started with an invalid
# Controller runs DEGRADED until restarted, and /health says so in
# ``controller_binding``.  While IN_SYNC the deployer reads it and, when
# degraded, warns on the Issue below and writes a receipt (rate limited like the
# quiescence warning).  It never holds, restarts or switches: the next deploy of
# a new main commit materializes a fresh Controller and heals it.
LIVE_DEGRADED_OUTCOME = "LIVE_DEGRADED_CONTROLLER"
# Deployer-only self-update (#2402).  Main requires a check this file cannot
# bind, but the candidate's own deployer (on main, read with ``ast``, never
# imported) knows it, and every check this file CAN bind (+ FLOOR_CHECKS) is
# green on the candidate: only the ``auto-deploy-current`` link moves to the
# candidate tree, the Gateway is untouched, and the next cycle runs the new
# deployer through the normal full gate.  Neither outcome is a deploy attempt:
# they never move the debounce or backoff clock of a candidate.
SELF_UPDATED_OUTCOME = "DEPLOYER_SELF_UPDATED"
SELF_UPDATE_REFUSED_OUTCOME = "DEPLOYER_SELF_UPDATE_REFUSED"
# Module-level names the candidate's deployer source is read for.
_KNOWN_CHECK_TABLES = ("REQUIRED_CHECKS", "PR_HEAD_STATUS_CONTEXTS")
CONTROLLER_ALERT_ISSUE = 2230
# Runs with the LIVE deployment's interpreter and tree, so tasks are classified
# by exactly the lifecycle code that owns them.  Read-only: it never takes the
# task state lock or reconciles anything.
TASK_QUIESCENCE_PROBE_CODE = """
import json, sys
from pathlib import Path
root, state_dir = sys.argv[1:3]
sys.path.insert(0, root)
import nexus.orchestrator.self_hosted_task_service as lifecycle
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
durable = lifecycle.DURABLE_SELF_HOSTED_STATUSES
invalid = lifecycle.INVALID_STATE_STATUSES
base = Path(state_dir)
paths = sorted(base.glob("*.json")) if base.exists() else []
tasks = []
for path in paths:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        tasks.append({"task_id": path.stem, "action_state": "UNREADABLE"})
        continue
    if not isinstance(state, dict):
        tasks.append({"task_id": path.stem, "action_state": "UNREADABLE"})
        continue
    status = state.get("status")
    if not isinstance(status, str) or status in invalid or status not in durable:
        # The lifecycle maps an unknown status to FINAL_BLOCK; fail closed here.
        tasks.append({"task_id": path.stem, "action_state": "INVALID_STATUS"})
        continue
    action = SelfHostedTaskService._task_action_envelope(state)
    tasks.append({"task_id": path.stem, "action_state": str(action.get("action_state"))})
# Assisted provider jobs run as children the Gateway tracks in memory; a reload
# orphans them, so a non-terminal job is in flight too.
jobs = base / "assisted_provider_jobs"
for path in sorted(jobs.glob("*.json")) if jobs.exists() else []:
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        tasks.append({"task_id": "assist." + path.stem, "action_state": "UNREADABLE"})
        continue
    job = job if isinstance(job, dict) else {}
    status = job.get("status")
    if status == "UNKNOWN_REQUIRES_RECONCILE" or job.get("reconciliation_required"):
        tasks.append({"task_id": "assist." + path.stem, "action_state": "ASSIST_RECONCILE"})
    elif status not in ("COMPLETED", "FAILED", "CANCELLED"):
        tasks.append({"task_id": "assist." + path.stem, "action_state": "ASSIST_RUNNING"})
    elif status == "CANCELLED" and job.get("process_killed") is False:
        # Cancellation could not confirm the child exited.
        tasks.append({"task_id": "assist." + path.stem, "action_state": "ASSIST_UNSETTLED"})
print(json.dumps({"schema": "nexus.gateway.task_quiescence.v1", "tasks": tasks}))
"""
# Open PRs that bump the runtime/dependency pin (or anchor such a bump).  While
# one is in flight no deploy starts, so deploys and pin bumps never interleave.
PIN_BUMP_PR = re.compile(
    r"auto/workforce-|pin nexus-runtime|pin-runtime|trusted-anchor|trusted runtime identity"
    r"|dependency.{0,20}transition",
    re.IGNORECASE,
)
PIN_FILES = ("uv.lock", "pyproject.toml", "requirements/canonical-runtime.txt")
PIN_BUMP_MAX_AGE_SECONDS = 3 * 24 * 60 * 60
# Parked pin bumps (#2309).  A non-draft, non-stale pin-bump PR blocks deploys
# only while it could plausibly merge soon.  It is PARKED (listed in
# ``ignored_parked``, warned, and no longer blocking) when either
#   * GitHub reports ``mergeable_state == "dirty"`` (a merge conflict: it cannot
#     merge as is), reason ``mergeable_state=dirty``; or
#   * it has held deploys at the SAME head SHA for more than the park threshold
#     (default ``PIN_BUMP_PARK_SECONDS``), reason ``held>threshold``.
# The holding clock is the first cycle that saw (PR number, head SHA) blocking,
# kept in ``pin-bump-park.json`` in the state dir.  A new head push restarts it;
# a missing, corrupt or future-dated record restarts it too (fail toward
# blocking, never toward parking).  The threshold can be raised or lowered only
# by explicitly setting ``PIN_BUMP_PARK_ENV`` or ``--pin-bump-park-seconds``.
PIN_BUMP_PARK_SECONDS = 60 * 60
PIN_BUMP_PARK_MIN_SECONDS = 60
PIN_BUMP_PARK_ENV = "NEXUS_GATEWAY_AUTO_DEPLOY_PIN_PARK_SECONDS"
PIN_PARK_SCHEMA = "nexus.gateway.auto_deploy.pin_park.v1"
PIN_PARK_REASON_DIRTY = "mergeable_state=dirty"
PIN_PARK_REASON_HELD = "held>threshold"
_SHA = re.compile(r"^[0-9a-f]{40}$")
# RFC 3339 date-time with an explicit offset; fractions up to microseconds (#2169).
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:[Zz]|[+-]\d{2}:\d{2})$"
)
# Timeline events that move a PR head; one of unknown age counts as recent.
_HEAD_PUSH_EVENTS = ("head_ref_force_pushed", "head_ref_restored")
_DEPLOYMENT_NAME = re.compile(r"(?:^|/)[ar]1-([0-9a-f]{40})$")
_SHELL_UNSAFE = ('"', "$", "`", "\\", "\n", "\r", "\x00")
# Each deployment runs the nexus-core revision its own tree pins (#2181).  The pin
# is read as text from the candidate tree (never imported) and materialized as a
# clean detached checkout ``core/<sha>`` of a bare ``core.git`` next to the
# Gateway repository; the wrapper exports it as NEXUS_CORE_REPO_ROOT.
CORE_REPOSITORY_URL = "https://github.com/James3014/nexus-core.git"
CORE_ORIGIN_URLS = (
    CORE_REPOSITORY_URL,
    "https://github.com/James3014/nexus-core",
    "git@github.com:James3014/nexus-core.git",
)
CORE_PIN_FILE = "nexus/orchestrator/canonical_core_transport.py"
_CORE_PIN_LINE = re.compile(
    r"^CANONICAL_CORE_REVISION\s*(?::\s*str\s*)?=\s*[\"']([^\"'\n]*)[\"']\s*(?:#.*)?$",
    re.MULTILINE,
)
# The Planner-selected codeintel hook (#1579) reaches the Repository
# Intelligence Engine only through NEXUS_RIE_ENGINE_ROOT / NEXUS_RIE_PYTHON_BIN.
# The engine revision is pinned by the candidate tree itself (text parse, never
# imported); the deployer materializes it like Core, as a clean detached
# checkout ``rie/<sha>`` of a bare ``rie.git``.  Unlike Core it is advisory: a
# missing or unverified engine never blocks a deploy, the wrapper just unsets
# both variables and the hook reports NOT_APPLICABLE.
RIE_REPOSITORY_URL = "https://github.com/James3014/repository-intelligence-engine.git"
RIE_ORIGIN_URLS = (
    RIE_REPOSITORY_URL,
    "https://github.com/James3014/repository-intelligence-engine",
    "git@github.com:James3014/repository-intelligence-engine.git",
)
RIE_PIN_FILE = "nexus/services/rie_knowledge_applicability.py"
_RIE_PIN_LINE = re.compile(
    r"^PINNED_RIE_ENGINE_REVISION\s*(?::\s*str\s*)?=\s*[\"']([^\"'\n]*)[\"']\s*(?:#.*)?$",
    re.MULTILINE,
)
RIE_ENV_ENGINE_ROOT = "NEXUS_RIE_ENGINE_ROOT"
RIE_ENV_PYTHON_BIN = "NEXUS_RIE_PYTHON_BIN"
RIE_FETCH_TIMEOUT_SECONDS = 120
RIE_ENGINE_CHECK_TIMEOUT_SECONDS = 60
# Run with ``-B -I`` (no bytecode, no PYTHON* env, no cwd/user site): the
# engine's CLI module must import from the pinned checkout alone.
RIE_ENGINE_CHECK_CODE = """
import sys
sys.path.insert(0, sys.argv[1])
import repository_intelligence.cli as cli
from pathlib import Path
here = Path(cli.__file__).resolve()
assert Path(sys.argv[1]).resolve() in here.parents, here
print("OK")
"""

# GB-077 per-request timeout and tries: a freshly started candidate can take
# longer than _fetch_gateway_health's 2 s default to answer /health.  Only
# transport failures are retried; an identity failure is final.
GB077_TIMEOUT_SECONDS = 30.0
GB077_ATTEMPTS = 3
GB077_PROBE_CODE = """
import json, sys, time
root, url, commit, timeout, attempts = sys.argv[1:6]
sys.path.insert(0, root)
from scripts.ops.run_golden_behavior_eval import _fetch_gateway_health, probe_gb077_live_gateway_identity
history = []
for attempt in range(int(attempts)):
    ok, detail = probe_gb077_live_gateway_identity(
        fetch_health=lambda: _fetch_gateway_health(url, timeout=float(timeout)),
        evaluated_identity=lambda: (commit, False),
    )
    try:
        reasons = json.loads(detail).get("reasons") or []
    except (ValueError, AttributeError):
        reasons = ["unparseable_probe_detail"]
    history.append({"attempt": attempt + 1, "ok": ok, "reasons": reasons})
    # Retry only transport failures (the health read itself timed out or failed).
    # A health answer that fails identity (wrong git_head, dirty, not ok) is final.
    transport_only = bool(reasons) and all(r.startswith("gateway_unreachable:") for r in reasons)
    if ok or not transport_only:
        break
    time.sleep(2)
try:
    # The probe reports its fixed live endpoint; record the URL actually probed.
    parsed = json.loads(detail)
    parsed.setdefault("observed", {})["endpoint"] = url
    parsed["attempts"] = history
    detail = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
except (ValueError, AttributeError):
    pass
print(detail)
sys.exit(0 if ok else 1)
"""

# Runs with the candidate's interpreter and the wrapper's NEXUS_CORE_REPO_ROOT in a
# fresh process: the transport resolves Core exactly as the Gateway would (#2181).
CORE_PROVENANCE_PROBE_CODE = """
import json, sys
root = sys.argv[1]
sys.path.insert(0, root)
from nexus.orchestrator.canonical_core_transport import core_provenance_status
print(json.dumps(core_provenance_status(), sort_keys=True, default=str))
"""

# Expected Core ``source_digest`` of a pinned checkout (#2246), with Core's own
# algorithm: ``product/protocol/build_identity.py`` is a leaf module and is loaded
# by file path (the ``product`` package is never imported).  Run with ``-B -I``
# so no bytecode lands in the checkout.  The digest is taken over the commit's
# git objects and over the files on disk; the deployer requires both to agree.
CORE_BUILD_IDENTITY_FILE = "product/protocol/build_identity.py"
CORE_SOURCE_DIGEST_CODE = r"""
import importlib.util, json, subprocess, sys
checkout, revision = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location(
    "_nexus_core_build_identity", checkout + "/product/protocol/build_identity.py"
)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def git(*args, data=None):
    return subprocess.run(
        ["git", "-C", checkout, *args],
        input=data, capture_output=True, check=True, timeout=300,
    ).stdout


entries = {}
for raw in git("ls-tree", "-r", "-z", "--full-tree", revision, "--", "product").split(b"\0"):
    if raw:
        meta, _, rel = raw.partition(b"\t")
        mode, kind, sha = meta.decode("ascii").split(" ")
        entries[rel.decode("utf-8")] = (mode, kind, sha)
shipped = core.select_shipped_paths(entries)
for rel in shipped:
    mode, kind, _sha = entries[rel]
    if kind != "blob" or mode not in ("100644", "100755"):
        raise SystemExit("CORE_SOURCE_NOT_A_REGULAR_FILE:" + rel)
batch = git("cat-file", "--batch", data="".join(entries[r][2] + "\n" for r in shipped).encode())
files, offset = [], 0
for rel in shipped:
    end = batch.index(b"\n", offset)
    sha, kind, size = batch[offset:end].decode("ascii").split(" ")
    if sha != entries[rel][2] or kind != "blob":
        raise SystemExit("CORE_SOURCE_BATCH_MISMATCH:" + rel)
    start, stop = end + 1, end + 1 + int(size)
    if stop >= len(batch) or batch[stop : stop + 1] != b"\n":
        raise SystemExit("CORE_SOURCE_BATCH_TRUNCATED:" + rel)
    files.append((rel, batch[start:stop]))
    offset = stop + 1
if offset != len(batch):
    raise SystemExit("CORE_SOURCE_BATCH_TRAILING_OUTPUT")
print(json.dumps({
    "committed": core.source_digest_of_files(files),
    "on_disk": core.source_digest(checkout + "/product"),
    "files": len(files),
}))
"""
_CORE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class DeployError(RuntimeError):
    pass


# HOLD text written when a validated journal could not be reconciled.
RECONCILE_FAILED_HOLD = "auto-hold: RECONCILE_FAILED"


def _park_seconds_or_none(value: Any) -> Optional[int]:
    """A park threshold override in whole seconds (>= the minimum), else None."""
    text = str(value).strip()
    if not (text.isascii() and text.isdigit()):
        return None
    seconds = int(text)
    return seconds if seconds >= PIN_BUMP_PARK_MIN_SECONDS else None


@dataclass(frozen=True)
class Config:
    gateway_root: Path
    state_dir: Path
    plist: Path
    env_file: Path
    canonical_state_dir: Path
    repository: str = REPOSITORY
    track_branch: str = "main"
    python_version: str = "3.12"
    uv_extras: str = "all"
    keep: int = 3
    min_interval_seconds: int = 600
    max_irrelevant_lag: int = 25
    probe_timeout_seconds: float = 120.0
    gh: str = "gh"
    quiescence_warn_after_seconds: int = QUIESCENCE_WARN_AFTER_SECONDS
    alert_issue: int = QUIESCENCE_ALERT_ISSUE
    pin_bump_park_seconds: int = PIN_BUMP_PARK_SECONDS
    # True when PIN_BUMP_PARK_ENV is set but invalid (the default is used and warned).
    pin_bump_park_env_invalid: bool = False

    @classmethod
    def default(cls, home: Optional[Path] = None, **overrides: Any) -> "Config":
        home = Path.home() if home is None else home
        support = home / "Library/Application Support/Nexus"
        # Same override the durable manager honours (scripts/ops/mcp_gateway_durable.py).
        plist_override = os.environ.get(GATEWAY_PLIST_ENV, "")
        values: Dict[str, Any] = {
            "gateway_root": support / "gateway-direct",
            "state_dir": home / ".local/state/nexus-gateway-auto-deploy",
            "plist": Path(plist_override)
            if plist_override
            else home / "Library/LaunchAgents" / f"{GATEWAY_LABEL}.plist",
            "env_file": support / "mcp-gateway.env",
            "canonical_state_dir": home / ".local/state/Nexus-new-self-hosted-state",
        }
        raw_park = os.environ.get(PIN_BUMP_PARK_ENV)
        if raw_park is not None and raw_park.strip():
            park = _park_seconds_or_none(raw_park)
            if park is None:
                values["pin_bump_park_env_invalid"] = True
            else:
                values["pin_bump_park_seconds"] = park
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)

    @property
    def bare_repo(self) -> Path:
        return self.gateway_root / "repository.git"

    @property
    def deployments(self) -> Path:
        return self.gateway_root / "deployments"

    @property
    def venvs(self) -> Path:
        return self.gateway_root / "venvs"

    @property
    def controllers(self) -> Path:
        """Controller worktrees (#1939): Task Card binds land here, never in deployments/."""
        return self.gateway_root / "controllers"

    @property
    def tool_link(self) -> Path:
        """Tree the auto-deploy LaunchAgent runs this script from (moves to each new deployment)."""
        return self.gateway_root / "auto-deploy-current"

    @property
    def core_bare_repo(self) -> Path:
        return self.gateway_root / "core.git"

    @property
    def core_checkouts(self) -> Path:
        return self.gateway_root / "core"

    @property
    def rie_bare_repo(self) -> Path:
        return self.gateway_root / "rie.git"

    @property
    def rie_checkouts(self) -> Path:
        return self.gateway_root / "rie"

    @property
    def pycache_prefixes(self) -> Path:
        """Per-deployment ``PYTHONPYCACHEPREFIX`` dirs, outside ``core/`` and every tree.

        With a prefix Python never reads an in-tree ``__pycache__``, so bytecode
        planted next to the pinned Core sources (which the source digest does
        not cover) is never executed (#2246).
        """
        return self.gateway_root / "pycache"

    @property
    def receipts(self) -> Path:
        return self.state_dir / "receipts.jsonl"

    @property
    def hold_file(self) -> Path:
        return self.state_dir / "HOLD"

    @property
    def journal(self) -> Path:
        return self.state_dir / "pending-switch.json"

    @property
    def known_plists(self) -> Path:
        return self.state_dir / "known-plists.json"

    @property
    def probe_state_root(self) -> Path:
        return self.state_dir / "probe-state"

    @property
    def deferrals(self) -> Path:
        """Deferral episode log (#2227); kept out of receipts.jsonl so backoff,
        give-up counting and the drift checker only ever see real attempts."""
        return self.state_dir / "deferrals.jsonl"

    @property
    def retained_controllers(self) -> Path:
        """Controllers kept from pruning because they hold a bind not carried (#1939)."""
        return self.state_dir / "retained-controllers.json"

    @property
    def quiescence_file(self) -> Path:
        """The current deferral episode (#2227); absent when nothing is deferred."""
        return self.state_dir / "quiescence.json"

    @property
    def pin_park_file(self) -> Path:
        """When each blocking pin-bump PR head was first seen (#2309)."""
        return self.state_dir / "pin-bump-park.json"

    @property
    def controller_alert_file(self) -> Path:
        """When the degraded-Controller warning (#2230) was last posted."""
        return self.state_dir / "controller_alert.json"


# --------------------------------------------------------------------------- host


class Host:
    """Every process, launchd and clock effect.  Tests replace this class."""

    # How long GATEWAY_LOCK and the R1 ledger lock are waited for.
    lock_timeout_seconds: float = 30.0

    def run(
        self,
        argv: List[str],
        *,
        cwd: Optional[Path] = None,
        env: Optional[Mapping[str, Optional[str]]] = None,
        timeout: float = 1800,
    ) -> subprocess.CompletedProcess:
        full_env = dict(os.environ)
        for key, value in (env or {}).items():
            if value is None:  # explicit removal of an inherited variable
                full_env.pop(key, None)
            else:
                full_env[key] = value
        return subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            env=full_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def start(self, command: str, log_path: Path) -> Callable[[], None]:
        """Start a candidate Gateway; return a function that stops it."""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(log_path, "ab")  # noqa: SIM115 - closed by the returned stop()
        proc = subprocess.Popen(  # noqa: S603 - fixed /bin/zsh wrapper, quoted paths
            ["/bin/zsh", "-c", command],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

        def stop() -> None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=15)
            log.close()

        return stop

    def reload_service(self, plist: Path, label: str) -> None:
        # The durable manager stays the single Gateway launchd effect owner.
        from scripts.ops.mcp_gateway_durable import reload_gateway_launch_agent

        if label != GATEWAY_LABEL:
            raise DeployError("GATEWAY_LABEL_MISMATCH")
        try:
            reload_gateway_launch_agent(plist)
        except Exception as exc:  # noqa: BLE001
            raise DeployError(f"GATEWAY_RELOAD_FAILED:{exc}") from exc

    def manager_lock_path(self, cfg: Config) -> Path:
        """The #526 manager's own ``GATEWAY_LOCK``; it must manage this gateway root."""
        from scripts.ops import mcp_gateway_durable as durable

        lock = Path(durable.GATEWAY_LOCK)
        if Path(durable.GATEWAY_STATE_ROOT).resolve() != cfg.gateway_root.resolve():
            raise DeployError(
                f"MANAGER_LOCK_UNAVAILABLE:manager state root {durable.GATEWAY_STATE_ROOT} "
                f"is not {cfg.gateway_root}"
            )
        return lock

    def tasks_in_flight(self, cfg: Config, live_plist: bytes) -> Dict[str, Any]:
        """Classify the live self-hosted tasks with the live deployment's own code (#2227).

        Fail closed: anything that cannot be read or classified is ``UNKNOWN``,
        which defers the switch exactly like an in-flight task.
        """
        try:
            root, python = live_root(live_plist), live_python(live_plist)
        except DeployError as exc:
            return {"verdict": "UNKNOWN", "reason": f"LIVE_PLIST_UNREADABLE:{exc}"[:300]}
        if root is None or python is None or not python.exists() or not root.is_dir():
            return {"verdict": "UNKNOWN", "reason": "LIVE_INTERPRETER_OR_ROOT_MISSING"}
        try:
            result = self.run(
                [
                    str(python),
                    "-W",
                    "ignore",
                    "-c",
                    TASK_QUIESCENCE_PROBE_CODE,
                    str(root),
                    str(cfg.canonical_state_dir),
                ],
                env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": os.environ.get("PATH", "")},
                timeout=QUIESCENCE_CLASSIFY_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 - unknown is in flight
            return {"verdict": "UNKNOWN", "reason": f"CLASSIFIER_FAILED:{type(exc).__name__}"}
        return classify_task_report(result.returncode, result.stdout or "", result.stderr or "")

    def controller_problem(
        self, python: Path, root: Path, controller: Path, code_root: Optional[Path] = None
    ) -> Optional[str]:
        """The candidate tree's own verdict on the Controller (#1939); None when bound.

        ``code_root`` defaults to ``root``: the candidate judges with its own code.
        """
        code = root if code_root is None else code_root
        try:
            result = self.run(
                [
                    str(python),
                    "-W",
                    "ignore",
                    "-c",
                    CONTROLLER_CHECK_CODE,
                    str(code),
                    str(root),
                    str(controller),
                ],
                env={"PYTHONDONTWRITEBYTECODE": "1", "NEXUS_CANONICAL_SOURCE_ROOT": ""},
                timeout=120,
            )
        except Exception as exc:  # noqa: BLE001 - unknown is not bound
            return f"CONTROLLER_CHECK_FAILED:{type(exc).__name__}"
        lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
        if result.returncode != 0 or not lines:
            return f"CONTROLLER_CHECK_EXIT_{result.returncode}"
        verdict = lines[-1]
        if verdict == "OK":
            return None
        match = re.match(r"[A-Z][A-Z0-9_]{0,63}", verdict)
        return match.group(0) if match else "CONTROLLER_CHECK_UNPARSEABLE"

    def post_issue_comment(self, cfg: Config, body: str, issue: Optional[int] = None) -> bool:
        """One comment on the alert Issue (default: quiescence); False on any failure."""
        try:
            result = self.run(
                [
                    cfg.gh,
                    "issue",
                    "comment",
                    str(int(cfg.alert_issue if issue is None else issue)),
                    "--repo",
                    cfg.repository,
                    "--body",
                    body,
                ],
                timeout=60,
            )
        except Exception:  # noqa: BLE001 - a failed alert is retried next cycle
            return False
        return result.returncode == 0

    def r1_recovery_block(self, cfg: Config) -> Optional[str]:
        """Why an open #526 R1 recovery forbids a Gateway effect now, else None.

        Delegates to the manager's own ``open_r1_recovery_blocks_effect`` on its
        own ledger (fail closed on a corrupt, locked or missing-with-history
        ledger).  Callers hold ``GATEWAY_LOCK`` first (lock order GATEWAY_LOCK
        then ledger), so no R1 request can start between check and effect.
        """
        from scripts.ops import mcp_gateway_durable as durable

        try:
            self.manager_lock_path(cfg)  # same state root as this gateway
            return durable.open_r1_recovery_blocks_effect(ledger=Path(durable.GATEWAY_LEDGER))
        except Exception as exc:  # noqa: BLE001 - an unknown R1 state blocks
            return f"R1_CHECK_FAILED:{type(exc).__name__}:{exc}"[:300]

    @contextlib.contextmanager
    def r1_guard(self, cfg: Config) -> Iterator[None]:
        """Hold the R1 ledger lock (``ledger.jsonl.lock``) across a Gateway effect.

        Taken after ``GATEWAY_LOCK`` (order GATEWAY_LOCK -> ledger, as the
        manager's own ``gateway_reload`` does) and held from the R1 check through
        journal, plist write, reload, live probe and any rollback.  R1 appends
        REQUESTED under this lock only, so it cannot open mid-effect; an R1
        request arriving meanwhile times out and fails closed on R1's side
        (intended).  The lock is re-entrant per process and thread, so
        ``open_r1_recovery_blocks_effect`` still reads under it.
        """
        from scripts.ops import mcp_gateway_durable as durable

        try:
            self.manager_lock_path(cfg)
            path = durable.GatewayLedger(Path(durable.GATEWAY_LEDGER)).lock_path
            lock = durable.InterProcessLock(path, timeout=self.lock_timeout_seconds)
            lock.__enter__()
        except DeployError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DeployError(f"MANAGER_LOCK_UNAVAILABLE:r1-ledger:{exc}") from exc
        try:
            yield
        finally:
            lock.__exit__(None, None, None)

    @contextlib.contextmanager
    def manager_lock(self, cfg: Config) -> Iterator[None]:
        """Hold the #526 manager's ledger lock so a manual rebind cannot interleave."""
        from scripts.ops import mcp_gateway_durable as durable

        try:
            lock = durable.InterProcessLock(
                self.manager_lock_path(cfg), timeout=self.lock_timeout_seconds
            )
            lock.__enter__()
        except DeployError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DeployError(f"MANAGER_LOCK_UNAVAILABLE:{exc}") from exc
        try:
            yield
        finally:
            lock.__exit__(None, None, None)

    def free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _must(host: Host, argv: List[str], code: str, **kwargs: Any) -> str:
    result = host.run(argv, **kwargs)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:300]
        raise DeployError(f"{code}:{detail}")
    return result.stdout


def _git(cfg: Config, *args: str) -> List[str]:
    return ["git", "--git-dir", str(cfg.bare_repo), *args]


# ------------------------------------------------------------------ GitHub gates


def gh_api_getter(host: Host, gh: str = "gh") -> Callable[[str], Any]:
    def get(path: str) -> Any:
        return json.loads(_must(host, [gh, "api", path], "GH_API_FAILED", timeout=60))

    return get


def _bound_runs(
    api_get: Callable[[str], Any],
    repo: str,
    sha: str,
    name: str,
    *,
    origin: Dict[str, Any],
    integration_id: Optional[int] = None,
) -> List[dict]:
    """Check runs for ``name`` on ``sha`` that provably belong to ``origin``.

    A run counts only if it comes from the bound Actions workflow (path), from
    the required issuer (``app.id == integration_id`` when the rules name one,
    and app ``github-actions``), and from the expected trigger: a ``push`` to
    the tracked branch for the candidate commit itself, or the merged PR for a
    PR-head run (event, head branch, head repository, created before the
    merge, and the PR number whenever GitHub lists one).  GitHub empties
    ``pull_requests`` once a PR is merged, so head branch + repository + the
    PR's lifetime (created_at .. merged_at, per attempt) are the binding there;
    anything that cannot be bound does not count.
    """
    query = urllib.parse.urlencode({"check_name": name, "per_page": 100})
    runs = api_get(f"repos/{repo}/commits/{sha}/check-runs?{query}").get("check_runs") or []
    bound = []
    for run in runs:
        app = run.get("app") or {}
        if run.get("name") != name or app.get("slug") != CHECK_APP:
            continue
        if integration_id is not None and app.get("id") != integration_id:
            continue
        suite = (run.get("check_suite") or {}).get("id")
        if not suite:
            continue
        workflow_runs = api_get(f"repos/{repo}/actions/runs?check_suite_id={int(suite)}")
        candidates = workflow_runs.get("workflow_runs") or []
        if any(
            w.get("path") == REQUIRED_CHECKS[name]
            and _from_origin(run, w, sha, origin)
            and _pr_event_allowed(name, w, origin)
            for w in candidates
        ):
            bound.append(run)
    return bound


def _pr_event_allowed(name: str, workflow_run: dict, origin: Dict[str, Any]) -> bool:
    """A merged-PR-head run of a pull_request_target-only check must be that event."""
    if origin["kind"] != "pr" or name not in PR_TARGET_ONLY_CHECKS:
        return True
    return workflow_run.get("event") == "pull_request_target"


def _from_origin(run: dict, workflow_run: dict, sha: str, origin: Dict[str, Any]) -> bool:
    if workflow_run.get("head_sha") != sha:
        return False
    if (workflow_run.get("head_repository") or {}).get("full_name") != origin["head_repo"]:
        return False
    if origin["kind"] == "push":
        return (
            workflow_run.get("event") == "push"
            and workflow_run.get("head_branch") == (origin["branch"])
        )
    if workflow_run.get("event") not in ("pull_request_target", "pull_request"):
        return False
    if workflow_run.get("head_branch") != origin["head_ref"]:
        return False
    # Lifetime of the merged PR: an earlier PR with the same branch and head sha
    # created its runs before this PR existed; a re-run after the merge is a new
    # attempt.  The workflow run's created_at is its first attempt; each check
    # run is one attempt with its own started_at/completed_at, so the attempt
    # times decide (run_started_at would follow a post-merge re-run and wrongly
    # discard the original pre-merge attempt).
    opened = _parse_time(origin["created_at"])
    merged = _parse_time(origin["merged_at"])
    created = _parse_time(workflow_run.get("created_at"))
    started = _parse_time(run.get("started_at"))
    if opened is None or merged is None or created is None or started is None:
        return False
    if not opened <= created <= merged or not opened <= started <= merged:
        return False
    # Only a provably finished attempt binds: a missing/null completed_at could
    # have finished after the merge.
    completed = _parse_time(run.get("completed_at"))
    if completed is None or not started <= completed <= merged:
        return False
    for listed in (run.get("pull_requests"), workflow_run.get("pull_requests")):
        numbers = {p.get("number") for p in listed or []}
        if numbers and origin["number"] not in numbers:
            return False
    return True


def _check_state(runs: List[dict], source: str) -> Dict[str, Any]:
    # Any run that is not completed (queued runs have started_at=null) keeps the
    # check PENDING; otherwise the newest run (largest id) decides.
    if any(r.get("status") != "completed" for r in runs):
        return {"state": "PENDING", "sha": source}
    latest = max(runs, key=lambda r: int(r.get("id") or 0))
    state = "SUCCESS" if latest.get("conclusion") == "success" else "FAILURE"
    return {"state": state, "conclusion": latest.get("conclusion"), "sha": source}


# The deployer's bar never drops below these, whatever the live rules say.
FLOOR_CHECKS = (
    "Full published Git history secret audit",
    "Deletion guard",
    "Exact-base impact gate",
)


def live_required_checks(
    api_get: Callable[[str], Any], *, repo: str = REPOSITORY, branch: str = "main"
) -> Dict[str, Optional[int]]:
    """Required status checks on ``branch`` as {name: integration_id or None}.

    Every ``required_status_checks`` rule must be well-formed; one malformed rule
    makes the whole answer unusable (fail closed), even if another rule parses.
    """
    required: Dict[str, Optional[int]] = {}
    for rule in _paged(api_get, f"repos/{repo}/rules/branches/{branch}"):
        if not isinstance(rule, dict):
            raise DeployError("BRANCH_RULES_MALFORMED:rule")
        if rule.get("type") != "required_status_checks":
            continue
        checks = (rule.get("parameters") or {}).get("required_status_checks")
        if not isinstance(checks, list) or not checks:
            raise DeployError("BRANCH_RULES_MALFORMED:required_status_checks")
        for check in checks:
            context = check.get("context") if isinstance(check, dict) else None
            issuer = check.get("integration_id") if isinstance(check, dict) else None
            if not isinstance(context, str) or not context:
                raise DeployError("BRANCH_RULES_MALFORMED:context")
            if issuer is not None and (isinstance(issuer, bool) or not isinstance(issuer, int)):
                raise DeployError("BRANCH_RULES_MALFORMED:integration_id")
            if context in required and required[context] != issuer:
                raise DeployError(f"BRANCH_RULES_CONFLICTING_ISSUER:{context}")
            required[context] = issuer
    if not required:
        # No required checks at all would make every commit "green": fail closed.
        raise DeployError("BRANCH_RULES_REQUIRE_NO_CHECKS")
    return required


def live_required_check_names(
    api_get: Callable[[str], Any], *, repo: str = REPOSITORY, branch: str = "main"
) -> List[str]:
    """Status-check names the branch rules (ruleset) currently require on ``branch``."""
    return list(live_required_checks(api_get, repo=repo, branch=branch))


def required_checks(
    api_get: Callable[[str], Any], sha: str, *, repo: str = REPOSITORY, branch: str = "main"
) -> Dict[str, Any]:
    """GREEN only when every check in (live required set + FLOOR_CHECKS) is success.

    Otherwise PENDING, RED, UNKNOWN (including an unreadable ruleset or a
    floor check with no bound run) or UNKNOWN_REQUIRED_CHECK (main requires a
    check this deployer cannot bind).
    """
    try:
        live = live_required_checks(api_get, repo=repo, branch=branch)
    except Exception as exc:  # noqa: BLE001 - an unreadable ruleset fails closed
        return {"verdict": "UNKNOWN", "error": f"RULESET:{type(exc).__name__}:{exc}"[:300]}
    merge_time_only = [name for name in live if name in PR_HEAD_STATUS_CONTEXTS]
    live = {name: issuer for name, issuer in live.items() if name not in merge_time_only}
    unknown = [name for name in live if name not in REQUIRED_CHECKS]
    if unknown:
        return {
            "verdict": "UNKNOWN_REQUIRED_CHECK",
            "unknown_required": unknown,
            # What this deployer CAN bind, for the deployer-only self-update (#2402).
            "known_required": {n: i for n, i in live.items() if n not in unknown},
            "merge_time_only": merge_time_only,
            "checks": {},
        }
    return _bind_required(
        api_get, sha, live, repo=repo, branch=branch, merge_time_only=merge_time_only
    )


def bindable_subset_checks(
    api_get: Callable[[str], Any],
    sha: str,
    known_required: Dict[str, Optional[int]],
    *,
    repo: str = REPOSITORY,
    branch: str = "main",
) -> Dict[str, Any]:
    """The verdict of ``required_checks`` restricted to the names this deployer can bind.

    Only for the deployer-only self-update (#2402), never for a Gateway switch:
    every live required check this file can bind, plus ``FLOOR_CHECKS``, must be
    bound and green on ``sha``.  Nothing this file can verify is skipped.
    """
    if any(name not in REQUIRED_CHECKS for name in known_required):
        return {"verdict": "UNKNOWN", "error": "SUBSET_NOT_BINDABLE"}
    return _bind_required(
        api_get, sha, dict(known_required), repo=repo, branch=branch, merge_time_only=[]
    )


def _bind_required(
    api_get: Callable[[str], Any],
    sha: str,
    live: Dict[str, Optional[int]],
    *,
    repo: str,
    branch: str,
    merge_time_only: List[str],
) -> Dict[str, Any]:
    """Bind every name in ``live`` + ``FLOOR_CHECKS`` on ``sha`` (all in REQUIRED_CHECKS)."""
    detail: Dict[str, Any] = {}
    required = {**live, **{name: live.get(name) for name in FLOOR_CHECKS}}
    floor_added = [name for name in FLOOR_CHECKS if name not in live]
    push_origin = {"kind": "push", "branch": branch, "head_repo": repo}
    try:
        merged_prs: Optional[List[Dict[str, Any]]] = None
        for name, issuer in required.items():
            runs = _bound_runs(api_get, repo, sha, name, origin=push_origin, integration_id=issuer)
            source = sha
            if not runs:
                if merged_prs is None:
                    merged_prs = [
                        {
                            "kind": "pr",
                            "number": p["number"],
                            "head_sha": p["head"]["sha"],
                            "head_ref": p["head"]["ref"],
                            "head_repo": ((p["head"].get("repo") or {}).get("full_name")),
                            "merged_at": p["merged_at"],
                            "created_at": p.get("created_at"),
                        }
                        for p in api_get(f"repos/{repo}/commits/{sha}/pulls") or []
                        if p.get("merged_at")
                        and p.get("merge_commit_sha") == sha
                        and (p.get("base") or {}).get("ref") == branch
                    ]
                for pr in merged_prs:
                    runs = _bound_runs(
                        api_get, repo, pr["head_sha"], name, origin=pr, integration_id=issuer
                    )
                    if runs:
                        source = pr["head_sha"]
                        break
            detail[name] = _check_state(runs, source) if runs else {"state": "MISSING"}
    except Exception as exc:  # noqa: BLE001 - any transport/shape error fails closed
        return {
            "verdict": "UNKNOWN",
            "error": f"{type(exc).__name__}:{exc}"[:300],
            "checks": detail,
        }
    states = {d["state"] for d in detail.values()}
    if states == {"SUCCESS"}:
        verdict = "GREEN"
    elif "FAILURE" in states:
        verdict = "RED"
    elif "MISSING" in states:
        verdict = "UNKNOWN"
    else:
        verdict = "PENDING"
    return {
        "verdict": verdict,
        "required": list(required),
        "floor_added": floor_added,
        "merge_time_only": merge_time_only,
        "missing": [n for n, d in detail.items() if d["state"] == "MISSING"],
        "checks": detail,
    }


def on_github_main(
    api_get: Callable[[str], Any], sha: str, *, repo: str = REPOSITORY, branch: str = "main"
) -> Dict[str, Any]:
    """The candidate must be GitHub's branch tip or an ancestor of it (fail closed)."""
    try:
        tip = api_get(f"repos/{repo}/branches/{branch}")["commit"]["sha"]
        if tip == sha:
            return {"ok": True, "tip": tip, "relation": "tip"}
        relation = api_get(f"repos/{repo}/compare/{sha}...{tip}").get("status")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"[:300]}
    return {"ok": relation in ("ahead", "identical"), "tip": tip, "relation": relation}


def deployer_known_checks(source: str) -> Optional[List[str]]:
    """Check names a deployer source binds or knowingly skips, read without running it.

    ``REQUIRED_CHECKS`` (exactly one module-level literal dict of str -> str)
    union ``PR_HEAD_STATUS_CONTEXTS`` (at most one module-level literal set or
    ``frozenset({...})`` of str; absent means none, as before #2370).  Anything
    else (a syntax error, a computed value, a second assignment) is None: the
    self-update then fails closed (#2402).  So is any other write to either
    table anywhere in the source (``del X[...]``, ``X[...] = ...``, ``X |= ...``,
    ``X.pop(...)`` or another mutating method, a ``global`` rebind): the literal
    would then over-claim names the running module no longer has (#2409 N2).
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    if _check_tables_mutated(tree):
        return None
    values: Dict[str, List[ast.expr]] = {name: [] for name in _KNOWN_CHECK_TABLES}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id in values:
                values[target.id].append(value)
    if len(values["REQUIRED_CHECKS"]) != 1 or len(values["PR_HEAD_STATUS_CONTEXTS"]) > 1:
        return None
    try:
        table = ast.literal_eval(values["REQUIRED_CHECKS"][0])
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None
    if not isinstance(table, dict) or not all(
        isinstance(k, str) and k and isinstance(v, str) and v for k, v in table.items()
    ):
        return None
    names = list(table)
    for node in values["PR_HEAD_STATUS_CONTEXTS"]:
        literal: ast.expr = node
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "frozenset"
            and len(node.args) <= 1
            and not node.keywords
        ):
            if not node.args:
                continue
            literal = node.args[0]
        try:
            contexts = ast.literal_eval(literal)
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
            return None
        if not isinstance(contexts, (set, frozenset, list, tuple)) or not all(
            isinstance(c, str) and c for c in contexts
        ):
            return None
        names.extend(sorted(c for c in contexts if c not in names))
    return names


# Methods that change a dict or set in place; any call of one on a check table
# makes the table unreadable for the self-update (fail closed, #2409 N2).
_MUTATING_METHODS = frozenset({
    "pop",
    "popitem",
    "clear",
    "update",
    "setdefault",
    "remove",
    "discard",
    "add",
    "difference_update",
    "intersection_update",
    "symmetric_difference_update",
    "__delitem__",
    "__setitem__",
    "__ior__",
    "__iand__",
    "__isub__",
    "__ixor__",
})


def _check_tables_mutated(tree: ast.Module) -> bool:
    """True when anything but one plain top-level assignment writes a check table."""
    tables = set(_KNOWN_CHECK_TABLES)

    def table_of(node: ast.AST) -> Optional[str]:
        while isinstance(node, (ast.Subscript, ast.Attribute, ast.Starred)):
            node = node.value
        return node.id if isinstance(node, ast.Name) and node.id in tables else None

    top_level = {
        id(target)
        for stmt in tree.body
        if isinstance(stmt, (ast.Assign, ast.AnnAssign))
        for target in (stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target])
        if isinstance(target, ast.Name)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Delete) and any(table_of(t) for t in node.targets):
            return True
        if isinstance(node, (ast.Global, ast.Nonlocal)) and tables & set(node.names):
            return True
        if isinstance(node, ast.Name) and node.id in tables:
            if isinstance(node.ctx, (ast.Store, ast.Del)) and id(node) not in top_level:
                return True
        if isinstance(node, (ast.Subscript, ast.Attribute)) and isinstance(
            node.ctx, (ast.Store, ast.Del)
        ):
            if table_of(node):
                return True
        if isinstance(node, ast.AugAssign) and table_of(node.target):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _MUTATING_METHODS
            and table_of(node.func.value)
        ):
            return True
    return False


def _parse_time(value: Any) -> Optional[float]:
    """Epoch seconds of an RFC 3339 timestamp (``Z``, ``+00:00``, fractions), else None.

    A value without a UTC offset, or one that is not a full date-time, is
    unparseable: guessing its zone could make an event look older than it is.
    """
    if not isinstance(value, str) or not _RFC3339.match(value):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value[-1] in "Zz" else value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.timestamp()


def _paged(api_get: Callable[[str], Any], path: str) -> Iterator[dict]:
    """Every item of a paginated list endpoint (100 per page)."""
    sep = "&" if "?" in path else "?"
    page = 1
    while True:
        items = api_get(f"{path}{sep}per_page=100&page={page}") or []
        if not isinstance(items, list):
            raise DeployError(f"PAGINATION_NOT_A_LIST:{path}")
        yield from items
        if len(items) < 100:
            return
        page += 1


def _is_stale_pin_pr(api_get: Callable[[str], Any], repo: str, pr: dict, now: float) -> bool:
    """Stale only if PR creation, head commit time AND last head push are all old.

    Each signal is checked in turn and the first recent (or unknown) one stops
    the search, so a fresh PR - even one carrying an old commit - always blocks.
    """
    cutoff = now - PIN_BUMP_MAX_AGE_SECONDS

    def recent(value: Optional[float]) -> bool:
        return value is None or value > cutoff

    if recent(_parse_time(pr.get("created_at"))):
        return False
    head = (pr.get("head") or {}).get("sha")
    if not head:
        return False
    commit = api_get(f"repos/{repo}/commits/{head}").get("commit") or {}
    if recent(_parse_time((commit.get("committer") or {}).get("date"))):
        return False
    for event in _paged(api_get, f"repos/{repo}/issues/{pr['number']}/timeline"):
        when = _timeline_time(api_get, repo, event)
        if when is None and event.get("event") in _HEAD_PUSH_EVENTS:
            # A head push of unknown age may be recent: fail closed (#2169).
            return False
        # Any other event without a usable timestamp is ignored, never
        # "recent forever" (a dateless ``committed`` event stays stale).
        if when is not None and when > cutoff:
            return False
    return True


def _timeline_time(api_get: Callable[[str], Any], repo: str, event: dict) -> Optional[float]:
    """Timestamp of a push-like timeline event, from documented fields only."""
    kind = event.get("event")
    if kind in _HEAD_PUSH_EVENTS:
        return _parse_time(event.get("created_at"))
    if kind != "committed":
        return None
    for actor in ("committer", "author"):
        when = _parse_time((event.get(actor) or {}).get("date"))
        if when is not None:
            return when
    sha = event.get("sha")
    if isinstance(sha, str) and _SHA.match(sha):
        commit = api_get(f"repos/{repo}/commits/{sha}").get("commit") or {}
        return _parse_time((commit.get("committer") or {}).get("date"))
    return None


def _load_pin_park(path: Optional[Path]) -> Dict[str, Any]:
    """The park record ({str(number): entry}); {} when absent or untrustworthy.

    An empty record means every blocking PR head is "first seen now", so a
    lost or corrupt file can only delay parking, never cause it (#2309).
    """
    if path is None:
        return {}
    data = _read_json_object(path)
    if data is None or data.get("schema") != PIN_PARK_SCHEMA:
        return {}
    prs = data.get("prs")
    return dict(prs) if isinstance(prs, dict) else {}


def _save_pin_park(path: Path, prs: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": PIN_PARK_SCHEMA, "prs": prs}
    _atomic_write(path, json.dumps(payload, sort_keys=True).encode(), 0o600)


def _first_seen(entry: Any, head: str, now: float) -> float:
    """When (PR, head) started holding deploys; ``now`` unless the record proves earlier."""
    if not isinstance(entry, dict) or entry.get("head_sha") != head:
        return now
    seen = entry.get("first_seen_epoch")
    if isinstance(seen, bool) or not isinstance(seen, (int, float)):
        return now
    seen = float(seen)
    if not math.isfinite(seen) or seen > now or seen <= 0:
        return now
    return seen


def _mergeable_state(
    api_get: Callable[[str], Any], repo: str, number: int, head: str
) -> Optional[str]:
    """GitHub's ``mergeable_state`` of one PR at ``head``, or None when it cannot be read.

    Only ``dirty`` parks a PR; None (unreadable, still computing, or a detail
    response for a different head than the listed one) keeps it blocking.
    """
    try:
        pr = api_get(f"repos/{repo}/pulls/{int(number)}")
    except Exception:  # noqa: BLE001 - unknown mergeability keeps the PR blocking
        return None
    if not isinstance(pr, dict) or (pr.get("head") or {}).get("sha") != head:
        return None
    state = pr.get("mergeable_state")
    return state if isinstance(state, str) else None


def pin_bumps_in_flight(
    api_get: Callable[[str], Any],
    *,
    repo: str = REPOSITORY,
    now: Optional[float] = None,
    park_file: Optional[Path] = None,
    park_seconds: float = PIN_BUMP_PARK_SECONDS,
    record: bool = True,
) -> Dict[str, Any]:
    """Open pin-bump PRs; CLEAR, IN_FLIGHT or UNKNOWN (fail closed).

    A pin-bump PR that was created, last committed and last pushed more than
    ``PIN_BUMP_MAX_AGE_SECONDS`` ago is treated as abandoned and does not block, but it is never silent: it is
    listed in ``ignored_stale`` and as a ``STALE_PIN_PR_IGNORED #N`` warning.
    A draft pin-bump PR cannot merge, so it cannot race a deploy: it is listed in
    ``ignored_draft`` / ``DRAFT_PIN_PR_IGNORED #N`` instead of blocking.  The
    re-check right before the switch applies the same rule, so a draft marked
    ready mid-cycle blocks the switch.

    PARKED (#2309, see ``PIN_BUMP_PARK_SECONDS``): any other pin-bump PR whose
    ``mergeable_state`` is ``dirty``, or that has held deploys at the same head
    SHA for more than ``park_seconds`` (clock in ``park_file``), stops
    blocking: it is listed in ``ignored_parked`` (detail with head SHA,
    holding_since and reason in ``parked``) and warned as
    ``PARKED_PIN_PR_IGNORED #N (holding since <iso>)``.  Without ``park_file``
    no clock survives a call, so only ``dirty`` can park.  ``record=False``
    (dry run) reads the clock without writing it.
    """
    now = time.time() if now is None else now
    hits: List[int] = []
    stale: List[int] = []
    drafts: List[int] = []
    parked: List[Dict[str, Any]] = []
    previous = _load_pin_park(park_file)
    current: Dict[str, Any] = {}
    try:
        for pr in _paged(api_get, f"repos/{repo}/pulls?state=open"):
            label = f"{pr.get('title') or ''} {(pr.get('head') or {}).get('ref') or ''}"
            is_pin = bool(PIN_BUMP_PR.search(label)) or any(
                f.get("filename") in PIN_FILES
                for f in _paged(api_get, f"repos/{repo}/pulls/{pr['number']}/files")
            )
            if not is_pin:
                continue
            if pr.get("draft") is True:
                drafts.append(pr["number"])
                continue
            if _is_stale_pin_pr(api_get, repo, pr, now):
                stale.append(pr["number"])
                continue
            number = pr["number"]
            head = (pr.get("head") or {}).get("sha")
            if not isinstance(head, str) or not _SHA.match(head):
                hits.append(number)  # no head to track: it keeps blocking
                continue
            entry = previous.get(str(number))
            since = _first_seen(entry, head, now)
            kept: Dict[str, Any] = {"head_sha": head, "first_seen_epoch": since}
            if isinstance(entry, dict) and entry.get("head_sha") == head:
                if entry.get("commented_head") == head:
                    kept["commented_head"] = head
            current[str(number)] = kept
            reason: Optional[str] = None
            if _mergeable_state(api_get, repo, number, head) == "dirty":
                reason = PIN_PARK_REASON_DIRTY
            elif now - since > park_seconds:
                reason = PIN_PARK_REASON_HELD
            if reason is None:
                hits.append(number)
            else:
                parked.append({
                    "number": number,
                    "head_sha": head,
                    "holding_since": _iso(since),
                    "reason": reason,
                    "threshold_seconds": int(park_seconds),
                })
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "UNKNOWN", "error": f"{type(exc).__name__}:{exc}"[:300]}
    result: Dict[str, Any] = {
        "verdict": "IN_FLIGHT" if hits else "CLEAR",
        "pull_requests": sorted(hits),
        "ignored_stale": sorted(stale),
        "ignored_draft": sorted(drafts),
        "ignored_parked": sorted(p["number"] for p in parked),
        "parked": sorted(parked, key=lambda p: p["number"]),
        "warnings": [f"STALE_PIN_PR_IGNORED #{n}" for n in sorted(stale)]
        + [f"DRAFT_PIN_PR_IGNORED #{n}" for n in sorted(drafts)]
        + [
            f"PARKED_PIN_PR_IGNORED #{p['number']} (holding since {p['holding_since']})"
            for p in sorted(parked, key=lambda p: p["number"])
        ],
    }
    if park_file is not None and record and current != previous:
        try:
            _save_pin_park(park_file, current)
        except OSError as exc:
            # The clock is not advanced: parking is only delayed, never forced.
            result["warnings"].append(f"PIN_PARK_STATE_UNWRITABLE:{type(exc).__name__}")
    return result


def _pin_parked_comment(parked: Dict[str, Any]) -> str:
    head = parked["head_sha"]
    if parked["reason"] == PIN_PARK_REASON_DIRTY:
        why = f"at head `{head}` because it has a merge conflict (mergeable_state=dirty)"
    else:
        minutes = max(1, int(parked.get("threshold_seconds", PIN_BUMP_PARK_SECONDS)) // 60)
        why = f"after {minutes} min at head `{head}`"
    return (
        "<!-- NEXUS_GATEWAY_PIN_BUMP_PARKED -->\n"
        f"Gateway auto-deploy stopped waiting for this pin-bump PR {why}; deploys continue. "
        "Mark it draft while it is parked.\n\n"
        f"Holding since {parked['holding_since']} (#2309). A new head push makes it block "
        "deploys again until it merges or parks.\n"
    )


# ------------------------------------------------------------------------- probes


WORKER_ROUTE_PREFLIGHT_STATUSES = ("OK", "BLOCKED", "UNKNOWN")
_WORKER_ROUTE_KEYS = ("route", "adapter", "preflight", "reason")
_WORKER_ROUTE_MAX = 50


def worker_route_preflight_summary(health: Any) -> Dict[str, Any]:
    """Bounded copy of ``/health`` ``worker_route_preflight`` (#2345).

    Shape: ``{"status": "OK"|"BLOCKED"|"UNKNOWN", "routes": [{"route",
    "adapter", "preflight", "reason"}]}``.  An absent key is
    ``{"status": "UNAVAILABLE"}``; anything else unexpected is UNAVAILABLE with
    a reason.  Only those four route fields are kept, as short strings.
    """
    if not isinstance(health, dict) or "worker_route_preflight" not in health:
        return {"status": "UNAVAILABLE"}
    block = health["worker_route_preflight"]
    if not isinstance(block, dict) or block.get("status") not in WORKER_ROUTE_PREFLIGHT_STATUSES:
        return {"status": "UNAVAILABLE", "reason": "MALFORMED"}
    routes: List[Dict[str, Any]] = []
    raw = block.get("routes")
    for item in raw if isinstance(raw, list) else []:
        if len(routes) >= _WORKER_ROUTE_MAX:
            break
        if isinstance(item, dict):
            routes.append({
                k: (str(item[k])[:200] if item.get(k) is not None else None)
                for k in _WORKER_ROUTE_KEYS
            })
    return {"status": block["status"], "routes": routes}


def read_env_token(env_file: Path) -> str:
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, sep, value = line.partition("=")
        if sep and key.strip() == TOKEN_ENV:
            parts = shlex.split(value)
            if parts and parts[0]:
                return parts[0]
    raise DeployError("GATEWAY_TOKEN_UNAVAILABLE")


def health_core_provenance(health: Any, core: Any) -> Dict[str, Any]:
    """The running Gateway's own ``/health`` ``core_provenance`` (#2169, since #2201).

    Required: status ``CORE_REVISION_PINNED``, expected and observed revision
    both equal to the deployment's Core pin, ``fail_closed`` exactly False and,
    when the build computed a Core digest, ``identity_source`` ``source_digest``
    (#2246).
    A missing or malformed block fails.
    """
    if not isinstance(core, dict) or not _SHA.match(str(core.get("revision") or "")):
        return {"ok": False, "error": "CORE_PIN_UNKNOWN"}
    block = health.get("core_provenance") if isinstance(health, dict) else None
    if not isinstance(block, dict):
        return {"ok": False, "error": "HEALTH_CORE_PROVENANCE_MISSING"}
    ok = (
        block.get("status") == "CORE_REVISION_PINNED"
        and block.get("expected_revision") == core["revision"]
        and block.get("observed_commit") == core["revision"]
        and block.get("fail_closed") is False
        # #2246: a build with a Core digest is pinned by that digest, not by git.
        and (core.get("source_digest") is None or block.get("identity_source") == "source_digest")
    )
    keys = ("status", "expected_revision", "observed_commit", "fail_closed", "identity_source")
    return {"ok": ok, **{k: block.get(k) for k in keys if k in block}}


def core_env(core: Any) -> Dict[str, str]:
    """Environment that binds a process to the deployment's pinned Core.

    ``NEXUS_CORE_SOURCE_DIGEST`` (and the revision it was computed from) is set
    only when the build computed it; a Core pin that predates Core's
    ``core_identity()`` has none.
    """
    env = {"NEXUS_CORE_REPO_ROOT": str(core["root"])}
    digest = core.get("source_digest")
    if digest is not None:
        env["NEXUS_CORE_SOURCE_DIGEST"] = str(digest)
        env["NEXUS_CORE_SOURCE_DIGEST_REVISION"] = str(core["revision"])
    return env


def core_probe_env(core: Any, pycache_prefix: Path) -> Dict[str, Optional[str]]:
    """``core_env`` for a probe subprocess; ``None`` removes an inherited value.

    Without a build digest, a stale ``NEXUS_CORE_SOURCE_DIGEST*`` from the
    deployer's own environment must not reach the probed transport.
    ``pycache_prefix`` (outside the Core checkout) keeps Python from reading
    bytecode inside it, as the wrapper does.
    """
    env: Dict[str, Optional[str]] = {
        "NEXUS_CORE_SOURCE_DIGEST": None,
        "NEXUS_CORE_SOURCE_DIGEST_REVISION": None,
    }
    env.update(core_env(core))
    env["PYTHONPYCACHEPREFIX"] = str(pycache_prefix)
    return env


def core_digest_verified(observed: Dict[str, Any], core: Dict[str, Any]) -> bool:
    """The transport must have verified exactly this build's Core digest (#2246).

    When the build computed ``core["source_digest"]`` from the pinned commit,
    the candidate's transport must report a git-free ``source_digest`` identity
    whose observed and expected digests are both that value; any other
    identity source (git, build stamp, none) fails.  Only a Core pin that
    predates ``core_identity()`` has no digest; then the transport must not
    claim a git-free identity either, and the revision checks decide.
    """
    digest = core.get("source_digest")
    if digest is None:
        return observed.get("identity_source") is None and "observed_source_digest" not in observed
    return bool(
        _CORE_DIGEST.match(str(digest))
        and observed.get("identity_source") == "source_digest"
        and observed.get("observed_source_digest") == digest
        and observed.get("expected_source_digest") == digest
    )


class Prober:
    """Smoke probe of one Gateway instance.  Tests replace this class."""

    def __init__(self, host: Host) -> None:
        self.host = host

    def _http(self, url: str, *, body: Optional[dict] = None, token: str = "") -> Any:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, method="GET" if body is None else "POST")
        if body is not None:
            request.add_header("Content-Type", "application/json")
            request.add_header("Authorization", f"Bearer {token}")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=30) as response:
            return json.loads(response.read(8 * 1024 * 1024).decode("utf-8"))

    def live_health(self) -> Any:
        """The live Gateway's unauthenticated /health (#2230 F2); raises when unreachable."""
        return self._http(f"http://127.0.0.1:{LIVE_PORT}/health")

    def core_provenance(self, *, root: Path, python: Path, core: Any) -> Dict[str, Any]:
        """The candidate's transport must resolve Core as CORE_REVISION_PINNED at ``core``."""
        if not isinstance(core, dict) or not _SHA.match(str(core.get("revision") or "")):
            return {"ok": False, "error": "CORE_PIN_UNKNOWN"}
        with tempfile.TemporaryDirectory(prefix="nexus-core-probe-pycache-") as prefix:
            result = self.host.run(
                [str(python), "-c", CORE_PROVENANCE_PROBE_CODE, str(root)],
                cwd=root,
                env={"PYTHONDONTWRITEBYTECODE": "1", **core_probe_env(core, Path(prefix))},
                timeout=120,
            )
        lines = (result.stdout or "").strip().splitlines()
        try:
            observed = json.loads(lines[-1]) if lines else None
        except ValueError:
            observed = None
        if result.returncode != 0 or not isinstance(observed, dict):
            detail = (result.stderr or result.stdout or "").strip()[-500:]
            return {"ok": False, "error": f"CORE_PROVENANCE_UNREADABLE:{detail}"}
        try:
            same_root = (
                Path(str(observed.get("source_root"))).resolve()
                == Path(str(core["root"])).resolve()
            )
        except (OSError, RuntimeError):
            same_root = False
        ok = (
            observed.get("status") == "CORE_REVISION_PINNED"
            and observed.get("observed_commit") == core["revision"]
            and observed.get("expected_revision") == core["revision"]
            and same_root
            and core_digest_verified(observed, core)
        )
        keys = (
            "status",
            "reason",
            "expected_revision",
            "observed_commit",
            "source_root",
            "identity_source",
            "observed_source_digest",
        )
        return {"ok": ok, **{k: observed.get(k) for k in keys if k in observed}}

    def probe(
        self,
        *,
        port: int,
        token: str,
        commit: str,
        root: Path,
        python: Path,
        timeout: float,
        core: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Smoke-probe one Gateway; ``core`` (candidate probes) also requires the pinned Core."""
        base = f"http://127.0.0.1:{port}"
        checks: Dict[str, Any] = {}
        deadline = self.host.now() + timeout
        observed: Any = None
        while True:
            try:
                observed = self._http(f"{base}/health")
                if isinstance(observed, dict) and observed.get("git_head") == commit:
                    break
            except Exception as exc:  # noqa: BLE001 - not up yet
                observed = f"{type(exc).__name__}"
            if self.host.now() >= deadline:
                checks["health"] = {"ok": False, "observed": observed}
                return {"ok": False, "checks": checks}
            self.host.sleep(2)
        checks["health"] = {"ok": observed.get("status") == "ok", "status": observed.get("status")}
        gb077 = self.host.run(
            [
                str(python),
                "-c",
                GB077_PROBE_CODE,
                str(root),
                f"{base}/health",
                commit,
                str(GB077_TIMEOUT_SECONDS),
                str(GB077_ATTEMPTS),
            ],
            env={"PYTHONDONTWRITEBYTECODE": "1"},
            timeout=GB077_ATTEMPTS * (GB077_TIMEOUT_SECONDS + 2) + 30,
        )
        checks["gb077"] = {"ok": gb077.returncode == 0, "detail": gb077.stdout.strip()[-2000:]}
        try:
            tools = self._http(
                f"{base}/mcp", body={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, token=token
            )
            count = len(tools["result"]["tools"])
            checks["tools_list"] = {"ok": count > 0, "tool_count": count}
        except Exception as exc:  # noqa: BLE001
            checks["tools_list"] = {"ok": False, "error": f"{type(exc).__name__}:{exc}"[:300]}
        try:
            call = {"name": "nexus_gateway_status", "arguments": {}}
            status = self._http(
                f"{base}/mcp",
                body={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": call},
                token=token,
            )
            checks["gateway_status"] = {"ok": status.get("result", {}).get("isError") is False}
        except Exception as exc:  # noqa: BLE001
            checks["gateway_status"] = {"ok": False, "error": f"{type(exc).__name__}:{exc}"[:300]}
        if core is not None:
            # Both: the fresh subprocess proves the on-disk resolution, the
            # /health block proves what the running process actually loaded.
            checks["core_provenance"] = self.core_provenance(root=root, python=python, core=core)
            checks["health_core_provenance"] = health_core_provenance(observed, core)
        return {"ok": all(c["ok"] for c in checks.values()), "checks": checks}


# --------------------------------------------------------------------- deployment


# The Gateway's ``nexus_worker_candidate`` default route is Agy, whose worker
# preflight requires this flag in the process environment.  Owner approved
# exporting only this narrow flag (#2318); the broad
# NEXUS_EXTERNAL_RUNTIME_AUTHORIZED is deliberately not exported.
AGY_RUNTIME_AUTHORIZATION_EXPORT = "export NEXUS_AGY_RUNTIME_AUTHORIZED=1 ; "


def wrapper_command(
    cfg: Config,
    root: Path,
    python: Path,
    port: Optional[int] = None,
    state_dir: Optional[Path] = None,
    core_root: Optional[Path] = None,
    controller_root: Optional[Path] = None,
    core_digest: Optional[Tuple[str, str]] = None,
    rie: Optional[Tuple[Path, Path]] = None,
) -> str:
    """The same fixed zsh wrapper as the #526 deployments, with a per-deployment venv.

    ``controller_root`` (#1939) is the separate Controller worktree exported as
    ``NEXUS_CANONICAL_SOURCE_ROOT``; the process still runs the deployment.

    ``port``/``state_dir`` are only used for the spare-port probe, which must never
    see the live self-hosted state.  ``core_root`` (exported after the env file, so
    the env file cannot override it) is the deployment's pinned Core checkout.
    ``core_digest`` is ``(revision, source_digest)`` of that checkout, exported as
    ``NEXUS_CORE_SOURCE_DIGEST_REVISION`` / ``NEXUS_CORE_SOURCE_DIGEST`` (#2246).
    With a Core root, ``PYTHONPYCACHEPREFIX`` points at the deployment's own
    ``pycache/<deployment>`` dir: the source digest excludes bytecode, so an
    in-tree ``__pycache__`` must never be read (#2246).

    The wrapper always exports ``NEXUS_AGY_RUNTIME_AUTHORIZED=1`` after the env
    file (Owner approval in #2318), so ``nexus_worker_candidate`` can dispatch
    its default Agy route.  It never exports the broader
    ``NEXUS_EXTERNAL_RUNTIME_AUTHORIZED``.

    ``rie`` is ``(engine_root, python)`` of a verified RIE checkout (#1579),
    exported after the env file; without one both variables are unset, so a
    stale env-file value can never point the Gateway at another engine.
    """
    state = cfg.canonical_state_dir if state_dir is None else state_dir
    controller = root if controller_root is None else controller_root
    values = [str(root), str(python), str(cfg.env_file), str(state), str(controller)]
    if core_root is not None:
        values.append(str(core_root))
    if rie is not None:
        values.extend([str(rie[0]), str(rie[1])])
    for value in values:
        if any(token in value for token in _SHELL_UNSAFE):
            raise DeployError("WRAPPER_PATH_UNSAFE")
    port_export = "" if port is None else f"export NEXUS_MCP_GATEWAY_PORT={int(port)} ; "
    core_export = "" if core_root is None else f'export NEXUS_CORE_REPO_ROOT="{core_root}" ; '
    if core_root is not None:
        # Bytecode is never read from (or written into) the Core checkout.
        prefix = cfg.pycache_prefixes / root.name
        if any(token in str(prefix) for token in _SHELL_UNSAFE):
            raise DeployError("WRAPPER_PATH_UNSAFE")
        core_export += f'export PYTHONPYCACHEPREFIX="{prefix}" ; '
    if core_digest is not None:
        revision, digest = core_digest
        if (
            core_root is None
            or not _SHA.match(str(revision))
            or not _CORE_DIGEST.match(str(digest))
        ):
            raise DeployError("WRAPPER_CORE_DIGEST_INVALID")
        core_export += (
            f'export NEXUS_CORE_SOURCE_DIGEST_REVISION="{revision}" ; '
            f'export NEXUS_CORE_SOURCE_DIGEST="{digest}" ; '
        )
    else:
        # No build digest: never let a stale value from the env file through.
        core_export += "unset NEXUS_CORE_SOURCE_DIGEST NEXUS_CORE_SOURCE_DIGEST_REVISION ; "
    if rie is None:
        rie_export = f"unset {RIE_ENV_ENGINE_ROOT} {RIE_ENV_PYTHON_BIN} ; "
    else:
        rie_export = (
            f'export {RIE_ENV_ENGINE_ROOT}="{rie[0]}" ; export {RIE_ENV_PYTHON_BIN}="{rie[1]}" ; '
        )
    return (
        f'cd "{controller}" ; source "{cfg.env_file}" ; export PYTHONDONTWRITEBYTECODE=1 ; '
        f"{AGY_RUNTIME_AUTHORIZATION_EXPORT}"
        f'export NEXUS_CANONICAL_SOURCE_ROOT="{controller}" ; '
        f'export NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR="{state}" ; '
        f'{rie_export}{core_export}{port_export}exec "{python}" "{root / ENTRYPOINT}"'
    )


def _load_gateway_plist(plist_bytes: bytes) -> Dict[str, Any]:
    """Parse plist bytes and require the Gateway LaunchAgent shape."""
    try:
        data = plistlib.loads(plist_bytes)
    except Exception as exc:  # noqa: BLE001 - any decode error is a bad plist
        raise DeployError(f"GATEWAY_PLIST_UNREADABLE:{type(exc).__name__}") from exc
    if not isinstance(data, dict):
        raise DeployError("GATEWAY_PLIST_NOT_A_DICT")
    if data.get("Label") != GATEWAY_LABEL:
        raise DeployError("GATEWAY_PLIST_LABEL_MISMATCH")
    args = data.get("ProgramArguments")
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise DeployError("GATEWAY_PLIST_PROGRAM_ARGUMENTS_INVALID")
    return data


def _wrapper_tokens(plist_bytes: bytes) -> List[str]:
    data = _load_gateway_plist(plist_bytes)
    if data.get("Label") != GATEWAY_LABEL:
        raise DeployError("GATEWAY_PLIST_LABEL_MISMATCH")
    args = data.get("ProgramArguments") or []
    if len(args) >= 3 and args[1] == "-c":
        return shlex.split(args[2])
    return list(args)


def live_root(plist_bytes: bytes) -> Optional[Path]:
    data = _load_gateway_plist(plist_bytes)
    if data.get("Label") != GATEWAY_LABEL:
        raise DeployError("GATEWAY_PLIST_LABEL_MISMATCH")
    root = data.get("WorkingDirectory")
    if isinstance(root, str) and root:
        return Path(root)
    for token in _wrapper_tokens(plist_bytes):
        if token.startswith("NEXUS_CANONICAL_SOURCE_ROOT="):
            return Path(token.split("=", 1)[1])
    return None


def live_controller(plist_bytes: bytes) -> Optional[Path]:
    """The exported Controller root when it is not the deployment itself (#1939)."""
    root = live_root(plist_bytes)
    for token in _wrapper_tokens(plist_bytes):
        if token.startswith("NEXUS_CANONICAL_SOURCE_ROOT="):
            path = Path(token.split("=", 1)[1])
            return None if root is not None and path == root else path
    return None


def live_python(plist_bytes: bytes) -> Optional[Path]:
    """Interpreter after ``exec`` in the wrapper, parsed with shell quoting rules."""
    tokens = _wrapper_tokens(plist_bytes)
    for index, token in enumerate(tokens[:-1]):
        if token == "exec":
            return Path(tokens[index + 1])
    return None


def commit_of(root: Optional[Path]) -> Optional[str]:
    match = _DEPLOYMENT_NAME.search(str(root)) if root else None
    return match.group(1) if match else None


def render_plist(previous: bytes, command: str, root: Path) -> bytes:
    data = _load_gateway_plist(previous)
    data["ProgramArguments"] = ["/bin/zsh", "-c", command]
    data["WorkingDirectory"] = str(root)
    return plistlib.dumps(data, sort_keys=True)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes, mode: int = 0o644) -> None:
    # Unique per write and created exclusively (O_EXCL, so never through an
    # existing file or symlink).  Cleanup runs only once this write has created
    # its own temp file, so it never removes anything it does not own (#2169 review).
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}.{os.urandom(6).hex()}")
    handle = open(tmp, "xb")
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        # Never leave a half-written temp file behind (#2169 review).
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def _atomic_symlink(target: Path, link: Path) -> None:
    tmp = link.with_name(f".{link.name}.tmp.{os.getpid()}")
    with contextlib.suppress(FileNotFoundError):
        tmp.unlink()
    os.symlink(str(target), str(tmp))
    os.replace(tmp, link)


def is_irrelevant(path: str) -> bool:
    return path.startswith(IRRELEVANT_PREFIXES) or (
        "/" not in path and path.endswith(IRRELEVANT_SUFFIXES)
    )


def _uv_extra_args(extras: str) -> List[str]:
    if extras == "all":
        return ["--all-extras"]
    args: List[str] = []
    for extra in filter(None, (e.strip() for e in extras.split(","))):
        args += ["--extra", extra]
    return args


def read_core_pin(root: Path) -> str:
    """``CANONICAL_CORE_REVISION`` of a deployment tree, by text parse (never imported)."""
    try:
        text = (root / CORE_PIN_FILE).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DeployError(f"CORE_PIN_INVALID:unreadable:{type(exc).__name__}") from exc
    found = _CORE_PIN_LINE.findall(text)
    if len(found) != 1 or not _SHA.match(found[0]):
        raise DeployError(f"CORE_PIN_INVALID:{found[:2]!r}"[:300])
    return found[0]


def _core_git(cfg: Config, *args: str) -> List[str]:
    return ["git", "--git-dir", str(cfg.core_bare_repo), *args]


def materialize_core(cfg: Config, host: Host, revision: str) -> Dict[str, Any]:
    """A clean detached nexus-core checkout ``core/<revision>``; any doubt raises.

    The bare ``core.git`` is created on first use with the James3014/nexus-core
    origin and fetched with the same ambient git credentials as the Gateway
    repository.  A commit already present is not fetched again; the checkout's
    own HEAD keeps it reachable.  There is no fallback: without a verified
    checkout the candidate is not deployed.
    """
    if not _SHA.match(revision):
        raise DeployError(f"CORE_PIN_INVALID:{revision!r}"[:300])
    if cfg.core_checkouts.is_symlink() or cfg.core_bare_repo.is_symlink():
        raise DeployError("CORE_PATH_SYMLINKED")
    if not cfg.core_bare_repo.exists():
        _must(
            host, ["git", "init", "--bare", "--quiet", str(cfg.core_bare_repo)], "CORE_INIT_FAILED"
        )
        _must(
            host, _core_git(cfg, "remote", "add", "origin", CORE_REPOSITORY_URL), "CORE_INIT_FAILED"
        )
    origin = _must(
        host, _core_git(cfg, "config", "--get", "remote.origin.url"), "CORE_ORIGIN_FAILED"
    ).strip()
    if origin not in CORE_ORIGIN_URLS:
        raise DeployError(f"CORE_ORIGIN_MISMATCH:{origin}"[:300])
    present = _core_git(cfg, "cat-file", "-e", f"{revision}^{{commit}}")
    if host.run(present, timeout=60).returncode != 0:
        refspec = "+refs/heads/*:refs/nexus-core/heads/*"
        fetch = _core_git(cfg, "fetch", "--quiet", "--no-tags", "origin", refspec)
        _must(host, fetch, "CORE_FETCH_FAILED", timeout=300)
        _must(host, present, "CORE_COMMIT_NOT_FOUND", timeout=60)
    checkout = cfg.core_checkouts / revision
    if checkout.is_symlink():
        raise DeployError("CORE_PATH_SYMLINKED")
    if not checkout.exists():
        _add_core_checkout(cfg, host, checkout, revision)
    problem = core_checkout_problem(host, checkout, revision)
    result = {"revision": revision, "root": str(checkout), "repository": CORE_REPOSITORY_URL}
    if problem is None:
        return result
    # A dirty or half-created checkout must not block every later candidate with
    # this pin.  Rebuild it once, but only if no running deployment uses it.
    if revision in core_pins_in_use(cfg):
        raise DeployError(f"CORE_IN_USE_UNHEALTHY:{problem}"[:300])
    _remove_core_checkout(cfg, host, checkout)
    _must(host, _core_git(cfg, "worktree", "prune"), "CORE_WORKTREE_PRUNE_FAILED")
    _add_core_checkout(cfg, host, checkout, revision)
    again = core_checkout_problem(host, checkout, revision)
    if again is not None:
        raise DeployError(again[:300])
    return {**result, "rebuilt": problem[:300]}


def _add_core_checkout(cfg: Config, host: Host, checkout: Path, revision: str) -> None:
    cfg.core_checkouts.mkdir(parents=True, exist_ok=True)
    _must(
        host,
        _core_git(cfg, "worktree", "add", "--detach", str(checkout), revision),
        "CORE_WORKTREE_ADD_FAILED",
    )


def _remove_core_checkout(cfg: Config, host: Host, checkout: Path) -> None:
    """Remove a checkout strictly inside a real ``core/`` (never through a symlink)."""
    parent = cfg.core_checkouts
    if (
        parent.is_symlink()
        or checkout.is_symlink()
        or checkout.resolve().parent != parent.resolve()
    ):
        raise DeployError("CORE_PATH_SYMLINKED")
    host.run(_core_git(cfg, "worktree", "remove", "--force", str(checkout)), timeout=300)
    if checkout.exists() and not checkout.is_symlink():
        shutil.rmtree(checkout, ignore_errors=True)


def core_checkout_problem(host: Host, checkout: Path, revision: str) -> Optional[str]:
    """None when ``checkout`` is a clean worktree at exactly ``revision``."""
    if not (checkout / ".git").is_file():
        # Half-created (e.g. a killed `worktree add`); never let git walk upwards.
        return "CORE_CHECKOUT_INCOMPLETE"
    head = host.run(["git", "-C", str(checkout), "rev-parse", "HEAD"])
    if head.returncode != 0:
        return f"CORE_HEAD_FAILED:{(head.stderr or '').strip()[:200]}"
    if head.stdout.strip() != revision:
        return f"CORE_HEAD_MISMATCH:{head.stdout.strip()}"
    # --ignored: an ignored file (say a stray module) can still be imported.
    status = host.run([
        "git",
        "-C",
        str(checkout),
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignored",
    ])
    if status.returncode != 0:
        return "CORE_STATUS_FAILED"
    for entry in (status.stdout or "").split("\0"):
        if not entry:
            continue
        code, rel = entry[:3], entry[3:]
        # Bytecode caches are not source: the host's Core identity ignores them
        # (#2246), so the in-use check must too.  Anything else is dirty.
        if code in ("!! ", "?? ") and _is_bytecode_cache(checkout, rel):
            continue
        return "CORE_TREE_DIRTY"
    return None


def _is_bytecode_cache(checkout: Path, rel: str) -> bool:
    """``rel`` is a ``__pycache__`` directory of only ``*.pyc`` files, or one such file.

    A ``.pyc`` outside ``__pycache__`` is not accepted: Python imports it as a
    sourceless module.  Symlinks and nested directories are never accepted.
    """
    path = checkout / rel.rstrip("/")
    parts = Path(rel.rstrip("/")).parts
    if not parts or ".." in parts or path.is_symlink():
        return False
    if rel.endswith("/"):
        if parts[-1] != "__pycache__" or not path.is_dir():
            return False
        children = list(path.iterdir())
        return all(
            not child.is_symlink() and child.is_file() and child.name.endswith(".pyc")
            for child in children
        )
    return (
        len(parts) >= 2
        and parts[-2] == "__pycache__"
        and parts[-1].endswith(".pyc")
        and path.is_file()
        and not path.parent.is_symlink()
    )


def core_source_digest(host: Host, checkout: Path, revision: str) -> Dict[str, Any]:
    """Expected Core ``source_digest`` of the clean pinned checkout (#2246).

    Computed by Core's own ``build_identity`` module from the checkout, over the
    commit's git objects and over the files on disk; both must agree or the
    candidate is rejected.  A Core pin without ``build_identity`` (before
    nexus-core #270) has no digest: ``source_digest`` is None and nothing is
    exported.  Only a tree whose host predates #2246 can pin such a Core; it
    keeps its git-based provenance (a #2246 host pins Core >= #270 itself).
    """
    if not (checkout / CORE_BUILD_IDENTITY_FILE).is_file():
        return {"source_digest": None, "source_digest_status": "UNSUPPORTED_CORE"}
    result = host.run(
        [sys.executable, "-B", "-I", "-c", CORE_SOURCE_DIGEST_CODE, str(checkout), revision],
        cwd=checkout,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        timeout=300,
    )
    lines = (result.stdout or "").strip().splitlines()
    try:
        report = json.loads(lines[-1]) if result.returncode == 0 and lines else None
    except ValueError:
        report = None
    if not isinstance(report, dict):
        detail = (result.stderr or result.stdout or "").strip()[-200:]
        raise DeployError(f"CORE_SOURCE_DIGEST_FAILED:{detail}"[:300])
    committed, on_disk = report.get("committed"), report.get("on_disk")
    if not _CORE_DIGEST.match(str(committed)) or not _CORE_DIGEST.match(str(on_disk)):
        raise DeployError("CORE_SOURCE_DIGEST_MALFORMED")
    if committed != on_disk:
        raise DeployError(f"CORE_SOURCE_DIGEST_MISMATCH:{committed}!={on_disk}"[:300])
    return {"source_digest": committed, "source_digest_status": "COMPUTED"}


def _core_digest_arg(core: Any) -> Optional[Tuple[str, str]]:
    """``wrapper_command(core_digest=...)`` for a receipt's ``core`` block."""
    if isinstance(core, dict) and core.get("source_digest") is not None:
        return (str(core.get("revision")), str(core["source_digest"]))
    return None


def core_pins_in_use(cfg: Config) -> set:
    """Core revisions the live Gateway or the deployer tree may be running.

    Same protected set as retention: the live (and, before a switch, previous)
    plist root and ``auto-deploy-current``, plus the NEXUS_CORE_REPO_ROOT the
    live wrapper exports.  Anything unreadable raises (treated as in use).
    """
    try:
        plist = cfg.plist.read_bytes()
        roots = [live_root(plist)]
        tokens = _wrapper_tokens(plist)
    except (OSError, DeployError) as exc:
        raise DeployError(f"CORE_IN_USE_UNKNOWN:{exc}"[:300]) from exc
    pins = set()
    for token in tokens:
        if token.startswith("NEXUS_CORE_REPO_ROOT="):
            pins.add(Path(token.split("=", 1)[1]).name)
    if cfg.tool_link.is_symlink():
        roots.append(Path(os.path.realpath(cfg.tool_link)))
    for root in roots:
        if root is None or not (root / CORE_PIN_FILE).exists():
            continue
        try:
            pins.add(read_core_pin(root))
        except DeployError as exc:
            raise DeployError(f"CORE_IN_USE_UNKNOWN:{exc}"[:300]) from exc
    return pins


def read_rie_pin(root: Path) -> str:
    """``PINNED_RIE_ENGINE_REVISION`` of a deployment tree, by text parse (never imported).

    Exactly one 40-hex constant, or ``RIE_PIN_UNREADABLE`` (#1579).
    """
    try:
        text = (root / RIE_PIN_FILE).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DeployError(f"RIE_PIN_UNREADABLE:unreadable:{type(exc).__name__}") from exc
    found = _RIE_PIN_LINE.findall(text)
    if len(found) != 1 or not _SHA.match(found[0]):
        raise DeployError(f"RIE_PIN_UNREADABLE:{found[:2]!r}"[:300])
    return found[0]


def _rie_git(cfg: Config, *args: str) -> List[str]:
    return ["git", "--git-dir", str(cfg.rie_bare_repo), *args]


def rie_checkout_problem(host: Host, checkout: Path, revision: str) -> Optional[str]:
    """None when ``checkout`` is a clean worktree at exactly ``revision``.

    Stricter than Core: nothing untracked or ignored at all, bytecode included,
    since the engine always runs with bytecode writing disabled.
    """
    if not (checkout / ".git").is_file():
        return "RIE_CHECKOUT_INCOMPLETE"
    head = host.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], timeout=60)
    if head.returncode != 0:
        return f"RIE_HEAD_FAILED:{(head.stderr or '').strip()[:200]}"
    if head.stdout.strip() != revision:
        return f"RIE_HEAD_MISMATCH:{head.stdout.strip()}"
    status = host.run(
        [
            "git",
            "-C",
            str(checkout),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignored",
        ],
        timeout=60,
    )
    if status.returncode != 0:
        return "RIE_STATUS_FAILED"
    if (status.stdout or "").strip():
        return f"RIE_TREE_DIRTY:{status.stdout.strip()[:200]}"
    return None


def rie_roots_in_use(cfg: Config) -> set:
    """RIE checkout names the live wrapper exports; unreadable raises (in use)."""
    try:
        tokens = _wrapper_tokens(cfg.plist.read_bytes())
    except (OSError, DeployError) as exc:
        raise DeployError(f"RIE_IN_USE_UNKNOWN:{exc}"[:300]) from exc
    prefix = f"{RIE_ENV_ENGINE_ROOT}="
    return {Path(t.split("=", 1)[1]).name for t in tokens if t.startswith(prefix)}


def _add_rie_checkout(cfg: Config, host: Host, checkout: Path, revision: str) -> None:
    cfg.rie_checkouts.mkdir(parents=True, exist_ok=True)
    _must(
        host,
        _rie_git(cfg, "worktree", "add", "--detach", str(checkout), revision),
        "RIE_WORKTREE_ADD_FAILED",
        timeout=300,
    )


def _remove_rie_checkout(cfg: Config, host: Host, checkout: Path) -> None:
    parent = cfg.rie_checkouts
    if (
        parent.is_symlink()
        or checkout.is_symlink()
        or checkout.resolve().parent != parent.resolve()
    ):
        raise DeployError("RIE_PATH_SYMLINKED")
    host.run(_rie_git(cfg, "worktree", "remove", "--force", str(checkout)), timeout=300)
    if checkout.exists() and not checkout.is_symlink():
        shutil.rmtree(checkout, ignore_errors=True)


def materialize_rie(cfg: Config, host: Host, revision: str) -> Dict[str, Any]:
    """A clean detached RIE checkout ``rie/<revision>``; any doubt raises.

    A commit already present (a previous verified deploy with the same pin) is
    never fetched again, so a later GitHub outage does not lose the engine.
    """
    if not _SHA.match(revision):
        raise DeployError(f"RIE_PIN_UNREADABLE:{revision!r}"[:300])
    if cfg.rie_checkouts.is_symlink() or cfg.rie_bare_repo.is_symlink():
        raise DeployError("RIE_PATH_SYMLINKED")
    if not cfg.rie_bare_repo.exists():
        _must(host, ["git", "init", "--bare", "--quiet", str(cfg.rie_bare_repo)], "RIE_INIT_FAILED")
        _must(host, _rie_git(cfg, "remote", "add", "origin", RIE_REPOSITORY_URL), "RIE_INIT_FAILED")
    origin = _must(
        host, _rie_git(cfg, "config", "--get", "remote.origin.url"), "RIE_ORIGIN_FAILED"
    ).strip()
    if origin not in RIE_ORIGIN_URLS:
        raise DeployError(f"RIE_ORIGIN_MISMATCH:{origin}"[:300])
    present = _rie_git(cfg, "cat-file", "-e", f"{revision}^{{commit}}")
    if host.run(present, timeout=60).returncode != 0:
        refspec = "+refs/heads/*:refs/rie/heads/*"
        fetch = _rie_git(cfg, "fetch", "--quiet", "--no-tags", "origin", refspec)
        _must(host, fetch, "RIE_FETCH_FAILED", timeout=RIE_FETCH_TIMEOUT_SECONDS)
        _must(host, present, "RIE_COMMIT_NOT_FOUND", timeout=60)
    checkout = cfg.rie_checkouts / revision
    if checkout.is_symlink():
        raise DeployError("RIE_PATH_SYMLINKED")
    if not checkout.exists():
        _add_rie_checkout(cfg, host, checkout, revision)
    tree = _must(
        host, _rie_git(cfg, "rev-parse", f"{revision}^{{tree}}"), "RIE_TREE_FAILED", timeout=60
    ).strip()
    result = {
        "revision": revision,
        "root": str(checkout),
        "repository": RIE_REPOSITORY_URL,
        "tree": tree,
    }
    problem = rie_checkout_problem(host, checkout, revision)
    if problem is None:
        return result
    if revision in rie_roots_in_use(cfg):
        raise DeployError(f"RIE_IN_USE_UNHEALTHY:{problem}"[:300])
    _remove_rie_checkout(cfg, host, checkout)
    _must(host, _rie_git(cfg, "worktree", "prune"), "RIE_WORKTREE_PRUNE_FAILED")
    _add_rie_checkout(cfg, host, checkout, revision)
    again = rie_checkout_problem(host, checkout, revision)
    if again is not None:
        raise DeployError(again[:300])
    return {**result, "rebuilt": problem[:300]}


def rie_engine(cfg: Config, host: Host, root: Path, python: Path) -> Dict[str, Any]:
    """The candidate's pinned RIE engine for the wrapper, or why there is none.

    Never raises: status ``VERIFIED`` (checkout clean at the pin and the engine
    CLI imports from it with the candidate's interpreter, bytecode off, then the
    checkout is still clean) or ``UNAVAILABLE`` with an error code.
    """
    try:
        revision = read_rie_pin(root)
        engine = materialize_rie(cfg, host, revision)
        check = host.run(
            [str(python), "-B", "-I", "-c", RIE_ENGINE_CHECK_CODE, engine["root"]],
            cwd=Path(engine["root"]),
            env={"PYTHONDONTWRITEBYTECODE": "1"},
            timeout=RIE_ENGINE_CHECK_TIMEOUT_SECONDS,
        )
        if check.returncode != 0 or (check.stdout or "").strip() != "OK":
            detail = (check.stderr or check.stdout or "").strip()[-200:]
            raise DeployError(f"RIE_ENGINE_CHECK_FAILED:{detail}")
        after = rie_checkout_problem(host, Path(engine["root"]), revision)
        if after is not None:
            raise DeployError(f"RIE_ENGINE_CHECK_WROTE:{after}"[:300])
        return {"status": "VERIFIED", **engine, "python": str(python)}
    except Exception as exc:  # noqa: BLE001 - advisory: never blocks the deploy
        return {"status": "UNAVAILABLE", "error": f"{exc}"[:300] or type(exc).__name__}


def _rie_arg(receipt: Any) -> Optional[Tuple[Path, Path]]:
    """``wrapper_command(rie=...)`` for a receipt's ``rie`` block (VERIFIED only)."""
    rie = receipt.get("rie") if isinstance(receipt, dict) else None
    if isinstance(rie, dict) and rie.get("status") == "VERIFIED":
        return (Path(str(rie["root"])), Path(str(rie["python"])))
    return None


def materialize_tree(cfg: Config, host: Host, commit: str) -> Path:
    """The detached ``deployments/a1-<commit>`` worktree, at exactly ``commit``."""
    root = cfg.deployments / f"{DEPLOYMENT_PREFIX}{commit}"
    if not root.exists():
        _must(
            host, _git(cfg, "worktree", "add", "--detach", str(root), commit), "WORKTREE_ADD_FAILED"
        )
    head = _must(
        host, ["git", "-C", str(root), "rev-parse", "HEAD"], "WORKTREE_HEAD_FAILED"
    ).strip()
    if head != commit:
        raise DeployError(f"WORKTREE_HEAD_MISMATCH:{head}")
    return root


def build(cfg: Config, host: Host, commit: str) -> Dict[str, Any]:
    """Materialize the immutable deployment and its dedicated venv."""
    root = materialize_tree(cfg, host, commit)
    venv = cfg.venvs / f"{DEPLOYMENT_PREFIX}{commit}"
    core = materialize_core(cfg, host, read_core_pin(root))
    core = {**core, **core_source_digest(host, Path(core["root"]), core["revision"])}
    cfg.venvs.mkdir(parents=True, exist_ok=True)
    _must(
        host,
        [
            "uv",
            "sync",
            "--frozen",
            *_uv_extra_args(cfg.uv_extras),
            "--no-install-project",
            "--python",
            cfg.python_version,
            "--project",
            str(root),
        ],
        "VENV_SYNC_FAILED",
        cwd=root,
        env={"UV_PROJECT_ENVIRONMENT": str(venv)},
    )
    python = venv / "bin" / "python"
    if not python.exists():
        raise DeployError("VENV_PYTHON_MISSING")
    dirty = _must(host, ["git", "-C", str(root), "status", "--porcelain"], "WORKTREE_STATUS_FAILED")
    if dirty.strip():
        raise DeployError("SOURCE_TREE_WRITTEN_BY_BUILD")
    rie = rie_engine(cfg, host, root, python)
    lock = root / "uv.lock"
    return {
        "deployment_root": str(root),
        "venv": str(venv),
        "venv_python": str(python),
        "uv_lock_sha256": _sha256(lock.read_bytes()) if lock.exists() else None,
        "core": core,
        "rie": rie,
    }


# Runs with the CANDIDATE's interpreter and tree: the exact rules the Gateway
# will apply at startup (#1939).  Prints OK or the refusal reason.
CONTROLLER_CHECK_CODE = """
import sys
import tempfile
from pathlib import Path
code_root, root, controller = sys.argv[1:4]
sys.path.insert(0, code_root)
from nexus.orchestrator.canonical_source_root import bound_controller_problem
print(bound_controller_problem(Path(controller), Path(root)) or "OK")
"""
CARRY_AUTHOR = (
    "-c",
    "user.name=Nexus Gateway auto-deploy",
    "-c",
    "user.email=nexus-auto-deploy@localhost",
)
CARRY_MAX_PATHS = 500


def _ctl(controller: Path, *args: str) -> List[str]:
    return ["git", "-C", str(controller), *args]


def materialize_controller(cfg: Config, host: Host, commit: str) -> Path:
    """A fresh, clean Controller worktree at ``commit`` (absolute paths, #1939)."""
    controller = cfg.controllers / f"{DEPLOYMENT_PREFIX}{commit}"
    refusal = prune_refusal(cfg)
    if refusal is not None:
        raise DeployError(f"CONTROLLER_ROOT_UNSAFE:{refusal}")
    if controller.is_symlink():
        raise DeployError("CONTROLLER_SYMLINKED")
    try:
        live = live_controller(cfg.plist.read_bytes())
    except (OSError, DeployError):
        live = None
    if live is not None and controller.exists() and os.path.samefile(live, controller):
        raise DeployError("CONTROLLER_IS_LIVE")
    if controller.exists():
        host.run(_git(cfg, "worktree", "remove", "--force", str(controller)), timeout=300)
        if controller.exists():
            shutil.rmtree(controller, ignore_errors=True)
    cfg.controllers.mkdir(parents=True, exist_ok=True)
    _must(
        host,
        _git(
            cfg,
            "-c",
            "worktree.useRelativePaths=false",
            "worktree",
            "add",
            "--detach",
            str(controller),
            commit,
        ),
        "CONTROLLER_ADD_FAILED",
    )
    head = _must(host, _ctl(controller, "rev-parse", "HEAD"), "CONTROLLER_HEAD_FAILED").strip()
    if head != commit:
        raise DeployError(f"CONTROLLER_HEAD_MISMATCH:{head}")
    if _must(host, _ctl(controller, "status", "--porcelain"), "CONTROLLER_STATUS_FAILED").strip():
        raise DeployError("CONTROLLER_NOT_CLEAN")
    return controller


def carry_bound_cards(
    host: Host, previous_plist: bytes, controller: Path, commit: str
) -> Dict[str, Any]:
    """Replay the live Controller's Task Card bind commits onto the new Controller.

    The source is the live Controller, or (first run after this change, when
    the live Gateway still binds into its deployment) the live deployment.
    Only regular files under ``tasks/`` that main did not touch since the live
    commit are carried, byte for byte (the card SHA-256 a bind recorded stays
    valid).  Anything unusual is skipped and reported in ``lost``; this never
    raises and never carries anything outside ``tasks/``.
    """
    try:
        return _carry_bound_cards(host, previous_plist, controller, commit)
    except Exception as exc:  # noqa: BLE001 - a carry problem must never block a deploy
        try:
            return _reset_carry(host, controller, commit, None, f"CARRY_ERROR:{type(exc).__name__}")
        except Exception:  # noqa: BLE001 - prepare_controller re-checks the Controller
            return {
                "status": "SKIPPED",
                "reason": f"CARRY_ERROR:{type(exc).__name__}",
                "lost": True,
            }


def _carry_bound_cards(
    host: Host, previous_plist: bytes, controller: Path, commit: str
) -> Dict[str, Any]:
    try:
        previous = live_controller(previous_plist) or live_root(previous_plist)
        previous_commit = commit_of(live_root(previous_plist))
    except DeployError as exc:
        return {"status": "SKIPPED", "reason": f"LIVE_PLIST_UNREADABLE:{exc}"[:200]}
    if previous is None or previous_commit is None:
        return {"status": "NONE", "reason": "NO_LIVE_CONTROLLER"}
    head = host.run(_ctl(previous, "rev-parse", "--verify", "HEAD^{commit}"))
    if head.returncode != 0 or not _SHA.match(head.stdout.strip()):
        return {"status": "SKIPPED", "reason": "LIVE_CONTROLLER_UNREADABLE"}
    previous_head = head.stdout.strip()
    if previous_head == previous_commit:
        return {"status": "NONE", "from": str(previous), "from_head": previous_head, "carried": []}
    # Bytes, not text: a non-UTF-8 path must not break the deploy.
    changed = subprocess.run(
        _ctl(
            previous,
            "diff",
            "--raw",
            "-z",
            "--no-renames",
            "--no-abbrev",
            previous_commit,
            previous_head,
        ),
        capture_output=True,
        timeout=120,
        check=False,
    )
    if changed.returncode != 0:
        return _skipped("LIVE_CONTROLLER_DIFF_FAILED", previous, previous_head)
    fields = changed.stdout.split(b"\0")
    entries = []
    for index in range(0, len(fields) - 1, 2):
        header = fields[index].decode("ascii", errors="replace")
        try:
            path = fields[index + 1].decode("utf-8")
        except UnicodeDecodeError:
            return _skipped("LIVE_CONTROLLER_PATH_NOT_UTF8", previous, previous_head)
        parts = header[1:].split()
        if not header.startswith(":") or len(parts) < 5:
            return _skipped("LIVE_CONTROLLER_DIFF_UNPARSEABLE", previous, previous_head)
        entries.append((parts[1], parts[4], path))
    if len(entries) > CARRY_MAX_PATHS:
        return _skipped("TOO_MANY_BOUND_PATHS", previous, previous_head)
    for new_mode, _change, path in entries:
        parts = path.split("/")
        if (
            parts[0] != "tasks"
            or any(part in {"", ".", ".."} for part in parts[1:])
            or any(
                part.casefold() in {".gitattributes", ".gitmodules", ".gitignore"} for part in parts
            )
            or new_mode not in {"000000", "100644", "100755"}
            or any(ord(char) < 32 for char in path)
        ):
            # Not a bind: the Gateway would refuse this Controller anyway.
            return _skipped("LIVE_CONTROLLER_NOT_BIND_ONLY", previous, previous_head)
    carried: List[str] = []
    skipped: List[str] = []
    for _new_mode, change, path in entries:
        base = host.run(
            _ctl(controller, "rev-parse", "--verify", "--quiet", f"{previous_commit}:{path}")
        )
        now = host.run(_ctl(controller, "rev-parse", "--verify", "--quiet", f"{commit}:{path}"))
        if base.stdout.strip() != now.stdout.strip():
            skipped.append(path)  # main changed this path since the live commit
            continue
        # Literal pathspecs: a bound file named ``tasks/c/x*`` must not match others.
        if change == "D":
            argv = _ctl_literal(controller, "rm", "-q", "--ignore-unmatch", "--", path)
        else:
            argv = _ctl_literal(controller, "checkout", previous_head, "--", path)
        if host.run(argv).returncode != 0:
            return _reset_carry(host, controller, commit, previous_head, "CARRY_APPLY_FAILED")
        carried.append(path)
    if carried:
        result = host.run([
            "git",
            *CARRY_AUTHOR,
            "-c",
            "commit.gpgsign=false",
            "-C",
            str(controller),
            "commit",
            "-q",
            "--no-verify",
            "-m",
            f"chore(tasks): carry bound Task Cards from {previous_head[:12]}",
        ])
        if result.returncode != 0:
            return _reset_carry(host, controller, commit, previous_head, "CARRY_COMMIT_FAILED")
    return {
        "status": "CARRIED" if carried else "NONE",
        "from": str(previous),
        "from_head": previous_head,
        "carried": sorted(carried)[:100],
        "carried_count": len(carried),
        "skipped_main_changed": sorted(skipped)[:100],
        "lost": bool(skipped),
    }


def _skipped(reason: str, previous: Path, previous_head: str) -> Dict[str, Any]:
    return {
        "status": "SKIPPED",
        "reason": reason,
        "from": str(previous),
        "from_head": previous_head,
        "lost": True,
    }


def _ctl_literal(controller: Path, *args: str) -> List[str]:
    return ["git", "--literal-pathspecs", "-C", str(controller), *args]


def _reset_carry(
    host: Host, controller: Path, commit: str, previous_head: Optional[str], reason: str
) -> Dict[str, Any]:
    host.run(_ctl(controller, "reset", "-q", "--hard", commit))
    host.run(_ctl(controller, "clean", "-q", "-fd", "--", "tasks"))
    return {"status": "SKIPPED", "reason": reason, "from_head": previous_head, "lost": True}


def _receipt_controller(receipt: Dict[str, Any]) -> Optional[Path]:
    root = (receipt.get("controller") or {}).get("root")
    return Path(root) if isinstance(root, str) and root else None


def _contained_dirs(parent: Path) -> List[Path]:
    """Real (non-symlink) ``a1-*`` directories strictly inside a real ``parent``."""
    if parent.is_symlink() or not parent.is_dir():
        return []
    real_parent = parent.resolve()
    found = []
    for child in parent.iterdir():
        if not child.name.startswith(DEPLOYMENT_PREFIX) or child.is_symlink():
            continue
        if child.is_dir() and child.resolve().parent == real_parent:
            found.append(child)
    return found


def prune_refusal(cfg: Config) -> Optional[str]:
    """Why pruning is unsafe here, or None.  Nothing may be reached through a symlink."""
    root = cfg.gateway_root
    if not root.is_absolute() or os.path.realpath(root) != str(root):
        return f"GATEWAY_ROOT_NOT_CANONICAL:{root}"
    for path in (
        cfg.deployments,
        cfg.venvs,
        cfg.core_checkouts,
        cfg.rie_checkouts,
        cfg.controllers,
        cfg.pycache_prefixes,
    ):
        if path.is_symlink():
            return f"SYMLINKED_DIRECTORY:{path}"
    return None


def prune(cfg: Config, host: Host, protected: List[Optional[Path]]) -> List[str]:
    """Keep the newest ``cfg.keep`` a1-* deployments plus every protected one.

    Refuses outright when ``deployments/`` or ``venvs/`` is a symlink and never
    follows symlinked children, so nothing outside those two directories is removed.
    """
    if prune_refusal(cfg):
        return []
    keep_names = {p.name for p in protected if p is not None}
    candidates = sorted(
        _contained_dirs(cfg.deployments), key=lambda p: p.stat().st_mtime, reverse=True
    )
    removed: List[str] = []
    retained_names = _retained_names(cfg)
    if retained_names is None:
        # Fail closed: an unreadable retention list may protect the only copy
        # of a late bind, so nothing is pruned until it is repaired.
        return []
    for index, path in enumerate(candidates):
        if index < cfg.keep or path.name in keep_names or path.name in retained_names:
            continue
        host.run(_git(cfg, "worktree", "remove", "--force", str(path)), timeout=300)
        if path.exists() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        removed.append(path.name)
    present = {p.name for p in cfg.deployments.iterdir()} if cfg.deployments.is_dir() else set()
    for venv in _contained_dirs(cfg.venvs):
        if venv.name not in present:
            shutil.rmtree(venv, ignore_errors=True)
    # A deployment's bytecode prefix goes with it (#2246).
    for cache in _contained_dirs(cfg.pycache_prefixes):
        if cache.name not in present:
            shutil.rmtree(cache, ignore_errors=True)
    # A Controller lives exactly as long as its deployment, and never goes while
    # a protected (live, previous, tool) deployment of that name exists (#1939).
    for controller in _contained_dirs(cfg.controllers):
        if (
            controller.name in present
            or controller.name in keep_names
            or controller.name in retained_names
        ):
            continue
        host.run(_git(cfg, "worktree", "remove", "--force", str(controller)), timeout=300)
        if controller.exists() and not controller.is_symlink():
            shutil.rmtree(controller, ignore_errors=True)
    prune_core(cfg, host, protected)
    prune_rie(cfg, host, protected)
    return removed


def prune_core(cfg: Config, host: Host, protected: List[Optional[Path]]) -> List[str]:
    """Remove ``core/<sha>`` checkouts no remaining or protected deployment pins.

    Nothing is removed if an ``a1-*`` deployment has a pin file that cannot be
    read, or if a protected ``a1-*`` deployment has none.  An unprotected ``a1-*``
    directory without a pin file pins nothing; r1 deployments never use these
    checkouts.
    """
    parent = cfg.core_checkouts
    if prune_refusal(cfg) or parent.is_symlink() or not parent.is_dir():
        return []
    guarded = [p for p in protected if p is not None]
    guarded_names = {p.name for p in guarded}
    roots = list(guarded)
    if cfg.deployments.is_dir():
        roots += [p for p in cfg.deployments.iterdir() if p.is_dir() and not p.is_symlink()]
    pinned = set()
    for root in roots:
        if not root.name.startswith(DEPLOYMENT_PREFIX):
            with contextlib.suppress(DeployError):
                pinned.add(read_core_pin(root))
            continue
        if not (root / CORE_PIN_FILE).exists() and root.name not in guarded_names:
            continue
        try:
            pinned.add(read_core_pin(root))
        except DeployError:
            return []
    real_parent = parent.resolve()
    removed: List[str] = []
    for child in sorted(parent.iterdir()):
        if child.is_symlink() or not child.is_dir() or not _SHA.match(child.name):
            continue
        if child.resolve().parent != real_parent or child.name in pinned:
            continue
        host.run(_core_git(cfg, "worktree", "remove", "--force", str(child)), timeout=300)
        if child.exists() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        removed.append(child.name)
    return removed


def prune_rie(cfg: Config, host: Host, protected: List[Optional[Path]]) -> List[str]:
    """Remove ``rie/<sha>`` checkouts no remaining or protected deployment pins (#1579).

    Kept: every pin of a remaining or protected deployment and the root the live
    wrapper exports.  Nothing is removed when any of that cannot be read.
    """
    parent = cfg.rie_checkouts
    if prune_refusal(cfg) or parent.is_symlink() or not parent.is_dir():
        return []
    roots = [p for p in protected if p is not None]
    if cfg.deployments.is_dir():
        roots += [p for p in cfg.deployments.iterdir() if p.is_dir() and not p.is_symlink()]
    try:
        pinned = set(rie_roots_in_use(cfg))
    except DeployError:
        return []
    for root in roots:
        if not (root / RIE_PIN_FILE).exists():
            continue
        try:
            pinned.add(read_rie_pin(root))
        except DeployError:
            return []
    real_parent = parent.resolve()
    removed: List[str] = []
    for child in sorted(parent.iterdir()):
        if child.is_symlink() or not child.is_dir() or not _SHA.match(child.name):
            continue
        if child.resolve().parent != real_parent or child.name in pinned:
            continue
        host.run(_rie_git(cfg, "worktree", "remove", "--force", str(child)), timeout=300)
        if child.exists() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        removed.append(child.name)
    return removed


# ----------------------------------------------------------------- receipts/state


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_receipts(state_dir: Path) -> List[Dict[str, Any]]:
    path = state_dir / "receipts.jsonl"
    if not path.is_file():
        return []
    receipts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        with contextlib.suppress(ValueError):
            item = json.loads(line)
            if isinstance(item, dict) and item.get("schema") == RECEIPT_SCHEMA:
                receipts.append(item)
    return receipts


def last_receipt(state_dir: Path) -> Optional[Dict[str, Any]]:
    receipts = read_receipts(state_dir)
    return receipts[-1] if receipts else None


def _append_receipt(cfg: Config, receipt: Dict[str, Any]) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    line = json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n"
    with open(cfg.receipts, "a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


_TASK_ID_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ACTION_STATE_SAFE = re.compile(r"^[A-Z][A-Z_]{0,39}$")


def _parse_iso(value: Any) -> Optional[float]:
    """Epoch of a ``%Y-%m-%dT%H:%M:%SZ`` string, or None for anything else."""
    if not isinstance(value, str) or not _ISO_UTC.match(value):
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return parsed.timestamp()


DEFERRALS_MAX_BYTES = 1_000_000


def _rotate_if_large(path: Path) -> None:
    """Keep the deferral log bounded: one previous generation, ~1 MB each."""
    try:
        if path.stat().st_size >= DEFERRALS_MAX_BYTES:
            os.replace(path, path.with_name(path.name + ".1"))
    except FileNotFoundError:
        pass


def _safe_reason(reason: str) -> str:
    """Only a code-like prefix of an UNKNOWN reason may reach a comment or log."""
    match = re.match(r"[A-Z][A-Z0-9_]{0,63}", reason)
    return match.group(0) if match else "UNKNOWN"


_ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def classify_task_report(returncode: int, stdout: str, stderr: str = "") -> Dict[str, Any]:
    """Turn the classifier output into CLEAR / IN_FLIGHT / UNKNOWN (fail closed)."""
    if returncode != 0:
        return {"verdict": "UNKNOWN", "reason": f"CLASSIFIER_EXIT_{returncode}"}
    lines = [line for line in stdout.splitlines() if line.strip()]
    try:
        report = json.loads(lines[-1]) if lines else None
    except ValueError:
        report = None
    tasks = report.get("tasks") if isinstance(report, dict) else None
    if not isinstance(tasks, list):
        return {"verdict": "UNKNOWN", "reason": "CLASSIFIER_OUTPUT_MALFORMED"}
    blocking: List[str] = []
    for task in tasks:
        if not isinstance(task, dict):
            return {"verdict": "UNKNOWN", "reason": "CLASSIFIER_OUTPUT_MALFORMED"}
        task_id = str(task.get("task_id") or "")
        name = task_id if _TASK_ID_SAFE.match(task_id) else "<unprintable-task-id>"
        state = task.get("action_state")
        if state == "TERMINAL" or state == "FINAL_BLOCK":
            continue
        if state in IN_FLIGHT_ACTION_STATES:
            blocking.append(name)
        else:
            label = (
                state if isinstance(state, str) and _ACTION_STATE_SAFE.match(state) else "UNKNOWN"
            )
            blocking.append(f"{name}:{label}")
    if blocking:
        return {"verdict": "IN_FLIGHT", "task_ids": sorted(blocking), "checked": len(tasks)}
    return {"verdict": "CLEAR", "checked": len(tasks)}


def _retained_names(cfg: Config) -> Optional[set]:
    """Names kept from pruning; None when an existing list cannot be trusted."""
    if not cfg.retained_controllers.exists():
        return set()
    retained = _read_json_object(cfg.retained_controllers)
    return None if retained is None else set(retained)


def _read_json_object(path: Path) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _quiescence_warning(cfg: Config, candidate: str, blocking: List[str], age: float) -> str:
    hours = age / 3600.0
    names = "\n".join(f"- `{name}`" for name in blocking[:50])
    return (
        "<!-- NEXUS_GATEWAY_QUIESCENCE_WARNING -->\n"
        f"**Gateway auto-deploy has been deferred for {hours:.1f} h** because governed tasks "
        f"are still in flight (#2227). Candidate `{candidate}` is waiting; the live Gateway "
        "is unchanged and will not be switched automatically.\n\n"
        f"Blocking tasks ({len(blocking)}):\n{names}\n\n"
        "Resolve each task (finish, reconcile or retire it), or, for an orphaned task, run "
        "`nexus_gateway_auto_deploy.py run --allow-in-flight` by hand. Deferral never ends "
        "in an automatic switch.\n"
    )


def _write_status(cfg: Config, payload: Dict[str, Any]) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(
        cfg.state_dir / "status.json", json.dumps(payload, sort_keys=True).encode(), 0o600
    )


def hold_reason(cfg: Config, environ: Optional[Dict[str, str]] = None) -> Optional[str]:
    env = os.environ if environ is None else environ
    if env.get(HOLD_ENV, "") not in ("", "0"):
        return f"env:{HOLD_ENV}"
    if cfg.hold_file.exists():
        return f"file:{cfg.hold_file}"
    return None


def _hold_text(cfg: Config) -> str:
    """The HOLD file's reason text, or "" when absent or unreadable."""
    try:
        return cfg.hold_file.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return ""


def _set_hold(cfg: Config, reason: str) -> None:
    """Write HOLD atomically: a crash or full disk leaves the whole text or none (#2169)."""
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(cfg.hold_file, (reason + "\n").encode("utf-8"), 0o600)


def known_plist_hashes(cfg: Config) -> List[str]:
    try:
        data = json.loads(cfg.known_plists.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [h for h in data.get("sha256", []) if isinstance(h, str)]


def remember_plist(cfg: Config, data: bytes) -> None:
    """Record plist bytes this deployer wrote or the Owner adopted (bounded history)."""
    digest = _sha256(data)
    hashes = [h for h in known_plist_hashes(cfg) if h != digest][-49:] + [digest]
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(cfg.known_plists, json.dumps({"sha256": hashes}).encode(), 0o600)


@contextlib.contextmanager
def _cycle_lock(cfg: Config) -> Iterator[bool]:
    import fcntl

    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    with open(cfg.state_dir / ".lock", "w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True


# -------------------------------------------------------------------------- cycle


def run_cycle(
    cfg: Config,
    host: Host,
    prober: Prober,
    api_get: Callable[[str], Any],
    *,
    dry_run: bool = False,
    force: bool = False,
    environ: Optional[Dict[str, str]] = None,
    tool_python: Optional[Path] = None,
    fetch: bool = True,
    allow_in_flight: bool = False,
) -> Dict[str, Any]:
    started = host.now()
    status: Dict[str, Any] = {
        "schema": STATUS_SCHEMA,
        "polled_at": _iso(started),
        "dry_run": dry_run,
    }
    with _cycle_lock(cfg) as acquired:
        if not acquired:
            return {**status, "status": "BUSY"}
        ctx = _Cycle(cfg, host, prober, api_get, environ, tool_python or Path(sys.executable))
        ctx.fetch = fetch
        ctx.allow_in_flight = allow_in_flight
        # Stuck: the last receipt says RECONCILE_FAILED, or (if that receipt
        # could not be written) the HOLD text itself does (#2169 F2).
        stuck = hold_reason(cfg, environ) and (
            (last_receipt(cfg.state_dir) or {}).get("outcome") == "RECONCILE_FAILED"
            or _hold_text(cfg).startswith(RECONCILE_FAILED_HOLD)
        )
        if cfg.journal.exists() and not dry_run and stuck:
            # A valid journal whose reconciliation failed unexpectedly: kept and
            # held for the Owner instead of failing again every cycle.
            return {**status, "status": "HELD", "hold": hold_reason(cfg, environ)}
        if cfg.journal.exists() and not dry_run:
            # A half-finished switch is safety work, not a new deploy: it is
            # resolved even under HOLD (HOLD still blocks every new switch).
            receipt = ctx.reconcile_journal()
            result = {**status, "status": f"RECONCILED_{receipt['outcome']}", "receipt": receipt}
        else:
            # Checked under the lock, so a HOLD set while waiting is honoured.
            held = hold_reason(cfg, environ)
            if held:
                return {**status, "status": "HELD", "hold": held}
            result = ctx.run(status, dry_run=dry_run, force=force)
    if not dry_run:
        _write_status(cfg, result)
    return result


class _Cycle:
    def __init__(
        self,
        cfg: Config,
        host: Host,
        prober: Prober,
        api_get: Callable[[str], Any],
        environ: Optional[Dict[str, str]],
        tool_python: Path,
    ) -> None:
        self.cfg, self.host, self.prober, self.api_get = cfg, host, prober, api_get
        self.environ = environ
        self.tool_python = tool_python
        self.fetch = True
        # Manual `run --allow-in-flight` only; the LaunchAgent never passes it.
        self.allow_in_flight = False
        self.quiescence_note: Optional[Dict[str, Any]] = None
        # The pre-build pin-bump verdict, copied into the receipt (#2309).
        self.pin_note: Optional[Dict[str, Any]] = None

    # -- task quiescence (#2227) --------------------------------------------

    def quiescence(self, live_plist: bytes, candidate: str) -> Dict[str, Any]:
        """Classify live tasks and track the deferral episode; never switches anything."""
        return self.track_deferral(candidate, self.host.tasks_in_flight(self.cfg, live_plist))

    def track_deferral(self, candidate: str, verdict: Dict[str, Any]) -> Dict[str, Any]:
        """CLEAR ends the episode; anything else extends it (#2227).

        The episode start lives in ``quiescence.json``.  A new or changed
        blocking set and the warning append one line to ``deferrals.jsonl``;
        once the episode is older than the warning cap, one loud comment naming
        the blocking tasks goes to the alert Issue.  The switch stays deferred
        whatever the age: it is never forced automatically.
        """
        cfg, host = self.cfg, self.host
        now = host.now()
        if verdict.get("verdict") == "CLEAR":
            # The episode ends only when the Gateway is current (a switch or
            # IN_SYNC, see ``end_deferral``), so a task that keeps appearing
            # during the build window still ages toward the warning.
            return verdict
        episode = _read_json_object(cfg.quiescence_file) or {}
        since = episode.get("since_epoch")
        if (
            isinstance(since, bool)
            or not isinstance(since, (int, float))
            or not math.isfinite(since)
        ):
            since = now
        warned_at = _parse_iso(episode.get("warned_at"))
        if warned_at is not None and warned_at > now:
            warned_at = None  # a future marker can never mute a warning
        if warned_at is not None and (
            (
                # The candidate the last warning named, not the latest one seen,
                # so a candidate that arrives inside the hour still re-arms later.
                episode.get("warned_candidate", episode.get("candidate")) != candidate
                and now - warned_at >= QUIESCENCE_REARM_MIN_SECONDS
            )
            or now - warned_at >= QUIESCENCE_REWARN_SECONDS
        ):
            # Re-arm: a new candidate or a day-old warning gets a fresh one, so a
            # past warning never mutes a later starvation.
            warned_at = None
        reason = str(verdict.get("reason") or "UNKNOWN")
        # Bounded: comments, episode and log lines never carry an unbounded list.
        blocking = sorted(verdict.get("task_ids") or [_safe_reason(reason)])[:100]
        changed = episode.get("blocking") != blocking or episode.get("candidate") != candidate
        # A clock that went backwards never restarts the episode; it just ages 0.
        age = max(0.0, now - float(since))
        updated: Dict[str, Any] = {
            "schema": "nexus.gateway.quiescence_episode.v1",
            "since": _iso(float(since)),
            "since_epoch": float(since),
            "candidate": candidate,
            "blocking": blocking,
            "warned_at": None if warned_at is None else _iso(warned_at),
            "warned_candidate": (
                None
                if warned_at is None
                else episode.get("warned_candidate", episode.get("candidate"))
            ),
        }
        warn_due = age >= cfg.quiescence_warn_after_seconds and warned_at is None
        if warn_due:
            # Posted before the marker is saved: a crash in between can repeat
            # the warning, but can never lose it.
            body = _quiescence_warning(cfg, candidate, blocking, age)
            posted = host.post_issue_comment(cfg, body)
            updated["warned_at"] = _iso(now) if posted else None
            updated["warned_candidate"] = candidate if posted else None
            updated["warning_failed"] = not posted
        _atomic_write(cfg.quiescence_file, json.dumps(updated, sort_keys=True).encode(), 0o600)
        result = {
            **verdict,
            "task_ids": blocking if verdict.get("task_ids") else None,
            "task_count": len(verdict.get("task_ids") or []),
            "deferred_since": updated["since"],
            "deferral_age_seconds": int(age),
            "blocking": blocking,
            "warned_at": updated["warned_at"],
        }
        if changed or (warn_due and updated["warned_at"] is not None):
            cfg.state_dir.mkdir(parents=True, exist_ok=True)
            _rotate_if_large(cfg.deferrals)
            line = {
                "schema": "nexus.gateway.quiescence_deferral.v1",
                "candidate_commit": candidate,
                "outcome": DEFERRED_OUTCOME,
                "at": _iso(now),
                "quiescence": result,
            }
            with open(cfg.deferrals, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n")
        return result

    def end_deferral(self) -> None:
        """A switch (automatic or overridden) or IN_SYNC ends the episode."""
        with contextlib.suppress(FileNotFoundError):
            self.cfg.quiescence_file.unlink()

    def deferral_age(self) -> Optional[Dict[str, Any]]:
        """The episode that ended, for the receipt of the deploy that follows it."""
        episode = _read_json_object(self.cfg.quiescence_file)
        since = (episode or {}).get("since_epoch")
        if (
            isinstance(since, bool)
            or not isinstance(since, (int, float))
            or not math.isfinite(since)
        ):
            return None
        return {
            "deferred_since": _iso(float(since)),
            "deferral_age_seconds": int(max(0.0, self.host.now() - float(since))),
        }

    # -- degraded Controller (#2230 F2) --------------------------------------

    def live_controller_binding(self, status: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """The live ``controller_binding`` when it is DEGRADED, else None.

        Absent (a Gateway from before #2232) or any other value changes nothing.
        An unreachable or unreadable /health only adds a warning: a single
        transient failure never holds the deployer.
        """
        try:
            health = self.prober.live_health()
        except Exception as exc:  # noqa: BLE001 - IN_SYNC must not gain a failure mode
            status.setdefault("warnings", []).append(f"LIVE_HEALTH_UNREADABLE:{type(exc).__name__}")
            return None
        binding = health.get("controller_binding") if isinstance(health, dict) else None
        if not isinstance(binding, dict) or binding.get("status") != "DEGRADED":
            # A non-degraded reading ends the alert episode, so a later
            # degraded start (after a restart) is announced again.
            # Any OSError: a clean IN_SYNC cycle must never fail on this marker.
            with contextlib.suppress(OSError):
                self.cfg.controller_alert_file.unlink()
            return None
        reason = _safe_reason(str(binding.get("reason") or "UNKNOWN"))
        status["live_controller_binding"] = {"status": "DEGRADED", "reason": reason}
        return {"status": "DEGRADED", "reason": reason}

    def alert_degraded(
        self,
        candidate: str,
        live: Optional[Path],
        binding: Dict[str, Any],
        status: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Warn and record (both rate limited); never holds, restarts or switches.

        No HOLD: the next deploy of a new main commit materializes a fresh
        Controller and so heals the Gateway, and a HOLD would block exactly
        that.  The receipt is written only with an alert attempt, so a
        degraded Gateway that stays IN_SYNC does not add one receipt per cycle.
        A local write failure only adds a warning: this path never fails a cycle.
        """
        cfg, host = self.cfg, self.host
        now = host.now()
        reason = binding["reason"]
        alert = _read_json_object(cfg.controller_alert_file) or {}
        warned_at = _parse_iso(alert.get("warned_at"))
        if warned_at is not None and warned_at > now:
            warned_at = None  # a future marker can never mute a warning
        if warned_at is not None and (
            (
                (alert.get("reason"), alert.get("commit")) != (reason, candidate)
                and now - warned_at >= QUIESCENCE_REARM_MIN_SECONDS
            )
            or now - warned_at >= QUIESCENCE_REWARN_SECONDS
        ):
            warned_at = None  # re-arm, as the quiescence warning does
        if warned_at is not None:
            return {"warning": {"posted": False, "suppressed_since": _iso(warned_at)}}
        body = (
            "<!-- NEXUS_GATEWAY_LIVE_DEGRADED_CONTROLLER -->\n"
            f"**The live Gateway `{candidate[:12]}` is running with a DEGRADED Controller** "
            f"(`{reason}`, #2230 F2). Every Controller effect is refused until the Gateway "
            "is restarted with a valid Controller; a degraded start never heals in place.\n\n"
            "The auto-deployer changed nothing: no HOLD, no restart, no switch. The next "
            "deploy of a new main commit materializes a fresh Controller and should heal it; "
            "to heal sooner, fix the Controller binding and restart the Gateway, then check "
            "that /health `controller_binding` is no longer DEGRADED.\n"
        )
        # Posted before the marker is saved: a crash in between can repeat the
        # warning, but can never lose it.
        posted = host.post_issue_comment(cfg, body, issue=CONTROLLER_ALERT_ISSUE)
        if posted:
            marker = {
                "schema": "nexus.gateway.controller_alert.v1",
                "warned_at": _iso(now),
                "reason": reason,
                "commit": candidate,
            }
            try:
                _atomic_write(
                    cfg.controller_alert_file, json.dumps(marker, sort_keys=True).encode(), 0o600
                )
            except OSError as exc:
                status.setdefault("warnings", []).append(
                    f"CONTROLLER_ALERT_MARKER_UNWRITABLE:{type(exc).__name__}"
                )
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "attempt_id": f"{candidate[:12]}-{int(now)}-degraded",
            "candidate_commit": candidate,
            "previous_commit": candidate,
            "previous_root": str(live),
            "started_at": _iso(now),
            "finished_at": _iso(now),
            "outcome": LIVE_DEGRADED_OUTCOME,
            "switched": False,
            "rolled_back": False,
            "controller_binding": binding,
            "warning": {"posted": posted},
        }
        try:
            _append_receipt(cfg, receipt)
        except OSError as exc:
            status.setdefault("warnings", []).append(
                f"LIVE_DEGRADED_RECEIPT_UNWRITABLE:{type(exc).__name__}"
            )
        return {"warning": {"posted": posted}, "receipt": receipt}

    # -- entry -------------------------------------------------------------

    def run(self, status: Dict[str, Any], *, dry_run: bool, force: bool) -> Dict[str, Any]:
        cfg, host = self.cfg, self.host
        if cfg.journal.exists():
            return {**status, "status": "PENDING_SWITCH_JOURNAL", "journal": str(cfg.journal)}
        previous_plist = cfg.plist.read_bytes()
        if _sha256(previous_plist) not in known_plist_hashes(cfg):
            if dry_run:
                block = host.r1_recovery_block(cfg)
                state = "BLOCKED_MANAGER_BUSY" if block is not None else "FOREIGN_PLIST"
                return {**status, "status": state}
            verdict = self.foreign_verdict()
            if verdict is not None:
                return {**status, **verdict}
            previous_plist = cfg.plist.read_bytes()
        origin = _must(host, _git(cfg, "remote", "get-url", "origin"), "ORIGIN_URL_FAILED").strip()
        if origin not in ORIGIN_URLS:
            return {**status, "status": "ORIGIN_MISMATCH", "origin": origin}
        if self.fetch:
            refspec = f"+refs/heads/{cfg.track_branch}:{TRACK_REF}"
            fetch = _git(cfg, "fetch", "--quiet", "--no-tags", "origin", refspec)
            _must(host, fetch, "FETCH_FAILED", timeout=300)
        candidate = _must(
            host, _git(cfg, "rev-parse", f"{TRACK_REF}^{{commit}}"), "TRACK_REF_FAILED"
        ).strip()
        if not _SHA.match(candidate):
            raise DeployError("TRACK_REF_NOT_A_COMMIT")
        previous_root = live_root(previous_plist)
        previous_commit = commit_of(previous_root)
        status.update(
            candidate_commit=candidate, live_commit=previous_commit, live_root=str(previous_root)
        )

        def finish(state: str, **extra: Any) -> Dict[str, Any]:
            if not dry_run and state != "PLAN":
                refusal = prune_refusal(cfg)
                if refusal:
                    extra["prune_refused"] = refusal
                removed = self.prune([previous_root])
                if removed:
                    extra["pruned"] = removed
            return {**status, "status": state, **extra}

        if candidate == previous_commit:
            self.end_deferral()
            binding = self.live_controller_binding(status)
            if binding is not None and not dry_run:
                degraded = self.alert_degraded(candidate, previous_root, binding, status)
                return finish(LIVE_DEGRADED_OUTCOME, **degraded)
            return finish("IN_SYNC")
        receipts = [
            r for r in read_receipts(cfg.state_dir) if r.get("candidate_commit") == candidate
        ]
        failures = [r for r in receipts if r.get("outcome") in FAILED_OUTCOMES]
        if not force and (
            any(r.get("outcome") == "REJECTED_BUILD" for r in failures)
            or sum(r.get("outcome") in RETRYABLE_REJECTIONS for r in failures)
            >= MAX_CANDIDATE_ATTEMPTS
        ):
            return finish("CANDIDATE_REJECTED_BEFORE", attempts=len(failures))
        main_check = on_github_main(
            self.api_get, candidate, repo=cfg.repository, branch=cfg.track_branch
        )
        status["github_main"] = main_check
        if not main_check["ok"]:
            return finish("CANDIDATE_NOT_ON_MAIN")
        checks = required_checks(
            self.api_get, candidate, repo=cfg.repository, branch=cfg.track_branch
        )
        status["required_checks"] = checks
        if checks["verdict"] == "UNKNOWN_REQUIRED_CHECK":
            # Never a deploy and no HOLD.  When the candidate's own deployer knows
            # the names, only the deployer link moves (#2402); otherwise this is
            # retried next cycle (and stays here while no main deployer knows them).
            update = self.self_update(candidate, previous_plist, checks, dry_run=dry_run)
            status["self_update"] = update["self_update"]
            if "receipt" in update:
                status["receipt"] = update["receipt"]
                return finish(update["receipt"]["outcome"])
            return finish("UNKNOWN_REQUIRED_CHECK:" + ",".join(checks["unknown_required"]))
        if checks["verdict"] != "GREEN":
            return finish(f"CHECKS_{checks['verdict']}")
        pins = self.pin_bumps(record=not dry_run)
        status["pin_bumps"] = pins
        self.pin_note = pins
        if not dry_run:
            self.announce_parked(pins)
        if pins.get("warnings"):
            status["warnings"] = list(pins["warnings"])
        if pins["verdict"] != "CLEAR":
            return finish(f"PIN_BUMP_{pins['verdict']}")
        if previous_commit and not force:
            diff = host.run(_git(cfg, "diff", "--name-only", previous_commit, candidate))
            count = host.run(_git(cfg, "rev-list", "--count", f"{previous_commit}..{candidate}"))
            if diff.returncode == 0 and count.returncode == 0:
                changed = [p for p in diff.stdout.splitlines() if p]
                behind = int(count.stdout.strip() or 0)
                status.update(changed_path_count=len(changed), behind=behind)
                if all(is_irrelevant(p) for p in changed) and behind < cfg.max_irrelevant_lag:
                    return finish("SKIPPED_IRRELEVANT")
        if not force:
            # A manager/R1 block is not the candidate's fault: plain debounce only.
            wait = self.backoff_remaining([
                r for r in failures if r.get("outcome") != "BLOCKED_MANAGER_BUSY"
            ])
            if wait > 0:
                return finish("BACKOFF" if failures else "DEBOUNCED", retry_in_seconds=int(wait))
        root = cfg.deployments / f"{DEPLOYMENT_PREFIX}{candidate}"
        venv_python = cfg.venvs / f"{DEPLOYMENT_PREFIX}{candidate}" / "bin" / "python"
        if dry_run:
            return finish(
                "PLAN",
                plan={
                    "deployment_root": str(root),
                    "venv_python": str(venv_python),
                    "steps": [
                        "build worktree + venv (uv sync --frozen)",
                        "materialize clean nexus-core checkout at the tree's "
                        "CANONICAL_CORE_REVISION (NEXUS_CORE_REPO_ROOT)",
                        "probe on spare port with throwaway state",
                        "re-check HOLD and pin bumps",
                        f"journal + rewrite {cfg.plist} under the manager lock",
                        f"reload {GATEWAY_LABEL}",
                        f"probe port {LIVE_PORT}",
                        "rollback to previous plist on failure",
                    ],
                    "live_command": wrapper_command(cfg, root, venv_python),
                },
            )
        # Advisory early checks (the authoritative ones are under the lock right
        # before the plist write): no build or probe churn while R1 is open or
        # while governed tasks are in flight (#2227).
        block = host.r1_recovery_block(cfg)
        if block is not None:
            return finish("BLOCKED_MANAGER_BUSY", reason=block)
        previous_deferral = self.deferral_age()
        quiet = self.quiescence(previous_plist, candidate)
        status["quiescence"] = quiet
        if quiet.get("verdict") != "CLEAR":
            if not self.allow_in_flight:
                return finish(DEFERRED_OUTCOME)
            status["quiescence_overridden"] = True
        if previous_deferral is not None:
            status["ended_deferral"] = previous_deferral
        self.quiescence_note = {
            "pre_build": quiet,
            "ended_deferral": previous_deferral,
            "overridden": bool(status.get("quiescence_overridden")),
        }
        receipt = self.attempt(candidate, previous_plist, checks, status.get("warnings", []))
        if receipt.get("outcome") == "DEPLOYED":
            self.end_deferral()
        status["receipt"] = receipt
        return finish(receipt["outcome"])

    # -- parked pin bumps (#2309) ----------------------------------------------

    def pin_bumps(self, *, record: bool) -> Dict[str, Any]:
        """``pin_bumps_in_flight`` with this deployer's park clock and threshold."""
        cfg = self.cfg
        pins = pin_bumps_in_flight(
            self.api_get,
            repo=cfg.repository,
            now=self.host.now(),
            park_file=cfg.pin_park_file,
            park_seconds=cfg.pin_bump_park_seconds,
            record=record,
        )
        if cfg.pin_bump_park_env_invalid:
            pins.setdefault("warnings", []).append("PIN_PARK_SECONDS_INVALID")
        return pins

    def announce_parked(self, pins: Dict[str, Any]) -> None:
        """One comment per (PR, head) on a pin-bump PR when it first parks (#2309).

        A failed post is retried next cycle; a posted one is remembered in the
        park record, so a PR is never commented twice for the same head.
        Never raises: a comment is visibility, not a gate.
        """
        cfg, host = self.cfg, self.host
        try:
            for parked in pins.get("parked") or []:
                key, head = str(parked["number"]), parked["head_sha"]
                prs = _load_pin_park(cfg.pin_park_file)
                entry = prs.get(key)
                if not isinstance(entry, dict) or entry.get("head_sha") != head:
                    continue  # the record was not written: no comment state to keep
                if entry.get("commented_head") == head:
                    continue
                if not host.post_issue_comment(
                    cfg, _pin_parked_comment(parked), issue=int(parked["number"])
                ):
                    continue
                prs[key] = {**entry, "commented_head": head}
                _save_pin_park(cfg.pin_park_file, prs)
        except Exception as exc:  # noqa: BLE001 - never let a comment stop a cycle
            pins.setdefault("warnings", []).append(
                f"PIN_PARK_COMMENT_FAILED:{type(exc).__name__}"[:200]
            )

    # -- deployer-only self-update (#2402) -------------------------------------

    def self_update(
        self,
        candidate: str,
        previous_plist: bytes,
        checks: Dict[str, Any],
        *,
        dry_run: bool,
    ) -> Dict[str, Any]:
        """Move only ``auto-deploy-current`` to a candidate deployer that knows the names.

        Called only for UNKNOWN_REQUIRED_CHECK on a candidate already proven on
        GitHub main.  In order, every step fails closed (no link move, the
        cycle stays UNKNOWN_REQUIRED_CHECK):
          1. the link already points at the candidate tree (no self-update loop);
          2. the candidate's deployer source, read from the fetched commit and
             parsed with ``ast`` (never imported), knows every unknown name;
          3. earlier refused attempts for this candidate: capped and backed off;
          4. every live required check THIS file can bind, plus FLOOR_CHECKS,
             is bound and green on the candidate (nothing verifiable is skipped);
          5. the candidate tree is created as a deploy creates it, the
             candidate deployer passes the same selftests as after a deploy, and
             only then does the link move.  The Gateway plist is never written.
        Returns {"self_update": detail} and, when step 5 ran, {"receipt": ...}.
        """
        cfg, host = self.cfg, self.host
        unknown = list(checks.get("unknown_required") or [])
        detail: Dict[str, Any] = {"unknown_required": unknown}
        root = cfg.deployments / f"{DEPLOYMENT_PREFIX}{candidate}"
        if cfg.tool_link.is_symlink() and os.path.realpath(cfg.tool_link) == os.path.realpath(root):
            return {"self_update": {**detail, "verdict": "ALREADY_CURRENT"}}
        shown = host.run(_git(cfg, "show", f"{candidate}:{DEPLOYER}"), timeout=60)
        if shown.returncode != 0:
            return {"self_update": {**detail, "verdict": "CANDIDATE_SOURCE_UNREADABLE"}}
        known = deployer_known_checks(shown.stdout or "")
        if known is None:
            return {"self_update": {**detail, "verdict": "CANDIDATE_SOURCE_UNPARSEABLE"}}
        still_unknown = [name for name in unknown if name not in known]
        detail["candidate_deployer_sha256"] = _sha256((shown.stdout or "").encode("utf-8"))
        if still_unknown or not unknown:
            return {
                "self_update": {
                    **detail,
                    "verdict": "CANDIDATE_DOES_NOT_KNOW",
                    "still_unknown": still_unknown,
                }
            }
        refused = [
            r
            for r in read_receipts(cfg.state_dir)
            if r.get("candidate_commit") == candidate
            and r.get("outcome") == SELF_UPDATE_REFUSED_OUTCOME
        ]
        if len(refused) >= MAX_CANDIDATE_ATTEMPTS:
            return {"self_update": {**detail, "verdict": "GAVE_UP", "attempts": len(refused)}}
        if refused:
            interval = min(
                float(cfg.min_interval_seconds * (2 ** (len(refused) - 1))),
                float(MAX_BACKOFF_SECONDS),
            )
            wait = interval - (host.now() - float(refused[-1].get("started_epoch", 0)))
            if wait > 0:
                return {
                    "self_update": {**detail, "verdict": "BACKOFF", "retry_in_seconds": int(wait)}
                }
        subset = bindable_subset_checks(
            self.api_get,
            candidate,
            checks.get("known_required") or {},
            repo=cfg.repository,
            branch=cfg.track_branch,
        )
        detail["bindable_checks"] = subset
        if subset.get("verdict") != "GREEN":
            return {"self_update": {**detail, "verdict": f"CHECKS_{subset.get('verdict')}"}}
        if dry_run:
            return {"self_update": {**detail, "verdict": "PLAN", "deployer_root": str(root)}}
        held = hold_reason(cfg, self.environ)
        if held:
            return {"self_update": {**detail, "verdict": "HELD", "hold": held}}
        receipt = self.new_receipt(candidate, previous_plist)
        receipt["attempt_id"] += "-self-update"
        receipt["required_checks"] = checks
        previous_link = os.path.realpath(cfg.tool_link) if cfg.tool_link.is_symlink() else None
        receipt["self_update"] = {**detail, "previous_deployer_root": previous_link}
        try:
            tree = materialize_tree(cfg, host, candidate)
            dirty = _must(
                host, ["git", "-C", str(tree), "status", "--porcelain"], "WORKTREE_STATUS_FAILED"
            )
            if dirty.strip():
                raise DeployError("SOURCE_TREE_DIRTY")
            link = self.move_tool_link(tree)
        except Exception as exc:  # noqa: BLE001 - every failure still leaves a receipt
            link = {"moved": False, "reason": f"{type(exc).__name__}:{exc}"[:300]}
        receipt["deployer_link"] = link
        receipt["outcome"] = (
            SELF_UPDATED_OUTCOME if link.get("moved") else SELF_UPDATE_REFUSED_OUTCOME
        )
        finished = host.now()
        receipt.update(
            finished_at=_iso(finished),
            duration_seconds=round(finished - float(receipt["started_epoch"]), 3),
        )
        # Create-only, like every receipt; the plist and the journal are untouched.
        _append_receipt(cfg, receipt)
        verdict = "UPDATED" if link.get("moved") else "REFUSED"
        return {"self_update": {**detail, "verdict": verdict}, "receipt": receipt}

    def backoff_remaining(self, failures: List[Dict[str, Any]]) -> float:
        receipts = read_receipts(self.cfg.state_dir)
        if not receipts:
            return 0.0
        interval = self.cfg.min_interval_seconds * (2 ** max(0, len(failures) - 1))
        interval = min(float(interval), float(MAX_BACKOFF_SECONDS))
        # Neither a deferral (tasks in flight, or the Controller moved under the
        # carry, #1939) nor a degraded-Controller alert (#2230 F2) is an
        # attempt, and neither is a deployer-only self-update (#2402): they must
        # not move the debounce or backoff clock.
        attempts = [
            r
            for r in receipts
            if r.get("outcome")
            not in (
                DEFERRED_OUTCOME,
                CONTROLLER_MOVED_OUTCOME,
                LIVE_DEGRADED_OUTCOME,
                SELF_UPDATED_OUTCOME,
                SELF_UPDATE_REFUSED_OUTCOME,
            )
        ]
        if not attempts:
            return 0.0
        last_started = float(attempts[-1].get("started_epoch", 0))
        return interval - (self.host.now() - last_started)

    def prune(self, extra: List[Optional[Path]]) -> List[str]:
        cfg = self.cfg
        if cfg.journal.exists():
            return []
        tool = Path(os.path.realpath(cfg.tool_link)) if cfg.tool_link.is_symlink() else None
        current = None
        with contextlib.suppress(Exception):
            current = live_root(cfg.plist.read_bytes())
        return prune(cfg, self.host, [*extra, current, tool])

    # -- receipts ------------------------------------------------------------

    def new_receipt(self, candidate: str, previous_plist: bytes) -> Dict[str, Any]:
        started = self.host.now()
        previous_root = live_root(previous_plist)
        return {
            "schema": RECEIPT_SCHEMA,
            "attempt_id": f"{candidate[:12]}-{int(started)}",
            "candidate_commit": candidate,
            "previous_commit": commit_of(previous_root),
            "previous_root": str(previous_root),
            "started_at": _iso(started),
            "started_epoch": started,
            "switched": False,
            "rolled_back": False,
            "probes": {},
        }

    def close_receipt(
        self,
        receipt: Dict[str, Any],
        *,
        hold: Optional[str] = None,
        journal_to: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """HOLD first, then the receipt, and only then the journal goes away.

        If writing HOLD or the receipt fails, the exception propagates and the
        pending-switch journal stays, so the next cycle reconciles again.
        """
        finished = self.host.now()
        receipt.update(
            finished_at=_iso(finished),
            duration_seconds=round(finished - float(receipt["started_epoch"]), 3),
        )
        if hold is None and receipt["outcome"] == "ROLLBACK_FAILED":
            hold = f"auto-hold after ROLLBACK_FAILED {receipt['attempt_id']}"
        if hold is not None:
            _set_hold(self.cfg, hold)
        _append_receipt(self.cfg, receipt)
        if receipt.get("journal_kept"):
            return receipt
        if journal_to is not None:
            os.replace(self.cfg.journal, journal_to)
        else:
            with contextlib.suppress(FileNotFoundError):
                self.cfg.journal.unlink()
        return receipt

    def foreign_verdict(self) -> Optional[Dict[str, Any]]:
        """Decide an unknown live plist under GATEWAY_LOCK -> R1 ledger lock.

        An open R1 recovery may have written it, and R1 appends REQUESTED under
        the ledger lock, so the R1 check, the re-read and the FOREIGN_PLIST +
        HOLD write all happen while both locks are held.  Returns None when the
        plist turned out to be known after all.
        """
        cfg = self.cfg
        try:
            with self.host.manager_lock(cfg), self.host.r1_guard(cfg):
                block = self.host.r1_recovery_block(cfg)
                if block is not None:
                    return {"status": "BLOCKED_MANAGER_BUSY", "reason": block}
                if _sha256(cfg.plist.read_bytes()) in known_plist_hashes(cfg):
                    return None
                return {"status": "FOREIGN_PLIST", "receipt": self.foreign_plist()}
        except DeployError as exc:
            if str(exc).startswith("MANAGER_LOCK_UNAVAILABLE"):
                return {"status": "BLOCKED_MANAGER_BUSY", "reason": str(exc)[:300]}
            raise

    def foreign_plist(self) -> Dict[str, Any]:
        receipt = self.new_receipt("0" * 40, self.cfg.plist.read_bytes())
        receipt.pop("candidate_commit")
        receipt.update(
            outcome="FOREIGN_PLIST",
            reason="live plist was not written or adopted by the auto-deployer (manual rebind?)",
            live_plist_sha256=_sha256(self.cfg.plist.read_bytes()),
        )
        return self.close_receipt(
            receipt, hold="auto-hold: FOREIGN_PLIST; run `adopt` then `release` to resume"
        )

    # -- one attempt ------------------------------------------------------------

    def attempt(
        self, candidate: str, previous_plist: bytes, checks: Dict[str, Any], warnings: List[str]
    ) -> Dict[str, Any]:
        receipt = self.new_receipt(candidate, previous_plist)
        receipt["required_checks"] = checks
        if self.quiescence_note is not None:
            receipt["quiescence"] = self.quiescence_note
        if self.pin_note is not None:
            receipt["pin_bumps"] = self.pin_note
        receipt["warnings"] = list(warnings)
        hold: Optional[str] = None
        try:
            receipt.update(self.attempt_effects(candidate, previous_plist, receipt))
            if receipt.get("outcome") == DEFERRED_OUTCOME:
                # Caught under the lock: the same episode clock and warning (#2227).
                receipt["quiescence_episode"] = self.track_deferral(
                    candidate, receipt.get("quiescence_before_switch") or {}
                )
        except Exception as exc:  # noqa: BLE001 - every failure must still leave a receipt
            receipt["reason"] = f"{type(exc).__name__}:{exc}"[:500]
            if receipt["switched"] and not receipt["rolled_back"]:
                receipt.update(self.guarded_rollback(previous_plist, receipt))
            elif str(exc).startswith(("SOURCE_TREE_WRITTEN", "CORE_PIN_INVALID")):
                receipt["outcome"] = "REJECTED_BUILD"
            elif str(exc).startswith("MANAGER_LOCK_UNAVAILABLE"):
                receipt["outcome"] = "BLOCKED_MANAGER_BUSY"
            else:
                receipt["outcome"] = "BUILD_FAILED"
                if str(exc).startswith(("CORE_IN_USE_UNHEALTHY", "CORE_IN_USE_UNKNOWN")):
                    # A running deployment's Core is never touched; stop retrying
                    # until the Owner repairs it and runs `release`.
                    hold = f"auto-hold: {str(exc)[:200]} (core checkout in use)"
        return self.close_receipt(receipt, hold=hold)

    def spare_probe(
        self, root: Path, python: Path, commit: str, receipt: Dict[str, Any]
    ) -> Dict[str, Any]:
        cfg, host = self.cfg, self.host
        probe_state = cfg.probe_state_root / receipt["attempt_id"]
        shutil.rmtree(probe_state, ignore_errors=True)
        probe_state.mkdir(parents=True)
        port = host.free_port()
        core = receipt.get("core")
        core_root = Path(core["root"]) if isinstance(core, dict) else None
        command = wrapper_command(
            cfg,
            root,
            python,
            port,
            state_dir=probe_state,
            core_root=core_root,
            controller_root=_receipt_controller(receipt),
            core_digest=_core_digest_arg(core),
            rie=_rie_arg(receipt),
        )
        stop = host.start(command, cfg.state_dir / "logs" / f"{receipt['attempt_id']}.probe.log")
        try:
            result = self.prober.probe(
                port=port,
                token=read_env_token(cfg.env_file),
                commit=commit,
                root=root,
                python=python,
                timeout=cfg.probe_timeout_seconds,
                core=core if isinstance(core, dict) else {},
            )
        finally:
            stop()
            shutil.rmtree(probe_state, ignore_errors=True)
        return {"port": port, "state_dir": str(probe_state), **result}

    def attempt_effects(
        self, candidate: str, previous_plist: bytes, receipt: Dict[str, Any]
    ) -> Dict[str, Any]:
        cfg, host = self.cfg, self.host
        built = build(cfg, host, candidate)
        receipt.update(built)
        root, python = Path(built["deployment_root"]), Path(built["venv_python"])
        receipt["controller"] = self.prepare_controller(root, python, candidate, previous_plist)
        carry = receipt["controller"].get("carry") or {}
        if carry.get("lost"):
            receipt.setdefault("warnings", []).append(
                "BOUND_CARDS_NOT_CARRIED:"
                + str(
                    carry.get("reason")
                    or "MAIN_CHANGED:" + ",".join(carry.get("skipped_main_changed") or [])
                )[:300]
            )

        spare = self.spare_probe(root, python, candidate, receipt)
        receipt["probes"]["spare"] = spare
        if not spare["ok"]:
            return {"outcome": "REJECTED_PROBE", "reason": "candidate failed the spare-port probe"}

        readiness = rollback_readiness(host, previous_plist)
        receipt["rollback_readiness"] = readiness
        if not readiness["ok"]:
            return {"outcome": "BLOCKED_NO_ROLLBACK", "reason": readiness["reason"]}

        with host.manager_lock(cfg):
            # Last gates before the only live effect.
            held = hold_reason(cfg, self.environ)
            if held:
                return {"outcome": "HELD", "reason": f"hold set during the cycle ({held})"}
            pins = self.pin_bumps(record=True)
            receipt["pin_bumps_before_switch"] = pins
            for warning in pins.get("warnings", []):
                if warning not in receipt["warnings"]:
                    receipt["warnings"].append(warning)
            if pins["verdict"] != "CLEAR":
                return {
                    "outcome": f"PIN_BUMP_{pins['verdict']}",
                    "reason": "pin bump before switch",
                }
            quiet = self.host.tasks_in_flight(cfg, previous_plist)
            receipt["quiescence_before_switch"] = quiet
            if quiet.get("verdict") != "CLEAR":
                if not self.allow_in_flight:
                    return {
                        "outcome": DEFERRED_OUTCOME,
                        "reason": "governed tasks in flight before switch",
                    }
                receipt["quiescence_overridden"] = True
            # The R1 ledger lock is held from the R1 check through journal, plist
            # write, reload, live probe and any rollback: R1 cannot open mid-effect.
            with host.r1_guard(cfg):
                block = host.r1_recovery_block(cfg)
                if block is not None:
                    # Checked before the plist comparison: a plist an open R1
                    # recovery wrote is R1's, not a foreign rebind.
                    return {"outcome": "BLOCKED_MANAGER_BUSY", "reason": block}
                if cfg.plist.read_bytes() != previous_plist:
                    _set_hold(cfg, "auto-hold: FOREIGN_PLIST; live plist changed during the cycle")
                    return {
                        "outcome": "FOREIGN_PLIST",
                        "reason": "live plist changed during the cycle",
                    }
                moved = self.live_controller_moved(previous_plist, receipt)
                if moved is not None:
                    # A card was bound after the carry: rebuild and carry again.
                    return {"outcome": CONTROLLER_MOVED_OUTCOME, "reason": moved}

                command = wrapper_command(
                    cfg,
                    root,
                    python,
                    core_root=Path(receipt["core"]["root"]),
                    controller_root=_receipt_controller(receipt),
                    core_digest=_core_digest_arg(receipt["core"]),
                    rie=_rie_arg(receipt),
                )
                new_plist = render_plist(previous_plist, command, root)
                self.write_journal(receipt, previous_plist, new_plist, python)
                _atomic_write(cfg.plist, new_plist)
                receipt["switched"] = True
                result = self.finish_switch(receipt, previous_plist, root, python)
                if result.get("outcome") == "DEPLOYED":
                    # A bind the old Gateway committed between the check above and
                    # its bootout is in neither Controller's new HEAD: say so loudly.
                    late = self.live_controller_moved(previous_plist, receipt)
                    if late is not None:
                        receipt["warnings"].append(f"LATE_BIND_NOT_CARRIED:{late}")
                        try:
                            self.retain_controller(receipt, late)
                        except Exception as exc:  # noqa: BLE001 - never roll back a good deploy
                            receipt["warnings"].append(
                                f"RETAIN_CONTROLLER_FAILED:{type(exc).__name__}:{exc}"[:300]
                            )
                            # HOLD stops every later cycle (and so every prune) until
                            # the Owner recovers the late bind and runs `release`.
                            _set_hold(cfg, f"auto-hold: RETAIN_CONTROLLER_FAILED ({late})"[:300])
                return result

    def prepare_controller(
        self, root: Path, python: Path, candidate: str, previous_plist: bytes
    ) -> Dict[str, Any]:
        """Fresh Controller + carried binds, accepted by the candidate's own check (#1939).

        A carry the candidate refuses falls back to a fresh Controller without
        it; a fresh Controller the candidate refuses fails the build.
        """
        cfg, host = self.cfg, self.host
        controller = materialize_controller(cfg, host, candidate)
        carry = carry_bound_cards(host, previous_plist, controller, candidate)
        problem = host.controller_problem(python, root, controller)
        if problem is not None and carry.get("status") == "CARRIED":
            carry = {
                **carry,
                "status": "DROPPED",
                "reason": f"CANDIDATE_REFUSED_CARRY:{problem}",
                "lost": True,
            }
            controller = materialize_controller(cfg, host, candidate)
            problem = host.controller_problem(python, root, controller)
        if problem is not None:
            raise DeployError(f"CONTROLLER_INVALID:{problem}")
        return {"root": str(controller), "carry": carry}

    def live_controller_moved(
        self, previous_plist: bytes, receipt: Dict[str, Any]
    ) -> Optional[str]:
        """Why the carry source is no longer the head the carry read, else None."""
        carry = (receipt.get("controller") or {}).get("carry") or {}
        source, from_head = carry.get("from"), carry.get("from_head")
        if not source or not from_head:
            return None  # nothing was (or could be) read from a live Controller
        head = self.host.run(_ctl(Path(source), "rev-parse", "--verify", "HEAD^{commit}"))
        now = head.stdout.strip() if head.returncode == 0 else "UNREADABLE"
        if now == from_head:
            return None
        return f"LIVE_CONTROLLER_MOVED:{from_head[:12]}->{now[:12]}"

    def retain_controller(self, receipt: Dict[str, Any], reason: str) -> None:
        """Keep the old Controller (the only copy of a late bind) out of pruning."""
        source = ((receipt.get("controller") or {}).get("carry") or {}).get("from")
        if not source:
            return
        if self.cfg.retained_controllers.exists():
            retained = _read_json_object(self.cfg.retained_controllers)
            if retained is None:
                # Never overwrite a list we cannot read; prune refuses meanwhile.
                raise DeployError("RETAINED_CONTROLLERS_UNREADABLE")
        else:
            retained = {}
        retained[Path(source).name] = {"reason": reason[:200], "at": _iso(self.host.now())}
        self.cfg.state_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(
            self.cfg.retained_controllers, json.dumps(retained, sort_keys=True).encode(), 0o600
        )

    def finish_switch(
        self, receipt: Dict[str, Any], previous_plist: bytes, root: Path, python: Path
    ) -> Dict[str, Any]:
        try:
            self.host.reload_service(self.cfg.plist, GATEWAY_LABEL)
            # A receipt without a Core pin (e.g. an older journal) fails closed.
            core = receipt.get("core") if isinstance(receipt.get("core"), dict) else {}
            live = self.live_probe(receipt["candidate_commit"], root, python, core=core)
        except Exception as exc:  # noqa: BLE001 - reload/probe trouble is a failed probe
            live = {"ok": False, "error": f"{type(exc).__name__}:{exc}"[:300]}
        receipt["probes"]["live"] = live
        if live.get("ok"):
            receipt["deployer_link"] = self.move_tool_link(root)
            # Informational only (#2345): never changes the outcome or rolls back.
            self.record_worker_route_preflight(receipt)
            return {"outcome": "DEPLOYED"}
        receipt["reason"] = "candidate failed the live probe"
        return self.guarded_rollback(previous_plist, receipt)

    def record_worker_route_preflight(self, receipt: Dict[str, Any]) -> None:
        """Copy the live ``/health`` ``worker_route_preflight`` into the receipt (#2345).

        A BLOCKED route is policy (e.g. a missing authorization flag), not
        health: it adds one ``WORKER_ROUTE_PREFLIGHT_BLOCKED <route>:<reason>``
        warning per blocked route and nothing else.  Never raises.
        """
        summary: Dict[str, Any]
        try:
            health = self.prober.live_health()
            summary = worker_route_preflight_summary(health)
        except Exception as exc:  # noqa: BLE001 - visibility only, never a deploy failure
            summary = {
                "status": "UNAVAILABLE",
                "reason": f"HEALTH_UNREADABLE:{type(exc).__name__}"[:200],
            }
        receipt["worker_route_preflight"] = summary
        warnings = receipt.setdefault("warnings", [])
        if summary.get("status") == "BLOCKED":
            for route in summary.get("routes") or []:
                if route.get("preflight") == "BLOCKED":
                    warnings.append(
                        "WORKER_ROUTE_PREFLIGHT_BLOCKED "
                        f"{route.get('route')}:{route.get('reason')}"[:300]
                    )

    def live_probe(
        self, commit: str, root: Path, python: Path, *, core: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """``core`` is set for a candidate; the rollback probe of the predecessor omits it."""
        return self.prober.probe(
            port=LIVE_PORT,
            token=read_env_token(self.cfg.env_file),
            commit=commit,
            root=root,
            python=python,
            timeout=self.cfg.probe_timeout_seconds,
            core=core,
        )

    def write_journal(
        self, receipt: Dict[str, Any], previous_plist: bytes, new_plist: bytes, python: Path
    ) -> None:
        remember_plist(self.cfg, new_plist)
        journal = {
            "schema": JOURNAL_SCHEMA,
            "receipt": receipt,
            "previous_plist_b64": base64.b64encode(previous_plist).decode("ascii"),
            "new_plist_sha256": _sha256(new_plist),
            "candidate_python": str(python),
        }
        _atomic_write(self.cfg.journal, json.dumps(journal, sort_keys=True).encode(), 0o600)

    def guarded_rollback(self, previous_plist: bytes, receipt: Dict[str, Any]) -> Dict[str, Any]:
        """Roll back only while holding the R1 ledger lock with no open R1 request.

        Otherwise the rollback is postponed: the journal is kept (no HOLD) and the
        next cycle reconciles it once R1 is done.
        """
        try:
            with self.host.r1_guard(self.cfg):
                block = self.host.r1_recovery_block(self.cfg)
                if block is None:
                    return self.rollback(previous_plist, receipt)
        except DeployError as exc:
            block = str(exc)
        receipt["journal_kept"] = True
        return {"outcome": "BLOCKED_MANAGER_BUSY", "reason": f"rollback postponed: {block}"[:300]}

    def postpone(self, receipt: Dict[str, Any], reason: str) -> Dict[str, Any]:
        """Record a postponed reconciliation; the journal stays for the next cycle."""
        receipt.update(outcome="BLOCKED_MANAGER_BUSY", reason=str(reason)[:300], journal_kept=True)
        return self.close_receipt(receipt)

    def rollback(self, previous_plist: bytes, receipt: Dict[str, Any]) -> Dict[str, Any]:
        """Restore the exact previous plist bytes, reload, and re-probe the previous deployment."""
        receipt["rolled_back"] = True
        previous_root = live_root(previous_plist)
        previous_commit = commit_of(previous_root)
        previous_python = live_python(previous_plist)
        try:
            remember_plist(self.cfg, previous_plist)
            _atomic_write(self.cfg.plist, previous_plist)
            self.host.reload_service(self.cfg.plist, GATEWAY_LABEL)
            if previous_commit and previous_root and previous_python:
                restored = self.live_probe(previous_commit, previous_root, previous_python)
            else:
                restored = {
                    "ok": False,
                    "error": "previous identity unknown; restored plist bytes only",
                }
        except Exception as exc:  # noqa: BLE001
            restored = {"ok": False, "error": f"{type(exc).__name__}:{exc}"[:300]}
        receipt["probes"]["rollback"] = restored
        return {"outcome": "ROLLED_BACK" if restored["ok"] else "ROLLBACK_FAILED"}

    def reconcile_journal(self) -> Dict[str, Any]:
        """Resolve a switch that a previous cycle did not finish (crash or kill)."""
        cfg = self.cfg
        try:
            loaded = _load_journal(cfg.journal)
        except Exception as exc:  # noqa: BLE001 - any decode/shape error quarantines
            return self.quarantine_journal(f"{type(exc).__name__}:{exc}"[:300])
        receipt, previous_plist, root, python, new_plist_sha = loaded
        receipt.update(reconciled=True, switched=True)
        hold: Optional[str] = None
        try:
            with self.host.manager_lock(cfg), self.host.r1_guard(cfg):
                # R1 first: while a #526 R1 recovery is open it owns the Gateway,
                # so no reload, no plist write and no FOREIGN verdict (R1 may have
                # written that plist).  Only a read-only finalize of an already
                # healthy live candidate proceeds; everything else is postponed
                # with the journal kept and no HOLD.
                block = self.host.r1_recovery_block(cfg)
                if block is not None:
                    # Recorded before anything else can fail, so a later error
                    # still postpones instead of writing HOLD (#2169 F1).
                    receipt["r1_block_observed"] = block
                live_plist = cfg.plist.read_bytes()
                is_candidate = _sha256(live_plist) == new_plist_sha
                if block is not None:
                    if not is_candidate:
                        return self.postpone(receipt, block)
                    core = receipt.get("core") if isinstance(receipt.get("core"), dict) else {}
                    try:
                        live = self.live_probe(receipt["candidate_commit"], root, python, core=core)
                    except Exception as exc:  # noqa: BLE001 - probe trouble is not corruption
                        live = {"ok": False, "error": f"{type(exc).__name__}:{exc}"[:300]}
                    receipt["probes"]["live"] = live
                    if not live.get("ok"):
                        return self.postpone(receipt, block)
                    receipt["deployer_link"] = self.move_tool_link(root)
                    receipt["outcome"] = "DEPLOYED"
                elif is_candidate:
                    # The switch got as far as the plist write; make sure launchd
                    # runs it, keep it if it passes, otherwise roll back.
                    receipt.update(self.finish_switch(receipt, previous_plist, root, python))
                elif live_plist == previous_plist:
                    # Equal bytes do not prove launchd runs them (the crash may
                    # have hit the rollback reload): reload and probe them.
                    receipt["reason"] = "interrupted switch; previous plist re-verified"
                    receipt.update(self.guarded_rollback(previous_plist, receipt))
                else:
                    hold = "auto-hold: FOREIGN_PLIST while reconciling a pending switch"
                    receipt.update(outcome="FOREIGN_PLIST", reason="unexpected live plist")
        except DeployError as exc:
            if str(exc).startswith("MANAGER_LOCK_UNAVAILABLE"):
                # The #526 manager or its ledger is busy: keep the journal, retry.
                return self.postpone(receipt, str(exc))
            # A validated journal is never quarantined, whatever the error (#2169 F3).
            return self.reconcile_failed(receipt, exc)
        except Exception as exc:  # noqa: BLE001 - never crash every cycle on one journal
            return self.reconcile_failed(receipt, exc)
        return self.close_receipt(receipt, hold=hold)

    def reconcile_failed(self, receipt: Dict[str, Any], exc: BaseException) -> Dict[str, Any]:
        """A validated journal whose reconciliation failed: kept, never quarantined.

        Normally HOLD stops the retry loop until the Owner has looked at it.
        While an R1 recovery was seen open, R1 owns the Gateway, so no HOLD is
        written: the journal is kept and the next cycle retries (#2169 F1).  If
        even that receipt cannot be written, the error propagates and the
        journal stays, as for every receipt failure.
        """
        reason = f"RECONCILE_FAILED:{type(exc).__name__}:{exc}"[:300]
        if receipt.get("r1_block_observed"):
            return self.postpone(receipt, reason)
        receipt.update(outcome="RECONCILE_FAILED", reason=reason, journal_kept=True)
        return self.close_receipt(
            receipt,
            hold=f"{RECONCILE_FAILED_HOLD} {receipt.get('attempt_id')}; journal kept",
        )

    def quarantine_journal(self, reason: str) -> Dict[str, Any]:
        """An unusable journal: HOLD, then a receipt, then move it aside."""
        cfg = self.cfg
        started = self.host.now()
        aside = cfg.journal.with_name(f"pending-switch.corrupt.{int(started)}.json")
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "attempt_id": f"journal-{int(started)}",
            "outcome": "JOURNAL_CORRUPT",
            "reason": reason,
            "journal_moved_to": str(aside),
            "started_at": _iso(started),
            "started_epoch": started,
            "switched": False,
            "rolled_back": False,
            "probes": {},
        }
        return self.close_receipt(
            receipt,
            hold=f"auto-hold: JOURNAL_CORRUPT (moved to {aside.name}); inspect the Gateway",
            journal_to=aside,
        )

    def move_tool_link(self, root: Path) -> Dict[str, Any]:
        """Self-update; never fails the deploy (an error just keeps the old link)."""
        try:
            return self._move_tool_link(root)
        except Exception as exc:  # noqa: BLE001
            return {"moved": False, "reason": f"{type(exc).__name__}:{exc}"[:300]}

    def _move_tool_link(self, root: Path) -> Dict[str, Any]:
        """Self-update: point the LaunchAgent at the new tree only if its deployer works."""
        cfg = self.cfg
        deployer = root / DEPLOYER
        env = {
            "PYTHONDONTWRITEBYTECODE": "1",
            "NEXUS_GATEWAY_PLIST": str(cfg.plist),
        }
        # The planning path runs against a scratch state dir with an offline gh
        # stub and no fetch, so it parses the LaunchAgent's `run` CLI and reads
        # the live plist/bare repo without any effect.
        scratch = cfg.state_dir / "selftest-state"
        shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir(parents=True)
        if cfg.known_plists.exists():
            shutil.copy2(cfg.known_plists, scratch / cfg.known_plists.name)
        offline_gh = scratch / "gh-offline"
        offline_gh.write_text("#!/bin/sh\necho 'offline gh stub' >&2\nexit 1\n", encoding="utf-8")
        offline_gh.chmod(0o755)
        base = [str(self.tool_python), str(deployer)]
        checks = (
            ("selftest", [*base, "selftest", "--state-dir", str(cfg.state_dir)]),
            ("status", [*base, "status", "--state-dir", str(cfg.state_dir)]),
            (
                "run --dry-run",
                [
                    *base,
                    "run",
                    "--dry-run",
                    "--no-fetch",
                    "--gh",
                    str(offline_gh),
                    "--state-dir",
                    str(scratch),
                    "--gateway-root",
                    str(cfg.gateway_root),
                    "--plist",
                    str(cfg.plist),
                ],
            ),
        )
        try:
            for name, argv in checks:
                result = self.host.run(argv, env=env, timeout=120)
                detail = (result.stderr or result.stdout or "").strip()[-300:]
                if result.returncode != 0:
                    return {"moved": False, "reason": f"{name} failed: {detail}"}
                if name == "run --dry-run":
                    planned = json.loads(result.stdout or "{}").get("status")
                    if planned in (None, "ERROR"):
                        return {"moved": False, "reason": f"{name} failed: {detail}"}
        except ValueError as exc:
            return {"moved": False, "reason": f"run --dry-run output unreadable: {exc}"}
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        _atomic_symlink(root, cfg.tool_link)
        return {"moved": True, "target": str(root)}


_JOURNAL_RECEIPT_FIELDS = {
    "schema": str,
    "attempt_id": str,
    "candidate_commit": str,
    "deployment_root": str,
    "started_epoch": (int, float),
    "started_at": str,
    "switched": bool,
    "rolled_back": bool,
    "probes": dict,
}


def _load_journal(path: Path) -> tuple:
    """Parse and fully validate a pending-switch journal (every field reconcile reads)."""
    journal = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(journal, dict) or journal.get("schema") != JOURNAL_SCHEMA:
        raise ValueError("journal schema")
    receipt = journal.get("receipt")
    if not isinstance(receipt, dict):
        raise ValueError("journal receipt")
    for name, kind in _JOURNAL_RECEIPT_FIELDS.items():
        if not isinstance(receipt.get(name), kind):
            raise ValueError(f"journal receipt.{name}")
    if receipt["schema"] != RECEIPT_SCHEMA or not _SHA.match(receipt["candidate_commit"]):
        raise ValueError("journal receipt identity")
    for name in ("previous_plist_b64", "candidate_python", "new_plist_sha256"):
        if not isinstance(journal.get(name), str) or not journal[name]:
            raise ValueError(f"journal {name}")
    if not re.fullmatch(r"[0-9a-f]{64}", journal["new_plist_sha256"]):
        raise ValueError("journal new_plist_sha256")
    previous_plist = base64.b64decode(journal["previous_plist_b64"], validate=True)
    _load_gateway_plist(previous_plist)  # a dict with the Gateway label and argv
    return (
        dict(receipt),
        previous_plist,
        Path(receipt["deployment_root"]),
        Path(journal["candidate_python"]),
        journal["new_plist_sha256"],
    )


def rollback_readiness(host: Host, previous_plist: bytes) -> Dict[str, Any]:
    """Refuse to switch unless the predecessor deployment could be restarted and re-probed."""
    root = live_root(previous_plist)
    python = live_python(previous_plist)
    if not commit_of(root):
        return {"ok": False, "reason": "PREDECESSOR_COMMIT_UNKNOWN"}
    if root is None or not (root / ENTRYPOINT).is_file():
        return {"ok": False, "reason": "PREDECESSOR_DEPLOYMENT_MISSING"}
    if python is None or not python.exists():
        return {"ok": False, "reason": "PREDECESSOR_PYTHON_MISSING"}
    controller = live_controller(previous_plist)
    if controller is not None:
        if not (controller / ".git").exists():
            return {"ok": False, "reason": "PREDECESSOR_CONTROLLER_MISSING"}
        # The predecessor's own startup rule must still accept its Controller,
        # or a rollback would restart a Gateway that refuses to start.
        problem = host.controller_problem(python, root, controller)
        if problem is not None:
            return {"ok": False, "reason": f"PREDECESSOR_CONTROLLER_INVALID:{problem}"}
    result = host.run([str(python), "-c", "import sys"], timeout=60)
    if result.returncode != 0:
        return {"ok": False, "reason": "PREDECESSOR_PYTHON_NOT_RUNNABLE"}
    return {"ok": True, "root": str(root), "python": str(python)}


def verify_commit(
    api_get: Callable[[str], Any], sha: str, *, repo: str = REPOSITORY
) -> Dict[str, Any]:
    """Installer gate: the bootstrap commit must be on GitHub main with green checks."""
    main_check = on_github_main(api_get, sha, repo=repo)
    checks = required_checks(api_get, sha, repo=repo) if main_check["ok"] else None
    ok = bool(main_check["ok"] and checks and checks["verdict"] == "GREEN")
    return {"ok": ok, "commit": sha, "github_main": main_check, "required_checks": checks}


# ---------------------------------------------------------------------------- cli


def _park_seconds_arg(value: str) -> int:
    seconds = _park_seconds_or_none(value)
    if seconds is None:
        raise argparse.ArgumentTypeError(
            f"must be a whole number of seconds >= {PIN_BUMP_PARK_MIN_SECONDS}"
        )
    return seconds


def main(
    argv: Optional[List[str]] = None,
    *,
    host: Optional[Host] = None,
    prober: Optional[Prober] = None,
    api_get: Optional[Callable[[str], Any]] = None,
) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "command",
        choices=("run", "status", "hold", "release", "adopt", "selftest", "verify-commit"),
    )
    parser.add_argument("commit", nargs="?", help="verify-commit: the commit to verify")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan; no build, launchd or prune"
    )
    parser.add_argument(
        "--force", action="store_true", help="ignore debounce, relevance and earlier rejection"
    )
    parser.add_argument(
        "--reason", default="manual hold", help="hold: reason written to the HOLD file"
    )
    parser.add_argument("--home", type=Path, default=None)
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--gateway-root", type=Path, default=None)
    parser.add_argument("--plist", type=Path, default=None)
    parser.add_argument("--gh", default="gh", help="gh executable used for the GitHub API")
    parser.add_argument("--keep", type=int, default=None)
    parser.add_argument("--min-interval", type=int, default=None, dest="min_interval_seconds")
    parser.add_argument("--max-irrelevant-lag", type=int, default=None)
    parser.add_argument("--python-version", default=None)
    parser.add_argument(
        "--pin-bump-park-seconds",
        type=_park_seconds_arg,
        default=None,
        help=f"seconds a pin-bump PR may hold deploys at one head before it is parked "
        f"(#2309; default {PIN_BUMP_PARK_SECONDS}, or ${PIN_BUMP_PARK_ENV}; "
        f"minimum {PIN_BUMP_PARK_MIN_SECONDS})",
    )
    parser.add_argument(
        "--allow-in-flight",
        action="store_true",
        help="run, by hand only: switch even while governed tasks are in flight (#2227); "
        "the LaunchAgent never passes it",
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="run --dry-run only: use the already fetched main (self-update check)",
    )
    parser.add_argument(
        "--adopt-if-unrecorded",
        action="store_true",
        help="adopt: only when nothing is recorded yet (first install); refuse an unknown plist",
    )
    parser.add_argument(
        "--uv-extras", default=None, help='"all" (default) or a comma list such as "legacy"'
    )
    args = parser.parse_args(argv)
    cfg = Config.default(
        args.home,
        state_dir=args.state_dir,
        gateway_root=args.gateway_root,
        plist=args.plist,
        keep=args.keep,
        min_interval_seconds=args.min_interval_seconds,
        max_irrelevant_lag=args.max_irrelevant_lag,
        python_version=args.python_version,
        uv_extras=args.uv_extras,
        gh=args.gh,
        pin_bump_park_seconds=args.pin_bump_park_seconds,
    )
    if args.command == "hold":
        _set_hold(cfg, args.reason)
        print(json.dumps({"status": "HELD", "hold": str(cfg.hold_file)}))
        return 0
    if args.command == "release":
        with contextlib.suppress(FileNotFoundError):
            cfg.hold_file.unlink()
        print(json.dumps({"status": "RELEASED"}))
        return 0
    if args.command == "adopt":
        data = cfg.plist.read_bytes()
        live_root(data)  # label check
        known = known_plist_hashes(cfg)
        if args.adopt_if_unrecorded and known and _sha256(data) not in known:
            print(
                json.dumps({
                    "status": "REFUSED",
                    "reason": "live Gateway plist differs from every plist the deployer wrote "
                    "or adopted (manual rebind?); re-run the installer with --adopt to accept it",
                    "plist_sha256": _sha256(data),
                })
            )
            return 3
        remember_plist(cfg, data)
        print(json.dumps({"status": "ADOPTED", "plist_sha256": _sha256(data)}))
        return 0
    if args.command == "selftest":
        # Proves this tree's deployer can reach the single launchd effect owner.
        from scripts.ops.mcp_gateway_durable import reload_gateway_launch_agent

        print(json.dumps({"status": "OK", "reload": reload_gateway_launch_agent.__name__}))
        return 0
    if args.command == "status":
        state = cfg.state_dir / "status.json"
        print(
            json.dumps(
                {
                    "hold": hold_reason(cfg),
                    "pending_switch": cfg.journal.exists(),
                    "warnings": (
                        json.loads(state.read_text(encoding="utf-8")).get("warnings", [])
                        if state.is_file()
                        else []
                    ),
                    "status": json.loads(state.read_text(encoding="utf-8"))
                    if state.is_file()
                    else None,
                    "last_receipt": last_receipt(cfg.state_dir),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    host = host or Host()
    if args.command == "verify-commit":
        if not args.commit or not _SHA.match(args.commit):
            print(json.dumps({"ok": False, "error": "commit must be a 40-hex sha"}))
            return 2
        verdict = verify_commit(api_get or gh_api_getter(host, args.gh), args.commit)
        print(json.dumps(verdict, sort_keys=True))
        return 0 if verdict["ok"] else 1
    if not args.dry_run and os.environ.get(TOKEN_ENV):
        # The Gateway wrapper sources the token; a deploy started from inside the
        # Gateway would kill itself mid-switch.  Run it out of process only.
        print(
            json.dumps({"schema": STATUS_SCHEMA, "status": "ERROR", "error": "IN_GATEWAY_PROCESS"})
        )
        return 2
    try:
        result = run_cycle(
            cfg,
            host,
            prober or Prober(host),
            api_get or gh_api_getter(host, args.gh),
            dry_run=args.dry_run,
            force=args.force,
            fetch=not (args.dry_run and args.no_fetch),
            allow_in_flight=args.allow_in_flight,
        )
    except (DeployError, OSError, ValueError) as exc:
        error = {
            "schema": STATUS_SCHEMA,
            "status": "ERROR",
            "error": str(exc)[:500],
            "polled_at": _iso(time.time()),
        }
        if not args.dry_run:
            with contextlib.suppress(OSError):
                _write_status(cfg, error)
        print(json.dumps(error))
        return 2
    print(json.dumps(result, indent=2 if args.dry_run else None, sort_keys=True))
    return 1 if result["status"] in FAILED_OUTCOMES else 0


if __name__ == "__main__":
    raise SystemExit(main())
