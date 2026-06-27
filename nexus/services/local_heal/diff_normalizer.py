from __future__ import annotations

from dataclasses import dataclass
import re

@dataclass(frozen=True)
class NormalizerReceipt:
    original_target_file: str
    normalized_target_file: str
    normalization_reason: str
    normalized_by_rule: str
    normalized: bool = False

def normalize_diff_header(diff_text: str, expected_target_file: str) -> tuple[str, NormalizerReceipt]:
    if not diff_text.strip():
        return diff_text, NormalizerReceipt("", expected_target_file, "empty_diff", "none", False)
        
    lines = diff_text.splitlines()
    
    minus_idx = -1
    plus_idx = -1
    original_minus_path = ""
    original_plus_path = ""
    
    for i, line in enumerate(lines):
        if line.startswith("--- "):
            minus_idx = i
            original_minus_path = line[4:].strip()
        elif line.startswith("+++ ") and minus_idx != -1:
            plus_idx = i
            original_plus_path = line[4:].strip()
            break
            
    if minus_idx == -1 or plus_idx == -1:
        return diff_text, NormalizerReceipt("", expected_target_file, "header_not_found", "none", False)
        
    def clean_path(p: str) -> str:
        p = p.strip('"\'')
        if p.startswith("a/") or p.startswith("b/"):
            return p[2:]
        return p
        
    clean_minus = clean_path(original_minus_path)
    clean_plus = clean_path(original_plus_path)
    
    expected_clean = expected_target_file.strip()
    
    reasons = []
    if not original_minus_path.startswith("a/") or not original_plus_path.startswith("b/"):
        reasons.append("missing_ab_prefix")
        
    if clean_plus != expected_clean or clean_minus != expected_clean:
        reasons.append("filename_mismatch")
        
    if reasons:
        new_minus = f"--- a/{expected_clean}"
        new_plus = f"+++ b/{expected_clean}"
        
        lines[minus_idx] = new_minus
        lines[plus_idx] = new_plus
        
        normalized_diff = "\n".join(lines) + ("\n" if diff_text.endswith("\n") else "")
        reason_str = ";".join(reasons)
        
        receipt = NormalizerReceipt(
            original_target_file=clean_plus if clean_plus else original_plus_path,
            normalized_target_file=expected_clean,
            normalization_reason=reason_str,
            normalized_by_rule="standard_header_prefix_normalization",
            normalized=True
        )
        return normalized_diff, receipt
        
    return diff_text, NormalizerReceipt(clean_plus, expected_clean, "", "none", False)
