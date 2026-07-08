from __future__ import annotations

import os


def forensic_apply_mismatch(
    *,
    apply_error: str,
    locked_search: str,
    source_text: str,
    target_file: str = "",
) -> str:
    """C6AZ: Forensic-only apply mismatch classifier.

    Maps apply failures to a single root cause from the C6AZ taxonomy:
      - search_span_mismatch
      - wrong_target_file
      - wrong_target_region
      - syntax_shape_invalid
      - partial_match_but_anchor_rejected
      - unknown_apply_failure

    This function does NOT change runtime behavior. It is for forensic analysis only.
    """
    error_lower = (apply_error or "").lower()

    if "corrupt patch" in error_lower or "malformed patch" in error_lower:
        return "syntax_shape_invalid"

    if target_file and target_file not in error_lower and "patch does not apply" not in error_lower:
        if "no such file" in error_lower or "file not found" in error_lower:
            return "wrong_target_file"

    locked = (locked_search or "").strip()
    source = source_text or ""
    if "patch does not apply" in error_lower:
        if locked and source:
            if locked in source:
                return "partial_match_but_anchor_rejected"
            if locked[:50] in source:
                return "partial_match_but_anchor_rejected"
            return "search_span_mismatch"
        return "search_span_mismatch"

    return "unknown_apply_failure"


def classify_apply_failure_root_cause(
    *,
    target_file: str,
    projected_patch: str,
    apply_error: str,
    current_source_text: str,
    target_file_hash_before_apply: str,
    target_file_hash_after_restore: str,
    target_file_hash_at_apply: str,
) -> str:
    if not projected_patch.strip():
        return "unknown_apply_failure"

    def _extract_projected_patch_header(unified_diff: str) -> str:
        header_lines: list[str] = []
        for line in unified_diff.splitlines():
            if line.startswith("--- ") or line.startswith("+++ "):
                header_lines.append(line)
                if len(header_lines) == 2:
                    break
        return "\n".join(header_lines)

    def _extract_projected_patch_paths(unified_diff: str) -> tuple[str, str]:
        old_path = ""
        new_path = ""
        for line in unified_diff.splitlines():
            if not old_path and line.startswith("--- a/"):
                old_path = os.path.normpath(line[len("--- a/"):].strip())
            elif not new_path and line.startswith("+++ b/"):
                new_path = os.path.normpath(line[len("+++ b/"):].strip())
            if old_path and new_path:
                break
        return old_path, new_path

    def _extract_search_excerpt_from_projected_patch(unified_diff: str) -> str:
        search_lines: list[str] = []
        inside_hunk = False
        for line in unified_diff.splitlines():
            if line.startswith("@@"):
                inside_hunk = True
                continue
            if not inside_hunk:
                continue
            if line.startswith(("--- ", "+++ ")):
                continue
            if line.startswith((" ", "-")):
                search_lines.append(line[1:])
        return "\n".join(search_lines).strip()

    projected_header = _extract_projected_patch_header(projected_patch)
    old_path, new_path = _extract_projected_patch_paths(projected_patch)
    target_norm = os.path.normpath(target_file)
    has_hunk_header = any(line.startswith("@@") for line in projected_patch.splitlines())

    if not projected_header or not has_hunk_header:
        return "patch_format_invalid"

    if old_path != target_norm or new_path != target_norm:
        return "projected_patch_header_mismatch"

    if (
        target_file_hash_after_restore
        and target_file_hash_at_apply
        and target_file_hash_after_restore != target_file_hash_at_apply
    ):
        return "target_file_state_drift"

    search_excerpt = _extract_search_excerpt_from_projected_patch(projected_patch)
    if search_excerpt and current_source_text and search_excerpt not in current_source_text:
        return "search_block_mismatch_current_source"

    if (
        target_file_hash_before_apply
        and target_file_hash_after_restore
        and target_file_hash_before_apply != target_file_hash_after_restore
    ):
        return "workspace_pollution_before_apply"

    error_lower = (apply_error or "").lower()
    if "patch does not apply" in error_lower:
        return "search_block_mismatch_current_source" if search_excerpt else "workspace_pollution_before_apply"
    if "corrupt patch" in error_lower or "malformed patch" in error_lower:
        return "patch_format_invalid"

    return "projected_patch_body_mismatch"
