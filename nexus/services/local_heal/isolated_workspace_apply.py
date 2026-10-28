from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any

from nexus.services.local_heal.armor_artifact_storage import make_isolated_workspace


@dataclass(frozen=True)
class IsolatedApplyRequest:
    task_id: str
    source_root: str
    target_file: str
    unified_diff: str
    selected_candidate_hash: str
    work_dir: str = ""
    mutation_allowed: bool = False
    search_text: str = ""
    # Files the verifier command reads (e.g. ``repro.py``); copied untracked so the isolated
    # verifier can run, never part of the applied diff.
    verifier_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class IsolatedApplyReceipt:
    task_id: str
    workspace_path: str
    target_file: str
    patch_apply_status: str
    patch_apply_error: str
    selected_candidate_hash: str
    applied_patch_hash: str
    selected_candidate_hash_matches_applied: bool
    candidate_output_isolated: bool
    mutation_allowed: bool
    public_claim_allowed: bool = False
    production_ready: bool = False
    applied_patch_hash_source: str = ""


_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")
_GIT_TRAILING_WS = " \t\r"  # what git itself strips/ignores; not \f, NBSP, U+2028 ...
_NO_EOL_MARKER = "\\ No newline at end of file"


def _canonicalize_effective_diff(diff_text: str) -> str:
    """Canonicalize one target's selected/applied effect for hash binding.

    Git may render a different unchanged context window around the same
    payload.  Keep the nearest unchanged line on either side of the payload;
    a side whose nearest context line is blank keeps no anchor (git may add or
    drop such lines), and the location itself is bound by ``git apply`` with
    the patch's own context plus the target-file gate, not by this identity.
    Every added or removed payload line remains part of the identity.  Target,
    source, successful apply, isolation, and verifier checks are separate gates.

    Fixed (#2821):
    * ``\\ No newline at end of file`` is part of the identity: it attaches to
      the line it follows, so ``Y\n`` and ``Y`` canonicalize differently.
    * Hunks are consumed by their ``@@ -a,b +c,d @@`` counts (as ``git apply``
      does), so ``--- a/..`` / ``+++ b/..`` / ``diff --git`` headers of a
      further file are never read as edited lines; a payload line that merely
      looks like a header (``--- x`` removed, ``+++ y`` added) stays payload.
      Lines beyond the counts are not part of any hunk, as in ``git apply``.

    Accepted, deliberately (#2821):
    * Trailing space, tab and CR (only those: other Unicode whitespace such as
      form feed or NBSP stays identity) are stripped from every line.  This identity
      binds the selected patch to the diff git renders after
      ``git apply --whitespace=fix``, which itself strips trailing whitespace
      and CR from added lines and matches removed/context lines ignoring it;
      the two sides would never bind if byte-exact whitespace were kept.
      Whitespace inside a line (including leading indentation) is kept.
    * Edits that the selected patch gives as separate hunks canonicalize
      differently from the same edits rendered by git as one merged hunk
      (the unchanged lines between them are not in the selected patch).  This
      fails closed (a valid edit may be rejected, never a different edit
      accepted).
    * File identity and non-hunk patch operations (new/deleted files, mode
      changes, binary sections) are not part of this hash: a diff over several
      files canonicalizes as the concatenation of its hunks, header-free.  No
      gate in this function checks the patch scope: ``_patch_scope_violation``
      (#2836) runs before the workspace is created and refuses any patch that
      git itself reads as touching a file other than ``target_file``, creating,
      deleting, renaming, copying or mode-changing anything, carrying binary
      data, or whose hunk payload differs from what git would apply.  Do not
      rely on this identity for any of that.
    """
    output: list[str] = []
    hunk_lines: list[str] = []
    in_hunk = False
    old_left: int | None = None
    new_left: int | None = None
    attachable = False

    def flush_hunk() -> None:
        nonlocal hunk_lines, in_hunk
        if not in_hunk:
            return
        changes = [
            index for index, line in enumerate(hunk_lines) if line.startswith(("+", "-"))
        ]
        if changes:
            first_change, last_change = changes[0], changes[-1]
            start = first_change
            end = last_change
            if start > 0 and hunk_lines[start - 1].startswith(" "):
                start -= 1
            if end + 1 < len(hunk_lines) and hunk_lines[end + 1].startswith(" "):
                end += 1
            hunk_lines[:] = hunk_lines[start : end + 1]
        hunk_lines[:] = [
            line for line in hunk_lines if not (line.startswith(" ") and not line[1:].rstrip(_GIT_TRAILING_WS))
        ]
        old_count = sum(1 for line in hunk_lines if not line.startswith("+"))
        new_count = sum(1 for line in hunk_lines if not line.startswith("-"))
        output.append(f"@@ -0,{old_count} +0,{new_count} @@")
        output.extend(hunk_lines)
        hunk_lines = []
        in_hunk = False

    def hunk_complete() -> bool:
        return old_left is not None and new_left is not None and old_left <= 0 and new_left <= 0

    for raw_line in diff_text.replace("\r\n", "\n").split("\n"):
        line = raw_line.rstrip(_GIT_TRAILING_WS)
        if line.startswith("@@"):
            flush_hunk()
            in_hunk = True
            attachable = False
            header = _HUNK_HEADER_RE.match(line)
            if header:
                old_left = int(header.group(1)) if header.group(1) is not None else 1
                new_left = int(header.group(2)) if header.group(2) is not None else 1
            else:
                old_left = new_left = None
            continue
        if not in_hunk:
            continue
        if raw_line.startswith("diff --git "):
            flush_hunk()
            continue
        if raw_line.startswith("\\"):
            # "\ No newline at end of file" belongs to the line before it.
            if attachable and hunk_lines:
                hunk_lines[-1] = f"{hunk_lines[-1]}\n{_NO_EOL_MARKER}"
            attachable = False
            continue
        if hunk_complete():
            attachable = False
            continue
        if raw_line.startswith(("-", "+", " ")):
            operation = raw_line[0]
            content = raw_line[1:].rstrip(_GIT_TRAILING_WS)
            hunk_lines.append(f"{operation}{content}")
        elif raw_line == "":
            operation = " "
            hunk_lines.append(" ")
        else:
            attachable = False
            continue
        attachable = True
        if old_left is not None and new_left is not None:
            if operation != "+":
                old_left -= 1
            if operation != "-":
                new_left -= 1
    flush_hunk()
    return "\n".join(output).strip(_GIT_TRAILING_WS + "\n")


