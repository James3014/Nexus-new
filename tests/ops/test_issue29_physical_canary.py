from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts.ops.canary_issue29_physical_local_online import (
    BLOCKED_MARKER,
    DURABLE_MARKER,
    build_and_freeze_vap,
    get_current_git_revision,
    run_physical_canary,
    verify_world_c_consumption,
)


def test_canary_refuses_without_authorization(monkeypatch):
    monkeypatch.delenv("NEXUS_CANARY_ALLOW_PHYSICAL", raising=False)
    with pytest.raises(RuntimeError, match="physical_canary_not_authorized"):
        run_physical_canary(allow_physical=False)


def test_canary_refuses_without_gemini_key(monkeypatch):
    monkeypatch.setenv("NEXUS_CANARY_ALLOW_PHYSICAL", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY_missing"):
        run_physical_canary(allow_physical=True)


def test_git_revision_fail_closed_when_unresolvable():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        with pytest.raises(RuntimeError, match="git_revision_unresolvable_fail_closed"):
            get_current_git_revision()


def test_vap_freeze_is_deterministic_and_hash_bound():
    vap1 = build_and_freeze_vap(
        task_id="task-1",
        target_file="test.py",
        local_output="recommendation text",
        source_revision="rev-123",
    )
    assert vap1["packet_hash"]
    assert len(vap1["packet_hash"]) == 64
    assert vap1["packet_content"]["task_id"] == "task-1"
    assert vap1["packet_content"]["source_revision"] == "rev-123"
    assert "Z" in vap1["packet_content"]["frozen_timestamp"] or "+00:00" in vap1["packet_content"]["frozen_timestamp"]


def test_world_c_verifier_tamper_detection_fail_closed():
    vap = build_and_freeze_vap(
        task_id="task-1",
        target_file="parse_kv.py",
        local_output="use dict comprehension",
        source_revision="rev-123",
    )
    frozen_hash = vap["packet_hash"]
    online_output_pass = f"VAP_CONSUMED:{frozen_hash}\ndef parse_kv(s: str) -> dict:\n    return {{}}"

    # Positive case: exact hash match and causal implementation present
    res_pass = verify_world_c_consumption(
        frozen_vap=vap,
        consumed_vap_hash=frozen_hash,
        online_output=online_output_pass,
    )
    assert res_pass["status"] == "PASS"
    assert res_pass["verifier_passed"] is True
    assert res_pass["hash_matches"] is True
    assert res_pass["causal_adoption_verified"] is True

    # Negative case 1: Content Tampered in VAP
    tampered_vap = {
        "packet_hash": frozen_hash,
        "packet_content": {**vap["packet_content"], "local_summary": "TAMPERED_CONTENT"},
    }
    res_tamper = verify_world_c_consumption(
        frozen_vap=tampered_vap,
        consumed_vap_hash=frozen_hash,
        online_output=online_output_pass,
    )
    assert res_tamper["status"] == "FAIL"
    assert res_tamper["verifier_passed"] is False
    assert "tamper_detected_content_recomputed_hash_mismatch" in res_tamper["reason"]

    # Negative case 2: Consumed Hash Mismatch
    res_consumed_mismatch = verify_world_c_consumption(
        frozen_vap=vap,
        consumed_vap_hash="deadbeef" * 8,
        online_output=online_output_pass,
    )
    assert res_consumed_mismatch["status"] == "FAIL"
    assert res_consumed_mismatch["verifier_passed"] is False
    assert "tamper_detected_consumed_hash_mismatch" in res_consumed_mismatch["reason"]

    # Negative case 3: Online did not produce causal code
    res_no_code = verify_world_c_consumption(
        frozen_vap=vap,
        consumed_vap_hash=frozen_hash,
        online_output=f"I cited VAP_CONSUMED:{frozen_hash} but did not write any function.",
    )
    assert res_no_code["status"] == "FAIL"
    assert res_no_code["verifier_passed"] is False
    assert "online_did_not_produce_causal_implementation" in res_no_code["reason"]


def test_run_canary_flow_with_simulated_tamper(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_CANARY_ALLOW_PHYSICAL", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")

    mock_local = {
        "provider": "ollama",
        "model": "qwen2.5-coder:7b-instruct",
        "output_text": "Split by comma and colon using dict comprehension.",
        "elapsed_sec": 0.5,
        "total_duration": 500000000,
        "eval_count": 25,
        "prompt_eval_count": 10,
        "call_count": 1,
    }

    def mock_gemini(prompt, api_key, **kwargs):
        import re
        m = re.search(r"\[VAP_PACKET_HASH:([a-f0-9]+)\]", prompt)
        packet_hash = m.group(1) if m else "nohash"
        return {
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "output_text": f"VAP_CONSUMED:{packet_hash}\ndef parse_kv(s: str) -> dict:\n    return dict(item.split(':') for item in s.split(','))",
            "elapsed_sec": 0.8,
            "usage": {"totalTokenCount": 150},
            "call_count": 1,
        }

    with patch("scripts.ops.canary_issue29_physical_local_online.call_physical_ollama", return_value=mock_local):
        with patch("scripts.ops.canary_issue29_physical_local_online.call_physical_gemini", side_effect=mock_gemini):
            # Test tamper run
            receipt_tamper = run_physical_canary(
                allow_physical=True,
                simulate_tamper=True,
                output_receipt_path=tmp_path / "tamper_receipt.json",
            )
            assert receipt_tamper["terminal"] == "BLOCKED_BY_VERIFIER"
            assert receipt_tamper["world_c_verifier"]["verifier_passed"] is False
            assert receipt_tamper["durable_marker"] == BLOCKED_MARKER

            # Test normal pass run
            receipt_pass = run_physical_canary(
                allow_physical=True,
                simulate_tamper=False,
                output_receipt_path=tmp_path / "pass_receipt.json",
            )
            assert receipt_pass["terminal"] == "COMPLETE"
            assert receipt_pass["world_c_verifier"]["verifier_passed"] is True
            assert receipt_pass["durable_marker"] == DURABLE_MARKER
            assert receipt_pass["local_execution"]["model_call_count"] == 1
            assert receipt_pass["online_execution"]["model_call_count"] == 1
            assert receipt_pass["online_execution"]["online_consumed"] is True
            assert receipt_pass["claim_boundary"]["output_consumed"] is True
            assert receipt_pass["claim_boundary"]["outcome_contributed"] is True
