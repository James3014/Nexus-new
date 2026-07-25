from __future__ import annotations

import os
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import pytest

from nexus.services.product_capability_closure import EVIDENCE_INCOMPLETE
from nexus.services.product_capability_closure_harness import run_closure_task
from tests.services.test_product_capability_online_native_closure import (
    STAGE_OWNED,
    _online_task,
    _production_canary_runner,
)


LIVE_ONLINE_GATES = frozenset({"claim_gate", "delivery_gate"})


def _stage_result(row, capability: str):
    evidence_payload = row["record"]["evidence_refs"][0]["payload"]
    mainchain_result = evidence_payload["mainchain_result"]
    raw_receipt = mainchain_result["_raw_receipt"]
    stage = (raw_receipt.get("capability_results") or {}).get(capability) or {}
    return mainchain_result, raw_receipt, stage


def _online_live_authorized() -> bool:
    provider = os.environ.get("NEXUS_ONLINE_PROVIDER", "").strip().lower()
    return bool(
        os.environ.get("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "").strip() == "1"
        and provider in {"agy", "codex"}
        and (
            os.environ.get("NEXUS_AGY_BIN", "").strip()
            or os.environ.get("NEXUS_CODEX_COMMAND", "").strip()
        )
    )


def test_stage_owned_denominator_is_exactly_four() -> None:
    assert STAGE_OWNED == {
        "artifact_gate",
        "claim_gate",
        "delivery_gate",
        "prompt_compression",
    }


@pytest.mark.parametrize("capability", sorted(STAGE_OWNED))
def test_stage_owned_canary_is_structurally_valid_but_not_live_claimable(
    capability: str,
    tmp_path: Path,
) -> None:
    if capability in LIVE_ONLINE_GATES and not _online_live_authorized():
        pytest.skip("claim/delivery require an authorized live registered CLI provider call")
    task = _online_task(capability, tmp_path / "workspace")
    # artifact_gate and prompt_compression do not require an Online provider
    # response.  Keep those deterministic even during an authorized live run.
    env = (
        patch.dict(os.environ, {"NEXUS_EXTERNAL_RUNTIME_AUTHORIZED": "0"})
        if capability not in LIVE_ONLINE_GATES
        else nullcontext()
    )
    with env:
        row = run_closure_task(
            task,
            lambda t: _production_canary_runner(t, evidence_mode="canary"),
            output_dir=tmp_path / "runs",
        )
    verdict = row["closure_verdict"]
    assert verdict["status"] == EVIDENCE_INCOMPLETE, (capability, verdict)
    assert verdict["live_pass"] is False
    assert "non_live_evidence_mode:canary" in verdict["missing_evidence_reasons"]
    assert row["harness_consistency_errors"] == []

    mainchain_result, raw_receipt, stage = _stage_result(row, capability)
    assert raw_receipt["task_id"] == task.task_id
    assert stage["invoked"] is True
    assert stage["gate_passed"] is True
    assert stage["outcome_contributed"] is True
    assert stage["evidence_refs"]

    if capability == "prompt_compression":
        measured = stage["response"]["response"]
        assert measured["action"] == "compress_context"
        assert measured["semantic_status"] == "SUCCEEDED"
        assert measured["original_context_chars"] > measured["compressed_context_chars"] > 0
        assert 0 < measured["compression_ratio"] <= 1
        assert "compressed_context" in measured
    else:
        assert row["handler_or_stage_callsite"].startswith(
            "online_nexus_context.evaluate_postflight_gate"
        )
        assert mainchain_result["action"] == "evaluate_postflight_gate"
        assert mainchain_result["semantic_status"] == "VERIFIED"
        assert mainchain_result["verifier_artifact"].startswith("sha256:")

    if capability in LIVE_ONLINE_GATES:
        assert mainchain_result["online_provider"] in {"agy", "codex"}
        assert mainchain_result["online_provider_call_count"] == 1
        assert mainchain_result["online_gate_passed"] is True
    assert row["public_claim_allowed"] is False
