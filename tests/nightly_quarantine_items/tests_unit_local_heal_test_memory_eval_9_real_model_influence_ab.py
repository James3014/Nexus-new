"""Nightly quarantine entry: tests/unit/local_heal/test_memory_eval_9_real_model_influence_ab.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_memory_eval_9_real_model_influence_ab.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "host-only probe: audits cwd-relative, gitignored artifacts/runtime/memory_eval_9_real_model_influence_ab_v0/ (validation.json, model_call_receipt.json, raw_model_output_memory_{on,off}.txt, runs/C_12481/*/prompt_manifest.json) produced by a real local-model A/B run; a clean runner lacks them and faking them would defeat the audit",
    "tests": ("test_memory_eval_9_real_model_influence_ab_verification",),
}
