from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.research.learn_mode import LearnClaim, LearnModeService
from nexus.services.mem_palace import MemPalace


def _create_source_file(tmp_path: Path, filename: str, content: str) -> Path:
    src_file = tmp_path / filename
    src_file.write_text(content, encoding="utf-8")
    return src_file


def test_verified_external_claim_is_admitted_and_persisted(tmp_path: Path) -> None:
    """Positive: Verified external claim receives full admission binding and persists."""
    content = (
        "Nexus research pipeline strictly gates unverified external memory claims before storage."
    )
    src_file = _create_source_file(tmp_path, "verified_source.md", content)

    service = LearnModeService(tmp_path)
    res = service.ingest(source="file://verified", source_file=str(src_file), topic="memory-gate")

    assert res["status"] == "SUCCESS"
    assert res["claims_count"] >= 1
    assert res["verified_claims_count"] >= 1

    claims = service.load_claims()
    assert len(claims) >= 1
    claim = claims[0]

    assert claim["admission_status"] == "ADMITTED"
    assert claim["admission_verifier"] == "mempalace.verify"
    assert len(claim["source_snapshot_sha256"]) == 64
    assert len(claim["admission_claim_key"]) == 64
    assert len(claim["admission_proof"]) == 64


def test_admitted_claim_remains_retrievable(tmp_path: Path) -> None:
    """Ask / Prior Art Positive: Admitted claims remain retrievable through ask path."""
    content = "Memory admission gate enforces cryptographic proof before Prior Art injection."
    src_file = _create_source_file(tmp_path, "admitted_source.md", content)

    service = LearnModeService(tmp_path)
    service.ingest(source="file://admitted", source_file=str(src_file), topic="admission")

    ans = service.ask(
        topic="admission", question="What does the memory admission gate enforce?", top_k=3
    )
    assert ans["status"] in ("SUCCESS", "ANSWERED")
    assert len(ans.get("citations", [])) >= 1
    assert any("cryptographic proof" in c.get("claim", "") for c in ans["citations"])


