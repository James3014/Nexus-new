from __future__ import annotations

import hashlib
import os
import subprocess
from typing import Any

from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt


def resolve_anchor_from_preimage(
    *,
    repo_root: str,
    target_file: str,
    search_text: str,
    current_anchor: int,
) -> int:
    """Return a better anchor line from git pre-image history, or current_anchor when no better match exists."""
    if current_anchor != 1 or not repo_root or not target_file:
        return current_anchor

    try:
        from pathlib import Path as _Path
        _repo = _Path(repo_root)
        _git_dir = _repo / ".git"
        if not (_git_dir.exists() or _git_dir.is_dir()):
            return current_anchor

        _search_first_line = str(search_text).strip().splitlines()[0].strip() if str(search_text).strip() else ""
        if not _search_first_line:
            return current_anchor

        _log_res = subprocess.run(
            ["git", "log", "--all", "--oneline", "--diff-filter=M",
             "-S", _search_first_line[:80], "--", target_file],
            cwd=str(_repo), capture_output=True, text=True, timeout=30,
        )
        _fix_commits = [l.split()[0] for l in _log_res.stdout.strip().splitlines() if l.strip()]
        if not _fix_commits:
            return current_anchor

        _fix = _fix_commits[0]
        _show_res = subprocess.run(
            ["git", "show", f"{_fix}^:{target_file}"],
            cwd=str(_repo), capture_output=True, text=True, timeout=30,
        )
        if _show_res.returncode != 0:
            return current_anchor

        _pre_lines = _show_res.stdout.splitlines()
        for _i, _l in enumerate(_pre_lines, 1):
            if _search_first_line in _l:
                return _i
    except Exception:
        pass

    return current_anchor


def run_c6bd_preimage_retry(
    *,
    source_root: str,
    target_file: str,
    search_text: str,
    tmpdir: str,
    patch_file: str,
    selected_candidate_hash: str,
    task_id: str,
) -> IsolatedApplyReceipt | None:
    """Attempt C6BD pre-image retry. Returns receipt on success, None if retry not applicable."""
    _search_first = search_text.strip().splitlines()[0].strip() if search_text.strip() else ""
    if not _search_first:
        return None

    try:
        _log_r = subprocess.run(
            ["git", "log", "--all", "--oneline", "--diff-filter=M",
             "-S", _search_first[:80], "--", target_file],
            cwd=source_root, capture_output=True, text=True, timeout=30,
        )
        _fix_commits = [l.split()[0] for l in _log_r.stdout.strip().splitlines() if l.strip()]
        if not _fix_commits:
            return None

        _fix = _fix_commits[0]
        _show_r = subprocess.run(
            ["git", "show", f"{_fix}^:{target_file}"],
            cwd=source_root, capture_output=True, text=True, timeout=30,
        )
        if _show_r.returncode != 0:
            return None

        _pre_src_path = os.path.join(tmpdir, target_file)
        os.makedirs(os.path.dirname(_pre_src_path), exist_ok=True)
        with open(_pre_src_path, "w", encoding="utf-8") as _f:
            _f.write(_show_r.stdout)
        subprocess.run(["git", "add", target_file],
            cwd=tmpdir, capture_output=True, timeout=5.0, check=True)
        _retry = subprocess.run(
            ["git", "apply", "--unidiff-zero", "--whitespace=fix", patch_file],
            cwd=tmpdir, capture_output=True, timeout=10.0,
        )
        if _retry.returncode != 0:
            return None

        _diff_r = subprocess.run(
            ["git", "diff", "--", target_file],
            cwd=tmpdir, capture_output=True, text=True, timeout=5.0,
        )
        _actual_diff = _diff_r.stdout
        if "---" in _actual_diff:
            _idx = _actual_diff.find("---")
            _actual_diff = _actual_diff[_idx:].strip()
        _applied_hash = hashlib.sha256(_actual_diff.encode("utf-8")).hexdigest()
        _matches = (_applied_hash == selected_candidate_hash)
        return IsolatedApplyReceipt(
            task_id=task_id,
            workspace_path=tmpdir,
            target_file=target_file,
            patch_apply_status="applied",
            patch_apply_error="",
            selected_candidate_hash=selected_candidate_hash,
            applied_patch_hash=_applied_hash,
            selected_candidate_hash_matches_applied=_matches,
            candidate_output_isolated=True,
            mutation_allowed=True,
            applied_patch_hash_source="git_preimage_retry",
        )
    except Exception:
        return None
