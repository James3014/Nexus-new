"""NEXUS arm driver: P1 ``nexus_worker_candidate`` on a measurement Gateway.

Per (task, repeat), strictly one at a time (a Controller allows one active
task lease per controller worktree):

  /health -> tools/list -> nexus_task_card_create -> nexus_task_card_commit
  -> nexus_worker_candidate (-> nexus_model_probe once if the Gateway asks)
  -> nexus_task_wait until the task leaves IN_PROGRESS -> nexus_task_status
  -> collect candidate diff + capability_observations + tokens
  -> nexus_task_cancel (always, so the instance is never left with a task in flight)

Safety rails:
* The live Gateway port 8766 is refused outright, whatever the host.
* The bearer token is read from a file and redacted from everything saved.
* An external task (any repo other than Nexus-new) needs the Gateway to
  advertise ``external_target`` on ``nexus_worker_candidate`` (the bounded
  change proposed in #2721 Phase A).  Until then the row is
  ``BLOCKED_EXTERNAL_TARGET_UNSUPPORTED`` and **no** card is created.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from nexus.executors.claude_measurement_worker import CLAUDE_MEASUREMENT_MODEL
from scripts.bench.measure_2721 import blind, controller_guard, state_phase
from scripts.bench.measure_2721.arms import (
    ARM_NEXUS,
    FLAG_NON_MODEL_SOLVE,
    FLAG_SECRET_IN_DIFF,
    ROW_SCHEMA,
    candidate_facts,
    claude_status,
    expected_cli_timeout,
    input_capture,
    new_run_id,
    non_model_solve,
    outcome_flags,
    redact_diff,
    task_prompt,
    venv_problem,
)
from scripts.bench.measure_2721.common import (
    INFRA_ERROR_MARKERS,
    append_jsonl,
    git,
    write_diff,
    write_json,
)
from scripts.bench.measure_2721.gateway_env import measurement_env, read_roots_sha256
from scripts.bench.measure_2721.leakage import FLAG_NETWORK_ATTEMPT, lookup_signals
from scripts.bench.measure_2721.portable import to_portable_row

LIVE_GATEWAY_PORT = 8766
NEXUS_REPO = "James3014/Nexus-new"
EXTERNAL_TARGET_FIELD = "external_target"
OUTCOME_BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL_TARGET_UNSUPPORTED"
OUTCOME_GATEWAY_ERROR = "GATEWAY_ERROR"
OUTCOME_INFRA = "INFRA"
OUTCOME_DONE = "OK"
_INFRA_MARKERS = INFRA_ERROR_MARKERS
CANCEL_RETRY_STATUSES = frozenset({"PENDING_HUMAN_APPROVAL"})
CANCEL_REFUSED_MARKERS = ("CANDIDATE_REF_PROTECTED", "PENDING_HUMAN_APPROVAL")


def _cancel_refused(payload: Any) -> bool:
    text = json.dumps(payload, default=str)
    return any(marker in text for marker in CANCEL_REFUSED_MARKERS)


from scripts.bench.measure_2721.state_phase import TERMINAL_STATUSES  # noqa: E402


class GatewayStuck(RuntimeError):
    """The previous task did not reach a terminal state: stop the batch (infra)."""


class LiveGatewayRefused(RuntimeError):
    pass


class GatewayToolError(RuntimeError):
    def __init__(self, tool: str, payload: Any):
        super().__init__(f"{tool}: {json.dumps(payload)[:500]}")
        self.tool = tool
        self.payload = payload


def refuse_live(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"gateway url must be http(s)://host:port: {url!r}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port == LIVE_GATEWAY_PORT:
        raise LiveGatewayRefused("the live Gateway (:8766) is never a measurement target")
    return url.rstrip("/")


def read_token(path: Path | str) -> str:
    path = Path(path).expanduser()
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise PermissionError(f"token file must not be group/world readable ({oct(mode)})")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*(?:export\s+)?NEXUS_MCP_GATEWAY_TOKEN=(.*)$", line)
        if match:
            return match.group(1).strip().strip("'\"")
    token = path.read_text(encoding="utf-8").strip()
    if not token or "\n" in token:
        raise ValueError("token file holds no token")
    return token


Transport = Callable[[str, str, Optional[dict[str, Any]]], dict[str, Any]]


class GatewayClient:
    def __init__(self, url: str, token: str, transport: Optional[Transport] = None, timeout: float = 120.0):
        self.url = refuse_live(url)
        self._token = token
        self._timeout = timeout
        self._transport = transport or self._http
        self._next_id = 0

    def redact(self, value: Any) -> Any:
        text = json.dumps(value, ensure_ascii=False)
        if self._token:
            text = text.replace(self._token, "<redacted>")
        return json.loads(text)

    def _http(self, method: str, path: str, body: Optional[dict[str, Any]]) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            self.url + path, data=data, method=method,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._token}"},
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310 (fixed scheme)
            return json.loads(response.read().decode("utf-8"))

    def health(self) -> dict[str, Any]:
        return self.redact(self._transport("GET", "/health", None))

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        reply = self._transport("POST", "/mcp", {"jsonrpc": "2.0", "id": self._next_id, "method": method,
                                                  "params": params})
        return self.redact(reply)

    def tools(self) -> list[dict[str, Any]]:
        return list((self._rpc("tools/list", {}).get("result") or {}).get("tools") or [])

    def call(self, tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        reply = self._rpc("tools/call", {"name": tool, "arguments": dict(arguments)})
        if "error" in reply:
            raise GatewayToolError(tool, reply["error"])
        result = reply.get("result") or {}
        payload = result.get("structuredContent")
        if payload is None:
            content = result.get("content") or [{}]
            payload = json.loads(content[0].get("text") or "{}")
        if result.get("isError"):
            raise GatewayToolError(tool, payload)
        return payload


def tool_properties(tools: Sequence[Mapping[str, Any]], name: str) -> set[str]:
    for tool in tools:
        if tool.get("name") == name:
            return set(((tool.get("inputSchema") or {}).get("properties") or {}).keys())
    return set()


def gateway_task_id(run_id: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", run_id.lower()).strip("-")
    return slug[:96]


def _is_infra(error: str) -> bool:
    return any(marker in error for marker in _INFRA_MARKERS)


_SNAP = "measurement_worktree_diff"


def measurement_snapshot(state: Mapping[str, Any]) -> dict[str, Any]:
    """P1's raw worktree diff snapshot (#2761), validated for this attempt.

    Accepted only when its attempt id is the task's current attempt; a
    truncated snapshot makes the row invalid; a lossy (non-UTF-8) diff is
    taken byte-exact from the base64 copy; a capture error is recorded."""
    import base64

    present = _SNAP in state or f"{_SNAP}_error" in state
    out: dict[str, Any] = {
        "present": False, "diff": "", "invalid_reason": None,
        "error": state.get(f"{_SNAP}_error"),
        "attempt_id": state.get(f"{_SNAP}_attempt_id"),
        "sha256": state.get(f"{_SNAP}_sha256"),
        "bytes": state.get(f"{_SNAP}_bytes"),
        "lossy": bool(state.get(f"{_SNAP}_lossy")),
        "truncated": bool(state.get(f"{_SNAP}_truncated")),
        "elapsed_ms": state.get(f"{_SNAP}_elapsed_ms"),
    }
    if not present:
        return out
    if out["attempt_id"] != state.get("attempt_id"):
        out["invalid_reason"] = "SNAPSHOT_ATTEMPT_MISMATCH"
        return out
    if out["error"]:
        out["invalid_reason"] = f"SNAPSHOT_ERROR:{out['error']}"
        return out
    if out["truncated"]:
        out["invalid_reason"] = "SNAPSHOT_TRUNCATED"
        return out
    if out["lossy"]:
        raw_b64 = state.get(f"{_SNAP}_b64")
        if not isinstance(raw_b64, str):
            out["invalid_reason"] = "SNAPSHOT_LOSSY_WITHOUT_BYTES"
            return out
        out["diff"] = base64.b64decode(raw_b64).decode("utf-8", errors="surrogateescape")
    else:
        out["diff"] = str(state.get(_SNAP) or "")
    if out["sha256"]:
        from scripts.bench.measure_2721.common import sha256_text

        if sha256_text(out["diff"]) != out["sha256"]:
            out["diff"] = ""
            out["invalid_reason"] = "SNAPSHOT_SHA256_MISMATCH"
            return out
    out["present"] = True
    return out


def dir_sha256(root: Path) -> str:
    """State hash (locks and the ``assisted_provider_jobs`` probe cache excluded)."""
    return state_phase.state_sha256(root)


def restore_state_root(state_root: Path, snapshot: Path) -> dict[str, Any]:
    """Make ``state_root`` an exact copy of ``snapshot`` and prove it by hash (driver item 9)."""
    return state_phase.restore_state(state_root, snapshot)


def leak_surfaces(repo: Path) -> dict[str, list[str]]:
    """What a later row could inherit from a shared repository (driver item 4)."""
    refs = git(repo, "for-each-ref", "--format=%(refname) %(objectname)", "refs/nexus-candidates/",
               check=False).splitlines()
    return {
        "candidate_refs": sorted(refs),
        "stash": git(repo, "stash", "list", check=False).splitlines(),
        "worktrees": sorted(line for line in git(repo, "worktree", "list", "--porcelain", check=False).splitlines()
                            if line.startswith("worktree ")),
    }


def new_leaks(before: Mapping[str, list[str]], after: Mapping[str, list[str]], own: str) -> dict[str, list[str]]:
    """Entries present after the row and not before it, except the row's own ones."""
    leaks = {}
    for key in before:
        added = [entry for entry in after.get(key, []) if entry not in before[key] and own not in entry]
        if added:
            leaks[key] = added
    return leaks


