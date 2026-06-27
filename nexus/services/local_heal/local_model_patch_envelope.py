from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re


@dataclass(frozen=True)
class LocalModelPatchEnvelope:
    task_id: str
    raw_model_output: str
    candidate_id: str
    target_file: str = ""
    unified_diff: str = ""
    parser_status: str = "not_run"
    parser_error: str = ""
    candidate_hash: str = ""
    public_claim_allowed: bool = False
    production_ready: bool = False
    adapter_output_is_route_truth: bool = False
    behavior_changed: bool = False


def parse_local_model_patch_envelope(task_id: str, raw_model_output: str) -> LocalModelPatchEnvelope:
    candidate_id = f"c-{task_id}"
    
    diff_pattern = re.compile(r"```diff\s*\n(.*?)\n\s*```", re.DOTALL)
    match = diff_pattern.search(raw_model_output)
    
    if match:
        unified_diff = match.group(1).strip()
    else:
        if "---" in raw_model_output and "+++" in raw_model_output:
            start_idx = raw_model_output.find("---")
            unified_diff = raw_model_output[start_idx:].strip()
        else:
            return LocalModelPatchEnvelope(
                task_id=task_id,
                raw_model_output=raw_model_output,
                candidate_id=candidate_id,
                parser_status="blocked",
                parser_error="missing_unified_diff",
            )
            
    candidate_hash = hashlib.sha256(unified_diff.encode("utf-8")).hexdigest()
    
    target_file = ""
    file_match = re.search(r"\+\+\+ b/(.*?)\s", unified_diff)
    if file_match:
        target_file = file_match.group(1).strip()
        
    return LocalModelPatchEnvelope(
        task_id=task_id,
        raw_model_output=raw_model_output,
        candidate_id=candidate_id,
        target_file=target_file,
        unified_diff=unified_diff,
        parser_status="pass",
        candidate_hash=candidate_hash,
    )
