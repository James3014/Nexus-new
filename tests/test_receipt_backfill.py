import pytest
import json
import tempfile
from pathlib import Path
from nexus.core.belief_contracts import CapabilityReceipt as CoreReceipt
from scripts.ops.backfill_telemetry import backfill_single_receipt

def test_row_keyed_evidence_hygiene_and_claimability_states():
    """
    TDD Phase 3 (RED): Verify receipt backfill tool acts as row-keyed hygiene.
    Verify claimability and public eligibility states under reconstructed vs estimated conditions.
    """
    # 1. Measured telemetry is missing -> is_claimable must be False
    raw_receipt = {
        "capability_name": "ast_scanning",
        "selected": True,
        "invoked": True,
        "evidence_id": "ev_row_999",
        "gate_passed": True,
        # missing telemetries completely
    }
    
    rcpt_incomplete = CoreReceipt(**raw_receipt)
    assert rcpt_incomplete.is_claimable is False
    
    # 2. Row-keyed backfill with reconstructed_from_bundle & no infra-invalid -> claimable becomes True
    reconstructed_receipt_data = backfill_single_receipt(
        receipt_dict=raw_receipt,
        source="reconstructed_from_bundle",
        has_infra_invalid=False,
        bundle_telemetries={
            "wall_time_ms": 1400,
            "token_usage": 800,
            "provider_costs": 0.015,
            "overhead_ms": 100
        }
    )
    
    rcpt_reconstructed = CoreReceipt(**reconstructed_receipt_data)
    assert rcpt_reconstructed.is_claimable is True
    assert rcpt_reconstructed.telemetries["telemetry_source"] == "reconstructed_from_bundle"
    assert rcpt_reconstructed.telemetries["has_infra_invalid"] is False
    
    # 3. Reconstructed but has infra-invalid reason -> remains False
    infra_invalid_receipt_data = backfill_single_receipt(
        receipt_dict=raw_receipt,
        source="reconstructed_from_bundle",
        has_infra_invalid=True,
        bundle_telemetries={
            "wall_time_ms": 1400,
            "token_usage": 800,
            "provider_costs": 0.015,
            "overhead_ms": 100
        }
    )
    
    rcpt_infra_invalid = CoreReceipt(**infra_invalid_receipt_data)
    assert rcpt_infra_invalid.is_claimable is False
    assert rcpt_infra_invalid.telemetries["has_infra_invalid"] is True

    # 4. Estimated-only backfill -> claimability must lock to OBSERVATION_ONLY, public_claim_safe remains False
    estimated_receipt_data = backfill_single_receipt(
        receipt_dict=raw_receipt,
        source="estimated",
        has_infra_invalid=False,
        bundle_telemetries={
            "wall_time_ms": 1400,
            "token_usage": 800,
            "provider_costs": 0.015,
            "overhead_ms": 100
        }
    )
    
    rcpt_estimated = CoreReceipt(**estimated_receipt_data)
    assert rcpt_estimated.is_claimable is False
    assert rcpt_estimated.telemetries["telemetry_source"] == "estimated"
    assert rcpt_estimated.telemetries["claimability"] == "OBSERVATION_ONLY"
