from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Collection, Mapping, Sequence

from nexus.services.external_intelligence import (
    ExternalIntelligenceError,
    validate_selected_worker,
)
from nexus.services.external_intelligence_core_binding import (
    CLOSURE_INTEGRITY_GIT_TIMEOUT_SECONDS,
)
from nexus.services.external_intelligence_fanout import (
    EIA_COMPOSER_EMAIL,
    EIA_COMPOSER_NAME,
    EIA_TRAILER_MODEL,
    EIA_TRAILER_WORKER,
    MODEL,
    MODEL_ID,
    PROVIDER,
    PROVIDER_ID,
    WORKER_RECEIPT_SCHEMA,
    eia_git_commit,
    eia_worker_identity,
)

UNIT_VERIFICATION_SCHEMA = "external_intelligence_unit_verification.v1"
WHOLE_VERIFICATION_SCHEMA = "external_intelligence_whole_task_verification.v1"
UNIT_REPAIR_DELTA_SCHEMA = "unit_repair_delta.v2"
COMPOSITION_REPAIR_DELTA_SCHEMA = "composition_repair_delta.v1"
TASK_CANDIDATE_SCHEMA = "external_intelligence_task_candidate.v1"
ACCEPTANCE_PACKET_SCHEMA = "external_intelligence_acceptance_packet.v1"
CLOSURE_CAPSULE_SCHEMA = "external_intelligence_closure_capsule.v1"
CLOSURE_RUN_SCHEMA = "external_intelligence_closure_run.v1"
CLAIM_CEILING = "TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE"
EXECUTABLE_TASK_CARD_STATUSES = frozenset({
    "ACTIVE",
    "APPROVED_IN_PROGRESS",
})
_SESSION_PREFIX = "ses_"
_HEX40 = frozenset("0123456789abcdef")
_HEX64 = _HEX40
_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
# Built-in scoped integrity checks closure always runs against the bound base,
# independent of the contract verifiers (which may be unscoped no-ops).
INTEGRITY_CHECK_WHITESPACE = "nexus.integrity.diff-check"
INTEGRITY_CHECK_DELETIONS = "nexus.integrity.deletions"
INTEGRITY_CHECK_SCOPE = "nexus.integrity.scope"
INTEGRITY_CHECK_IDS = (INTEGRITY_CHECK_WHITESPACE, INTEGRITY_CHECK_DELETIONS, INTEGRITY_CHECK_SCOPE)
# Shared with the Core binding window sizing (binding_validity_seconds).
INTEGRITY_CHECK_TIMEOUT_SECONDS = CLOSURE_INTEGRITY_GIT_TIMEOUT_SECONDS
INTEGRITY_WHITESPACE_ERRORS = "INTEGRITY_WHITESPACE_ERRORS"
INTEGRITY_DELETION_NOT_AUTHORIZED = "INTEGRITY_DELETION_NOT_AUTHORIZED"
INTEGRITY_SCOPE_WIDENING = "INTEGRITY_SCOPE_WIDENING"
INTEGRITY_CHECK_ERROR = "INTEGRITY_CHECK_ERROR"
# Environment handed to contract verifiers so they can scope to the bound base
# deterministically (e.g. ``git diff --check "$NEXUS_BASE_SHA" "$NEXUS_CANDIDATE_SHA"``).
VERIFIER_ENV_BASE_SHA = "NEXUS_BASE_SHA"
VERIFIER_ENV_CANDIDATE_SHA = "NEXUS_CANDIDATE_SHA"
_INTEGRITY_FINDINGS_LIMIT = 50
_DIFF_CHECK_LOCATION_RE = re.compile(r"^(?P<path>.+?):(?P<line>[0-9]+): ")


@dataclass(frozen=True)
class TaskCardAuthority:
    task_id: str
    status: str
    allowed_files: tuple[str, ...]
    verification_commands: tuple[tuple[str, ...], ...]
    allow_deletions: bool = False
    # Owner-authored Core binding inputs.  They are only required (fail closed) when
    # an Open SWE bound dispatch mints a repository_mutation_binding.
    execution_lane: str = ""
    capability_disposition: str = ""
    capability_ids: tuple[str, ...] | None = None
    capability_justification: str = ""

    @property
    def is_executable(self) -> bool:
        return self.status.upper() in EXECUTABLE_TASK_CARD_STATUSES


