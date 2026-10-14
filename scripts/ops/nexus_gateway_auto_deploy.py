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
   durable state stays in ``~/.local/state`` (#1539).
3. Probe: start the candidate on a spare loopback port with a throwaway state
   dir (never the live self-hosted state) and require ``/health`` for the exact
   commit, the candidate's own GB-077 live identity probe, MCP ``tools/list``
   and ``nexus_gateway_status``.  On failure the live Gateway is left untouched.
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
passes ``selftest`` with the LaunchAgent's own interpreter.  It needs only the
stdlib plus the tree's ``scripts/ops/mcp_gateway_durable.py``, which stays the
single owner of the Gateway launchd effect.  The #526 governed rebind stays
available as a manual fallback.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import os
import plistlib
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

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
    "Trusted dependency contract (default branch)": (
        ".github/workflows/trusted-dependency-contract.yml"
    ),
}
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
# Open PRs that bump the runtime/dependency pin (or anchor such a bump).  While
# one is in flight no deploy starts, so deploys and pin bumps never interleave.
PIN_BUMP_PR = re.compile(
    r"auto/workforce-|pin nexus-runtime|pin-runtime|trusted-anchor|trusted runtime identity"
    r"|dependency.{0,20}transition",
    re.IGNORECASE,
)
PIN_FILES = ("uv.lock", "pyproject.toml", "requirements/canonical-runtime.txt")
PIN_BUMP_MAX_AGE_SECONDS = 3 * 24 * 60 * 60
_SHA = re.compile(r"^[0-9a-f]{40}$")
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


class DeployError(RuntimeError):
    pass


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


# --------------------------------------------------------------------------- host


class Host:
    """Every process, launchd and clock effect.  Tests replace this class."""

    def run(
        self,
        argv: List[str],
        *,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 1800,
    ) -> subprocess.CompletedProcess:
        full_env = dict(os.environ, **(env or {}))
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
            lock = durable.InterProcessLock(path, timeout=30.0)
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
            lock = durable.InterProcessLock(self.manager_lock_path(cfg), timeout=30.0)
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
            w.get("path") == REQUIRED_CHECKS[name] and _from_origin(run, w, sha, origin)
            for w in candidates
        ):
            bound.append(run)
    return bound


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
    detail: Dict[str, Any] = {}
    try:
        live = live_required_checks(api_get, repo=repo, branch=branch)
    except Exception as exc:  # noqa: BLE001 - an unreadable ruleset fails closed
        return {"verdict": "UNKNOWN", "error": f"RULESET:{type(exc).__name__}:{exc}"[:300]}
    unknown = [name for name in live if name not in REQUIRED_CHECKS]
    if unknown:
        return {"verdict": "UNKNOWN_REQUIRED_CHECK", "unknown_required": unknown, "checks": {}}
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


def _parse_time(value: Any) -> Optional[float]:
    try:
        return (
            datetime
            .strptime(str(value), "%Y-%m-%dT%H:%M:%SZ")
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
    except ValueError:
        return None


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
        # An event without a usable timestamp is ignored, never "recent forever".
        if when is not None and when > cutoff:
            return False
    return True


def _timeline_time(api_get: Callable[[str], Any], repo: str, event: dict) -> Optional[float]:
    """Timestamp of a push-like timeline event, from documented fields only."""
    kind = event.get("event")
    if kind in ("head_ref_force_pushed", "head_ref_restored"):
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


def pin_bumps_in_flight(
    api_get: Callable[[str], Any], *, repo: str = REPOSITORY, now: Optional[float] = None
) -> Dict[str, Any]:
    """Open pin-bump PRs; CLEAR, IN_FLIGHT or UNKNOWN (fail closed).

    A pin-bump PR that was created, last committed and last pushed more than
    ``PIN_BUMP_MAX_AGE_SECONDS`` ago is treated as abandoned and does not block, but it is never silent: it is
    listed in ``ignored_stale`` and as a ``STALE_PIN_PR_IGNORED #N`` warning.
    A draft pin-bump PR cannot merge, so it cannot race a deploy: it is listed in
    ``ignored_draft`` / ``DRAFT_PIN_PR_IGNORED #N`` instead of blocking.  The
    re-check right before the switch applies the same rule, so a draft marked
    ready mid-cycle blocks the switch.
    """
    now = time.time() if now is None else now
    hits: List[int] = []
    stale: List[int] = []
    drafts: List[int] = []
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
            elif _is_stale_pin_pr(api_get, repo, pr, now):
                stale.append(pr["number"])
            else:
                hits.append(pr["number"])
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "UNKNOWN", "error": f"{type(exc).__name__}:{exc}"[:300]}
    return {
        "verdict": "IN_FLIGHT" if hits else "CLEAR",
        "pull_requests": sorted(hits),
        "ignored_stale": sorted(stale),
        "ignored_draft": sorted(drafts),
        "warnings": [f"STALE_PIN_PR_IGNORED #{n}" for n in sorted(stale)]
        + [f"DRAFT_PIN_PR_IGNORED #{n}" for n in sorted(drafts)],
    }


