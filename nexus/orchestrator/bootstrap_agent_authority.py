"""Agent authority for Task Card binds in BOOTSTRAP with a separate Controller (#2270).

Owner decision (James, 2026-10-13 and 2026-10-15, recorded on #2270): Owner
authorization is what the Owner says in chat to the agent. Governed tasks must
run with no interactive Owner step while the operating mode is BOOTSTRAP.

This module does not pretend to be the Owner. It never writes a standing grant
and never answers an Owner confirmation form. It changes what two effects
require: ``TASK_CARD_CREATE`` and ``TASK_CARD_COMMIT`` only write ``tasks/``
files into, and commit them on, the separate Controller worktree. They publish
nothing, push nothing and touch no protected ref. When, and only when,

* ``docs/governance/current_operating_mode.yaml`` of the loaded deployment is
  VALID (``scripts/ops/check_operating_mode.py``) with ``mode: BOOTSTRAP``, and
* the Controller binding is ``SEPARATE`` (not ``NOT_SEPARATE``, not
  ``DEGRADED``),

those two effects are authorized by the agent identity, and a durable authority
record is appended before the effect runs. Every other effect, and these two
outside that state, keep the existing standing-grant requirement.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

import yaml

from nexus.contracts.autonomy_goal import AutonomyActionClass, canonical_autonomy_hash
from nexus.orchestrator.task_card_scope import protected_path_reason

AUTHORITY_BASIS = "OWNER_CHAT_DELEGATION_BOOTSTRAP"
DECISION_REFERENCE = "James3014/Nexus-new#2270"
ACTOR = "AGENT"
RECORD_SCHEMA = "nexus.bootstrap_agent_authority_record.v1"
AUTHORIZATION_SCHEMA = "nexus.bootstrap_agent_effect_authorization.v1"
RECORD_FILENAME = "bootstrap-agent-authority.jsonl"
PREV_FIELD = "prev_record_hash"
OPERATING_MODE_RELATIVE_PATH = Path("docs/governance/current_operating_mode.yaml")
REQUIRED_MODE = "BOOTSTRAP"
REQUIRED_CONTROLLER_BINDING = "SEPARATE"
_SHA_RE = re.compile(r"[0-9a-f]{40}")
# Link of the first chained record when no legacy (unchained) record precedes it.
GENESIS_PREV_RECORD_HASH = "0" * 64
BASIS_BOOTSTRAP_AGENT = "bootstrap_agent"
BASIS_OWNER_GRANT = "owner_grant"

# Effects that only bind Task Card files into the separate Controller. Anything
# that publishes or is irreversible (merge, push, release, deletion, ruleset,
# candidate integration/disposal, grant issuance) is deliberately absent.
DELEGABLE_ACTIONS = frozenset({
    AutonomyActionClass.TASK_CARD_CREATE,
    AutonomyActionClass.TASK_CARD_COMMIT,
})


class BootstrapAgentAuthorityError(RuntimeError):
    """The authority record could not be written; the effect must not run."""


def observe_operating_mode(source_root: Path) -> dict[str, Any]:
    """Read the operating mode from the existing source of truth, fail closed.

    Returns ``mode`` only when the repository's own validator says VALID and the
    validated bytes are the bytes read here. Any other outcome returns
    ``mode: None`` with a reason.
    """
    path = Path(source_root) / OPERATING_MODE_RELATIVE_PATH
    observation: dict[str, Any] = {
        "path": OPERATING_MODE_RELATIVE_PATH.as_posix(),
        "mode": None,
        "source_sha256": None,
        "loaded_source_head": None,
        "reason": None,
    }
    try:
        # No symlink anywhere between the loaded root and the file.
        current = Path(source_root)
        for part in OPERATING_MODE_RELATIVE_PATH.parts[:-1]:
            current = current / part
            if not stat.S_ISDIR(os.lstat(current).st_mode):
                observation["reason"] = "MODE_FILE_NOT_REGULAR"
                return observation
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode):
            observation["reason"] = "MODE_FILE_NOT_REGULAR"
            return observation
        raw = path.read_bytes()
    except OSError as exc:
        observation["reason"] = f"MODE_FILE_UNREADABLE:{type(exc).__name__}"
        return observation
    digest = hashlib.sha256(raw).hexdigest()
    observation["source_sha256"] = digest
    # The mode must be the committed one of the loaded deployment, not an
    # uncommitted edit or a replacement file in its working tree.
    committed = _committed_blob(Path(source_root), OPERATING_MODE_RELATIVE_PATH.as_posix())
    if committed is None:
        observation["reason"] = "MODE_FILE_NOT_COMMITTED"
        return observation
    head, blob = committed
    observation["loaded_source_head"] = head
    if blob != raw:
        observation["reason"] = "MODE_FILE_DIFFERS_FROM_LOADED_COMMIT"
        return observation
    try:
        from scripts.ops.check_operating_mode import STATUS_VALID, evaluate_operating_mode

        verdict = evaluate_operating_mode(path)
    except Exception as exc:  # validator unavailable or crashed: fail closed
        observation["reason"] = f"MODE_VALIDATOR_UNAVAILABLE:{type(exc).__name__}"
        return observation
    if verdict.get("status") != STATUS_VALID:
        codes = ",".join(sorted({str(r.get("code")) for r in verdict.get("reasons") or []}))
        observation["reason"] = f"MODE_INVALID:{codes or 'UNKNOWN'}"
        return observation
    if verdict.get("source_sha256") != digest:
        observation["reason"] = "MODE_FILE_CHANGED_DURING_READ"
        return observation
    try:
        document = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        observation["reason"] = f"MODE_INVALID:{type(exc).__name__}"
        return observation
    mode = document.get("mode") if isinstance(document, dict) else None
    if not isinstance(mode, str):
        observation["reason"] = "MODE_INVALID:MODE_MISSING"
        return observation
    observation["mode"] = mode
    return observation


def _committed_blob(source_root: Path, relative: str) -> Optional[tuple[str, bytes]]:
    """``(HEAD, bytes)`` of ``relative`` at the loaded checkout's HEAD, or ``None``."""
    # Pin git to exactly this checkout: no inherited GIT_DIR/GIT_WORK_TREE,
    # no walking up into a parent repository.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}

    def run(*args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", "-C", str(source_root), *args],
            capture_output=True,
            timeout=5.0,
            check=False,
            env=env,
        )

    try:
        # ``resolve()`` can raise (symlink loop, vanished path): that must mean
        # "no committed blob", i.e. the grant path, never an exception.
        env["GIT_CEILING_DIRECTORIES"] = str(Path(source_root).resolve().parent)
        top = run("rev-parse", "--show-toplevel")
        toplevel = top.stdout.decode("utf-8", errors="replace").strip()
        if top.returncode != 0 or not toplevel:
            return None
        if Path(toplevel).resolve() != Path(source_root).resolve():
            return None
        head = run("rev-parse", "HEAD")
        sha = head.stdout.decode("ascii", errors="replace").strip()
        if head.returncode != 0 or not _SHA_RE.fullmatch(sha):
            return None
        blob = run("cat-file", "blob", f"{sha}:{relative}")
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
        return None
    if blob.returncode != 0:
        return None
    return sha, blob.stdout


