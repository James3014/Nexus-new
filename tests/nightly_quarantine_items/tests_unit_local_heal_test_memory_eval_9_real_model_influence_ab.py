"""Nightly quarantine entry: tests/unit/local_heal/test_memory_eval_9_real_model_influence_ab.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_memory_eval_9_real_model_influence_ab.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "host-only probe: audits generated, gitignored artifacts/runtime evidence (real model call receipts, selected candidates, evidence bundles) that a clean runner lacks; faking them would defeat the audit",
    "tests": ("test_memory_eval_9_real_model_influence_ab_verification",),
}