def _scan_patch(diff_text: str) -> tuple[int, int, int, list[str]]:
    """Return ``(added, deleted, hunks, header_lines)`` consuming hunks as ``git apply`` does."""
    added = deleted = hunks = 0
    old_left = new_left = 0
    headers: list[str] = []
    for raw_line in diff_text.replace("\r\n", "\n").split("\n"):
        if old_left > 0 or new_left > 0:
            if raw_line.startswith("\\"):
                continue
            operation = raw_line[:1] or " "
            if operation == "+":
                added += 1
                new_left -= 1
            elif operation == "-":
                deleted += 1
                old_left -= 1
            else:
                old_left -= 1
                new_left -= 1
            continue
        header = _HUNK_HEADER_RE.match(raw_line.rstrip(_GIT_TRAILING_WS))
        if header:
            hunks += 1
            old_left = int(header.group(1)) if header.group(1) is not None else 1
            new_left = int(header.group(2)) if header.group(2) is not None else 1
        else:
            headers.append(raw_line)
    return added, deleted, hunks, headers


def _hunk_payload_counts(diff_text: str) -> tuple[int, int]:
    """Count added/removed payload lines the way ``git apply`` consumes hunks."""
    added, deleted, _hunks, _headers = _scan_patch(diff_text)
    return added, deleted


_FORBIDDEN_HEADER_RE = re.compile(
    r"^(old mode |new mode |new file mode |deleted file mode |rename |copy |similarity index |"
    r"dissimilarity index |GIT binary patch|Binary files )"
)


_QUOTED_NAME = r'"(?:\\.|[^"\\])*"'
_ESCAPES = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13, '"': 34, "\\": 92}


