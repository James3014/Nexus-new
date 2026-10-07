from pathlib import Path

import pytest

from nexus.research.hybrid_replication_live import (
    FROZEN_RECEIPT_DURABLE_AUTHORITIES,
    FROZEN_RECEIPT_SHA256S,
    _frozen_receipt_hashes,
)


def _binding(tmp_path: Path) -> dict[str, object]:
    dm1 = tmp_path / "DM1_FINAL_RECEIPT.json"
    re2 = tmp_path / "RE2_FINAL_RECEIPT.json"
    dm1.write_text("dm1", encoding="utf-8")
    re2.write_text("re2", encoding="utf-8")
    return {
        "frozen_receipts": {
            "r3": {
                "path": str(tmp_path / "missing-r3.json"),
                "sha256": FROZEN_RECEIPT_SHA256S["r3"],
                "durable_authority": dict(FROZEN_RECEIPT_DURABLE_AUTHORITIES["r3"]),
            },
            "d2": {
                "path": str(tmp_path / "missing-d2.json"),
                "sha256": FROZEN_RECEIPT_SHA256S["d2"],
                "durable_authority": dict(FROZEN_RECEIPT_DURABLE_AUTHORITIES["d2"]),
            },
            "dm1": {"path": str(dm1), "sha256": FROZEN_RECEIPT_SHA256S["dm1"]},
            "re2": {"path": str(re2), "sha256": FROZEN_RECEIPT_SHA256S["re2"]},
        }
    }


def test_retired_artifacts_require_exact_pinned_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = _binding(tmp_path)
    physical = {
        "DM1_FINAL_RECEIPT.json": FROZEN_RECEIPT_SHA256S["dm1"],
        "RE2_FINAL_RECEIPT.json": FROZEN_RECEIPT_SHA256S["re2"],
    }
    monkeypatch.setattr(
        "nexus.research.hybrid_replication_live._sha256_file",
        lambda path: physical[path.name],
    )
    actual, declared = _frozen_receipt_hashes(binding)
    assert actual == FROZEN_RECEIPT_SHA256S
    assert declared == FROZEN_RECEIPT_SHA256S


def test_missing_retired_authority_fails_closed(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    binding["frozen_receipts"]["r3"].pop("durable_authority")
    with pytest.raises(ValueError, match="frozen_receipt_authority_missing:r3"):
        _frozen_receipt_hashes(binding)


def test_changed_retired_authority_fails_closed(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    binding["frozen_receipts"]["d2"]["durable_authority"]["comment_body_sha256"] = "invalid"
    with pytest.raises(ValueError, match="frozen_receipt_authority_mismatch:d2"):
        _frozen_receipt_hashes(binding)


def test_undeclared_fallback_for_physical_receipt_fails_closed(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    binding["frozen_receipts"]["dm1"]["durable_authority"] = dict(
        FROZEN_RECEIPT_DURABLE_AUTHORITIES["r3"]
    )
    with pytest.raises(ValueError, match="frozen_receipt_authority_undeclared:dm1"):
        _frozen_receipt_hashes(binding)
