from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import re
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

        def canonicalize_diff(diff_text: str) -> str:
            lines = []
            # 1. Normalize line endings (CRLF -> LF)
            raw_lines = diff_text.replace("\r\n", "\n").split("\n")
            for line in raw_lines:
                # 2. Strip trailing whitespaces only to ignore minor trailing spaces
                line_rstrip = line.rstrip()

                # 3. Skip git diff metadata headers
                if line_rstrip.startswith(("diff --git", "index ", "--- ", "+++ ", "new file", "deleted file")):
                    continue

                # 4. Standardize hunk headers: keep only the unified diff coordinate part, drop function context
                if line_rstrip.startswith("@@"):
                    m = re.match(r"^(@@\s+-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@)", line_rstrip)
                    if m:
                        lines.append(m.group(1))
                    continue

                # 5. For code modifications (+, -, space context), keep the exact indentation and whitespaces
                if line_rstrip.startswith(("-", "+", " ")):
                    op = line_rstrip[0]
                    content = line[1:].rstrip()  # Keep the exact code payload including leading indentation and internal spaces
                    lines.append(f"{op}{content}")
                    continue

            # 6. Join lines and strip start/end empty lines
            return "\n".join(lines).strip()

        canonical_applied = canonicalize_diff(actual_diff)
        canonical_selected = canonicalize_diff(request.unified_diff)

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