def _unquote_git_name(text: str) -> str | None:
    """Undo git's C-style path quoting; ``None`` when the text is not a well-formed quoted name."""
    if len(text) < 2 or not (text.startswith('"') and text.endswith('"')):
        return None
    body, out, index = text[1:-1], bytearray(), 0
    while index < len(body):
        char = body[index]
        if char != "\\":
            out += char.encode("utf-8")
            index += 1
            continue
        index += 1
        if index >= len(body):
            return None
        if body[index] in _ESCAPES:
            out.append(_ESCAPES[body[index]])
            index += 1
        elif re.fullmatch(r"[0-7]{3}", body[index : index + 3]):
            out.append(int(body[index : index + 3], 8))
            index += 3
        else:
            return None
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _header_violation(target_file: str, headers: list[str]) -> str | None:
    """Every file header git may read must name ``target_file`` and nothing else (#2836)."""
    allowed = os.path.normpath(target_file)

    def names_target(text: str, prefixes: tuple[str, ...]) -> bool:
        name = text.split("\t", 1)[0].rstrip(_GIT_TRAILING_WS)
        if name.startswith('"'):
            unquoted = _unquote_git_name(name)
            if unquoted is None:
                return False
            name = unquoted
        if name == "/dev/null":
            return False  # create/delete of the tracked target is never a plain hunk edit
        for prefix in prefixes:
            if name.startswith(prefix) and os.path.normpath(name[len(prefix) :]) == allowed:
                return True
        return os.path.normpath(name) == allowed

    for line in headers:
        if _FORBIDDEN_HEADER_RE.match(line):
            return f"non-hunk operation header: {line[:80]!r}"
        if line.startswith("diff --git "):
            rest = line[len("diff --git ") :]
            quoted = re.fullmatch(rf"({_QUOTED_NAME}) ({_QUOTED_NAME})", rest)
            pair = (
                (_unquote_git_name(quoted.group(1)), _unquote_git_name(quoted.group(2)))
                if quoted
                else None
            )
            if rest not in {
                f"a/{target_file} b/{target_file}",
                f"{target_file} {target_file}",
            } and pair not in {
                (f"a/{target_file}", f"b/{target_file}"),
                (target_file, target_file),
            }:
                return f"diff header names another path: {line[:120]!r}"
        elif line.startswith("--- ") and not names_target(line[4:], ("a/",)):
            return f"--- header names another path: {line[:120]!r}"
        elif line.startswith("+++ ") and not names_target(line[4:], ("b/",)):
            return f"+++ header names another path: {line[:120]!r}"
    return None


def _git_apply_query(flags: list[str], diff_bytes: bytes) -> subprocess.CompletedProcess[bytes]:
    with tempfile.TemporaryDirectory(prefix="armor-scope-") as scratch:
        return subprocess.run(
            ["git", "apply", *flags, "--unidiff-zero", "-"],
            cwd=scratch,
            input=diff_bytes,
            shell=False,
            capture_output=True,
            timeout=10.0,
        )


def _patch_scope_violation(target_file: str, diff_content: str) -> tuple[str, str] | None:
    """Return ``(kind, detail)`` when the selected patch is not exactly an edit of ``target_file``.

    Fail closed (#2836): the allowed file set of this receipt is ``target_file``
    alone (``verifier_files`` are copied untracked and never part of the applied
    diff).  Git's own reading of the patch (``git apply --numstat -z`` and
    ``--summary``) must show hunks for that one path only, with no create, delete,
    rename, copy or mode line and no binary section, and the hunk payload counted
    here must equal what git reports, so no operation escapes the canonical
    identity.  ``kind`` is ``unparseable`` when git cannot read the patch at all.
    """
    diff_bytes = diff_content.encode("utf-8")
    try:
        numstat = _git_apply_query(["--numstat", "-z"], diff_bytes)
        summary = _git_apply_query(["--summary"], diff_bytes)
    except (OSError, subprocess.SubprocessError) as exc:
        return "unparseable", f"{type(exc).__name__}: {exc}"
    for res in (numstat, summary):
        if res.returncode != 0:
            detail = (
                res.stderr.decode("utf-8", "replace").strip()
                or "git apply could not read the patch"
            )
            return "unparseable", detail[:500]
    _added, _deleted, hunk_count, header_lines = _scan_patch(diff_content)
    header_problem = _header_violation(target_file, header_lines)
    if header_problem:
        return "scope", header_problem[:500]
    if hunk_count == 0:
        return "scope", "patch carries no hunk"
    # A header-less (traditional) patch makes git guess create/delete for a hunk that starts
    # from or ends at an empty file; that is a plain edit of the tracked target, never a
    # mode-carrying file operation (those headers are refused above).
    benign = {f" create {target_file}", f" delete {target_file}"}
    summary_lines = [
        line
        for line in summary.stdout.decode("utf-8", "replace").splitlines()
        if line.strip() and line.rstrip() not in benign
    ]
    if summary_lines:
        return "scope", f"non-hunk operation: {summary_lines[0].strip()}"[:500]
    allowed = os.path.normpath(target_file)
    git_added = git_deleted = 0
    entries = [entry for entry in numstat.stdout.decode("utf-8", "replace").split("\0") if entry]
    if not entries:
        return "unparseable", "git reports no file in the patch"
    for entry in entries:
        parts = entry.split("\t", 2)
        if len(parts) != 3:
            return "scope", f"unreadable git numstat entry: {entry!r}"[:500]
        added_text, deleted_text, path = parts
        if os.path.normpath(path) != allowed:
            return "scope", f"patch touches {path!r}, allowed only {target_file!r}"
        if not (added_text.isdigit() and deleted_text.isdigit()):
            return "scope", f"binary patch for {path!r}"
        git_added += int(added_text)
        git_deleted += int(deleted_text)
    if (git_added, git_deleted) != _hunk_payload_counts(diff_content):
        return "scope", "hunk payload does not cover every operation git would apply"
    return None