class NexusArmDriver:
    QUIESCENCE_POLLS = 6
    QUIESCENCE_SLEEP_S = 10.0
    def __init__(
        self,
        client: GatewayClient,
        *,
        campaign_id: str,
        goal_id: str,
        scope_id: str,
        controller_git: Optional[Path] = None,
        state_dir: Optional[Path] = None,
        external_target_root: Optional[Path] = None,
        probe_model: str = CLAUDE_MEASUREMENT_MODEL,
        probe_provider: str = "claude",
        trace_dir: Optional[Path] = None,
        arm_label: str = ARM_NEXUS,
        poll_seconds: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        targets_root: Optional[Path] = None,
        state_root: Optional[Path] = None,
        state_snapshot: Optional[Path] = None,
        learning_phase: Optional[str] = None,
        key_file: Optional[str] = None,
        controller_repo: Optional[Path] = None,
        controller_pin: Optional[str] = None,
        cancel_backoff: Sequence[float] = (10.0, 20.0, 40.0, 60.0),
        measurement_root: Optional[Path] = None,
        live_configs: Optional[Sequence[Path]] = None,
        state_dir_snapshot: Optional[Path] = None,
        gateway_state_paths: Optional[Mapping[str, str]] = None,
    ):
        self.client = client
        if (controller_repo is None) != (controller_pin is None):
            raise ValueError("controller_repo and controller_pin go together (M3)")
        self._reset: Optional[controller_guard.ControllerReset] = None
        router_roots: list[Path] = []
        if controller_repo is not None:
            # B1/H1/M1/M2: one nested measurement root, the Controller (a linked
            # worktree) and its common dir under it, nothing live or main-clone.
            root = controller_guard.measurement_root({
                "--measurement-root": measurement_root,
                "--external-target-root": external_target_root,
                "NEXUS_MEASURE_EXTERNAL_TARGET_ROOT": measurement_env().get("NEXUS_MEASURE_EXTERNAL_TARGET_ROOT"),
            })
            guarded = controller_guard.guard_controller(
                controller_repo, root, controller_guard.live_locations(live_configs))
            controller_repo = guarded["controller"]
            self._reset = controller_guard.ControllerReset(controller_repo, str(controller_pin))
            # The router writes router_decisions.jsonl under its project root (the
            # Controller or the repository's main worktree): restored every row.
            router_roots = [controller_repo, guarded["common_dir"].parent]
            # The per-row ``clean -fdx`` would wipe any state kept inside the
            # Controller worktree: refuse to start (gap found in the 84ae047ba review).
            for name, path in (
                ("--state-root", state_root),
                ("--state-dir", state_dir),
                ("--state-snapshot", state_snapshot),
                ("--state-dir-snapshot", state_dir_snapshot),
                *sorted((gateway_state_paths or {}).items()),
            ):
                if path and controller_guard.is_within(path, controller_repo):
                    raise controller_guard.ControllerGuardError(f"STATE_INSIDE_CONTROLLER: {name}")
        # The Gateway env names the state the instance really uses: the driver
        # must restore (and watch) the same directories.
        for name, given in (
            ("NEXUS_STATE_ROOT", state_root),
            ("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", state_dir),
        ):
            configured = (gateway_state_paths or {}).get(name)
            if (
                configured
                and given is not None
                and not controller_guard.same_path(configured, given)
            ):
                raise controller_guard.ControllerGuardError(
                    f"STATE_PATH_DISAGREES_WITH_GATEWAY: {name}"
                )
        self._extra_state = state_phase.ExtraStateFiles.router_logs(router_roots)
        # The Gateway's own Controller checkout: reset to its pin before every
        # row (each row adds a card commit), and the source of expected_head.
        self.controller_repo = controller_repo
        self.controller_pin = controller_pin
        self.cancel_backoff = tuple(cancel_backoff)
        self.campaign_id = campaign_id
        self.goal_id = goal_id
        self.scope_id = scope_id
        self.controller_git = controller_git
        self.state_dir = state_dir
        self.external_target_root = external_target_root
        self.probe_model = probe_model
        self.probe_provider = probe_provider
        self.trace_dir = trace_dir
        self._probes: list[Any] = []
        # NEXUS_NOOP: the same P1 path while the Gateway's claude binary is the
        # no-model fake (``fake_claude.py`` mode noop); must score 0 RESOLVED.
        self.arm_label = arm_label
        self.poll_seconds = poll_seconds
        self.sleep = sleep
        # #2742: per (task, repeat) Controller clones live under the measurement
        # root (M4: ~/Workspace/nexus-measure-2721/targets/<task>-<repeat>/).
        self.targets_root = targets_root
        # Driver item 9: NEXUS_STATE_ROOT is restored from the snapshot before
        # every row and verified by a whole-dir sha256 (``.lock`` files excluded).
        self.state_root = state_root
        self.state_snapshot = state_snapshot
        # Recorded on every row; the Gateway's NEXUS_LEARNING_WRITEBACK /
        # NEXUS_STATE_READ_ONLY (#2736) are set per phase by the instance owner.
        self.learning_phase = learning_phase
        self.key_file = key_file
        self._phase_restored = False
        self._phase_resumed = False
        # The self-hosted state dir (NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR = --state-dir)
        # is restored under the same phase policy from its own snapshot, unless it
        # lies inside the state root (then the state-root restore covers it).
        self.state_dir_snapshot = state_dir_snapshot
        inside_root = bool(
            state_root is not None
            and state_dir is not None
            and controller_guard.is_within(state_dir, state_root)
        )
        if state_dir_snapshot is not None and (state_dir is None or inside_root):
            raise ValueError("--state-dir-snapshot needs a --state-dir outside --state-root")
        if (
            state_snapshot is not None
            and state_dir is not None
            and not inside_root
            and state_dir_snapshot is None
        ):
            raise ValueError(
                "SELF_HOSTED_STATE_NOT_RESTORED: --state-dir lies outside --state-root; "
                "give --state-dir-snapshot"
            )
        if learning_phase is not None or gateway_state_paths:
            # Fail closed (review blocking 3): a learning phase (M, L-A, L-B, ...) restores
            # every state tree the Gateway uses, each from its own snapshot.
            phase = str(learning_phase or "").upper()
            if phase not in state_phase.PER_ROW_PHASES | state_phase.PER_PHASE_PHASES:
                raise ValueError(f"LEARNING_PHASE_REQUIRED: {learning_phase!r}")
            if state_root is None or state_snapshot is None:
                raise ValueError("STATE_ROOT_SNAPSHOT_REQUIRED: give --state-root and --state-snapshot")
            if state_dir is None:
                raise ValueError("SELF_HOSTED_STATE_DIR_REQUIRED: give --state-dir")
            if not inside_root and state_dir_snapshot is None:
                raise ValueError(
                    "SELF_HOSTED_STATE_NOT_RESTORED: --state-dir lies outside --state-root; "
                    "give --state-dir-snapshot"
                )
        self._restore_targets: list[tuple[str, Path, Path]] = []
        if state_root is not None and state_snapshot is not None:
            self._restore_targets.append(("state_root", Path(state_root), Path(state_snapshot)))
        if state_dir is not None and state_dir_snapshot is not None:
            self._restore_targets.append(("self_hosted", Path(state_dir), Path(state_dir_snapshot)))
        self._snapshot_hashes: Optional[dict[str, str]] = None
        # The task states themselves (P1 writes one per row) are not learning state:
        # left out of the L-B read-only hash when they live inside the state root.
        self._state_hash_exclude: list[str] = []
        if state_root is not None and state_dir is not None:
            try:
                self._state_hash_exclude = [Path(os.path.realpath(state_dir)).relative_to(
                    os.path.realpath(state_root)).as_posix()]
            except ValueError:
                pass

    # -- argument builders (pure; the dry run captures them) -------------------
    def card_args(self, task: Mapping[str, Any], gw_task: str, repeat: Optional[int] = None) -> dict[str, Any]:
        text = task["text"]
        # Every (task, repeat) gets its own task id and card content, so P1 never
        # sees two rows as one logical task (DUPLICATE_LOGICAL_TASK).  The worker
        # prompt is built from what/why only, so BARE and NEXUS prompts stay equal.
        objective = text["what"] if repeat is None else (
            f"{text['what']}\n\nMeasurement row {gw_task} (repeat {repeat}).")
        return {
            "owner_confirmation": True,
            "campaign_id": self.campaign_id,
            "task_id": gw_task,
            "objective": objective,
            "allowed_files": list(text["allowed_files"]),
            "verifier_commands": list(text["verifier_commands"]),
            "authority_goal_id": self.goal_id,
            "authority_coordination_scope_id": self.scope_id,
        }

    def worker_args(self, task: Mapping[str, Any], gw_task: str, card_path: str, card_hash: str,
                    external: bool, controller: Optional[Path] = None) -> dict[str, Any]:
        text = task["text"]
        args = {
            "owner_confirmation": True,
            "task_id": gw_task,
            "what": text["what"],
            "why": text["why"],
            "allowed_files": list(text["allowed_files"]),
            "verifier_commands": list(text["verifier_commands"]),
            "task_card_path": card_path,
            "task_card_hash": card_hash,
        }
        if external:
            args[EXTERNAL_TARGET_FIELD] = {
                "repo_root": str(self._external_repo_root(controller or Path(task["base_checkout"]))),
                "base_revision": task["base_commit"],
            }
        return args

    def _external_repo_root(self, controller: Path) -> Path:
        root = Path(controller).resolve()
        if self.external_target_root is not None and self.external_target_root.resolve() not in root.parents:
            raise ValueError("controller is outside the external target root the Gateway allows")
        return root

    def fresh_controller(self, task: Mapping[str, Any], run_root: Path, run_id: str) -> Path:
        """A new Controller per (task, repeat): only the base commit, no refs (gap F6).

        A shared Controller would let repeat 2 see repeat 1's candidate refs.
        The task venv is linked beside it as ``../venv`` (the adapter's rule).
        """
        from scripts.bench.measure_2721.materialize import (
            checkout_base,
            link_venv,
            verify_base_checkout,
        )

        root = (self.targets_root / f"{task['task_id']}-r{run_id.rsplit('-r', 1)[-1]}"
                if self.targets_root is not None else run_root / "controllers" / run_id)
        if root.exists():
            raise RuntimeError(f"Controller dir already exists (never reused): {root}")
        controller = root / "repo"
        checkout_base(Path(task["base_checkout"]), task["base_commit"], controller)
        link_venv(task, controller)
        verify_base_checkout(controller, task["base_commit"])
        return controller

    # -- one run -------------------------------------------------------------
    def run(self, task: Mapping[str, Any], repeat: int, run_root: Path, *, timeout_seconds: float,
            ledger: Any = None) -> dict[str, Any]:
        """One NEXUS row.  With a ledger the row is admitted first and charged in
        ``finally`` -- also on GatewayStuck or any exception (review M3) -- with
        the cost of every Claude attempt (H2); an unknown cost is charged the
        reservation (H1)."""
        if task.get("repo") == NEXUS_REPO:
            raise ValueError("NEXUS_NEW_TASKS_NOT_MEASURED")
        token = ledger.begin_row() if ledger is not None else None
        self._submitted = False
        self._worker_accepted = False
        self._probes: list[Any] = []
        try:
            return self._run(task, repeat, run_root, timeout_seconds=timeout_seconds)
        finally:
            if ledger is not None:
                if not self._submitted:
                    ledger.finish_row(token, 0.0)
                else:
                    known, unknown, estimate = self.attempt_cost(gateway_task_id(self._run_id))
                    ledger.finish_row(token, known, unknown_attempts=unknown, estimate_usd=estimate)

    def _run(self, task: Mapping[str, Any], repeat: int, run_root: Path, *, timeout_seconds: float) -> dict[str, Any]:
        if task.get("repo") == NEXUS_REPO:
            # b6 ruling: #2721 measures external tasks only.  A Nexus-new task would
            # run on the shared Gateway Controller, whose history holds later fixes.
            raise ValueError("NEXUS_NEW_TASKS_NOT_MEASURED")
        # M3: L-A's "phase start already restored" survives a resume (exit 75);
        # a marker for other snapshots raises PhaseMarkerMismatch before any row.
        self._load_phase_marker(run_root)
        run_id = new_run_id(self.arm_label, task["task_id"], repeat)
        self._run_id = run_id
        gw_task = gateway_task_id(run_id)
        external = True
        self._current_task = task
        self.expected_cli_timeout = expected_cli_timeout(timeout_seconds)
        prompt = task_prompt(task)
        tree_sha = git(Path(task["base_checkout"]), "rev-parse", "HEAD^{tree}").strip()
        capture = input_capture(self.arm_label, task, repeat, run_id, prompt=prompt, tree_sha=tree_sha,
                                timeout_seconds=timeout_seconds)
        transcript: list[dict[str, Any]] = []
        row: dict[str, Any] = {
            "schema": ROW_SCHEMA, "arm": self.arm_label, "run_id": run_id, "task_id": task["task_id"],
            "repeat": repeat, "gateway_task_id": gw_task, "gateway_url": self.client.url,
            "non_model_solve_path": False,
        }
        from scripts.bench.measure_2721 import watchdog

        started = time.monotonic()
        created = False
        diff = ""
        controller: Optional[Path] = None
        row["learning_phase"] = self.learning_phase
        row["started_at"] = watchdog.begin_row(run_root, row_id=run_id, task_id=task["task_id"],
                                               arm=self.arm_label, cap_s=timeout_seconds)
        leak_repo = self.controller_repo or self.controller_git
        # M2 (84ae047ba review): the instance must be quiet BEFORE anything is
        # reset -- on a resume a previous Gateway task may still be in flight in
        # the Controller, and ``clean -fdx`` would wipe it.  Checked on every row.
        busy = state_phase.quiescence_problem(self.state_dir)
        for _ in range(self.QUIESCENCE_POLLS if busy else 0):
            # Wait a bounded time for the previous task to end; a row that is still
            # busy is INFRA and the runner stops with exit 75 (review item 6).
            self.sleep(self.QUIESCENCE_SLEEP_S)
            busy = state_phase.quiescence_problem(self.state_dir)
            if not busy:
                break
        # The reset reports (and this row flags) whatever the previous row left (M1).
        reset = None if busy else self.reset_controller()
        leak_before = leak_surfaces(leak_repo) if leak_repo is not None else None
        row["read_roots_sha256"] = read_roots_sha256()
        try:
            if busy:
                prefix = "STATE_RESTORE_BUSY" if self._restore_targets else "INSTANCE_BUSY"
                row.update(
                    outcome=OUTCOME_INFRA,
                    infra=True,
                    void_reason=f"{prefix}:{busy}",
                    controller_reset_skipped=True,
                )
                return row
            if reset is not None:
                row["controller_reset"] = reset
                if not reset["ok"]:
                    row.update(outcome=OUTCOME_INFRA, infra=True, void_reason="CONTROLLER_RESET_MISMATCH")
                    return row
            extra = self._extra_state.restore()
            row["extra_state_restore"] = extra
            if not extra["ok"]:
                row.update(outcome=OUTCOME_INFRA, infra=True, void_reason="EXTRA_STATE_RESTORE_MISMATCH")
                return row
            if self._restore_targets:
                policy = state_phase.restore_policy(self.learning_phase)
                row["state_restore_policy"] = policy
                if policy == "per_row" or not self._phase_restored:
                    # Only when the instance is quiet: no task in flight, the previous
                    # task cancelled and its Target removed.
                    busy = state_phase.quiescence_problem(self.state_dir)
                    if busy:
                        row.update(outcome=OUTCOME_INFRA, infra=True, void_reason=f"STATE_RESTORE_BUSY:{busy}")
                        return row
                    restored: dict[str, str] = {}
                    for label, root, snapshot in self._restore_targets:
                        restore = restore_state_root(root, snapshot)
                        row[
                            "state_restore" if label == "state_root" else f"{label}_state_restore"
                        ] = restore
                        if not restore["ok"]:
                            row.update(
                                outcome=OUTCOME_INFRA,
                                infra=True,
                                void_reason=(
                                    "STATE_ROOT_RESTORE_MISMATCH"
                                    if label == "state_root"
                                    else "SELF_HOSTED_STATE_RESTORE_MISMATCH"
                                ),
                            )
                            return row
                        restored[label] = restore["restored_sha256"]
                    self._phase_restored = True
                    if policy == "per_phase":
                        marker = state_phase.write_phase_marker(
                            run_root, self.learning_phase, self.snapshot_hashes(), restored
                        )
                        row["state_phase_marker"] = marker.name
                elif self._phase_resumed:
                    row["state_phase_marker"] = "resumed"
            if self.state_root is not None and self.state_snapshot is not None:
                row["state_before_sha256"] = state_phase.state_sha256(self.state_root,
                                                                     exclude=self._state_hash_exclude)
            health = self.client.health()
            row["gateway_health"] = {key: health.get(key) for key in (
                "git_head", "repo_head_current", "server_instance_id", "core_provenance", "controller_binding")}
            props = tool_properties(self.client.tools(), "nexus_worker_candidate")
            if external and EXTERNAL_TARGET_FIELD not in props:
                capture["gateway_worker_args"] = self.worker_args(task, gw_task, "<card>", "<hash>", external)
                row.update(outcome=OUTCOME_BLOCKED_EXTERNAL, infra=False, model_calls=0, total_tokens=None)
                return row
            if external:
                problem = venv_problem(task)
                if problem:
                    # Both arms must run with the task venv (8d pre-run witness).
                    row.update(outcome=OUTCOME_INFRA, infra=True, void_reason=problem)
                    return row
                controller = self.fresh_controller(task, run_root, run_id)
            card = self.client.call("nexus_task_card_create", self.card_args(task, gw_task, repeat))
            created = True
            transcript.append({"tool": "nexus_task_card_create", "result": card})
            commit = self.client.call("nexus_task_card_commit", {
                "owner_confirmation": True, "campaign_id": self.campaign_id, "task_id": gw_task,
                "expected_head": self.controller_head(health),
                "card_hash": card["card_hash"], "index_hash": card["index_hash"],
                "authority_goal_id": self.goal_id, "authority_coordination_scope_id": self.scope_id,
            })
            transcript.append({"tool": "nexus_task_card_commit", "result": commit})
            worker_args = self.worker_args(task, gw_task, card["card_path"], card["card_hash"], external,
                                           controller)
            capture["gateway_worker_args"] = worker_args
            self._submitted = True  # from here on the worker may spend money
            submitted = self._submit_worker(worker_args, transcript)
            self._worker_accepted = True  # the Gateway took the worker call without an error
            transcript.append({"tool": "nexus_worker_candidate", "result": submitted})
            duplicate = submitted.get("duplicate") if isinstance(submitted, Mapping) else None
            if duplicate or "DUPLICATE_LOGICAL_TASK" in json.dumps(submitted, default=str):
                # P1 joined another row's task: this row did not run its own worker.
                # Amendment 10: this row's model never ran, so it counts as not accepted.
                self._worker_accepted = False
                row.update(outcome=OUTCOME_INFRA, infra=True, void_reason="DUPLICATE_TASK",
                           duplicate=duplicate if duplicate is not True else True)
                return row
            final = self._wait(gw_task, started + timeout_seconds + 600.0, transcript)
            status = self.client.call("nexus_task_status", {"task_id": gw_task})
            transcript.append({"tool": "nexus_task_status", "result": status})
            row.update(self._collect(gw_task, status, final,
                                     controller if external else self.controller_git,
                                     repo=str(task.get("repo") or ""), base=task["base_commit"]))
            diff = row.pop("_diff", "")
        except GatewayToolError as exc:
            message = json.dumps(exc.payload)
            if not self._submitted:
                # Before the worker was submitted (card create/commit, probe, e.g.
                # TASK_CARD_COMMIT_HEAD_MISMATCH): the model never ran -> infra,
                # re-run in both arms.
                row.update(outcome=OUTCOME_INFRA, infra=True, void_reason=f"PRE_SUBMIT_FAILURE:{exc.tool}",
                           error=message[:2000])
            elif not self._worker_accepted:
                # Amendment 10: the Gateway refused the worker request, so the model
                # never ran -> infra (Nexus reliability), re-run in all arms.
                row.update(outcome=OUTCOME_INFRA, infra=True, void_reason=f"WORKER_NOT_ACCEPTED:{exc.tool}",
                           error=message[:2000])
            else:
                row.update(outcome=OUTCOME_INFRA if _is_infra(message) else OUTCOME_GATEWAY_ERROR,
                           infra=_is_infra(message), error=message[:2000])
        finally:
            stuck = None
            if created:
                try:
                    cancelled = self.client.call("nexus_task_cancel", {"task_id": gw_task})
                    transcript.append({"tool": "nexus_task_cancel", "result": cancelled})
                    refused = _cancel_refused(cancelled)
                except GatewayToolError as exc:
                    transcript.append({"tool": "nexus_task_cancel", "error": exc.payload})
                    refused = _cancel_refused(exc.payload)
                stuck = self._await_terminal(gw_task, transcript, cancel_refused=refused)
                if stuck is not None:
                    row.update(outcome=OUTCOME_INFRA, infra=True, gateway_stuck=stuck)
            if reset is not None and reset.get("removed"):
                row.setdefault("flags", []).append("CONTROLLER_LEFTOVERS")
                row["controller_leftovers"] = reset["removed"]
            if leak_before is not None and leak_repo is not None:
                leaks = new_leaks(leak_before, leak_surfaces(leak_repo), gw_task)
                if leaks:
                    row["leaks"] = leaks
                    row.setdefault("flags", []).append("STATE_LEAK")
            # ``submitted``: the worker call was sent (the model may have spent money;
            # scored as a candidate).  ``worker_accepted``: the Gateway answered it
            # without an error.  Both false on every pre-submit path.
            row["submitted"] = bool(self._submitted)
            row["worker_accepted"] = bool(self._worker_accepted)
            if self.state_root is not None and row.get("state_before_sha256"):
                row["state_after_sha256"] = state_phase.state_sha256(self.state_root,
                                                                    exclude=self._state_hash_exclude)
                if state_phase.read_only_phase(self.learning_phase) and \
                        row["state_after_sha256"] != row["state_before_sha256"]:
                    # Q2: L-B is read-only; a changed state means the freeze leaked.
                    row.setdefault("flags", []).append("LB_STATE_CHANGED")
                    row.update(outcome=OUTCOME_INFRA, infra=True,
                               void_reason=row.get("void_reason") or "LB_STATE_CHANGED")
            event = watchdog.infra_event_for(run_root, run_id)
            if event is not None:
                row.update(outcome=OUTCOME_INFRA, infra=True, watchdog_event=event)
            diff, redacted = redact_diff(diff, self.key_file)
            if redacted:
                row.setdefault("flags", []).append(FLAG_SECRET_IN_DIFF)
            watchdog.mark_snapshot(run_root)
            row["wall_seconds"] = round(time.monotonic() - started, 3)
            write_json(run_root / "inputs" / f"{run_id}.json", capture)
            write_json(run_root / "transcripts" / f"{run_id}.json", self.client.redact(transcript))
            diff_path = run_root / "diffs" / f"{run_id}.diff"
            diff_path.parent.mkdir(parents=True, exist_ok=True)
            write_diff(diff_path, diff)
            row["diff_path"] = str(diff_path)
            row.update(candidate_facts(diff, task))
            row["non_model_solve_path"] = non_model_solve(diff, row)
            if row["non_model_solve_path"]:
                row.setdefault("flags", []).append(FLAG_NON_MODEL_SOLVE)
            # Amendment 10 (blind.exclusion_reason applies the same rule): not accepted
            # -> infra; accepted -> infra only for the model-side causes BARE shares,
            # any other failure is Nexus-side and a not-solved candidate.
            row["symmetric_infra_reasons"] = blind.symmetric_infra_reasons(row)
            rule = blind.exclusion_reason(row)
            if rule is None and row.get("infra"):
                row.update(infra=False, nexus_failure_after_acceptance=True)
            elif rule is not None:
                row.update(infra=True, infra_rule=rule[0])
                if not row.get("void_reason"):
                    row["void_reason"] = f"WORKER_NOT_ACCEPTED:{row.get('outcome')}"
            append_jsonl(run_root / "rows.jsonl", row)
            append_jsonl(run_root / "rows.portable.jsonl", to_portable_row(row))
            watchdog.end_row(run_root)
        if stuck is not None:
            raise GatewayStuck(f"{gw_task}: {stuck}")
        return row

    def _await_terminal(self, gw_task: str, transcript: list[dict[str, Any]], *, attempts: int = 12,
                        cancel_refused: bool = False) -> Optional[str]:
        """None once the task is terminal (lease released), else the last status (gap F7).

        A cancel is refused while the worker is finishing (CANDIDATE_REF_PROTECTED)
        and the task then waits in PENDING_HUMAN_APPROVAL: the cancel is retried
        with backoff, and the row is stuck only after ``attempts`` polls.
        """
        status = ""
        retries = 0
        for _ in range(attempts):
            try:
                snapshot = self.client.call("nexus_task_status", {"task_id": gw_task})
            except GatewayToolError as exc:
                return f"status_error:{json.dumps(exc.payload)[:200]}"
            status = str(snapshot.get("status") or "")
            if status in TERMINAL_STATUSES:
                return None
            backoff = self.cancel_backoff[min(retries, len(self.cancel_backoff) - 1)] if self.cancel_backoff else 10.0
            self.sleep(backoff)
            if cancel_refused or status in CANCEL_RETRY_STATUSES:
                retries += 1
                try:
                    cancelled = self.client.call("nexus_task_cancel", {"task_id": gw_task})
                    transcript.append({"tool": "nexus_task_cancel", "retry": retries, "result": cancelled})
                    cancel_refused = _cancel_refused(cancelled)
                except GatewayToolError as exc:
                    transcript.append({"tool": "nexus_task_cancel", "retry": retries, "error": exc.payload})
                    cancel_refused = _cancel_refused(exc.payload)
        transcript.append({"tool": "nexus_task_status", "stuck_status": status, "cancel_retries": retries})
        return status or "unknown"

    def _submit_worker(self, args: Mapping[str, Any], transcript: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            return self.client.call("nexus_worker_candidate", args)
        except GatewayToolError as exc:
            if "MODEL_PROBE_REQUIRED" not in json.dumps(exc.payload):
                raise
        probe_id = f"{args['task_id']}-probe"[:96]
        self._probes.append(None)  # a model call: charged even if its usage never comes back
        probe = self.client.call("nexus_model_probe", {
            "provider": self.probe_provider, "model": self.probe_model, "task_id": probe_id,
            "prompt": "Return exactly a JSON object with boolean field ok=true. Do not use tools or modify files.",
            "output_schema": {"type": "object", "additionalProperties": False, "required": ["ok"],
                              "properties": {"ok": {"type": "boolean", "const": True}}},
        })
        transcript.append({"tool": "nexus_model_probe", "result": probe})
        for _ in range(30):
            result = self.client.call("nexus_model_probe_result", {"task_id": probe_id})
            if str(result.get("status") or "").upper() not in ("", "PENDING", "RUNNING", "QUEUED"):
                transcript.append({"tool": "nexus_model_probe_result", "result": result})
                if isinstance(result.get("probe_usage"), dict):
                    self._probes[-1] = result["probe_usage"]
                break
            self.sleep(10.0)
        return self.client.call("nexus_worker_candidate", args)

    def _wait(self, gw_task: str, deadline: float, transcript: list[dict[str, Any]]) -> dict[str, Any]:
        while True:
            waited = self.client.call("nexus_task_wait", {"task_id": gw_task, "timeout_seconds": self.poll_seconds})
            if not (waited.get("wait") or {}).get("timed_out", False):
                transcript.append({"tool": "nexus_task_wait", "result": waited})
                return waited
            if time.monotonic() >= deadline:
                transcript.append({"tool": "nexus_task_wait", "result": waited, "driver_deadline": True})
                return waited

    def _read_state(self, gw_task: str) -> dict[str, Any]:
        if self.state_dir is None:
            return {}
        path = self.state_dir / f"{gw_task}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    def snapshot_hashes(self) -> dict[str, str]:
        if self._snapshot_hashes is None:
            self._snapshot_hashes = {
                label: state_phase.state_sha256(snapshot)
                for label, _root, snapshot in self._restore_targets
            }
        return self._snapshot_hashes

    def _load_phase_marker(self, run_root: Path) -> None:
        """Honour a persisted L-A marker once per process (M3)."""
        if (
            self._phase_restored
            or not self._restore_targets
            or state_phase.restore_policy(self.learning_phase) != "per_phase"
        ):
            return
        if state_phase.read_phase_marker(run_root, self.learning_phase, self.snapshot_hashes()):
            self._phase_restored = True
            self._phase_resumed = True

    def reset_controller(self) -> Optional[dict[str, Any]]:
        """Reset the Controller worktree to its pin (B1): its own worktree and the
        measurement refs only; see ``controller_guard.ControllerReset``."""
        return self._reset.reset() if self._reset is not None else None

    def controller_head(self, health: Mapping[str, Any]) -> Optional[str]:
        """expected_head for the card commit: the Controller's own HEAD."""
        if self.controller_repo is not None:
            return git(self.controller_repo, "rev-parse", "HEAD").strip()  # the Controller's own HEAD
        return health.get("repo_head_current") or health.get("git_head")

    def _trace_runs(self, gw_task: str) -> list[Path]:
        if self.trace_dir is None or not (self.trace_dir / gw_task).is_dir():
            return []
        return sorted((self.trace_dir / gw_task).glob("*.run.json"), key=lambda p: (p.stat().st_mtime, p.name))

    def attempt_cost(self, gw_task: str) -> tuple[float, int, float]:
        """(known cost over every attempt, unknown attempts, usage-priced estimate of those).

        Read straight from the traces so that it also works when the row
        failed part-way (review M3).  No trace at all counts as one unknown.
        Model probes the driver triggered are charged too (usage-priced, or
        one unknown attempt when the Gateway did not report usage).
        """
        from scripts.bench.measure_2721.providers import (
            estimate_stream_usd,
            estimate_usage_usd,
            read_claude_trace,
        )

        known, unknown, estimate = 0.0, 0, 0.0
        runs = self._trace_runs(gw_task)
        for run in runs:
            name = run.name.split(".", 1)[0]
            try:
                cost = read_claude_trace(self.trace_dir, gw_task, name)["summary"].total_cost_usd
            except Exception:  # noqa: BLE001 - an unreadable trace is an unknown cost
                cost = None
            if cost is None:
                unknown += 1
                estimate += estimate_stream_usd(self.trace_dir / gw_task / f"{name}.stream.jsonl")
            else:
                known += float(cost)
        if not runs:
            unknown += 1
        for usage in getattr(self, "_probes", []):
            if isinstance(usage, dict):
                known += estimate_usage_usd(usage)
            else:
                unknown += 1
        return round(known, 6), unknown, round(estimate, 6)

    def _collect(self, gw_task: str, status: Mapping[str, Any], final: Mapping[str, Any],
                 controller: Optional[Path], *, repo: str = "", base: str = "") -> dict[str, Any]:
        """Row fields for one P1 task.

        Candidate (gap F2, same rule as BARE): the worker's raw worktree diff
        at stop.  Sources in order: the Gateway's measurement snapshot
        (``measurement_worktree_diff``, workspace-33), the live target
        worktree, then the candidate commit; ``candidate_source`` says which.
        """
        from scripts.bench.measure_2721.arms import claude_row_fields
        from scripts.bench.measure_2721.providers import (
            claude_usage_fields,
            observed_models,
            read_claude_trace,
        )

        state = {**status, **self._read_state(gw_task)}
        materialization = state.get("worker_model_context_materialization") or {}
        error = json.dumps(state.get("error") or state.get("blocker") or "")
        initial = state.get("target_initial_revision") or base
        candidate = state.get("candidate_commit_sha") or ""
        diff, source = "", "none"
        # Scored ONLY from P1's measurement_worktree_diff (#2761): never from the
        # final task state, whose Candidate Core may have refused (SCOPE_ESCAPE).
        snapshot = measurement_snapshot(state)
        if snapshot["present"]:
            diff, source = snapshot["diff"], "gateway_snapshot"
        elif not snapshot["invalid_reason"]:
            snapshot["invalid_reason"] = "SNAPSHOT_MISSING"
        del controller
        claude: dict[str, Any] = {}
        trace_text = ""
        runs = self._trace_runs(gw_task)
        traces = [read_claude_trace(self.trace_dir, gw_task, run.name.split(".", 1)[0]) for run in runs]
        if traces:
            # Every attempt is billed and counted (review H2); identity fields
            # come from the last attempt, the per-attempt checks run on all.
            trace = traces[-1]
            summary = trace["summary"]
            usages = [claude_usage_fields(t["summary"]) for t in traces]
            usage = {key: sum(u[key] for u in usages) for key in usages[0]}
            costs = [t["summary"].total_cost_usd for t in traces]
            claude = claude_row_fields({
                "claude_version": (summary.init or {}).get("claude_code_version"),
                "usage": usage, "num_turns": sum(int(t["summary"].num_turns or 0) for t in traces),
                "tool_call_count": sum(len(t["summary"].tool_calls) for t in traces),
                "total_cost_usd": round(sum(float(c) for c in costs if c is not None), 6),
                "models_seen": sorted({m for t in traces for m in observed_models(t["trace_path"])["seen"]}),
                "seatbelt_sha256": trace["sidecar"].get("seatbelt_sha256"),
                "proxy_attempts": trace["sidecar"].get("proxy_attempts"),
                "worker_span_ms": trace["sidecar"].get("wall_time_ms"),
                "served_models": sorted({m for t in traces for m in observed_models(t["trace_path"])["served"]}),
                "cli_timeout_seconds": trace["sidecar"].get("cli_timeout_seconds"),
                "key_label": trace["sidecar"].get("key_label"),
                "api_key_sha256_12": trace["sidecar"].get("api_key_sha256_12"),
                "venv": trace["sidecar"].get("venv"),
            })
            claude["claude_trace_path"] = trace["trace_path"]
            claude["claude_attempts"] = len(runs)
            claude["cost_unknown_attempts"] = sum(1 for c in costs if c is None)
            claude["attempt_cli_timeouts"] = [t["sidecar"].get("cli_timeout_seconds") for t in traces]
            claude["attempt_venvs"] = [t["sidecar"].get("venv") for t in traces]
            claude["fake_observed"] = any(t["fake_observed"] for t in traces)
            # The same labelling rule as BARE, from the last attempt's adapter record.
            last = trace["sidecar"]
            completed = bool(summary.result_seen) and summary.is_error is False
            claude["attempt_status"] = claude_status(infra=bool(last.get("infra")),
                                                     timed_out=bool(last.get("timed_out")), completed=completed)
            trace_text = "\n".join(json.dumps(call.get("input"), default=str)
                                   for t in traces for call in t["summary"].tool_calls)
        elif self.trace_dir is not None:
            # The worker was submitted but left no trace: same as BARE's missing
            # sidecar -> the row is void, never scored (review M2).
            snapshot["invalid_reason"] = snapshot["invalid_reason"] or "TRACE_MISSING"
        telemetry = state.get("telemetry") or {}
        status = claude.get("attempt_status")
        # As in BARE: an infra attempt (a 429 included) voids the row whatever
        # partial diff it left; both arms re-run it.
        infra = _is_infra(error) or status == "INFRA"
        worker_texts = [json.dumps(state.get(key), default=str) for key in
                        ("execution", "executions", "execution_outcome", "error") if state.get(key) is not None]
        lookup = lookup_signals([*worker_texts, trace_text], repo=repo)
        timed_out = bool((final.get("wait") or {}).get("timed_out")) or "timed_out\": true" in " ".join(worker_texts)
        network = [a for a in claude.get("proxy_denied") or []]
        if status is None and timed_out:
            status = "TIMEOUT"
        fake_arm = self.arm_label != ARM_NEXUS  # NEXUS_NOOP: the Gateway runs the fake CLI
        flags = [*outcome_flags(status, claude.get("served_models"), seen=claude.get("models_seen"),
                                fake_arm=fake_arm and bool(claude)),
                 *(flag for flag in (lookup["flag"], FLAG_NETWORK_ATTEMPT if network else None) if flag)]
        if snapshot["invalid_reason"]:
            flags.append("SNAPSHOT_INVALID")
        expected_limit = getattr(self, "expected_cli_timeout", None)
        if expected_limit is not None and claude and any(
                limit != expected_limit for limit in claude.get("attempt_cli_timeouts") or [None]):
            # M2': both arms must have had the same CLI time limit.
            snapshot["invalid_reason"] = snapshot["invalid_reason"] or "CLI_TIMEOUT_MISMATCH"
            flags.append("CLI_TIMEOUT_MISMATCH")
        if claude and getattr(self, "_current_task", None) is not None:
            issue = next((found for found in (
                venv_problem(self._current_task, venv, check_observed=True)
                for venv in claude.get("attempt_venvs") or [None]) if found), None)
            if issue:
                flags.append("VENV_NOT_USABLE")
                snapshot["invalid_reason"] = snapshot["invalid_reason"] or issue
        return {
            "flags": flags,
            "lookup": lookup,
            "_diff": diff,
            "candidate_source": source,
            "snapshot": {key: value for key, value in snapshot.items() if key != "diff"},
            "void_reason": snapshot["invalid_reason"],
            # An unusable snapshot voids the row: re-run in every arm (S4).
            "outcome": OUTCOME_INFRA if infra or snapshot["invalid_reason"] else (
                status if status in ("TIMEOUT", "MODEL_FAILED") else OUTCOME_DONE),
            "infra": infra or bool(snapshot["invalid_reason"]),
            "gateway_status": state.get("status"),
            "verification_verdict": state.get("verification_verdict"),
            "candidate_commit_sha": candidate or None,
            "target_initial_revision": initial or None,
            "selected_capabilities": materialization.get("selected_capabilities"),
            "capability_observations": materialization.get("capability_observations"),
            "selected_provider": state.get("selected_provider"),
            "selected_model": state.get("selected_model"),
            "worker_started_at": state.get("worker_started_at"),
            "worker_finished_at": state.get("worker_finished_at"),
            "model_calls": claude.get("num_turns", telemetry.get("provider_calls") if isinstance(telemetry, Mapping) else None),
            "total_tokens": None,
            "telemetry": telemetry,
            **claude,
            "error": error[:2000] if error not in ('""', "null") else "",
            "final_wait": {key: final.get(key) for key in ("status", "blocker", "wait")},
        }


class DriverStartRefused(RuntimeError):
    pass


BUSY_PREFIXES = ("INSTANCE_BUSY:", "STATE_RESTORE_BUSY:")


def instance_busy(row: Mapping[str, Any]) -> bool:
    """The row found the instance still busy after the bounded wait: stop the run (exit 75)."""
    return str(row.get("void_reason") or "").startswith(BUSY_PREFIXES)


def add_gateway_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--gateway-url", required=True, help="e.g. http://127.0.0.1:18766 (never :8766)")
    parser.add_argument("--token-file", required=True, help="0600 file with the measurement-only token")
    parser.add_argument("--campaign-id", default="measure-2721")
    parser.add_argument("--goal-id", default="issue-2721-measurement")
    parser.add_argument("--scope-id", required=True, help="e.g. <session>-i2721-runK")
    parser.add_argument("--controller-git", help="git dir holding candidate commits (for the diff)")
    parser.add_argument(
        "--state-dir",
        help="the instance's self-hosted state dir "
        "(NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR); read for quiescence, restored with "
        "--state-dir-snapshot",
    )
    parser.add_argument("--external-target-root", help="root the Gateway allows external targets under")
    parser.add_argument("--trace-dir", required=True,
                        help="the Gateway's NEXUS_MEASUREMENT_TRACE_DIR (read only; cost and checks come from it)")
    parser.add_argument("--targets-root", help="measurement root for per-row Controller clones (#2742)")
    parser.add_argument("--state-root", help="the Gateway's NEXUS_STATE_ROOT (restored per the phase's policy)")
    parser.add_argument("--state-snapshot", help="phase-start snapshot NEXUS_STATE_ROOT is restored from")
    parser.add_argument(
        "--state-dir-snapshot",
        help="phase-start snapshot the self-hosted state dir (--state-dir, "
        "NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR) is restored from; required when it lies "
        "outside --state-root",
    )
    parser.add_argument("--learning-phase", help="M / LA / LB (also COLD / IRRELEVANT); sets the restore policy")
    parser.add_argument("--arm-label", choices=[ARM_NEXUS, "NEXUS_NOOP"], default=ARM_NEXUS,
                        help="NEXUS_NOOP when the Gateway runs the no-model fake claude binary")
    parser.add_argument("--controller-repo", help="the measurement Gateway's Controller worktree (reset per row)")
    parser.add_argument("--controller-pin", help="commit the Controller is reset to before every row")
    parser.add_argument("--measurement-root", help="the measurement dir; the Controller and its git common dir "
                        "must lie under it (with --external-target-root / NEXUS_MEASURE_EXTERNAL_TARGET_ROOT)")
    parser.add_argument("--live-config", action="append",
                        help="live Gateway configuration to read live locations from (default: the live "
                        "launchd plists and mcp-gateway.env); none readable -> refuse to start")


def build_driver(args: argparse.Namespace, parser: argparse.ArgumentParser) -> "NexusArmDriver":
    if bool(args.controller_pin) != bool(args.controller_repo):
        parser.error("--controller-repo and --controller-pin go together (M3)")
    if args.state_snapshot and not args.state_dir:
        parser.error("--state-snapshot needs --state-dir (a restore waits for a quiet instance)")
    if args.controller_repo and not args.state_dir:
        # M2: the Controller reset waits for a quiet instance, read from the state dir.
        parser.error("--controller-repo needs --state-dir (the reset waits for a quiet instance)")
    bad = state_phase.invalid_states(Path(args.state_dir) if args.state_dir else None)
    if bad:
        raise DriverStartRefused(f"STATE_INVALID_RECORDS: {bad[:5]}")
    from scripts.bench.measure_2721.gateway_env import GatewayEnvError, gateway_state_paths

    try:
        state_paths = (
            gateway_state_paths(args.gateway_env) if getattr(args, "gateway_env", None) else {}
        )
    except (OSError, GatewayEnvError) as exc:
        raise DriverStartRefused(f"GATEWAY_STATE_PATHS_UNREADABLE: {exc}") from exc
    client = GatewayClient(args.gateway_url, read_token(args.token_file))
    try:
        return NexusArmDriver(
            client,
            campaign_id=args.campaign_id,
            goal_id=args.goal_id,
            scope_id=args.scope_id,
            controller_git=Path(args.controller_git) if args.controller_git else None,
            state_dir=Path(args.state_dir) if args.state_dir else None,
            external_target_root=Path(args.external_target_root)
            if args.external_target_root
            else None,
            trace_dir=Path(args.trace_dir),
            arm_label=args.arm_label,
            targets_root=Path(args.targets_root) if args.targets_root else None,
            state_root=Path(args.state_root) if args.state_root else None,
            state_snapshot=Path(args.state_snapshot) if args.state_snapshot else None,
            learning_phase=args.learning_phase,
            key_file=args.key_file,
            controller_repo=Path(args.controller_repo) if args.controller_repo else None,
            controller_pin=args.controller_pin,
            measurement_root=Path(args.measurement_root) if args.measurement_root else None,
            live_configs=[Path(p) for p in args.live_config] if args.live_config else None,
            state_dir_snapshot=Path(args.state_dir_snapshot) if args.state_dir_snapshot else None,
            gateway_state_paths=state_paths,
        )
    except (controller_guard.ControllerGuardError, ValueError) as exc:
        raise DriverStartRefused(str(exc)) from exc


def main(argv: Sequence[str] | None = None) -> int:
    from scripts.bench.measure_2721.runner import (
        PrepareStop,
        add_common_args,
        add_single_arm_flag,
        prepare,
        single_arm_refusal,
    )

    parser = argparse.ArgumentParser(
        description="Drive the NEXUS arm of #2721 on its own (debug; formal runs "
        "go through runner.py)"
    )
    add_common_args(parser)
    add_gateway_args(parser)
    add_single_arm_flag(parser)
    args = parser.parse_args(argv)
    try:
        tasks = prepare(args, need_read_roots=True)
        driver = build_driver(args, parser)
    except PrepareStop as stop:
        print(json.dumps(stop.payload))
        return stop.code
    except DriverStartRefused as exc:
        print(json.dumps({"stopped": "DRIVER_REFUSED", "detail": str(exc)}))
        return 2
    # Checked after the start checks (their refusals stay the first answer) and
    # before any row: a real-model NEXUS arm on its own is not a formal run.
    refused = single_arm_refusal(args, paid=args.arm_label == ARM_NEXUS)
    if refused is not None:
        print(json.dumps(refused))
        return 2
    from scripts.bench.measure_2721.budget import BudgetExhausted, SpendLedger

    ledger = SpendLedger(Path(args.spend_ledger), args.budget_usd, args.max_row_usd)
    rows = []
    try:
        for task in tasks:
            for repeat in args.repeats:
                rows.append(driver.run(task, repeat, Path(args.run_root), timeout_seconds=args.timeout,
                                       ledger=ledger))
                if instance_busy(rows[-1]):
                    print(json.dumps({"stopped": "INSTANCE_BUSY", "detail": rows[-1]["void_reason"],
                                      "rows": len(rows)}))
                    return 75
    except BudgetExhausted as exc:
        print(json.dumps({"stopped": str(exc), "rows": len(rows)}))
        return 75
    except GatewayStuck as exc:
        print(json.dumps({"stopped": "GATEWAY_STUCK", "detail": str(exc), "rows": len(rows)}))
        return 75
    except state_phase.PhaseMarkerMismatch as exc:
        print(
            json.dumps({
                "stopped": "STATE_PHASE_MARKER_MISMATCH",
                "detail": str(exc),
                "rows": len(rows),
            })
        )
        return 2
    print(json.dumps({"rows": len(rows), "outcomes": sorted({row["outcome"] for row in rows})}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
