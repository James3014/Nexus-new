"""Nightly quarantine entry: tests/train/test_s2t_repair_dataset_contract.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/train/test_s2t_repair_dataset_contract.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "host-only probe: validates the cwd-relative, untracked .nexus/training/s2t_3b_repair_v2.jsonl fine-tuning dataset (>=33 repair rows), which only exists on a host that generated it; mark as a host-only probe or commit a reduced fixture with owner approval",
    "tests": ("test_s2t_repair_dataset_contract",),
}
