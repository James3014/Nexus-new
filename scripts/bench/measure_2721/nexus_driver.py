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

from scripts.bench.measure_2721.arms import (
    ARM_NEXUS,
    FLAG_SECRET_IN_DIFF,
    ROW_SCHEMA,
    candidate_facts,
    expected_cli_timeout,
    input_capture,
    load_manifest,
    new_run_id,
    redact_diff,
    served_model_flag,
    task_prompt,
)
from scripts.bench.measure_2721.common import append_jsonl, git, write_diff, write_json
from scripts.bench.measure_2721.leakage import FLAG_NETWORK_ATTEMPT, FLAG_TIMEOUT, lookup_signals
from scripts.bench.measure_2721.portable import to_portable_row

LIVE_GATEWAY_PORT = 8766
NEXUS_REPO = "James3014/Nexus-new"
EXTERNAL_TARGET_FIELD = "external_target"
OUTCOME_BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL_TARGET_UNSUPPORTED"
OUTCOME_GATEWAY_ERROR = "GATEWAY_ERROR"
OUTCOME_INFRA = "INFRA"
OUTCOME_DONE = "OK"
_INFRA_MARKERS = ("agy_pool_busy", "AGY_POOL_BUSY", "POOL_EXHAUSTED", "agy_pool_exhausted",
                  "credentials_unavailable", "MODEL_PROBE_REQUIRED", "claude_infra:",
                  "MEASUREMENT_CLAUDE_PROBE_FAILED", "MEASUREMENT_CLAUDE_BINARY_UNAVAILABLE")