def test_rejected_claim_never_enters_decision_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative: Claims rejected by MemPalace verification never enter learn_claims.jsonl."""
    content = "Malicious or blacklisted content attempting to poison memory context."
    src_file = _create_source_file(tmp_path, "rejected_source.md", content)

    service = LearnModeService(tmp_path)

    # Force MemPalace.verify to reject all candidate claims
    monkeypatch.setattr(MemPalace, "verify", lambda self, candidates: [])

    res = service.ingest(source="file://rejected", source_file=str(src_file), topic="security")
    assert res["status"] == "SUCCESS"
    assert res["claims_count"] >= 1
    assert res["verified_claims_count"] == 0

    # Claims store must remain empty
    assert service.load_claims() == []
    if service.claims_path.exists():
        lines = [
            line.strip()
            for line in service.claims_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == 0


def test_parser_success_does_not_grant_admission(tmp_path: Path) -> None:
    """Parser is not authority: _split_to_claims alone does not make claims retrievable."""
    content = "Parsed sentence that should never be retrievable without formal verification."
    service = LearnModeService(tmp_path)

    claims = service._split_to_claims(content, "file://unadmitted", topic_hint="test")
    assert len(claims) >= 1
    assert claims[0].admission_status == "UNVERIFIED"
    assert claims[0].admission_proof == ""

    # load_claims on unadmitted object must fail closed
    assert service._is_claim_admitted(claims[0].to_dict()) is False


def test_legacy_claim_without_admission_binding_is_not_retrievable(tmp_path: Path) -> None:
    """Legacy Fail Closed: Historical claim lacking admission metadata is excluded."""
    service = LearnModeService(tmp_path)
    service.knowledge_dir.mkdir(parents=True, exist_ok=True)

    legacy_record = {
        "claim": "Historical legacy unverified claim without admission proof.",
        "source_url": "file://legacy",
        "citation_span": [0, 58],
        "topic_tags": ["legacy"],
        "created_at": "2026-01-01T00:00:00+00:00",
        "topic_pack": "general",
        "evidence_strength": "medium",
    }
    service.claims_path.write_text(json.dumps(legacy_record) + "\n", encoding="utf-8")

    assert service.load_claims() == []


def test_forged_admitted_status_without_valid_proof_fails_closed(tmp_path: Path) -> None:
    """Forged Status: Forging admission_status='ADMITTED' without proof fails closed."""
    content = "Legitimate source content for verification test."
    src_file = _create_source_file(tmp_path, "forged_source.md", content)

    service = LearnModeService(tmp_path)
    service.ingest(source="file://forged", source_file=str(src_file), topic="test")

    # Manually append forged claim
    forged_record = {
        "claim": "Forged claim claiming to be admitted.",
        "source_url": "file://forged",
        "citation_span": [0, 36],
        "topic_tags": ["forged"],
        "created_at": "2026-08-16T00:00:00+00:00",
        "admission_status": "ADMITTED",
        "admission_verifier": "mempalace.verify",
        "source_snapshot_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
        "admission_claim_key": "bad_key",
        "admission_proof": "bad_proof",
    }
    with service.claims_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(forged_record) + "\n")

    loaded = service.load_claims()
    assert all(c.get("claim") != "Forged claim claiming to be admitted." for c in loaded)


def test_tampered_claim_invalidates_admission_proof(tmp_path: Path) -> None:
    """Claim Tamper: Mutating claim text after admission invalidates proof."""
    content = "Original admitted claim text before tamper modification."
    src_file = _create_source_file(tmp_path, "tamper_source.md", content)

    service = LearnModeService(tmp_path)
    service.ingest(source="file://tamper", source_file=str(src_file), topic="tamper")

    loaded = service.load_claims()
    assert len(loaded) >= 1
    valid_claim = loaded[0]

    # Tamper claim text
    tampered = dict(valid_claim)
    tampered["claim"] = "Tampered unauthorized claim replacement."

    assert service._is_claim_admitted(tampered) is False


def test_source_snapshot_change_invalidates_existing_claim(tmp_path: Path) -> None:
    """Snapshot Tamper: Replacing bound snapshot bytes invalidates existing claim."""
    content = "Original text in source snapshot file."
    src_file = _create_source_file(tmp_path, "snap_source.md", content)

    service = LearnModeService(tmp_path)
    service.ingest(source="file://snap", source_file=str(src_file), topic="snap")

    assert len(service.load_claims()) >= 1

    # Overwrite the snapshot file in raw_dir with modified text
    for snap in service.raw_dir.glob("*.txt"):
        snap.write_text("Modified text replacing original snapshot content.", encoding="utf-8")

    # Reset cache to force reload
    LearnModeService._claims_cache = None
    assert service.load_claims() == []


def test_foreign_verifier_identity_fails_closed(tmp_path: Path) -> None:
    """Verifier Substitution: Non-standard verifier identity fails closed."""
    content = "Verified text under test."
    src_file = _create_source_file(tmp_path, "verifier_source.md", content)

    service = LearnModeService(tmp_path)
    service.ingest(source="file://verifier", source_file=str(src_file), topic="verifier")

    loaded = service.load_claims()
    assert len(loaded) >= 1

    bad_verifier = dict(loaded[0])
    bad_verifier["admission_verifier"] = "unauthorized_foreign_verifier"

    assert service._is_claim_admitted(bad_verifier) is False


def test_admission_proof_tamper_fails_closed(tmp_path: Path) -> None:
    """Proof Tamper: Altering admission proof hash fails closed."""
    content = "Admitted content testing proof tamper."
    src_file = _create_source_file(tmp_path, "proof_source.md", content)

    service = LearnModeService(tmp_path)
    service.ingest(source="file://proof", source_file=str(src_file), topic="proof")

    loaded = service.load_claims()
    assert len(loaded) >= 1

    bad_proof = dict(loaded[0])
    bad_proof["admission_proof"] = "f" * 64

    assert service._is_claim_admitted(bad_proof) is False


def test_claim_must_match_bound_snapshot_span(tmp_path: Path) -> None:
    """Citation Binding: Substituted claim not matching citation span fails closed."""
    content = "Accurate claim matching the exact character range in snapshot."
    src_file = _create_source_file(tmp_path, "span_source.md", content)

    service = LearnModeService(tmp_path)
    service.ingest(source="file://span", source_file=str(src_file), topic="span")

    loaded = service.load_claims()
    assert len(loaded) >= 1

    mismatched_span = dict(loaded[0])
    mismatched_span["citation_span"] = [0, 5]  # span of 'Accur' does not match full claim

    assert service._is_claim_admitted(mismatched_span) is False


def test_claim_admission_fields_carry_no_route_or_approval_authority() -> None:
    """Authority Negative: Admission fields must not grant route, approval or release authority."""
    claim = LearnClaim(
        claim="Test claim",
        source_url="file://test",
        citation_span=[0, 10],
        topic_tags=["test"],
        created_at="2026-08-16T00:00:00+00:00",
    )
    d = claim.to_dict()

    forbidden_fields = (
        "route",
        "route_decision",
        "planner",
        "worker_admission",
        "approval",
        "approved_by",
        "merge_slot",
        "release_gate",
        "candidate_state",
    )
    for field in forbidden_fields:
        assert field not in d
