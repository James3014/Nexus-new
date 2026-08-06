from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import shutil
import subprocess
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


def _canonicalize_effective_diff(diff_text: str) -> str:
    """Canonicalize one target's selected/applied effect for hash binding.

    Git may add or drop pure blank *unchanged* context when it renders the
    applied diff.  Exclude only those lines; hunk order, nonblank context, and
    every added or removed payload line remain part of the identity.  Target,
    source, successful apply, isolation, and verifier checks are separate gates.
    """
    output: list[str] = []
    hunk_lines: list[str] = []
    in_hunk = False

    def flush_hunk() -> None:
        nonlocal hunk_lines, in_hunk
        if not in_hunk:
            return
        old_count = sum(1 for line in hunk_lines if not line.startswith("+"))
        new_count = sum(1 for line in hunk_lines if not line.startswith("-"))
        output.append(f"@@ -0,{old_count} +0,{new_count} @@")
        output.extend(hunk_lines)
        hunk_lines = []
        in_hunk = False

    for raw_line in diff_text.replace("\r\n", "\n").split("\n"):
        line = raw_line.rstrip()
        if line.startswith("@@"):
            flush_hunk()
            in_hunk = True
            continue
        if not in_hunk or not raw_line.startswith(("-", "+", " ")):
            continue
        operation = raw_line[0]
        content = raw_line[1:].rstrip()
        if operation == " " and not content:
            continue
        hunk_lines.append(f"{operation}{content}")
    flush_hunk()
    return "\n".join(output).strip()


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

    # Durable parent by default (.nexus/artifacts/local_armor/workspaces).
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

        subprocess.run(["git", "add", request.target_file], cwd=tmpdir, shell=False, capture_output=True, timeout=5.0, check=True)

        patch_file = os.path.join(tmpdir, "candidate.patch")
        diff_content = request.unified_diff
        if not diff_content.endswith("\n"):
            diff_content += "\n"

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
