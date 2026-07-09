"""P7-A1: Armor Evidence Manifest Tests."""
from __future__ import annotations

import json
import os
import tempfile
import pytest
from nexus.services.local_heal.p7_armor_evidence_manifest import P7ArmorEvidenceManifest, load_armor_manifest


def test_missing_p3_seal_blocks():
    with tempfile.TemporaryDirectory() as d:
        m = load_armor_manifest(d)
        assert m.manifest_complete is False
        assert "missing_artifacts" in m.blocked_reasons


def test_complete_manifest_passes():
    with tempfile.TemporaryDirectory() as d:
        for rel, _ in [
            ("docs/reports/p3_final_seal_report_v0.md", ""),
            ("artifacts/effect_reports/p3_synthetic_e2e_trace_v0.jsonl", ""),
            ("artifacts/effect_reports/p3_authority_coupled_synthetic_trace_v0.jsonl", ""),
            ("artifacts/effect_reports/p3_closeout_evidence_bundle_v0.json", ""),
            ("docs/reports/p6_final_seal_report_v0.md", ""),
            ("artifacts/effect_reports/p6_closeout_evidence_bundle_v0.json", ""),
            ("artifacts/effect_reports/p6_p3_handoff_trace_v0.jsonl", ""),
        ]:
            fp = os.path.join(d, rel)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            open(fp, "w").close()
        m = load_armor_manifest(d)
        assert m.manifest_complete is True
        assert m.missing_artifacts == []


def test_p2_hash_truth_required():
    m = P7ArmorEvidenceManifest()
    assert m.p2_hash_truth_required is True


def test_p2_anchor_truth_required():
    m = P7ArmorEvidenceManifest()
    assert m.p2_anchor_truth_required is True


def test_p4_verifier_required():
    m = P7ArmorEvidenceManifest()
    assert m.p4_verifier_required is True


def test_p4_claim_gate_required():
    m = P7ArmorEvidenceManifest()
    assert m.p4_claim_gate_required is True


def test_p5_selection_metadata_required():
    m = P7ArmorEvidenceManifest()
    assert m.p5_selection_metadata_required is True


def test_json_serializable():
    m = P7ArmorEvidenceManifest()
    json.dumps({"manifest_complete": m.manifest_complete, "blocked_reasons": m.blocked_reasons})