TERMINAL_STATUSES = frozenset({"CANCELLED", "FINAL_BLOCK", "REJECTED", "SUPERSEDED", "INTEGRATED",
                               "INTEGRATION_FAILED", "RETAINED_FOR_REVIEW", "FAILED", "TERMINAL"})


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
    """sha256 over every file under ``root`` (relative path + content), ``.lock`` files excluded."""
    import hashlib

    digest = hashlib.sha256()
    for path in sorted(p for p in Path(root).rglob("*") if p.is_file() and not p.name.endswith(".lock")):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def restore_state_root(state_root: Path, snapshot: Path) -> dict[str, Any]:
    """Make ``state_root`` an exact copy of ``snapshot`` and prove it by hash (driver item 9)."""
    import shutil

    expected = dir_sha256(snapshot)
    for child in list(Path(state_root).iterdir()) if Path(state_root).exists() else []:
        if child.name.endswith(".lock"):
            continue
        shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
    Path(state_root).mkdir(parents=True, exist_ok=True)
    shutil.copytree(snapshot, state_root, dirs_exist_ok=True, symlinks=True)
    actual = dir_sha256(state_root)
    return {"expected_sha256": expected, "restored_sha256": actual, "ok": expected == actual}


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
    def __init__(self, client: GatewayClient, *, campaign_id: str, goal_id: str, scope_id: str,
                 controller_git: Optional[Path] = None, state_dir: Optional[Path] = None,
                 external_target_root: Optional[Path] = None, probe_model: str = "claude-haiku-5-5",
                 probe_provider: str = "claude", trace_dir: Optional[Path] = None, arm_label: str = ARM_NEXUS,
                 poll_seconds: float = 60.0, sleep: Callable[[float], None] = time.sleep,
                 targets_root: Optional[Path] = None, state_root: Optional[Path] = None,
                 state_snapshot: Optional[Path] = None, learning_phase: Optional[str] = None,
                 key_file: Optional[str] = None):
        self.client = client
        self.campaign_id = campaign_id
        self.goal_id = goal_id
        self.scope_id = scope_id
        self.controller_git = controller_git
        self.state_dir = state_dir
        self.external_target_root = external_target_root
        self.probe_model = probe_model
        self.probe_provider = probe_provider
        self.trace_dir = trace_dir
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

    # -- argument builders (pure; the dry run captures them) -------------------
    def card_args(self, task: Mapping[str, Any], gw_task: str) -> dict[str, Any]:
        text = task["text"]
        return {
            "owner_confirmation": True,
            "campaign_id": self.campaign_id,
            "task_id": gw_task,
            "objective": text["what"],
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
    def run(self, task: Mapping[str, Any], repeat: int, run_root: Path, *, timeout_seconds: float) -> dict[str, Any]:
        if task.get("repo") == NEXUS_REPO:
            # b6 ruling: #2721 measures external tasks only.  A Nexus-new task would
            # run on the shared Gateway Controller, whose history holds later fixes.
            raise ValueError("NEXUS_NEW_TASKS_NOT_MEASURED")
        run_id = new_run_id(self.arm_label, task["task_id"], repeat)
        gw_task = gateway_task_id(run_id)
        external = True
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
        watchdog.begin_row(run_root, row_id=run_id, task_id=task["task_id"], arm=self.arm_label,
                           cap_s=timeout_seconds)
        leak_before = leak_surfaces(self.controller_git) if self.controller_git is not None else None
        try:
            if self.state_root is not None and self.state_snapshot is not None:
                restore = restore_state_root(self.state_root, self.state_snapshot)
                row["state_restore"] = restore
                if not restore["ok"]:
                    row.update(outcome=OUTCOME_INFRA, infra=True, void_reason="STATE_ROOT_RESTORE_MISMATCH")
                    return row
            health = self.client.health()
            row["gateway_health"] = {key: health.get(key) for key in (
                "git_head", "repo_head_current", "server_instance_id", "core_provenance", "controller_binding")}
            props = tool_properties(self.client.tools(), "nexus_worker_candidate")
            if external and EXTERNAL_TARGET_FIELD not in props:
                capture["gateway_worker_args"] = self.worker_args(task, gw_task, "<card>", "<hash>", external)
                row.update(outcome=OUTCOME_BLOCKED_EXTERNAL, infra=False, model_calls=0, total_tokens=None)
                return row
            if external:
                controller = self.fresh_controller(task, run_root, run_id)
            card = self.client.call("nexus_task_card_create", self.card_args(task, gw_task))
            created = True
            transcript.append({"tool": "nexus_task_card_create", "result": card})
            commit = self.client.call("nexus_task_card_commit", {
                "owner_confirmation": True, "campaign_id": self.campaign_id, "task_id": gw_task,
                "expected_head": health.get("repo_head_current") or health.get("git_head"),
                "card_hash": card["card_hash"], "index_hash": card["index_hash"],
                "authority_goal_id": self.goal_id, "authority_coordination_scope_id": self.scope_id,
            })
            transcript.append({"tool": "nexus_task_card_commit", "result": commit})
            worker_args = self.worker_args(task, gw_task, card["card_path"], card["card_hash"], external,
                                           controller)
            capture["gateway_worker_args"] = worker_args
            submitted = self._submit_worker(worker_args, transcript)
            transcript.append({"tool": "nexus_worker_candidate", "result": submitted})
            final = self._wait(gw_task, started + timeout_seconds + 600.0, transcript)
            status = self.client.call("nexus_task_status", {"task_id": gw_task})
            transcript.append({"tool": "nexus_task_status", "result": status})
            row.update(self._collect(gw_task, status, final,
                                     controller if external else self.controller_git,
                                     repo=str(task.get("repo") or ""), base=task["base_commit"]))
            diff = row.pop("_diff", "")
        except GatewayToolError as exc:
            message = json.dumps(exc.payload)
            row.update(outcome=OUTCOME_INFRA if _is_infra(message) else OUTCOME_GATEWAY_ERROR,
                       infra=_is_infra(message), error=message[:2000])
        finally:
            stuck = None
            if created:
                try:
                    transcript.append({"tool": "nexus_task_cancel",
                                       "result": self.client.call("nexus_task_cancel", {"task_id": gw_task})})
                except GatewayToolError as exc:
                    transcript.append({"tool": "nexus_task_cancel", "error": exc.payload})
                stuck = self._await_terminal(gw_task, transcript)
                if stuck is not None:
                    row.update(outcome=OUTCOME_INFRA, infra=True, gateway_stuck=stuck)
            if leak_before is not None and self.controller_git is not None:
                leaks = new_leaks(leak_before, leak_surfaces(self.controller_git), gw_task)
                if leaks:
                    row["leaks"] = leaks
                    row.setdefault("flags", []).append("STATE_LEAK")
            if self.state_root is not None and self.state_snapshot is not None and row.get("state_restore"):
                row["state_after_sha256"] = dir_sha256(self.state_root)
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
            append_jsonl(run_root / "rows.jsonl", row)
            append_jsonl(run_root / "rows.portable.jsonl", to_portable_row(row))
            watchdog.end_row(run_root)
        if stuck is not None:
            raise GatewayStuck(f"{gw_task}: {stuck}")
        return row

    def _await_terminal(self, gw_task: str, transcript: list[dict[str, Any]], *, attempts: int = 12) -> Optional[str]:
        """None once the task is terminal (lease released), else the last status (gap F7)."""
        status = ""
        for _ in range(attempts):
            try:
                snapshot = self.client.call("nexus_task_status", {"task_id": gw_task})
            except GatewayToolError as exc:
                return f"status_error:{json.dumps(exc.payload)[:200]}"
            status = str(snapshot.get("status") or "")
            if status in TERMINAL_STATUSES:
                return None
            self.sleep(10.0)
        transcript.append({"tool": "nexus_task_status", "stuck_status": status})
        return status or "unknown"

    def _submit_worker(self, args: Mapping[str, Any], transcript: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            return self.client.call("nexus_worker_candidate", args)
        except GatewayToolError as exc:
            if "MODEL_PROBE_REQUIRED" not in json.dumps(exc.payload):
                raise
        probe_id = f"{args['task_id']}-probe"[:96]
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

    def _collect(self, gw_task: str, status: Mapping[str, Any], final: Mapping[str, Any],
                 controller: Optional[Path], *, repo: str = "", base: str = "") -> dict[str, Any]:
        """Row fields for one P1 task.

        Candidate (gap F2, same rule as BARE): the worker's raw worktree diff
        at stop.  Sources in order: the Gateway's measurement snapshot
        (``measurement_worktree_diff``, workspace-33), the live target
        worktree, then the candidate commit; ``candidate_source`` says which.
        """
        from scripts.bench.measure_2721.arms import claude_row_fields
        from scripts.bench.measure_2721.providers import claude_usage_fields, read_claude_trace

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
        runs = sorted((self.trace_dir / gw_task).glob("*.run.json"), key=lambda p: p.stat().st_mtime) \
            if self.trace_dir is not None and (self.trace_dir / gw_task).is_dir() else []
        if runs:
            stdout_sha = runs[-1].name.split(".", 1)[0]
            trace = read_claude_trace(self.trace_dir, gw_task, stdout_sha)
            summary = trace["summary"]
            claude = claude_row_fields({
                "claude_version": (summary.init or {}).get("claude_code_version"),
                "usage": claude_usage_fields(summary), "num_turns": summary.num_turns,
                "tool_call_count": len(summary.tool_calls), "total_cost_usd": summary.total_cost_usd,
                "models_seen": list(summary.models_seen),
                "seatbelt_sha256": trace["sidecar"].get("seatbelt_sha256"),
                "proxy_attempts": trace["sidecar"].get("proxy_attempts"),
                "worker_span_ms": trace["sidecar"].get("wall_time_ms"),
                "served_models": list(summary.served_models),
                "cli_timeout_seconds": trace["sidecar"].get("cli_timeout_seconds"),
                "key_label": trace["sidecar"].get("key_label"),
                "api_key_sha256_12": trace["sidecar"].get("api_key_sha256_12"),
            })
            claude["claude_trace_path"] = trace["trace_path"]
            claude["claude_attempts"] = len(runs)
            claude["fake_observed"] = trace["fake_observed"]
            trace_text = "\n".join(json.dumps(call.get("input"), default=str) for call in summary.tool_calls)
        telemetry = state.get("telemetry") or {}
        infra = _is_infra(error) and not diff.strip()
        worker_texts = [json.dumps(state.get(key), default=str) for key in
                        ("execution", "executions", "execution_outcome", "error") if state.get(key) is not None]
        lookup = lookup_signals([*worker_texts, trace_text], repo=repo)
        timed_out = bool((final.get("wait") or {}).get("timed_out")) or "timed_out\": true" in " ".join(worker_texts)
        network = [a for a in claude.get("proxy_denied") or []]
        flags = [flag for flag in (FLAG_TIMEOUT if timed_out else None, lookup["flag"],
                                   FLAG_NETWORK_ATTEMPT if network else None) if flag]
        if snapshot["invalid_reason"]:
            flags.append("SNAPSHOT_INVALID")
        expected_limit = getattr(self, "expected_cli_timeout", None)
        if expected_limit is not None and claude and claude.get("cli_timeout_seconds") != expected_limit:
            # M2': both arms must have had the same CLI time limit.
            snapshot["invalid_reason"] = snapshot["invalid_reason"] or "CLI_TIMEOUT_MISMATCH"
            flags.append("CLI_TIMEOUT_MISMATCH")
        served_flag = served_model_flag(claude.get("served_models"))
        if served_flag:
            flags.append(served_flag)
        return {
            "flags": flags,
            "lookup": lookup,
            "_diff": diff,
            "candidate_source": source,
            "snapshot": {key: value for key, value in snapshot.items() if key != "diff"},
            "void_reason": snapshot["invalid_reason"],
            # An unusable snapshot voids the row: re-run in every arm (S4).
            "outcome": OUTCOME_INFRA if infra or snapshot["invalid_reason"] else OUTCOME_DONE,
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drive the NEXUS arm of #2721 on a measurement Gateway")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--gateway-url", required=True, help="e.g. http://127.0.0.1:18766 (never :8766)")
    parser.add_argument("--token-file", required=True, help="0600 file with the measurement-only token")
    parser.add_argument("--campaign-id", default="measure-2721")
    parser.add_argument("--goal-id", default="issue-2721-measurement")
    parser.add_argument("--scope-id", required=True, help="e.g. <session>-i2721-runK")
    parser.add_argument("--controller-git", help="git dir holding candidate commits (for the diff)")
    parser.add_argument("--state-dir", help="the instance's self-hosted state dir (read only)")
    parser.add_argument("--external-target-root", help="root the Gateway allows external targets under")
    parser.add_argument("--trace-dir", help="the Gateway's NEXUS_MEASUREMENT_TRACE_DIR (read only)")
    parser.add_argument("--targets-root", help="measurement root for per-row Controller clones (#2742)")
    parser.add_argument("--state-root", help="the Gateway's NEXUS_STATE_ROOT (restored before each row)")
    parser.add_argument("--state-snapshot", help="directory snapshot to restore NEXUS_STATE_ROOT from")
    parser.add_argument("--learning-phase", help="recorded on every row (LA / LB / COLD / IRRELEVANT / M)")
    parser.add_argument("--key-file", default=str(Path("~/.config/nexus-measure-2721/anthropic.env").expanduser()),
                        help="the measurement key file, used only to redact candidate diffs")
    parser.add_argument("--arm-label", choices=[ARM_NEXUS, "NEXUS_NOOP"], default=ARM_NEXUS,
                        help="NEXUS_NOOP when the Gateway runs the no-model fake claude binary")
    parser.add_argument("--repeats", type=int, nargs="+", default=[1])
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args(argv)
    client = GatewayClient(args.gateway_url, read_token(args.token_file))
    driver = NexusArmDriver(
        client, campaign_id=args.campaign_id, goal_id=args.goal_id, scope_id=args.scope_id,
        controller_git=Path(args.controller_git) if args.controller_git else None,
        state_dir=Path(args.state_dir) if args.state_dir else None,
        external_target_root=Path(args.external_target_root) if args.external_target_root else None,
        trace_dir=Path(args.trace_dir) if args.trace_dir else None,
        arm_label=args.arm_label,
        targets_root=Path(args.targets_root) if args.targets_root else None,
        state_root=Path(args.state_root) if args.state_root else None,
        state_snapshot=Path(args.state_snapshot) if args.state_snapshot else None,
        learning_phase=args.learning_phase,
        key_file=args.key_file,
    )
    rows = []
    try:
        for task in load_manifest(args.manifest, args.ids):
            for repeat in args.repeats:
                rows.append(driver.run(task, repeat, Path(args.run_root), timeout_seconds=args.timeout))
    except GatewayStuck as exc:
        print(json.dumps({"stopped": "GATEWAY_STUCK", "detail": str(exc), "rows": len(rows)}))
        return 75
    print(json.dumps({"rows": len(rows), "outcomes": sorted({row["outcome"] for row in rows})}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