def run_isolated_workspace_apply(request: IsolatedApplyRequest) -> IsolatedApplyReceipt:
    if not request.mutation_allowed:
        return IsolatedApplyReceipt(
            task_id=request.task_id,
            workspace_path="",
            target_file=request.target_file,
            patch_apply_status="blocked",
            patch_apply_error="mutation_not_allowed",
            selected_candidate_hash=request.selected_candidate_hash,
            applied_patch_hash="",
            selected_candidate_hash_matches_applied=False,
            candidate_output_isolated=False,
            mutation_allowed=False,
        )

    normalized = os.path.normpath(request.target_file)
    if normalized.startswith("/") or normalized.startswith("..") or ".." in normalized.split(os.sep):
        return IsolatedApplyReceipt(
            task_id=request.task_id,
            workspace_path="",
            target_file=request.target_file,
            patch_apply_status="blocked",
            patch_apply_error="path_traversal_detected",
            selected_candidate_hash=request.selected_candidate_hash,
            applied_patch_hash="",
            selected_candidate_hash_matches_applied=False,
            candidate_output_isolated=False,
            mutation_allowed=True,
        )

    diff_content = request.unified_diff
    if not diff_content.endswith("\n"):
        diff_content += "\n"
    # #2836: refuse before any workspace exists (and before C6BD may retry) unless git
    # itself reads the patch as hunk edits of target_file only.
    scope_violation = _patch_scope_violation(request.target_file, diff_content)
    if scope_violation is not None:
        kind, detail = scope_violation
        return IsolatedApplyReceipt(
            task_id=request.task_id,
            workspace_path="",
            target_file=request.target_file,
            patch_apply_status="failed" if kind == "unparseable" else "blocked",
            patch_apply_error=f"patch_scope_{kind}: {detail}",
            selected_candidate_hash=request.selected_candidate_hash,
            applied_patch_hash="",
            selected_candidate_hash_matches_applied=False,
            candidate_output_isolated=False,
            mutation_allowed=True,
        )

    # Durable parent by default (.nexus/artifacts/local_armor/workspaces, or a home-relative
    # root when that one is sandbox-denied, #2966).
    # When work_dir is set, isolate under that durable/operator-supplied parent.
    tmpdir = str(make_isolated_workspace(work_dir=request.work_dir or None, prefix="armor-apply-"))

    try:
        subprocess.run(["git", "init"], cwd=tmpdir, shell=False, capture_output=True, timeout=5.0, check=True)

        src_path = os.path.join(request.source_root, request.target_file)
        dest_path = os.path.join(tmpdir, request.target_file)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        if not os.path.exists(src_path):
            with open(dest_path, "w", encoding="utf-8") as f:
                pass
        else:
            shutil.copy2(src_path, dest_path)
        _copy_verifier_files(request, tmpdir)

        subprocess.run(["git", "add", request.target_file], cwd=tmpdir, shell=False, capture_output=True, timeout=5.0, check=True)

        patch_file = os.path.join(tmpdir, "candidate.patch")
        with open(patch_file, "w", encoding="utf-8") as f:
            f.write(diff_content)

        res = subprocess.run(
            ["git", "apply", "--unidiff-zero", "--whitespace=fix", patch_file],
            cwd=tmpdir,
            shell=False,
            capture_output=True,
            timeout=10.0,
        )

        if res.returncode != 0:
            error_msg = res.stderr.decode("utf-8") or res.stdout.decode("utf-8") or "git apply failed"

            # C6BD: retry with git pre-image when patch fails and search_text is provided
            if request.search_text and request.source_root:
                from nexus.experimental.c6bd_preimage_retry import run_c6bd_preimage_retry
                retry_result = run_c6bd_preimage_retry(
                    source_root=request.source_root,
                    target_file=request.target_file,
                    search_text=request.search_text,
                    tmpdir=tmpdir,
                    patch_file=patch_file,
                    selected_candidate_hash=request.selected_candidate_hash,
                    task_id=request.task_id,
                )
                if retry_result is not None:
                    return retry_result

            return IsolatedApplyReceipt(
                task_id=request.task_id,
                workspace_path=tmpdir,
                target_file=request.target_file,
                patch_apply_status="failed",
                patch_apply_error=error_msg[:1000],
                selected_candidate_hash=request.selected_candidate_hash,
                applied_patch_hash="",
                selected_candidate_hash_matches_applied=False,
                candidate_output_isolated=False,
                mutation_allowed=True,
            )

        diff_res = subprocess.run(
            ["git", "diff", "--", request.target_file],
            cwd=tmpdir,
            shell=False,
            capture_output=True,
            timeout=5.0,
        )
        actual_diff = diff_res.stdout.decode("utf-8")

        canonical_applied = _canonicalize_effective_diff(actual_diff)
        canonical_selected = _canonicalize_effective_diff(request.unified_diff)

        applied_hash = hashlib.sha256(canonical_applied.encode("utf-8")).hexdigest()
        selected_hash = hashlib.sha256(canonical_selected.encode("utf-8")).hexdigest()

        raw_hash = hashlib.sha256(request.unified_diff.encode("utf-8")).hexdigest()
        raw_strip_hash = hashlib.sha256(request.unified_diff.strip().encode("utf-8")).hexdigest()

        matches = (
            (applied_hash == selected_hash)
            and (request.selected_candidate_hash in (selected_hash, raw_hash, raw_strip_hash))
            and bool(selected_hash)
        )

        return IsolatedApplyReceipt(
            task_id=request.task_id,
            workspace_path=tmpdir,
            target_file=request.target_file,
            patch_apply_status="applied",
            patch_apply_error="",
            selected_candidate_hash=request.selected_candidate_hash,
            applied_patch_hash=request.selected_candidate_hash if matches else applied_hash,
            selected_candidate_hash_matches_applied=matches,
            candidate_output_isolated=True,
            mutation_allowed=True,
            applied_patch_hash_source="git_diff",
        )
    except Exception as e:
        return IsolatedApplyReceipt(
            task_id=request.task_id,
            workspace_path=tmpdir,
            target_file=request.target_file,
            patch_apply_status="failed",
            patch_apply_error=f"internal_apply_error: {str(e)}",
            selected_candidate_hash=request.selected_candidate_hash,
            applied_patch_hash="",
            selected_candidate_hash_matches_applied=False,
            candidate_output_isolated=False,
            mutation_allowed=True,
        )


def _copy_verifier_files(request: IsolatedApplyRequest, workspace: str) -> None:
    """Copy verifier inputs next to the candidate. Only plain relative files under source_root."""
    from nexus.services.local_heal.pipeline_isolation import verifier_input_files

    if not request.verifier_files or not request.source_root:
        return
    allowed = set(verifier_input_files(request.source_root, ("", *request.verifier_files)))
    for relative in request.verifier_files:
        if relative not in allowed or os.path.normpath(relative) == os.path.normpath(
            request.target_file
        ):
            continue
        destination = os.path.join(workspace, relative)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(os.path.join(request.source_root, relative), destination)
