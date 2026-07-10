from __future__ import annotations

import json

from scripts.bench.ab_eval import compute_from_receipt


def test_compute_from_receipt_single(tmp_path):
    receipt = {"capability_name": "codeintel", "gate_passed": True}
    p = tmp_path / "receipt.json"
    p.write_text(json.dumps(receipt), encoding="utf-8")
    result = compute_from_receipt(p)
    assert result["status"] == "pass"
    assert "codeintel" in result["capabilities"]


def test_compute_from_receipt_list(tmp_path):
    receipts = [
        {"capability_name": "codeintel", "gate_passed": True},
        {"capability_name": "belief", "gate_passed": True},
    ]
    p = tmp_path / "receipt.json"
    p.write_text(json.dumps(receipts), encoding="utf-8")
    result = compute_from_receipt(p)
    assert len(result["capabilities"]) == 2


def test_compute_from_receipt_empty(tmp_path):
    p = tmp_path / "receipt.json"
    p.write_text("[]", encoding="utf-8")
    result = compute_from_receipt(p)
    assert result["status"] == "pass"
    assert result["capabilities"] == []


def test_compute_from_receipt_unknown_capability(tmp_path):
    receipt = {"unknown_field": "value"}
    p = tmp_path / "receipt.json"
    p.write_text(json.dumps(receipt), encoding="utf-8")
    result = compute_from_receipt(p)
    assert result["status"] == "pass"