def delegation_context(
    action: AutonomyActionClass,
    *,
    source_root: Path,
    controller_binding: Mapping[str, Optional[str]],
    expected_source_head: Optional[str],
) -> Optional[dict[str, Any]]:
    """Return the facts that admit agent authority, or ``None`` to keep the grant path.

    ``expected_source_head`` is the commit the Gateway process loaded at start
    (``SERVER_REPO_HEAD_AT_START``). The mode is only trusted when the loaded
    tree's HEAD still equals it; a moved HEAD, or no known start HEAD, keeps
    the grant path (#2301).
    """
    if action not in DELEGABLE_ACTIONS:
        return None
    if controller_binding.get("status") != REQUIRED_CONTROLLER_BINDING:
        return None
    if controller_binding.get("reason") is not None:
        return None
    if not isinstance(expected_source_head, str) or not _SHA_RE.fullmatch(expected_source_head):
        return None
    mode = observe_operating_mode(source_root)
    if mode.get("mode") != REQUIRED_MODE:
        return None
    if mode.get("loaded_source_head") != expected_source_head:
        return None
    return {
        "operating_mode": mode,
        "controller_binding": {
            "status": controller_binding.get("status"),
            "reason": controller_binding.get("reason"),
        },
    }


def _verify_chain(raw: bytes) -> str:
    """Verify the whole record file and return the hash the next record must link to.

    Legacy records (no ``prev_record_hash``) are only valid as a prefix; the
    first chained record links to the last legacy record's hash, or to
    :data:`GENESIS_PREV_RECORD_HASH` when none precedes it. Any unparseable
    line, wrong record hash, or broken link raises.
    """
    last_hash = GENESIS_PREV_RECORD_HASH
    chained = False
    for line in raw.split(b"\n"):
        if not line:
            continue
        try:
            record = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise BootstrapAgentAuthorityError(
                "BOOTSTRAP_AGENT_AUTHORITY_CHAIN_BROKEN:UNPARSEABLE_RECORD"
            ) from exc
        if not isinstance(record, dict) or not isinstance(record.get("record_hash"), str):
            raise BootstrapAgentAuthorityError(
                "BOOTSTRAP_AGENT_AUTHORITY_CHAIN_BROKEN:MALFORMED_RECORD"
            )
        body = {k: v for k, v in record.items() if k != "record_hash"}
        if canonical_autonomy_hash(body) != record["record_hash"]:
            raise BootstrapAgentAuthorityError(
                "BOOTSTRAP_AGENT_AUTHORITY_CHAIN_BROKEN:RECORD_HASH_MISMATCH"
            )
        if PREV_FIELD in record:
            chained = True
            if record[PREV_FIELD] != last_hash:
                raise BootstrapAgentAuthorityError(
                    "BOOTSTRAP_AGENT_AUTHORITY_CHAIN_BROKEN:LINK_MISMATCH"
                )
        elif chained:
            raise BootstrapAgentAuthorityError(
                "BOOTSTRAP_AGENT_AUTHORITY_CHAIN_BROKEN:UNCHAINED_AFTER_CHAINED"
            )
        last_hash = record["record_hash"]
    return last_hash


