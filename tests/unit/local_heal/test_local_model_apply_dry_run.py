from __future__ import annotations

from nexus.services.local_heal.local_model_patch_envelope import parse_local_model_patch_envelope
from nexus.services.local_heal.local_model_apply_dry_run import run_local_model_apply_dry_run


def test_apply_dry_run_missing_apply_fn() -> None:
    raw = "```diff\n--- a/f.py\n+++ b/f.py\n-print()\n+print(1)\n```"
    envelope = parse_local_model_patch_envelope("t1", raw)
    
    receipt = run_local_model_apply_dry_run(envelope)
    assert receipt.patch_apply_status == "blocked"
    assert receipt.patch_apply_error == "apply_fn_missing"
    assert receipt.applied_patch_hash == ""
    assert receipt.selected_candidate_hash_matches_applied is False
    assert receipt.candidate_output_isolated is False
    assert receipt.mutation_allowed is False


def test_apply_dry_run_success_match() -> None:
    raw = "```diff\n--- a/f.py\n+++ b/f.py\n-print()\n+print(1)\n```"
    envelope = parse_local_model_patch_envelope("t2", raw)
    
    def my_apply(env) -> str:
        return env.unified_diff
        
    receipt = run_local_model_apply_dry_run(envelope, apply_fn=my_apply)
    assert receipt.patch_apply_status == "applied"
    assert receipt.applied_patch_hash == envelope.candidate_hash
    assert receipt.selected_candidate_hash_matches_applied is True
    assert receipt.candidate_output_isolated is True
    assert receipt.mutation_allowed is False  # 必須是 False


def test_apply_dry_run_success_mismatch() -> None:
    raw = "```diff\n--- a/f.py\n+++ b/f.py\n-print()\n+print(1)\n```"
    envelope = parse_local_model_patch_envelope("t3", raw)
    
    def my_apply(env) -> str:
        return "completely different diff"
        
    receipt = run_local_model_apply_dry_run(envelope, apply_fn=my_apply)
    assert receipt.patch_apply_status == "applied"
    assert receipt.applied_patch_hash != envelope.candidate_hash
    assert receipt.selected_candidate_hash_matches_applied is False
    assert receipt.candidate_output_isolated is True
    assert receipt.mutation_allowed is False
