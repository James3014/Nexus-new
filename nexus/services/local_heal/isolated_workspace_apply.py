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
                _search_first = request.search_text.strip().splitlines()[0].strip() if request.search_text.strip() else ""
                if _search_first:
                    try:
                        _log_r = subprocess.run(
                            ["git", "log", "--all", "--oneline", "--diff-filter=M",
                             "-S", _search_first[:80], "--", request.target_file],
                            cwd=request.source_root, capture_output=True, text=True, timeout=30,
                        )
                        _fix_commits = [l.split()[0] for l in _log_r.stdout.strip().splitlines() if l.strip()]
                        if _fix_commits:
                            _fix = _fix_commits[0]
                            _show_r = subprocess.run(
                                ["git", "show", f"{_fix}^:{request.target_file}"],
                                cwd=request.source_root, capture_output=True, text=True, timeout=30,
                            )
                            if _show_r.returncode == 0:
                                _pre_src_path = os.path.join(tmpdir, request.target_file)
                                os.makedirs(os.path.dirname(_pre_src_path), exist_ok=True)
                                with open(_pre_src_path, "w", encoding="utf-8") as _f:
                                    _f.write(_show_r.stdout)
                                subprocess.run(["git", "add", request.target_file],
                                    cwd=tmpdir, capture_output=True, timeout=5.0, check=True)
                                _retry = subprocess.run(
                                    ["git", "apply", "--unidiff-zero", "--whitespace=fix", patch_file],
                                    cwd=tmpdir, capture_output=True, timeout=10.0,
                                )
                                if _retry.returncode == 0:
                                    _diff_r = subprocess.run(
                                        ["git", "diff", "--", request.target_file],
                                        cwd=tmpdir, capture_output=True, text=True, timeout=5.0,
                                    )
                                    _actual_diff = _diff_r.stdout
                                    if "---" in _actual_diff:
                                        _idx = _actual_diff.find("---")
                                        _actual_diff = _actual_diff[_idx:].strip()
                                    _applied_hash = hashlib.sha256(_actual_diff.encode("utf-8")).hexdigest()
                                    _matches = (_applied_hash == request.selected_candidate_hash)
                                    return IsolatedApplyReceipt(
                                        task_id=request.task_id,
                                        workspace_path=tmpdir,
                                        target_file=request.target_file,
                                        patch_apply_status="applied",
                                        patch_apply_error="",
                                        selected_candidate_hash=request.selected_candidate_hash,
                                        applied_patch_hash=_applied_hash,
                                        selected_candidate_hash_matches_applied=_matches,
                                        candidate_output_isolated=True,
                                        mutation_allowed=True,
                                        applied_patch_hash_source="git_preimage_retry",
                                    )
                    except Exception:
                        pass

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