# ------------------------------------------------------------------------- probes


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

    def core_provenance(self, *, root: Path, python: Path, core: Any) -> Dict[str, Any]:
        """The candidate's transport must resolve Core as CORE_REVISION_PINNED at ``core``."""
        if not isinstance(core, dict) or not _SHA.match(str(core.get("revision") or "")):
            return {"ok": False, "error": "CORE_PIN_UNKNOWN"}
        result = self.host.run(
            [str(python), "-c", CORE_PROVENANCE_PROBE_CODE, str(root)],
            cwd=root,
            env={"PYTHONDONTWRITEBYTECODE": "1", "NEXUS_CORE_REPO_ROOT": str(core["root"])},
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
        )
        keys = ("status", "reason", "expected_revision", "observed_commit", "source_root")
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
            checks["core_provenance"] = self.core_provenance(root=root, python=python, core=core)
        return {"ok": all(c["ok"] for c in checks.values()), "checks": checks}


# --------------------------------------------------------------------- deployment


def wrapper_command(
    cfg: Config,
    root: Path,
    python: Path,
    port: Optional[int] = None,
    state_dir: Optional[Path] = None,
    core_root: Optional[Path] = None,
) -> str:
    """The same fixed zsh wrapper as the #526 deployments, with a per-deployment venv.

    ``port``/``state_dir`` are only used for the spare-port probe, which must never
    see the live self-hosted state.  ``core_root`` (exported after the env file, so
    the env file cannot override it) is the deployment's pinned Core checkout.
    """
    state = cfg.canonical_state_dir if state_dir is None else state_dir
    values = [str(root), str(python), str(cfg.env_file), str(state)]
    if core_root is not None:
        values.append(str(core_root))
    for value in values:
        if any(token in value for token in _SHELL_UNSAFE):
            raise DeployError("WRAPPER_PATH_UNSAFE")
    port_export = "" if port is None else f"export NEXUS_MCP_GATEWAY_PORT={int(port)} ; "
    core_export = "" if core_root is None else f'export NEXUS_CORE_REPO_ROOT="{core_root}" ; '
    return (
        f'cd "{root}" ; source "{cfg.env_file}" ; export PYTHONDONTWRITEBYTECODE=1 ; '
        f'export NEXUS_CANONICAL_SOURCE_ROOT="{root}" ; '
        f'export NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR="{state}" ; '
        f'{core_export}{port_export}exec "{python}" "{root / ENTRYPOINT}"'
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
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp, mode)
    os.replace(tmp, path)


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
    # --ignored: an ignored file (say a stray .pyc) can still be imported.
    status = host.run([
        "git",
        "-C",
        str(checkout),
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--ignored",
    ])
    if status.returncode != 0:
        return "CORE_STATUS_FAILED"
    if status.stdout.strip():
        return "CORE_TREE_DIRTY"
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


def build(cfg: Config, host: Host, commit: str) -> Dict[str, Any]:
    """Materialize the immutable deployment and its dedicated venv."""
    root = cfg.deployments / f"{DEPLOYMENT_PREFIX}{commit}"
    venv = cfg.venvs / f"{DEPLOYMENT_PREFIX}{commit}"
    if not root.exists():
        _must(
            host, _git(cfg, "worktree", "add", "--detach", str(root), commit), "WORKTREE_ADD_FAILED"
        )
    head = _must(
        host, ["git", "-C", str(root), "rev-parse", "HEAD"], "WORKTREE_HEAD_FAILED"
    ).strip()
    if head != commit:
        raise DeployError(f"WORKTREE_HEAD_MISMATCH:{head}")
    core = materialize_core(cfg, host, read_core_pin(root))
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
    lock = root / "uv.lock"
    return {
        "deployment_root": str(root),
        "venv": str(venv),
        "venv_python": str(python),
        "uv_lock_sha256": _sha256(lock.read_bytes()) if lock.exists() else None,
        "core": core,
    }


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
    for path in (cfg.deployments, cfg.venvs, cfg.core_checkouts):
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
    for index, path in enumerate(candidates):
        if index < cfg.keep or path.name in keep_names:
            continue
        host.run(_git(cfg, "worktree", "remove", "--force", str(path)), timeout=300)
        if path.exists() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        removed.append(path.name)
    present = {p.name for p in cfg.deployments.iterdir()} if cfg.deployments.is_dir() else set()
    for venv in _contained_dirs(cfg.venvs):
        if venv.name not in present:
            shutil.rmtree(venv, ignore_errors=True)
    prune_core(cfg, host, protected)
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


