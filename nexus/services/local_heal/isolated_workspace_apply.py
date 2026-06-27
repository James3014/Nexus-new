from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import shutil
import subprocess
import tempfile
from typing import Any


@dataclass(frozen=True)
class IsolatedApplyRequest:
    task_id: str
    source_root: str
    target_file: str
    unified_diff: str
    selected_candidate_hash: str
    work_dir: str = ""
    mutation_allowed: bool = False


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
        
    if request.work_dir:
        os.makedirs(request.work_dir, exist_ok=True)
        tmpdir = tempfile.mkdtemp(dir=request.work_dir)
    else:
        tmpdir = tempfile.mkdtemp()
        
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
            ["git", "apply", "--whitespace=fix", patch_file],
            cwd=tmpdir,
            shell=False,
            capture_output=True,
            timeout=10.0,
        )
        
        if res.returncode != 0:
            error_msg = res.stderr.decode("utf-8") or res.stdout.decode("utf-8") or "git apply failed"
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
        
        if "---" in actual_diff:
            idx = actual_diff.find("---")
            normalized_diff = actual_diff[idx:].strip()
        else:
            normalized_diff = actual_diff.strip()
            
        applied_hash = hashlib.sha256(normalized_diff.encode("utf-8")).hexdigest()
        matches = (applied_hash == request.selected_candidate_hash)
        
        return IsolatedApplyReceipt(
            task_id=request.task_id,
            workspace_path=tmpdir,
            target_file=request.target_file,
            patch_apply_status="applied",
            patch_apply_error="",
            selected_candidate_hash=request.selected_candidate_hash,
            applied_patch_hash=applied_hash,
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
