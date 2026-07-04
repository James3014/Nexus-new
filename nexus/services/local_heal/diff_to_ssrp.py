import re
import hashlib
from pathlib import Path
from typing import Tuple, Dict, Any

class DiffToSSRPConverter:
    """🛡️ Deterministic Unified-Diff-to-SSRP Bridge (Nexus Armor Rule Alignment)"""

    @staticmethod
    def convert(
        raw_diff: str, 
        expected_target_file: str, 
        source_text: str
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Converts a single-file unified diff into a SSRP string.
        
        Returns:
            Tuple[ssrp_text, status, telemetry]
        """
        telemetry = {
            "source_hash_before": hashlib.sha256(source_text.encode("utf-8")).hexdigest() if source_text else "",
            "candidate_hash": hashlib.sha256(raw_diff.encode("utf-8")).hexdigest() if raw_diff else "",
            "target_file": expected_target_file,
            "target_file_correct": True,
            "preimage_match_status": "none",
        }
        
        if not raw_diff or not raw_diff.strip():
            return "", "unified_diff_malformed", telemetry

        # 1. Extract targets from diff headers
        # Check standard --- and +++ lines
        minus_headers = re.findall(r'^--- (?:a/|b/)?([^\n]+)', raw_diff, re.MULTILINE)
        plus_headers = re.findall(r'^\+\+\+ (?:a/|b/)?([^\n]+)', raw_diff, re.MULTILINE)
        
        if not minus_headers and not plus_headers:
            return "", "unified_diff_malformed", telemetry
            
        unique_files = set()
        for f in minus_headers + plus_headers:
            f_clean = f.split('\t')[0].strip()
            # strip a/ or b/ prefixes
            if f_clean.startswith("a/") or f_clean.startswith("b/"):
                f_clean = f_clean[2:]
            unique_files.add(f_clean)
            
        if len(unique_files) > 1:
            telemetry["target_file_correct"] = False
            return "", "unified_diff_multi_file_rejected", telemetry
            
        if unique_files:
            target_path = list(unique_files)[0]
            target_path_norm = target_path.replace("\\", "/").strip("/")
            expected_target_norm = expected_target_file.replace("\\", "/").strip("/")
            if (target_path_norm != expected_target_norm 
                and not expected_target_norm.endswith(target_path_norm) 
                and not target_path_norm.endswith(expected_target_norm)):
                telemetry["target_file_correct"] = False
                return "", "unified_diff_target_mismatch", telemetry
                
        # 2. Split hunks and convert
        hunk_split = re.split(r'^(@@\s+-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@[^\n]*)', raw_diff, flags=re.MULTILINE)
        
        if len(hunk_split) < 3:
            return "", "unified_diff_malformed", telemetry
            
        ssrp_blocks = []
        
        for idx in range(1, len(hunk_split), 2):
            hunk_header = hunk_split[idx]
            hunk_content = hunk_split[idx+1]
            
            search_lines = []
            replace_lines = []
            
            lines = hunk_content.splitlines()
            for line in lines:
                if line.startswith('-'):
                    search_lines.append(line[1:])
                elif line.startswith('+'):
                    replace_lines.append(line[1:])
                elif line.startswith(' '):
                    search_lines.append(line[1:])
                    replace_lines.append(line[1:])
                elif line.startswith('\\ No newline at end of file'):
                    continue
                else:
                    # Ignore random text outside diff lines
                    pass
            
            search_block = "\n".join(search_lines)
            replace_block = "\n".join(replace_lines)
            
            if not search_block:
                telemetry["preimage_match_status"] = "missing"
                return "", "unified_diff_missing_preimage", telemetry
                
            # 1. Exact match check
            if search_block in source_text:
                if source_text.count(search_block) > 1:
                    telemetry["preimage_match_status"] = "ambiguous"
                    return "", "unified_diff_ambiguous_preimage", telemetry
                matched_search_block = search_block
                overall_match_status = "exact_match"
            else:
                # 2. Recovery sequence
                recovered_block, status = _recover_preimage_unique(search_block, source_text)
                if status == "ambiguous":
                    telemetry["preimage_match_status"] = "ambiguous"
                    return "", "unified_diff_ambiguous_preimage", telemetry
                elif status == "too_short":
                    telemetry["preimage_match_status"] = "too_short"
                    return "", "unified_diff_preimage_too_short", telemetry
                elif status in ("whitespace_unique_match", "indentation_unique_match"):
                    matched_search_block = recovered_block
                    overall_match_status = status
                else:
                    telemetry["preimage_match_status"] = "missing"
                    return "", "unified_diff_missing_preimage", telemetry
                
            ssrp_blocks.append((matched_search_block, replace_block))
            
        if not ssrp_blocks:
            return "", "unified_diff_malformed", telemetry
            
        telemetry["preimage_match_status"] = overall_match_status
            
        # Construct SSRP text
        ssrp_lines = [f"FILE: {expected_target_file}"]
        for search_block, replace_block in ssrp_blocks:
            ssrp_lines.append("<<<<<<< SEARCH")
            ssrp_lines.append(search_block)
            ssrp_lines.append("=======")
            ssrp_lines.append(replace_block)
            ssrp_lines.append(">>>>>>> REPLACE")
            
        ssrp_text = "\n".join(ssrp_lines)
        return ssrp_text, "unified_diff_to_ssrp_converted", telemetry


def _recover_preimage_unique(search_block: str, source_text: str) -> tuple[str | None, str]:
    """🛡️ Bounded preimage recovery based on whitespace/indentation normalization.
    Returns (recovered_block, status).
    """
    if not search_block or not source_text:
        return None, "missing"

    search_lines = search_block.splitlines()
    source_lines = source_text.splitlines()
    n_search = len(search_lines)
    n_source = len(source_lines)

    # 1. Whitespace-trimmed line match (rstrip only)
    norm_search_ws = [line.rstrip() for line in search_lines]
    
    ws_matches = []
    for i in range(n_source - n_search + 1):
        window = [source_lines[i + j].rstrip() for j in range(n_search)]
        if window == norm_search_ws:
            matched_text = "\n".join(source_lines[i : i + n_search])
            ws_matches.append(matched_text)

    # 2. Indentation-normalized match (strip leading and trailing)
    norm_search_indent = [line.strip() for line in search_lines]
    indent_matches = []
    for i in range(n_source - n_search + 1):
        window = [source_lines[i + j].strip() for j in range(n_search)]
        if window == norm_search_indent:
            matched_text = "\n".join(source_lines[i : i + n_search])
            indent_matches.append(matched_text)

    # Verify if there is any match at all
    has_match = (len(ws_matches) > 0 or len(indent_matches) > 0)
    if not has_match:
        return None, "missing"

    # Enforce minimum line safety limit for recovery
    non_empty_search_count = sum(1 for line in search_lines if line.strip())
    if non_empty_search_count < 2:
        return None, "too_short"

    # Process whitespace-trimmed match first
    if len(ws_matches) == 1:
        return ws_matches[0], "whitespace_unique_match"
    elif len(ws_matches) > 1:
        return None, "ambiguous"

    # Process indentation-normalized match
    if len(indent_matches) == 1:
        return indent_matches[0], "indentation_unique_match"
    elif len(indent_matches) > 1:
        return None, "ambiguous"

    return None, "missing"
