"""EA-R1: Effect Ledger Tests."""
from __future__ import annotations

import json
import os
import tempfile
import pytest
from nexus.services.local_heal.effect_ledger import EffectLedger, EffectLedgerRow


def test_ledger_append_and_save():
    """EA-R1: Ledger rows are appendable and saveable."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test_ledger.jsonl")
        ledger = EffectLedger(path=path)

        row = EffectLedgerRow(
            case_id="test_1",
            source="counterfactual_fixture",
            phase="P5",
            p5_off_selected_index=0,
            p5_on_selected_index=1,
            selection_changed=True,
            p5_selected_hash_matches_p4=True,
            memory_trace_status="TRACE_AVAILABLE",
            memory_sources=["p5_selection_memory"],
            trace_event_count=5,
            fuzzy_backend_used=True,
            learning_closure_ref="",
            findings_memory_card_id="",
        )
        ledger.append(row)
        ledger.save()

        # Verify file exists and is valid JSONL
        assert os.path.exists(path)
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["case_id"] == "test_1"
        assert data["claim_level"] == "controlled"


def test_ledger_claim_level_validation():
    """EA-R1: claim_level is validated on append."""
    ledger = EffectLedger()

    # shadow requires real_model_shadow source AND trace_event_count > 0
    row = EffectLedgerRow(
        case_id="test_2",
        source="counterfactual_fixture",  # wrong source
        phase="P5",
        p5_off_selected_index=0,
        p5_on_selected_index=0,
        selection_changed=False,
        p5_selected_hash_matches_p4=True,
        memory_trace_status="TRACE_MISSING",
        memory_sources=[],
        trace_event_count=0,
        fuzzy_backend_used=False,
        learning_closure_ref="",
        findings_memory_card_id="",
        claim_level="shadow",
    )
    ledger.append(row)
    assert ledger.rows[0].claim_level == "controlled"  # downgraded


def test_ledger_summary():
    """EA-R1: Summary produces correct stats."""
    ledger = EffectLedger()
    ledger.append(EffectLedgerRow(
        case_id="a", source="counterfactual_fixture", phase="P5",
        p5_off_selected_index=0, p5_on_selected_index=1, selection_changed=True,
        p5_selected_hash_matches_p4=True, memory_trace_status="TRACE_AVAILABLE",
        memory_sources=["p5_selection_memory"], trace_event_count=5,
        fuzzy_backend_used=True, learning_closure_ref="", findings_memory_card_id="",
    ))
    ledger.append(EffectLedgerRow(
        case_id="b", source="historical_replay", phase="P5",
        p5_off_selected_index=0, p5_on_selected_index=0, selection_changed=False,
        p5_selected_hash_matches_p4=True, memory_trace_status="TRACE_MISSING",
        memory_sources=[], trace_event_count=0, fuzzy_backend_used=True,
        learning_closure_ref="", findings_memory_card_id="",
    ))

    summary = ledger.summary()
    assert summary["total_rows"] == 2
    assert summary["selection_changed_count"] == 1
    assert summary["memory_trace_available_count"] == 1
    assert summary["claim_level_distribution"]["controlled"] == 2


def test_ledger_load():
    """EA-R1: Ledger can load from JSONL file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test_ledger.jsonl")
        row = EffectLedgerRow(
            case_id="load_test", source="counterfactual_fixture", phase="P5",
            p5_off_selected_index=0, p5_on_selected_index=1, selection_changed=True,
            p5_selected_hash_matches_p4=True, memory_trace_status="TRACE_AVAILABLE",
            memory_sources=["p5_selection_memory"], trace_event_count=5,
            fuzzy_backend_used=True, learning_closure_ref="", findings_memory_card_id="",
        )
        with open(path, "w") as f:
            f.write(json.dumps(row.to_jsonl_row()) + "\n")

        ledger = EffectLedger(path=path)
        loaded = ledger.load()
        assert len(loaded) == 1
        assert loaded[0].case_id == "load_test"


def test_ledger_path_under_artifacts():
    """EA-R1: Ledger path is under artifacts/effect_reports/, NOT .nexus/."""
    ledger = EffectLedger()
    assert "artifacts/effect_reports/" in ledger.path
    assert ".nexus/" not in ledger.path