def _set_hold(cfg: Config, reason: str) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.hold_file.write_text(reason + "\n", encoding="utf-8")


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
        stuck = (
            hold_reason(cfg, environ)
            and (last_receipt(cfg.state_dir) or {}).get("outcome") == "RECONCILE_FAILED"
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
            # No deploy and no HOLD: retried next cycle once this file knows the check.
            return finish("UNKNOWN_REQUIRED_CHECK:" + ",".join(checks["unknown_required"]))
        if checks["verdict"] != "GREEN":
            return finish(f"CHECKS_{checks['verdict']}")
        pins = pin_bumps_in_flight(self.api_get, repo=cfg.repository, now=host.now())
        status["pin_bumps"] = pins
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
        # Advisory early check (the authoritative one is under the lock right
        # before the plist write): no build or probe churn while R1 is open.
        block = host.r1_recovery_block(cfg)
        if block is not None:
            return finish("BLOCKED_MANAGER_BUSY", reason=block)
        receipt = self.attempt(candidate, previous_plist, checks, status.get("warnings", []))
        status["receipt"] = receipt
        return finish(receipt["outcome"])

    def backoff_remaining(self, failures: List[Dict[str, Any]]) -> float:
        receipts = read_receipts(self.cfg.state_dir)
        if not receipts:
            return 0.0
        interval = self.cfg.min_interval_seconds * (2 ** max(0, len(failures) - 1))
        interval = min(float(interval), float(MAX_BACKOFF_SECONDS))
        last_started = float(receipts[-1].get("started_epoch", 0))
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
        receipt["warnings"] = list(warnings)
        hold: Optional[str] = None
        try:
            receipt.update(self.attempt_effects(candidate, previous_plist, receipt))
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
            cfg, root, python, port, state_dir=probe_state, core_root=core_root
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
            pins = pin_bumps_in_flight(self.api_get, repo=cfg.repository, now=host.now())
            receipt["pin_bumps_before_switch"] = pins
            for warning in pins.get("warnings", []):
                if warning not in receipt["warnings"]:
                    receipt["warnings"].append(warning)
            if pins["verdict"] != "CLEAR":
                return {
                    "outcome": f"PIN_BUMP_{pins['verdict']}",
                    "reason": "pin bump before switch",
                }
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

                command = wrapper_command(
                    cfg, root, python, core_root=Path(receipt["core"]["root"])
                )
                new_plist = render_plist(previous_plist, command, root)
                self.write_journal(receipt, previous_plist, new_plist, python)
                _atomic_write(cfg.plist, new_plist)
                receipt["switched"] = True
                return self.finish_switch(receipt, previous_plist, root, python)

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
            return {"outcome": "DEPLOYED"}
        receipt["reason"] = "candidate failed the live probe"
        return self.guarded_rollback(previous_plist, receipt)

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
                live_plist = cfg.plist.read_bytes()
                is_candidate = _sha256(live_plist) == new_plist_sha
                if block is not None:
                    receipt["r1_block_observed"] = block
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
            if not str(exc).startswith("MANAGER_LOCK_UNAVAILABLE"):
                return self.quarantine_journal(f"RECONCILE_FAILED:DeployError:{exc}"[:300])
            # The #526 manager or its ledger is busy: keep the journal, retry.
            return self.postpone(receipt, str(exc))
        except Exception as exc:  # noqa: BLE001 - never crash every cycle on one journal
            # The journal passed validation, so it is kept (never quarantined):
            # HOLD stops the retry loop until the Owner has looked at it.
            receipt.update(
                outcome="RECONCILE_FAILED",
                reason=f"RECONCILE_FAILED:{type(exc).__name__}:{exc}"[:300],
                journal_kept=True,
            )
            return self.close_receipt(
                receipt,
                hold=f"auto-hold: RECONCILE_FAILED {receipt.get('attempt_id')}; journal kept",
            )
        return self.close_receipt(receipt, hold=hold)

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
