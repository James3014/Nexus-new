#!/usr/bin/env python3
"""Unattended nightly scheduler for Nexus External Intelligence Automation (EIA) on M4.

Subcommands (each idempotent, serialised by a lock, one state file per night):

  prepare   afternoon: render one Task Card per ``eia:queue`` Issue, validate it with the
            daemon's own validators, open ONE card PR and hand it to merge-queue (coord).
  start     23:30: caffeinate, Chrome + ibase Browser Bridge, health check, start the daemon.
            Skips the night when the card PR is not merged.
  dispatch  every 5 min: arm one Issue at a time (contract appended, label added LAST);
            turn COMPLETE into a candidate PR handed to merge-queue; retry infra failures with
            a new revision/unit (max 2); escalate model failures.
  stop      07:30 (hard stop 09:00): arm nothing new, boot the daemon out, kill caffeinate,
            write the morning report, send it to coordinator, post a macOS notification.
  status    print the night state.

It never merges anything and never touches an Issue without the ``eia:queue`` label.  Every
decision fails closed.  See docs/ops/eia_nightly.md.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import plistlib
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.services.external_intelligence_automation import (  # noqa: E402
    FENCE_RE,
    ISSUE_SCHEMA,
    TERMINAL_DISPOSITIONS,
    ExternalIntelligenceAutomation,
    IssueWorkItem,
    parse_issue_contract,
)
from nexus.services.external_intelligence_core_binding import (  # noqa: E402
    CAPABILITY_DISCOVERY_INDEX_PATH,
    DONOR_CAPABILITY_DISPOSITIONS,
    _require_lane,
    build_capability_discovery_receipt,
)

HOME = Path.home()
REPOSITORY = "James3014/Nexus-new"
STATE_SCHEMA = "nexus.eia_nightly_state.v1"
L_QUEUE, L_EIA, L_ESCALATE = "eia:queue", "nexus:external-intelligence", "eia:escalate"
L_TEMPLATE, L_CANDIDATE = "eia:needs-template", "eia:candidate-pr"
SKIP_LABELS = {L_EIA, L_ESCALATE, L_TEMPLATE, L_CANDIDATE}
TRACKING_TITLE = "EIA nightly task cards"
CARD_DIR = "tasks/eia-nightly"
COORD_AS = "m4-eia-nightly"
DAEMON_LABEL = "com.nexus.external-intelligence"
BOT_NAME = "james3014-nexus-agent[bot]"
BOT_EMAIL = "341779647+james3014-nexus-agent[bot]@users.noreply.github.com"
TASK_FENCE_RE = re.compile(r"```eia-task[ \t]*\n(.*?)\n```", re.DOTALL)
CONTRACT_MARKER = "<!-- eia-nightly:contract -->"
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")
# Paths an overnight worker must never change: CI, governance, dependencies, the EIA daemon and
# this scheduler (prefix match on whole path components; ``*`` entries are name prefixes).
PROTECTED_PATHS = (
    ".github",
    ".nexus-core",
    ".gitmodules",
    "docs/governance",
    "docs/agents",
    "docs/testing/test_impact_map.md",
    "tasks",
    "pyproject.toml",
    "uv.lock",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "MUSE_PROTO.md",
    "nexus/services/external_intelligence*",
    "scripts/ops/trusted_*",
    "scripts/ops/external_intelligence*",
    "scripts/ops/eia_nightly*",
    "scripts/ops/com.nexus.eia-nightly*",
    "tests/ops/test_eia_nightly.py",
)
# Who may queue an Issue (apply ``eia:queue``) or edit its body after it was queued.
TRUSTED_ACTORS = frozenset({"James3014", "james3014-nexus-agent", "james3014-nexus-agent[bot]"})
PYTEST_TARGET_RE = re.compile(r"^tests/[A-Za-z0-9_][A-Za-z0-9_/.-]*\.py(::[A-Za-z0-9_]+)*$")
DIFF_CHECK_ARGV = ["sh", "-c", 'git diff --check "$NEXUS_BASE_SHA" "$NEXUS_CANDIDATE_SHA"']
MAX_ALLOWED_FILES = 10
MAX_NIGHTS_WITHOUT_CANDIDATE = 3
WATCH_INTERVAL = 20
EXCEPTION_NAME_RE = re.compile(r"^[A-Za-z]+(Error|Exception|Expired)$")
WAIT_STATES = {
    "DISCOVERED",
    "INTELLIGENCE_DISPATCHING",
    "INTELLIGENCE_COMPLETED",
    "FANOUT_DISPATCHING",
    "FANOUT_COMPLETED",
    "CLOSURE_DISPATCHING",
}
RESUMABLE_PRIOR = {"INTELLIGENCE_DISPATCHING", "FANOUT_DISPATCHING"}
INFRA_MARKERS = ("OPENCLI_", "TRANSPORT", "OUTCOME_UNKNOWN", "REMOTE_MAIN_REFRESH_FAILED")
MODEL_MARKERS = ("WORKER_BLOCKED", "REPAIR", "SCOPE_DELTA", "VERIFICATION_FAIL", "VERIFIER_FAIL")
PUBLICATION_GRACE_MIN = 15


class NightlyError(RuntimeError):
    pass


Runner = Callable[..., subprocess.CompletedProcess]


def default_runner(argv: list[str], **kw: Any) -> subprocess.CompletedProcess:
    kw.setdefault("timeout", 120)
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", check=False, **kw
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(argv, 124, "", f"{type(exc).__name__}: {exc}")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _one_line(text: Any, limit: int) -> str:
    clean = re.sub(r"[`#<>|\\]", "", str(text or ""))
    return re.sub(r"\s+", " ", clean).strip()[:limit]


def _issue_number(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not str(value).isdigit():
        raise NightlyError("ISSUE_NUMBER_INVALID")
    number = int(value)
    if not 0 < number < 10**7:
        raise NightlyError("ISSUE_NUMBER_INVALID")
    return number


def _sha(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not SHA1_RE.fullmatch(text):
        raise NightlyError("SHA_INVALID")
    return text


def _number_from_url(output: str) -> int:
    lines = (output or "").strip().splitlines()
    return _issue_number(lines[-1].rstrip("/").rsplit("/", 1)[-1] if lines else "")


def _ts(value: Any) -> dt.datetime:
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise NightlyError("TIMESTAMP_INVALID") from exc


def night_of(now: dt.datetime) -> str:
    """Nights run from noon to noon: 16:00 and 23:30 belong to today, 03:00 to yesterday."""
    return (now - dt.timedelta(hours=12)).strftime("%Y%m%d")


def night_clock(night: str, hhmm: str) -> dt.datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    morning = dt.datetime.strptime(night, "%Y%m%d") + dt.timedelta(days=1)
    return morning.replace(hour=hour, minute=minute)


# --------------------------------------------------------------------------- task block


def parse_task_block(body: str) -> dict[str, Any]:
    """Parse the single ```eia-task JSON block of a queued Issue (see docs/ops/eia_nightly.md)."""
    blocks = TASK_FENCE_RE.findall(body or "")
    if len(blocks) != 1:
        raise NightlyError("TASK_BLOCK_REQUIRED")
    if FENCE_RE.search(body or ""):
        raise NightlyError("TASK_BODY_HAS_FOREIGN_CONTRACT")
    try:
        raw = json.loads(blocks[0])
    except ValueError as exc:
        raise NightlyError("TASK_BLOCK_JSON_INVALID") from exc
    allowed = {
        "difficulty",
        "allowed_files",
        "verification",
        "capability_ids",
        "capability_disposition",
        "summary",
    }
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise NightlyError("TASK_BLOCK_KEYS_INVALID")
    difficulty = raw.get("difficulty")
    if difficulty not in ("easy", "medium", "hard"):
        raise NightlyError("TASK_DIFFICULTY_INVALID")
    files = raw.get("allowed_files")
    if (
        not isinstance(files, list)
        or not 0 < len(files) <= MAX_ALLOWED_FILES
        or len(set(files)) != len(files)
    ):
        raise NightlyError("TASK_ALLOWED_FILES_INVALID")
    for path in files:
        if not isinstance(path, str) or not SAFE_PATH_RE.fullmatch(path):
            raise NightlyError("TASK_ALLOWED_FILES_INVALID")
        parts = PurePosixPath(path).parts
        if PurePosixPath(path).as_posix() != path or ".." in parts or "." in parts:
            raise NightlyError("TASK_ALLOWED_FILES_INVALID")
        if is_protected(path):
            raise NightlyError("TASK_ALLOWED_FILES_PROTECTED")
    commands = raw.get("verification")
    if not isinstance(commands, list) or not 0 < len(commands) <= 8:
        raise NightlyError("TASK_VERIFICATION_INVALID")
    argvs: list[list[str]] = []
    for command in commands:
        try:
            argv = shlex.split(command) if isinstance(command, str) else []
        except ValueError as exc:
            raise NightlyError("TASK_VERIFICATION_INVALID") from exc
        argvs.append(allowlisted_verifier(argv))
    ids = raw.get("capability_ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i for i in ids):
        raise NightlyError("TASK_CAPABILITY_IDS_INVALID")
    disposition = raw.get("capability_disposition", "EXTEND_EXISTING")
    if disposition not in DONOR_CAPABILITY_DISPOSITIONS:
        raise NightlyError("TASK_CAPABILITY_DISPOSITION_INVALID")
    summary = raw.get("summary", "")
    if not isinstance(summary, str):
        raise NightlyError("TASK_SUMMARY_INVALID")
    return {
        "difficulty": difficulty,
        "allowed_files": list(files),
        "verifiers": argvs,
        "capability_ids": list(ids),
        "capability_disposition": disposition,
        "summary": _one_line(summary, 400),
    }


def is_protected(path: str) -> bool:
    for rule in PROTECTED_PATHS:
        if rule.endswith("*"):
            if path.startswith(rule[:-1]):
                return True
        elif path == rule or path.startswith(rule + "/"):
            return True
    return False


def allowlisted_verifier(argv: list[str]) -> list[str]:
    """Accept only the two verifier shapes a nightly card may authorise; return the card argv.

    * ``python3 -m pytest [-q] [-p no:cacheprovider] tests/<file>.py[::node] ...``
      (``python`` is normalised to ``python3``; no other option, no shell);
    * the exact closure diff check ``sh -c 'git diff --check "$NEXUS_BASE_SHA" ...'``.
    """
    if argv == DIFF_CHECK_ARGV:
        return list(argv)
    if len(argv) < 4 or argv[0] not in ("python", "python3") or argv[1:3] != ["-m", "pytest"]:
        raise NightlyError("TASK_VERIFICATION_NOT_ALLOWLISTED")
    rest, targets = list(argv[3:]), []
    flags: list[str] = []
    while rest:
        part = rest.pop(0)
        if part == "-q" and "-q" not in flags:
            flags.append(part)
        elif part == "-p" and rest[:1] == ["no:cacheprovider"] and "-p" not in flags:
            flags += [part, rest.pop(0)]
        else:
            path = part.split("::", 1)[0]
            if (
                not PYTEST_TARGET_RE.fullmatch(part)
                or ".." in PurePosixPath(path).parts
                or PurePosixPath(path).as_posix() != path
            ):
                raise NightlyError("TASK_VERIFICATION_NOT_ALLOWLISTED")
            targets.append(part)
    if not targets or len(set(targets)) != len(targets):
        raise NightlyError("TASK_VERIFICATION_NOT_ALLOWLISTED")
    return ["python3", "-m", "pytest", *flags, *targets]


def verifier_paths(task: Mapping[str, Any]) -> list[str]:
    return sorted({
        part.split("::", 1)[0]
        for argv in task["verifiers"]
        if argv != DIFF_CHECK_ARGV
        for part in argv[3:]
        if part.startswith("tests/")
    })


def render_card(*, task_id: str, issue: int, title: str, task: Mapping[str, Any]) -> str:
    allowed = "\n".join(f"- `{path}`" for path in task["allowed_files"])
    verify = "\n".join(shlex.join(argv) for argv in task["verifiers"])
    objective = f"Resolve GitHub Issue #{issue}: {_one_line(title, 200)}."
    if task.get("summary"):
        objective += f" {task['summary']}"
    return f"""# Task Card: EIA nightly {task_id}

## Identity

- task_id: `{task_id}`
- campaign_id: `eia-nightly`
- artifact_authority: current
- status: ACTIVE
- owner: James Chen
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false
- allow_deletions: false
- execution_lane: `DIRECT_DELEGATED`
- capability_disposition: `{task["capability_disposition"]}`
- capability_ids: `{", ".join(task["capability_ids"])}`

## Objective

{objective}

The full problem statement is the body of Issue #{issue} (difficulty: {task["difficulty"]}).

## Allowed files

{allowed}

## Required implementation

Change only the allowed files so that the behaviour described in Issue #{issue} holds. Keep
every existing public name and signature working.

## Forbidden scope

No workflow, configuration, dependency, Task Card or control-plane changes; no deletions;
no files outside the allowed list.

## Verification commands

```bash
{verify}
```

## Claim ceiling

`TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE` only. This card grants no approval,
merge, integration or release authority.
"""


def build_contract(entry: Mapping[str, Any], attempt: int, main_sha: str) -> dict[str, Any]:
    task_id = entry["task_id"]
    unit_id = f"{task_id}-a{attempt}"

    def specs(scope: str) -> list[dict[str, Any]]:
        return [
            {"argv": list(argv), "id": f"{scope}-v{i}-a{attempt}", "timeout": 900}
            for i, argv in enumerate(entry["verifiers"], 1)
        ]

    return {
        "active_elsewhere": False,
        "blocked_reasons": [],
        "contract_ready": True,
        "execution_units": [
            {
                "allow_deletions": False,
                "dependencies_ready": True,
                "mutation_paths": list(entry["allowed_files"]),
                "priority": 1,
                "unit_id": unit_id,
            }
        ],
        "main_sha": _sha(main_sha),
        "needs_reconciliation": False,
        "pipeline_mode": "FULL_PIPELINE",
        "ready": True,
        "requested_concurrency": 1,
        "revision": f"n{entry['night']}-a{attempt}",
        "schema": ISSUE_SCHEMA,
        "task_card_hash": entry["card_hash"],
        "task_card_ref": entry["card_ref"],
        "task_id": task_id,
        "unit_verifiers": {unit_id: specs("unit")},
        "whole_verifiers": specs("whole"),
    }


def strip_contract(body: str) -> str:
    return (body or "").split(f"\n\n{CONTRACT_MARKER}", 1)[0].rstrip()


def body_with_contract(body: str, contract: Mapping[str, Any], attempt: int) -> str:
    fence = json.dumps(dict(contract), indent=2, sort_keys=True)
    return (
        f"{strip_contract(body)}\n\n{CONTRACT_MARKER}\n## EIA nightly contract (attempt {attempt})"
        f"\n\n```nexus-external-intelligence\n{fence}\n```"
    )


def validate_contract(
    repo_root: Path, issue: int, title: str, body: str, *, lineage: bool
) -> tuple[str, dict[str, Any]]:
    """Run the daemon's own pre-dispatch validators; return (identity_hash, contract)."""
    try:
        contract = parse_issue_contract(body)
        checker = ExternalIntelligenceAutomation.__new__(ExternalIntelligenceAutomation)
        checker.repository_root = Path(repo_root).expanduser().resolve()
        if lineage:
            checker._validate_source_lineage(REPOSITORY, contract["main_sha"])
        _path, text = checker._task_card(contract)
        authority = checker._validate_task_card_authority(contract, text)
        _require_lane(authority.execution_lane)
        index = subprocess.run(
            [
                "git",
                "cat-file",
                "blob",
                f"{contract['main_sha']}:{CAPABILITY_DISCOVERY_INDEX_PATH}",
            ],
            cwd=checker.repository_root,
            capture_output=True,
            check=False,
            timeout=30,
        )
        build_capability_discovery_receipt(
            repository=REPOSITORY,
            main_sha=contract["main_sha"],
            index_bytes=index.stdout if index.returncode == 0 else None,
            intent=contract["task_id"],
            disposition=authority.capability_disposition,
            matched_capability_ids=authority.capability_ids,
            justification=authority.capability_justification,
            evidence={
                layer: [contract["task_card_ref"]]
                for layer in ("architecture", "source", "history", "runtime")
            },
        )
    except NightlyError:
        raise
    except Exception as exc:  # validator errors carry their code in str(exc)
        raise NightlyError(f"CONTRACT_INVALID:{str(exc) or type(exc).__name__}") from exc
    return IssueWorkItem(REPOSITORY, issue, title, body, contract).identity_hash, contract


def classify(daemon_state: Mapping[str, Any]) -> tuple[str, str]:
    """Return (kind, reason) with kind in wait|complete|infra|model.  Unknown -> model."""
    state = str(daemon_state.get("state") or "")
    if state == "COMPLETE":
        return "complete", state
    if state in WAIT_STATES:
        return "wait", state
    if state in TERMINAL_DISPOSITIONS:
        return "model", state
    result = daemon_state.get("result")
    result = result if isinstance(result, Mapping) else {}
    fields = [daemon_state.get(k) for k in ("error", "stage", "closure_status")]
    fields += [result.get(k) for k in ("error", "status", "reason", "errors")]
    detail = json.dumps(fields, default=str).upper()
    if state == "RECONCILIATION_REQUIRED":
        if str(daemon_state.get("prior_state") or "") in RESUMABLE_PRIOR:
            return "wait", f"{state}:{daemon_state.get('prior_state')}"
        return "infra", f"{state}:RECONCILE_ONLY:{daemon_state.get('prior_state')}"
    if state == "BLOCKED":
        error = str(daemon_state.get("error") or "")
        if any(marker in detail for marker in MODEL_MARKERS):
            return "model", f"BLOCKED:{error or daemon_state.get('closure_status')}"
        if daemon_state.get("stage") == "CLOSURE":
            return "model", f"BLOCKED:CLOSURE:{daemon_state.get('closure_status')}"
        if any(marker in detail for marker in INFRA_MARKERS):
            return "infra", f"BLOCKED:{error or 'TRANSPORT'}"
        if not daemon_state.get("semantic_dispatched") and EXCEPTION_NAME_RE.fullmatch(error):
            return "infra", f"BLOCKED:{error}"
        return "model", f"BLOCKED:{error or 'UNCLASSIFIED'}"
    return "model", f"UNKNOWN_STATE:{state or 'EMPTY'}"


# --------------------------------------------------------------------------- scheduler


class Nightly:
    def __init__(
        self,
        *,
        state_dir: Path,
        eia_config: Path,
        work_repo: Path,
        runner: Runner = default_runner,
        now: Callable[[], dt.datetime] = dt.datetime.now,
        sleep: Callable[[float], None] = time.sleep,
        spawn: Callable[[list[str]], int] | None = None,
        kill: Callable[[int, int], None] = os.kill,
        max_issues: int = 4,
        max_retries: int = 2,
        issue_cap_min: int = 150,
        arm_cutoff: str = "06:00",
        hard_stop: str = "09:00",
        gh: Path = HOME / ".config/nexus-agent-bot/bin/gh",
        git_credential: Path = HOME / ".config/nexus-agent-bot/bin/nexus-agent-git-credential",
        healthcheck: Path = HOME / ".local/share/nexus-open-swe-runtime/bin/eia-healthcheck",
        coord_host: str = "james@100.104.233.2",
        daemon_plist: Path = HOME / "Library/LaunchAgents" / f"{DAEMON_LABEL}.plist",
        trusted_actors: Sequence[str] = tuple(TRUSTED_ACTORS),
        watch_seconds: int = 270,
    ):
        self.watch_seconds = watch_seconds
        self.trusted_actors = frozenset(a.strip().removesuffix("[bot]") for a in trusted_actors)
        self.state_dir = Path(state_dir).expanduser()
        self.work_repo = Path(work_repo).expanduser()
        self.run, self.now, self.sleep, self.kill = runner, now, sleep, kill
        self.spawn = spawn or self._spawn
        self.max_issues, self.max_retries, self.issue_cap_min = (
            max_issues,
            max_retries,
            issue_cap_min,
        )
        self.arm_cutoff, self.hard_stop = arm_cutoff, hard_stop
        self.gh, self.git_credential, self.healthcheck = (
            str(gh),
            str(git_credential),
            str(healthcheck),
        )
        self.coord_host, self.daemon_plist = coord_host, str(daemon_plist)
        config = json.loads(Path(eia_config).expanduser().read_text(encoding="utf-8"))
        self.daemon_repo = Path(config["repository_roots"][REPOSITORY]).expanduser()
        self.eia_state_root = Path(config["state_root"]).expanduser().resolve()
        self.opencli = str(config.get("opencli_executable") or "opencli")

    # ---- plumbing -------------------------------------------------------------------
    @staticmethod
    def _spawn(argv: list[str]) -> int:
        proc = subprocess.Popen(  # noqa: S603 - fixed argv list
            argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
        )
        return proc.pid

    def _ok(self, argv: list[str], *, code: str, **kw: Any) -> str:
        result = self.run(argv, **kw)
        if result.returncode != 0:
            tail = str(result.stderr or result.stdout or "")[-300:].strip()
            raise NightlyError(f"{code}:{tail}")
        return str(result.stdout or "")

    def _ghj(self, *args: str) -> Any:
        return json.loads(self._ok([self.gh, *args], code="GH_FAILED") or "null")

    def _git(self, repo: Path, *args: str, code: str = "GIT_FAILED", **kw: Any) -> str:
        return self._ok(["git", "-C", str(repo), *args], code=code, **kw).strip()

    def _push(self, repo: Path, sha: str, branch: str) -> None:
        ref = f"refs/heads/{branch}"
        remote = self._git(repo, "ls-remote", "origin", "--", ref, code="LS_REMOTE_FAILED")
        if remote:
            if remote.split()[0] != sha:
                raise NightlyError(f"REMOTE_BRANCH_CONFLICT:{branch}")
            return
        helper = f"credential.helper=!{self.git_credential}"
        argv = ["git", "-C", str(repo), "-c", "credential.helper=", "-c", helper, "push"]
        self._ok([*argv, "origin", "--", f"{sha}:{ref}"], code="PUSH_FAILED", timeout=180)

    def _is_ancestor(self, repo: Path, older: str, newer: str) -> bool:
        argv = ["git", "-C", str(repo), "merge-base", "--is-ancestor", older, newer]
        return self.run(argv).returncode == 0

    def _fetch_main(self) -> str:
        refspec = "+refs/heads/main:refs/remotes/origin/main"
        self._git(
            self.work_repo,
            "fetch",
            "--no-tags",
            "origin",
            refspec,
            code="FETCH_FAILED",
            timeout=180,
        )
        return _sha(
            self._git(self.work_repo, "rev-parse", "--verify", "refs/remotes/origin/main^{commit}")
        )

    def _gh_file(self, args: list[str], text: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write(text)
        try:
            return self._ok([self.gh, *args, "--body-file", fh.name], code="GH_WRITE_FAILED")
        finally:
            os.unlink(fh.name)

    def _labels(self, issue: int, add: Sequence[str] = (), remove: Sequence[str] = ()) -> None:
        args = ["issue", "edit", str(issue), "--repo", REPOSITORY]
        for label in add:
            args += ["--add-label", label]
        for label in remove:
            args += ["--remove-label", label]
        self._ok([self.gh, *args], code="GH_LABEL_FAILED")

    def _comment_once(self, issue: int, marker: str, text: str) -> None:
        path = f"repos/{REPOSITORY}/issues/{issue}/comments"
        bodies = self._ok(
            [self.gh, "api", "--paginate", path, "--jq", ".[].body"], code="GH_COMMENTS_FAILED"
        )
        if marker not in bodies:
            self._gh_file(
                ["issue", "comment", str(issue), "--repo", REPOSITORY], f"{marker}\n{text}"
            )

    def _pr_for_branch(self, branch: str) -> list[dict[str, Any]]:
        args = f"pr list --repo {REPOSITORY} --state all --json number,headRefOid --head"
        return self._ghj(*args.split(), branch) or []

    def _view_issue(self, issue: int) -> dict[str, Any]:
        value = self._ghj(
            *f"issue view {issue} --repo {REPOSITORY} --json number,title,body,labels,state".split()
        )
        value["label_names"] = {row.get("name") for row in value.get("labels") or []}
        return value

    def _queue_msg(self, night: dict[str, Any], key: str, target: str, note: str) -> None:
        night.setdefault("outbox", {}).setdefault(
            key, {"target": target, "note": note, "sent": False}
        )

    def _flush_outbox(self, night: dict[str, Any]) -> None:
        for key, msg in sorted((night.get("outbox") or {}).items()):
            if msg.get("sent"):
                continue
            note = re.sub(r"[\x00-\x1f]+", " ", str(msg["note"]))[:1800]
            remote = "~/workspace/agent-coord/bin/coord " + shlex.join([
                "msg",
                msg["target"],
                "--as",
                COORD_AS,
                "--note",
                note,
            ])
            result = self.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", self.coord_host, remote],
                timeout=60,
            )
            msg["sent"] = result.returncode == 0
            msg["last_try"] = self._iso()
            if msg["sent"]:
                self._event(night, "coord_sent", key=key)

    def _notify(self, text: str) -> None:
        safe = _one_line(text, 200).replace('"', "'")
        self.run(
            ["osascript", "-e", f'display notification "{safe}" with title "EIA nightly"'],
            timeout=20,
        )

    # ---- state ----------------------------------------------------------------------
    def path(self, night: str) -> Path:
        return self.state_dir / f"{night}.json"

    def load(self, night: str) -> dict[str, Any] | None:
        path = self.path(night)
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("schema") != STATE_SCHEMA or value.get("night") != night:
            raise NightlyError("NIGHT_STATE_INVALID")
        return value

    def save(self, night: dict[str, Any]) -> None:
        path = self.path(night["night"])
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(night, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)

    def _event(self, night: dict[str, Any], event: str, **data: Any) -> None:
        night.setdefault("events", []).append({
            "at": self._iso(),
            "event": event,
            **data,
        })

    @contextlib.contextmanager
    def locked(self) -> Iterator[bool]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with open(self.state_dir / ".lock", "a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def paused(self) -> bool:
        return (self.state_dir / "PAUSE").exists()

    # ---- prepare --------------------------------------------------------------------
    def prepare(self, night_id: str | None = None) -> dict[str, Any]:
        night_id = night_id or night_of(self.now())
        night = self.load(night_id)
        if night and night.get("card_pr"):
            if not night["card_pr"].get("number"):
                return self._open_card_pr(night)
            self.refresh_card_pr(night)
            return night
        night = night or {"schema": STATE_SCHEMA, "night": night_id, "issues": {}, "order": []}
        self._ensure_labels()
        rows = self._ghj(
            *f"issue list --repo {REPOSITORY} --state open --label {L_QUEUE} --limit 100".split(),
            *("--json", "number,title,body,labels"),
        )
        picked: list[dict[str, Any]] = []
        commit, base, ledger = "", self._fetch_main(), self._ledger()
        for row in sorted(rows or [], key=lambda r: int(r.get("number") or 0)):
            number = _issue_number(row.get("number"))
            names = {label.get("name") for label in row.get("labels") or []}
            if L_QUEUE not in names or names & SKIP_LABELS:
                continue
            trusted, why = self._queue_trusted(number)
            if not trusted:  # never touch an Issue queued or edited by someone else
                self._event(night, "untrusted_skipped", issue=number, reason=why)
                continue
            if len(ledger.get(str(number), {}).get("nights", [])) >= MAX_NIGHTS_WITHOUT_CANDIDATE:
                self._escalate_issue(
                    number,
                    f"<!-- eia-nightly:cross-night-cap:{number} -->",
                    f"EIA nightly stopped scheduling this Issue: {MAX_NIGHTS_WITHOUT_CANDIDATE} "
                    "nights attempted without a candidate PR.",
                )
                continue
            try:
                task = parse_task_block(str(row.get("body") or ""))
                if task["difficulty"] == "hard":
                    raise NightlyError("TASK_DIFFICULTY_HARD_NOT_SCHEDULED")
                self._check_paths(base, task)
            except NightlyError as exc:
                self._needs_template(night, number, str(exc))
                continue
            if len(picked) >= self.max_issues:
                continue
            task_id = f"eia-nightly-{night_id}-i{number}"
            picked.append({
                "issue": number,
                "title": _one_line(row.get("title"), 200),
                "task_id": task_id,
                "night": night_id,
                "card_ref": f"{CARD_DIR}/{night_id}/issue-{number}.md",
                "status": "PREPARED",
                "attempts": [],
                **task,
            })
        for _round in range(2):
            if not picked:
                break
            commit = self._card_commit(night_id, picked, base)
            bad = []
            for entry in picked:
                contract = build_contract(entry, 1, commit)
                try:
                    validate_contract(
                        self.work_repo,
                        entry["issue"],
                        entry["title"],
                        body_with_contract("", contract, 1),
                        lineage=False,
                    )
                except NightlyError as exc:
                    bad.append(entry)
                    self._needs_template(night, entry["issue"], str(exc))
            if not bad:
                break
            picked = [entry for entry in picked if entry not in bad]
        else:
            picked = []
        if not picked:
            night["status"] = "NO_TASKS"
            self._event(night, "prepare_no_tasks")
            self.save(night)
            return night
        night["issues"] = {str(e["issue"]): e for e in picked}
        night["order"] = [e["issue"] for e in picked]
        branch = f"eia-nightly/cards-{night_id}"
        night["card_pr"] = {"branch": branch, "commit": commit, "number": None, "merged": False}
        night["status"] = "CARDS_PENDING"
        self.save(night)  # write-ahead before any remote effect
        return self._open_card_pr(night)

    def _open_card_pr(self, night: dict[str, Any]) -> dict[str, Any]:
        night_id, pr = night["night"], night["card_pr"]
        branch, commit = pr["branch"], _sha(pr["commit"])
        picked = [night["issues"][str(n)] for n in night["order"]]
        self._push(self.work_repo, commit, branch)
        tracking = self._tracking_issue()
        existing = self._pr_for_branch(branch)
        if existing:
            number = _issue_number(existing[0]["number"])
        else:
            listing = "\n".join(f"- `{e['card_ref']}` for #{e['issue']}" for e in picked)
            body = (
                f"EIA nightly task cards for night {night_id}, generated by "
                f"`scripts/ops/eia_nightly.py prepare`. Task Card files only:\n\n{listing}\n\n"
                "Each card was validated with the EIA daemon's own validators "
                "(`parse_issue_contract`, `_task_card`, `_validate_task_card_authority`, Core lane "
                "and capability checks). Merging lets tonight's run arm these Issues; it changes "
                f"no code. Tracking: #{tracking}.\n\n"
                f"<!-- NEXUS_CORE_ISSUE: {tracking} -->\n<!-- NEXUS_ISSUE_INTENT_V1\n"
                f'[{{"issue": {tracking}, "on_merge": "KEEP_OPEN"}}]\nNEXUS_ISSUE_INTENT_V1 -->\n\n'
                "🤖 Generated with [Claude Code](https://claude.com/claude-code)\n"
            )
            url = self._gh_file(
                [
                    *f"pr create --repo {REPOSITORY} --base main --head".split(),
                    branch,
                    "--title",
                    f"tasks: EIA nightly task cards {night_id}",
                ],
                body,
            )
            number = _number_from_url(url)
        head = _sha(
            self._ghj("pr", "view", str(number), "--repo", REPOSITORY, "--json", "headRefOid")[
                "headRefOid"
            ]
        )
        if head != commit:
            raise NightlyError("CARD_PR_HEAD_MISMATCH")
        pr.update(number=number, head_sha=head, tracking_issue=tracking)
        self._queue_msg(
            night,
            f"ready-cards-{number}",
            "merge-queue",
            f"READY Nexus-new#{number} head {head}; EIA nightly Task Cards for night "
            f"{night_id} (only {CARD_DIR}/{night_id}/*.md, {len(picked)} cards, validated "
            "with the daemon validators); high-risk no; please review/merge per normal "
            "rules before 23:30. Sent by m4-eia-nightly (unattended).",
        )
        self._event(night, "card_pr_opened", number=number, head=head)
        self.save(night)
        self._flush_outbox(night)
        self.save(night)
        return night

    def _trusted(self, login: Any) -> bool:
        return isinstance(login, str) and login.removesuffix("[bot]") in self.trusted_actors

    def _queue_trusted(self, issue: int) -> tuple[bool, str]:
        """The latest ``eia:queue`` label, and every title/body edit after it, by a trusted actor."""
        try:
            return self._queue_trusted_unchecked(issue)
        except (NightlyError, ValueError, TypeError, AttributeError) as exc:
            return False, f"TRUST_CHECK_FAILED:{_one_line(exc, 120)}"

    def _queue_trusted_unchecked(self, issue: int) -> tuple[bool, str]:
        jq = (
            '.[] | select(.event=="labeled" or .event=="renamed") | '
            "{event, label: .label.name, actor: .actor.login, at: .created_at}"
        )
        out = self._ok(
            [
                self.gh,
                "api",
                "--paginate",
                f"repos/{REPOSITORY}/issues/{issue}/timeline",
                "--jq",
                jq,
            ],
            code="GH_TIMELINE_FAILED",
        )
        events = [json.loads(line) for line in out.splitlines() if line.strip()]
        labeled = [e for e in events if e.get("event") == "labeled" and e.get("label") == L_QUEUE]
        if not labeled:
            return False, "QUEUE_LABEL_EVENT_MISSING"
        last = max(labeled, key=lambda e: _ts(e.get("at")))
        if not self._trusted(last.get("actor")):
            return False, f"QUEUE_LABELED_BY_UNTRUSTED:{_one_line(last.get('actor'), 60)}"
        since = _ts(last.get("at"))
        for e in events:
            if e.get("event") == "renamed" and _ts(e.get("at")) > since:
                if not self._trusted(e.get("actor")):
                    return False, "TITLE_EDITED_BY_UNTRUSTED"
        owner, name = REPOSITORY.split("/")
        query = (
            f'query($num:Int!){{repository(owner:"{owner}",name:"{name}"){{issue(number:$num)'
            "{userContentEdits(first:100){totalCount nodes{editedAt editor{login}}}}}}"
        )
        data = self._ghj("api", "graphql", "-f", f"query={query}", "-F", f"num={issue}")
        edits = (((data or {}).get("data") or {}).get("repository") or {}).get("issue") or {}
        edits = edits.get("userContentEdits") or {}
        nodes = edits.get("nodes")
        if not isinstance(nodes, list):
            return False, "EDIT_HISTORY_UNREADABLE"
        for node in nodes:
            if _ts(node.get("editedAt")) > since:
                if not self._trusted((node.get("editor") or {}).get("login")):
                    return False, "BODY_EDITED_BY_UNTRUSTED"
        if int(edits.get("totalCount") or 0) > len(nodes) and (
            not nodes or min(_ts(n.get("editedAt")) for n in nodes) > since
        ):
            return False, "EDIT_HISTORY_TRUNCATED"
        return True, ""

    def _tree_mode(self, base: str, path: str) -> str | None:
        out = self._git(self.work_repo, "ls-tree", base, "--", path)
        return out.split()[0] if out else None

    def _check_paths(self, base: str, task: Mapping[str, Any]) -> None:
        """No symlinks at main; allowed files exist or their parent directory does;
        verifier test files exist or are allowed files."""
        for path in [*task["allowed_files"], *verifier_paths(task)]:
            parts = PurePosixPath(path).parts
            for depth in range(1, len(parts)):
                if self._tree_mode(base, "/".join(parts[:depth])) != "040000":
                    raise NightlyError(f"TASK_PATH_PARENT_INVALID:{path}")
            mode = self._tree_mode(base, path)
            if mode not in (None, "100644", "100755"):
                raise NightlyError(f"TASK_PATH_NOT_REGULAR_FILE:{path}")
            if mode is None and path not in task["allowed_files"]:
                raise NightlyError(f"TASK_VERIFIER_TARGET_MISSING:{path}")

    def _ledger(self) -> dict[str, Any]:
        path = self.state_dir / "issues.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _update_ledger(self, night: Mapping[str, Any]) -> None:
        ledger = self._ledger()
        for number in night.get("order", []):
            entry = night["issues"][str(number)]
            row = ledger.setdefault(str(number), {"nights": []})
            if entry["status"] == "CANDIDATE_PR":
                row["nights"] = []
            elif entry.get("attempts") and night["night"] not in row["nights"]:
                row["nights"].append(night["night"])
        path = self.state_dir / "issues.json"
        fd, tmp = tempfile.mkstemp(prefix=".issues.", dir=self.state_dir)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(ledger, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)

    def _escalate_issue(self, issue: int, marker: str, text: str) -> None:
        self._labels(issue, add=[L_ESCALATE], remove=[L_EIA])
        self._comment_once(issue, marker, text)

    def _needs_template(self, night: dict[str, Any], issue: int, reason: str) -> None:
        self._labels(issue, add=[L_TEMPLATE])
        self._comment_once(
            issue,
            f"<!-- eia-nightly:needs-template:{night['night']} -->",
            f"EIA nightly skipped this Issue: `{_one_line(reason, 300)}`.{self._capability_hint(reason)}"
            "\n\nFix the ```eia-task "
            "block (see `docs/ops/eia_nightly.md`; hard tasks are not run nightly), then remove "
            f"the `{L_TEMPLATE}` label.",
        )
        self._event(night, "needs_template", issue=issue, reason=reason)

    def _capability_hint(self, reason: str) -> str:
        if "CAPABILITY" not in reason:
            return ""
        spec = f"refs/remotes/origin/main:{CAPABILITY_DISCOVERY_INDEX_PATH}"
        out = self.run(["git", "-C", str(self.work_repo), "show", spec])
        try:
            ids = [c["id"] for c in json.loads(out.stdout)["capabilities"]]
        except (ValueError, KeyError, TypeError):
            return ""
        return " `capability_ids` is required; valid ids: " + ", ".join(f"`{i}`" for i in ids) + "."

    def _ensure_labels(self) -> None:
        have = {
            row.get("name")
            for row in self._ghj(
                *f"label list --repo {REPOSITORY} --search eia --json name --limit 100".split()
            )
            or []
        }
        for name in (L_QUEUE, L_ESCALATE, L_TEMPLATE, L_CANDIDATE):
            if name not in have:
                self._ok(
                    [self.gh, "label", "create", name, "--repo", REPOSITORY],
                    code="GH_LABEL_CREATE_FAILED",
                )

    def _tracking_issue(self) -> int:
        rows = self._ghj(
            *f"issue list --repo {REPOSITORY} --state open --json number,title".split(),
            *("--search", f'in:title "{TRACKING_TITLE}"'),
        )
        for row in rows or []:
            if row.get("title") == TRACKING_TITLE:
                return _issue_number(row["number"])
        url = self._gh_file(
            ["issue", "create", "--repo", REPOSITORY, "--title", TRACKING_TITLE],
            "Standing KEEP_OPEN tracking Issue for the nightly EIA Task Card PRs opened by "
            "`scripts/ops/eia_nightly.py prepare`. Do not close.",
        )
        return _number_from_url(url)

    def _card_commit(self, night_id: str, entries: list[dict[str, Any]], base: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(
                os.environ,
                GIT_INDEX_FILE=str(Path(tmp) / "index"),
                GIT_AUTHOR_NAME=BOT_NAME,
                GIT_AUTHOR_EMAIL=BOT_EMAIL,
                GIT_COMMITTER_NAME=BOT_NAME,
                GIT_COMMITTER_EMAIL=BOT_EMAIL,
            )
            self._git(self.work_repo, "read-tree", "--", base, env=env)
            for entry in entries:
                card = render_card(
                    task_id=entry["task_id"], issue=entry["issue"], title=entry["title"], task=entry
                ).encode("utf-8")
                entry["card_hash"] = _sha256(card)
                blob = _sha(
                    self._git(
                        self.work_repo, "hash-object", "-w", "--stdin", input=card.decode("utf-8")
                    )
                )
                entry["card_blob"] = blob
                self._git(
                    self.work_repo,
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    f"100644,{blob},{entry['card_ref']}",
                    env=env,
                )
            tree = self._git(self.work_repo, "write-tree", env=env)
            return _sha(
                self._git(
                    self.work_repo,
                    "commit-tree",
                    tree,
                    "-p",
                    base,
                    "-m",
                    f"tasks: EIA nightly task cards {night_id}",
                    env=env,
                )
            )

    def refresh_card_pr(self, night: dict[str, Any]) -> bool:
        pr = night.get("card_pr") or {}
        if pr.get("merged"):
            return True
        if not pr.get("number"):
            return False
        view = self._ghj(
            "pr", "view", str(pr["number"]), "--repo", REPOSITORY, "--json", "state,mergeCommit"
        )
        if view.get("state") != "MERGED":
            pr["state"] = view.get("state")
            return False
        merge_sha = _sha((view.get("mergeCommit") or {}).get("oid"))
        main = self._fetch_main()
        if not self._is_ancestor(self.work_repo, merge_sha, main):
            raise NightlyError("CARD_MERGE_NOT_ON_MAIN")
        for entry in night["issues"].values():
            spec = f"{merge_sha}:{entry['card_ref']}"
            raw = self.run(["git", "-C", str(self.work_repo), "rev-parse", "--verify", "-q", spec])
            entry["merged_card_blob"] = str(raw.stdout).strip() if raw.returncode == 0 else None
            if entry["merged_card_blob"] != entry["card_blob"]:
                entry["status"] = "CARD_DRIFT"
        pr.update(merged=True, merge_sha=merge_sha)
        self._event(night, "card_pr_merged", merge_sha=merge_sha)
        return True

    # ---- start ----------------------------------------------------------------------
    def start(self) -> dict[str, Any]:
        night_id = night_of(self.now())
        night = self.load(night_id) or {
            "schema": STATE_SCHEMA,
            "night": night_id,
            "issues": {},
            "order": [],
            "status": "NO_TASKS",
        }
        if (night.get("started") or {}).get("ok"):
            return night
        if not night.get("issues"):
            night["status"] = "SKIPPED_NO_TASKS"
        elif not self.refresh_card_pr(night):
            night["status"] = "SKIPPED_CARD_PR_NOT_MERGED"
        if str(night.get("status", "")).startswith("SKIPPED"):
            self._queue_msg(
                night,
                "skip",
                "coordinator",
                f"EIA nightly {night_id}: {night['status']} (card PR "
                f"{(night.get('card_pr') or {}).get('number')}); daemon not started.",
            )
            self.save(night)
            return night
        started: dict[str, Any] = {"at": self._iso()}
        night["started"] = started
        seconds = int((night_clock(night_id, self.hard_stop) - self.now()).total_seconds()) + 1800
        pid = night.get("caffeinate_pid")
        if not (pid and self._is_caffeinate(pid)):
            night["caffeinate_pid"] = self.spawn([
                "caffeinate",
                "-dimsu",
                "-t",
                str(max(seconds, 60)),
            ])
        self.save(night)
        try:
            self._check_daemon_python()
            self._ensure_bridge()
            self._ensure_daemon()
            for attempt in range(3):
                if self.run([self.healthcheck], timeout=300).returncode == 0:
                    break
                if attempt < 2:
                    self.sleep(60)
            else:
                raise NightlyError("HEALTHCHECK_FAILED")
        except NightlyError as exc:
            started.update(ok=False, error=str(exc))
            night["status"] = "START_FAILED"
            self._queue_msg(
                night,
                "start-failed",
                "coordinator",
                f"EIA nightly {night_id}: START_FAILED {exc}; nothing will be armed.",
            )
            self.save(night)
            return night
        started["ok"] = True
        night["status"] = "RUNNING"
        self._event(night, "started")
        self.save(night)
        return night

    def _check_daemon_python(self) -> None:
        """Cards run plain ``python3``: it must import Nexus under the daemon's PATH."""
        try:
            plist = plistlib.loads(Path(self.daemon_plist).read_bytes())
            path = str(plist["EnvironmentVariables"]["PATH"])
        except (OSError, KeyError, TypeError, ValueError, plistlib.InvalidFileException) as exc:
            raise NightlyError("DAEMON_PLIST_PATH_UNREADABLE") from exc
        argv = ["/usr/bin/env", "-i", f"PATH={path}", f"HOME={HOME}", "python3", "-c"]
        if self.run(
            [*argv, "import nexus, pytest"], cwd=str(self.daemon_repo), timeout=60
        ).returncode:
            raise NightlyError("DAEMON_PYTHON3_CANNOT_IMPORT_NEXUS")

    def _bridge_connected(self) -> bool:
        out = self.run([self.opencli, "daemon", "status"], timeout=30)
        return bool(re.search(r"extension:\s*connected", str(out.stdout), re.IGNORECASE))

    def _ensure_bridge(self) -> None:
        if self._bridge_connected():
            return
        self.run(["open", "-a", "Google Chrome"], timeout=30)
        self.sleep(5)
        self.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to tell process "Google Chrome" to click '
                'menu item "ibase" of menu 1 of menu bar item "設定檔" of menu bar 1',
            ],
            timeout=30,
        )
        for _ in range(20):
            self.sleep(15)
            if self._bridge_connected():
                return
        raise NightlyError("BROWSER_BRIDGE_NOT_CONNECTED")

    def _daemon_state(self) -> str:
        out = self.run(["launchctl", "print", f"gui/{os.getuid()}/{DAEMON_LABEL}"], timeout=20)
        text = str(out.stdout) + str(out.stderr)
        if "Could not find service" in text:
            return "absent"
        if out.returncode != 0:
            raise NightlyError("LAUNCHCTL_PRINT_FAILED")
        return "running" if re.search(r"^\s*state = running", text, re.M) else "loaded"

    def _ensure_daemon(self) -> None:
        state = self._daemon_state()
        domain = f"gui/{os.getuid()}"
        if state == "absent":
            self._ok(["launchctl", "bootstrap", domain, self.daemon_plist], code="BOOTSTRAP_FAILED")
        elif state == "loaded":
            self._ok(
                ["launchctl", "kickstart", f"{domain}/{DAEMON_LABEL}"], code="KICKSTART_FAILED"
            )
        for _ in range(6):
            if self._daemon_state() == "running":
                return
            self.sleep(10)
        raise NightlyError("DAEMON_NOT_RUNNING")

    def _is_caffeinate(self, pid: int) -> bool:
        out = self.run(["ps", "-p", str(int(pid)), "-o", "comm="], timeout=10)
        return out.returncode == 0 and str(out.stdout).strip().endswith("caffeinate")

    # ---- dispatch -------------------------------------------------------------------
    def dispatch(self) -> dict[str, Any]:
        night = self.load(night_of(self.now()))
        if not night:
            return {"status": "IDLE"}
        if not (night.get("started") or {}).get("ok") or night.get("finalized"):
            self._flush_outbox(night)  # retry unsent coord messages only
            self.save(night)
            return night
        try:
            for entry in self._entries(night, "ARMING"):  # resume an interrupted arming
                self._arm(night, entry)
            for entry in self._entries(night, "ARMED"):
                self._harvest(night, entry)
                self.save(night)
            self._watch(night)
            now, busy = (
                self.now(),
                bool(self._entries(night, "ARMED") or self._entries(night, "ARMING")),
            )
            if now >= night_clock(night["night"], self.hard_stop) or (
                night.get("stop_requested_at") and not busy
            ):
                self.finalize(night)
            elif not night.get("stop_requested_at") and not busy:
                nxt = self._entries(night, "PREPARED") + self._entries(night, "RETRY_PENDING")
                if nxt and now < night_clock(night["night"], self.arm_cutoff):
                    if not self._foreign_in_flight():
                        self._arm(night, min(nxt, key=lambda e: night["order"].index(e["issue"])))
        finally:
            self._flush_outbox(night)
            self.save(night)
        return night

    def _watch(self, night: dict[str, Any]) -> None:
        """Poll the local daemon state file (no GitHub) every 20 s while an Issue is in flight,
        so a terminal result is disarmed within seconds instead of at the next 5-min tick."""
        for _ in range(int(self.watch_seconds // WATCH_INTERVAL)):
            armed = self._entries(night, "ARMED")
            if not armed:
                return
            att = armed[0]["attempts"][-1]
            record = self._daemon_record(int(armed[0]["issue"]), att["identity_hash"])
            if record is not None:
                kind = classify(record)[0]
                published = (record.get("publication_record") or {}).get("state") == "COMPLETED"
                if kind in ("infra", "model") or (kind == "complete" and published):
                    self._harvest(night, armed[0])
                    self.save(night)
                    return
            self.sleep(WATCH_INTERVAL)

    @staticmethod
    def _entries(night: Mapping[str, Any], status: str) -> list[dict[str, Any]]:
        return [
            night["issues"][str(n)]
            for n in night.get("order", [])
            if night["issues"][str(n)]["status"] == status
        ]

    def _foreign_in_flight(self) -> bool:
        args = f"issue list --repo {REPOSITORY} --state open --json number --label {L_EIA}"
        return bool(self._ghj(*args.split()))

    def _arm(self, night: dict[str, Any], entry: dict[str, Any]) -> None:
        issue = _issue_number(entry["issue"])
        pr = night.get("card_pr") or {}
        if not pr.get("merged") or entry.get("merged_card_blob") != entry["card_blob"]:
            raise NightlyError("CARD_NOT_MERGED")
        view = self._view_issue(issue)
        if (
            view.get("state") != "OPEN"
            or L_QUEUE not in view["label_names"]
            or (view["label_names"] & {L_ESCALATE, L_TEMPLATE, L_CANDIDATE})
        ):
            entry["status"] = "SKIPPED_LABELS_CHANGED"
            if L_EIA in view["label_names"] and L_QUEUE in view["label_names"]:
                self._labels(issue, remove=[L_EIA])
            self._event(night, "arm_skipped", issue=issue)
            return
        trusted, why = self._queue_trusted(issue)
        if not trusted:  # disarm only; never write to an Issue someone else controls
            entry["status"] = "SKIPPED_UNTRUSTED"
            if L_EIA in view["label_names"]:
                self._labels(issue, remove=[L_EIA])
            self._event(night, "arm_untrusted", issue=issue, reason=why)
            return
        resume = entry["status"] == "ARMING"
        record: dict[str, Any] = entry["attempts"][-1] if resume else {}
        if resume:
            attempt, main_sha = int(record["attempt"]), _sha(record["main_sha"])
        else:
            attempt, main_sha = len(entry["attempts"]) + 1, self._fetch_main()
        contract = build_contract(entry, attempt, main_sha)
        new_body = body_with_contract(str(view.get("body") or ""), contract, attempt)
        try:
            identity, _ = validate_contract(
                self.work_repo, issue, view["title"], new_body, lineage=True
            )
        except NightlyError as exc:
            return self._escalate(night, entry, "model", f"ARM_VALIDATION_FAILED:{exc}")
        if resume and identity != record["identity_hash"]:
            return self._escalate(night, entry, "model", "ARM_RESUME_IDENTITY_MISMATCH")
        if not resume:
            record = {
                "attempt": attempt,
                "revision": contract["revision"],
                "unit_id": contract["execution_units"][0]["unit_id"],
                "main_sha": main_sha,
                "identity_hash": identity,
                "body_sha256": _sha256(new_body.encode("utf-8")),
                "armed_at": self._iso(),
            }
            entry["attempts"].append(record)
            entry["status"] = "ARMING"
            self.save(night)
        if view.get("body") != new_body:
            if L_EIA in view["label_names"]:
                self._labels(issue, remove=[L_EIA])
            self._gh_file(["issue", "edit", str(issue), "--repo", REPOSITORY], new_body)
            view = self._view_issue(issue)
        # byte-identical read-back, and the daemon will derive exactly this identity
        if view.get("body") != new_body or self._body_identity(issue, view) != identity:
            return self._escalate(night, entry, "model", "ARM_READBACK_MISMATCH")
        if L_EIA not in view["label_names"]:
            self._labels(issue, add=[L_EIA])  # the arming mutation, always last
        record["armed_at"] = self._iso()
        entry["status"] = "ARMED"
        self._event(night, "armed", issue=issue, attempt=attempt, identity=identity)

    @staticmethod
    def _body_identity(issue: int, view: Mapping[str, Any]) -> str:
        try:
            body = str(view.get("body") or "")
            contract = parse_issue_contract(body)
            return IssueWorkItem(
                REPOSITORY, issue, str(view.get("title") or ""), body, contract
            ).identity_hash
        except Exception:
            return ""

    def _daemon_record(self, issue: int, identity: str) -> dict[str, Any] | None:
        if not re.fullmatch(r"[0-9a-f]{64}", identity):
            raise NightlyError("IDENTITY_INVALID")
        repo = re.sub(r"[^A-Za-z0-9_.-]+", "_", REPOSITORY)
        path = self.eia_state_root / "automation" / repo / f"issue-{issue}-{identity}.json"
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("identity_hash") != identity or value.get("issue_number") != issue:
            raise NightlyError("DAEMON_STATE_IDENTITY_MISMATCH")
        return value

    def _iso(self) -> str:
        return self.now().isoformat(timespec="seconds")

    def _minutes_since(self, iso: str) -> float:
        return (self.now() - dt.datetime.fromisoformat(iso)).total_seconds() / 60

    def _harvest(self, night: dict[str, Any], entry: dict[str, Any]) -> None:
        issue, att = _issue_number(entry["issue"]), entry["attempts"][-1]
        view = self._view_issue(issue)
        body_sha = _sha256(str(view.get("body") or "").encode("utf-8"))
        if body_sha != att.get("body_sha256") or L_QUEUE not in view["label_names"]:
            # The daemon's semantic request embeds the Issue body: a changed body or a
            # withdrawn queue label must stop the run before anything else is sent.
            return self._escalate(night, entry, "model", "ISSUE_CHANGED_AFTER_ARMING")
        record = self._daemon_record(issue, att["identity_hash"])
        age = self._minutes_since(att["armed_at"])
        if record is None:
            if age > self.issue_cap_min:
                self._infra(night, entry, "NO_DAEMON_STATE_WITHIN_CAP")
            return
        kind, reason = classify(record)
        att["daemon_state"] = record.get("state")
        if kind == "complete":
            pub = (record.get("publication_record") or {}).get("state")
            att.setdefault("complete_seen_at", self._iso())
            if (
                pub != "COMPLETED"
                and self._minutes_since(att["complete_seen_at"]) < PUBLICATION_GRACE_MIN
            ):
                return
            try:
                sha, rows = self._verify_candidate(entry, record)
            except NightlyError as exc:
                return self._escalate(night, entry, "model", f"CANDIDATE_REJECTED:{exc}")
            self._candidate_pr(night, entry, record, sha, rows)  # GitHub errors retry next tick
        elif kind == "wait":
            if age > self.issue_cap_min:
                self._infra(night, entry, f"ISSUE_CAP_EXCEEDED:{reason}")
        elif kind == "infra":
            self._infra(night, entry, reason)
        else:
            self._escalate(night, entry, "model", reason)

    def _infra(self, night: dict[str, Any], entry: dict[str, Any], reason: str) -> None:
        entry["attempts"][-1].update(result="infra", reason=reason, finished_at=self._iso())
        self._labels(entry["issue"], remove=[L_EIA])
        if (
            len(entry["attempts"]) <= self.max_retries
            and self.now() < night_clock(night["night"], self.arm_cutoff)
            and not night.get("stop_requested_at")
        ):
            entry["status"] = "RETRY_PENDING"
            self._event(night, "retry_pending", issue=entry["issue"], reason=reason)
        else:
            self._escalate(night, entry, "infra", f"INFRA_RETRIES_EXHAUSTED:{reason}")

    def _escalate(
        self, night: dict[str, Any], entry: dict[str, Any], kind: str, reason: str
    ) -> None:
        issue = _issue_number(entry["issue"])
        if entry["attempts"]:
            entry["attempts"][-1].setdefault("finished_at", self._iso())
            entry["attempts"][-1].setdefault("result", kind)
            entry["attempts"][-1].setdefault("reason", reason)
        self._escalate_issue(
            issue,
            f"<!-- eia-nightly:escalate:{entry['task_id']}-a{len(entry['attempts'])} -->",
            f"EIA nightly escalated this Issue ({kind}): `{_one_line(reason, 400)}`.\n\n"
            f"Attempts: {len(entry['attempts'])}. Night state: `{self.path(night['night'])}`.",
        )
        entry.update(status="ESCALATED", escalation={"kind": kind, "reason": reason})
        self._event(night, "escalated", issue=issue, kind=kind, reason=reason)

    def _verify_candidate(
        self, entry: Mapping[str, Any], record: Mapping[str, Any]
    ) -> tuple[str, list[list[str]]]:
        """Check the daemon's COMPLETE receipt against git before anything is pushed."""
        att = entry["attempts"][-1]
        pub = record.get("publication") or {}
        sha = _sha(pub.get("candidate_commit"))
        if (
            pub.get("verification_state") != "WHOLE_TASK_PASS"
            or pub.get("task_id") != entry["task_id"]
        ):
            raise NightlyError("PUBLICATION_NOT_WHOLE_TASK_PASS")
        packet_path = Path(str(pub.get("acceptance_packet_ref") or "")).resolve()
        if not packet_path.is_relative_to(self.eia_state_root) or not packet_path.is_file():
            raise NightlyError("ACCEPTANCE_PACKET_MISSING")
        raw = packet_path.read_bytes()
        packet = json.loads(raw)
        if (
            _sha256(raw) != pub.get("acceptance_packet_sha256")
            or (packet.get("task_candidate") or {}).get("candidate_commit") != sha
            or packet.get("task_card_hash") != entry["card_hash"]
        ):
            raise NightlyError("ACCEPTANCE_PACKET_MISMATCH")
        repo = self.daemon_repo
        if self._git(repo, "cat-file", "-t", sha) != "commit":
            raise NightlyError("CANDIDATE_NOT_COMMIT")
        if not self._is_ancestor(repo, _sha(att["main_sha"]), sha):
            raise NightlyError("CANDIDATE_NOT_ON_MAIN_SHA")
        status = self._git(
            repo, "diff", "--name-status", "--no-renames", att["main_sha"], sha, "--"
        )
        rows = [line.split("\t", 1) for line in status.splitlines() if line.strip()]
        if not rows or any(
            kind == "D" or path not in entry["allowed_files"] for kind, path in rows
        ):
            raise NightlyError("CANDIDATE_SCOPE_VIOLATION")
        return sha, rows

    def _candidate_pr(
        self,
        night: dict[str, Any],
        entry: dict[str, Any],
        record: Mapping[str, Any],
        sha: str,
        rows: list[list[str]],
    ) -> None:
        issue, att = _issue_number(entry["issue"]), entry["attempts"][-1]
        pub, repo = record.get("publication") or {}, self.daemon_repo
        branch = f"eia/{issue}-{att['revision']}"
        att.update(candidate_commit=sha, branch=branch)
        self.save(night)
        self._push(repo, sha, branch)
        existing = self._pr_for_branch(branch)
        if existing:
            number = _issue_number(existing[0]["number"])
        else:
            worker = record.get("worker_binding") or {}
            files = "\n".join(f"- `{p}` ({k})" for k, p in rows)
            body = (
                f"Closes #{issue}\n\nEIA candidate produced overnight by the External Intelligence "
                f"daemon on M4 for #{issue} (task `{entry['task_id']}`, revision "
                f"`{att['revision']}`). The branch head is the daemon's candidate commit, unchanged, "
                f"on base `{att['main_sha']}`.\n\nChanged files:\n{files}\n\n## EIA receipt\n"
                f"- Candidate: `{sha}` (tree `{pub.get('candidate_tree')}`)\n"
                f"- Verification: `{pub.get('verification_state')}`, gate `{pub.get('current_gate')}`\n"
                f"- Acceptance packet sha256: `{pub.get('acceptance_packet_sha256')}`\n"
                f"- Closure run: `{record.get('closure_run_id')}`; identity `{att['identity_hash']}`\n"
                f"- Worker: `{_one_line(worker.get('provider'), 60)}/{_one_line(worker.get('model'), 60)}`\n"
                f"- Claim ceiling: `{pub.get('claim_ceiling')}`\n\nNot reviewed yet: this needs the "
                "normal independent review before merge.\n\n"
                f"<!-- NEXUS_CORE_ISSUE: {issue} -->\n<!-- NEXUS_ISSUE_INTENT_V1\n"
                f'[{{"issue": {issue}, "on_merge": "CLOSE"}}]\nNEXUS_ISSUE_INTENT_V1 -->\n\n'
                "🤖 Generated with [Claude Code](https://claude.com/claude-code)\n"
            )
            url = self._gh_file(
                [
                    *f"pr create --repo {REPOSITORY} --base main --head".split(),
                    branch,
                    "--title",
                    f"EIA candidate for #{issue}: {entry['title']}"[:200],
                ],
                body,
            )
            number = _number_from_url(url)
        entry.update(
            status="CANDIDATE_PR", pr={"number": number, "head_sha": sha, "branch": branch}
        )
        att.update(result="complete", finished_at=self._iso())
        self.save(night)
        self._queue_msg(
            night,
            f"ready-candidate-{number}",
            "merge-queue",
            f"READY Nexus-new#{number} head {sha}; EIA candidate for #{issue} "
            f"(WHOLE_TASK_PASS, packet {str(pub.get('acceptance_packet_sha256'))[:12]}); "
            "NOT reviewed yet: needs independent review (+ cross-model if high-risk) per "
            "normal rules. Sent by m4-eia-nightly (unattended).",
        )
        self._labels(issue, add=[L_CANDIDATE], remove=[L_EIA, L_QUEUE])
        self._event(night, "candidate_pr", issue=issue, pr=number, head=sha)

    # ---- stop -----------------------------------------------------------------------
    def stop(self) -> dict[str, Any]:
        night = self.load(night_of(self.now()))
        if not night or not night.get("started") or night.get("finalized"):
            return night or {"status": "IDLE"}
        night.setdefault("stop_requested_at", self._iso())
        if self._entries(night, "ARMED") and self.now() < night_clock(
            night["night"], self.hard_stop
        ):
            night["status"] = "DRAINING"
            self.save(night)
            return night
        self.finalize(night)
        self.save(night)
        return night

    def finalize(self, night: dict[str, Any]) -> None:
        out = self.run(["launchctl", "bootout", f"gui/{os.getuid()}/{DAEMON_LABEL}"], timeout=30)
        bootout_ok = out.returncode == 0 or "Could not find service" in f"{out.stdout}{out.stderr}"
        pid = night.get("caffeinate_pid")
        if pid and self._is_caffeinate(pid):
            with contextlib.suppress(ProcessLookupError):
                self.kill(int(pid), signal.SIGTERM)
        for entry in self._entries(night, "ARMED") + self._entries(night, "ARMING"):
            entry["status"] = "HARD_STOPPED"
            if entry["attempts"]:
                entry["attempts"][-1].update(
                    result="infra", reason="HARD_STOP", finished_at=self._iso()
                )
            try:
                self._labels(entry["issue"], remove=[L_EIA])
            except NightlyError as exc:  # best effort; the daemon is already booted out
                entry["disarm_error"] = str(exc)
        report = self.report(night)
        self._update_ledger(night)
        report_path = self.state_dir / f"{night['night']}-report.md"
        report_path.write_text(report, encoding="utf-8")
        night["finalized"] = {
            "at": self._iso(),
            "bootout_ok": bootout_ok,
            "report": str(report_path),
        }
        night["status"] = "FINISHED"
        totals = night["totals"]
        summary = (
            f"EIA nightly {night['night']}: {totals['candidate_pr']} candidate PR, "
            f"{totals['escalated']} escalated, {totals['other']} other of {totals['issues']}"
            f"{'' if bootout_ok else '; DAEMON BOOTOUT FAILED'}"
        )
        self._queue_msg(
            night,
            "morning-report",
            "coordinator",
            f"{summary}. Report {report_path}:\n{report[:1200]}",
        )
        self._notify(summary)
        self._event(night, "finalized", bootout_ok=bootout_ok)

    def report(self, night: dict[str, Any]) -> str:
        lines = [
            f"# EIA nightly report {night['night']}",
            "",
            f"- Card PR: #{(night.get('card_pr') or {}).get('number')} "
            f"(merged: {(night.get('card_pr') or {}).get('merged')})",
            f"- Night status: {night.get('status')}",
            "",
            "| Issue | Result | Attempts | Duration (min) | PR | Escalation |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        totals = {"issues": 0, "candidate_pr": 0, "escalated": 0, "other": 0}
        for number in night.get("order", []):
            entry = night["issues"][str(number)]
            totals["issues"] += 1
            key = {"CANDIDATE_PR": "candidate_pr", "ESCALATED": "escalated"}.get(
                entry["status"], "other"
            )
            totals[key] += 1
            atts = entry.get("attempts") or []
            duration = ""
            if atts and atts[-1].get("finished_at"):
                spent = dt.datetime.fromisoformat(
                    atts[-1]["finished_at"]
                ) - dt.datetime.fromisoformat(atts[0]["armed_at"])
                duration = f"{spent.total_seconds() / 60:.0f}"
            pr = f"#{entry['pr']['number']}" if entry.get("pr") else ""
            esc = _one_line((entry.get("escalation") or {}).get("reason", ""), 120)
            lines.append(
                f"| #{number} | {entry['status']} | {len(atts)} | {duration} | {pr} | {esc} |"
            )
        night["totals"] = totals
        lines += ["", f"Totals: {totals}", ""]
        return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eia_nightly", description="EIA nightly scheduler")
    parser.add_argument("command", choices=("prepare", "start", "dispatch", "stop", "status"))
    parser.add_argument(
        "--state-dir", default=str(HOME / "Workspace/nexus-self-hosted-state/eia-nightly")
    )
    parser.add_argument(
        "--eia-config", default=str(HOME / ".config/nexus-external-intelligence/config.json")
    )
    parser.add_argument("--work-repo", default=str(HOME / "Workspace/Nexus-new"))
    parser.add_argument("--max-issues", type=int, default=4)
    parser.add_argument("--night", help="YYYYMMDD override (prepare/status only)")
    parser.add_argument(
        "--trusted-actors",
        default=",".join(sorted(TRUSTED_ACTORS)),
        help="comma-separated logins allowed to queue/edit Issues",
    )
    args = parser.parse_args(argv)
    if args.night and not re.fullmatch(r"20\d{6}", args.night):
        parser.error("--night must be YYYYMMDD")
    app = Nightly(
        state_dir=Path(args.state_dir),
        eia_config=Path(args.eia_config),
        work_repo=Path(args.work_repo),
        max_issues=max(1, min(args.max_issues, 8)),
        trusted_actors=[a for a in args.trusted_actors.split(",") if a.strip()],
    )
    if args.command == "status":
        night = app.load(args.night or night_of(app.now()))
        print(json.dumps({"paused": app.paused(), "night": night}, indent=2, sort_keys=True))
        return 0
    if app.paused() and args.command != "stop":
        print(json.dumps({"status": "PAUSED"}))
        return 0
    with app.locked() as got:
        if not got:
            print(json.dumps({"status": "LOCKED"}))
            return 0
        try:
            result = (
                app.prepare(args.night)
                if args.command == "prepare"
                else getattr(app, args.command)()
            )
            if result.get("schema") == STATE_SCHEMA:
                app._flush_outbox(result)
                app.save(result)
        except NightlyError as exc:
            print(json.dumps({"status": "ERROR", "error": str(exc)}))
            return 1
    print(json.dumps({"status": result.get("status"), "night": result.get("night")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
