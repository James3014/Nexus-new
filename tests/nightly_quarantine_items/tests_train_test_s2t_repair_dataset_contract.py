"""Nightly quarantine entry: tests/train/test_s2t_repair_dataset_contract.py (#1926). See package docstring."""

from __future__ import annotations

# Tombstone (#1926): the contract test now builds the dataset with scripts/train/build_s2t_repair_dataset.py in tmp_path from 35 SFT rows and 33 malformed failures, then applies the same checks.
ENTRY = None