def _read_all(fd: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks = []
    while True:
        chunk = os.read(fd, 1 << 20)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _append_record(directory: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    """Chain ``record`` to the verified file tail, append it durably, return it.

    The file is verified end to end under an exclusive lock before the append,
    so a tampered or forked chain refuses new agent authority.
    """
    # Same directory chain and file rules as the standing-grant store and the
    # Owner confirmation audit next to it.
    from nexus.orchestrator import standing_grant_store as store

    try:
        store._assert_dir_chain_safe(directory, create=True)
        target = directory / RECORD_FILENAME
        # O_NONBLOCK: a planted FIFO fails instead of blocking the Gateway.
        fd = os.open(
            str(target),
            os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o600,
        )
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid():
                raise OSError("authority record is not a regular file owned by this user")
            fcntl.flock(fd, fcntl.LOCK_EX)
            chained_record = dict(record)
            chained_record[PREV_FIELD] = _verify_chain(_read_all(fd))
            chained_record["record_hash"] = canonical_autonomy_hash(chained_record)
            line = (json.dumps(chained_record, sort_keys=True, ensure_ascii=False) + "\n").encode(
                "utf-8"
            )
            written = os.write(fd, line)
            if written != len(line):
                raise OSError("short write")
            os.fsync(fd)
        finally:
            os.close(fd)
        # Make the directory entry durable before the effect runs (always:
        # the file may have been (re)created by this very open).
        dir_fd = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except (OSError, store.StandingGrantReceiptError) as exc:
        raise BootstrapAgentAuthorityError(
            f"BOOTSTRAP_AGENT_AUTHORITY_RECORD_WRITE_FAILED:{type(exc).__name__}"
        ) from exc
    return chained_record


def authority_basis(authorization: Any) -> str:
    """``bootstrap_agent`` for an agent-authority authorization, else ``owner_grant``."""
    if isinstance(authorization, Mapping) and authorization.get("schema") == AUTHORIZATION_SCHEMA:
        return BASIS_BOOTSTRAP_AGENT
    return BASIS_OWNER_GRANT


def authorize_bootstrap_agent_effect(
    *,
    repository: Any,
    action: AutonomyActionClass,
    effect: Mapping[str, Any],
    key: Any,
    context: Mapping[str, Any],
    record_directory: Path,
    server_instance_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Write the authority record, then return the effect authorization.

    The caller must have obtained ``context`` from :func:`delegation_context`
    for this exact action. The record is durable before the effect runs; if it
    cannot be written the effect is refused.
    """
    if action not in DELEGABLE_ACTIONS:
        raise BootstrapAgentAuthorityError("BOOTSTRAP_AGENT_AUTHORITY_ACTION_NOT_DELEGABLE")
    # #1750: a Task Card that lists an authority-bearing path is never delegable.
    for path in effect.get("allowed_files") or ():
        if protected_path_reason(str(path)) is not None:
            raise BootstrapAgentAuthorityError("BOOTSTRAP_AGENT_AUTHORITY_PROTECTED_PATH")
    recorded_at = (now or datetime.now(timezone.utc)).isoformat()
    effect_payload = json.loads(json.dumps(dict(effect), sort_keys=True))
    effect_hash = canonical_autonomy_hash(effect_payload)
    record: dict[str, Any] = {
        "schema": RECORD_SCHEMA,
        "effect": action.value,
        "effect_payload": effect_payload,
        "effect_hash": effect_hash,
        "actor": ACTOR,
        "authority_basis": AUTHORITY_BASIS,
        "decision_reference": DECISION_REFERENCE,
        "operating_mode": dict(context["operating_mode"]),
        "controller_binding": dict(context["controller_binding"]),
        "repository": repository.model_dump(mode="json"),
        "goal_id": getattr(key, "goal_id", None),
        "coordination_scope_id": getattr(key, "coordinator_thread", None),
        "standing_grant_key": getattr(key, "digest", None),
        "standing_grant_used": False,
        # Attribution: which Gateway process and loaded commit acted.
        "server_instance_id": server_instance_id,
        "loaded_source_head": context["operating_mode"].get("loaded_source_head"),
        "recorded_at": recorded_at,
    }
    record = _append_record(Path(record_directory), record)
    payload: dict[str, Any] = {
        "schema": AUTHORIZATION_SCHEMA,
        "action": action.value,
        "actor": ACTOR,
        "authority_basis": AUTHORITY_BASIS,
        "decision_reference": DECISION_REFERENCE,
        "operating_mode": record["operating_mode"]["mode"],
        "controller_binding": record["controller_binding"]["status"],
        "effect": effect_payload,
        "effect_hash": effect_hash,
        "authority_record_hash": record["record_hash"],
        "authority_record_file": RECORD_FILENAME,
        "standing_grant_key": record["standing_grant_key"],
        "requested_at": recorded_at,
        "mutation_authorized": True,
    }
    payload["authorization_hash"] = canonical_autonomy_hash(payload)
    return payload
