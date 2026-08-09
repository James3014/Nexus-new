"""Single GPT-visible MCP gateway for bounded Nexus workspace/lifecycle actions.

The gateway deliberately exposes a small public surface.  The existing
29-action self-hosted server remains an internal lifecycle provider; callers
must not need to know its Target paths or internal action names.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os
import re
import select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional
from uuid import uuid4

from nexus.contracts.lifecycle_action import (
    ContractKind,
    LifecycleActionType,
    MutationDomain,
    PermissionProfile,
    build_action_envelope,
    build_owner_inline_contract,
)
from nexus.contracts.target_integration_lifecycle import ExternalAcceptanceReceipt
from nexus.engine.canonical_task_seam import execute_canonical_product_task
from nexus.orchestrator.canonical_mcp_ingress import (
    build_mcp_execution_context,
    reject_caller_route_overrides,
)
from nexus.orchestrator.lifecycle_guards import (
    LifecycleGuardError,
    configure_runtime_manifest_hash,
    post_action_receipt_formatter,
    pre_action_guard,
    validate_approval_grant,
)
from nexus.orchestrator.self_hosted_task_service import (
    CANONICAL_SOURCE_ROOT,
    SelfHostedTaskService,
    resolve_contract_identity,
    validate_workforce_dispatch_binding,
)
from nexus.services.model_workforce_policy import NON_ADMISSIBLE_STATES, WorkforcePolicyLoader
from nexus.services.unified_runtime import (
    LOCAL_ONLY_PROVIDERS,
    ONLINE_CLI_SPEC_REGISTRY,
    resolve_registered_provider_executable,
)

GATEWAY_NAME = "nexus-mcp-gateway"
GATEWAY_VERSION = "0.1.0"
PUBLIC_APP_NAME = "Nexus"
SERVER_INSTANCE_ID = uuid4().hex
SERVER_STARTED_AT = datetime.now(timezone.utc).isoformat()
LIFECYCLE_REVISION = "nexus.lifecycle.gateway.v2"
LIFECYCLE_STATE_SCHEMA_REVISION = "nexus.self_hosted_task_state.v1"
TASK_CONTRACT_REVISION = "nexus.task_contract.v1"
PERMISSION_POLICY_REVISION = "nexus.permission.policy.v1"
PERMISSION_POLICY = {
    "revision": PERMISSION_POLICY_REVISION,
    "profiles": ["DISCOVERY", "OBSERVE", "VERIFY", "MUTATE_BOUNDED", "CANDIDATE", "INTEGRATE"],
    "approval_scopes": ["ALLOW_ACTION_ONCE", "ALLOW_TASK_ATTEMPT", "REJECT"],
    "always_allow": False,
}
PERMISSION_POLICY_HASH = hashlib.sha256(
    json.dumps(PERMISSION_POLICY, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
MAX_READ_BYTES = 1024 * 1024
MAX_RESULT_BYTES = 1024 * 1024
MAX_SEARCH_RESULTS = 200
MAX_SEARCH_FILE_BYTES = 1024 * 1024
MAX_SEARCH_TOTAL_BYTES = 64 * 1024 * 1024
MAX_SEARCH_FILES = 10000
MAX_SEARCH_SECONDS = 3
MAX_SEARCH_LINE_BYTES = 4096
MAX_SEARCH_STDERR_BYTES = 64 * 1024
FRESHNESS_SEMANTICS_REVISION = "nexus.gateway_freshness.v3"
CLINE_RUN_TIMEOUT_SECONDS = 60
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# Populated from ``UnifiedMCPGateway.tool_specs()`` after the class definition.
# There must be one public manifest truth; status, health, recovery validation,
# and the MCP initialize revision all consume this derived tuple.
PUBLIC_TOOL_NAMES: tuple[str, ...]
TOOL_MANIFEST_REVISION: str
FULL_TOOL_SCHEMA_HASH: str
SERVER_REPO_HEAD_AT_START: str
# Freeze the runtime source set and its digests once at gateway load so later
# imports never change the freshness comparison baseline.
RUNTIME_SOURCE_PATHS: tuple[Path, ...]
RUNTIME_SOURCE_SHA256_AT_START: str
ACTION_CONTRACT_SHA256_AT_START: str
PERMISSION_ENFORCEMENT_SHA256_AT_START: str


# Agy 1.1.11 encodes the reasoning tier in the model identity suffix
# (-high/-medium/-low) and rejects an ``--effort`` flag that contradicts the
# tier.  Both assisted-provider paths must normalize effort through this single
# compiler so a hard-coded default can never override the model identity.
AGY_EFFORT_TIERS: tuple[str, ...] = ("high", "medium", "low")
AGY_PRINT_TIMEOUT = "25s"


def _agy_effort_tier(model: str) -> str:
    """Return the effort tier embedded in an Agy model name, or ``""``."""
    name = (model or "").strip()
    for tier in AGY_EFFORT_TIERS:
        if name.endswith(f"-{tier}"):
            return tier
    return ""


def _compile_agy_command(
    *,
    executable: str,
    model: str,
    prompt: str,
    json_schema: str = "",
    explicit_effort: str = "",
) -> list[str]:
    """Single source of truth for Agy CLI argument compilation.

    Rules:
    - ``--effort`` is emitted only when the caller explicitly supplies it.
    - An explicit effort that contradicts a tier suffix in the model identity
      fails closed deterministically instead of silently overriding.
    - A model carrying no tier suffix still requires an explicit effort for
      Agy 1.1.11; the compiler never invents a default tier on its own.
    - Suffixed models accept the canonical ``--model <name>`` form with the
      tier omitted from the flag surface.
    """
    name = (model or "").strip()
    tier = _agy_effort_tier(name)
    explicit = (explicit_effort or "").strip().lower()
    if explicit and explicit not in AGY_EFFORT_TIERS:
        raise GatewayInputError(f"agy effort must be one of {', '.join(AGY_EFFORT_TIERS)}")
    if explicit and tier and explicit != tier:
        raise GatewayInputError(
            f"agy model {name!r} embeds {(tier + ' effort')!r}; explicit --effort {explicit!r} conflicts"
        )
    command = [executable, "--mode", "plan", "--sandbox", "--output-format", "json"]
    if json_schema:
        command.extend(["--json-schema", json_schema])
    if explicit:
        command.extend(["--effort", explicit])
    elif not tier and not name:
        # Neither the model nor the caller pinned an effort.  The adapter must
        # not choose one on behalf of the caller.
        raise GatewayInputError("agy model requires an explicit effort or an embedded tier suffix")
    if name:
        command.extend(["--model", name])
    command.extend(["--print-timeout", AGY_PRINT_TIMEOUT, "--prompt", prompt])
    return command


class GatewayInputError(ValueError):
    """Raised when a public gateway request is outside its bounded contract."""


def _text(value: Any, field: str, *, max_length: int = 4096) -> str:
    result = str(value or "").strip()
    if not result:
        raise GatewayInputError(f"{field} is required")
    if len(result) > max_length:
        raise GatewayInputError(f"{field} exceeds {max_length} characters")
    return result


def _safe_relative_path(value: Any, field: str = "path") -> Path:
    raw = _text(value, field, max_length=1024)
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise GatewayInputError(f"{field} must be a bounded relative path")
    if ".git" in candidate.parts:
        raise GatewayInputError(f"{field} cannot access .git")
    resolved = (CANONICAL_SOURCE_ROOT / candidate).resolve()
    try:
        resolved.relative_to(CANONICAL_SOURCE_ROOT)
    except ValueError as exc:
        raise GatewayInputError(f"{field} escapes canonical root") from exc
    return resolved


def _safe_search_target(value: Any) -> tuple[Path, Path]:
    """Validate a search target fail-closed against symlink traversal.

    Returns ``(lexical, resolved)`` where ``lexical`` stays inside the canonical
    root and ``resolved`` is the on-disk target.  Every path component - the
    intermediate directories and the final component - is checked with
    ``lstat()``; any symlink rejects the request so a search can never read
    through a link planted outside the canonical root.
    """
    raw = _text(value, "path", max_length=1024)
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise GatewayInputError("path must be a bounded relative path")
    if ".git" in candidate.parts:
        raise GatewayInputError("path cannot access .git")
    lexical = CANONICAL_SOURCE_ROOT / candidate
    current = CANONICAL_SOURCE_ROOT
    for part in candidate.parts:
        current = current / part
        try:
            if stat.S_ISLNK(os.lstat(current).st_mode):
                raise GatewayInputError("search path cannot traverse symlinks")
        except FileNotFoundError:
            break
    resolved = lexical.resolve()
    try:
        resolved.relative_to(CANONICAL_SOURCE_ROOT)
    except ValueError as exc:
        raise GatewayInputError("path escapes canonical root") from exc
    return lexical, resolved


def _git(*args: str, timeout: float = 3.0) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=CANONICAL_SOURCE_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git command failed: {' '.join(args)}")
    return result.stdout


def _bounded_text(value: str, field: str) -> str:
    if len(value.encode("utf-8")) > MAX_RESULT_BYTES:
        raise RuntimeError(f"{field} exceeds {MAX_RESULT_BYTES} bytes")
    return value


def _bounded_match_line(line: str) -> tuple[str, bool]:
    """Deterministically cap one search match line so a single oversized line
    cannot blow through the response byte budget.

    Returns ``(bounded_line, truncated)`` where ``truncated`` is true when the
    line was trimmed to ``MAX_SEARCH_LINE_BYTES`` and must surface as a global
    truncation flag.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= MAX_SEARCH_LINE_BYTES:
        return line, False
    return encoded[:MAX_SEARCH_LINE_BYTES].decode("utf-8", errors="ignore"), True


def _git_ls_files(*, root: Path, relative: str) -> list[str]:
    """List Git-tracked and non-ignored untracked files under one relative path.

    Parsing is NUL-safe: the ``-z`` flag emits each path name verbatim (newlines
    and surrounding whitespace preserved) and non-UTF-8 names survive via
    ``os.fsdecode`` surrogateescape.
    """
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--deduplicate", "-z", "--", relative],
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=MAX_SEARCH_SECONDS, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or "git ls-files failed")
    paths: list[str] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        paths.append(os.fsdecode(raw))
    return paths


def _search_candidate_files(*, root: Path, target: Path) -> list[Path]:
    """Return the ordered candidate files for a literal search target.

    A single regular file scans only that file.  A directory resolves to the
    Git-tracked and non-ignored untracked file list so the search never runs an
    unbounded whole-filesystem recursion.
    """
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError:
        return []
    if not target_resolved.is_symlink() and target_resolved.is_file():
        return [target_resolved]
    try:
        relative = str(target_resolved.relative_to(root_resolved)) or "."
    except ValueError:
        return []
    candidates: list[Path] = []
    for raw in _git_ls_files(root=root_resolved, relative=relative):
        raw_path = root_resolved / raw
        if raw_path.is_symlink():
            continue
        resolved = raw_path.resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            continue
        candidates.append(resolved)
    candidates.sort(key=lambda path: path.relative_to(root_resolved).as_posix())
    return candidates


def _searchable_file(*, root: Path, candidate: Path) -> bool:
    """Re-validate one candidate file before reading it."""
    if candidate.is_symlink():
        return False
    if ".git" in candidate.parts:
        return False
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    if not candidate.is_file():
        return False
    try:
        if candidate.stat().st_size > MAX_SEARCH_FILE_BYTES:
            return False
    except OSError:
        return False
    return True


def _display_search_path(path: Path, *, root: Path) -> str:
    """Render a canonical-relative path safely when its name bytes are not UTF-8.

    Non-UTF-8 filename bytes are escaped deterministically (e.g. ``caf\xe9.txt``)
    so the displayed path never contains surrogate code points, survives UTF-8
    re-encoding, and stays JSON-serializable.
    """
    relative = path.relative_to(root)
    raw = os.fsencode(relative)
    return raw.decode("utf-8", errors="backslashreplace")


def _literal_matches_in_file(*, root: Path, candidate: Path, pattern: str) -> tuple[list[str], bool]:
    """Literal substring match over one UTF-8 file, skipping unreadable or
    binary content.  Output lines use ``relative/path.py:line:content`` and
    ``truncated`` is true when any matching line was capped."""
    try:
        raw = candidate.read_bytes()
    except OSError:
        return [], False
    if b"\x00" in raw:
        return [], False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return [], False
    relative = _display_search_path(candidate, root=root)
    found: list[str] = []
    truncated = False
    for lineno, line in enumerate(text.split("\n"), start=1):
        if pattern not in line:
            continue
        if line.endswith("\r"):
            line = line[:-1]
        bounded, line_truncated = _bounded_match_line(f"{relative}:{lineno}:{line}")
        truncated = truncated or line_truncated
        found.append(bounded)
    return found, truncated


def _python_literal_search(
    *,
    root: Path,
    target: Path,
    pattern: str,
) -> tuple[list[str], bool]:
    """Standard-library literal search fallback used when ripgrep is absent.

    Enforces the named search resource limits and returns ``(matches, truncated)``
    where the match lines are always canonical-root-relative.
    """
    root_resolved = root.resolve()
    candidates = _search_candidate_files(root=root_resolved, target=target)
    deadline = time.monotonic() + MAX_SEARCH_SECONDS
    matches: list[str] = []
    output_bytes = 0
    scanned = 0
    total_bytes = 0
    truncated = False
    for candidate in candidates:
        if len(matches) >= MAX_SEARCH_RESULTS:
            truncated = True
            break
        if scanned >= MAX_SEARCH_FILES:
            truncated = True
            break
        if time.monotonic() >= deadline:
            truncated = True
            break
        scanned += 1
        if not _searchable_file(root=root_resolved, candidate=candidate):
            continue
        try:
            size = candidate.stat().st_size
        except OSError:
            continue
        if total_bytes + size > MAX_SEARCH_TOTAL_BYTES:
            truncated = True
            break
        total_bytes += size
        file_matches, file_truncated = _literal_matches_in_file(root=root_resolved, candidate=candidate, pattern=pattern)
        truncated = truncated or file_truncated
        for matched in file_matches:
            if len(matches) >= MAX_SEARCH_RESULTS:
                truncated = True
                break
            matched_bytes = len(matched.encode("utf-8"))
            if output_bytes + matched_bytes > MAX_RESULT_BYTES:
                truncated = True
                break
            matches.append(matched)
            output_bytes += matched_bytes
        if truncated:
            break
    return matches, truncated


def _bounded_rg_matches(lines: list[str]) -> tuple[list[str], bool]:
    """Apply the same result and byte caps to ripgrep output lines."""
    matches: list[str] = []
    truncated = bool(len(lines) > MAX_SEARCH_RESULTS)
    output_bytes = 0
    for line in lines:
        if len(matches) >= MAX_SEARCH_RESULTS:
            truncated = True
            break
        bounded, line_truncated = _bounded_match_line(line)
        truncated = truncated or line_truncated
        matched_bytes = len(bounded.encode("utf-8"))
        if output_bytes + matched_bytes > MAX_RESULT_BYTES:
            truncated = True
            break
        matches.append(bounded)
        output_bytes += matched_bytes
    return matches, truncated


def _terminate_and_reap_search_process(process: subprocess.Popen) -> str:
    """Force a search child to exit and reap it, failing closed on refusal.

    Returns one of ``already_exited``, ``sigterm``, or ``sigkill`` describing
    the action actually taken so the caller only accepts a return code when it
    matches the signal this helper really sent.  terminate -> wait(0.5) ->
    kill -> wait(1.0) bounds the total wait; if the process still refuses to
    die the second wait timeout raises so a leaked child can never pass as a
    successful cleanup.

    If the child exits between ``poll`` and ``terminate``/``kill``
    (``ProcessLookupError``) it is reaped with a bounded ``wait`` and reported
    as ``already_exited`` rather than falsely claiming a signal was sent.
    """
    if process.poll() is not None:
        process.wait()
        return "already_exited"
    try:
        process.terminate()
    except ProcessLookupError:
        process.wait()
        return "already_exited"
    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            process.wait()
            return "already_exited"
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            raise RuntimeError("search process cleanup failed") from None
        return "sigkill"
    return "sigterm"