class ClosureError(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _is_hex(value: Any, size: int) -> bool:
    text = str(value or "").lower()
    return len(text) == size and all(char in _HEX40 for char in text)


def _safe_slug(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if (
        not text
        or len(text) > 160
        or any(
            char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
            for char in text
        )
    ):
        raise ClosureError(f"INVALID_{field.upper()}")
    return text


def _safe_relative_path(value: Any) -> str:
    text = str(value or "").strip()
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts or "\\" in text or "\x00" in text:
        raise ClosureError("INVALID_MUTATION_PATH")
    return path.as_posix()


def _path_matches(path: str, boundary: str) -> bool:
    p = path.rstrip("/")
    b = boundary.rstrip("/")
    return p == b or p.startswith(b + "/")


def _run_git(root: Path, *args: str, timeout: float = 30.0) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:1200]
        raise ClosureError(f"GIT_COMMAND_FAILED:{args[0]}:{detail}")
    return result.stdout.strip()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(dict(value), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return _sha256(payload)


def _changed_paths(root: Path, base: str, head: str) -> list[str]:
    # ``--no-renames``: a rename must surface as delete + add so its source path is
    # scope- and deletion-checked (rename detection would hide the deleted source).
    output = _run_git(root, "diff", "--no-renames", "--name-only", base, head, "--")
    return sorted(line.strip() for line in output.splitlines() if line.strip())


def _deleted_paths(root: Path, base: str, head: str) -> list[str]:
    output = _run_git(root, "diff", "--no-renames", "--name-status", base, head, "--")
    deleted: list[str] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if parts and parts[0].startswith("D") and len(parts) >= 2:
            deleted.append(parts[-1])
    return sorted(deleted)


def _diff_sha(root: Path, base: str, head: str) -> str:
    return _sha256(_run_git(root, "diff", "--binary", base, head))


def _raw_diff_patch(root: Path, base: str, head: str) -> str:
    result = subprocess.run(
        ["git", "diff", "--binary", base, head],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ClosureError(f"GIT_DIFF_FAILED:{(result.stderr or result.stdout).strip()[:1200]}")
    return result.stdout


def _git_no_replace_env() -> dict[str, str]:
    """Environment for closure-owned git reads: ``refs/replace`` must not change what
    closure sees as the base config or the base..candidate diff."""
    return {**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"}


def _integrity_git(root: Path, args: Sequence[str]) -> tuple[list[str], int | None, str, str]:
    argv = ["git", *args]
    try:
        proc = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=INTEGRITY_CHECK_TIMEOUT_SECONDS,
            check=False,
            env=_git_no_replace_env(),
        )
    except subprocess.TimeoutExpired as exc:
        return argv, None, str(exc.stdout or ""), str(exc.stderr or "")
    return argv, int(proc.returncode), proc.stdout or "", proc.stderr or ""


def _integrity_row(
    check_id: str,
    argv: Sequence[str],
    returncode: int | None,
    stdout: str,
    stderr: str,
    *,
    code: str,
    findings: Sequence[str],
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "argv": list(argv),
        "argv_sha256": _sha256(_canonical_json(list(argv))),
        "returncode": returncode,
        "stdout_sha256": _sha256(stdout),
        "stderr_sha256": _sha256(stderr),
        "findings": sorted(set(findings))[:_INTEGRITY_FINDINGS_LIMIT],
        "code": code,
        "passed": not code,
    }


def _nul_paths(output: str) -> list[str]:
    return [part for part in output.split("\x00") if part]


def run_integrity_checks(
    root: Path,
    *,
    base_sha: str,
    candidate_commit: str,
    authorized_paths: Sequence[str],
    deletable_paths: Sequence[str],
) -> list[dict[str, Any]]:
    """Closure-owned scoped integrity checks of ``base_sha..candidate_commit``.

    Always scoped to the bound base (never the clean working tree), so they cannot
    degenerate into no-ops.  Each check fails closed: a git error or timeout is a
    failure with ``INTEGRITY_CHECK_ERROR``.

    - whitespace: ``git diff --check <base> <candidate>`` must report nothing;
    - deletions: every deleted path (renames count as deletions) must lie under
      ``deletable_paths``;
    - scope: every changed path must lie under ``authorized_paths``.
    """
    if not _is_hex(base_sha, 40) or not _is_hex(candidate_commit, 40):
        raise ClosureError("INTEGRITY_CHECK_IDENTITY_INVALID")
    rows: list[dict[str, Any]] = []

    argv, rc, out, err = _integrity_git(
        root, ["diff", "--no-ext-diff", "--no-renames", "--check", base_sha, candidate_commit, "--"]
    )
    findings: list[str] = []
    for line in out.splitlines():
        match = _DIFF_CHECK_LOCATION_RE.match(line)
        if match and not line.startswith(("+", "-")):
            findings.append(match.group("path"))
    if rc == 0 and not out.strip():
        code = ""
    elif rc is not None and rc != 0 and findings:
        code = INTEGRITY_WHITESPACE_ERRORS
    else:
        code = INTEGRITY_CHECK_ERROR
    rows.append(
        _integrity_row(INTEGRITY_CHECK_WHITESPACE, argv, rc, out, err, code=code, findings=findings)
    )

    argv, rc, out, err = _integrity_git(
        root,
        [
            "diff",
            "--no-ext-diff",
            "--no-renames",
            "--name-only",
            "-z",
            "--diff-filter=D",
            base_sha,
            candidate_commit,
            "--",
        ],
    )
    if rc != 0:
        findings, code = [], INTEGRITY_CHECK_ERROR
    else:
        findings = [
            path
            for path in _nul_paths(out)
            if not any(_path_matches(path, boundary) for boundary in deletable_paths)
        ]
        code = INTEGRITY_DELETION_NOT_AUTHORIZED if findings else ""
    rows.append(
        _integrity_row(INTEGRITY_CHECK_DELETIONS, argv, rc, out, err, code=code, findings=findings)
    )

    argv, rc, out, err = _integrity_git(
        root,
        [
            "diff",
            "--no-ext-diff",
            "--no-renames",
            "--name-only",
            "-z",
            base_sha,
            candidate_commit,
            "--",
        ],
    )
    if rc != 0:
        findings, code = [], INTEGRITY_CHECK_ERROR
    else:
        findings = [
            path
            for path in _nul_paths(out)
            if not any(_path_matches(path, boundary) for boundary in authorized_paths)
        ]
        code = INTEGRITY_SCOPE_WIDENING if findings else ""
    rows.append(
        _integrity_row(INTEGRITY_CHECK_SCOPE, argv, rc, out, err, code=code, findings=findings)
    )
    return rows


def _receipt_identity(receipt: Mapping[str, Any]) -> str:
    material = dict(receipt)
    material.pop("receipt_id", None)
    return _sha256(_canonical_json(material))


def _extract_markdown_section(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    marker = f"## {heading}".lower()
    start = -1
    for idx, line in enumerate(lines):
        if line.strip().lower() == marker:
            start = idx + 1
            break
    if start == -1:
        return []
    end = len(lines)
    for idx in range(start, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break
    return lines[start:end]


def _frontmatter_value(text: str, key: str) -> str | None:
    patterns = (
        rf"^\s*-\s+{re.escape(key)}:\s*`([^`]+)`\s*$",
        rf"^\s*\*\*{re.escape(key)}:\*\*\s*`([^`]+)`\s*$",
        rf"^\s*-\s+{re.escape(key)}:\s*([^\s]+)\s*$",
        rf"^\s*\*\*{re.escape(key)}:\*\*\s*([^\s]+)\s*$",
        rf"^\s*{re.escape(key)}:\s*`([^`]+)`\s*$",
        rf"^\s*{re.escape(key)}:\s*([^\s]+)\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def parse_task_card_authority(text: str) -> TaskCardAuthority:
    task_id = _frontmatter_value(text, "task_id") or ""
    status = _frontmatter_value(text, "status") or ""

    allowed_lines = _extract_markdown_section(text, "Allowed files")
    allowed_files: list[str] = []
    if allowed_lines:
        for raw in allowed_lines:
            line = raw.strip()
            if not line or line.startswith("```"):
                continue
            matches = re.findall(r"`([^`]+)`", line)
            if matches:
                for m in matches:
                    p = m.strip()
                    if p and not p.startswith("#"):
                        allowed_files.append(p)
            else:
                if line.startswith(("- ", "* ")):
                    line = line[2:].strip()
                if line and not line.startswith("#"):
                    allowed_files.append(line)
    else:
        inline = re.search(r"Allowed files:\s*(.*)", text, re.IGNORECASE)
        if inline:
            matches = re.findall(r"`([^`]+)`", inline.group(1))
            for m in matches:
                allowed_files.append(m.strip())

    cleaned_allowed: list[str] = []
    for p in allowed_files:
        try:
            cleaned_allowed.append(_safe_relative_path(p))
        except Exception:
            continue

    v_lines = _extract_markdown_section(text, "Verification commands")
    commands: set[tuple[str, ...]] = set()
    in_fence = False
    for raw in v_lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("```"):
            fence_lang = line[3:].strip().lower()
            if not in_fence:
                if fence_lang in ("", "bash", "sh", "shell", "zsh"):
                    in_fence = True
            else:
                in_fence = False
            continue

        cmd_str: str | None = None
        if in_fence:
            if line.startswith("#"):
                continue
            if line.startswith(("- ", "* ")):
                line = line[2:].strip()
            if line.startswith("`") and line.endswith("`") and len(line) >= 2:
                line = line[1:-1].strip()
            cmd_str = line
        else:
            m = re.match(r"^(?:[-*]\s*)?`([^`]+)`\s*$", line)
            if m:
                cand = m.group(1).strip()
                if not cand.startswith("#"):
                    cmd_str = cand

        if not cmd_str:
            continue
        try:
            tokens = shlex.split(cmd_str)
        except ValueError:
            continue
        while tokens and _ENV_RE.match(tokens[0]):
            tokens.pop(0)
        if tokens:
            commands.add(tuple(tokens))

    del_val = (
        _frontmatter_value(text, "allow_deletions")
        or _frontmatter_value(text, "worker_may_delete")
        or _frontmatter_value(text, "deletions_allowed")
    )
    allow_del = str(del_val).lower() in ("true", "1", "yes") if del_val else False

    raw_capability_ids = _frontmatter_value(text, "capability_ids")
    capability_ids: tuple[str, ...] | None
    if raw_capability_ids is None:
        capability_ids = None
    elif raw_capability_ids.strip().lower() == "none":
        capability_ids = ()
    else:
        capability_ids = tuple(part.strip() for part in raw_capability_ids.split(","))

    return TaskCardAuthority(
        task_id=task_id,
        status=status,
        allowed_files=tuple(sorted(dict.fromkeys(cleaned_allowed))),
        verification_commands=tuple(sorted(commands)),
        allow_deletions=allow_del,
        execution_lane=(_frontmatter_value(text, "execution_lane") or "").strip(),
        capability_disposition=(_frontmatter_value(text, "capability_disposition") or "").strip(),
        capability_ids=capability_ids,
        capability_justification=(
            _frontmatter_value(text, "capability_justification") or ""
        ).strip(),
    )


def _verify_task_card_binding(
    repository_root: Path, main_sha: str, task_card_ref: str, task_card_hash: str
) -> TaskCardAuthority:
    if not _is_hex(main_sha, 40):
        raise ClosureError("INVALID_MAIN_SHA")
    if not _is_hex(task_card_hash, 64):
        raise ClosureError("TASK_CARD_HASH_INVALID")
    relative = _safe_relative_path(task_card_ref)
    commit_check = subprocess.run(
        ["git", "cat-file", "-e", f"{main_sha}^{{commit}}"],
        cwd=repository_root,
        capture_output=True,
        check=False,
    )
    if commit_check.returncode != 0:
        raise ClosureError("MAIN_SHA_NOT_FOUND")
    blob_res = subprocess.run(
        ["git", "cat-file", "blob", f"{main_sha}:{relative}"],
        cwd=repository_root,
        capture_output=True,
        check=False,
    )
    if blob_res.returncode != 0:
        raise ClosureError("TASK_CARD_NOT_FOUND")
    raw = blob_res.stdout
    if _sha256(raw) != str(task_card_hash).lower():
        raise ClosureError("TASK_CARD_HASH_MISMATCH")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ClosureError("TASK_CARD_DECODE_FAILED") from exc
    return parse_task_card_authority(text)


@dataclass(frozen=True)
class VerifierSpec:
    verifier_id: str
    argv: tuple[str, ...]
    owner_unit: str = ""
    timeout: float = 120.0

    @classmethod
    def from_value(cls, value: Mapping[str, Any] | "VerifierSpec") -> "VerifierSpec":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise ClosureError("INVALID_VERIFIER_SPEC")
        verifier_id = _safe_slug(value.get("id"), "verifier_id")
        raw_argv = value.get("argv")
        if not isinstance(raw_argv, (list, tuple)) or not raw_argv or len(raw_argv) > 64:
            raise ClosureError("INVALID_VERIFIER_ARGV")
        argv: list[str] = []
        for part in raw_argv:
            text = str(part)
            if not text or len(text) > 4096 or "\x00" in text:
                raise ClosureError("INVALID_VERIFIER_ARGV")
            argv.append(text)
        owner_unit = str(value.get("owner_unit") or "").strip()
        if owner_unit:
            owner_unit = _safe_slug(owner_unit, "owner_unit")
        timeout = float(value.get("timeout", 120.0))
        if timeout <= 0 or timeout > 1800:
            raise ClosureError("INVALID_VERIFIER_TIMEOUT")
        return cls(
            verifier_id=verifier_id, argv=tuple(argv), owner_unit=owner_unit, timeout=timeout
        )


@dataclass(frozen=True)
class AssemblyLease:
    workspace_id: str
    path: str
    base_sha: str


class ClosureStore:
    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root).expanduser().resolve()
        self.verifications = self.root / "verifications"
        self.repair_deltas = self.root / "repair-deltas"
        self.task_candidates = self.root / "task-candidates"
        self.acceptance_packets = self.root / "acceptance-packets"
        self.capsules = self.root / "capsules"

    def write_verification(self, value: Mapping[str, Any]) -> tuple[str, str]:
        scope = str(value.get("scope") or "")
        task = _safe_slug(value.get("task_id"), "task_id")
        unit = str(value.get("unit_id") or "task")
        name = f"{task}--{unit}--{scope.lower()}--{value.get('verification_id')}.json"
        path = self.verifications / name
        return str(path), _atomic_json(path, value)

    def repair_count(self, task_id: str, unit_id: str) -> int:
        prefix = f"{_safe_slug(task_id, 'task_id')}--{_safe_slug(unit_id, 'unit_id')}--"
        if not self.repair_deltas.exists():
            return 0
        return sum(
            1
            for path in self.repair_deltas.iterdir()
            if path.is_file() and path.name.startswith(prefix)
        )

    def next_repair_index(self, task_id: str, unit_id: str) -> int:
        return self.repair_count(task_id, unit_id) + 1

    def write_repair_delta(self, value: Mapping[str, Any], *, repair_index: int) -> tuple[str, str]:
        task = _safe_slug(value.get("task_id"), "task_id")
        unit = _safe_slug(value.get("unit_id"), "unit_id")
        path = self.repair_deltas / f"{task}--{unit}--{repair_index:03d}.json"
        if path.exists():
            raise ClosureError("REPAIR_DELTA_REPLAY_FORBIDDEN")
        return str(path), _atomic_json(path, value)

    def write_task_candidate(self, value: Mapping[str, Any]) -> tuple[str, str]:
        task = _safe_slug(value.get("task_id"), "task_id")
        path = self.task_candidates / f"{task}--{value.get('task_candidate_id')}.json"
        return str(path), _atomic_json(path, value)

    def write_acceptance_packet(self, value: Mapping[str, Any]) -> tuple[str, str]:
        task = _safe_slug(value.get("task_id"), "task_id")
        path = self.acceptance_packets / f"{task}--{value.get('packet_id')}.json"
        return str(path), _atomic_json(path, value)

    def write_capsule(self, value: Mapping[str, Any]) -> tuple[str, str]:
        task = _safe_slug(value.get("task_id"), "task_id")
        path = self.capsules / f"{task}--{value.get('capsule_id')}.json"
        return str(path), _atomic_json(path, value)


class CompositionWorkspaceAllocator:
    def __init__(
        self, repository_root: str | os.PathLike[str], workspace_root: str | os.PathLike[str]
    ):
        self.repository_root = Path(repository_root).expanduser().resolve()
        self.workspace_root = Path(workspace_root).expanduser().resolve()

    def allocate(self, task_id: str, base_sha: str) -> AssemblyLease:
        if not _is_hex(base_sha, 40):
            raise ClosureError("INVALID_BASE_SHA")
        if _run_git(self.repository_root, "cat-file", "-t", base_sha) != "commit":
            raise ClosureError("BASE_NOT_COMMIT")
        workspace_id = f"ei-close-{_safe_slug(task_id, 'task_id')}-{uuid.uuid4().hex[:12]}"
        path = self.workspace_root / workspace_id
        if path.exists():
            raise ClosureError("ASSEMBLY_WORKSPACE_COLLISION")
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "worktree", "add", "--detach", str(path), base_sha],
            cwd=self.repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ClosureError(
                f"ASSEMBLY_WORKSPACE_FAILED:{(result.stderr or result.stdout).strip()[:1200]}"
            )
        if _run_git(path, "rev-parse", "HEAD") != base_sha or _run_git(
            path, "status", "--porcelain=v1"
        ):
            raise ClosureError("ASSEMBLY_WORKSPACE_NOT_FRESH")
        return AssemblyLease(workspace_id=workspace_id, path=str(path), base_sha=base_sha)


_CORE_BOUND_RECEIPT_FIELDS = (
    "bound_envelope_ref",
    "bound_envelope_sha256",
    "core_binding_status",
    "core_binding_hash",
    "acceptance_contract_hash",
)


def _validate_core_binding_receipt(
    receipt: Mapping[str, Any], *, worker_backend: str
) -> dict[str, Any]:
    """Require BOUND Core identity for receipts produced by a bound dispatch.

    Receipts without any bound field are legacy/unbound dispatches and stay valid.
    A bound receipt is re-checked against its durable bound envelope artifact (the
    attempt-side record of what was sent), not against the runtime's own claim.
    A bound repair continuation reuses its parent's binding, so its binding pins the
    recorded root operation/attempt instead of the continuation's own ids.
    """
    present = [field for field in _CORE_BOUND_RECEIPT_FIELDS if field in receipt]
    if not present:
        return {}
    if len(present) != len(_CORE_BOUND_RECEIPT_FIELDS) or worker_backend != "open_swe":
        raise ClosureError("CORE_BINDING_RECEIPT_INVALID")
    if receipt.get("core_binding_status") != "BOUND":
        raise ClosureError("CORE_BINDING_NOT_BOUND")
    binding_hash = str(receipt.get("core_binding_hash") or "")
    contract_hash = str(receipt.get("acceptance_contract_hash") or "")
    bound_sha = str(receipt.get("bound_envelope_sha256") or "")
    if (
        not binding_hash.startswith("sha256:")
        or not _is_hex(binding_hash[7:], 64)
        or not contract_hash.startswith("sha256:")
        or not _is_hex(contract_hash[7:], 64)
        or not _is_hex(bound_sha, 64)
    ):
        raise ClosureError("CORE_BINDING_RECEIPT_INVALID")
    from nexus.services.external_intelligence_core_binding import (
        CoreBindingError,
        parse_bound_execution_envelope_v2,
    )

    bound_path = Path(str(receipt.get("bound_envelope_ref") or "")).expanduser()
    try:
        text = bound_path.read_text(encoding="utf-8")
        _semantic, binding, observed_bound_sha = parse_bound_execution_envelope_v2(
            text, semantic_envelope_sha256=str(receipt.get("envelope_sha256") or "")
        )
    except (OSError, UnicodeDecodeError, CoreBindingError) as exc:
        raise ClosureError("CORE_BINDING_ENVELOPE_INVALID") from exc
    root_fields = ("core_binding_operation_id", "core_binding_attempt_id")
    if receipt.get("mode") == "REPAIR_CONTINUE":
        root_operation = receipt.get("core_binding_operation_id")
        root_attempt = receipt.get("core_binding_attempt_id")
        if not isinstance(root_operation, str) or not isinstance(root_attempt, str):
            raise ClosureError("CORE_BINDING_RECEIPT_INVALID")
    elif any(field in receipt for field in root_fields):
        raise ClosureError("CORE_BINDING_RECEIPT_INVALID")
    else:
        root_operation = receipt.get("operation_id")
        root_attempt = receipt.get("attempt_id")
    if (
        observed_bound_sha != bound_sha
        or binding.get("binding_hash") != binding_hash
        or binding["core"].get("acceptance_contract_hash") != contract_hash
        or binding.get("attempt_id") != root_attempt
        or binding.get("operation_id") != root_operation
    ):
        raise ClosureError("CORE_BINDING_RECEIPT_MISMATCH")
    return {
        "core_binding_status": "BOUND",
        "core_binding_hash": binding_hash,
        "acceptance_contract_hash": contract_hash,
        "bound_envelope_sha256": bound_sha,
        "core_binding_operation_id": str(root_operation),
        "core_binding_attempt_id": str(root_attempt),
    }


def validate_worker_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(receipt, Mapping) or receipt.get("schema") != WORKER_RECEIPT_SCHEMA:
        raise ClosureError("INVALID_WORKER_RECEIPT")
    if receipt.get("status") != "CANDIDATE_READY_FOR_VERIFICATION":
        raise ClosureError("UNIT_CANDIDATE_REQUIRED")
    task_id = _safe_slug(receipt.get("task_id"), "task_id")
    unit_id = _safe_slug(receipt.get("unit_id"), "unit_id")
    if receipt.get("selected_worker"):
        try:
            selected_worker = validate_selected_worker(receipt["selected_worker"])
        except ExternalIntelligenceError as exc:
            raise ClosureError("INVALID_SELECTED_WORKER") from exc
        provider = str(selected_worker.get("provider") or PROVIDER)
        model = str(selected_worker.get("model") or MODEL)
        if receipt.get("provider") != provider or receipt.get("model") != model:
            raise ClosureError("WORKER_MODEL_BINDING_MISMATCH")
        if "/" in model:
            exp_p_id, exp_m_id = model.split("/", 1)
            expected_provider_id = exp_p_id.strip()
            expected_model_id = exp_m_id.strip()
        elif provider in ("opencode", "opencode-go"):
            expected_provider_id = "opencode-go"
            expected_model_id = model
        elif provider == "deepseek":
            expected_provider_id = "deepseek"
            expected_model_id = model
        else:
            expected_provider_id = provider
            expected_model_id = model
    else:
        selected_worker = None
        if receipt.get("provider") != PROVIDER or receipt.get("model") != MODEL:
            raise ClosureError("WORKER_MODEL_BINDING_MISMATCH")
        expected_provider_id = PROVIDER_ID
        expected_model_id = MODEL_ID
    receipt_provider_id = str(receipt.get("provider_id") or "").strip()
    receipt_model_id = str(receipt.get("model_id") or "").strip()
    if receipt_provider_id != expected_provider_id or receipt_model_id != expected_model_id:
        raise ClosureError("WORKER_ATTESTATION_MISMATCH")
    worker_backend = str(receipt.get("worker_backend") or "")
    if not worker_backend:
        legacy_provider = str(receipt.get("provider") or "")
        if legacy_provider not in {"deepseek", "opencode", "opencode-go"}:
            raise ClosureError("WORKER_BACKEND_REQUIRED")
        worker_backend = "opencode_legacy"
    elif worker_backend not in {"open_swe", "opencode"}:
        raise ClosureError("WORKER_BACKEND_INVALID")
    diagnosis_status = str(receipt.get("diagnosis_status") or "")
    if worker_backend == "open_swe":
        operation_id = receipt.get("operation_id")
        if not isinstance(operation_id, str) or not _is_hex(operation_id, 64):
            raise ClosureError("OPEN_SWE_OPERATION_ID_REQUIRED")
        diagnosis_sha256 = str(receipt.get("diagnosis_sha256") or "")
        evidence_paths = receipt.get("diagnosis_evidence_paths")
        repair_phase_count = receipt.get("repair_phase_count")
        worker_identity_sha256 = str(receipt.get("worker_identity_sha256") or "")
        if (
            diagnosis_status != "ROOT_CAUSE_SUPPORTED"
            or not _is_hex(diagnosis_sha256, 64)
            or not isinstance(evidence_paths, list)
            or not evidence_paths
            or any(not isinstance(path, str) or not path for path in evidence_paths)
            or receipt.get("repair_admitted") is not True
            or type(repair_phase_count) is not int
            or repair_phase_count < 1
            or not _is_hex(worker_identity_sha256, 64)
        ):
            raise ClosureError("OPEN_SWE_DIAGNOSIS_RECEIPT_INVALID")
        if selected_worker is None:
            raise ClosureError("OPEN_SWE_WORKER_BINDING_REQUIRED")
        expected_worker_sha = _sha256(_canonical_json(selected_worker))
        if worker_identity_sha256 != expected_worker_sha:
            raise ClosureError("OPEN_SWE_WORKER_IDENTITY_MISMATCH")
    core_binding = _validate_core_binding_receipt(receipt, worker_backend=worker_backend)
    session_id = str(receipt.get("session_id") or "")
    if not session_id.startswith(_SESSION_PREFIX) or len(session_id) < 12:
        raise ClosureError("INVALID_SESSION_ID")
    workspace_id = _safe_slug(receipt.get("workspace_id"), "workspace_id")
    workspace_path = Path(str(receipt.get("workspace_path") or "")).expanduser().resolve()
    if not workspace_path.is_dir():
        raise ClosureError("UNIT_WORKSPACE_MISSING")
    base_sha = str(receipt.get("base_sha") or "").lower()
    candidate_commit = str(receipt.get("candidate_commit") or "").lower()
    candidate_tree = str(receipt.get("candidate_tree") or "").lower()
    candidate_diff_sha256 = str(receipt.get("candidate_diff_sha256") or "").lower()
    receipt_id = str(receipt.get("receipt_id") or "").lower()
    if (
        not _is_hex(base_sha, 40)
        or not _is_hex(candidate_commit, 40)
        or not _is_hex(candidate_tree, 40)
    ):
        raise ClosureError("INVALID_CANDIDATE_GIT_IDENTITY")
    if not _is_hex(candidate_diff_sha256, 64) or not _is_hex(receipt_id, 64):
        raise ClosureError("INVALID_CANDIDATE_HASH_IDENTITY")
    if _receipt_identity(receipt) != receipt_id:
        raise ClosureError("WORKER_RECEIPT_IDENTITY_MISMATCH")
    if _run_git(workspace_path, "rev-parse", "HEAD") != candidate_commit:
        raise ClosureError("UNIT_WORKSPACE_HEAD_MISMATCH")
    if _run_git(workspace_path, "status", "--porcelain=v1"):
        raise ClosureError("UNIT_WORKSPACE_DIRTY")
    if _run_git(workspace_path, "rev-parse", "HEAD^{tree}") != candidate_tree:
        raise ClosureError("UNIT_CANDIDATE_TREE_MISMATCH")
    parent_commit = str(receipt.get("parent_commit") or base_sha).lower()
    if not _is_hex(parent_commit, 40):
        raise ClosureError("INVALID_PARENT_COMMIT")
    if _diff_sha(workspace_path, parent_commit, candidate_commit) != candidate_diff_sha256:
        raise ClosureError("UNIT_CANDIDATE_DIFF_HASH_MISMATCH")
    mutation_paths_raw = receipt.get("mutation_paths")
    if not isinstance(mutation_paths_raw, list) or not mutation_paths_raw:
        raise ClosureError("UNIT_MUTATION_SCOPE_MISSING")
    mutation_paths = [_safe_relative_path(path) for path in mutation_paths_raw]
    cumulative_changed = _changed_paths(workspace_path, base_sha, candidate_commit)
    if not cumulative_changed:
        raise ClosureError("EMPTY_UNIT_CANDIDATE")
    for path in cumulative_changed:
        if not any(_path_matches(path, boundary) for boundary in mutation_paths):
            raise ClosureError(f"UNIT_SCOPE_WIDENING:{path}")
    cumulative_deleted = _deleted_paths(workspace_path, base_sha, candidate_commit)
    if cumulative_deleted and not bool(receipt.get("allow_deletions", False)):
        raise ClosureError("UNIT_DELETION_NOT_AUTHORIZED")
    return {
        "task_id": task_id,
        "unit_id": unit_id,
        "receipt_id": receipt_id,
        "session_id": session_id,
        "workspace_id": workspace_id,
        "workspace_path": str(workspace_path),
        "base_sha": base_sha,
        "candidate_commit": candidate_commit,
        "candidate_tree": candidate_tree,
        "candidate_diff_sha256": candidate_diff_sha256,
        "parent_commit": parent_commit,
        "mutation_paths": mutation_paths,
        "allow_deletions": bool(receipt.get("allow_deletions", False)),
        "cumulative_changed_paths": cumulative_changed,
        "cumulative_deleted_paths": cumulative_deleted,
        "provider": str(receipt.get("provider") or PROVIDER),
        "model": str(receipt.get("model") or MODEL),
        "provider_id": receipt_provider_id,
        "model_id": receipt_model_id,
        "selected_worker": dict(receipt["selected_worker"])
        if receipt.get("selected_worker")
        else None,
        "worker_backend": worker_backend,
        "operation_id": str(receipt.get("operation_id") or ""),
        **core_binding,
    }


# --- Verifier hardening (#2793) -------------------------------------------------
# Pytest verifiers must leave positive JUnit evidence; every verifier runs with an
# allow-listed environment; candidate diffs that add or change root-level files able
# to shadow the interpreter or pytest configuration are refused unless authorized.
VERIFIER_EVIDENCE_PYTEST_JUNIT = "PYTEST_JUNIT"
VERIFIER_EVIDENCE_EXIT_CODE_ONLY = "EXIT_CODE_ONLY"
VERIFIER_JUNIT_MISSING = "VERIFIER_JUNIT_MISSING"
VERIFIER_JUNIT_INVALID = "VERIFIER_JUNIT_INVALID"
VERIFIER_JUNIT_NO_TESTS = "VERIFIER_JUNIT_NO_TESTS"
VERIFIER_JUNIT_FAILURES = "VERIFIER_JUNIT_FAILURES"
VERIFIER_JUNIT_SKIPPED = "VERIFIER_JUNIT_SKIPPED"
VERIFIER_DECLARED_TESTS_NOT_PASSED = "VERIFIER_DECLARED_TESTS_NOT_PASSED"
VERIFIER_PYTEST_INTERPRETER_UNRESOLVED = "VERIFIER_PYTEST_INTERPRETER_UNRESOLVED"
VERIFIER_ROOT_SHADOWING_REFUSED = "VERIFIER_ROOT_SHADOWING_REFUSED"
VERIFIER_ROOT_SHADOW_CHECK_ERROR = "VERIFIER_ROOT_SHADOW_CHECK_ERROR"
# Root-level paths (compared case-insensitively) that can shadow ``python -m pytest``
# or a plugin closure loads explicitly, inject code at interpreter start-up, or carry
# pytest configuration.
VERIFIER_ROOT_SHADOW_NAMES = frozenset({
    "pytest.py",
    "pytest_asyncio.py",
    "pluggy.py",
    "conftest.py",
    "sitecustomize.py",
    "usercustomize.py",
    "setup.cfg",
    "tox.ini",
    "pytest.ini",
    ".pytest.ini",
})
# Root-level package directories that shadow pytest (or the explicitly loaded
# ``pytest_asyncio`` plugin: the candidate root is on ``pythonpath``) like ``pytest.py``.
# ``pluggy`` (and ``pluggy.py`` above) too: pytest's hook machinery (#2811).
VERIFIER_ROOT_SHADOW_DIRS = frozenset({"pytest", "_pytest", "pytest_asyncio", "pluggy"})
# Basenames refused at ANY depth: a nested ``conftest.py`` below ``--confcutdir`` is
# loaded too and can rewrite outcomes (e.g. a ``pytest_runtest_makereport`` hookwrapper).
VERIFIER_ANY_DEPTH_SHADOW_NAMES = frozenset({"conftest.py"})
# The complete verifier environment.  Nothing else from the daemon environment is
# forwarded (no tokens, keys, ``GH_*``, ``NEXUS_*``, ``PYTHONPATH``, ``GIT_*`` ...).
# ``PATH`` is needed because task cards name ``python3``/``sh``/``git`` by name and the
# deployment puts the Nexus venv ``bin`` first on PATH (docs/ops/eia_nightly.md); a venv
# interpreter locates its site-packages from ``pyvenv.cfg``, so ``VIRTUAL_ENV`` and
# ``UV_*`` are not needed.  ``HOME`` and ``TMPDIR`` are fresh per-verifier temp dirs.
VERIFIER_ENV_FORWARDED = ("PATH", "LANG", "LC_ALL")
# Set by closure itself for a pytest verifier (#2795), never forwarded: the witness
# channel fds and ``PYTHONPATH`` = the parent-owned dir holding the witness plugin.  The
# witness removes all three from ``os.environ`` before any test module is imported.
VERIFIER_WITNESS_ENV_KEYS = (
    "NEXUS_VERIFIER_WITNESS_FD",
    "NEXUS_VERIFIER_WITNESS_KEY_FD",
    "PYTHONPATH",
)
VERIFIER_ENV_ALLOWLIST = frozenset({
    *VERIFIER_ENV_FORWARDED,
    *VERIFIER_WITNESS_ENV_KEYS,
    "HOME",
    "TMPDIR",
    "PYTHONDONTWRITEBYTECODE",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    VERIFIER_ENV_BASE_SHA,
    VERIFIER_ENV_CANDIDATE_SHA,
})
# Keys copied from the BASE commit's pytest configuration into the verifier's own ini
# (the candidate tree's configuration is never read).  ``addopts`` is not copied; only its
# ``--import-mode=`` token is kept.
_PYTEST_BASE_INI_KEYS = (
    "python_files",
    "python_classes",
    "python_functions",
    "norecursedirs",
    "testpaths",
    "filterwarnings",
    "markers",
    "xfail_strict",
    "asyncio_mode",
    "asyncio_default_fixture_loop_scope",
    "asyncio_default_test_loop_scope",
)
_PYTEST_VALUE_OPTIONS = frozenset({
    "-k",
    "-m",
    "-n",
    "-p",
    "-o",
    "-c",
    "-W",
    "-r",
    "--assert",
    "--basetemp",
    "--capture",
    "--code-highlight",
    "--color",
    "--confcutdir",
    "--config-file",
    "--cov",
    "--cov-config",
    "--cov-fail-under",
    "--cov-report",
    "--deselect",
    "--dist",
    "--durations",
    "--durations-min",
    "--ignore",
    "--ignore-glob",
    "--import-mode",
    "--junit-xml",
    "--junitxml",
    "--log-auto-indent",
    "--log-cli-date-format",
    "--log-cli-format",
    "--log-cli-level",
    "--log-date-format",
    "--log-file",
    "--log-file-date-format",
    "--log-file-format",
    "--log-file-level",
    "--log-format",
    "--log-level",
    "--maxfail",
    "--maxprocesses",
    "--numprocesses",
    "--override-ini",
    "--pastebin",
    "--rootdir",
    "--rsyncdir",
    "--rsyncignore",
    "--show-capture",
    "--tb",
    "--timeout",
    "--timeout-method",
    "--tx",
    "--verbosity",
})
_PYTHON_VALUE_OPTIONS = frozenset({"-X", "-W", "-Q"})


def _short_option_takes_next(token: str) -> bool:
    """Whether a short option group (``-k``, ``-xk``) takes the next token as its value."""
    letters = token[1:]
    for position, letter in enumerate(letters):
        if f"-{letter}" in _PYTEST_VALUE_OPTIONS:
            return position == len(letters) - 1  # otherwise the value is attached (``-pno:x``)
    return False


def _pytest_target_indices(args: Sequence[str]) -> tuple[tuple[int, ...], frozenset[int]]:
    """Indices of ``args`` that pytest takes as file, directory or node targets (#2934), and
    which of them may instead be the value of the unknown long option before them.

    The value of a known value option (``--durations 5``, ``-k expr``, ``-xk expr``) is never a
    target. A token right after an unknown long option written without ``=`` may be that option's
    value or a target: it counts only when another target exists, so it never narrows a card's
    targets and never turns a card without targets into a file-scoped one. Everything after
    ``--`` is a target."""
    certain: list[int] = []
    maybe: list[int] = []
    after_unknown_long = False
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            certain.extend(range(index + 1, len(args)))
            break
        if token.startswith("--"):
            name, has_eq, _ = token.partition("=")
            takes_next = not has_eq and name in _PYTEST_VALUE_OPTIONS
            after_unknown_long = not has_eq and not takes_next
            index += 2 if takes_next else 1
            continue
        if token.startswith("-") and len(token) > 1:
            after_unknown_long = False
            index += 2 if _short_option_takes_next(token) else 1
            continue
        (maybe if after_unknown_long else certain).append(index)
        after_unknown_long = False
        index += 1
    if not certain:
        return (), frozenset()
    return tuple(sorted(certain + maybe)), frozenset(maybe)


def _with_pytest_options(args: Sequence[str], *options: str) -> tuple[str, ...]:
    """``args`` with ``options`` added after its last option, before a ``--`` separator: pytest
    reads every token after ``--`` as a target, an appended option included (#2934)."""
    end = args.index("--") if "--" in args else len(args)
    return (*args[:end], *options, *args[end:])


_PYTHON_NAME_RE = re.compile(r"^python(?:[0-9]+(?:\.[0-9]+)*)?$")
_JUNIT_MAX_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class _PytestInvocation:
    interpreter: str
    interpreter_args: tuple[str, ...]
    pytest_args: tuple[str, ...]
    declared_node_ids: tuple[str, ...]
    # Positional file or directory targets without ``::`` (#2811).
    declared_paths: tuple[str, ...] = ()


def _pytest_invocation(argv: Sequence[str], path_env: str) -> _PytestInvocation | None | str:
    """Classify ``argv``: a pytest invocation, ``None`` (not pytest) or an error code."""
    if not argv:
        return None
    name = PurePosixPath(argv[0]).name
    if name in {"pytest", "py.test"}:
        located = argv[0] if "/" in argv[0] else shutil.which(argv[0], path=path_env)
        if not located:
            return VERIFIER_PYTEST_INTERPRETER_UNRESOLVED
        directory = Path(located).parent
        interpreter = next(
            (str(directory / c) for c in ("python3", "python") if (directory / c).is_file()),
            "",
        )
        if not interpreter:
            return VERIFIER_PYTEST_INTERPRETER_UNRESOLVED
        interpreter_args: tuple[str, ...] = ()
        pytest_args = tuple(argv[1:])
    elif _PYTHON_NAME_RE.match(name):
        index = 1
        while index < len(argv) and argv[index] != "-m":
            token = argv[index]
            if not token.startswith("-") or token.startswith("-c"):
                return None
            index += 2 if token in _PYTHON_VALUE_OPTIONS else 1
        if index + 1 >= len(argv) or argv[index + 1] != "pytest":
            return None
        interpreter = argv[0]
        interpreter_args = tuple(argv[1:index])
        pytest_args = tuple(argv[index + 2 :])
    else:
        return None
    declared: list[str] = []
    declared_paths: list[str] = []
    for index in _pytest_target_indices(pytest_args)[0]:
        token = pytest_args[index]
        if "::" not in token:
            declared_paths.append(token)
            continue
        path_part, _, rest = token.partition("::")
        declared.append(f"{PurePosixPath(path_part).as_posix()}::{rest}")
    return _PytestInvocation(
        interpreter=interpreter,
        interpreter_args=interpreter_args,
        pytest_args=pytest_args,
        declared_node_ids=tuple(declared),
        declared_paths=tuple(declared_paths),
    )


def _git_show_bytes(root: Path, rev: str, path: str) -> bytes | None:
    try:
        proc = subprocess.run(
            ["git", "show", f"{rev}:{path}"],
            cwd=root,
            capture_output=True,
            timeout=INTEGRITY_CHECK_TIMEOUT_SECONDS,
            check=False,
            env=_git_no_replace_env(),
        )
    except subprocess.TimeoutExpired:
        return None
    return proc.stdout if proc.returncode == 0 else None


def _base_pytest_config(root: Path, base_sha: str) -> tuple[dict[str, Any], str]:
    """Read pytest configuration from ``base_sha`` (never the candidate tree).

    Returns the raw key/value mapping and the source path ("" when there is none).
    Discovery order follows pytest: ``pytest.ini``, ``.pytest.ini``, ``pyproject.toml``
    ``[tool.pytest.ini_options]``, ``tox.ini`` ``[pytest]``, ``setup.cfg`` ``[tool:pytest]``.
    """
    import configparser
    import tomllib

    def ini_section(raw: bytes, section: str) -> dict[str, Any] | None:
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read_string(raw.decode("utf-8"))
        except (configparser.Error, UnicodeDecodeError):
            return None
        if not parser.has_section(section):
            return None
        return dict(parser.items(section))

    for path, section in (("pytest.ini", "pytest"), (".pytest.ini", "pytest")):
        raw = _git_show_bytes(root, base_sha, path)
        if raw is not None:
            return ini_section(raw, section) or {}, path
    raw = _git_show_bytes(root, base_sha, "pyproject.toml")
    if raw is not None:
        try:
            data = tomllib.loads(raw.decode("utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError):
            data = {}
        options = data.get("tool", {}).get("pytest", {}).get("ini_options")
        if isinstance(options, Mapping):
            return dict(options), "pyproject.toml"
    for path, section in (("tox.ini", "pytest"), ("setup.cfg", "tool:pytest")):
        raw = _git_show_bytes(root, base_sha, path)
        if raw is not None:
            values = ini_section(raw, section)
            if values is not None:
                return values, path
    return {}, ""


def _ini_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "".join(f"\n    {item}" for item in value)
    text = str(value)
    if "\n" in text:
        return "".join(f"\n    {line.strip()}" for line in text.splitlines() if line.strip())
    return text


def _verifier_pytest_ini(root: Path, base_config: Mapping[str, Any]) -> tuple[str, list[str]]:
    """Render the verifier's own ini and the extra pytest args derived from the base config."""
    lines = ["[pytest]"]
    for key in _PYTEST_BASE_INI_KEYS:
        if key in base_config:
            lines.append(f"{key} = {_ini_value(base_config[key])}")
    # ``-P`` removes the cwd from sys.path; pytest re-adds the candidate root (and any
    # base-declared pythonpath entries) once pytest itself is imported, so a root
    # ``pytest.py`` can no longer replace pytest while candidate packages stay importable.
    raw_paths = base_config.get("pythonpath") or []
    if isinstance(raw_paths, str):
        raw_paths = shlex.split(raw_paths)
    paths = [str(root)]
    for entry in raw_paths:
        candidate = (root / str(entry)).resolve()
        if candidate.is_relative_to(root) and str(candidate) not in paths:
            paths.append(str(candidate))
    lines.append("pythonpath = " + " ".join(shlex.quote(p) for p in paths))
    lines.append("junit_family = xunit2")
    extra: list[str] = []
    addopts = base_config.get("addopts") or []
    if isinstance(addopts, str):
        try:
            addopts = shlex.split(addopts)
        except ValueError:
            addopts = []
    tokens = [str(token) for token in addopts]
    for index, token in enumerate(tokens):
        if token.startswith("--import-mode="):
            extra.append(token)
        elif token == "--import-mode" and index + 1 < len(tokens):
            extra.append(f"--import-mode={tokens[index + 1]}")
    # Plugin autoload is disabled; load pytest-asyncio explicitly when the base config
    # declares it (otherwise async tests fail, which is fail-closed).
    if any(str(key).startswith("asyncio_") for key in base_config):
        extra.extend(["-p", "pytest_asyncio.plugin"])
    return "\n".join(lines) + "\n", extra


_SKIP_LOCATION_RES = (
    re.compile(r"^\('(?P<path>[^']+)', [0-9]+,"),
    re.compile(r"^(?P<path>[^\n:]+):[0-9]+: "),
)


def _dotted_module(path: str) -> str:
    return re.sub(r"\.py$", "", PurePosixPath(path).as_posix().replace("/", "."))


def _empty_junit_summary(declared_node_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "present": False,
        "tests": 0,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "declared_node_ids": list(declared_node_ids),
        "declared_node_ids_not_passed": [],
        "skipped_touched": [],
        "skipped_untouched": [],
        "skipped_at_base": [],
        "skipped_not_at_base": [],
    }


def _junit_evidence(
    junit_path: Path,
    declared_node_ids: Sequence[str],
    *,
    root: Path | None = None,
    touched_paths: Sequence[str] = (),
    base_skipped: Collection[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Positive evidence from a JUnit file: (error code or "", summary).

    See ``_junit_evidence_bytes``; this reads the file (no symlink, bounded size).
    """
    summary = _empty_junit_summary(declared_node_ids)
    try:
        if not junit_path.is_file() or junit_path.is_symlink():
            return VERIFIER_JUNIT_MISSING, summary
        if junit_path.stat().st_size > _JUNIT_MAX_BYTES:
            return VERIFIER_JUNIT_INVALID, summary
        with junit_path.open("rb") as stream:
            raw = stream.read(_JUNIT_MAX_BYTES + 1)
    except OSError:
        return VERIFIER_JUNIT_MISSING, summary
    return _junit_evidence_bytes(
        raw, declared_node_ids, root=root, touched_paths=touched_paths, base_skipped=base_skipped
    )


def _junit_evidence_bytes(
    raw: bytes,
    declared_node_ids: Sequence[str],
    *,
    root: Path | None = None,
    touched_paths: Sequence[str] = (),
    base_skipped: Collection[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Positive evidence from JUnit bytes: (error code or "", summary).

    Skip policy (#2795): a skipped (or xfailed) test is tolerated only when the same
    node was also skipped when the same verifier ran at the base commit
    (``base_skipped``, from ``_run_base_verifier``); with no base comparison every skip
    fails.  ``skipped_touched`` / ``skipped_untouched`` (#2794) are kept as information.
    At least one test must pass and every declared node id must pass.
    """
    import xml.etree.ElementTree as ElementTree

    touched_modules = {_dotted_module(p) for p in touched_paths if p.endswith(".py")}
    touched_set = {PurePosixPath(p).as_posix() for p in touched_paths}

    def skip_is_touched(owner: str, text: str) -> bool:
        if any(owner == m or owner.startswith(m + ".") for m in touched_modules):
            return True
        for pattern in _SKIP_LOCATION_RES:
            match = pattern.match(text.strip())
            if not match:
                continue
            location = Path(match.group("path"))
            if root is not None and location.is_absolute():
                try:
                    location = location.resolve().relative_to(root)
                except (OSError, ValueError):
                    return False
            return location.as_posix() in touched_set
        return False

    summary = _empty_junit_summary(declared_node_ids)
    summary["present"] = True
    summary["junit_sha256"] = _sha256(raw)
    # The JUnit file is untrusted (candidate code can write it): refuse oversized
    # files, NUL bytes (UTF-16/32 would hide the markers below) and any DTD/entity
    # declaration, the XML feature that makes the stdlib parser unsafe, before parsing.
    upper = raw.upper()
    if (
        len(raw) > _JUNIT_MAX_BYTES
        or b"\x00" in raw
        or b"<!DOCTYPE" in upper
        or b"<!ENTITY" in upper
    ):
        return VERIFIER_JUNIT_INVALID, summary
    try:
        tree = ElementTree.fromstring(raw)  # noqa: S314  # nosec B314 - DTD/entities rejected above
    except ElementTree.ParseError:
        return VERIFIER_JUNIT_INVALID, summary
    suites = list(tree.iter("testsuite"))
    if tree.tag not in {"testsuite", "testsuites"} or not suites:
        return VERIFIER_JUNIT_INVALID, summary
    attr_counts = {"failures": 0, "errors": 0, "skipped": 0}
    case_counts = {"failures": 0, "errors": 0, "skipped": 0}
    passed_names: list[str] = []
    skipped_names: list[str] = []
    for suite in suites:
        try:
            for key in attr_counts:
                attr_counts[key] += int(suite.get(key) or 0)
        except ValueError:
            return VERIFIER_JUNIT_INVALID, summary
        for case in suite.iter("testcase"):
            summary["tests"] += 1
            outcomes = {child.tag for child in case}
            case_counts["failures"] += int("failure" in outcomes)
            case_counts["errors"] += int("error" in outcomes)
            case_counts["skipped"] += int("skipped" in outcomes)
            classname = str(case.get("classname") or "")
            name = str(case.get("name") or "")
            full = f"{classname}.{name}" if classname else name
            if "skipped" in outcomes and not outcomes & {"failure", "error"}:
                skipped = case.find("skipped")
                text = (skipped.text or "") if skipped is not None else ""
                bucket = (
                    "skipped_touched"
                    if skip_is_touched(classname or name, text)
                    else "skipped_untouched"
                )
                summary[bucket].append(full)
                skipped_names.append(full)
            if outcomes & {"failure", "error", "skipped"}:
                continue
            passed_names.append(full)
    for key in attr_counts:
        summary[key] = max(attr_counts[key], case_counts[key])
    if summary["errors"] or summary["failures"]:
        return VERIFIER_JUNIT_FAILURES, summary
    # A skip count in the suite attributes without matching testcases cannot be
    # attributed to a module, so it is treated as touched.
    unattributed = summary["skipped"] - case_counts["skipped"]
    summary["skipped_touched"] = summary["skipped_touched"][:_INTEGRITY_FINDINGS_LIMIT]
    summary["skipped_untouched"] = summary["skipped_untouched"][:_INTEGRITY_FINDINGS_LIMIT]
    at_base = set(base_skipped or ())
    not_at_base = [name for name in skipped_names if name not in at_base]
    summary["skipped_at_base"] = [n for n in skipped_names if n in at_base][
        :_INTEGRITY_FINDINGS_LIMIT
    ]
    summary["skipped_not_at_base"] = not_at_base[:_INTEGRITY_FINDINGS_LIMIT]
    if not_at_base or unattributed > 0:
        return VERIFIER_JUNIT_SKIPPED, summary
    if summary["tests"] < 1 or not passed_names:
        return VERIFIER_JUNIT_NO_TESTS, summary
    missing: list[str] = []
    for node_id in declared_node_ids:
        path_part, open_bracket, params = node_id.partition("[")
        names = path_part.split("::")
        names[0] = re.sub(r"\.py$", "", names[0].replace("/", "."))
        names[-1] += open_bracket + params
        dotted = ".".join(names)
        if not any(
            full == dotted
            or full.startswith(dotted + ".")
            or (not open_bracket and full.startswith(dotted + "["))
            for full in passed_names
        ):
            missing.append(node_id)
    summary["declared_node_ids_not_passed"] = missing
    if missing:
        return VERIFIER_DECLARED_TESTS_NOT_PASSED, summary
    return "", summary


def _candidate_changed_paths(root: Path, base_sha: str, candidate_commit: str) -> list[str] | None:
    """Paths changed in ``base_sha..candidate_commit`` (``None`` when git fails)."""
    _argv, rc, out, _err = _integrity_git(
        root,
        [
            "diff",
            "--no-ext-diff",
            "--no-renames",
            "--name-only",
            "-z",
            base_sha,
            candidate_commit,
            "--",
        ],
    )
    if rc != 0:
        return None
    return sorted(set(_nul_paths(out)))


def _shadowing_paths(changed_paths: Sequence[str]) -> list[str]:
    found: list[str] = []
    for path in changed_paths:
        parts = PurePosixPath(path).parts
        if not parts:
            continue
        head = parts[0].casefold()
        name = PurePosixPath(path).name.casefold()
        if (
            (len(parts) == 1 and head in VERIFIER_ROOT_SHADOW_NAMES)
            or (len(parts) > 1 and head in VERIFIER_ROOT_SHADOW_DIRS)
            or name in VERIFIER_ANY_DEPTH_SHADOW_NAMES
        ):
            found.append(path)
    return sorted(set(found))


def _root_shadowing_paths(
    root: Path, base_sha: str, candidate_commit: str
) -> tuple[list[str] | None, str]:
    """Shadowing paths changed in ``base_sha..candidate_commit``: root-level
    interpreter/pytest shadows and config files, and ``conftest.py`` at any depth.

    Returns ``(None, code)`` when git fails (fail closed).
    """
    changed = _candidate_changed_paths(root, base_sha, candidate_commit)
    if changed is None:
        return None, VERIFIER_ROOT_SHADOW_CHECK_ERROR
    return _shadowing_paths(changed), ""


def _verifier_env(
    *, home: Path, tmpdir: Path, base_sha: str, candidate_commit: str
) -> dict[str, str]:
    env = {key: os.environ[key] for key in VERIFIER_ENV_FORWARDED if key in os.environ}
    env.setdefault("PATH", os.defpath)
    env["HOME"] = str(home)
    env["TMPDIR"] = str(tmpdir)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env[VERIFIER_ENV_BASE_SHA] = base_sha
    env[VERIFIER_ENV_CANDIDATE_SHA] = candidate_commit
    return env


# --- Out-of-process verifier evidence (#2795) ----------------------------------
# Candidate code runs inside the pytest process, so nothing that process reports about
# itself is trusted on its own.  A pytest verifier now runs:
#
# * under ``sandbox-exec`` (macOS) with the ``nexus.engine.sandboxed_lane`` profile:
#   network denied, writes confined to the work tree and a per-run scratch dir, the
#   parent's evidence and trusted dirs and the work tree's ``.git`` denied last;
# * with the trusted witness plugin (``external_intelligence_verifier_witness``) loaded
#   from a parent-owned dir before any candidate code.  It streams MAC'd records over an
#   inherited pipe; the parent rebuilds the JUnit evidence from them and writes it into a
#   dir the child cannot write.  A test counts as passed only when pytest's report says
#   passed AND the witness saw the test's own code object start and return without an
#   exception unwinding out of it, so a rewritten report, a swallowed exception or a test
#   that never ran is not passed;
# * a skip is tolerated only when the same node is also skipped when the same verifier
#   runs at the base commit in a read-only base checkout.
#
# Without an OS barrier (Linux) the verifier runs unsandboxed as in #2794, with the same
# witness, and the row records ``sandbox.sandboxed: false``.
VERIFIER_WITNESS_PLUGIN = "_nexus_eia_verifier_witness"
VERIFIER_WITNESS_SOURCE = Path(__file__).with_name("external_intelligence_verifier_witness.py")
VERIFIER_WITNESS_FD_ENV = "NEXUS_VERIFIER_WITNESS_FD"
VERIFIER_WITNESS_KEY_FD_ENV = "NEXUS_VERIFIER_WITNESS_KEY_FD"
VERIFIER_WITNESS_KEY_BYTES = 32
VERIFIER_WITNESS_MAX_BYTES = 32 * 1024 * 1024
VERIFIER_OUTPUT_MAX_BYTES = 16 * 1024 * 1024
VERIFIER_DRAIN_GRACE_SECONDS = 2.0
VERIFIER_WITNESS_TAMPERED = "VERIFIER_WITNESS_TAMPERED"
VERIFIER_FOREIGN_PLUGIN = "VERIFIER_FOREIGN_PLUGIN"
VERIFIER_PYTEST_INTERNALS_PATCHED = "VERIFIER_PYTEST_INTERNALS_PATCHED"
VERIFIER_OUTCOME_FORGED = "VERIFIER_OUTCOME_FORGED"
VERIFIER_TEST_IDENTITY_UNRESOLVED = "VERIFIER_TEST_IDENTITY_UNRESOLVED"
VERIFIER_TESTS_DESELECTED = "VERIFIER_TESTS_DESELECTED"
# A node of a declared file (or directory) was deselected or silently dropped while the
# candidate changed a ``conftest.py`` (#2811).
VERIFIER_DECLARED_FILE_DESELECTED = "VERIFIER_DECLARED_FILE_DESELECTED"
# A node the same verifier selects at the base commit, in a declared target whose test
# file the candidate did not change, is not selected in the candidate run while the
# candidate changed a ``conftest.py`` (dropped at collection time; #2811 review).
VERIFIER_DECLARED_NODE_MISSING = "VERIFIER_DECLARED_NODE_MISSING"
VERIFIER_SANDBOX_SETUP_FAILED = "VERIFIER_SANDBOX_SETUP_FAILED"
VERIFIER_EVIDENCE_TAMPERED = "VERIFIER_EVIDENCE_TAMPERED"
VERIFIER_BASE_RUN_FAILED = "VERIFIER_BASE_RUN_FAILED"
# Options with which a card itself narrows the selection; without one of them a node
# that was collected but not selected is a candidate-made deselection.
_DESELECT_OPTIONS = frozenset({"-k", "-m", "--deselect"})
_XML_INVALID_CHARS = re.compile("[^\t\n\r\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")
# Prefixes, executable, then the import roots of pytest and the plugins closure loads.
# The roots matter when the runtime is linked into the venv through ``.pth`` path lines
# (the trusted impact executor's offline runtime, #2808): they are neither prefix.
_INTERPRETER_PROBE = (
    "import importlib.util, os, sys\n"
    "print(sys.prefix); print(sys.base_prefix); print(sys.executable)\n"
    "for name in ('pytest', '_pytest', 'pluggy', 'pytest_asyncio'):\n"
    "    spec = importlib.util.find_spec(name)\n"
    "    if spec is None or not spec.origin:\n"
    "        continue\n"
    "    path = os.path.dirname(spec.origin)\n"
    "    print(os.path.dirname(path) if spec.submodule_search_locations else path)\n"
)


def _junit_names(nodeid: str) -> tuple[str, str]:
    """(classname, name) as pytest's junitxml derives them (``mangle_test_address``)."""
    path, open_bracket, params = nodeid.partition("[")
    names = path.split("::")
    names[0] = re.sub(r"\.py$", "", names[0].replace("/", "."))
    names[-1] += open_bracket + params
    return ".".join(names[:-1]), names[-1]


def _junit_full_name(nodeid: str) -> str:
    classname, name = _junit_names(nodeid)
    return f"{classname}.{name}" if classname else name


def _render_junit(cases: Sequence[tuple[str, str, str]]) -> bytes:
    """JUnit XML for ``(nodeid, kind, text)`` cases; kind is passed/failure/error/skipped."""
    import xml.etree.ElementTree as ElementTree

    counts = {kind: sum(1 for _, k, _ in cases if k == kind) for kind in ("failure", "error")}
    skipped = sum(1 for _, k, _ in cases if k == "skipped")
    suites = ElementTree.Element("testsuites")
    suite = ElementTree.SubElement(
        suites,
        "testsuite",
        name="nexus-eia-verifier-witness",
        tests=str(len(cases)),
        failures=str(counts["failure"]),
        errors=str(counts["error"]),
        skipped=str(skipped),
    )
    for nodeid, kind, text in cases:
        classname, name = _junit_names(nodeid)
        case = ElementTree.SubElement(
            suite,
            "testcase",
            classname=_XML_INVALID_CHARS.sub("?", classname),
            name=_XML_INVALID_CHARS.sub("?", name),
        )
        if kind != "passed":
            child = ElementTree.SubElement(case, kind, message=kind)
            child.text = _XML_INVALID_CHARS.sub("?", text)[:4000]
    return ElementTree.tostring(suites, encoding="utf-8", xml_declaration=True)


def _parse_witness(raw: bytes, key: bytes) -> tuple[str, list[dict[str, Any]]]:
    """Verify and decode the witness stream: ("" or VERIFIER_WITNESS_TAMPERED, records)."""
    import hmac

    if len(raw) > VERIFIER_WITNESS_MAX_BYTES or (raw and not raw.endswith(b"\n")):
        return VERIFIER_WITNESS_TAMPERED, []
    records: list[dict[str, Any]] = []
    for index, line in enumerate(raw.split(b"\n")[:-1]):
        mac, _sep, payload = line.partition(b" ")
        expected = hmac.new(key, payload, hashlib.sha256).hexdigest().encode("ascii")
        if not hmac.compare_digest(mac, expected):
            return VERIFIER_WITNESS_TAMPERED, records
        try:
            record = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return VERIFIER_WITNESS_TAMPERED, records
        if not isinstance(record, dict) or record.get("seq") != index:
            return VERIFIER_WITNESS_TAMPERED, records
        records.append(record)
    return "", records


def _empty_witness_summary() -> dict[str, Any]:
    return {
        "present": False,
        "records": 0,
        "complete": False,
        "error": "",
        "foreign_plugins": [],
        "pytest_internals_patched": [],
        "forged_node_ids": [],
        "not_run_node_ids": [],
        "deselected_node_ids": [],
        "declared_file_deselected_node_ids": [],
        "identity_unresolved_node_ids": [],
        "declared_node_ids_missing": [],
    }


def _expected_test_code(
    root: Path, nodeid: str, cache: dict[str, Any]
) -> tuple[str, str, int] | None:
    """(file, qualname, first line) of the test function ``nodeid`` names, read with
    ``ast`` from the checked-out test file (never from the verifier process).

    A method not defined in the named class is looked up in base classes defined in
    the same file.  ``None`` (not passed) when the definition cannot be found, e.g. a
    test assembled at runtime or inherited from another module.
    """
    import ast

    path_part = nodeid.partition("[")[0]
    rel, *names = path_part.split("::")
    if not names:
        return None
    file = (root / rel).resolve()
    if not file.is_relative_to(root):
        return None
    if rel not in cache:
        try:
            cache[rel] = ast.parse(file.read_bytes())
        except (OSError, SyntaxError, ValueError):
            cache[rel] = None
    tree = cache[rel]
    if tree is None:
        return None
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}

    def find(body: Sequence[ast.stmt], chain: list[str], remaining: list[str], seen: set[str]):
        head, rest = remaining[0], remaining[1:]
        for node in body:
            if rest and isinstance(node, ast.ClassDef) and node.name == head:
                found = find(node.body, [*chain, head], rest, seen)
                if found:
                    return found
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id in classes and base.id not in seen:
                        cls = classes[base.id]
                        found = find(cls.body, [cls.name], rest, seen | {base.id})
                        if found:
                            return found
            if (
                not rest
                and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == head
            ):
                same = [
                    n
                    for n in body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == head
                ]
                if len(same) != 1:
                    return None  # defined twice: the identity is ambiguous
                lines = [node.lineno, *(d.lineno for d in node.decorator_list)]
                return ".".join([*chain, head]), min(lines)
        return None

    found = find(tree.body, [], names, set())
    if not found:
        return None
    return str(file), found[0], found[1]


def _witness_passed(
    witness: Mapping[str, Any] | None, expected: tuple[str, str, int] | None
) -> bool:
    """The witness saw the test's OWN code object (file, qualname, first line as the
    test file defines it) start and return, with no exception unwinding out of it."""
    if not witness or expected is None:
        return False
    try:
        code_file = str(Path(str(witness.get("code_file") or "")).resolve())
    except (OSError, ValueError):
        return False
    return (
        (code_file, str(witness.get("code_qualname") or ""), witness.get("code_firstlineno"))
        == expected
        and int(witness.get("starts") or 0) >= 1
        and int(witness.get("returns") or 0) >= 1
        and int(witness.get("unwinds") or 0) == 0
        and int(witness.get("depth") or 0) == 0
    )


def _plugin_is_trusted(
    path_text: str,
    *,
    root: Path,
    trusted_dirs: Sequence[Path],
    in_tree_trusted: Callable[[str], bool] = lambda _rel: False,
) -> bool:
    """A plugin may come from the trusted interpreter or the witness dir, be a
    ``conftest.py`` in the tree (a changed one is refused or explicitly authorized
    before the run), or be an in-tree module that ``in_tree_trusted`` accepts (tracked
    at the base commit and not changed by the candidate).  Anything else, e.g. a module
    the candidate added or changed and names in ``pytest_plugins``, is foreign."""
    if not path_text:
        return False
    try:
        path = Path(path_text).resolve()
    except (OSError, ValueError):
        return False
    if path.is_relative_to(root):
        if path.name.casefold() == "conftest.py":
            return True
        return in_tree_trusted(path.relative_to(root).as_posix())
    return any(path.is_relative_to(directory) for directory in trusted_dirs)


def _base_unchanged_predicate(
    root: Path, base_sha: str, changed_paths: Sequence[str]
) -> Callable[[str], bool]:
    """``rel`` is tracked at ``base_sha`` (no ``refs/replace``) and the candidate diff
    does not change it: an in-tree helper plugin the candidate did not write."""
    changed = {PurePosixPath(p).as_posix() for p in changed_paths}
    cache: dict[str, bool] = {}

    def trusted(rel: str) -> bool:
        if rel in changed:
            return False
        if rel not in cache:
            try:
                proc = subprocess.run(
                    ["git", "cat-file", "-e", f"{base_sha}:{rel}"],
                    cwd=root,
                    capture_output=True,
                    timeout=INTEGRITY_CHECK_TIMEOUT_SECONDS,
                    check=False,
                    env=_git_no_replace_env(),
                )
                cache[rel] = proc.returncode == 0
            except (OSError, subprocess.SubprocessError):
                cache[rel] = False
        return cache[rel]

    return trusted


def _declared_match(nodeid: str, declared: Sequence[str]) -> bool:
    return any(
        nodeid == d or nodeid.startswith(d + "::") or nodeid.startswith(d + "[") for d in declared
    )


def _declared_path_prefixes(root: Path, declared_paths: Sequence[str]) -> list[str]:
    """Root-relative posix forms of the card's positional file/directory targets."""
    prefixes: list[str] = []
    for token in declared_paths:
        text = os.path.normpath(token)
        if os.path.isabs(text):
            try:
                text = os.path.relpath(os.path.realpath(text), root)
            except ValueError:
                continue
        prefixes.append(Path(text).as_posix())
    return prefixes


def _conftest_changed(changed_paths: Sequence[str]) -> bool:
    """The candidate diff touches a ``conftest.py`` at any depth (git paths use ``/``)."""
    return any(PurePosixPath(p).name.casefold() == "conftest.py" for p in changed_paths)


def _in_declared_path(nodeid: str, prefixes: Sequence[str]) -> bool:
    path = nodeid.split("::", 1)[0]
    return any(p == "." or path == p or path.startswith(p + "/") for p in prefixes)


def _witness_outcomes(
    records: Sequence[Mapping[str, Any]],
    *,
    root: Path,
    trusted_plugin_dirs: Sequence[Path],
    deselect_allowed: bool,
    declared_node_ids: Sequence[str] = (),
    in_tree_trusted: Callable[[str], bool] = lambda _rel: False,
    declared_paths: Sequence[str] = (),
    conftest_changed: bool = False,
) -> tuple[str, list[tuple[str, str, str]] | None, dict[str, Any]]:
    """Derive per-test outcomes from verified witness records.

    Returns (error code or "", JUnit cases or None when the stream is incomplete,
    witness summary).  pytest's reports are untrusted: "passed" also needs the witness
    observation; "failed"/"skipped" are believed because they can only lose a pass.

    ``conftest_changed`` (the candidate diff touches a ``conftest.py``): a deselected or
    silently dropped node of a declared file or directory (``declared_paths``; no
    positional target at all declares the whole run) is refused (#2811), since a
    file-level declaration is otherwise satisfied by any surviving node of that file.
    """
    summary = _empty_witness_summary()
    summary["present"] = bool(records)
    summary["records"] = len(records)
    if not records or records[0].get("t") != "begin" or records[-1].get("t") != "end":
        return VERIFIER_JUNIT_MISSING, None, summary
    summary["complete"] = True
    foreign: list[str] = []
    collected: list[str] = []
    selected: list[str] | None = None
    deselected_by_hook: set[str] = set()
    collect_cases: list[tuple[str, str, str]] = []
    reports: dict[str, dict[str, Mapping[str, Any]]] = {}
    witnesses: dict[str, Mapping[str, Any]] = {}
    for record in records:
        kind = record.get("t")
        nodeid = str(record.get("nodeid") or "")
        if kind == "plugin":
            if not _plugin_is_trusted(
                str(record.get("file") or ""),
                root=root,
                trusted_dirs=trusted_plugin_dirs,
                in_tree_trusted=in_tree_trusted,
            ):
                foreign.append(f"{record.get('name')}:{record.get('file') or '<no file>'}")
        elif kind == "item":
            collected.append(nodeid)
        elif kind == "selected":
            selected = [str(n) for n in record.get("nodeids") or []]
        elif kind == "deselected":
            deselected_by_hook.update(str(n) for n in record.get("nodeids") or [])
        elif kind == "collect_skip":
            collect_cases.append((nodeid, "skipped", str(record.get("text") or "")))
        elif kind == "collect_error":
            collect_cases.append((nodeid, "error", "collection error"))
        elif kind == "report":
            reports.setdefault(nodeid, {})[str(record.get("when"))] = record
        elif kind == "witness":
            witnesses[nodeid] = record
    patched = [str(p) for p in records[-1].get("patched") or []]
    # Hookimpls that appeared after the witness configured (#2812): a conftest or a
    # trusted plugin may add some; one whose function lives anywhere else (e.g. injected
    # into an existing hook caller by candidate code) is a patched pytest call path.
    for added in records[-1].get("hookimpls_added") or []:
        file_text = str(added.get("file") or "") if isinstance(added, Mapping) else ""
        if not _plugin_is_trusted(
            file_text, root=root, trusted_dirs=trusted_plugin_dirs, in_tree_trusted=in_tree_trusted
        ):
            plugin_name = added.get("plugin") if isinstance(added, Mapping) else None
            patched.append(f"hookimpl_added:{plugin_name}:{file_text or '<no file>'}")
    summary["foreign_plugins"] = sorted(set(foreign))[:_INTEGRITY_FINDINGS_LIMIT]
    summary["pytest_internals_patched"] = patched[:_INTEGRITY_FINDINGS_LIMIT]
    selected = selected if selected is not None else []
    selected_set = set(selected)
    deselected = [n for n in dict.fromkeys(collected) if n not in selected_set]
    cases: list[tuple[str, str, str]] = list(collect_cases)
    forged: list[str] = []
    not_run: list[str] = []
    ast_cache: dict[str, Any] = {}
    unresolved: list[str] = []
    for nodeid in dict.fromkeys(selected):
        phases = reports.get(nodeid, {})
        outcome = {when: str(rep.get("outcome")) for when, rep in phases.items()}
        if outcome.get("call") == "failed":
            cases.append((nodeid, "failure", "failed"))
        elif "failed" in outcome.values():
            cases.append((nodeid, "error", "setup or teardown failed"))
        elif "skipped" in outcome.values() or any(r.get("wasxfail") for r in phases.values()):
            text = next(
                (
                    str(r.get("text") or "")
                    for r in phases.values()
                    if r.get("outcome") == "skipped"
                ),
                "",
            )
            cases.append((nodeid, "skipped", text))
        elif all(outcome.get(when) == "passed" for when in ("setup", "call", "teardown")):
            expected = _expected_test_code(root, nodeid, ast_cache)
            if expected is None:
                # Fail closed, but say why: the parent cannot name the test's own code.
                unresolved.append(nodeid)
                cases.append((nodeid, "failure", VERIFIER_TEST_IDENTITY_UNRESOLVED))
            elif _witness_passed(witnesses.get(nodeid), expected):
                cases.append((nodeid, "passed", ""))
            else:
                forged.append(nodeid)
                cases.append((
                    nodeid,
                    "failure",
                    f"{VERIFIER_OUTCOME_FORGED}: {witnesses.get(nodeid)}",
                ))
        else:
            not_run.append(nodeid)
            cases.append((nodeid, "error", "no complete report"))
    summary["forged_node_ids"] = forged[:_INTEGRITY_FINDINGS_LIMIT]
    summary["not_run_node_ids"] = not_run[:_INTEGRITY_FINDINGS_LIMIT]
    summary["deselected_node_ids"] = deselected[:_INTEGRITY_FINDINGS_LIMIT]
    summary["identity_unresolved_node_ids"] = unresolved[:_INTEGRITY_FINDINGS_LIMIT]
    declared_file_deselected: list[str] = []
    if conftest_changed:
        whole_run = not declared_paths and not declared_node_ids
        prefixes = _declared_path_prefixes(root, declared_paths)
        declared_file_deselected = [
            n for n in deselected if whole_run or _in_declared_path(n, prefixes)
        ]
    summary["declared_file_deselected_node_ids"] = declared_file_deselected[
        :_INTEGRITY_FINDINGS_LIMIT
    ]
    # Every declared node must appear among the observed cases (#2808 review round 3):
    # a hook that drops it from ``session.items`` without ``pytest_deselected`` is not
    # silent any more.
    observed = [nodeid for nodeid, _kind, _text in cases]
    missing_declared = [
        d for d in declared_node_ids if not any(_declared_match(n, [d]) for n in observed)
    ]
    summary["declared_node_ids_missing"] = missing_declared[:_INTEGRITY_FINDINGS_LIMIT]
    error = ""
    if foreign:
        error = VERIFIER_FOREIGN_PLUGIN
    elif patched:
        error = VERIFIER_PYTEST_INTERNALS_PATCHED
    elif forged:
        error = VERIFIER_OUTCOME_FORGED
    elif unresolved:
        error = VERIFIER_TEST_IDENTITY_UNRESOLVED
    elif declared_file_deselected:
        # Even a card ``-k``/``-m``/``--deselect`` does not excuse it: a changed conftest
        # can report its own drop through ``pytest_deselected`` (#2811).
        error = VERIFIER_DECLARED_FILE_DESELECTED
    elif any(_declared_match(n, declared_node_ids) for n in deselected) and not (
        deselect_allowed and set(deselected) <= deselected_by_hook
    ):
        # A declared node dropped from the selection without a card option is refused;
        # other deselections (e.g. an unchanged in-tree plugin's
        # ``pytest_collection_modifyitems``) are only recorded (#2808 review).
        error = VERIFIER_TESTS_DESELECTED
    elif missing_declared:
        # Never collected, or dropped some other way: not observed, not passed.
        error = VERIFIER_DECLARED_TESTS_NOT_PASSED
    return error, cases, summary


def _located_interpreter(interpreter: str, path_env: str) -> str:
    located = interpreter if "/" in interpreter else shutil.which(interpreter, path=path_env)
    return str(located or "")


def _interpreter_dirs(located: str, scratch: Path) -> list[Path]:
    """Directories the verifier interpreter needs to read and whose plugins are trusted:
    its prefixes, bin dir and the import roots of pytest and the plugins it loads.

    The probe runs the trusted interpreter with ``-I`` and an empty environment from a
    scratch cwd: no candidate code is on its path.
    """
    proc = subprocess.run(
        [located, "-I", "-c", _INTERPRETER_PROBE],
        cwd=scratch,
        env={"PATH": os.defpath},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    if proc.returncode != 0 or len(lines) < 3:
        raise ClosureError(VERIFIER_SANDBOX_SETUP_FAILED)
    dirs = [Path(lines[0]), Path(lines[1]), Path(lines[2]).parent, Path(located).parent]
    dirs.append(Path(located).resolve().parent)
    dirs.extend(Path(line) for line in lines[3:])
    return list(dict.fromkeys(p.resolve() for p in dirs))


def _write_deny_rules(paths: Sequence[Path], literals: Sequence[Path]) -> list[str]:
    from nexus.engine.sandboxed_lane import sbpl_path

    rules = [f'(deny file-write* (subpath "{sbpl_path(p)}"))' for p in paths]
    rules.extend(f'(deny file-write* (literal "{sbpl_path(p)}"))' for p in literals)
    return rules


def _refuse_trusted_roots_in_writable(
    interpreter_dirs: Sequence[Path], writable: Sequence[Path]
) -> None:
    """No trusted interpreter or plugin root may lie inside a dir the verifier child can
    write (the work tree for a candidate run, the per-run child dir): candidate code
    could rewrite site-packages or pytest there.  Applied with and without an OS
    sandbox (#2811)."""
    for directory in interpreter_dirs:
        if any(directory.is_relative_to(w) for w in writable):
            raise ClosureError(VERIFIER_SANDBOX_SETUP_FAILED)


def _verifier_sandbox_profile(
    *,
    root: Path,
    root_writable: bool,
    child_dir: Path,
    trusted_dir: Path,
    evidence_dir: Path,
    interpreter_dirs: Sequence[Path],
) -> str:
    """The ``sandboxed_lane`` profile for one verifier run, with write denies appended last.

    Writes: the work tree (candidate run only) and the per-run child dir.  The evidence
    dir, the trusted dir (witness plugin + ini) and the tree's ``.git`` are denied by the
    last rules, as are renames of the run dir, the child dir and the tree itself (Seatbelt
    checks a rename against its source path, #2791).
    """
    from nexus.engine.sandboxed_lane import (
        build_sandbox_profile,
        checked_read_roots,
        tool_read_roots,
    )

    writable = [str(child_dir)] + ([str(root)] if root_writable else [])
    _refuse_trusted_roots_in_writable(interpreter_dirs, [Path(w) for w in writable])
    read_roots = checked_read_roots([
        str(root),
        str(child_dir),
        str(trusted_dir),
        *(str(d) for d in interpreter_dirs),
        *tool_read_roots(),
    ])
    profile = build_sandbox_profile(
        writable=writable, read_roots=read_roots, allow_signal_same_sandbox=True
    )
    denied = [evidence_dir, trusted_dir]
    if (root / ".git").exists():
        denied.append(root / ".git")
    literals = [child_dir, root, *child_dir.parents]
    return "\n".join([profile, *_write_deny_rules(denied, literals)])


def _spawn_verifier(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: float,
    profile: str | None,
    pass_fds: list[int],
    witness_fd: int,
) -> dict[str, Any]:
    """Run one verifier (wrapped in sandbox-exec when ``profile``), reading stdout,
    stderr and the witness pipe until EOF or the deadline.  The child's process group
    is always killed afterwards so nothing it started outlives the run."""
    import selectors

    from nexus.engine.sandboxed_lane import SANDBOX_EXEC

    command = [SANDBOX_EXEC, "-p", profile, *argv] if profile else list(argv)
    proc = subprocess.Popen(  # noqa: S603 - argv list, no shell
        command,
        cwd=cwd,
        env=dict(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        pass_fds=tuple(pass_fds),
        start_new_session=True,
    )
    # The child holds its own copies now; closing the parent's write end lets the
    # witness pipe reach EOF when the child exits.  The list is emptied so the caller
    # does not close the (possibly reused) numbers again.
    for fd in pass_fds:
        os.close(fd)
    pass_fds.clear()
    out_fd = proc.stdout.fileno()  # type: ignore[union-attr]
    err_fd = proc.stderr.fileno()  # type: ignore[union-attr]
    caps = {
        out_fd: VERIFIER_OUTPUT_MAX_BYTES,
        err_fd: VERIFIER_OUTPUT_MAX_BYTES,
        witness_fd: VERIFIER_WITNESS_MAX_BYTES + 1,
    }
    buffers = {fd: bytearray() for fd in caps}
    overflow: set[int] = set()
    selector = selectors.DefaultSelector()
    for fd in caps:
        os.set_blocking(fd, False)
        selector.register(fd, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    drain_until: float | None = None
    timed_out = False
    try:
        while selector.get_map():
            now = time.monotonic()
            if now >= deadline:
                timed_out = proc.poll() is None
                break
            if proc.poll() is not None:
                # Exited: keep reading what is buffered, but a grandchild holding a
                # pipe open must not keep the parent waiting.
                if drain_until is None:
                    drain_until = now + VERIFIER_DRAIN_GRACE_SECONDS
                elif now >= drain_until:
                    break
            wait = min(0.5, deadline - now)
            if drain_until is not None:
                wait = max(0.0, min(wait, drain_until - now))
            for key, _mask in selector.select(timeout=wait):
                try:
                    chunk = os.read(key.fd, 65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fd)
                    continue
                room = caps[key.fd] - len(buffers[key.fd])
                if room < len(chunk):
                    overflow.add(key.fd)
                buffers[key.fd].extend(chunk[: max(0, room)])
        if not timed_out and proc.poll() is None:
            try:
                proc.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
    finally:
        selector.close()
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        returncode = proc.wait()
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                stream.close()
    return {
        "returncode": None if timed_out else int(returncode),
        "timed_out": timed_out,
        "stdout": bytes(buffers[out_fd]).decode("utf-8", "replace"),
        "stderr": bytes(buffers[err_fd]).decode("utf-8", "replace"),
        "witness": bytes(buffers[witness_fd]),
        "witness_overflow": witness_fd in overflow,
    }


def _write_evidence_file(directory: Path, identity: tuple[int, int], data: bytes) -> bool:
    """Write ``junit.xml`` into the parent-created evidence dir without following any
    symlink; False when the dir was replaced or the file already exists (tampering)."""
    try:
        info = os.lstat(directory)
        if (info.st_dev, info.st_ino) != identity or not os.path.isdir(directory):
            return False
        dir_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW)
    except OSError:
        return False
    try:
        if (os.fstat(dir_fd).st_dev, os.fstat(dir_fd).st_ino) != identity:
            return False
        fd = os.open(
            "junit.xml",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=dir_fd,
        )
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        return True
    except OSError:
        return False
    finally:
        os.close(dir_fd)


def _safe_base_member(member: tarfile.TarInfo, dest: str) -> tarfile.TarInfo | None:
    """tarfile's ``data`` filter, but an unsafe member (e.g. a symlink to an absolute
    path) is left out instead of aborting the whole base checkout."""
    try:
        return tarfile.data_filter(member, dest)
    except tarfile.FilterError:
        return None


def _base_checkout(root: Path, base_sha: str, dest: Path) -> None:
    """Extract ``base_sha`` (no ``refs/replace``) into ``dest``: a plain, read-only base
    tree (no ``.git``) for the base comparison run."""

    dest.mkdir(mode=0o700)
    proc = subprocess.Popen(  # noqa: S603 - fixed git argv
        ["git", "archive", "--format=tar", base_sha],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=_git_no_replace_env(),
    )
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as archive:
            # Every member goes through tarfile.data_filter (unsafe ones are dropped).
            archive.extractall(dest, filter=_safe_base_member)  # nosec B202
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
        returncode = proc.wait(timeout=INTEGRITY_CHECK_TIMEOUT_SECONDS)
    if returncode != 0:
        raise ClosureError(VERIFIER_BASE_RUN_FAILED)


@dataclass
class _PytestRun:
    executed_argv: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    error: str
    junit: dict[str, Any]
    witness: dict[str, Any]
    sandbox: dict[str, Any]
    skipped_names: list[str]
    env_keys: list[str]
    junit_bytes: bytes = b""
    # The node ids pytest selected (the witness ``selected`` record), for the #2811
    # base collection comparison.
    selected_node_ids: tuple[str, ...] = ()


def _run_pytest_verifier(
    invocation: _PytestInvocation,
    *,
    root: Path,
    run_dir: Path,
    base_config: Mapping[str, Any],
    base_sha: str,
    candidate_commit: str,
    timeout: float,
    changed_paths: Sequence[str],
    base_skipped: Collection[str] | None,
    root_writable: bool = True,
) -> _PytestRun:
    """One pytest verifier run with the witness (and the sandbox where available)."""
    from nexus.engine.sandboxed_lane import SandboxError, os_sandbox_available

    child_dir = run_dir / "child"
    trusted_dir = run_dir / "trusted"
    evidence_dir = run_dir / "evidence"
    home, tmpdir = child_dir / "home", child_dir / "tmp"
    run_dir.mkdir(mode=0o700, exist_ok=True)
    for directory in (child_dir, trusted_dir, evidence_dir, home, tmpdir):
        directory.mkdir(mode=0o700)
    evidence_info = os.lstat(evidence_dir)
    env = _verifier_env(
        home=home, tmpdir=tmpdir, base_sha=base_sha, candidate_commit=candidate_commit
    )
    ini_text, extra_args = _verifier_pytest_ini(root, base_config)
    ini_path = trusted_dir / "pytest.ini"
    ini_path.write_text(ini_text, encoding="utf-8")
    shutil.copyfile(VERIFIER_WITNESS_SOURCE, trusted_dir / f"{VERIFIER_WITNESS_PLUGIN}.py")
    executed_argv = [
        invocation.interpreter,
        "-P",
        *invocation.interpreter_args,
        "-m",
        "pytest",
        # Added after the card's options so they override any earlier value.
        *_with_pytest_options(
            invocation.pytest_args,
            *extra_args,
            "-c",
            str(ini_path),
            "--rootdir",
            str(root),
            "--confcutdir",
            str(root),
            "-p",
            "no:cacheprovider",
            "-p",
            VERIFIER_WITNESS_PLUGIN,
        ),
    ]
    sandbox: dict[str, Any] = {"sandboxed": False, "barrier": None, "network": "not_confined"}
    witness = _empty_witness_summary()
    junit = _empty_junit_summary(invocation.declared_node_ids)

    def result(
        error: str, returncode: int | None = None, out: str = "", err: str = ""
    ) -> _PytestRun:
        return _PytestRun(
            executed_argv, returncode, out, err, error, junit, witness, sandbox, [], sorted(env)
        )

    located = _located_interpreter(invocation.interpreter, env["PATH"])
    if not located or Path(located).resolve().is_relative_to(root):
        return result(VERIFIER_PYTEST_INTERPRETER_UNRESOLVED)
    try:
        interpreter_dirs = _interpreter_dirs(located, child_dir)
        _refuse_trusted_roots_in_writable(
            interpreter_dirs, [child_dir.resolve()] + ([root] if root_writable else [])
        )
    except (ClosureError, OSError, subprocess.SubprocessError):
        return result(VERIFIER_SANDBOX_SETUP_FAILED)
    profile: str | None = None
    if os_sandbox_available():
        try:
            profile = _verifier_sandbox_profile(
                root=root,
                root_writable=root_writable,
                child_dir=child_dir,
                trusted_dir=trusted_dir,
                evidence_dir=evidence_dir,
                interpreter_dirs=interpreter_dirs,
            )
        except (ClosureError, SandboxError):
            return result(VERIFIER_SANDBOX_SETUP_FAILED)
        sandbox = {
            "sandboxed": True,
            "barrier": "macos_sandbox_exec",
            "profile": "nexus.engine.sandboxed_lane.build_sandbox_profile",
            "profile_sha256": _sha256(profile),
            "network": "denied",
            "writes_confined_to": (["<work-tree>"] if root_writable else [])
            + ["<verifier-sandbox>/child"],
            "write_denied_last": ["<verifier-sandbox>/evidence", "<verifier-sandbox>/trusted"]
            + (["<work-tree>/.git"] if (root / ".git").exists() else []),
        }
    else:
        sandbox["reason"] = "no_os_barrier"
    key = os.urandom(VERIFIER_WITNESS_KEY_BYTES)
    witness_r, witness_w = os.pipe()
    key_r, key_w = os.pipe()
    child_fds = [witness_w, key_r]
    try:
        os.write(key_w, key)
        os.close(key_w)
        env[VERIFIER_WITNESS_FD_ENV] = str(witness_w)
        env[VERIFIER_WITNESS_KEY_FD_ENV] = str(key_r)
        env["PYTHONPATH"] = str(trusted_dir)
        try:
            spawned = _spawn_verifier(
                executed_argv,
                cwd=root,
                env=env,
                timeout=timeout,
                profile=profile,
                pass_fds=child_fds,
                witness_fd=witness_r,
            )
        except OSError:
            return result(VERIFIER_SANDBOX_SETUP_FAILED)
    finally:
        for fd in (witness_r, *child_fds):
            try:
                os.close(fd)
            except OSError:
                pass
    out, err, returncode = spawned["stdout"], spawned["stderr"], spawned["returncode"]
    if spawned["timed_out"]:
        return result("VERIFIER_TIMEOUT", None, out, err)
    tamper, records = (
        (VERIFIER_WITNESS_TAMPERED, [])
        if spawned["witness_overflow"]
        else _parse_witness(spawned["witness"], key)
    )
    if tamper:
        witness["error"] = tamper
        witness["records"] = len(records)
        return result(tamper, returncode, out, err)
    pytest_args = set(invocation.pytest_args)
    witness_error, cases, witness = _witness_outcomes(
        records,
        root=root,
        trusted_plugin_dirs=[trusted_dir.resolve(), *interpreter_dirs],
        deselect_allowed=bool(pytest_args & _DESELECT_OPTIONS),
        declared_node_ids=invocation.declared_node_ids,
        declared_paths=invocation.declared_paths,
        conftest_changed=_conftest_changed(changed_paths),
        in_tree_trusted=(
            _base_unchanged_predicate(root, base_sha, changed_paths)
            if root_writable
            else (lambda _rel: True)  # the base run's tree IS the base commit
        ),
    )
    witness["error"] = witness_error
    if cases is None:
        return result(witness_error, returncode, out, err)
    junit_bytes = _render_junit(cases)
    if not _write_evidence_file(
        evidence_dir, (evidence_info.st_dev, evidence_info.st_ino), junit_bytes
    ):
        return result(VERIFIER_EVIDENCE_TAMPERED, returncode, out, err)
    junit_error, junit = _junit_evidence_bytes(
        junit_bytes,
        invocation.declared_node_ids,
        root=root,
        touched_paths=changed_paths,
        base_skipped=base_skipped,
    )
    junit["evidence_source"] = "parent_witness_channel"
    skipped_names = [_junit_full_name(nodeid) for nodeid, kind, _ in cases if kind == "skipped"]
    run = result(witness_error or junit_error, returncode, out, err)
    run.skipped_names = skipped_names
    run.junit_bytes = junit_bytes
    run.selected_node_ids = next(
        (
            tuple(str(n) for n in r.get("nodeids") or [])
            for r in reversed(records)
            if r.get("t") == "selected"
        ),
        (),
    )
    return run


def _base_skipped_nodes(
    invocation: _PytestInvocation,
    *,
    root: Path,
    base_sha: str,
    base_config: Mapping[str, Any],
    base_tree: Path,
    candidate_commit: str,
    timeout: float,
) -> tuple[set[str] | None, dict[str, Any]]:
    """Nodes skipped when the same verifier runs at ``base_sha`` (read-only checkout).

    ``None`` (no skip tolerated) when the base run produced no complete witness.
    """
    run_dir = Path(tempfile.mkdtemp(prefix="nexus-verifier-base-")).resolve()
    try:
        run = _run_pytest_verifier(
            invocation,
            root=base_tree,
            run_dir=run_dir,
            base_config=base_config,
            base_sha=base_sha,
            candidate_commit=candidate_commit,
            timeout=timeout,
            changed_paths=(),
            base_skipped=(),
            root_writable=False,
        )
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
    info = {
        "ran": True,
        "returncode": run.returncode,
        "witness_complete": bool(run.witness.get("complete")),
        "sandboxed": bool(run.sandbox.get("sandboxed")),
        "skipped": sorted(run.skipped_names)[:_INTEGRITY_FINDINGS_LIMIT],
    }
    if not run.witness.get("complete") or run.witness.get("error") == VERIFIER_WITNESS_TAMPERED:
        info["error"] = VERIFIER_BASE_RUN_FAILED
        return None, info
    return set(run.skipped_names), info


def _base_collect_invocation(
    invocation: _PytestInvocation, base_tree: Path, root: Path
) -> _PytestInvocation | None:
    """The same verifier as a ``--collect-only`` run at the base commit, over the
    card's file and directory targets only.

    Node-id targets are left out: a declared node must be observed and passed anyway
    (``VERIFIER_DECLARED_TESTS_NOT_PASSED``), and one that is new at the candidate would
    make the base run fail.  Targets are made relative to the candidate root (an
    absolute one would otherwise name the candidate tree, #2846 review r2); targets
    outside the root or missing at base are dropped (a file the candidate added has
    nothing to compare).  ``None`` when no file or directory target is left although
    the card named targets."""
    args: list[str] = []
    had_target = kept_target = False
    targets, maybe_values = _pytest_target_indices(invocation.pytest_args)
    for index, token in enumerate(invocation.pytest_args):
        if index in targets:
            had_target = True
            if "::" in token:
                continue
            (rel,) = _declared_path_prefixes(root, [token]) or ("",)
            missing = not rel or rel == ".." or rel.startswith("../") or os.path.isabs(rel)
            if missing or not (base_tree / rel).exists():
                if index in maybe_values:  # most likely the option's value: keep it with the option
                    args.append(token)
                continue
            kept_target = True
            token = rel
        args.append(token)
    if had_target and not kept_target:
        return None
    return _PytestInvocation(
        interpreter=invocation.interpreter,
        interpreter_args=invocation.interpreter_args,
        pytest_args=_with_pytest_options(args, "--collect-only"),
        declared_node_ids=(),
        declared_paths=(),
    )


def _base_declared_nodes_missing(
    invocation: _PytestInvocation,
    candidate_selected: Collection[str],
    *,
    root: Path,
    base_sha: str,
    base_config: Mapping[str, Any],
    base_tree: Path,
    candidate_commit: str,
    timeout: float,
    changed_paths: Sequence[str],
) -> tuple[list[str] | None, dict[str, Any]]:
    """#2811 review: with a changed ``conftest.py``, every node the same verifier
    selects at the base commit in a declared target (no positional target: the whole
    run) whose test file the candidate did not change must also be selected in the
    candidate run; otherwise it was dropped at collection time (``pytest_ignore_collect``,
    ``pytest_collect_file``, ``pytest_pycollect_makeitem`` ...).  Nodes in test files the
    candidate changed or added are judged by the other rules.  ``None`` when the base
    collection produced no complete witness (fail closed)."""
    base_invocation = _base_collect_invocation(invocation, base_tree, root)
    if base_invocation is None:
        return [], {"ran": False, "reason": "no_declared_target_at_base"}
    run_dir = Path(tempfile.mkdtemp(prefix="nexus-verifier-base-collect-")).resolve()
    try:
        run = _run_pytest_verifier(
            base_invocation,
            root=base_tree,
            run_dir=run_dir,
            base_config=base_config,
            base_sha=base_sha,
            candidate_commit=candidate_commit,
            timeout=timeout,
            changed_paths=(),
            base_skipped=(),
            root_writable=False,
        )
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
    info: dict[str, Any] = {
        "ran": True,
        "returncode": run.returncode,
        "witness_complete": bool(run.witness.get("complete")),
        "sandboxed": bool(run.sandbox.get("sandboxed")),
        "selected": len(run.selected_node_ids),
    }
    # Fail closed on anything but a clean collection (#2846 review r2): an incomplete
    # or flagged witness, collection errors (rc 2), usage errors (rc 4) ...  rc 5 (no
    # tests collected) is a clean, empty base collection.
    if (
        not run.witness.get("complete")
        or run.witness.get("error")
        or run.error in {VERIFIER_WITNESS_TAMPERED, VERIFIER_JUNIT_MISSING}
        or run.returncode not in (0, 5)
    ):
        info["error"] = VERIFIER_BASE_RUN_FAILED
        return None, info
    changed = {PurePosixPath(p).as_posix() for p in changed_paths}
    prefixes = _declared_path_prefixes(root, invocation.declared_paths)
    whole_run = not invocation.declared_paths and not invocation.declared_node_ids
    observed = set(candidate_selected)
    # A test file the candidate changed is exempt: changing it needs it in the card's
    # authorized scope (``nexus.integrity.scope`` fails the verification otherwise),
    # and with that authorization the candidate may delete or rewrite its tests
    # outright; such a node is judged by the other rules and by diff review.
    missing = [
        n
        for n in run.selected_node_ids
        if n.split("::", 1)[0] not in changed
        and (whole_run or _in_declared_path(n, prefixes))
        and n not in observed
    ]
    info["missing"] = missing[:_INTEGRITY_FINDINGS_LIMIT]
    return missing, info


def _ensure_base_tree(
    root: Path, base_sha: str, base_tree_parent: Path | None, base_tree_error: str
) -> tuple[Path | None, str]:
    """One read-only base checkout per call, extracted on first use (#2795)."""
    if base_tree_parent is None and not base_tree_error:
        base_tree_parent = Path(tempfile.mkdtemp(prefix="nexus-verifier-base-tree-")).resolve()
        try:
            _base_checkout(root, base_sha, base_tree_parent / "tree")
        except (
            ClosureError,
            OSError,
            ValueError,
            tarfile.TarError,
            subprocess.SubprocessError,
        ):
            base_tree_error = VERIFIER_BASE_RUN_FAILED
    return base_tree_parent, base_tree_error


def _run_one_verifier(
    spec: VerifierSpec,
    *,
    root: Path,
    base_sha: str,
    candidate_commit: str,
    changed_paths: Sequence[str] | None,
    shadow_error: str,
    refused_shadow: Sequence[str],
    authorized_shadow: Sequence[str],
    base_state: tuple[tuple[dict[str, Any], str] | None, Path | None, str],
) -> dict[str, Any]:
    """Run one verifier spec and return its result row (plus ``_base_state``)."""
    base_pytest_config, base_tree_parent, base_tree_error = base_state
    started = time.monotonic()
    sandbox = Path(tempfile.mkdtemp(prefix="nexus-verifier-")).resolve()
    executed_argv = list(spec.argv)
    junit_summary: dict[str, Any] | None = None
    witness_summary: dict[str, Any] | None = None
    sandbox_info: dict[str, Any] = {"sandboxed": False, "barrier": None}
    base_run: dict[str, Any] | None = None
    base_collect: dict[str, Any] | None = None
    returncode: int | None = None
    stdout = stderr = error = ""
    try:
        if sandbox.is_relative_to(root):
            raise ClosureError("VERIFIER_SANDBOX_INSIDE_WORKSPACE")
        home = sandbox / "home"
        tmpdir = sandbox / "tmp"
        for directory in (home, tmpdir):
            directory.mkdir(mode=0o700)
        env = _verifier_env(
            home=home, tmpdir=tmpdir, base_sha=base_sha, candidate_commit=candidate_commit
        )
        env_keys = sorted(env)
        invocation = _pytest_invocation(spec.argv, env["PATH"])
        evidence = (
            VERIFIER_EVIDENCE_EXIT_CODE_ONLY
            if invocation is None
            else VERIFIER_EVIDENCE_PYTEST_JUNIT
        )
        if shadow_error:
            error = shadow_error
        elif isinstance(invocation, str):
            error = invocation
        elif isinstance(invocation, _PytestInvocation):
            if base_pytest_config is None:
                base_pytest_config = _base_pytest_config(root, base_sha)
            run = _run_pytest_verifier(
                invocation,
                root=root,
                run_dir=sandbox / "run",
                base_config=base_pytest_config[0],
                base_sha=base_sha,
                candidate_commit=candidate_commit,
                timeout=spec.timeout,
                changed_paths=changed_paths or (),
                base_skipped=None,
            )
            executed_argv = run.executed_argv
            returncode, stdout, stderr, error = run.returncode, run.stdout, run.stderr, run.error
            junit_summary, witness_summary, sandbox_info = run.junit, run.witness, run.sandbox
            env_keys = run.env_keys
            if error == VERIFIER_JUNIT_SKIPPED and returncode == 0 and run.junit_bytes:
                # A skip passes only if the same node is also skipped at the base commit.
                base_tree_parent, base_tree_error = _ensure_base_tree(
                    root, base_sha, base_tree_parent, base_tree_error
                )
                if base_tree_error or base_tree_parent is None:
                    base_run = {"ran": False, "error": base_tree_error or VERIFIER_BASE_RUN_FAILED}
                else:
                    base_skipped, base_run = _base_skipped_nodes(
                        invocation,
                        root=root,
                        base_sha=base_sha,
                        base_config=base_pytest_config[0],
                        base_tree=base_tree_parent / "tree",
                        candidate_commit=candidate_commit,
                        timeout=spec.timeout,
                    )
                    if base_skipped is not None:
                        error, junit_summary = _junit_evidence_bytes(
                            run.junit_bytes,
                            invocation.declared_node_ids,
                            root=root,
                            touched_paths=changed_paths or (),
                            base_skipped=base_skipped,
                        )
                        junit_summary["evidence_source"] = "parent_witness_channel"
            if not error and returncode == 0 and _conftest_changed(changed_paths or ()):
                base_tree_parent, base_tree_error = _ensure_base_tree(
                    root, base_sha, base_tree_parent, base_tree_error
                )
                if base_tree_error or base_tree_parent is None:
                    base_collect = {"ran": False, "error": base_tree_error}
                    error = VERIFIER_BASE_RUN_FAILED
                else:
                    missing, base_collect = _base_declared_nodes_missing(
                        invocation,
                        run.selected_node_ids,
                        root=root,
                        base_sha=base_sha,
                        base_config=base_pytest_config[0],
                        base_tree=base_tree_parent / "tree",
                        candidate_commit=candidate_commit,
                        timeout=spec.timeout,
                        changed_paths=changed_paths or (),
                    )
                    if missing is None:
                        error = VERIFIER_BASE_RUN_FAILED
                    elif missing:
                        error = VERIFIER_DECLARED_NODE_MISSING
        else:
            sandbox_info["reason"] = "not_a_pytest_verifier"
            try:
                proc = subprocess.run(
                    executed_argv,
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=spec.timeout,
                    check=False,
                    env=env,
                    shell=False,
                )
                returncode = int(proc.returncode)
                stdout = proc.stdout or ""
                stderr = proc.stderr or ""
            except subprocess.TimeoutExpired as exc:
                stdout = str(exc.stdout or "")
                stderr = str(exc.stderr or "")
                error = "VERIFIER_TIMEOUT"
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
    wall_ms = max(0, int((time.monotonic() - started) * 1000))
    sandbox_text = str(sandbox)
    return {
        "verifier_id": spec.verifier_id,
        "argv": list(spec.argv),
        "argv_sha256": _sha256(_canonical_json(list(spec.argv))),
        # Per-run temp paths are replaced so the row stays comparable across runs.
        "executed_argv": [
            part.replace(sandbox_text, "<verifier-sandbox>") for part in executed_argv
        ],
        "cwd_sha256": _sha256(str(root)),
        "owner_unit": spec.owner_unit,
        "returncode": returncode,
        "stdout_sha256": _sha256(stdout),
        "stderr_sha256": _sha256(stderr),
        "wall_time_ms": wall_ms,
        "error": error,
        "evidence": evidence,
        "junit": junit_summary,
        "witness": witness_summary,
        "sandbox": sandbox_info,
        "base_run": base_run,
        "base_collect": base_collect,
        "env_keys": env_keys,
        "root_shadowing_refused_paths": list(refused_shadow),
        "root_shadowing_authorized_paths": list(authorized_shadow),
        "passed": returncode == 0 and not error,
        "_base_state": (base_pytest_config, base_tree_parent, base_tree_error),
    }


def _run_verifier_specs(
    *,
    task_id: str,
    unit_id: str,
    workspace_path: str,
    candidate_commit: str,
    specs: Sequence[Mapping[str, Any] | VerifierSpec],
    schema: str,
    scope: str,
    base_sha: str,
    authorized_paths: Sequence[str],
    deletable_paths: Sequence[str],
    shadow_authorized_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    root = Path(workspace_path).expanduser().resolve()
    if _run_git(root, "rev-parse", "HEAD") != candidate_commit:
        raise ClosureError("VERIFIER_HEAD_MISMATCH")
    if _run_git(root, "status", "--porcelain=v1"):
        raise ClosureError("VERIFIER_WORKSPACE_DIRTY")
    parsed = [VerifierSpec.from_value(spec) for spec in specs]
    if not parsed:
        raise ClosureError("VERIFIER_SPECS_REQUIRED")
    integrity_checks = run_integrity_checks(
        root,
        base_sha=base_sha,
        candidate_commit=candidate_commit,
        authorized_paths=authorized_paths,
        deletable_paths=deletable_paths,
    )
    results: list[dict[str, Any]] = []
    # Shadowing: a root-level pytest.py/sitecustomize.py/... or pytest config file, or a
    # conftest.py at any depth, changed by the candidate is refused unless it is explicitly (exactly)
    # authorized; an authorized one is still flagged on every row.
    explicit = {
        str(path).strip().rstrip("/")
        for path in (
            authorized_paths if shadow_authorized_paths is None else shadow_authorized_paths
        )
    }
    changed_paths = _candidate_changed_paths(root, base_sha, candidate_commit)
    if changed_paths is None:
        shadow_paths, shadow_error = None, VERIFIER_ROOT_SHADOW_CHECK_ERROR
    else:
        shadow_paths, shadow_error = _shadowing_paths(changed_paths), ""
    refused_shadow = sorted(p for p in shadow_paths or [] if p not in explicit)
    authorized_shadow = sorted(p for p in shadow_paths or [] if p in explicit)
    if not shadow_error and refused_shadow:
        shadow_error = VERIFIER_ROOT_SHADOWING_REFUSED
    base_pytest_config: tuple[dict[str, Any], str] | None = None
    # One read-only base checkout per call, extracted only when a skip needs the base
    # comparison (#2795).
    base_tree_parent: Path | None = None
    base_tree_error = ""
    try:
        for spec in parsed:
            results.append(
                _run_one_verifier(
                    spec,
                    root=root,
                    base_sha=base_sha,
                    candidate_commit=candidate_commit,
                    changed_paths=changed_paths,
                    shadow_error=shadow_error,
                    refused_shadow=refused_shadow,
                    authorized_shadow=authorized_shadow,
                    base_state=(base_pytest_config, base_tree_parent, base_tree_error),
                )
            )
            base_pytest_config, base_tree_parent, base_tree_error = results[-1].pop("_base_state")
            if _run_git(root, "rev-parse", "HEAD") != candidate_commit or _run_git(
                root, "status", "--porcelain=v1"
            ):
                raise ClosureError("VERIFIER_MUTATED_WORKSPACE")
    finally:
        if base_tree_parent is not None:
            shutil.rmtree(base_tree_parent, ignore_errors=True)
    integrity_passed = all(row["passed"] for row in integrity_checks)
    status = "PASS" if integrity_passed and all(row["passed"] for row in results) else "FAIL"
    verification = {
        "schema": schema,
        "scope": scope,
        "task_id": task_id,
        "unit_id": unit_id,
        "workspace_path": str(root),
        "candidate_commit": candidate_commit,
        "status": status,
        "failed_verifier_ids": [row["verifier_id"] for row in results if not row["passed"]],
        "results": results,
        # Additive: closure-owned scoped checks against the bound base.
        "integrity_base_sha": base_sha,
        "integrity_status": "PASS" if integrity_passed else "FAIL",
        "failed_integrity_check_ids": [
            row["check_id"] for row in integrity_checks if not row["passed"]
        ],
        "integrity_checks": integrity_checks,
    }
    verification["verification_id"] = _sha256(_canonical_json(verification))
    return verification


def verify_unit_candidate(
    receipt: Mapping[str, Any],
    verifier_specs: Sequence[Mapping[str, Any] | VerifierSpec],
) -> dict[str, Any]:
    bound = validate_worker_receipt(receipt)
    result = _run_verifier_specs(
        task_id=bound["task_id"],
        unit_id=bound["unit_id"],
        workspace_path=bound["workspace_path"],
        candidate_commit=bound["candidate_commit"],
        specs=verifier_specs,
        schema=UNIT_VERIFICATION_SCHEMA,
        scope="UNIT",
        base_sha=bound["base_sha"],
        authorized_paths=bound["mutation_paths"],
        deletable_paths=bound["mutation_paths"] if bound["allow_deletions"] else (),
    )
    result.update({
        "worker_receipt_id": bound["receipt_id"],
        "session_id": bound["session_id"],
        "workspace_id": bound["workspace_id"],
        "candidate_tree": bound["candidate_tree"],
        "candidate_diff_sha256": bound["candidate_diff_sha256"],
        "base_sha": bound["base_sha"],
    })
    material = dict(result)
    material.pop("verification_id", None)
    result["verification_id"] = _sha256(_canonical_json(material))
    return result


def _integrity_findings(verification: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Repair findings for failed built-in integrity checks (same shape as verifier rows)."""
    return [
        {
            "verifier_id": row["check_id"],
            "returncode": row["returncode"],
            "stdout_sha256": row["stdout_sha256"],
            "stderr_sha256": row["stderr_sha256"],
            "error": row["code"],
            "paths": list(row.get("findings") or []),
        }
        for row in verification.get("integrity_checks", [])
        if not row.get("passed")
    ]


def build_unit_repair_delta(
    receipt: Mapping[str, Any],
    verification: Mapping[str, Any],
    *,
    repair_index: int,
) -> dict[str, Any]:
    bound = validate_worker_receipt(receipt)
    if (
        verification.get("schema") != UNIT_VERIFICATION_SCHEMA
        or verification.get("status") != "FAIL"
    ):
        raise ClosureError("FAILED_UNIT_VERIFICATION_REQUIRED")
    if (
        verification.get("worker_receipt_id") != bound["receipt_id"]
        or verification.get("task_id") != bound["task_id"]
        or verification.get("unit_id") != bound["unit_id"]
    ):
        raise ClosureError("UNIT_VERIFICATION_BINDING_MISMATCH")
    if repair_index <= 0:
        raise ClosureError("INVALID_REPAIR_INDEX")
    findings = [
        {
            "verifier_id": row["verifier_id"],
            "returncode": row["returncode"],
            "stdout_sha256": row["stdout_sha256"],
            "stderr_sha256": row["stderr_sha256"],
            "error": row["error"],
        }
        for row in verification.get("results", [])
        if not row.get("passed")
    ]
    findings.extend(_integrity_findings(verification))
    delta = {
        "schema": UNIT_REPAIR_DELTA_SCHEMA,
        "task_id": bound["task_id"],
        "unit_id": bound["unit_id"],
        "repair_index": repair_index,
        "parent_receipt_id": bound["receipt_id"],
        "parent_candidate_commit": bound["candidate_commit"],
        "verification_id": verification["verification_id"],
        "session_id": bound["session_id"],
        "workspace_id": bound["workspace_id"],
        "workspace_path": bound["workspace_path"],
        "provider": bound["provider"],
        "model": bound["model"],
        "allowed_mutation_paths": list(bound["mutation_paths"]),
        "findings": findings,
        "stop_conditions": [
            "scope_expands",
            "session_changes",
            "workspace_changes",
            "model_changes",
            "provider_outcome_becomes_ambiguous",
        ],
        "claim_ceiling": "BOUNDED_REPAIR_ONLY",
    }
    if bound.get("selected_worker"):
        delta["selected_worker"] = dict(bound["selected_worker"])
    delta["delta_id"] = _sha256(_canonical_json(delta))
    return delta


def build_composition_repair_delta(
    receipt: Mapping[str, Any],
    whole_verification: Mapping[str, Any],
    *,
    repair_index: int,
) -> dict[str, Any]:
    bound = validate_worker_receipt(receipt)
    if (
        whole_verification.get("schema") != WHOLE_VERIFICATION_SCHEMA
        or whole_verification.get("status") != "FAIL"
    ):
        raise ClosureError("FAILED_WHOLE_VERIFICATION_REQUIRED")
    failed = [row for row in whole_verification.get("results", []) if not row.get("passed")]
    owners = {str(row.get("owner_unit") or "") for row in failed}
    if not failed or owners != {bound["unit_id"]}:
        raise ClosureError("WHOLE_FAILURE_NOT_UNIQUELY_OWNED")
    findings = [
        {
            "verifier_id": row["verifier_id"],
            "returncode": row["returncode"],
            "stdout_sha256": row["stdout_sha256"],
            "stderr_sha256": row["stderr_sha256"],
            "error": row["error"],
        }
        for row in failed
    ]
    delta = {
        "schema": COMPOSITION_REPAIR_DELTA_SCHEMA,
        "task_id": bound["task_id"],
        "unit_id": bound["unit_id"],
        "repair_index": repair_index,
        "parent_receipt_id": bound["receipt_id"],
        "parent_candidate_commit": bound["candidate_commit"],
        "whole_verification_id": whole_verification["verification_id"],
        "session_id": bound["session_id"],
        "workspace_id": bound["workspace_id"],
        "workspace_path": bound["workspace_path"],
        "provider": bound["provider"],
        "model": bound["model"],
        "allowed_mutation_paths": list(bound["mutation_paths"]),
        "findings": findings,
        "stop_conditions": [
            "scope_expands",
            "failure_requires_more_than_this_unit",
            "session_changes",
            "workspace_changes",
            "model_changes",
        ],
        "claim_ceiling": "BOUNDED_COMPOSITION_REPAIR_ONLY",
    }
    if bound.get("selected_worker"):
        delta["selected_worker"] = dict(bound["selected_worker"])
    delta["delta_id"] = _sha256(_canonical_json(delta))
    return delta


def _validate_repair_result(parent_bound: Mapping[str, Any], repaired: Mapping[str, Any]) -> None:
    repaired_bound = validate_worker_receipt(repaired)
    for field in (
        "task_id",
        "unit_id",
        "session_id",
        "workspace_id",
        "workspace_path",
        "base_sha",
    ):
        if repaired_bound[field] != parent_bound[field]:
            raise ClosureError(f"REPAIR_{field.upper()}_MISMATCH")
    if repaired_bound.get("provider") != parent_bound.get("provider") or repaired_bound.get(
        "model"
    ) != parent_bound.get("model"):
        raise ClosureError("REPAIR_MODEL_BINDING_MISMATCH")
    if parent_bound.get("selected_worker") or repaired_bound.get("selected_worker"):
        if parent_bound.get("selected_worker") != repaired_bound.get("selected_worker"):
            raise ClosureError("REPAIR_WORKER_BINDING_MISMATCH")
    if repaired.get("parent_receipt_id") != parent_bound["receipt_id"]:
        raise ClosureError("REPAIR_PARENT_RECEIPT_MISMATCH")
    # A bound unit stays bound to the same Core binding across every repair; an
    # unbound (or differently bound) repair of a bound parent is never accepted.
    for field in (
        "core_binding_status",
        "core_binding_hash",
        "acceptance_contract_hash",
        "bound_envelope_sha256",
        "core_binding_operation_id",
        "core_binding_attempt_id",
    ):
        if repaired_bound.get(field) != parent_bound.get(field):
            raise ClosureError("REPAIR_CORE_BINDING_MISMATCH")


def compose_task_candidate(
    *,
    repository_root: str | os.PathLike[str],
    allocator: CompositionWorkspaceAllocator,
    receipts: Sequence[Mapping[str, Any]],
    verifications: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], AssemblyLease]:
    if not receipts:
        raise ClosureError("UNIT_RECEIPTS_REQUIRED")
    receipt_by_unit: dict[str, tuple[Mapping[str, Any], dict[str, Any]]] = {}
    for receipt in receipts:
        bound = validate_worker_receipt(receipt)
        if bound["unit_id"] in receipt_by_unit:
            raise ClosureError("DUPLICATE_UNIT_RECEIPT")
        receipt_by_unit[bound["unit_id"]] = (receipt, bound)
    verification_by_unit: dict[str, Mapping[str, Any]] = {}
    for verification in verifications:
        unit_id = _safe_slug(verification.get("unit_id"), "unit_id")
        if (
            verification.get("schema") != UNIT_VERIFICATION_SCHEMA
            or verification.get("status") != "PASS"
        ):
            raise ClosureError("ALL_UNIT_VERIFICATIONS_MUST_PASS")
        if unit_id in verification_by_unit:
            raise ClosureError("DUPLICATE_UNIT_VERIFICATION")
        verification_by_unit[unit_id] = verification
    if set(verification_by_unit) != set(receipt_by_unit):
        raise ClosureError("UNIT_VERIFICATION_SET_MISMATCH")
    task_ids = {bound["task_id"] for _, bound in receipt_by_unit.values()}
    bases = {bound["base_sha"] for _, bound in receipt_by_unit.values()}
    if len(task_ids) != 1:
        raise ClosureError("MIXED_TASK_COMPOSITION_FORBIDDEN")
    if len(bases) != 1:
        raise ClosureError("COMMON_BASE_REQUIRED")
    task_id = next(iter(task_ids))
    base_sha = next(iter(bases))
    for unit_id, (receipt, bound) in receipt_by_unit.items():
        verification = verification_by_unit[unit_id]
        if (
            verification.get("worker_receipt_id") != bound["receipt_id"]
            or verification.get("candidate_commit") != bound["candidate_commit"]
        ):
            raise ClosureError("UNIT_VERIFICATION_RECEIPT_DRIFT")
    lease = allocator.allocate(task_id, base_sha)
    assembly = Path(lease.path)
    repo = Path(repository_root).expanduser().resolve()
    order = sorted(receipt_by_unit)
    cumulative_paths_by_unit: dict[str, list[str]] = {}
    seen_changed: set[str] = set()
    for unit_id in order:
        _, bound = receipt_by_unit[unit_id]
        cumulative = _changed_paths(repo, base_sha, bound["candidate_commit"])
        if not cumulative:
            raise ClosureError("EMPTY_UNIT_CANDIDATE")
        overlap = seen_changed.intersection(cumulative)
        if overlap:
            raise ClosureError(f"COMPOSITION_PATH_OVERLAP:{','.join(sorted(overlap))}")
        seen_changed.update(cumulative)
        cumulative_paths_by_unit[unit_id] = cumulative
        patch = _raw_diff_patch(repo, base_sha, bound["candidate_commit"])
        check = subprocess.run(
            ["git", "apply", "--index", "--check"],
            cwd=assembly,
            input=patch,
            capture_output=True,
            text=True,
            check=False,
        )
        if check.returncode != 0:
            raise ClosureError(
                f"COMPOSITION_CONFLICT:{unit_id}:{(check.stderr or check.stdout).strip()[:800]}"
            )
        apply = subprocess.run(
            ["git", "apply", "--index"],
            cwd=assembly,
            input=patch,
            capture_output=True,
            text=True,
            check=False,
        )
        if apply.returncode != 0:
            raise ClosureError(
                f"COMPOSITION_APPLY_FAILED:{unit_id}:{(apply.stderr or apply.stdout).strip()[:800]}"
            )
    staged = sorted(
        line for line in _run_git(assembly, "diff", "--cached", "--name-only").splitlines() if line
    )
    if staged != sorted(seen_changed):
        raise ClosureError("COMPOSED_STAGED_PATH_SET_MISMATCH")
    for unit_id, (_, bound) in receipt_by_unit.items():
        for path in cumulative_paths_by_unit[unit_id]:
            if not any(_path_matches(path, boundary) for boundary in bound["mutation_paths"]):
                raise ClosureError(f"COMPOSED_SCOPE_WIDENING:{unit_id}:{path}")
    check = subprocess.run(
        ["git", "diff", "--cached", "--check"],
        cwd=assembly,
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode != 0:
        raise ClosureError(
            f"COMPOSED_DIFF_CHECK_FAILED:{(check.stdout or check.stderr).strip()[:800]}"
        )
    trailers: list[tuple[str, str]] = []
    for unit_id in order:
        unit_bound = receipt_by_unit[unit_id][1]
        identity = eia_worker_identity(
            provider=unit_bound["provider"],
            model=unit_bound["model"],
            worker_id=str((unit_bound.get("selected_worker") or {}).get("worker_id") or ""),
            worker_backend=unit_bound["worker_backend"],
        )
        for trailer in (
            (EIA_TRAILER_WORKER, identity["worker_id"]),
            (EIA_TRAILER_MODEL, identity["model"]),
        ):
            if trailer not in trailers:
                trailers.append(trailer)
    commit = eia_git_commit(
        assembly,
        subject=f"candidate: {task_id}/composed",
        name=EIA_COMPOSER_NAME,
        email=EIA_COMPOSER_EMAIL,
        trailers=trailers,
    )
    if commit.returncode != 0:
        raise ClosureError(
            f"COMPOSED_COMMIT_FAILED:{(commit.stderr or commit.stdout).strip()[:1000]}"
        )
    candidate_commit = _run_git(assembly, "rev-parse", "HEAD")
    candidate_tree = _run_git(assembly, "rev-parse", "HEAD^{tree}")
    changed_paths = _changed_paths(assembly, base_sha, candidate_commit)
    deleted_paths = _deleted_paths(assembly, base_sha, candidate_commit)
    for path in deleted_paths:
        owners = [
            bound
            for _, bound in receipt_by_unit.values()
            if any(_path_matches(path, boundary) for boundary in bound["mutation_paths"])
        ]
        if not owners or not all(owner["allow_deletions"] for owner in owners):
            raise ClosureError(f"COMPOSED_DELETION_NOT_AUTHORIZED:{path}")
    task_candidate = {
        "schema": TASK_CANDIDATE_SCHEMA,
        "task_id": task_id,
        "base_sha": base_sha,
        "workspace_id": lease.workspace_id,
        "workspace_path": lease.path,
        "candidate_commit": candidate_commit,
        "candidate_tree": candidate_tree,
        "candidate_diff_sha256": _diff_sha(assembly, base_sha, candidate_commit),
        "changed_paths": changed_paths,
        "deleted_paths": deleted_paths,
        "composition_order": order,
        "unit_lineage": [
            {
                "unit_id": unit_id,
                "receipt_id": receipt_by_unit[unit_id][1]["receipt_id"],
                "verification_id": verification_by_unit[unit_id]["verification_id"],
                "unit_candidate_commit": receipt_by_unit[unit_id][1]["candidate_commit"],
                "unit_candidate_tree": receipt_by_unit[unit_id][1]["candidate_tree"],
            }
            for unit_id in order
        ],
        "claim_ceiling": "TASK_CANDIDATE_REQUIRES_WHOLE_TASK_VERIFICATION",
    }
    task_candidate["task_candidate_id"] = _sha256(_canonical_json(task_candidate))
    return task_candidate, lease


def verify_whole_task_candidate(
    task_candidate: Mapping[str, Any],
    verifier_specs: Sequence[Mapping[str, Any] | VerifierSpec],
    *,
    authorized_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Run whole-task verifiers plus closure-owned integrity checks.

    ``authorized_paths`` is the union of the composed units' mutation boundaries;
    without it the scope check falls back to the candidate's composed path set.
    Deletions are only allowed for paths composition already authorized.
    """
    if task_candidate.get("schema") != TASK_CANDIDATE_SCHEMA:
        raise ClosureError("INVALID_TASK_CANDIDATE")
    changed = [str(path) for path in task_candidate.get("changed_paths") or []]
    deleted = [str(path) for path in task_candidate.get("deleted_paths") or []]
    result = _run_verifier_specs(
        task_id=_safe_slug(task_candidate.get("task_id"), "task_id"),
        unit_id="",
        workspace_path=str(task_candidate.get("workspace_path") or ""),
        candidate_commit=str(task_candidate.get("candidate_commit") or ""),
        specs=verifier_specs,
        schema=WHOLE_VERIFICATION_SCHEMA,
        scope="WHOLE_TASK",
        base_sha=str(task_candidate.get("base_sha") or ""),
        authorized_paths=list(authorized_paths) if authorized_paths is not None else changed,
        deletable_paths=deleted,
        # The composed-path fallback is a scope boundary, not an explicit authorization
        # of root-level shadowing files.
        shadow_authorized_paths=list(authorized_paths) if authorized_paths is not None else (),
    )
    result.update({
        "base_sha": task_candidate.get("base_sha"),
        "task_candidate_id": task_candidate.get("task_candidate_id"),
        "candidate_tree": task_candidate.get("candidate_tree"),
        "candidate_diff_sha256": task_candidate.get("candidate_diff_sha256"),
    })
    material = dict(result)
    material.pop("verification_id", None)
    result["verification_id"] = _sha256(_canonical_json(material))
    return result


def _unique_failed_owner(whole_verification: Mapping[str, Any], valid_units: set[str]) -> str:
    if any(not row.get("passed") for row in whole_verification.get("integrity_checks", [])):
        # Built-in integrity failures are task-level; no single unit owns them.
        return ""
    failed = [row for row in whole_verification.get("results", []) if not row.get("passed")]
    if not failed:
        return ""
    owners = [str(row.get("owner_unit") or "") for row in failed]
    if any(not owner for owner in owners):
        return ""
    unique = set(owners)
    if len(unique) != 1:
        return ""
    owner = next(iter(unique))
    return owner if owner in valid_units else ""


def _integrity_passed(verification: Mapping[str, Any]) -> bool:
    """True only when every built-in integrity check ran and passed (fail closed)."""
    rows = verification.get("integrity_checks")
    if verification.get("integrity_status") != "PASS" or not isinstance(rows, list):
        return False
    return sorted(str(row.get("check_id")) for row in rows) == sorted(INTEGRITY_CHECK_IDS) and all(
        row.get("passed") is True for row in rows
    )


def build_acceptance_packet(
    *,
    task_candidate: Mapping[str, Any],
    whole_verification: Mapping[str, Any],
    unit_receipts: Sequence[Mapping[str, Any]],
    unit_verifications: Sequence[Mapping[str, Any]],
    task_card_ref: str,
    task_card_hash: str,
    external_intelligence_refs: Sequence[str] = (),
) -> dict[str, Any]:
    if task_candidate.get("schema") != TASK_CANDIDATE_SCHEMA:
        raise ClosureError("INVALID_TASK_CANDIDATE")
    if (
        whole_verification.get("schema") != WHOLE_VERIFICATION_SCHEMA
        or whole_verification.get("status") != "PASS"
    ):
        raise ClosureError("WHOLE_TASK_PASS_REQUIRED")
    if whole_verification.get("task_candidate_id") != task_candidate.get("task_candidate_id"):
        raise ClosureError("WHOLE_VERIFICATION_CANDIDATE_MISMATCH")
    if not _integrity_passed(whole_verification):
        raise ClosureError("WHOLE_TASK_INTEGRITY_PASS_REQUIRED")
    if not task_card_ref or not _is_hex(task_card_hash, 64):
        raise ClosureError("TASK_CARD_BINDING_REQUIRED")
    receipt_by_unit = {
        str(receipt.get("unit_id")): validate_worker_receipt(receipt) for receipt in unit_receipts
    }
    verification_by_unit = {str(value.get("unit_id")): value for value in unit_verifications}
    if set(receipt_by_unit) != set(verification_by_unit):
        raise ClosureError("ACCEPTANCE_UNIT_SET_MISMATCH")
    for unit_id, verification in verification_by_unit.items():
        if (
            verification.get("schema") != UNIT_VERIFICATION_SCHEMA
            or verification.get("status") != "PASS"
        ):
            raise ClosureError("ACCEPTANCE_REQUIRES_UNIT_PASS")
        if verification.get("worker_receipt_id") != receipt_by_unit[unit_id]["receipt_id"]:
            raise ClosureError("ACCEPTANCE_UNIT_BINDING_MISMATCH")
        if not _integrity_passed(verification):
            raise ClosureError("ACCEPTANCE_REQUIRES_UNIT_INTEGRITY_PASS")
    packet = {
        "schema": ACCEPTANCE_PACKET_SCHEMA,
        "task_id": task_candidate["task_id"],
        "task_card_ref": str(task_card_ref),
        "task_card_hash": str(task_card_hash).lower(),
        "external_intelligence_refs": [str(ref) for ref in external_intelligence_refs],
        "task_candidate": {
            "task_candidate_id": task_candidate["task_candidate_id"],
            "base_sha": task_candidate["base_sha"],
            "candidate_commit": task_candidate["candidate_commit"],
            "candidate_tree": task_candidate["candidate_tree"],
            "candidate_diff_sha256": task_candidate["candidate_diff_sha256"],
            "changed_paths": list(task_candidate["changed_paths"]),
            "deleted_paths": list(task_candidate["deleted_paths"]),
            "composition_order": list(task_candidate["composition_order"]),
        },
        "unit_lineage": [
            {
                "unit_id": unit_id,
                "worker_receipt_id": receipt_by_unit[unit_id]["receipt_id"],
                "unit_verification_id": verification_by_unit[unit_id]["verification_id"],
                "session_id": receipt_by_unit[unit_id]["session_id"],
                "workspace_id": receipt_by_unit[unit_id]["workspace_id"],
                "candidate_commit": receipt_by_unit[unit_id]["candidate_commit"],
                "candidate_tree": receipt_by_unit[unit_id]["candidate_tree"],
            }
            for unit_id in sorted(receipt_by_unit)
        ],
        "whole_task_verification_id": whole_verification["verification_id"],
        "whole_task_status": "PASS",
        # Additive: closure-owned integrity checks that passed at each level.
        "integrity_checks": {
            "base_sha": task_candidate["base_sha"],
            "whole_task": [
                str(row.get("check_id")) for row in whole_verification.get("integrity_checks", [])
            ],
            "units": {
                unit_id: [
                    str(row.get("check_id"))
                    for row in verification_by_unit[unit_id].get("integrity_checks", [])
                ]
                for unit_id in sorted(verification_by_unit)
            },
        },
        "current_gate": "PENDING_INDEPENDENT_ACCEPTANCE",
        "claim_ceiling": CLAIM_CEILING,
    }
    packet["packet_id"] = _sha256(_canonical_json(packet))
    return packet


def build_closure_capsule(
    *,
    task_candidate: Mapping[str, Any],
    acceptance_packet_ref: str,
    acceptance_packet_sha256: str,
) -> dict[str, Any]:
    if (
        task_candidate.get("schema") != TASK_CANDIDATE_SCHEMA
        or not acceptance_packet_ref
        or not _is_hex(acceptance_packet_sha256, 64)
    ):
        raise ClosureError("INVALID_CAPSULE_INPUT")
    capsule = {
        "schema": CLOSURE_CAPSULE_SCHEMA,
        "task_id": task_candidate["task_id"],
        "candidate_commit": task_candidate["candidate_commit"],
        "candidate_tree": task_candidate["candidate_tree"],
        "candidate_diff_sha256": task_candidate["candidate_diff_sha256"],
        "verification_state": "WHOLE_TASK_PASS",
        "acceptance_packet_ref": acceptance_packet_ref,
        "acceptance_packet_sha256": acceptance_packet_sha256,
        "current_gate": "PENDING_INDEPENDENT_ACCEPTANCE",
        "next_action": "run_independent_candidate_acceptance_audit",
        "stop_if": "independent_acceptance_not_explicitly_granted",
        "claim_ceiling": CLAIM_CEILING,
    }
    capsule["capsule_id"] = _sha256(_canonical_json(capsule))
    return capsule


class ExternalIntelligenceClosureRuntime:
    def __init__(
        self,
        *,
        repository_root: str | os.PathLike[str],
        allocator: CompositionWorkspaceAllocator,
        store: ClosureStore,
        c_runtime: Any | None = None,
        max_repairs_per_unit: int = 1,
    ):
        if max_repairs_per_unit < 0 or max_repairs_per_unit > 20:
            raise ClosureError("INVALID_REPAIR_BUDGET")
        worker_budget = getattr(c_runtime, "max_repairs_per_unit", None)
        if isinstance(worker_budget, int) and worker_budget < max_repairs_per_unit:
            # Core bindings are minted to live for the worker runtime's budget; a larger
            # closure budget would continue repairs on an expired binding.
            raise ClosureError("REPAIR_BUDGET_EXCEEDS_WORKER_BUDGET")
        self.repository_root = Path(repository_root).expanduser().resolve()
        self.allocator = allocator
        self.store = store
        self.c_runtime = c_runtime
        self.max_repairs_per_unit = max_repairs_per_unit

    def _persist_verification(self, verification: Mapping[str, Any]) -> dict[str, Any]:
        ref, sha = self.store.write_verification(verification)
        value = dict(verification)
        value["artifact_ref"] = ref
        value["artifact_sha256"] = sha
        return value

    def _repair(
        self,
        *,
        receipt: Mapping[str, Any],
        delta: Mapping[str, Any],
        repair_index: int,
    ) -> tuple[Mapping[str, Any] | None, dict[str, Any]]:
        ref, sha = self.store.write_repair_delta(delta, repair_index=repair_index)
        persisted = dict(delta)
        persisted["artifact_ref"] = ref
        persisted["artifact_sha256"] = sha
        if self.c_runtime is None:
            return None, persisted
        parent_bound = validate_worker_receipt(receipt)
        repaired = self.c_runtime.continue_repair(
            receipt,
            repair_id=f"d{repair_index:03d}",
            repair_ref=ref,
            repair_sha256=sha,
        )
        _validate_repair_result(parent_bound, repaired)
        return repaired, persisted

    def close_task(
        self,
        *,
        main_sha: str,
        unit_receipts: Sequence[Mapping[str, Any]],
        unit_verifiers: Mapping[str, Sequence[Mapping[str, Any] | VerifierSpec]],
        whole_verifiers: Sequence[Mapping[str, Any] | VerifierSpec],
        task_card_ref: str,
        task_card_hash: str,
        external_intelligence_refs: Sequence[str] = (),
    ) -> dict[str, Any]:
        started = time.monotonic()
        task_card_authority = _verify_task_card_binding(
            self.repository_root, main_sha, task_card_ref, task_card_hash
        )
        for unit_id, specs in unit_verifiers.items():
            for spec in specs:
                parsed_spec = VerifierSpec.from_value(spec)
                if parsed_spec.argv not in task_card_authority.verification_commands:
                    raise ClosureError("VERIFIER_NOT_AUTHORIZED")
        for spec in whole_verifiers:
            parsed_spec = VerifierSpec.from_value(spec)
            if parsed_spec.argv not in task_card_authority.verification_commands:
                raise ClosureError("VERIFIER_NOT_AUTHORIZED")
        if not unit_receipts:
            raise ClosureError("UNIT_RECEIPTS_REQUIRED")
        current: dict[str, Mapping[str, Any]] = {}
        for receipt in unit_receipts:
            bound = validate_worker_receipt(receipt)
            if bound["base_sha"] != main_sha.lower():
                raise ClosureError("CLOSURE_BASE_SHA_MISMATCH")
            if bound["unit_id"] in current:
                raise ClosureError("DUPLICATE_UNIT_RECEIPT")
            current[bound["unit_id"]] = receipt
        if set(unit_verifiers) != set(current):
            raise ClosureError("UNIT_VERIFIER_SET_MISMATCH")
        task_ids = {validate_worker_receipt(receipt)["task_id"] for receipt in current.values()}
        if len(task_ids) != 1:
            raise ClosureError("MIXED_TASK_CLOSURE_FORBIDDEN")
        task_id = next(iter(task_ids))
        repair_counts = {unit_id: self.store.repair_count(task_id, unit_id) for unit_id in current}
        repair_deltas: list[dict[str, Any]] = []
        verification_history: list[dict[str, Any]] = []
        composition_conflicts = 0
        max_cycles = max(2, 2 + self.max_repairs_per_unit * max(1, len(current)))

        for _cycle in range(max_cycles):
            latest_verifications: dict[str, dict[str, Any]] = {}
            failing_units: list[str] = []
            for unit_id in sorted(current):
                verification = self._persist_verification(
                    verify_unit_candidate(current[unit_id], unit_verifiers[unit_id])
                )
                latest_verifications[unit_id] = verification
                verification_history.append(verification)
                if verification["status"] != "PASS":
                    failing_units.append(unit_id)
            if failing_units:
                for unit_id in failing_units:
                    if repair_counts[unit_id] >= self.max_repairs_per_unit:
                        return self._terminal(
                            status="REPAIR_BUDGET_EXHAUSTED",
                            current=current,
                            verifications=latest_verifications,
                            repair_deltas=repair_deltas,
                            composition_conflicts=composition_conflicts,
                            started=started,
                            reason=unit_id,
                        )
                    repair_index = self.store.next_repair_index(task_id, unit_id)
                    delta = build_unit_repair_delta(
                        current[unit_id], latest_verifications[unit_id], repair_index=repair_index
                    )
                    repaired, persisted = self._repair(
                        receipt=current[unit_id], delta=delta, repair_index=repair_index
                    )
                    repair_deltas.append(persisted)
                    repair_counts[unit_id] += 1
                    if repaired is None:
                        return self._terminal(
                            status="UNIT_REPAIR_REQUIRED",
                            current=current,
                            verifications=latest_verifications,
                            repair_deltas=repair_deltas,
                            composition_conflicts=composition_conflicts,
                            started=started,
                            reason=unit_id,
                        )
                    current[unit_id] = repaired
                continue

            try:
                task_candidate, _lease = compose_task_candidate(
                    repository_root=self.repository_root,
                    allocator=self.allocator,
                    receipts=[current[unit_id] for unit_id in sorted(current)],
                    verifications=[latest_verifications[unit_id] for unit_id in sorted(current)],
                )
            except ClosureError as exc:
                composition_conflicts += 1
                return self._terminal(
                    status="SCOPE_DELTA_REQUIRED",
                    current=current,
                    verifications=latest_verifications,
                    repair_deltas=repair_deltas,
                    composition_conflicts=composition_conflicts,
                    started=started,
                    reason=str(exc),
                )
            task_candidate_ref, task_candidate_sha = self.store.write_task_candidate(task_candidate)
            task_candidate = dict(task_candidate)
            task_candidate["artifact_ref"] = task_candidate_ref
            task_candidate["artifact_sha256"] = task_candidate_sha
            authorized_paths = sorted({
                str(path)
                for receipt in current.values()
                for path in validate_worker_receipt(receipt)["mutation_paths"]
            })
            whole = self._persist_verification(
                verify_whole_task_candidate(
                    task_candidate, whole_verifiers, authorized_paths=authorized_paths
                )
            )
            if whole["status"] == "FAIL":
                owner = _unique_failed_owner(whole, set(current))
                if not owner:
                    return self._terminal(
                        status="SCOPE_DELTA_REQUIRED",
                        current=current,
                        verifications=latest_verifications,
                        repair_deltas=repair_deltas,
                        composition_conflicts=composition_conflicts,
                        started=started,
                        reason="WHOLE_FAILURE_OWNER_AMBIGUOUS",
                        task_candidate=task_candidate,
                        whole_verification=whole,
                    )
                if repair_counts[owner] >= self.max_repairs_per_unit:
                    return self._terminal(
                        status="REPAIR_BUDGET_EXHAUSTED",
                        current=current,
                        verifications=latest_verifications,
                        repair_deltas=repair_deltas,
                        composition_conflicts=composition_conflicts,
                        started=started,
                        reason=owner,
                        task_candidate=task_candidate,
                        whole_verification=whole,
                    )
                repair_index = self.store.next_repair_index(task_candidate["task_id"], owner)
                delta = build_composition_repair_delta(
                    current[owner], whole, repair_index=repair_index
                )
                repaired, persisted = self._repair(
                    receipt=current[owner], delta=delta, repair_index=repair_index
                )
                repair_deltas.append(persisted)
                repair_counts[owner] += 1
                if repaired is None:
                    return self._terminal(
                        status="COMPOSITION_REPAIR_REQUIRED",
                        current=current,
                        verifications=latest_verifications,
                        repair_deltas=repair_deltas,
                        composition_conflicts=composition_conflicts,
                        started=started,
                        reason=owner,
                        task_candidate=task_candidate,
                        whole_verification=whole,
                    )
                current[owner] = repaired
                continue

            packet = build_acceptance_packet(
                task_candidate=task_candidate,
                whole_verification=whole,
                unit_receipts=[current[unit_id] for unit_id in sorted(current)],
                unit_verifications=[latest_verifications[unit_id] for unit_id in sorted(current)],
                task_card_ref=task_card_ref,
                task_card_hash=task_card_hash,
                external_intelligence_refs=external_intelligence_refs,
            )
            packet_ref, packet_sha = self.store.write_acceptance_packet(packet)
            packet = dict(packet)
            packet["artifact_ref"] = packet_ref
            packet["artifact_sha256"] = packet_sha
            capsule = build_closure_capsule(
                task_candidate=task_candidate,
                acceptance_packet_ref=packet_ref,
                acceptance_packet_sha256=packet_sha,
            )
            capsule_ref, capsule_sha = self.store.write_capsule(capsule)
            capsule = dict(capsule)
            capsule["artifact_ref"] = capsule_ref
            capsule["artifact_sha256"] = capsule_sha
            telemetry = {
                "unit_count": len(current),
                "verified_unit_count": len(latest_verifications),
                "repair_count": sum(repair_counts.values()),
                "composition_conflict_count": composition_conflicts,
                "whole_task_verifier_count": len(whole.get("results", [])),
                "whole_task_outcome": whole["status"],
                "wall_time_ms": max(0, int((time.monotonic() - started) * 1000)),
                "policy_tuned": False,
            }
            result = {
                "schema": CLOSURE_RUN_SCHEMA,
                "status": CLAIM_CEILING,
                "task_id": task_candidate["task_id"],
                "task_candidate": task_candidate,
                "whole_verification": whole,
                "unit_verifications": [
                    latest_verifications[unit_id] for unit_id in sorted(latest_verifications)
                ],
                "repair_deltas": repair_deltas,
                "acceptance_packet": packet,
                "control_capsule": capsule,
                "telemetry": telemetry,
                "claim_ceiling": CLAIM_CEILING,
            }
            result["run_id"] = _sha256(_canonical_json(result))
            return result

        return self._terminal(
            status="REPAIR_BUDGET_EXHAUSTED",
            current=current,
            verifications={},
            repair_deltas=repair_deltas,
            composition_conflicts=composition_conflicts,
            started=started,
            reason="CLOSURE_CYCLE_LIMIT",
        )

    def _terminal(
        self,
        *,
        status: str,
        current: Mapping[str, Mapping[str, Any]],
        verifications: Mapping[str, Mapping[str, Any]],
        repair_deltas: Sequence[Mapping[str, Any]],
        composition_conflicts: int,
        started: float,
        reason: str,
        task_candidate: Mapping[str, Any] | None = None,
        whole_verification: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        task_ids = {validate_worker_receipt(receipt)["task_id"] for receipt in current.values()}
        result = {
            "schema": CLOSURE_RUN_SCHEMA,
            "status": status,
            "task_id": next(iter(task_ids)) if len(task_ids) == 1 else "",
            "reason": reason,
            "unit_verifications": [dict(verifications[key]) for key in sorted(verifications)],
            "repair_deltas": [dict(value) for value in repair_deltas],
            "task_candidate": dict(task_candidate or {}),
            "whole_verification": dict(whole_verification or {}),
            "acceptance_packet": {},
            "control_capsule": {},
            "telemetry": {
                "unit_count": len(current),
                "verified_unit_count": sum(
                    1 for value in verifications.values() if value.get("status") == "PASS"
                ),
                "repair_count": len(repair_deltas),
                "composition_conflict_count": composition_conflicts,
                "whole_task_verifier_count": len((whole_verification or {}).get("results", [])),
                "whole_task_outcome": str((whole_verification or {}).get("status") or "NOT_RUN"),
                "wall_time_ms": max(0, int((time.monotonic() - started) * 1000)),
                "policy_tuned": False,
            },
            "claim_ceiling": "NO_ACCEPTANCE_CLAIM",
        }
        result["run_id"] = _sha256(_canonical_json(result))
        return result


__all__ = [
    "ACCEPTANCE_PACKET_SCHEMA",
    "CLAIM_CEILING",
    "CLOSURE_CAPSULE_SCHEMA",
    "CLOSURE_RUN_SCHEMA",
    "COMPOSITION_REPAIR_DELTA_SCHEMA",
    "TASK_CANDIDATE_SCHEMA",
    "UNIT_REPAIR_DELTA_SCHEMA",
    "UNIT_VERIFICATION_SCHEMA",
    "WHOLE_VERIFICATION_SCHEMA",
    "AssemblyLease",
    "INTEGRITY_CHECK_DELETIONS",
    "INTEGRITY_CHECK_ERROR",
    "INTEGRITY_CHECK_IDS",
    "INTEGRITY_CHECK_SCOPE",
    "INTEGRITY_CHECK_WHITESPACE",
    "INTEGRITY_DELETION_NOT_AUTHORIZED",
    "INTEGRITY_SCOPE_WIDENING",
    "INTEGRITY_WHITESPACE_ERRORS",
    "VERIFIER_ENV_BASE_SHA",
    "VERIFIER_ENV_CANDIDATE_SHA",
    "ClosureError",
    "ClosureStore",
    "CompositionWorkspaceAllocator",
    "ExternalIntelligenceClosureRuntime",
    "VerifierSpec",
    "build_acceptance_packet",
    "build_closure_capsule",
    "build_composition_repair_delta",
    "build_unit_repair_delta",
    "compose_task_candidate",
    "run_integrity_checks",
    "validate_worker_receipt",
    "verify_unit_candidate",
    "verify_whole_task_candidate",
]
