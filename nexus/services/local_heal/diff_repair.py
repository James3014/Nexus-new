from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass

@dataclass(frozen=True)
class RepairReceipt:
    repair_attempted: bool
    repair_success: bool
    repair_reason: str
    original_patch_hash: str
    repaired_patch_hash: str
    repaired_by_rule: str
    still_within_locked_span: bool
    repaired_diff: str = ""

def repair_malformed_diff(
    original_diff: str,
    target_file: str,
    locked_search: str,
    span_start: int = 1,
    source_root: str = "",
) -> tuple[str, RepairReceipt]:
    orig_hash = hashlib.sha256(original_diff.encode("utf-8")).hexdigest() if original_diff else ""
    
    if not target_file or not locked_search.strip():
        return original_diff, RepairReceipt(
            repair_attempted=True,
            repair_success=False,
            repair_reason="missing_target_file_or_locked_search",
            original_patch_hash=orig_hash,
            repaired_patch_hash="",
            repaired_by_rule="none",
            still_within_locked_span=False
        )
        
    lines = original_diff.splitlines()
    
    removed_lines = []
    added_lines = []
    
    for line in lines:
        if line.startswith("-") and not line.startswith("---"):
            removed_lines.append(line[1:])
        elif line.startswith("+") and not line.startswith("+++"):
            added_lines.append(line[1:])
            
    removed_content = "\n".join(removed_lines).strip()
    added_content = "\n".join(added_lines).strip()
    
    if removed_content and removed_content not in locked_search:
        return original_diff, RepairReceipt(
            repair_attempted=True,
            repair_success=False,
            repair_reason="removed_content_not_in_locked_search",
            original_patch_hash=orig_hash,
            repaired_patch_hash="",
            repaired_by_rule="none",
            still_within_locked_span=False
        )
        
    if not added_content:
        return original_diff, RepairReceipt(
            repair_attempted=True,
            repair_success=False,
            repair_reason="no_added_lines_found_in_diff",
            original_patch_hash=orig_hash,
            repaired_patch_hash="",
            repaired_by_rule="none",
            still_within_locked_span=False
        )
        
    locked_lines = []
    from pathlib import Path
    if source_root and target_file:
        file_path = Path(source_root) / target_file
        if file_path.exists():
            try:
                all_lines = file_path.read_text(encoding="utf-8").splitlines()
                if 1 <= span_start <= len(all_lines):
                    search_len = len(locked_search.splitlines())
                    locked_lines = all_lines[span_start - 1 : span_start - 1 + search_len]
            except Exception:
                pass
                
    if not locked_lines:
        locked_lines = locked_search.splitlines()
        
    added_lines_split = added_content.splitlines()
    
    first_locked_line = locked_lines[0] if locked_lines else ""
    indent = ""
    for char in first_locked_line:
        if char in (" ", "\t"):
            indent += char
        else:
            break
            
    realigned_added = []
    for line in added_lines_split:
        if not line.startswith(indent) and line.strip():
            realigned_added.append(indent + line.lstrip())
        else:
            realigned_added.append(line)
            
    diff_generator = difflib.unified_diff(
        locked_lines,
        realigned_added,
        fromfile=f"a/{target_file}",
        tofile=f"b/{target_file}",
        lineterm=""
    )
    
    reconstructed_diff = "\n".join(diff_generator)
    if reconstructed_diff:
        reconstructed_diff += "\n"
        
    import re
    pattern = re.compile(r"@@ -1(,\d+)? \+1(,\d+)? @@")
    match = pattern.search(reconstructed_diff)
    if match:
        hunk_len_minus = match.group(1) if match.group(1) else ""
        hunk_len_plus = match.group(2) if match.group(2) else ""
        new_header = f"@@ -{span_start}{hunk_len_minus} +{span_start}{hunk_len_plus} @@"
        reconstructed_diff = pattern.sub(new_header, reconstructed_diff)
        
    repaired_hash = hashlib.sha256(reconstructed_diff.encode("utf-8")).hexdigest()
    
    receipt = RepairReceipt(
        repair_attempted=True,
        repair_success=True,
        repair_reason="reconstruct_from_added_lines",
        original_patch_hash=orig_hash,
        repaired_patch_hash=repaired_hash,
        repaired_by_rule="reconstruct_single_span_diff",
        still_within_locked_span=True,
        repaired_diff=reconstructed_diff
    )
    
    return reconstructed_diff, receipt