def _run_rg_literal_search(
    *,
    executable: str,
    root: Path,
    relative: str,
    pattern: str,
) -> tuple[list[str], bool]:
    """Run one literal ripgrep search under hard process-level resource limits.

    Reads stdout and stderr in bounded binary chunks (never ``communicate()``
    or a whole ``stdout.read()``) with ``select``-bounded reads so
    ``MAX_SEARCH_SECONDS`` is enforced while the process runs, and counts raw
    streamed bytes so ``MAX_RESULT_BYTES`` caps the process output itself.  The
    stderr pipe is drained simultaneously (never left to backpressure) and
    retained only up to ``MAX_SEARCH_STDERR_BYTES`` for error reporting.

    The process is never force-terminated just because its pipes reached EOF:
    a normally exiting child that outlives its last output gets a bounded
    natural ``wait`` for its own exit.  Only a result limit, an output-byte
    limit, or the deadline may force termination, and the caller only accepts
    a forced exit whose return code matches the signal the helper actually
    sent.  A returning ``_terminate_and_reap_search_process`` of
    ``already_exited`` is classified by the natural return-code rules instead.
    A genuine ripgrep failure (exit code outside the normal 0=matches /
    1=no-matches contract, an unforced signal exit, or a cleanup failure)
    raises ``RuntimeError`` and is never masked by the Python fallback or by a
    truncated-read state.
    """
    process = subprocess.Popen(
        [
            executable,
            "-n",
            "--fixed-strings",
            "--no-heading",
            "--color",
            "never",
            "--with-filename",
            "--max-count",
            str(MAX_SEARCH_RESULTS),
            "--",
            pattern,
            relative,
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    stdout_fd = process.stdout.fileno()
    stderr_fd = process.stderr.fileno()
    deadline = time.monotonic() + MAX_SEARCH_SECONDS
    matches: list[str] = []
    raw_output_bytes = 0
    truncated = False
    rejected_match_line = False
    line_buffer = bytearray()
    stderr_bytes = bytearray()
    stderr_overflow = False
    forced_termination = False
    termination_reason: str | None = None
    termination_method: str | None = None
    stdout_open = True
    stderr_open = True
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                returncode = process.poll()
                if returncode is not None:
                    process.wait()
                    break
                truncated = True
                forced_termination = True
                termination_reason = "deadline"
                break
            if len(matches) >= MAX_SEARCH_RESULTS:
                truncated = True
                forced_termination = True
                termination_reason = "result_limit"
                break
            if raw_output_bytes > MAX_RESULT_BYTES:
                truncated = True
                forced_termination = True
                termination_reason = "output_byte_limit"
                break
            active_fds: list[int] = []
            if stdout_open:
                active_fds.append(stdout_fd)
            if stderr_open:
                active_fds.append(stderr_fd)
            if not active_fds:
                natural_remaining = max(0.0, deadline - time.monotonic())
                try:
                    process.wait(timeout=natural_remaining)
                except subprocess.TimeoutExpired:
                    truncated = True
                    forced_termination = True
                    termination_reason = "deadline"
                break
            readable, _, _ = select.select(active_fds, [], [], min(remaining, 0.1))
            if not readable:
                continue
            for fd in readable:
                if fd == stdout_fd:
                    try:
                        chunk = os.read(stdout_fd, 64 * 1024)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        stdout_open = False
                        continue
                    raw_output_bytes += len(chunk)
                    if raw_output_bytes > MAX_RESULT_BYTES:
                        truncated = True
                        forced_termination = True
                        termination_reason = "output_byte_limit"
                        break
                    line_buffer.extend(chunk)
                    while b"\n" in line_buffer:
                        raw_line, _, rest = line_buffer.partition(b"\n")
                        line_buffer = bytearray(rest)
                        if rejected_match_line:
                            continue
                        if len(matches) >= MAX_SEARCH_RESULTS:
                            truncated = True
                            rejected_match_line = True
                            continue
                        bounded, line_truncated = _bounded_match_line(
                            raw_line.decode("utf-8", errors="replace")
                        )
                        truncated = truncated or line_truncated
                        matches.append(bounded)
                else:
                    try:
                        chunk = os.read(stderr_fd, 64 * 1024)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        stderr_open = False
                        continue
                    room = MAX_SEARCH_STDERR_BYTES - len(stderr_bytes)
                    if room > 0:
                        stderr_bytes.extend(chunk[:room])
                    if len(chunk) > room:
                        stderr_overflow = True
            if termination_reason is not None:
                break
        if line_buffer and not truncated:
            bounded, line_truncated = _bounded_match_line(
                bytes(line_buffer).decode("utf-8", errors="replace")
            )
            truncated = truncated or line_truncated
            if len(matches) >= MAX_SEARCH_RESULTS:
                truncated = True
            else:
                matches.append(bounded)
        if forced_termination:
            termination_method = _terminate_and_reap_search_process(process)
        else:
            assert process.returncode is not None
    finally:
        for cleanup_stream in (process.stdout, process.stderr):
            try:
                cleanup_stream.close()
            except Exception:
                pass

    stderr_text = stderr_bytes.decode("utf-8", errors="replace")
    if stderr_overflow:
        stderr_text += "[stderr truncated]"
    stderr_text = stderr_text.strip()

    returncode = process.returncode
    if forced_termination:
        if termination_method == "already_exited":
            if returncode not in (0, 1):
                raise RuntimeError(stderr_text or f"search failed (exit {returncode})")
        elif termination_method == "sigterm":
            if returncode != -signal.SIGTERM:
                raise RuntimeError(stderr_text or "search process exited unexpectedly")
        elif termination_method == "sigkill":
            if returncode != -signal.SIGKILL:
                raise RuntimeError(stderr_text or "search process exited unexpectedly")
        else:  # pragma: no cover - defensive; helper only returns documented values
            raise RuntimeError("search process cleanup failed")
    elif returncode not in (0, 1):
        raise RuntimeError(stderr_text or f"search failed (exit {returncode})")
    return matches, truncated


def _loaded_runtime_source_paths() -> tuple[Path, ...]:
    """Collect the Nexus Python modules already loaded inside the canonical repo.

    The comparison set must be frozen at gateway start; later imports of other
    modules must never change it.
    """
    root_resolved = CANONICAL_SOURCE_ROOT.resolve()
    paths: list[Path] = []
    for module in sorted(sys.modules.values(), key=lambda value: str(getattr(value, "__name__", ""))):
        name = str(getattr(module, "__name__", ""))
        if name != "nexus" and not name.startswith("nexus."):
            continue
        file_path = getattr(module, "__file__", None)
        if not file_path:
            continue
        candidate = Path(file_path)
        if candidate.suffix != ".py":
            continue
        if "__pycache__" in candidate.parts or candidate.suffix == ".pyc":
            continue
        if "tests" in candidate.parts:
            continue
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            continue
        paths.append(resolved)
    return tuple(sorted(set(paths), key=lambda path: path.as_posix()))


def _hash_source_paths(paths: tuple[Path, ...], *, root: Path = CANONICAL_SOURCE_ROOT) -> str:
    """Deterministic SHA-256 over relative path + file bytes for a frozen set.

    A missing or unreadable file contributes a distinct marker so any change,
    including deletion, surfaces as runtime source drift.
    """
    root_resolved = root.resolve()
    digest = hashlib.sha256()
    for path in paths:
        resolved = Path(path).resolve()
        try:
            relative = resolved.relative_to(root_resolved)
        except ValueError:
            relative = Path(resolved.name)
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\x00")
        try:
            data = resolved.read_bytes()
        except OSError:
            digest.update(b"\x00missing\x00")
            continue
        digest.update(b"\x00len=%d\x00" % len(data))
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


# Directly define the public action schema or permission semantics.  Implementation
# changes (for example ``_search``) must not alter the action contract fingerprint.
ACTION_CONTRACT_TOP_LEVEL_CONSTANTS = (
    "PERMISSION_POLICY",
    "PERMISSION_POLICY_REVISION",
    "TASK_CONTRACT_REVISION",
    "LIFECYCLE_REVISION",
    "LIFECYCLE_STATE_SCHEMA_REVISION",
)


def _action_contract_digest(source: str) -> Optional[str]:
    """Non-executing AST fingerprint of the public action contract.

    Hashes the assignment expression of each named top-level constant plus the
    body of ``UnifiedMCPGateway.tool_specs``.  Returns ``None`` when the source
    cannot be parsed (fail closed).
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    collected: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            if isinstance(node, ast.Assign):
                targets = node.targets
            else:
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in ACTION_CONTRACT_TOP_LEVEL_CONSTANTS:
                    collected[target.id] = ast.dump(node.value, include_attributes=False)
        elif isinstance(node, ast.ClassDef) and node.name == "UnifiedMCPGateway":
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name == "tool_specs":
                    collected["UnifiedMCPGateway.tool_specs"] = ast.dump(member, include_attributes=False)
    if not collected:
        return None
    digest = hashlib.sha256()
    for key in sorted(collected):
        digest.update(key.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(collected[key].encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _action_contract_fingerprint(
    *,
    root: Path = CANONICAL_SOURCE_ROOT,
    source: Optional[str] = None,
) -> tuple[str, bool, tuple[str, ...]]:
    """Return ``(sha256, ok, reasons)`` for the action contract.

    ``ok=False`` means the contract cannot be evaluated and review must fail
    closed; ``reasons`` carries the explicit cause for ``reload_reasons``.
    """
    if source is None:
        source_path = root / "nexus" / "orchestrator" / "unified_mcp_gateway.py"
        try:
            source = source_path.read_text(encoding="utf-8")
        except OSError as exc:
            return "", False, (f"action_contract_source_unreadable:{exc.__class__.__name__}",)
    digest = _action_contract_digest(source)
    if digest is None:
        return "", False, ("action_contract_source_unparseable",)
    return digest, True, ()


# Modules that define or enforce the permission policy.  Implementation changes
# (for example ``_search``) must never alter the permission enforcement digest.
PERMISSION_ENFORCEMENT_PATHS = (
    "nexus/orchestrator/lifecycle_guards.py",
    "nexus/contracts/lifecycle_action.py",
)


def _permission_enforcement_fingerprint(
    *,
    root: Path = CANONICAL_SOURCE_ROOT,
) -> tuple[str, bool, tuple[str, ...]]:
    """Non-executing AST fingerprint of the permission enforcement surface.

    Hashes the full syntax tree of every module that defines or enforces the
    permission policy without importing or executing them.  ``ok=False`` means
    the enforcement contract cannot be evaluated and permission review must
    fail closed; ``reasons`` carries the explicit cause for ``review_reasons``.
    """
    digest = hashlib.sha256()
    for relative in PERMISSION_ENFORCEMENT_PATHS:
        source_path = root / relative
        try:
            source = source_path.read_text(encoding="utf-8")
        except OSError as exc:
            return "", False, (f"permission_enforcement_source_unreadable:{exc.__class__.__name__}",)
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            return "", False, (f"permission_enforcement_source_unparseable:{relative}",)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(ast.dump(tree, include_attributes=False).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest(), True, ()


def _evaluate_freshness(
    *,
    repo_head_at_start: str,
    repo_head_current: str,
    runtime_sha_at_start: str,
    runtime_sha_current: str,
    action_sha_at_start: str,
    action_sha_current: str,
    permission_sha_at_start: str = "",
    permission_sha_current: str = "",
    action_contract_ok: bool = True,
    action_contract_reasons: tuple[str, ...] = (),
    permission_contract_ok: bool = True,
    permission_contract_reasons: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Derive the freshness semantics for ``nexus_gateway_status``.

    ``repository_drift`` is informational only; only runtime source drift
    triggers ``reload_required``.  ``reload_reasons`` therefore reports the
    runtime reload decision alone (``runtime_source_changed``).  Action
    definition changes, permission enforcement changes, or a fail-closed
    contract evaluation are review-only concerns: they surface only in
    ``review_reasons`` and never in ``reload_reasons``.
    """
    repository_drift = bool(repo_head_at_start != repo_head_current)
    runtime_source_drift = bool(runtime_sha_at_start != runtime_sha_current)
    reload_required = bool(runtime_source_drift)
    action_definition_changed = bool(action_sha_at_start != action_sha_current)
    permission_changed = bool(permission_sha_at_start != permission_sha_current)
    action_definition_review_required = bool(not action_contract_ok or action_definition_changed)
    permission_review_required = bool(not permission_contract_ok or permission_changed)
    action_review_required = bool(action_definition_review_required or permission_review_required)
    reload_reasons: list[str] = []
    review_reasons: list[str] = []
    if not action_contract_ok:
        review_reasons.extend(action_contract_reasons)
    if action_definition_changed:
        review_reasons.append("action_definition_changed")
    if not permission_contract_ok:
        review_reasons.extend(permission_contract_reasons)
    if permission_changed:
        review_reasons.append("permission_enforcement_changed")
    if runtime_source_drift:
        reload_reasons.append("runtime_source_changed")
    return {
        "repository_drift": repository_drift,
        "runtime_source_sha256_at_start": runtime_sha_at_start,
        "runtime_source_sha256_current": runtime_sha_current,
        "runtime_source_drift": runtime_source_drift,
        "action_definition_sha256_at_start": action_sha_at_start,
        "action_definition_sha256_current": action_sha_current,
        "action_contract_sha256_at_start": action_sha_at_start,
        "action_contract_sha256_current": action_sha_current,
        "permission_enforcement_sha256_at_start": permission_sha_at_start,
        "permission_enforcement_sha256_current": permission_sha_current,
        "action_definition_review_required": action_definition_review_required,
        "permission_review_required": permission_review_required,
        "action_review_required": action_review_required,
        "review_reasons": review_reasons,
        "reload_required": reload_required,
        "reload_reasons": reload_reasons,
    }


class UnifiedMCPGateway:
    """JSON-RPC MCP server with one public identity and bounded tools."""

    def __init__(self, service: Optional[SelfHostedTaskService] = None, *, model_runner: Any = None, apply_runner: Any = None):
        self.service = service or SelfHostedTaskService()
        # These kwargs remain accepted for compatibility with older callers,
        # but neither runner is a gateway authority.  Assisted jobs are
        # provider probes/advice only; governed implementation enters through
        # nexus_worker_candidate.
        self._model_runner = self._run_agy_plan
        self._ignored_model_runner = model_runner
        self._ignored_apply_runner = apply_runner
        self._workforce_loader = WorkforcePolicyLoader()
        self._assist_processes: dict[str, subprocess.Popen[str]] = {}
        self._assist_lock = threading.RLock()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _assist_root(self) -> Path:
        configured = getattr(self.service, "state_dir", None)
        root = Path(configured).expanduser().resolve() if configured else Path("/tmp/nexus-mcp-gateway-assist-jobs")
        root = root / "assisted_provider_jobs"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _assist_path(self, task_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", str(task_id)):
            raise GatewayInputError("task_id must be a stable bounded slug")
        return self._assist_root() / f"{task_id}.json"

    def _probe_evidence_root(self) -> Path:
        root = self._assist_root() / "probe_evidence"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _probe_evidence_read_root(self) -> Path:
        configured = getattr(self.service, "state_dir", None)
        base = Path(configured).expanduser().resolve() if configured else Path("/tmp/nexus-mcp-gateway-assist-jobs")
        return base / "assisted_provider_jobs" / "probe_evidence"

    def _assist_read_root(self) -> Path:
        """Return the evidence root without creating any filesystem state."""
        configured = getattr(self.service, "state_dir", None)
        base = Path(configured).expanduser().resolve() if configured else Path("/tmp/nexus-mcp-gateway-assist-jobs")
        return base / "assisted_provider_jobs"

    @staticmethod
    def _canonical_hash(value: Any) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

    @staticmethod
    def _provider_requires_authentication(provider: str) -> bool:
        key = str(provider or "").strip().lower()
        return key in ONLINE_CLI_SPEC_REGISTRY and key not in LOCAL_ONLY_PROVIDERS

    def _provider_execution_ready(
        self,
        preflight: Mapping[str, Any],
        *,
        provider: str,
        model: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        if preflight.get("provider") != provider:
            return False, "WORKER_PREFLIGHT_PROVIDER_MISMATCH"
        if model is not None and preflight.get("requested_model") != model:
            return False, "WORKER_PREFLIGHT_REQUESTED_MODEL_MISMATCH"
        if model is not None and preflight.get("resolved_model") != model:
            return False, "WORKER_PREFLIGHT_RESOLVED_MODEL_MISMATCH"
        if str(preflight.get("status") or "") != "VERSION_VERIFIED":
            return False, str(preflight.get("blocker") or "WORKER_PREFLIGHT_FAILED")
        blocker = str(preflight.get("blocker") or "")
        if blocker in {"MODEL_PROBE_REQUIRED", "MODEL_PROBE_ASYNC_REQUIRED"}:
            return False, blocker
        if preflight.get("readiness_status") != "MODEL_VERIFIED" or preflight.get("execution_ready") is not True:
            return False, "MODEL_PROBE_REQUIRED"
        if preflight.get("model_reachable") is not True or preflight.get("requested_model_verified") is not True:
            return False, "MODEL_PROBE_REQUIRED"
        required_identity = (
            "probe_evidence_hash",
            "binary_path",
            "binary_sha256",
            "cli_version_sha256",
            "probe_expires_at",
        )
        if any(not preflight.get(field) for field in required_identity):
            return False, "MODEL_PROBE_REQUIRED"
        if self._provider_requires_authentication(provider):
            if (
                preflight.get("authenticated") is not True
                or preflight.get("authentication_evidence") != "successful_exact_model_probe"
            ):
                return False, "PROVIDER_AUTHENTICATION_REQUIRED"
        return True, None

    def _assist_read(self, task_id: str) -> Optional[dict[str, Any]]:
        path = self._assist_path(task_id)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _assist_read_snapshot(self, task_id: str) -> Optional[dict[str, Any]]:
        """Read a persisted job without creating the state root."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", str(task_id)):
            return None
        path = self._assist_read_root() / f"{task_id}.json"
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _assist_write(self, value: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _text(value.get("task_id"), "task_id")
        path = self._assist_path(task_id)
        serialized = json.dumps(dict(value), sort_keys=True, ensure_ascii=False, indent=2) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(serialized)
            temporary = Path(handle.name)
        os.replace(temporary, path)
        return dict(value)

    @classmethod
    def _probe_evidence_identity(cls, values: Mapping[str, Any]) -> str:
        identity = {
            key: values.get(key)
            for key in (
                "provider",
                "requested_model",
                "resolved_model",
                "binary_path",
                "binary_sha256",
                "cli_version",
            )
        }
        return cls._canonical_hash(identity)

    def _write_probe_evidence(self, job: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        if job.get("job_kind") != "model_probe" or job.get("status") != "COMPLETED":
            return None
        required = (
            "task_id",
            "job_id",
            "provider",
            "requested_model",
            "resolved_model",
            "binary_path",
            "binary_sha256",
            "cli_version",
            "cli_version_sha256",
            "command_hash",
            "probe_prompt_hash",
            "probe_semantics_hash",
            "action_request_hash",
            "action_id",
            "attempt_id",
            "result",
            "output_schema",
            "finished_at",
            "stdout_sha256",
            "stderr_sha256",
            "stdout_bytes",
            "stderr_bytes",
            "filesystem_delta",
            "process_cleanup",
            "durable_exit_marker",
            "stream_flush_status",
            "workspace_mode",
            "model_response_provenance",
            "submitted_at",
            "started_at",
        )
        if any(job.get(key) in (None, "") for key in required) or job.get("exit_code") != 0:
            return None
        if (
            job.get("model_response_verified") is not True
            or job.get("durable_exit_marker") is not True
            or job.get("process_cleanup") is not True
            or job.get("filesystem_delta") != {"created": [], "removed": [], "changed": []}
            or job.get("schema_error") not in (None, "")
            or job.get("stream_flush_status") != "FLUSHED"
            or job.get("workspace_mode") != "isolated"
            or not self._probe_command_identity_valid(job)
        ):
            return None
        remote_authentication = self._provider_requires_authentication(str(job.get("provider") or ""))
        payload = {
            key: job.get(key)
            for key in required
            if key not in {"result", "output_schema"}
        }
        payload.update({
            "schema": "nexus.model_probe_evidence.v1",
            "status": "SUCCESS",
            "model_response_verified": True,
            # Authentication is inferred only from a successful exact remote
            # model response, never from provider metadata or --version.
            "authenticated": remote_authentication,
            "authentication_evidence": (
                "successful_exact_model_probe"
                if remote_authentication
                else "local_provider_no_auth_required"
            ),
            "exit_code": 0,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        })
        payload["output_schema_hash"] = self._canonical_hash(job.get("output_schema"))
        payload["result_hash"] = self._canonical_hash(job.get("result"))
        trust = {key: value for key, value in payload.items() if key != "evidence_hash"}
        payload["evidence_hash"] = self._canonical_hash(trust)
        identity = self._probe_evidence_identity(payload)
        path = self._probe_evidence_root() / f"{identity}.json"
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(serialized)
            temporary = Path(handle.name)
        os.replace(temporary, path)
        return payload

    def _read_probe_evidence(self, *, provider: str, requested_model: str, resolved_model: str, executable: str, binary_sha256: str, cli_version: str) -> Optional[dict[str, Any]]:
        root = self._probe_evidence_read_root()
        if not root.exists():
            return None
        identity_values = {
            "provider": provider,
            "requested_model": requested_model,
            "resolved_model": resolved_model,
            "binary_path": executable,
            "binary_sha256": binary_sha256,
            "cli_version": cli_version,
        }
        path = root / f"{self._probe_evidence_identity(identity_values)}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            expires_at = datetime.fromisoformat(str(value.get("expires_at")))
            finished_at = datetime.fromisoformat(str(value.get("finished_at")))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None
        now = datetime.now(timezone.utc)
        if expires_at.tzinfo is None or finished_at.tzinfo is None:
            return None
        if (
            finished_at > now + timedelta(minutes=1)
            or expires_at <= now
            or expires_at <= finished_at
            or expires_at - finished_at > timedelta(hours=1, minutes=1)
        ):
            return None
        if value.get("status") != "SUCCESS" or value.get("model_response_verified") is not True:
            return None
        if any(value.get(key) != expected for key, expected in identity_values.items()):
            return None
        if value.get("cli_version_sha256") != hashlib.sha256(cli_version.encode("utf-8")).hexdigest():
            return None
        digest = value.get("evidence_hash")
        trust = {key: item for key, item in value.items() if key != "evidence_hash"}
        if not digest or self._canonical_hash(trust) != digest:
            return None
        job = self._assist_read_snapshot(str(value.get("task_id")))
        matched_fields = (
            "job_id",
            "action_id",
            "attempt_id",
            "command_hash",
            "probe_prompt_hash",
            "probe_semantics_hash",
            "action_request_hash",
            "submitted_at",
            "started_at",
            "provider",
            "requested_model",
            "resolved_model",
            "binary_path",
            "binary_sha256",
            "cli_version",
            "cli_version_sha256",
            "finished_at",
            "stdout_sha256",
            "stderr_sha256",
            "stdout_bytes",
            "stderr_bytes",
            "filesystem_delta",
            "process_cleanup",
            "durable_exit_marker",
            "model_response_verified",
            "model_response_provenance",
            "stream_flush_status",
            "workspace_mode",
        )
        if job is None or any(job.get(key) != value.get(key) for key in matched_fields):
            return None
        if (
            job.get("status") != "COMPLETED"
            or job.get("exit_code") != 0
            or job.get("durable_exit_marker") is not True
            or job.get("process_cleanup") is not True
            or job.get("model_response_verified") is not True
            or not job.get("model_response_provenance")
            or job.get("filesystem_delta") != {"created": [], "removed": [], "changed": []}
            or value.get("exit_code") != 0
            or not self._probe_command_identity_valid(job)
            or value.get("output_schema_hash") != self._canonical_hash(job.get("output_schema"))
            or value.get("result_hash") != self._canonical_hash(job.get("result"))
        ):
            return None
        for name in ("stdout", "stderr"):
            artifact = Path(str(job.get(f"{name}_artifact") or ""))
            try:
                if (
                    not artifact.is_file()
                    or artifact.resolve().parent != self._assist_read_root().resolve()
                    or self._hash_file(artifact) != job.get(f"{name}_sha256")
                    or artifact.stat().st_size != job.get(f"{name}_bytes")
                ):
                    return None
            except OSError:
                return None
        if job.get("schema_error") not in (None, "") or job.get("stream_flush_status") != "FLUSHED":
            return None
        if self._provider_requires_authentication(provider):
            if value.get("authenticated") is not True or value.get("authentication_evidence") != "successful_exact_model_probe":
                return None
        return value

    @staticmethod
    def _assist_command(*, executable: str, provider: str, model: str, prompt: str, explicit_effort: str = "") -> list[str]:
        if provider == "cline":
            selected = model or "glm-5.2"
            if "/" not in selected:
                selected = f"cline-pass/{selected}"
            return [executable, "--json", "--plan", "--auto-approve", "false", "--thinking", "none", "--timeout", str(CLINE_RUN_TIMEOUT_SECONDS), "--model", selected, prompt]
        if provider == "agy":
            return _compile_agy_command(executable=executable, model=model, prompt=prompt, explicit_effort=explicit_effort)
        if provider == "gemini":
            return [executable, "--skip-trust", "--approval-mode", "auto_edit", "-m", model, "-p", prompt, "--output-format", "json"]
        if provider == "opencode":
            return [executable, "run", "--model", model, prompt]
        if provider == "mimo":
            return [executable, "run", "--never-ask-questions", "--model", model, prompt]
        if provider == "ollama":
            return [executable, "run", model, prompt]
        if provider == "grok":
            return [executable, "--model", model, "--single", prompt, "--output-format", "json", "--no-alt-screen"]
        if provider == "codex":
            return [executable, "exec", "--json", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", "-m", model, prompt]
        raise GatewayInputError("ASSIST_ASYNC_PROVIDER_UNSUPPORTED")

    @classmethod
    def _probe_command_identity_valid(cls, job: Mapping[str, Any]) -> bool:
        command = job.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
            return False
        if command[0] != job.get("binary_path"):
            return False
        command_hash = hashlib.sha256(
            json.dumps(command, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if command_hash != job.get("command_hash"):
            return False
        provider = str(job.get("provider") or "")
        expected_model = str(job.get("resolved_model") or "")
        try:
            if provider in {"cline", "agy", "opencode", "mimo", "grok"}:
                model_value = command[command.index("--model") + 1]
            elif provider in {"codex", "gemini"}:
                model_value = command[command.index("-m") + 1]
            elif provider == "ollama":
                model_value = command[2]
            else:
                return False
            if model_value != expected_model:
                return False
            if provider == "agy":
                prompt = command[command.index("--prompt") + 1]
            elif provider == "gemini":
                prompt = command[command.index("-p") + 1]
            else:
                prompt = command[-1]
        except (ValueError, IndexError):
            return False
        return cls._canonical_hash(prompt) == job.get("probe_prompt_hash")

    @staticmethod
    def _decode_model_probe_payload(text: str, provider: str, resolved_model: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        """Return only a model-originated JSON payload, never transport metadata."""

        def decode_document(raw: str) -> Optional[dict[str, Any]]:
            try:
                value = json.loads(raw.strip())
            except (json.JSONDecodeError, TypeError):
                return None
            return value if isinstance(value, dict) else None

        stripped = text.strip()
        direct = decode_document(stripped)
        transport_types = {
            "run_start",
            "run_result",
            "item.started",
            "item.completed",
            "agent_message",
            "thread.started",
            "turn.started",
            "turn.completed",
        }
        if provider not in {"cline", "codex"} and direct is not None and direct.get("type") not in transport_types:
            return direct, "direct_json_document"

        events: list[dict[str, Any]] = []
        for line in text.splitlines():
            value = decode_document(line)
            if value is not None:
                events.append(value)
        if provider == "codex":
            event_types = [str(event.get("type") or "") for event in events]
            try:
                thread_index = event_types.index("thread.started")
                turn_index = event_types.index("turn.started", thread_index + 1)
                completed_index = event_types.index("turn.completed", turn_index + 1)
            except ValueError:
                return None, None
            for event in reversed(events[turn_index + 1 : completed_index]):
                if event.get("type") != "item.completed":
                    continue
                item = event.get("item") if isinstance(event.get("item"), Mapping) else event
                if item.get("type") != "agent_message" or not isinstance(item.get("text"), str):
                    continue
                payload = decode_document(item["text"])
                if payload is not None:
                    return payload, "codex_jsonl_sequence"
            return None, None
        if provider == "cline":
            start_indices = [
                index
                for index, event in enumerate(events)
                if (
                event.get("type") == "run_start"
                and event.get("providerId") == "cline"
                and event.get("modelId") == resolved_model
                )
            ]
            if not start_indices:
                return None, None
            for event in reversed(events[start_indices[-1] + 1 :]):
                if event.get("type") != "run_result" or str(event.get("finishReason") or "").lower() == "error":
                    continue
                model = event.get("model") if isinstance(event.get("model"), Mapping) else {}
                if (
                    str(model.get("provider") or "") != "cline"
                    or str(model.get("id") or "") != resolved_model
                    or not isinstance(event.get("text"), str)
                ):
                    continue
                payload = decode_document(event["text"])
                if payload is not None:
                    return payload, "cline_run_result"
            return None, None
        return None, None

    @staticmethod
    def _decode_assist_payload(text: str, provider: str, *, require_patch: bool = False) -> Optional[dict[str, Any]]:
        decoder = json.JSONDecoder()
        candidates: list[Any] = []
        stripped = text.strip()
        if stripped:
            try:
                candidates.append(json.loads(stripped))
            except json.JSONDecodeError:
                pass
        for line in reversed(text.splitlines()):
            try:
                candidates.append(json.loads(line))
            except json.JSONDecodeError:
                pass

        # Cline emits JSON events, and some versions wrap the event stream in
        # an array.  Extract complete JSON values instead of using a greedy
        # object regex, which can join unrelated log objects together.
        if provider == "cline":
            for index, char in enumerate(text):
                if char not in "[{":
                    continue
                try:
                    value, _ = decoder.raw_decode(text[index:])
                except json.JSONDecodeError:
                    continue
                candidates.append(value)

        def visit(value: Any) -> Optional[dict[str, Any]]:
            if isinstance(value, dict):
                if "patch" in value:
                    return value
                # Codex JSONL wraps the model payload in an agent_message
                # event whose text field is itself JSON.  Decode that inner
                # value instead of treating the transport envelope as the
                # probe result.
                if provider == "codex" and value.get("type") == "agent_message" and isinstance(value.get("text"), str):
                    nested = UnifiedMCPGateway._decode_assist_payload(value["text"], provider, require_patch=require_patch)
                    if nested is not None:
                        return nested
                if provider == "codex" and isinstance(value.get("item"), Mapping):
                    nested = visit(value["item"])
                    if nested is not None:
                        return nested
                if not require_patch:
                    return value
                # These are the documented/observed Cline envelope fields.
                # Preserve event order and inspect the final content first.
                nested_values: list[Any] = []
                for key in ("text", "content", "message", "result", "output", "data", "event", "payload"):
                    if key in value:
                        nested_values.append(value[key])
                for nested in reversed(nested_values):
                    if isinstance(nested, str) and nested.strip():
                        found = UnifiedMCPGateway._decode_assist_payload(nested, provider, require_patch=require_patch)
                    else:
                        found = visit(nested)
                    if found is not None:
                        return found
                return None if require_patch or provider == "cline" else value
            if isinstance(value, list):
                for item in reversed(value):
                    found = visit(item)
                    if found is not None:
                        return found
            return None

        for candidate in candidates:
            found = visit(candidate)
            if found is not None:
                return found
        return None

    @staticmethod
    def _snapshot_workspace(root: Path) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        if not root.exists():
            return snapshot
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            try:
                snapshot[str(path.relative_to(root))] = UnifiedMCPGateway._hash_file(path)
            except OSError:
                snapshot[str(path.relative_to(root))] = "unreadable"
        return snapshot

    @staticmethod
    def _validate_output_schema(value: Any, schema: Any) -> tuple[bool, str]:
        if not isinstance(schema, Mapping):
            return True, ""
        def validate(current: Any, shape: Mapping[str, Any], path: str = "$") -> str:
            expected = shape.get("type")
            type_ok = {
                "object": lambda x: isinstance(x, Mapping),
                "array": lambda x: isinstance(x, list),
                "string": lambda x: isinstance(x, str),
                "number": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool),
                "integer": lambda x: isinstance(x, int) and not isinstance(x, bool),
                "boolean": lambda x: isinstance(x, bool),
                "null": lambda x: x is None,
            }
            if expected in type_ok and not type_ok[expected](current):
                return f"output_schema_type:{path}:{expected}"
            if "enum" in shape and current not in shape.get("enum", []):
                return f"output_schema_enum:{path}"
            if isinstance(current, Mapping):
                missing = [str(field) for field in shape.get("required", []) or [] if str(field) not in current]
                if missing:
                    return "output_schema_missing:" + ",".join(f"{path}.{field}" for field in missing)
                properties = shape.get("properties") if isinstance(shape.get("properties"), Mapping) else {}
                for key, child in properties.items():
                    if key in current and isinstance(child, Mapping):
                        error = validate(current[key], child, f"{path}.{key}")
                        if error:
                            return error
                if shape.get("additionalProperties") is False:
                    extras = sorted(set(current) - set(properties))
                    if extras:
                        return f"output_schema_additional:{path}:{','.join(map(str, extras))}"
            if isinstance(current, list) and isinstance(shape.get("items"), Mapping):
                for index, item in enumerate(current):
                    error = validate(item, shape["items"], f"{path}[{index}]")
                    if error:
                        return error
            return ""

        error = validate(value, schema)
        return (not bool(error), error)

    def _assist_refresh(self, task_id: str) -> Optional[dict[str, Any]]:
        job = self._assist_read(task_id)
        if job is None:
            return None
        if job.get("status") in {"COMPLETED", "FAILED", "CANCELLED"}:
            return job
        with self._assist_lock:
            process = self._assist_processes.get(task_id)
        returncode = process.poll() if process is not None else None
        if process is not None and returncode is not None:
            job["durable_exit_marker"] = True
            job["durable_exit_code"] = returncode
        if process is None and job.get("pid"):
            try:
                os.kill(int(job["pid"]), 0)
                return job
            except (OSError, ValueError):
                # A restarted Gateway may retain artifacts but no durable exit
                # marker.  Output alone is not completion evidence: fail closed
                # and require an explicit reconciliation decision.
                if not job.get("durable_exit_marker"):
                    job.update({
                        "status": "UNKNOWN_REQUIRES_RECONCILE",
                        "blocker": "ASSIST_PROVIDER_PROCESS_LOST",
                        "reconciliation_required": True,
                        "last_polled_at": self._utc_now(),
                    })
                    return self._assist_write(job)
                returncode = job.get("exit_code")
        if returncode is None:
            job["status"] = "RUNNING"
            job["last_polled_at"] = self._utc_now()
            return self._assist_write(job)
        stdout_path = Path(str(job.get("stdout_artifact") or ""))
        stderr_path = Path(str(job.get("stderr_artifact") or ""))
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
        is_model_probe = str(job.get("job_kind") or "assist") == "model_probe"
        response_provenance: Optional[str] = None
        if is_model_probe:
            parsed, response_provenance = self._decode_model_probe_payload(
                stdout,
                str(job.get("provider") or ""),
                str(job.get("resolved_model") or ""),
            )
        else:
            parsed = self._decode_assist_payload(
                stdout,
                str(job.get("provider") or ""),
                require_patch=True,
            )
        schema_valid, schema_error = self._validate_output_schema(parsed, job.get("output_schema"))
        started_at = job.get("started_at")
        provider_time_ms = 0
        if started_at:
            try:
                provider_time_ms = max(0, int((time.time() - datetime.fromisoformat(str(started_at)).timestamp()) * 1000))
            except (TypeError, ValueError):
                provider_time_ms = 0
        model_response_verified = bool(
            is_model_probe
            and returncode == 0
            and parsed is not None
            and schema_valid
            and response_provenance
        )
        provider_error_sha256 = hashlib.sha256(stderr.encode("utf-8")).hexdigest() if returncode != 0 and stderr else None
        job.update({
            "status": "COMPLETED" if returncode == 0 and parsed is not None and schema_valid else "FAILED",
            "finished_at": self._utc_now(),
            "exit_code": returncode,
            "result": parsed,
            "model_response_verified": model_response_verified,
            "model_response_provenance": response_provenance,
            "blocker": ("ASSIST_PROVIDER_MALFORMED_OUTPUT" if returncode == 0 and (parsed is None or not schema_valid) else ("ASSIST_PROVIDER_FAILED" if returncode != 0 else None)),
            "schema_error": schema_error,
            "schema_validation_level": "bounded_subset",
            "provider_error": "provider process failed" if returncode != 0 else "",
            "provider_error_sha256": provider_error_sha256,
            "provider_time_ms": provider_time_ms,
        })
        self._assist_record_stream_artifacts(job)
        workspace_root = Path(str(job.get("workspace_root") or ""))
        if workspace_root.exists() and workspace_root != CANONICAL_SOURCE_ROOT:
            after = self._snapshot_workspace(workspace_root)
            before = job.get("filesystem_before") if isinstance(job.get("filesystem_before"), Mapping) else {}
            job["filesystem_after"] = after
            job["filesystem_delta"] = {
                "created": sorted(set(after) - set(before)),
                "removed": sorted(set(before) - set(after)),
                "changed": sorted(path for path in set(before) & set(after) if before[path] != after[path]),
            }
            try:
                shutil.rmtree(workspace_root)
                job["process_cleanup"] = True
            except OSError as exc:
                job["process_cleanup"] = False
                job["cleanup_error"] = str(exc)
        with self._assist_lock:
            self._assist_processes.pop(task_id, None)
        evidence = self._write_probe_evidence(job)
        if evidence is not None:
            job["probe_evidence_hash"] = evidence["evidence_hash"]
            job["probe_expires_at"] = evidence["expires_at"]
            job["authentication_evidence"] = evidence["authentication_evidence"]
            identity = self._probe_evidence_identity(evidence)
            job["probe_evidence_path"] = str(self._probe_evidence_read_root() / (identity + ".json"))
        return self._assist_write(job)

    @staticmethod
    def _assist_action(job: Mapping[str, Any]) -> dict[str, Any]:
        """Project one Assisted job into current action and pending-count state."""
        status = str(job.get("status") or "UNKNOWN")
        terminal = status in {"COMPLETED", "FAILED", "CANCELLED"}
        reconciliation_required = status == "UNKNOWN_REQUIRES_RECONCILE" or bool(job.get("reconciliation_required"))
        cleanup_settled = job.get("process_cleanup") is True and not job.get("cleanup_error")
        settled_failure = (
            status in {"FAILED", "CANCELLED"}
            and not reconciliation_required
            and cleanup_settled
            and job.get("durable_exit_marker") is True
            and not job.get("uncertain_mutation")
        )
        if status == "UNKNOWN_REQUIRES_RECONCILE":
            next_action = "nexus_task_reconcile"
        else:
            result_tool = "nexus_model_probe_result" if str(job.get("job_kind") or "assist") == "model_probe" else "nexus_assist_result"
            next_action = result_tool if not terminal else ("none" if status == "COMPLETED" else "nexus_task_retry")
        return {
            "attention_required": status == "UNKNOWN_REQUIRES_RECONCILE" or (status in {"FAILED", "CANCELLED"} and not settled_failure),
            "next_action": next_action,
            "recommended_tool": next_action,
            "pending": not terminal or status == "UNKNOWN_REQUIRES_RECONCILE",
        }

    def _assist_response(self, job: Mapping[str, Any], *, operation: str = "status") -> dict[str, Any]:
        status = str(job.get("status") or "UNKNOWN")
        action = self._assist_action(job)
        return {
            "schema": "nexus.assisted_provider_job.v1",
            "operation": operation,
            "task_id": job.get("task_id"),
            "job_id": job.get("job_id"),
            "action_id": job.get("action_id"),
            "attempt_id": job.get("attempt_id"),
            "attempt_history": job.get("attempt_history", []),
            "status": status,
            "execution_lane": "ASSISTED_CANONICAL",
            "candidate_only": True,
            "apply_requested": bool(job.get("apply_requested")),
            "apply_ignored": bool(job.get("apply_ignored", False)),
            "provider": job.get("provider"),
            "model": job.get("model"),
            "command_hash": job.get("command_hash"),
            "job_kind": job.get("job_kind", "assist"),
            "workspace_mode": job.get("workspace_mode", "isolated"),
            "workspace_root": job.get("workspace_root"),
            "pid": job.get("pid"),
            "pgid": job.get("pgid"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "exit_code": job.get("exit_code"),
            "provider_time_ms": job.get("provider_time_ms", 0),
            "provider_started": bool(job.get("started_at")),
            "binary_exec_started": job.get("started_at"),
            "last_stdout_at": job.get("last_stdout_at"),
            "last_stderr_at": job.get("last_stderr_at"),
            "stdout_sha256": job.get("stdout_sha256"),
            "stderr_sha256": job.get("stderr_sha256"),
            "stdout_bytes": job.get("stdout_bytes"),
            "stderr_bytes": job.get("stderr_bytes"),
            "model_response_verified": bool(job.get("model_response_verified", False)),
            "probe_evidence_hash": job.get("probe_evidence_hash"),
            "probe_expires_at": job.get("probe_expires_at"),
            "authentication_evidence": job.get("authentication_evidence"),
            "durable_exit_marker": bool(job.get("durable_exit_marker", False)),
            "reconciliation_required": bool(job.get("reconciliation_required", False)),
            "uncertain_mutation": bool(job.get("uncertain_mutation", False)),
            "context_arm": job.get("context_arm"),
            "context_arm_applied": bool(job.get("context_arm_applied", False)),
            "context_arm_semantics": job.get("context_arm_semantics", "record_only_not_applied"),
            "result": job.get("result") if status == "COMPLETED" else None,
            "blocker": job.get("blocker"),
            "provider_error": job.get("provider_error", ""),
            "provider_error_sha256": job.get("provider_error_sha256"),
            "schema_error": job.get("schema_error", ""),
            "schema_validation_level": job.get("schema_validation_level", "bounded_subset"),
            "requested_tools_policy": job.get("requested_tools_policy", []),
            "tool_policy_enforcement": job.get("tool_policy_enforcement", "not_enforced"),
            "filesystem_delta": job.get("filesystem_delta", {"created": [], "removed": [], "changed": []}),
            "process_cleanup": job.get("process_cleanup", False),
            "process_killed": bool(job.get("process_killed", False)),
            "stream_flush_status": job.get("stream_flush_status", "not_observed"),
            "connector_disconnected_at": job.get("connector_disconnected_at"),
            "reconnected_at": job.get("reconnected_at"),
            "artifacts": {"stdout": job.get("stdout_artifact"), "stderr": job.get("stderr_artifact")},
            "attention_required": action["attention_required"],
            "next_action": action["next_action"],
            "recommended_tool": action["recommended_tool"],
        }

    def _assist_submit(self, arguments: Mapping[str, Any], *, action: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        task_id = self._task_id(arguments, str(arguments.get("what") or "assist"), str(arguments.get("why") or "assist"), [str(path) for path in arguments.get("allowed_files") or []])
        existing = self._assist_read(task_id)
        if existing is not None:
            return self._assist_response(self._assist_refresh(task_id) or existing, operation="submit")
        provider = str(arguments.get("provider") or arguments.get("preferred_worker") or "cline").strip().lower()
        model = str(arguments.get("model") or arguments.get("preferred_model") or "glm-5.2").strip()
        if provider != "cline":
            raise GatewayInputError("ASSIST_ASYNC_PROVIDER_UNSUPPORTED")
        metadata = ONLINE_CLI_SPEC_REGISTRY.get(provider)
        if metadata is None:
            raise GatewayInputError("ASSIST_PROVIDER_NOT_REGISTERED")
        binary_env = metadata.get("binary_env", "")
        configured = os.environ.get(binary_env, "").strip() if binary_env else ""
        executable = configured or shutil.which(metadata.get("binary_name", provider))
        if not executable or not Path(executable).is_file():
            raise GatewayInputError("ASSIST_PROVIDER_UNAVAILABLE")
        allowed = [str(path).strip() for path in arguments.get("allowed_files") or [] if str(path).strip()]
        if not allowed or len(allowed) > 4:
            raise GatewayInputError("allowed_files must contain 1-4 bounded paths")
        for path in allowed:
            _safe_relative_path(path, "allowed_files")
        prompt = self._assist_prompt(str(arguments.get("what") or "assist"), str(arguments.get("why") or "assist"), allowed, list(arguments.get("verifier_commands") or ["git diff --check"]))
        command = self._assist_command(executable=executable, provider=provider, model=model, prompt=prompt)
        job_id = f"assist-{uuid4().hex}"
        root = self._assist_root()
        stdout_path = root / f"{job_id}.stdout"
        stderr_path = root / f"{job_id}.stderr"
        workspace_root = Path(tempfile.mkdtemp(prefix=f"nexus-assist-{task_id}-", dir="/tmp"))
        action_value = dict(action or {})
        if not action_value:
            base = _git("rev-parse", "HEAD").strip()
            action_value = build_action_envelope(
                task_id=task_id,
                action_type=LifecycleActionType.TASK_RUN,
                request={
                    "task_id": task_id,
                    "what": str(arguments.get("what") or "assist"),
                    "why": str(arguments.get("why") or "assist"),
                    "allowed_files": allowed,
                    "apply": False,
                },
                tool_manifest_hash=TOOL_MANIFEST_REVISION,
                expected_head=base,
                allowed_paths=allowed,
                mutation=False,
                permission_profile=PermissionProfile.VERIFY,
            ).model_dump(mode="json")
        now = self._utc_now()
        job: dict[str, Any] = {
            "schema": "nexus.assisted_provider_job.v1",
            "job_kind": "assist",
            "task_id": task_id,
            "job_id": job_id,
            "attempt_history": [],
            "action_id": action_value.get("action_id") or f"action-{uuid4().hex}",
            "attempt_id": action_value.get("attempt_id") or f"attempt-{uuid4().hex}",
            "status": "SUBMITTED",
            "execution_lane": "ASSISTED_CANONICAL",
            "candidate_only": True,
            # ``apply`` is a legacy compatibility input.  It is deliberately
            # not carried into execution or authority receipts.
            "apply_requested": False,
            "apply_ignored": bool(arguments.get("apply", False)),
            "workspace_mode": "isolated",
            "workspace_root": str(workspace_root),
            "filesystem_before": self._snapshot_workspace(workspace_root),
            "filesystem_after": None,
            "filesystem_delta": {"created": [], "removed": [], "changed": []},
            "process_cleanup": False,
            "output_schema": {"type": "object", "required": ["patch"]},
            "result_artifact": str(self._assist_path(task_id)),
            "provider": provider,
            "model": model if "/" in model else f"cline-pass/{model}",
            "command_hash": hashlib.sha256(json.dumps(command, separators=(",", ":")).encode("utf-8")).hexdigest(),
            "command": command,
            "submitted_at": now,
            "started_at": None,
            "finished_at": None,
            "provider_time_ms": 0,
            "stdout_artifact": str(stdout_path),
            "stderr_artifact": str(stderr_path),
            "action": action_value,
            "connector_disconnected_at": None,
            "reconnected_at": None,
        }
        self._assist_write(job)
        started = time.perf_counter()
        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(command, cwd=workspace_root, stdout=stdout_handle, stderr=stderr_handle, text=True, start_new_session=True)
        except Exception:
            stdout_handle.close()
            stderr_handle.close()
            shutil.rmtree(workspace_root, ignore_errors=True)
            job.update({"status": "FAILED", "finished_at": self._utc_now(), "blocker": "ASSIST_PROVIDER_FAILED", "provider_error": "provider process could not start"})
            return self._assist_response(self._assist_write(job), operation="submit")
        stdout_handle.close()
        stderr_handle.close()
        job.update({"status": "RUNNING", "pid": process.pid, "pgid": process.pid, "started_at": self._utc_now(), "provider_start_ms": max(0, int((time.perf_counter() - started) * 1000))})
        with self._assist_lock:
            self._assist_processes[task_id] = process
        return self._assist_response(self._assist_write(job), operation="submit")

    def _assist_wait(self, task_id: str, *, timeout_seconds: float = 10.0, poll_interval_seconds: float = 0.25) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.0, min(60.0, timeout_seconds))
        while True:
            job = self._assist_refresh(task_id)
            if job is None:
                raise KeyError(f"unknown task_id: {task_id}")
            response = self._assist_response(job, operation="wait")
            if response["status"] in {"COMPLETED", "FAILED", "CANCELLED", "UNKNOWN_REQUIRES_RECONCILE"} or time.monotonic() >= deadline:
                return response
            time.sleep(max(0.01, min(5.0, poll_interval_seconds)))

    def _cleanup_assist_workspace(self, job: dict[str, Any]) -> None:
        workspace_root = Path(str(job.get("workspace_root") or ""))
        if not workspace_root.exists() or workspace_root == CANONICAL_SOURCE_ROOT:
            job["process_cleanup"] = workspace_root == CANONICAL_SOURCE_ROOT or not workspace_root.exists()
            return
        after = self._snapshot_workspace(workspace_root)
        before = job.get("filesystem_before") if isinstance(job.get("filesystem_before"), Mapping) else {}
        job["filesystem_after"] = after
        job["filesystem_delta"] = {
            "created": sorted(set(after) - set(before)),
            "removed": sorted(set(before) - set(after)),
            "changed": sorted(path for path in set(before) & set(after) if before[path] != after[path]),
        }
        try:
            shutil.rmtree(workspace_root)
            job["process_cleanup"] = True
        except OSError as exc:
            job["process_cleanup"] = False
            job["cleanup_error"] = str(exc)

    @staticmethod
    def _assist_record_stream_artifacts(job: dict[str, Any]) -> None:
        """Record flushed stdout/stderr evidence after the child has exited.

        Cancellation must not report cleanup closure while leaving the durable
        receipt without the bytes that were already emitted.  Reading after a
        bounded wait/reap makes the hashes an observation of the final files,
        not a promise that the provider completed successfully.
        """
        streams = {
            "stdout": Path(str(job.get("stdout_artifact") or "")),
            "stderr": Path(str(job.get("stderr_artifact") or "")),
        }
        complete = True
        for name, path in streams.items():
            if not path.exists():
                complete = False
                job[f"{name}_sha256"] = None
                job[f"{name}_bytes"] = 0
                job[f"last_{name}_at"] = None
                continue
            try:
                data = path.read_bytes()
                stat = path.stat()
            except OSError:
                complete = False
                job[f"{name}_sha256"] = None
                job[f"{name}_bytes"] = 0
                job[f"last_{name}_at"] = None
                continue
            job[f"{name}_sha256"] = hashlib.sha256(data).hexdigest()
            job[f"{name}_bytes"] = len(data)
            job[f"last_{name}_at"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        job["stream_flush_status"] = "FLUSHED" if complete else "PARTIAL_OR_MISSING"

    def _assist_cancel(self, task_id: str) -> dict[str, Any]:
        job = self._assist_refresh(task_id)
        if job is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if job.get("status") == "UNKNOWN_REQUIRES_RECONCILE":
            job.update({
                "status": "CANCELLED",
                "finished_at": self._utc_now(),
                "blocker": "ASSIST_PROVIDER_PROCESS_LOST",
                "process_killed": False,
            })
            self._assist_record_stream_artifacts(job)
            self._cleanup_assist_workspace(job)
            self._assist_write(job)
        elif job.get("status") not in {"COMPLETED", "FAILED", "CANCELLED"}:
            pid = int(job.get("pid") or 0)
            process = None
            with self._assist_lock:
                process = self._assist_processes.get(task_id)
            terminated = False
            if pid:
                try:
                    os.killpg(int(job.get("pgid") or pid), signal.SIGTERM)
                except OSError:
                    pass
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    if process is not None and process.poll() is not None:
                        terminated = True
                        break
                    try:
                        os.kill(pid, 0)
                    except OSError:
                        terminated = True
                        break
                    time.sleep(0.05)
                if not terminated:
                    try:
                        os.killpg(int(job.get("pgid") or pid), signal.SIGKILL)
                    except OSError:
                        pass
                    if process is not None:
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            pass
                    try:
                        os.kill(pid, 0)
                    except OSError:
                        terminated = True
            job.update({
                "status": "CANCELLED",
                "finished_at": self._utc_now(),
                "blocker": "ASSIST_CANCELLED" if terminated else "ASSIST_CANCEL_CLEANUP_INCOMPLETE",
                "process_killed": terminated,
                "exit_code": process.returncode if process is not None else None,
            })
            self._assist_record_stream_artifacts(job)
            self._cleanup_assist_workspace(job)
            with self._assist_lock:
                self._assist_processes.pop(task_id, None)
            self._assist_write(job)
        return self._assist_response(job, operation="cancel")

    def _assist_retry(self, task_id: str) -> dict[str, Any]:
        job = self._assist_refresh(task_id)
        if job is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if job.get("status") not in {"FAILED", "CANCELLED"}:
            raise GatewayInputError("ASSIST_RETRY_REQUIRES_TERMINAL_FAILURE")
        command = job.get("command")
        if not isinstance(command, list) or not command:
            raise GatewayInputError("ASSIST_RETRY_COMMAND_NOT_RETAINED")
        history = list(job.get("attempt_history") or [])
        history.append({
            "job_id": job.get("job_id"),
            "attempt_id": job.get("attempt_id"),
            "status": job.get("status"),
            "exit_code": job.get("exit_code"),
            "result_artifact": job.get("result_artifact"),
        })
        new_job_id = f"{str(job.get('job_kind') or 'assist')}-{uuid4().hex}"
        root = self._assist_root()
        stdout_path = root / f"{new_job_id}.stdout"
        stderr_path = root / f"{new_job_id}.stderr"
        workspace_root = Path(tempfile.mkdtemp(prefix=f"nexus-retry-{task_id}-", dir="/tmp"))
        new_job = dict(job)
        new_job.update({
            "job_id": new_job_id,
            "attempt_id": f"attempt-{uuid4().hex}",
            "attempt_history": history,
            "status": "SUBMITTED",
            "submitted_at": self._utc_now(),
            "started_at": None,
            "finished_at": None,
            "pid": None,
            "pgid": None,
            "exit_code": None,
            "blocker": None,
            "provider_error": "",
            "result": None,
            "stdout_artifact": str(stdout_path),
            "stderr_artifact": str(stderr_path),
            "result_artifact": str(self._assist_path(task_id)),
            "workspace_root": str(workspace_root),
            "filesystem_before": self._snapshot_workspace(workspace_root),
            "filesystem_after": None,
            "filesystem_delta": {"created": [], "removed": [], "changed": []},
            "process_cleanup": False,
            "process_killed": False,
            "connector_disconnected_at": None,
            "reconnected_at": self._utc_now(),
        })
        self._assist_write(new_job)
        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(command, cwd=workspace_root, stdout=stdout_handle, stderr=stderr_handle, text=True, start_new_session=True)
        except Exception:
            stdout_handle.close()
            stderr_handle.close()
            shutil.rmtree(workspace_root, ignore_errors=True)
            new_job.update({"status": "FAILED", "finished_at": self._utc_now(), "blocker": "ASSIST_PROVIDER_FAILED", "provider_error": "provider process could not start"})
            return self._assist_response(self._assist_write(new_job), operation="retry")
        stdout_handle.close()
        stderr_handle.close()
        new_job.update({"status": "RUNNING", "pid": process.pid, "pgid": process.pid, "started_at": self._utc_now()})
        with self._assist_lock:
            self._assist_processes[task_id] = process
        return self._assist_response(self._assist_write(new_job), operation="retry")

    @staticmethod
    def _safe_slug(value: Any, field: str, *, max_length: int = 80) -> str:
        result = _text(value, field, max_length=max_length)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0," + str(max_length - 1) + r"}", result):
            raise GatewayInputError(f"{field} must be a stable bounded slug")
        return result

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _provider_executable(self, provider: str) -> tuple[dict[str, str], Optional[str]]:
        metadata = ONLINE_CLI_SPEC_REGISTRY.get(provider)
        if metadata is None:
            return {}, None
        try:
            executable = resolve_registered_provider_executable(provider)
        except ValueError:
            return metadata, None
        return metadata, str(Path(executable).resolve())

    def _provider_preflight(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        provider = str(arguments.get("provider") or "cline").strip().lower()
        requested_model = str(arguments.get("model") or arguments.get("preferred_model") or "").strip()
        if provider == "cline" and not requested_model:
            requested_model = "glm-5.2"
        metadata, executable = self._provider_executable(provider)
        resolved_model = requested_model
        if provider == "cline" and resolved_model and "/" not in resolved_model:
            resolved_model = f"cline-pass/{resolved_model}"
        result: dict[str, Any] = {
            "schema": "nexus.provider_preflight.v1",
            "provider": provider,
            "requested_model": requested_model,
            "resolved_model": resolved_model,
            "requested_model_verified": False,
            "resolved_model_evidence": None,
            "binary_found": bool(executable),
            "binary_path": executable,
            "binary_sha256": None,
            "cli_version": None,
            "authenticated": False,
            "model_reachable": False,
            "probe_requested": bool(arguments.get("probe", False)),
            "probe_latency_ms": 0,
            "exit_code": None,
            "stdout_sha256": None,
            "stderr_sha256": None,
            "status": "BLOCKED",
            "blocker": None,
            "next_action": None,
        }
        if not metadata:
            result["blocker"] = "ASSIST_PROVIDER_NOT_REGISTERED"
            return result
        if not executable:
            result["blocker"] = "ASSIST_PROVIDER_UNAVAILABLE"
            return result
        try:
            result["binary_sha256"] = self._hash_file(Path(executable))
        except OSError:
            result["blocker"] = "ASSIST_PROVIDER_BINARY_UNREADABLE"
            return result
        version_started = time.perf_counter()
        version_root = Path(tempfile.mkdtemp(prefix=f"nexus-preflight-{provider}-", dir="/tmp"))
        try:
            version = subprocess.run([executable, "--version"], cwd=version_root, capture_output=True, text=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["blocker"] = "ASSIST_PROVIDER_VERSION_FAILED"
            result["provider_error"] = str(exc)
            shutil.rmtree(version_root, ignore_errors=True)
            return result
        shutil.rmtree(version_root, ignore_errors=True)
        result["cli_version"] = (version.stdout or version.stderr).strip()[:512]
        result["cli_version_sha256"] = hashlib.sha256(result["cli_version"].encode()).hexdigest()
        result["version_latency_ms"] = max(0, int((time.perf_counter() - version_started) * 1000))
        if version.returncode != 0:
            result["exit_code"] = version.returncode
            result["blocker"] = "ASSIST_PROVIDER_VERSION_FAILED"
            return result
        # Model/auth execution is intentionally never synchronous here.  A
        # caller asking for probe=true receives a bounded handoff to the
        # isolated async model-probe surface, so ChatGPT request lifetimes and
        # the canonical checkout are not part of provider probing.
        evidence = self._read_probe_evidence(provider=provider, requested_model=requested_model, resolved_model=resolved_model, executable=executable, binary_sha256=result["binary_sha256"], cli_version=result["cli_version"])
        evidence_auth_ready = evidence is not None and (not self._provider_requires_authentication(provider) or evidence.get("authenticated") is True)
        if evidence_auth_ready:
            result.update({
                "status": "VERSION_VERIFIED",
                "blocker": None,
                "next_action": None,
                "readiness_status": "MODEL_VERIFIED",
                "execution_ready": True,
                "model_reachable": True,
                "requested_model_verified": True,
                "authenticated": evidence.get("authenticated") is True,
                "authentication_evidence": evidence.get("authentication_evidence"),
                "probe_evidence_hash": evidence.get("evidence_hash"),
                "probe_expires_at": evidence.get("expires_at"),
            })
        elif bool(arguments.get("probe", False)):
            result.update({
                "status": "VERSION_VERIFIED",
                "blocker": "MODEL_PROBE_ASYNC_REQUIRED",
                "next_action": "nexus_model_probe",
                "probe_mode": "deferred_async_isolated",
            })
        else:
            result.update({"status": "VERSION_VERIFIED", "blocker": "MODEL_PROBE_REQUIRED", "next_action": "nexus_model_probe"})
        result.setdefault("readiness_status", "VERSION_VERIFIED")
        result.setdefault("execution_ready", False)
        return result

    def _task_card_create(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if arguments.get("owner_confirmation") is not True:
            raise GatewayInputError("OWNER_CONFIRMATION_REQUIRED")
        campaign = self._safe_slug(arguments.get("campaign_id"), "campaign_id")
        task_id = self._safe_slug(arguments.get("task_id"), "task_id")
        objective = _text(arguments.get("objective"), "objective", max_length=4000)
        allowed = [str(path).strip() for path in arguments.get("allowed_files") or [] if str(path).strip()]
        if not allowed or len(allowed) > 10:
            raise GatewayInputError("allowed_files must contain 1-10 bounded paths")
        for path in allowed:
            _safe_relative_path(path, "allowed_files")
        verifiers = [str(command).strip() for command in arguments.get("verifier_commands") or [] if str(command).strip()]
        if not verifiers:
            raise GatewayInputError("verifier_commands is required")
        campaign_root = CANONICAL_SOURCE_ROOT / "tasks" / campaign
        index_path = campaign_root / "INDEX.md"
        card_path = campaign_root / f"00-{task_id}.md"
        if campaign_root.exists() or index_path.exists() or card_path.exists():
            raise GatewayInputError("TASK_CARD_CREATE_WOULD_OVERWRITE")
        card = "\n".join([
            f"# Task Card: {task_id}", "", "artifact_authority: current", f"task_id: `{task_id}`",
            "owner: James Chen", "status: ACTIVE", "commit_required: true", "candidate_required: true",
            "worker_may_commit: true", "worker_may_approve: false", "worker_may_integrate: false",
            "worker_may_push: false", "AUTO_CHAIN: false", "", "## Objective", "", objective, "",
            "## Allowed files", "", *[f"- `{path}`" for path in allowed], "", "## Verification commands", "",
            "```bash", *verifiers, "```", "", "## Exit criteria", "", "Owner review of the exact scoped commit.",
            "", "## Block classification", "", "Unverifiable or out-of-scope mutation is a HARD_BLOCK.", "",
        ])
        index = "\n".join([
            f"# Campaign Index: {campaign}", "", "artifact_authority: current", "owner: James Chen",
            "status: active, governed and sequential", "AUTO_CHAIN: false", "", "## Objective", "", objective,
            "", "## Ordered cards", "", "| Order | Task ID | Card | Status | Dependency |", "|---:|---|---|---|---|",
            f"| 0 | `{task_id}` | `00-{task_id}.md` | ACTIVE | Owner confirmation |", "",
        ])
        tasks_root = CANONICAL_SOURCE_ROOT / "tasks"
        tasks_root.mkdir(parents=True, exist_ok=True)
        temporary_root = tasks_root / f".{campaign}.create-{uuid4().hex}"
        try:
            temporary_root.mkdir(parents=False, exist_ok=False)
            temporary_index = temporary_root / "INDEX.md"
            temporary_card = temporary_root / f"00-{task_id}.md"
            temporary_index.write_text(index, encoding="utf-8")
            temporary_card.write_text(card, encoding="utf-8")
            if not temporary_index.is_file() or not temporary_card.is_file():
                raise RuntimeError("TASK_CARD_CREATE_ATOMIC_WRITE_FAILED")
            hashed = subprocess.run(["git", "hash-object", str(temporary_card)], cwd=CANONICAL_SOURCE_ROOT, capture_output=True, text=True, check=False)
            card_hash = hashed.stdout.strip()
            if hashed.returncode != 0 or not _SHA_RE.fullmatch(card_hash):
                raise RuntimeError("TASK_CARD_CREATE_HASH_FAILED")
            card_sha256 = hashlib.sha256(card.encode("utf-8")).hexdigest()
            if campaign_root.exists():
                raise GatewayInputError("TASK_CARD_CREATE_WOULD_OVERWRITE")
            os.replace(temporary_root, campaign_root)
        except Exception:
            shutil.rmtree(temporary_root, ignore_errors=True)
            raise
        diff_lines = list(difflib.unified_diff([], card.splitlines(True), fromfile="/dev/null", tofile=str(card_path.relative_to(CANONICAL_SOURCE_ROOT))))
        index_diff_lines = list(difflib.unified_diff([], index.splitlines(True), fromfile="/dev/null", tofile=str(index_path.relative_to(CANONICAL_SOURCE_ROOT))))
        return {
            "schema": "nexus.task_card_create.v1",
            "status": "CREATED_PENDING_COMMIT",
            "campaign_id": campaign,
            "task_id": task_id,
            "index_path": str(index_path.relative_to(CANONICAL_SOURCE_ROOT)),
            "card_path": str(card_path.relative_to(CANONICAL_SOURCE_ROOT)),
            "card_hash": card_sha256,
            "git_blob_sha": card_hash,
            "exact_card_diff": "".join(diff_lines),
            "exact_index_diff": "".join(index_diff_lines),
            "successor_execution": "NOT_STARTED",
            "owner_confirmation": True,
        }

    def _model_probe_submit(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        provider = str(arguments.get("provider") or "cline").strip().lower()
        metadata, executable = self._provider_executable(provider)
        if not metadata:
            raise GatewayInputError("ASSIST_PROVIDER_NOT_REGISTERED")
        if not executable:
            raise GatewayInputError("ASSIST_PROVIDER_UNAVAILABLE")
        model = str(arguments.get("model") or metadata.get("default_model") or "").strip()
        requested_model = model
        resolved_model = f"cline-pass/{model}" if provider == "cline" and "/" not in model else model
        prompt = _text(arguments.get("prompt"), "prompt", max_length=16000)
        schema = arguments.get("output_schema") or {"type": "object"}
        if not isinstance(schema, Mapping) or len(json.dumps(schema, ensure_ascii=False)) > 16000:
            raise GatewayInputError("output_schema must be a bounded object")
        workspace_mode = str(arguments.get("workspace_mode") or "isolated").strip().lower()
        if workspace_mode != "isolated":
            raise GatewayInputError("MODEL_PROBE_REQUIRES_ISOLATED_WORKSPACE")
        task_id = self._task_id(arguments, prompt, provider, ["model_probe"])
        existing = self._assist_read(task_id)
        if existing is not None:
            semantics = self._canonical_hash({"provider": provider, "model": model, "prompt": prompt, "output_schema": schema})
            if existing.get("probe_semantics_hash") != semantics:
                raise GatewayInputError("MODEL_PROBE_TASK_ID_CONFLICT")
            return self._assist_response(self._assist_refresh(task_id) or existing, operation="submit")
        # Resolve and attest the exact executable/version before creating an
        # isolated workspace or invoking Popen.  A failed preflight leaves no
        # probe workspace or provider process behind.
        version_root = Path(tempfile.mkdtemp(prefix=f"nexus-probe-preflight-{provider}-", dir="/tmp"))
        try:
            binary_sha256 = self._hash_file(Path(executable))
            version = subprocess.run(
                [executable, "--version"],
                cwd=version_root,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            cli_version = (version.stdout or version.stderr).strip()[:512]
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GatewayInputError("ASSIST_PROVIDER_VERSION_FAILED") from exc
        finally:
            shutil.rmtree(version_root, ignore_errors=True)
        if version.returncode != 0 or not cli_version:
            raise GatewayInputError("ASSIST_PROVIDER_VERSION_FAILED")
        action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.TASK_RUN,
            request={"task_id": task_id, "provider": provider, "model": model, "prompt": prompt, "output_schema": schema, "context_arm": arguments.get("context_arm")},
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            expected_head=_git("rev-parse", "HEAD").strip(),
            allowed_paths=[],
            mutation=False,
            permission_profile=PermissionProfile.VERIFY,
        ).model_dump(mode="json")
        job_id = f"probe-{uuid4().hex}"
        root = self._assist_root()
        stdout_path = root / f"{job_id}.stdout"
        stderr_path = root / f"{job_id}.stderr"
        workspace_root = Path(tempfile.mkdtemp(prefix=f"nexus-probe-{task_id}-", dir="/tmp"))
        probe_prompt = f"{prompt}\nReturn JSON matching this schema exactly: {json.dumps(schema, ensure_ascii=False)}"
        command = self._assist_command(executable=executable, provider=provider, model=model, prompt=probe_prompt)
        job: dict[str, Any] = {
            "schema": "nexus.assisted_provider_job.v1",
            "job_kind": "model_probe",
            "task_id": task_id,
            "job_id": job_id,
            "attempt_history": [],
            "action_id": action["action_id"],
            "attempt_id": action["attempt_id"],
            "status": "SUBMITTED",
            "execution_lane": "ASSISTED_CANONICAL",
            "candidate_only": True,
            "apply_requested": False,
            "provider": provider,
            "model": model,
            "requested_model": requested_model,
            "resolved_model": resolved_model,
            "binary_path": executable,
            "binary_sha256": binary_sha256,
            "cli_version": cli_version,
            "cli_version_sha256": hashlib.sha256(cli_version.encode("utf-8")).hexdigest(),
            "context_arm": arguments.get("context_arm"),
            "context_arm_applied": False,
            "context_arm_semantics": "record_only_not_applied",
            "requested_tools_policy": list(arguments.get("tools_allowed") or []),
            "tool_policy_enforcement": "cline_plan_auto_approve_false_allowlist_not_enforced",
            "workspace_mode": workspace_mode,
            "workspace_root": str(workspace_root),
            "filesystem_before": self._snapshot_workspace(workspace_root),
            "output_schema": dict(schema),
            "command_hash": hashlib.sha256(json.dumps(command, separators=(",", ":")).encode("utf-8")).hexdigest(),
            "probe_prompt_hash": self._canonical_hash(probe_prompt),
            "probe_semantics_hash": self._canonical_hash({"provider": provider, "model": model, "prompt": prompt, "output_schema": schema}),
            "action_request_hash": action["request_hash"],
            "command": command,
            "submitted_at": self._utc_now(),
            "started_at": None,
            "finished_at": None,
            "provider_time_ms": 0,
            "stdout_artifact": str(stdout_path),
            "stderr_artifact": str(stderr_path),
            "result_artifact": str(self._assist_path(task_id)),
            "action": action,
            "connector_disconnected_at": None,
            "reconnected_at": None,
        }
        self._assist_write(job)
        # Re-resolve and re-attest immediately before launch.  This closes the
        # avoidable gap between the initial evidence packet and the executable
        # actually handed to Popen.
        launch_root = Path(tempfile.mkdtemp(prefix=f"nexus-probe-launch-{provider}-", dir="/tmp"))
        launch_identity_matches = False
        launch_stat_identity: Optional[tuple[int, int, int, int]] = None
        try:
            _, launch_executable = self._provider_executable(provider)
            if launch_executable:
                launch_path = Path(launch_executable)
                launch_stat = launch_path.stat()
                launch_stat_identity = (
                    launch_stat.st_dev,
                    launch_stat.st_ino,
                    launch_stat.st_size,
                    launch_stat.st_mtime_ns,
                )
                launch_binary_sha256 = self._hash_file(launch_path)
                launch_version = subprocess.run(
                    [launch_executable, "--version"],
                    cwd=launch_root,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                launch_cli_version = (launch_version.stdout or launch_version.stderr).strip()[:512]
                launch_identity_matches = bool(
                    launch_version.returncode == 0
                    and launch_executable == executable
                    and launch_binary_sha256 == binary_sha256
                    and launch_cli_version == cli_version
                )
        except (OSError, subprocess.TimeoutExpired):
            launch_identity_matches = False
        finally:
            shutil.rmtree(launch_root, ignore_errors=True)
        if not launch_identity_matches:
            shutil.rmtree(workspace_root, ignore_errors=True)
            job.update({
                "status": "FAILED",
                "finished_at": self._utc_now(),
                "blocker": "ASSIST_PROVIDER_IDENTITY_DRIFT",
                "provider_error": "provider executable identity changed before launch",
                "model_response_verified": False,
                "process_cleanup": True,
            })
            return self._assist_response(self._assist_write(job), operation="submit")
        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(command, cwd=workspace_root, stdout=stdout_handle, stderr=stderr_handle, text=True, start_new_session=True)
        except Exception:
            stdout_handle.close()
            stderr_handle.close()
            shutil.rmtree(workspace_root, ignore_errors=True)
            job.update({"status": "FAILED", "finished_at": self._utc_now(), "blocker": "ASSIST_PROVIDER_FAILED", "provider_error": "provider process could not start"})
            return self._assist_response(self._assist_write(job), operation="submit")
        stdout_handle.close()
        stderr_handle.close()
        post_launch_identity_matches = False
        try:
            _, post_launch_executable = self._provider_executable(provider)
            if post_launch_executable:
                post_launch_path = Path(post_launch_executable)
                post_launch_stat = post_launch_path.stat()
                post_launch_stat_identity = (
                    post_launch_stat.st_dev,
                    post_launch_stat.st_ino,
                    post_launch_stat.st_size,
                    post_launch_stat.st_mtime_ns,
                )
                post_launch_identity_matches = bool(
                    post_launch_executable == executable
                    and post_launch_stat_identity == launch_stat_identity
                    and self._hash_file(post_launch_path) == binary_sha256
                )
        except OSError:
            post_launch_identity_matches = False
        if not post_launch_identity_matches:
            terminated = False
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except OSError:
                pass
            try:
                process.wait(timeout=2)
                terminated = True
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
                try:
                    process.wait(timeout=2)
                    terminated = True
                except subprocess.TimeoutExpired:
                    terminated = False
            if terminated:
                shutil.rmtree(workspace_root, ignore_errors=True)
            job.update({
                "status": "FAILED",
                "finished_at": self._utc_now(),
                "blocker": (
                    "ASSIST_PROVIDER_IDENTITY_DRIFT"
                    if terminated
                    else "ASSIST_PROVIDER_IDENTITY_DRIFT_CLEANUP_INCOMPLETE"
                ),
                "provider_error": "provider executable identity changed during launch",
                "model_response_verified": False,
                "process_cleanup": terminated,
                "pid": process.pid,
                "pgid": process.pid,
            })
            return self._assist_response(self._assist_write(job), operation="submit")
        job.update({"status": "RUNNING", "pid": process.pid, "pgid": process.pid, "started_at": self._utc_now()})
        with self._assist_lock:
            self._assist_processes[task_id] = process
        return self._assist_response(self._assist_write(job), operation="submit")

    def _resolve_assisted_worker(self, requested: str, requested_model: str) -> tuple[str, str, str | None]:
        """Resolve provider, exact model, and policy worker ID from one request."""
        key = str(requested or "auto").strip().lower() or "auto"
        model = str(requested_model or "").strip()
        if key == "auto":
            provider = os.environ.get("NEXUS_ASSIST_PROVIDER", "agy").strip().lower() or "agy"
            return provider, model, None
        snapshot = self._workforce_loader.load()
        worker = snapshot.workers.get(key)
        if worker is None:
            matches = [item for item in snapshot.workers.values() if item.model == key]
            if len(matches) == 1:
                worker = matches[0]
            elif key not in ONLINE_CLI_SPEC_REGISTRY and key not in {"mimo", "ollama"}:
                raise GatewayInputError("ASSIST_PROVIDER_NOT_REGISTERED")
        if worker is not None:
            if worker.state in NON_ADMISSIBLE_STATES:
                raise GatewayInputError(f"ASSIST_MODEL_NOT_ADMISSIBLE:{worker.worker_id}")
            if model and model != worker.model:
                raise GatewayInputError("ASSIST_MODEL_IDENTITY_MISMATCH")
            return worker.provider, worker.model, worker.worker_id
        return key, model, None

    def _resolve_worker_candidate(self, requested: str) -> tuple[str, str, str]:
        """Resolve one admissible registered worker without accepting overrides."""
        key = _text(requested, "worker", max_length=128).lower()
        snapshot = self._workforce_loader.load()
        def eligible(item: Any) -> bool:
            return item.state not in NON_ADMISSIBLE_STATES and str(item.state).upper() != "EXPERIMENT_ONLY" and str(getattr(item, "availability", "AVAILABLE")).upper() == "AVAILABLE"
        worker = snapshot.workers.get(key)
        if worker is None:
            matches = [item for item in snapshot.workers.values() if str(item.provider).lower() == key and eligible(item)]
            if not matches:
                raise GatewayInputError("WORKER_NOT_FOUND")
            if len(matches) != 1:
                raise GatewayInputError("WORKER_AMBIGUOUS")
            worker = matches[0]
        if not eligible(worker):
            raise GatewayInputError(f"WORKER_NOT_ADMISSIBLE:{worker.worker_id}")
        return str(worker.provider), str(worker.model), str(worker.worker_id)

    def _worker_candidate(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        allowed_keys = {
            "task_id", "what", "why", "worker", "allowed_files", "verifier_commands",
            "owner_confirmation", "authority_change_candidate_confirmation",
            "workforce_demands", "workforce_admission", "planner_output",
        }
        unknown = sorted(set(arguments) - allowed_keys)
        if unknown:
            raise GatewayInputError(f"WORKER_CANDIDATE_UNKNOWN_FIELDS:{','.join(unknown)}")
        if arguments.get("owner_confirmation") is not True:
            raise GatewayInputError("OWNER_CONFIRMATION_REQUIRED")
        authority_confirmation = arguments.get("authority_change_candidate_confirmation", False)
        if not isinstance(authority_confirmation, bool):
            raise GatewayInputError("AUTHORITY_CHANGE_CONFIRMATION_INVALID")
        what = _text(arguments.get("what"), "what", max_length=4000)
        why = _text(arguments.get("why"), "why", max_length=4000)
        task_id = self._task_id(arguments, what, why, [str(p).strip() for p in arguments.get("allowed_files") or []])
        allowed = [str(path).strip() for path in arguments.get("allowed_files") or [] if str(path).strip()]
        if not 1 <= len(allowed) <= 4:
            raise GatewayInputError("allowed_files must contain 1-4 bounded paths")
        for path in allowed:
            _safe_relative_path(path, "allowed_files")
        verifiers = [str(command).strip() for command in arguments.get("verifier_commands") or [] if str(command).strip()]
        if not verifiers or len(verifiers) > 4:
            raise GatewayInputError("verifier_commands must contain 1-4 bounded commands")
        if any(any(token in command for token in (";", "&&", "||", "`", "$(", "|")) for command in verifiers):
            raise GatewayInputError("verifier_commands must be bounded")
        dispatch_binding = validate_workforce_dispatch_binding(arguments)
        if dispatch_binding is not None:
            requested_worker = str(arguments.get("worker") or "").strip().lower()
            if requested_worker not in {
                "auto", dispatch_binding["worker_id"].lower(), dispatch_binding["provider"].lower(),
            }:
                raise GatewayInputError("WORKFORCE_ADMISSION_WORKER_MISMATCH")
            provider = dispatch_binding["provider"]
            model = dispatch_binding["model"]
            worker_id = dispatch_binding["worker_id"]
        else:
            provider, model, worker_id = self._resolve_worker_candidate(str(arguments.get("worker") or ""))
        preflight = self._provider_preflight({"provider": provider, "model": model})
        ready, blocker = self._provider_execution_ready(
            preflight,
            provider=provider,
            model=model if dispatch_binding is not None else None,
        )
        if not ready:
            detail = blocker or "WORKER_PREFLIGHT_FAILED"
            if preflight.get("next_action"):
                detail = f"{detail}:{preflight['next_action']}"
            raise GatewayInputError(detail)
        readiness_binding = {
            "provider_probe_evidence_hash": self._exact_hash(
                preflight.get("probe_evidence_hash"),
                "provider_probe_evidence_hash",
                64,
            ),
            "provider_binary_path": _text(
                preflight.get("binary_path"),
                "provider_binary_path",
                max_length=1024,
            ),
            "provider_binary_sha256": self._exact_hash(
                preflight.get("binary_sha256"),
                "provider_binary_sha256",
                64,
            ),
            "provider_cli_version_sha256": self._exact_hash(
                preflight.get("cli_version_sha256"),
                "provider_cli_version_sha256",
                64,
            ),
            "provider_probe_expires_at": _text(
                preflight.get("probe_expires_at"),
                "provider_probe_expires_at",
                max_length=128,
            ),
            "provider_authentication_evidence": str(
                preflight.get("authentication_evidence") or "local_provider_no_auth_required"
            ),
        }
        head = self._exact_hash(_git("rev-parse", "HEAD").strip(), "expected_head", 40)
        issued = self._utc_now()
        expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        contract = build_owner_inline_contract(
            task_id=task_id, objective=what, allowed_files=allowed,
            verifier_commands=verifiers, expected_head=head, issued_at=issued,
            expires_at=expires, permission_profile=PermissionProfile.CANDIDATE,
            worker_may_commit=False,
            authority_change_candidate_confirmation=authority_confirmation,
        )
        contract_binding = {
            "contract_kind": ContractKind.OWNER_INLINE.value,
            "contract_hash": contract["contract_hash"],
            "owner_inline_contract": contract,
            "task_card_path": None, "task_card_hash": None,
        }
        bound = self._canonical_request(
            task_id, what, why, allowed, verifiers, head,
            contract_binding=contract_binding,
        )
        protected_contracts = ["repository-authority-change.v1"] if authority_confirmation else []
        bound.update({"provider": provider, "model": model, "worker": provider, "worker_id": worker_id,
                      "execution_lane": "ISOLATED_TARGET", "primary_agent": False,
                      "worker_candidate_ingress": True,
                      "protected_contracts": protected_contracts})
        if dispatch_binding is not None:
            bound["workforce_demands"] = dispatch_binding["demands"]
            bound["workforce_admission"] = dispatch_binding["admission"]
        bound.update(readiness_binding)
        if authority_confirmation:
            bound["authority_change_candidate_confirmation"] = True
        action = build_action_envelope(
            task_id=task_id, action_type=LifecycleActionType.TASK_RUN,
            request=bound, tool_manifest_hash=TOOL_MANIFEST_REVISION,
            expected_head=head, allowed_paths=allowed, mutation=True,
            task_card_path=None, task_card_hash=None,
            contract_kind=ContractKind.OWNER_INLINE,
            contract_hash=contract["contract_hash"],
            permission_profile=PermissionProfile.CANDIDATE,
            mutation_domain=MutationDomain.TARGET,
        ).model_dump(mode="json")
        bound.update({
            "attempt_id": action["attempt_id"], "action_id": action["action_id"],
            "idempotency_key": action["idempotency_key"],
            "action_type": action["action_type"],
        })
        action = build_action_envelope(
            task_id=task_id, action_type=LifecycleActionType.TASK_RUN,
            request=bound, tool_manifest_hash=TOOL_MANIFEST_REVISION,
            expected_head=head, allowed_paths=allowed, mutation=True,
            contract_kind=ContractKind.OWNER_INLINE,
            contract_hash=contract["contract_hash"],
            permission_profile=PermissionProfile.CANDIDATE,
            mutation_domain=MutationDomain.TARGET,
            attempt_id=bound["attempt_id"], action_id=bound["action_id"],
            idempotency_key=bound["idempotency_key"],
        ).model_dump(mode="json")
        request = self._canonical_request(
            task_id, what, why, allowed, verifiers, head,
            action=action, contract_binding=contract_binding,
            bound_action_request=bound,
        )
        request["request_hash"] = action["request_hash"]
        request.update({"provider": provider, "model": model, "worker": provider, "worker_id": worker_id,
                        "execution_lane": "ISOLATED_TARGET", "primary_agent": False,
                        "worker_candidate_ingress": True})
        if dispatch_binding is not None:
            request["workforce_demands"] = dispatch_binding["demands"]
            request["workforce_admission"] = dispatch_binding["admission"]
        request.update(readiness_binding)
        if authority_confirmation:
            request["authority_change_candidate_confirmation"] = True
        request["protected_contracts"] = protected_contracts
        current_head = self._exact_hash(_git("rev-parse", "HEAD").strip(), "current_head", 40)
        if current_head != head:
            raise GatewayInputError("HEAD_DRIFT")
        pre_action_guard(action, request=request, current_head=head, tool_manifest_hash=TOOL_MANIFEST_REVISION)
        result = self.service.submit_task(request)
        payload = dict(result or {})
        payload.update({"schema": "nexus.worker_candidate.v1", "worker_id": worker_id,
                        "provider": provider, "model": model, "preflight": preflight,
                        "candidate_only": True})
        return payload

    @staticmethod
    def tool_specs() -> list[dict[str, Any]]:
        return [
            {
                "name": "nexus_gateway_status",
                "description": "Read the single gateway identity, manifest, route stages, and lifecycle counts.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "nexus_workspace_snapshot",
                "description": "Read the canonical checkout snapshot without creating state or a Target.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "nexus_read",
                "description": "Read a bounded UTF-8 file inside the canonical checkout.",
                "inputSchema": {
                    "type": "object",
                    "required": ["path"],
                    "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "integer", "minimum": 1, "default": 1},
                        "max_lines": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 200},
                    },
                },
            },
            {
                "name": "nexus_search",
                "description": "Search bounded literal text inside one canonical relative path.",
                "inputSchema": {
                    "type": "object",
                    "required": ["pattern"],
                    "properties": {
                        "pattern": {"type": "string", "maxLength": 200},
                        "path": {"type": "string", "default": "."},
                    },
                },
            },
            {
                "name": "nexus_git_diff",
                "description": "Read a bounded canonical diff; no arbitrary Git flags are accepted.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "base_revision": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "staged": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "nexus_task_run",
                "description": "Run one bounded task through the canonical Planner, Online/Local runtime, verifier, and RootReceipt path.",
                "inputSchema": {
                    "type": "object",
                    "required": ["what", "why", "allowed_files"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "what": {"type": "string"},
                        "why": {"type": "string"},
                        "allowed_files": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}, "maxItems": 1},
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "nexus_worker_candidate",
                "description": "Submit one explicit Owner Inline worker candidate through an isolated Target.",
                "inputSchema": {
                    "type": "object",
                    "required": ["what", "why", "worker", "allowed_files", "verifier_commands", "owner_confirmation"],
                    "additionalProperties": False,
                    "properties": {
                        "task_id": {"type": "string", "maxLength": 80},
                        "what": {"type": "string", "maxLength": 4000},
                        "why": {"type": "string", "maxLength": 4000},
                        "worker": {"type": "string", "maxLength": 128},
                        "allowed_files": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
                        "owner_confirmation": {"type": "boolean", "const": True},
                        "authority_change_candidate_confirmation": {"type": "boolean", "default": False},
                        "workforce_demands": {"type": "object"},
                        "workforce_admission": {"type": "object"},
                        "planner_output": {"type": "object"},
                    },
                },
            },
            {
                "name": "nexus_task_status",
                "description": "Read one durable task's status and next action.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_task_wait",
                "description": "Poll one bounded lifecycle task until attention, terminal, or timeout.",
                "inputSchema": {
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "timeout_seconds": {"type": "number", "minimum": 0, "maximum": 60, "default": 10},
                        "poll_interval_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 5, "default": 0.25},
                    },
                },
            },
            {
                "name": "nexus_task_finish",
                "description": "Finish a Direct receipt or owner-finish an exact isolated Candidate binding.",
                "inputSchema": {
                    "type": "object",
                    "required": ["execution_lane"],
                    "properties": {
                        "execution_lane": {"type": "string", "enum": ["DIRECT_CANONICAL", "ISOLATED_TARGET"]},
                        "request": {"type": "object"},
                        "base_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "controller_revision": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "allowed_files": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}},
                        "expected_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "task_id": {"type": "string"},
                        "candidate_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_tree_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_state_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "verified_receipt_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    },
                },
            },
            {
                "name": "nexus_task_cancel",
                "description": "Cancel one non-running lifecycle task through formal cleanup authority.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_task_list_actionable",
                "description": "List durable tasks that require exactly one recovery or owner action.",
                "inputSchema": {"type": "object", "properties": {"include_details": {"type": "boolean", "default": False}}},
            },
            {
                "name": "nexus_task_reconcile",
                "description": "Reconcile one uncertain task from durable evidence without replaying a mutation.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_task_retry",
                "description": "Retry one terminal task with the same task_id and a new attempt_id after cleanup.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_task_resume",
                "description": "Resume one durable task only from its recorded execution evidence.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_assist_submit",
                "description": "Submit a durable Assisted Cline provider job and return immediately.",
                "inputSchema": {
                    "type": "object",
                    "required": ["what", "why", "allowed_files"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "what": {"type": "string"},
                        "why": {"type": "string"},
                        "allowed_files": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}},
                        "provider": {"type": "string", "enum": ["cline"], "default": "cline"},
                        "model": {"type": "string", "default": "glm-5.2"},
                        "apply": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "nexus_assist_result",
                "description": "Read the durable Assisted provider result for one task after disconnect or timeout.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_assist_cancel",
                "description": "Cancel one running Assisted provider job without applying a candidate.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_provider_preflight",
                "description": "Verify a registered provider binary, version, identity, and optional exact-model probe.",
                "inputSchema": {
                    "type": "object",
                    "required": ["provider"],
                    "properties": {
                        "provider": {"type": "string"},
                        "model": {"type": "string"},
                        "probe": {"type": "boolean", "default": False},
                        "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 60, "default": 30},
                    },
                },
            },
            {
                "name": "nexus_task_card_create",
                "description": "Create exactly one new governed campaign INDEX and Task Card after explicit owner confirmation.",
                "inputSchema": {
                    "type": "object",
                    "required": ["owner_confirmation", "campaign_id", "task_id", "objective", "allowed_files", "verifier_commands"],
                    "properties": {
                        "owner_confirmation": {"type": "boolean"},
                        "campaign_id": {"type": "string"},
                        "task_id": {"type": "string"},
                        "objective": {"type": "string"},
                        "allowed_files": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    },
                },
            },
            {
                "name": "nexus_model_probe",
                "description": "Run one schema-bound model probe in an isolated workspace and return a durable job.",
                "inputSchema": {
                    "type": "object",
                    "required": ["provider", "model", "prompt", "output_schema"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "provider": {"type": "string"},
                        "model": {"type": "string"},
                        "prompt": {"type": "string", "maxLength": 16000},
                        "output_schema": {"type": "object"},
                        "tools_allowed": {"type": "array", "items": {"type": "string"}, "maxItems": 16, "description": "Requested policy only; provider-specific enforcement is not claimed."},
                        "workspace_mode": {"type": "string", "enum": ["isolated"], "default": "isolated"},
                        "context_arm": {"type": "string", "enum": ["bare", "nexus_bounded", "nexus_full"], "description": "Recorded for future calibration only; not applied to the probe prompt in this version."},
                    },
                },
            },
            {
                "name": "nexus_model_probe_result",
                "description": "Retrieve one durable schema-bound model probe result and filesystem/process receipt.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_candidate_approve",
                "description": "Approve an exact Candidate binding; approval does not integrate or push.",
                "inputSchema": {
                    "type": "object",
                    "required": ["task_id", "candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash", "approval"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "candidate_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_tree_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_state_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "verified_receipt_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "approval": {
                            "type": "object",
                            "description": "Versioned, expiring approval bound to the persisted task attempt and runtime identity.",
                            "required": [
                                "schema", "approval_id", "approved_by", "issued_at", "expires_at",
                                "bound_task_id", "bound_attempt_id", "bound_action_type", "contract_kind", "contract_hash", "task_card_hash",
                                "tool_manifest_hash", "full_tool_schema_hash", "permission_policy_hash",
                                "lifecycle_revision", "server_instance_id",
                            ],
                            "properties": {
                                "schema": {"type": "string", "const": "nexus.approval.v2"},
                                "approval_id": {"type": "string"},
                                "approved_by": {"type": "string"},
                                "issued_at": {"type": "string", "format": "date-time"},
                                "expires_at": {"type": "string", "format": "date-time"},
                                "bound_task_id": {"type": "string"},
                                "bound_attempt_id": {"type": "string"},
                                "bound_action_type": {"type": "string", "const": "CANDIDATE_APPROVE"},
                                "approval_scope": {"type": "string", "const": "ALLOW_ACTION_ONCE", "default": "ALLOW_ACTION_ONCE"},
                                "contract_kind": {"type": "string", "enum": ["TRACKED_TASK_CARD", "OWNER_INLINE"]},
                                "contract_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "task_card_hash": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"},
                                "tool_manifest_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "full_tool_schema_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "permission_policy_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "lifecycle_revision": {"type": "string"},
                                "server_instance_id": {"type": "string"},
                                "consumed_at": {"type": ["string", "null"], "format": "date-time"},
                                "architecture_approval": {
                                    "type": ["object", "null"],
                                    "description": "Exact, one-shot Owner acknowledgement for the pending repository authority findings.",
                                    "required": ["schema", "approval_id", "approved_by", "issued_at", "expires_at", "approval_scope", "bound_task_id", "bound_attempt_id", "candidate_commit_sha", "candidate_tree_sha", "authority_findings_sha256"],
                                    "properties": {
                                        "schema": {"type": "string", "const": "nexus.architecture_approval.v1"},
                                        "approval_id": {"type": "string"},
                                        "approved_by": {"type": "string"},
                                        "issued_at": {"type": "string", "format": "date-time"},
                                        "expires_at": {"type": "string", "format": "date-time"},
                                        "approval_scope": {"type": "string", "const": "ALLOW_ACTION_ONCE"},
                                        "bound_task_id": {"type": "string"},
                                        "bound_attempt_id": {"type": "string"},
                                        "candidate_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                                        "candidate_tree_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                                        "authority_findings_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                        "consumed_at": {"type": ["string", "null"], "format": "date-time"},
                                    },
                                    "additionalProperties": False,
                                },
                            },
                            "additionalProperties": False,
                        },
                    },
                },
            },
            {
                "name": "nexus_candidate_bind_integration",
                "description": "Bind an independently accepted exact Candidate to a fresh CANDIDATE_INTEGRATE approval; prepares but does not apply integration.",
                "inputSchema": {
                    "type": "object",
                    "required": ["task_id", "expected_canonical_head", "external_acceptance", "approval"],
                    "additionalProperties": False,
                    "properties": {
                        "task_id": {"type": "string"},
                        "integration_branch": {"type": "string", "default": "nexus/integration/main"},
                        "expected_canonical_head": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "external_acceptance": {
                            "type": "object", "additionalProperties": False,
                            "required": ["schema", "task_id", "attempt_id", "candidate_commit", "receipt_hash", "reviewer_id", "passed", "verifier_artifact"],
                            "properties": {
                                "schema": {"type": "string", "const": "nexus.external_acceptance_receipt.v1"},
                                "task_id": {"type": "string"}, "attempt_id": {"type": "string"},
                                "candidate_commit": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                                "receipt_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "reviewer_id": {"type": "string"}, "passed": {"type": "boolean", "const": True},
                                "verifier_artifact": {"type": "string"},
                            },
                        },
                        "approval": {
                            "type": "object", "additionalProperties": False,
                            "required": ["schema", "approval_id", "approved_by", "issued_at", "expires_at", "bound_task_id", "bound_attempt_id", "bound_action_type", "contract_kind", "contract_hash", "task_card_hash", "tool_manifest_hash", "full_tool_schema_hash", "permission_policy_hash", "lifecycle_revision", "server_instance_id", "expected_canonical_head", "integration_branch", "candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash", "acceptance_receipt_hash"],
                            "properties": {
                                "schema": {"type": "string", "const": "nexus.approval.v2"}, "approval_id": {"type": "string"}, "approved_by": {"type": "string"},
                                "issued_at": {"type": "string", "format": "date-time"}, "expires_at": {"type": "string", "format": "date-time"},
                                "bound_task_id": {"type": "string"}, "bound_attempt_id": {"type": "string"},
                                "bound_action_type": {"type": "string", "const": "CANDIDATE_INTEGRATE"},
                                "approval_scope": {"type": "string", "const": "ALLOW_ACTION_ONCE", "default": "ALLOW_ACTION_ONCE"},
                                "contract_kind": {"type": "string", "enum": ["TRACKED_TASK_CARD", "OWNER_INLINE"]}, "contract_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "task_card_hash": {"type": ["string", "null"]},
                                "tool_manifest_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "full_tool_schema_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "permission_policy_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "lifecycle_revision": {"type": "string"}, "server_instance_id": {"type": "string"},
                                "expected_canonical_head": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                                "integration_branch": {"type": "string"},
                                "candidate_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"}, "candidate_tree_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"}, "candidate_state_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "verified_receipt_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "acceptance_receipt_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                            },
                        },
                    },
                },
            },
            {
                "name": "nexus_candidate_integrate",
                "description": "Integrate an already approved exact Candidate binding without pushing.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}, "integration_branch": {"type": "string", "default": "nexus/integration/main"}}},
            },
            {
                "name": "nexus_candidate_dispose",
                "description": "Dispose a pending Candidate as REJECTED or SUPERSEDED through cleanup authority.",
                "inputSchema": {"type": "object", "required": ["task_id", "disposition"], "properties": {"task_id": {"type": "string"}, "disposition": {"type": "string", "enum": ["REJECTED", "SUPERSEDED"]}, "superseded_by": {"type": "string"}}},
            },
        ]

    @staticmethod
    def _success(request_id: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
        text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": text}], "structuredContent": dict(payload), "isError": False}}

    @staticmethod
    def _task_not_found(
        task_id: str,
        *,
        operation: str,
        timeout_seconds: Optional[float] = None,
        poll_interval_seconds: Optional[float] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": "nexus.self_hosted_task_status.v1",
            "task_id": task_id,
            "status": "NOT_FOUND",
            "found": False,
            "state_valid": False,
            "retry_authorized": False,
            "blocker": {"code": "TASK_NOT_FOUND", "detail": "no lifecycle state exists for task_id"},
            "task_action": {
                "schema": "nexus.self_hosted_task_action.v1",
                "task_id": task_id,
                "task_status": "NOT_FOUND",
                "action_state": "NOT_FOUND",
                "attention_required": False,
                "next_action": "none",
                "recommended_tool": None,
            },
            "operation": operation,
        }
        if operation == "wait":
            payload["wait"] = {
                "timed_out": False,
                "not_found": True,
                "timeout_seconds": timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
            }
        return payload

    @staticmethod
    def _error(request_id: Any, error: Exception | str) -> dict[str, Any]:
        payload = error.as_dict() if isinstance(error, LifecycleGuardError) else {"schema": "nexus.mcp_gateway_error.v1", "error": str(error)}
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "structuredContent": payload, "isError": True}}

    def _gateway_status(self) -> dict[str, Any]:
        lifecycle = self.service.lifecycle_status()
        current_head = _git("rev-parse", "HEAD").strip()
        formal_actionable = self.service.list_actionable_tasks()
        pending_actions = int(formal_actionable.get("actionable_count", 0) or 0)
        for job_path in self._assist_root().glob("*.json"):
            try:
                job = json.loads(job_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(job, Mapping):
                action = self._assist_action(job)
                if action["pending"] or action["attention_required"]:
                    pending_actions += 1
        action_sha_current, action_contract_ok, action_contract_reasons = _action_contract_fingerprint()
        permission_sha_current, permission_contract_ok, permission_contract_reasons = _permission_enforcement_fingerprint()
        freshness = _evaluate_freshness(
            repo_head_at_start=SERVER_REPO_HEAD_AT_START,
            repo_head_current=current_head,
            runtime_sha_at_start=RUNTIME_SOURCE_SHA256_AT_START,
            runtime_sha_current=_hash_source_paths(RUNTIME_SOURCE_PATHS),
            action_sha_at_start=ACTION_CONTRACT_SHA256_AT_START,
            action_sha_current=action_sha_current,
            permission_sha_at_start=PERMISSION_ENFORCEMENT_SHA256_AT_START,
            permission_sha_current=permission_sha_current,
            action_contract_ok=action_contract_ok,
            action_contract_reasons=action_contract_reasons,
            permission_contract_ok=permission_contract_ok,
            permission_contract_reasons=permission_contract_reasons,
        )
        return {
            "schema": "nexus.mcp_gateway_status.v1",
            "public_app_name": PUBLIC_APP_NAME,
            "namespace_policy": "stable_public_name_with_manifest_revision",
            "server": GATEWAY_NAME,
            "version": GATEWAY_VERSION,
            "tool_manifest_revision": TOOL_MANIFEST_REVISION,
            "full_tool_schema_hash": FULL_TOOL_SCHEMA_HASH,
            "permission_policy_hash": PERMISSION_POLICY_HASH,
            "permission_policy_revision": PERMISSION_POLICY_REVISION,
            "task_contract_revision": TASK_CONTRACT_REVISION,
            "lifecycle_revision": LIFECYCLE_REVISION,
            "lifecycle_state_schema_revision": LIFECYCLE_STATE_SCHEMA_REVISION,
            "server_instance_id": SERVER_INSTANCE_ID,
            "server_started_at": SERVER_STARTED_AT,
            "repo_head_at_start": SERVER_REPO_HEAD_AT_START,
            "repo_head_current": current_head,
            "freshness_semantics_revision": FRESHNESS_SEMANTICS_REVISION,
            **freshness,
            "session_tracking": "unsupported",
            "active_sessions": None,
            "pending_actions": pending_actions,
            "tool_count": len(PUBLIC_TOOL_NAMES),
            "route_authority": "CapabilityPlanner",
            "execution_lanes": ["DIRECT_CANONICAL", "ASSISTED_CANONICAL", "ISOLATED_TARGET"],
            "canonical_repo_root": str(CANONICAL_SOURCE_ROOT),
            "lifecycle": lifecycle,
        }

    @staticmethod
    def _recovery_payload(state: Mapping[str, Any], *, operation: str = "status", include_state: bool = False) -> dict[str, Any]:
        """Normalize every recovery response to one actionable contract."""
        action = state.get("task_action") if isinstance(state.get("task_action"), Mapping) else {}
        action = dict(action)
        task_id = str(state.get("task_id") or action.get("task_id") or "")
        status = str(state.get("status") or action.get("task_status") or "UNKNOWN")
        terminal = status in {"CANCELLED", "INTEGRATED", "REJECTED", "SUPERSEDED", "FINAL_BLOCK"} and not bool(state.get("reconciliation_required"))
        next_action = str(action.get("next_action") or ("none" if terminal else "nexus_task_reconcile"))
        candidate = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        if not candidate and isinstance(action.get("candidate"), Mapping):
            candidate = action.get("candidate") or {}
        cleanup = state.get("cleanup_status") if isinstance(state.get("cleanup_status"), Mapping) else {}
        cleanup = dict(cleanup)
        if not cleanup:
            cleanup = {
                "state_retention_status": state.get("state_retention_status"),
                "cleanup_eligible": state.get("cleanup_eligible"),
                "cleanup_performed": state.get("cleanup_performed"),
                "cleanup_decision": state.get("cleanup_decision"),
                "cleanup_blocker": state.get("cleanup_blocker"),
            }
        action_id = state.get("action_id")
        if not action_id and isinstance(state.get("action"), Mapping):
            action_id = state["action"].get("action_id")
        if not action_id and isinstance(state.get("request"), Mapping) and isinstance(state["request"].get("action"), Mapping):
            action_id = state["request"]["action"].get("action_id")
        recommended = action.get("recommended_tool") or next_action
        if recommended not in PUBLIC_TOOL_NAMES:
            if status in {"DIRECT_RECONCILE_REQUIRED", "UNKNOWN_REQUIRES_RECONCILE"} or state.get("reconciliation_required"):
                recommended = "nexus_task_reconcile"
            elif status in {"FINAL_BLOCK", "RETAINED_FOR_REVIEW", "INTEGRATION_FAILED"}:
                recommended = "nexus_task_status"
            else:
                recommended = "nexus_task_wait"
        result: dict[str, Any] = {
            "schema": "nexus.lifecycle_recovery.v1",
            "operation": operation,
            "task_id": task_id,
            "attempt_id": state.get("attempt_id") or action.get("attempt_id"),
            "last_action_id": action_id,
            "status": status,
            "attention_required": bool(action.get("attention_required", not terminal)),
            "next_action": next_action,
            "recommended_tool": recommended,
            "candidate_binding": {
                "candidate_commit_sha": state.get("candidate_commit_sha") or candidate.get("candidate_commit_sha"),
                "candidate_tree_sha": state.get("candidate_tree_sha") or candidate.get("candidate_tree_sha"),
                "candidate_state_hash": state.get("candidate_state_hash") or candidate.get("candidate_state_hash"),
                "verified_receipt_hash": state.get("verified_receipt_hash") or candidate.get("verified_receipt_hash"),
                "candidate_ref": state.get("candidate_ref"),
            },
            "cleanup_status": cleanup,
            "uncertain_mutation": status in {"DIRECT_RECONCILE_REQUIRED", "UNKNOWN_REQUIRES_RECONCILE"} or bool(state.get("reconciliation_required")),
        }
        if include_state:
            result["state"] = dict(state)
        return result

    def _task_list_actionable(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        include_details = bool(arguments.get("include_details", False))
        raw = self.service.list_actionable_tasks(include_details=include_details)
        tasks = [self._recovery_payload(item, operation="list", include_state=include_details) for item in raw.get("tasks", []) if isinstance(item, Mapping)]
        for path in sorted(self._assist_root().glob("*.json")):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(job, Mapping):
                continue
            response = self._assist_response(self._assist_refresh(str(job.get("task_id"))) or job, operation="list")
            if response.get("attention_required") is True:
                tasks.append(response)
        return {
            "schema": "nexus.task_actionable_list.v1",
            "actionable_count": len(tasks),
            "details_included": include_details,
            "tasks": tasks,
        }

    def _task_reconcile(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _text(arguments.get("task_id"), "task_id")
        assisted = self._assist_read(task_id)
        if assisted is not None:
            current = self._assist_refresh(task_id) or assisted
            if current.get("status") == "UNKNOWN_REQUIRES_RECONCILE":
                # No durable exit marker means the provider outcome is not
                # recoverable from output alone.  Reconciliation deliberately
                # converges to a retryable process-loss failure and performs
                # isolated-workspace cleanup; it never upgrades to success.
                current.update({
                    "status": "FAILED",
                    "blocker": "ASSIST_PROVIDER_PROCESS_LOST",
                    "reconciliation_required": False,
                    "reconciled_from": "UNKNOWN_REQUIRES_RECONCILE",
                    "reconciled_at": self._utc_now(),
                    "finished_at": current.get("finished_at") or self._utc_now(),
                })
                self._cleanup_assist_workspace(current)
                current = self._assist_write(current)
            return self._assist_response(current, operation="reconcile")
        result = self.service.reconcile_task(task_id)
        if result is None:
            raise KeyError(f"unknown task_id: {task_id}")
        return self._recovery_payload(result, operation="reconcile", include_state=True)

    def _task_retry(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _text(arguments.get("task_id"), "task_id")
        assisted = self._assist_read(task_id)
        if assisted is not None:
            return self._assist_retry(task_id)
        return self._recovery_payload(self.service.retry_task(task_id), operation="retry", include_state=True)

    def _task_resume(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _text(arguments.get("task_id"), "task_id")
        assisted = self._assist_read(task_id)
        if assisted is not None:
            return self._assist_wait(task_id, timeout_seconds=0.0)
        result = self.service.resume_task(task_id)
        if result is None:
            raise KeyError(f"unknown task_id: {task_id}")
        return self._recovery_payload(result, operation="resume", include_state=True)

    @staticmethod
    def _exact_hash(value: Any, field: str, length: int) -> str:
        text = _text(value, field)
        pattern = rf"^[0-9a-f]{{{length}}}$"
        if not re.fullmatch(pattern, text):
            raise GatewayInputError(f"{field} must be an exact lowercase Git hash")
        return text

    def _candidate_approve(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _text(arguments.get("task_id"), "task_id")
        candidate_commit_sha = self._exact_hash(arguments.get("candidate_commit_sha"), "candidate_commit_sha", 40)
        candidate_tree_sha = self._exact_hash(arguments.get("candidate_tree_sha"), "candidate_tree_sha", 40)
        candidate_state_hash = self._exact_hash(arguments.get("candidate_state_hash"), "candidate_state_hash", 64)
        verified_receipt_hash = self._exact_hash(arguments.get("verified_receipt_hash"), "verified_receipt_hash", 64)
        state = self.service.get_task_snapshot(task_id, include_details=True)
        if not isinstance(state, Mapping):
            raise GatewayInputError("CANDIDATE_TASK_STATE_REQUIRED")
        base = str(state.get("controller_revision") or "").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", base):
            raise GatewayInputError("CANDIDATE_CONTROLLER_REVISION_REQUIRED")
        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        try:
            identity = resolve_contract_identity(state, expected_task_id=task_id, expected_head=base)
        except RuntimeError as exc:
            raise GatewayInputError(str(exc)) from exc
        contract_kind = identity["contract_kind"]
        contract_hash = identity["contract_hash"]
        task_card_hash = identity["task_card_hash"]
        owner_inline_contract = identity["owner_inline_contract"]
        if contract_kind == ContractKind.TRACKED_TASK_CARD.value and not re.fullmatch(r"[0-9a-f]{64}", task_card_hash):
            raise GatewayInputError("CANDIDATE_TASK_CARD_HASH_REQUIRED")
        if contract_kind == ContractKind.OWNER_INLINE.value and not contract_hash:
            raise GatewayInputError("CANDIDATE_OWNER_INLINE_CONTRACT_REQUIRED")
        approval_receipt = validate_approval_grant(
            arguments.get("approval"),
            task_id=task_id,
            attempt_id=str(state.get("attempt_id") or ""),
            action_type=LifecycleActionType.CANDIDATE_APPROVE.value,
            task_card_hash=task_card_hash,
            contract_kind=contract_kind,
            contract_hash=contract_hash,
            owner_inline_contract=owner_inline_contract,
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            full_tool_schema_hash=FULL_TOOL_SCHEMA_HASH,
            permission_policy_hash=PERMISSION_POLICY_HASH,
            lifecycle_revision=LIFECYCLE_REVISION,
            server_instance_id=SERVER_INSTANCE_ID,
        )
        action_request = {**dict(arguments), "source_attempt_id": state.get("attempt_id"), "candidate_binding": {
            "candidate_commit_sha": packet.get("candidate_commit_sha") or state.get("candidate_commit_sha"),
            "candidate_tree_sha": packet.get("candidate_tree_sha") or state.get("candidate_tree_sha"),
            "candidate_state_hash": packet.get("candidate_state_hash") or state.get("candidate_state_hash"),
            "verified_receipt_hash": packet.get("verified_receipt_hash") or state.get("verified_receipt_hash"),
        }}
        action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.CANDIDATE_APPROVE,
            request=action_request,
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            expected_head=base,
            allowed_paths=[],
            mutation=True,
            permission_profile=PermissionProfile.CANDIDATE,
            mutation_domain=MutationDomain.LIFECYCLE_STATE,
        )
        guard_receipt = pre_action_guard(action, request={}, current_head=base, tool_manifest_hash=TOOL_MANIFEST_REVISION)
        result = self.service.approve_promotion(
            task_id,
            candidate_commit_sha=candidate_commit_sha,
            candidate_tree_sha=candidate_tree_sha,
            candidate_state_hash=candidate_state_hash,
            verified_receipt_hash=verified_receipt_hash,
            approval_context={**dict(arguments.get("approval") or {}), "validation_receipt": approval_receipt},
        )
        payload = self._recovery_payload(result, operation="candidate_approve", include_state=True)
        payload["guard_receipt"] = guard_receipt
        payload["approval_receipt"] = approval_receipt
        return payload

    def _candidate_bind_integration(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        forbidden = {"integration_authorization", "action_set", "approval_context", "shell"}
        if forbidden.intersection(arguments):
            raise GatewayInputError("CLOSURE_SCHEMA_CLOSED")
        task_id = _text(arguments.get("task_id"), "task_id")
        branch = str(arguments.get("integration_branch") or "nexus/integration/main").strip()
        expected_head = _text(arguments.get("expected_canonical_head"), "expected_canonical_head")
        if not re.fullmatch(r"[0-9a-f]{40}", expected_head):
            raise GatewayInputError("expected_canonical_head is invalid")
        if not branch or branch.startswith("-") or any(char in branch for char in "\n\r"):
            raise GatewayInputError("integration_branch is invalid")
        raw_acceptance = arguments.get("external_acceptance")
        raw_approval = arguments.get("approval")
        if not isinstance(raw_acceptance, Mapping) or not isinstance(raw_approval, Mapping):
            raise GatewayInputError("typed external_acceptance and approval are required")
        try:
            acceptance = ExternalAcceptanceReceipt(**dict(raw_acceptance))
        except Exception as exc:
            raise GatewayInputError(f"EXTERNAL_ACCEPTANCE_INVALID: {exc}") from exc
        state = self.service.get_task_snapshot(task_id, include_details=True)
        if not isinstance(state, Mapping):
            raise GatewayInputError("CANDIDATE_TASK_STATE_REQUIRED")
        base = str(state.get("controller_revision") or "").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", base):
            raise GatewayInputError("CANDIDATE_CONTROLLER_REVISION_REQUIRED")
        try:
            identity = resolve_contract_identity(state, expected_task_id=task_id, expected_head=base)
        except RuntimeError as exc:
            raise GatewayInputError(str(exc)) from exc
        contract = state.get("contract") if isinstance(state.get("contract"), Mapping) else {}
        controller_root = Path(str(contract.get("controller_repo_root") or CANONICAL_SOURCE_ROOT)).expanduser().resolve()
        live_head_result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=controller_root, capture_output=True, text=True, check=False)
        live_head = live_head_result.stdout.strip()
        if live_head_result.returncode != 0 or live_head != expected_head:
            raise GatewayInputError("CANDIDATE_BIND_HEAD_DRIFT")
        allowed_files = [str(path) for path in contract.get("allowed_files") or [] if str(path).strip()]
        if not allowed_files:
            raise GatewayInputError("CANDIDATE_ALLOWED_PATHS_REQUIRED")
        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        action_request = {"task_id": task_id, "integration_branch": branch, "expected_canonical_head": expected_head, "external_acceptance": dict(raw_acceptance), "approval": dict(raw_approval), "source_attempt_id": state.get("attempt_id"), "candidate_binding": {
            "candidate_commit_sha": packet.get("candidate_commit_sha") or state.get("candidate_commit_sha"),
            "candidate_tree_sha": packet.get("candidate_tree_sha") or state.get("candidate_tree_sha"),
            "candidate_state_hash": packet.get("candidate_state_hash") or state.get("candidate_state_hash"),
            "verified_receipt_hash": packet.get("verified_receipt_hash") or state.get("verified_receipt_hash"),
        }}
        action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.CANDIDATE_INTEGRATE,
            request=action_request,
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            expected_head=expected_head,
            allowed_paths=allowed_files,
            mutation=True,
            permission_profile=PermissionProfile.INTEGRATE,
            mutation_domain=MutationDomain.LIFECYCLE_STATE,
        )
        guard_receipt = pre_action_guard(action, request={"allowed_files": allowed_files}, current_head=live_head, tool_manifest_hash=TOOL_MANIFEST_REVISION)
        result = self.service.bind_candidate_integration_closure(
            task_id,
            external_acceptance=acceptance,
            approval=raw_approval,
            expected_canonical_head=expected_head,
            integration_branch=branch,
            runtime_identity={
                **identity,
                "tool_manifest_hash": TOOL_MANIFEST_REVISION,
                "full_tool_schema_hash": FULL_TOOL_SCHEMA_HASH,
                "permission_policy_hash": PERMISSION_POLICY_HASH,
                "lifecycle_revision": LIFECYCLE_REVISION,
                "server_instance_id": SERVER_INSTANCE_ID,
            },
        )
        payload = self._recovery_payload(result, operation="candidate_bind_integration", include_state=True)
        payload["guard_receipt"] = guard_receipt
        payload["integration_performed"] = False
        return payload

    def _candidate_integrate(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _text(arguments.get("task_id"), "task_id")
        branch = str(arguments.get("integration_branch") or "nexus/integration/main").strip()
        if not branch or branch.startswith("-") or any(char in branch for char in "\n\r"):
            raise GatewayInputError("integration_branch is invalid")
        state = self.service.get_task_snapshot(task_id, include_details=True)
        if not isinstance(state, Mapping):
            raise GatewayInputError("CANDIDATE_TASK_STATE_REQUIRED")
        base = str(state.get("controller_revision") or "").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", base):
            raise GatewayInputError("CANDIDATE_CONTROLLER_REVISION_REQUIRED")
        contract = state.get("contract") if isinstance(state.get("contract"), Mapping) else {}
        allowed_files = [str(path) for path in contract.get("allowed_files") or [] if str(path).strip()]
        if not allowed_files:
            raise GatewayInputError("CANDIDATE_ALLOWED_PATHS_REQUIRED")
        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        try:
            identity = resolve_contract_identity(state, expected_task_id=task_id, expected_head=base)
        except RuntimeError as exc:
            raise LifecycleGuardError("CONTRACT_HASH_MISMATCH", str(exc)) from exc
        contract_kind = identity["contract_kind"]
        contract_hash = identity["contract_hash"]
        task_card_hash = identity["task_card_hash"]
        owner_inline_contract = identity["owner_inline_contract"]
        binding = state.get("approved_binding") if isinstance(state.get("approved_binding"), Mapping) else {}
        approval_grant = (state.get("integration_approval_grant") if isinstance(state.get("integration_approval_grant"), Mapping) else None) or (binding.get("approval_grant") if isinstance(binding.get("approval_grant"), Mapping) else None)
        persisted_authorization = state.get("integration_authorization") if isinstance(state.get("integration_authorization"), Mapping) else {}
        expected_integration_head = str(persisted_authorization.get("expected_canonical_head") or base)
        live_head = base
        if isinstance(state.get("integration_approval_grant"), Mapping):
            controller_root = Path(str(contract.get("controller_repo_root") or CANONICAL_SOURCE_ROOT)).expanduser().resolve()
            live_head_result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=controller_root, capture_output=True, text=True, check=False)
            live_head = live_head_result.stdout.strip()
            if live_head_result.returncode != 0 or live_head != expected_integration_head:
                raise GatewayInputError("CANDIDATE_INTEGRATE_HEAD_DRIFT")
        if contract_kind == ContractKind.TRACKED_TASK_CARD.value and not re.fullmatch(r"[0-9a-f]{64}", task_card_hash):
            raise LifecycleGuardError("CANDIDATE_TASK_CARD_HASH_REQUIRED", "tracked candidate integration requires a task card hash")
        if contract_kind == ContractKind.OWNER_INLINE.value and not contract_hash:
            raise LifecycleGuardError("CANDIDATE_OWNER_INLINE_CONTRACT_REQUIRED", "Owner Inline integration requires a contract hash")
        if not approval_grant:
            raise LifecycleGuardError("APPROVAL_REVALIDATION_REQUIRED", "integration requires a persisted versioned approval binding")
        approval_receipt = validate_approval_grant(
            approval_grant,
            task_id=task_id,
            attempt_id=str(state.get("attempt_id") or ""),
            action_type=LifecycleActionType.CANDIDATE_INTEGRATE.value if isinstance(state.get("integration_approval_grant"), Mapping) else LifecycleActionType.CANDIDATE_APPROVE.value,
            task_card_hash=task_card_hash,
            contract_kind=contract_kind,
            contract_hash=contract_hash,
            owner_inline_contract=owner_inline_contract,
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            full_tool_schema_hash=FULL_TOOL_SCHEMA_HASH,
            permission_policy_hash=PERMISSION_POLICY_HASH,
            lifecycle_revision=LIFECYCLE_REVISION,
            server_instance_id=SERVER_INSTANCE_ID,
            allow_consumed=True,
        )
        action_request = {**dict(arguments), "allowed_files": allowed_files, "source_attempt_id": state.get("attempt_id"), "candidate_binding": {
            "candidate_commit_sha": packet.get("candidate_commit_sha") or state.get("candidate_commit_sha"),
            "candidate_tree_sha": packet.get("candidate_tree_sha") or state.get("candidate_tree_sha"),
            "candidate_state_hash": packet.get("candidate_state_hash") or state.get("candidate_state_hash"),
            "verified_receipt_hash": packet.get("verified_receipt_hash") or state.get("verified_receipt_hash"),
        }}
        action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.CANDIDATE_INTEGRATE,
            request=action_request,
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            expected_head=live_head,
            allowed_paths=allowed_files,
            mutation=True,
            permission_profile=PermissionProfile.INTEGRATE,
            mutation_domain=MutationDomain.INTEGRATION,
        )
        guard_receipt = pre_action_guard(action, request={"allowed_files": allowed_files}, current_head=live_head, tool_manifest_hash=TOOL_MANIFEST_REVISION)
        result = self.service.integrate_approved(
            task_id,
            integration_branch=branch,
            runtime_identity={
                **identity,
                "tool_manifest_hash": TOOL_MANIFEST_REVISION,
                "full_tool_schema_hash": FULL_TOOL_SCHEMA_HASH,
                "permission_policy_hash": PERMISSION_POLICY_HASH,
                "lifecycle_revision": LIFECYCLE_REVISION,
                "server_instance_id": SERVER_INSTANCE_ID,
            },
        )
        payload = self._recovery_payload(result, operation="candidate_integrate", include_state=True)
        payload["guard_receipt"] = guard_receipt
        payload["approval_revalidation"] = approval_receipt
        return payload

    def _candidate_dispose(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _text(arguments.get("task_id"), "task_id")
        disposition = str(arguments.get("disposition") or "").strip().upper()
        if disposition not in {"REJECTED", "SUPERSEDED"}:
            raise GatewayInputError("disposition must be REJECTED or SUPERSEDED")
        superseded_by = str(arguments.get("superseded_by") or "").strip() or None
        if disposition == "SUPERSEDED" and not superseded_by:
            raise GatewayInputError("superseded_by is required for SUPERSEDED")
        state = self.service.get_task_snapshot(task_id, include_details=True)
        if not isinstance(state, Mapping):
            raise GatewayInputError("CANDIDATE_TASK_STATE_REQUIRED")
        base = str(state.get("controller_revision") or "").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", base):
            raise GatewayInputError("CANDIDATE_CONTROLLER_REVISION_REQUIRED")
        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        action_request = {**dict(arguments), "source_attempt_id": state.get("attempt_id"), "candidate_binding": {
            "candidate_commit_sha": packet.get("candidate_commit_sha") or state.get("candidate_commit_sha"),
            "candidate_tree_sha": packet.get("candidate_tree_sha") or state.get("candidate_tree_sha"),
            "candidate_state_hash": packet.get("candidate_state_hash") or state.get("candidate_state_hash"),
            "verified_receipt_hash": packet.get("verified_receipt_hash") or state.get("verified_receipt_hash"),
        }}
        action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.CANDIDATE_DISPOSE,
            request=action_request,
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            expected_head=base,
            allowed_paths=[],
            mutation=True,
            permission_profile=PermissionProfile.CANDIDATE,
            mutation_domain=MutationDomain.CANDIDATE_REF,
        )
        guard_receipt = pre_action_guard(action, request={}, current_head=base, tool_manifest_hash=TOOL_MANIFEST_REVISION)
        result = self.service.dispose_candidate(task_id, disposition=disposition, superseded_by=superseded_by)
        payload = self._recovery_payload(result, operation="candidate_dispose", include_state=True)
        payload["guard_receipt"] = guard_receipt
        return payload

    def _workspace_snapshot(self) -> dict[str, Any]:
        status = _git("status", "--porcelain=v1")
        branch = _git("branch", "--show-current").strip()
        head = _git("rev-parse", "HEAD").strip()
        worktree_lines = _git("worktree", "list", "--porcelain").splitlines()
        worktrees = [line.removeprefix("worktree ") for line in worktree_lines if line.startswith("worktree ")]
        actionable = self.service.list_actionable_tasks()
        return {
            "schema": "nexus.workspace_snapshot.v1",
            "root": str(CANONICAL_SOURCE_ROOT),
            "branch": branch,
            "head": head,
            "clean": not bool(status.strip()),
            "registered_worktrees": worktrees,
            "registered_worktree_count": len(worktrees),
            "actionable_count": int(actionable.get("actionable_count", 0)),
            "target_root": str(CANONICAL_SOURCE_ROOT.parent / "nexus-runtime-targets"),
        }

    def _read(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        path = _safe_relative_path(arguments.get("path"))
        if not path.is_file():
            raise GatewayInputError("path is not a regular file")
        if path.stat().st_size > MAX_READ_BYTES:
            raise GatewayInputError(f"path exceeds {MAX_READ_BYTES} bytes")
        start = max(1, int(arguments.get("start_line", 1)))
        limit = min(1000, max(1, int(arguments.get("max_lines", 200))))
        lines = path.read_text(encoding="utf-8").splitlines()
        selected = lines[start - 1 : start - 1 + limit]
        return {"schema": "nexus.workspace_read.v1", "path": str(path.relative_to(CANONICAL_SOURCE_ROOT)), "start_line": start, "lines": selected, "truncated": start - 1 + limit < len(lines)}

    def _search(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        pattern = _text(arguments.get("pattern"), "pattern", max_length=200)
        _, path = _safe_search_target(arguments.get("path", "."))
        relative = str(path.relative_to(CANONICAL_SOURCE_ROOT)) or "."
        rg = shutil.which("rg")
        if rg is None:
            matches, truncated = _python_literal_search(root=CANONICAL_SOURCE_ROOT, target=path, pattern=pattern)
            backend = "python"
        else:
            try:
                matches, truncated = _run_rg_literal_search(
                    executable=rg, root=CANONICAL_SOURCE_ROOT, relative=relative, pattern=pattern
                )
            except FileNotFoundError:
                matches, truncated = _python_literal_search(root=CANONICAL_SOURCE_ROOT, target=path, pattern=pattern)
                backend = "python"
            else:
                backend = "ripgrep"
        return {"schema": "nexus.workspace_search.v1", "pattern": pattern, "path": relative, "matches": matches, "truncated": truncated, "backend": backend}

    def _diff(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        base = arguments.get("base_revision")
        if base is not None and not _SHA_RE.fullmatch(str(base)):
            raise GatewayInputError("base_revision must be an exact lowercase Git SHA")
        args = ["diff", "--no-ext-diff", "--unified=3"]
        if bool(arguments.get("staged", False)):
            args.append("--cached")
        if base:
            args.append(str(base))
        output = _bounded_text(_git(*args), "git diff")
        return {"schema": "nexus.workspace_diff.v1", "base_revision": base, "staged": bool(arguments.get("staged", False)), "diff": output}

    @staticmethod
    def _task_id(arguments: Mapping[str, Any], what: str, why: str, allowed: list[str]) -> str:
        explicit = str(arguments.get("task_id") or "").strip()
        if explicit:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", explicit):
                raise GatewayInputError("task_id must be a stable bounded slug")
            return explicit
        seed = json.dumps([what, why, sorted(allowed)], ensure_ascii=False, separators=(",", ":"))
        return "dispatch-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    def _task_run(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        try:
            reject_caller_route_overrides(arguments)
        except ValueError as exc:
            raise GatewayInputError(str(exc)) from exc
        what = _text(arguments.get("what"), "what")
        why = _text(arguments.get("why"), "why")
        allowed = [str(path).strip() for path in (arguments.get("allowed_files") or []) if str(path).strip()]
        if not allowed or len(allowed) > 4:
            raise GatewayInputError("allowed_files must contain 1-4 bounded paths")
        for path in allowed:
            _safe_relative_path(path, "allowed_files")
        verifiers = [str(command).strip() for command in (arguments.get("verifier_commands") or []) if str(command).strip()]
        task_id = self._task_id(arguments, what, why, allowed)
        if len(verifiers) > 1:
            raise GatewayInputError("verifier_commands supports exactly one isolated command")
        revision = _git("rev-parse", "HEAD").strip()
        try:
            execution_context = build_mcp_execution_context(
                task_id=task_id,
                workspace_revision=revision,
                allowed_files=allowed,
                verifier_commands=verifiers,
            )
            result = execute_canonical_product_task(
                f"{what}\n\nAcceptance context: {why}",
                CANONICAL_SOURCE_ROOT,
                execution_context=execution_context,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise GatewayInputError(f"canonical_product_runtime_failed_closed:{exc}") from exc
        receipt = dict(result.receipt)
        canonical_execution = (
            dict(receipt.get("canonical_execution"))
            if isinstance(receipt.get("canonical_execution"), Mapping)
            else {}
        )
        return {
            "schema": "nexus.mcp_canonical_runtime.v1",
            "status": "SUCCEEDED" if bool(result) else "BLOCKED",
            "task_id": str(receipt.get("task_id") or task_id),
            "execution_decision_authority": result.execution_decision_authority,
            "canonical_execution": canonical_execution,
            "execution_world": str(canonical_execution.get("execution_world") or ""),
            "canonical_execution_topology": str(
                canonical_execution.get("canonical_execution_topology") or ""
            ),
            "root_receipt": dict(result.root_receipt),
            "root_receipt_valid": result.root_receipt_valid,
            "root_receipt_blockers": list(result.root_receipt_blockers),
            "runtime_receipt_path": result.receipt_path,
            "runtime_dispatched": True,
            "formal_workspace_mutated": False,
            "production_ingress_count": result.production_ingress_count,
            "production_runtime_entry_count": result.production_runtime_entry_count,
            "public_claim_allowed": False,
        }

    @staticmethod
    def _canonical_request(task_id: str, what: str, why: str, allowed: list[str], verifiers: list[str], base: str, *, action: Optional[Mapping[str, Any]] = None, contract_binding: Optional[Mapping[str, Any]] = None, controller_dirty_baseline_authorization: Optional[Mapping[str, Any]] = None, bound_action_request: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        target_worktree_root = CANONICAL_SOURCE_ROOT.parent / "nexus-runtime-targets"
        request = {
            "task_id": task_id, "what": what, "why": why,
            "controller_revision": base, "target_base_revision": base,
            "controller_repo_root": str(CANONICAL_SOURCE_ROOT),
            "target_repo_root": str(target_worktree_root / task_id),
            "target_worktree_root": str(target_worktree_root),
            "allowed_files": allowed, "verifier_commands": verifiers,
        }
        if contract_binding:
            request.update({
                "contract_kind": contract_binding.get("contract_kind"),
                "contract_hash": contract_binding.get("contract_hash"),
                "owner_inline_contract": contract_binding.get("owner_inline_contract"),
                "task_card_path": contract_binding.get("task_card_path"),
                "task_card_hash": contract_binding.get("task_card_hash"),
            })
        if controller_dirty_baseline_authorization:
            request["controller_dirty_baseline_authorization"] = dict(controller_dirty_baseline_authorization)
        if action:
            request["action"] = dict(action)
            request["action_id"] = action.get("action_id")
            request["attempt_id"] = action.get("attempt_id")
            request["idempotency_key"] = action.get("idempotency_key")
            request["action_request_hash"] = action.get("request_hash")
        if bound_action_request is not None:
            request["bound_action_request"] = dict(bound_action_request)
        return request

    @staticmethod
    def _assist_prompt(what: str, why: str, allowed: list[str], verifiers: list[str]) -> str:
        context: list[str] = []
        for raw in allowed:
            path = _safe_relative_path(raw, "allowed_files")
            if path.is_file() and path.stat().st_size <= 128 * 1024:
                context.append(f"FILE {raw}\n{path.read_text(encoding='utf-8')}\nEND FILE")
        return (
            "You are a bounded patch proposer. Use plan/read-only mode. Do not edit files, run tools, or commit. "
            "Return only JSON matching the requested schema, with a unified diff in patch. "
            "The patch string must begin exactly with diff --git and must not use markdown fences. "
            f"WHAT: {what}\nWHY: {why}\nALLOWED FILES: {', '.join(allowed)}\nVERIFIERS: {verifiers}\n" + "\n".join(context)
        )

    @staticmethod
    def _run_agy_plan(*, prompt: str, allowed_files: list[str], provider: str, model: str = "", explicit_effort: str = "") -> dict[str, Any]:
        """Run any registered assisted provider with one bounded JSON contract.

        The historical name is retained for compatibility, but the provider
        edge is no longer hard-coded to Agy. Unknown providers fail closed;
        registered providers still require an installed executable and return
        parser/transport failures as non-success receipts.
        """
        requested = str(provider or "auto").strip().lower() or "auto"
        if requested == "auto":
            requested = os.environ.get("NEXUS_ASSIST_PROVIDER", "agy").strip().lower() or "agy"
        metadata = ONLINE_CLI_SPEC_REGISTRY.get(requested)
        if metadata is None:
            return {"provider": requested, "blocker": "ASSIST_PROVIDER_NOT_REGISTERED"}
        binary_env = metadata.get("binary_env", "")
        configured = os.environ.get(binary_env, "").strip() if binary_env else ""
        executable = configured or shutil.which(metadata.get("binary_name", requested))
        if not executable or not Path(executable).is_file():
            return {"provider": requested, "blocker": "ASSIST_PROVIDER_UNAVAILABLE"}
        schema = json.dumps({"type": "object", "required": ["patch"], "properties": {"patch": {"type": "string"}, "summary": {"type": "string"}, "tests": {"type": "array", "items": {"type": "string"}}}}, separators=(",", ":"))
        selected_model = str(model or os.environ.get("NEXUS_ASSIST_MODEL", "") or metadata.get("default_model", "")).strip()
        if requested == "agy":
            try:
                command = _compile_agy_command(
                    executable=executable,
                    model=selected_model,
                    prompt=prompt,
                    json_schema=schema,
                    explicit_effort=explicit_effort,
                )
            except GatewayInputError as exc:
                return {
                    "provider": requested,
                    "model": selected_model,
                    "blocker": "AGY_ARGUMENT_COMPILATION_CONFLICT",
                    "error": str(exc),
                }
        elif requested == "cline":
            # Cline's JSON mode is non-interactive; yolo is restricted to the
            # bounded canonical apply path or an isolated Target by the caller.
            cline_model = selected_model or "glm-5.2"
            if "/" not in cline_model:
                cline_model = f"cline-pass/{cline_model}"
            command = [executable, "--json", "--plan", "--auto-approve", "false", "--thinking", "none", "--timeout", str(CLINE_RUN_TIMEOUT_SECONDS), "--model", cline_model, prompt]
        elif requested == "gemini":
            command = [executable, "--skip-trust", "--approval-mode", "auto_edit", "-m", selected_model, "-p", prompt, "--output-format", "json"]
        elif requested == "opencode":
            command = [executable, "run", "--model", selected_model, prompt]
        elif requested == "codex":
            command = [
                executable,
                "exec",
                "--json",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "-m",
                selected_model,
                prompt,
            ]
        elif requested == "mimo":
            command = [executable, "run", "--model", selected_model, prompt]
        elif requested == "ollama":
            command = [executable, "run", selected_model, prompt]
        elif requested == "grok":
            command = [executable, "--model", selected_model, "--single", prompt, "--output-format", "json", "--no-alt-screen"]
        else:
            command = [executable, "--model", selected_model, "--prompt", prompt]
        provider_timeout = CLINE_RUN_TIMEOUT_SECONDS + 5 if requested == "cline" else 30
        try:
            result = subprocess.run(command, cwd=CANONICAL_SOURCE_ROOT, capture_output=True, text=True, timeout=provider_timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            return {
                "provider": requested,
                "model": selected_model,
                "blocker": "ASSIST_PROVIDER_TIMEOUT",
                "timeout_seconds": provider_timeout,
                "error": str(exc),
                "tool_policy_enforcement": "cline_plan_auto_approve_false_allowlist_not_enforced" if requested == "cline" else "provider_specific",
            }
        if result.returncode != 0:
            return {"provider": requested, "model": selected_model, "blocker": "ASSIST_PROVIDER_FAILED", "error": result.stderr.strip()[-1000:]}
        def decode_object(text: str) -> dict[str, Any] | None:
            candidates = [text.strip()]
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match and match.group(0) not in candidates:
                candidates.append(match.group(0))
            for candidate_text in candidates:
                try:
                    candidate = json.loads(candidate_text)
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict):
                    return candidate
            return None

        payload = decode_object(result.stdout)
        if requested == "cline" and isinstance(payload, dict) and "patch" not in payload:
            payload = None
        if payload is None:
            for line in reversed(result.stdout.splitlines()):
                try:
                    candidate = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(candidate, dict):
                    continue
                nested_texts = [str(candidate.get("text") or "")]
                event = candidate.get("event")
                if isinstance(event, dict):
                    nested_texts.append(str(event.get("text") or ""))
                for nested_text in nested_texts:
                    if nested_text:
                        payload = decode_object(nested_text)
                        if payload is not None:
                            break
                if payload is not None:
                    break
                if requested != "cline":
                    payload = candidate
                    break
            if payload is None:
                return {"provider": requested, "model": selected_model, "blocker": "ASSIST_PROVIDER_MALFORMED_OUTPUT"}
        if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
            payload = payload["result"]
        if not isinstance(payload, dict):
            return {"provider": requested, "model": selected_model, "blocker": "ASSIST_PROVIDER_MALFORMED_OUTPUT"}
        payload["provider"] = requested
        payload["model"] = selected_model
        if requested == "cline":
            payload["tool_policy_enforcement"] = "cline_plan_auto_approve_false_allowlist_not_enforced"
        return payload

    def _finish(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        lane = _text(arguments.get("execution_lane"), "execution_lane").upper()
        if lane == "DIRECT_CANONICAL":
            request = dict(arguments.get("request") or {})
            if not request:
                task_id = _text(arguments.get("task_id"), "task_id")
                base = arguments.get("base_sha") or arguments.get("controller_revision")
                if not isinstance(base, str) or not _SHA_RE.fullmatch(base):
                    raise GatewayInputError("base_sha is required for minimal Direct finish")
                allowed = [str(path).strip() for path in (arguments.get("allowed_files") or []) if str(path).strip()]
                if not allowed or len(allowed) > 4:
                    raise GatewayInputError("allowed_files is required for minimal Direct finish")
                for path in allowed:
                    _safe_relative_path(path, "allowed_files")
                request = self._canonical_request(
                    task_id,
                    "Complete bounded canonical task",
                    "Finish the prior gateway Direct handoff",
                    allowed,
                    list(arguments.get("verifier_commands") or ["git diff --check"]),
                    base,
                )
            request.setdefault("execution_lane", "DIRECT_CANONICAL")
            request.setdefault("primary_agent", True)
            request.setdefault("worker", "primary")
            result = self.service.complete_direct_canonical(request, expected_commit_sha=arguments.get("expected_commit_sha"))
            action_payload = request.get("action") if isinstance(request.get("action"), Mapping) else None
            if action_payload is not None:
                result["guard_receipt"] = post_action_receipt_formatter(
                    action=action_payload,
                    status="COMPLETED",
                    commit_sha=result.get("commit_sha"),
                    receipt=result,
                )
            return result
        if lane == "ISOLATED_TARGET":
            task_id = _text(arguments.get("task_id"), "task_id")
            fields = ("candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash")
            values = {field: _text(arguments.get(field), field) for field in fields}
            return self.service.owner_finish(task_id, **values)
        raise GatewayInputError("execution_lane is unsupported")

    def _call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name == "nexus_gateway_status":
            return self._gateway_status()
        if name == "nexus_workspace_snapshot":
            return self._workspace_snapshot()
        if name == "nexus_read":
            return self._read(arguments)
        if name == "nexus_search":
            return self._search(arguments)
        if name == "nexus_git_diff":
            return self._diff(arguments)
        if name == "nexus_task_run":
            return self._task_run(arguments)
        if name == "nexus_worker_candidate":
            return self._worker_candidate(arguments)
        if name == "nexus_task_status":
            task_id = _text(arguments.get("task_id"), "task_id")
            assisted = self._assist_read(task_id)
            if assisted is not None:
                return self._assist_response(self._assist_refresh(task_id) or assisted, operation="status")
            status = self.service.get_task_snapshot(task_id)
            return status or self._task_not_found(task_id, operation="status")
        if name == "nexus_task_wait":
            task_id = _text(arguments.get("task_id"), "task_id")
            timeout = min(60.0, max(0.0, float(arguments.get("timeout_seconds", 10.0))))
            poll = min(5.0, max(0.01, float(arguments.get("poll_interval_seconds", 0.25))))
            if self._assist_read(task_id) is not None:
                return self._assist_wait(task_id, timeout_seconds=timeout, poll_interval_seconds=poll)
            waited = self.service.wait_task(task_id, timeout_seconds=timeout, poll_interval_seconds=poll)
            return waited or self._task_not_found(
                task_id,
                operation="wait",
                timeout_seconds=timeout,
                poll_interval_seconds=poll,
            )
        if name == "nexus_task_finish":
            return self._finish(arguments)
        if name == "nexus_task_cancel":
            task_id = _text(arguments.get("task_id"), "task_id")
            if self._assist_read(task_id) is not None:
                return self._assist_cancel(task_id)
            return self.service.cancel_task(task_id)
        if name == "nexus_task_list_actionable":
            return self._task_list_actionable(arguments)
        if name == "nexus_task_reconcile":
            return self._task_reconcile(arguments)
        if name == "nexus_task_retry":
            return self._task_retry(arguments)
        if name == "nexus_task_resume":
            return self._task_resume(arguments)
        if name == "nexus_assist_submit":
            return self._assist_submit(arguments)
        if name == "nexus_assist_result":
            task_id = _text(arguments.get("task_id"), "task_id")
            job = self._assist_read(task_id)
            if job is None:
                raise KeyError(f"unknown task_id: {task_id}")
            return self._assist_response(self._assist_refresh(task_id) or job, operation="result")
        if name == "nexus_assist_cancel":
            return self._assist_cancel(_text(arguments.get("task_id"), "task_id"))
        if name == "nexus_provider_preflight":
            return self._provider_preflight(arguments)
        if name == "nexus_task_card_create":
            return self._task_card_create(arguments)
        if name == "nexus_model_probe":
            return self._model_probe_submit(arguments)
        if name == "nexus_model_probe_result":
            task_id = _text(arguments.get("task_id"), "task_id")
            job = self._assist_read(task_id)
            if job is None or job.get("job_kind") != "model_probe":
                raise KeyError(f"unknown model_probe task_id: {task_id}")
            return self._assist_response(self._assist_refresh(task_id) or job, operation="result")
        if name == "nexus_candidate_approve":
            return self._candidate_approve(arguments)
        if name == "nexus_candidate_bind_integration":
            return self._candidate_bind_integration(arguments)
        if name == "nexus_candidate_integrate":
            return self._candidate_integrate(arguments)
        if name == "nexus_candidate_dispose":
            return self._candidate_dispose(arguments)
        raise GatewayInputError(f"unknown public tool: {name}")

    def handle(self, request: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        method = request.get("method")
        request_id = request.get("id")
        if method == "notifications/initialized" or request_id is None:
            return None
        if method == "initialize":
            return {
                "jsonrpc": "2.0", "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": GATEWAY_NAME,
                        "title": PUBLIC_APP_NAME,
                        "version": GATEWAY_VERSION,
                        "toolManifestRevision": TOOL_MANIFEST_REVISION,
                        "fullToolSchemaHash": FULL_TOOL_SCHEMA_HASH,
                        "permissionPolicyHash": PERMISSION_POLICY_HASH,
                        "taskContractRevision": TASK_CONTRACT_REVISION,
                        "lifecycleRevision": LIFECYCLE_REVISION,
                        "serverInstanceId": SERVER_INSTANCE_ID,
                        "serverStartedAt": SERVER_STARTED_AT,
                    },
                },
            }
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.tool_specs()}}
        if method == "tools/call":
            params = request.get("params") or {}
            try:
                return self._success(request_id, self._call_tool(str(params.get("name", "")), params.get("arguments") or {}))
            except Exception as exc:
                return self._error(request_id, exc)
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"method not found: {method}"}}

    def serve(self, input_stream, output_stream) -> None:
        for line in input_stream:
            if not line.strip():
                continue
            response = self.handle(json.loads(line))
            if response is not None:
                output_stream.write(json.dumps(response, sort_keys=True, ensure_ascii=False) + "\n")
                output_stream.flush()


# Single manifest truth: every public name is derived from the actual MCP
# schema returned by tools/list.  No second hand-maintained inventory can drift
# from connector discovery, status, health, or recommended-tool validation.
PUBLIC_TOOL_NAMES = tuple(spec["name"] for spec in UnifiedMCPGateway.tool_specs())
TOOL_MANIFEST_REVISION = hashlib.sha256(
    json.dumps(PUBLIC_TOOL_NAMES, separators=(",", ":")).encode("utf-8")
).hexdigest()
FULL_TOOL_SCHEMA_HASH = hashlib.sha256(
    json.dumps(UnifiedMCPGateway.tool_specs(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
).hexdigest()
try:
    SERVER_REPO_HEAD_AT_START = _git("rev-parse", "HEAD").strip() or "unknown"
except Exception:
    SERVER_REPO_HEAD_AT_START = "unknown"
# Freeze the runtime source comparison set and its digests at gateway load so
# the freshness baseline never drifts just because a later import loads another
# Nexus module.  A failed start fingerprint is treated as unknown and therefore
# drifts against any readable current fingerprint (fail closed).
RUNTIME_SOURCE_PATHS = _loaded_runtime_source_paths()
try:
    RUNTIME_SOURCE_SHA256_AT_START = _hash_source_paths(RUNTIME_SOURCE_PATHS)
except Exception:
    RUNTIME_SOURCE_SHA256_AT_START = ""
ACTION_CONTRACT_SHA256_AT_START, _ACTION_CONTRACT_OK, _ACTION_CONTRACT_REASONS = _action_contract_fingerprint()
PERMISSION_ENFORCEMENT_SHA256_AT_START, _PERMISSION_ENFORCEMENT_OK, _PERMISSION_ENFORCEMENT_REASONS = _permission_enforcement_fingerprint()
configure_runtime_manifest_hash(TOOL_MANIFEST_REVISION)
