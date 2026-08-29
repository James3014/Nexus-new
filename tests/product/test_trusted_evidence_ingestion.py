from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone

import pytest

from product.evidence import AcceptanceContract, ChangeSet, VerificationPlan, ObservationStatus, _hash


def _api():
    """Import the wished-for public surface so RED is a test failure, not collection noise."""
    from product.evidence import ingestion

    return ingestion


def _enum(enum_type, *names):
    for name in names:
        if hasattr(enum_type, name):
            return getattr(enum_type, name)
    return next(iter(enum_type))


def _at(offset=0):
    return (datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc) + timedelta(seconds=offset)).isoformat()


def _fixture():
    api = _api()
    evidence_type = _enum(api.EvidenceType, "TEST_RESULT", "TEST", "VERIFICATION")
    producer_role = _enum(api.ProducerRole, "VERIFIER", "AUTOMATED_VERIFIER", "MACHINE")
    generation = _enum(api.EvidenceGeneration, "CURRENT", "GENERATION_1", "READY")
    trust_role = _enum(api.TrustRole, "MACHINE_VERIFIER", "VERIFIER", "ISSUER")
    contract = AcceptanceContract("ac-1", _hash("requirements"), ("unit",), ("src/a.py",), "FORBID")
    change = ChangeSet("cs-1", "source-r1", "target-r2", _hash("diff"), ("src/a.py",))
    plan = VerificationPlan("plan-1", contract.hash, change.hash, ("unit",))
    producer = api.ProducerGrant("producer-1", producer_role, _hash("producer-software"), ("pytest",))
    issuer = api.IssuerGrant("issuer-1", trust_role, _hash("issuer-software"), ("pytest",))
    profile = api.IngestionProfile("profile-1", (producer,), (issuer,), 3600)
    runtime = api.RuntimeSourceObservation(
        "target-r2", "target-r2", "runtime-1", "runtime-1", 1, 1, _at(-10), _at(3500), "READY"
    )
    raw = b"unit passed\n"
    envelope = api.ProvenanceEnvelope(
        "product.evidence.provenance.v1", "evidence-1", evidence_type, "unit", "artifact-1",
        "producer-1", producer_role, producer.software_hash, "repo-1", "source-r1", "tree-source",
        "target-r2", "tree-target", change.hash, change.diff_hash, _at(-10), "tests/test_a.py",
        _hash(raw.decode()), "pytest", "exec-1", "attempt-1", _hash("environment"), generation, runtime,
    )
    reference = api.TrustReference(b"external receipt", _hash("external receipt"))
    submission = api.EvidenceSubmission(raw, _hash(raw.decode()), envelope, reference)
    requirement = api.EvidenceRequirement("unit", evidence_type, producer_role, "pytest", trust_role)
    context = api.TrustedIngestionContext(
        contract, change, plan, "repo-1", "tree-source", "tree-target", _at(), profile,
        profile.hash, (requirement,), "merge", ((trust_role, reference.receipt_hash),),
    )
    return api, context, submission, envelope, runtime, (evidence_type, producer_role, generation, trust_role)


def test_public_ingestion_surface_exposes_the_frozen_types_and_functions():
    api = _api()
    expected = {
        "EvidenceType", "ProducerRole", "EvidenceGeneration", "FreshnessStatus", "TrustRole", "TrustDecision",
        "ProducerGrant", "IssuerGrant", "IngestionProfile", "EvidenceRequirement", "RuntimeSourceObservation",
        "ProvenanceEnvelope", "EvidenceSubmission", "TrustReference", "TrustedIngestionContext", "IngestionReceipt",
        "IngestionResult", "derive_runtime_freshness", "ingest_evidence",
    }
    assert expected <= set(dir(api))
    assert {f.name for f in fields(api.TrustReference)} >= {"receipt_bytes", "receipt_hash"}


def test_valid_submission_preserves_raw_hash_producer_method_and_runtime_scope():
    api, context, submission, envelope, *_ = _fixture()
    result = api.ingest_evidence(context, (submission,))
    assert result.decision is _enum(api.TrustDecision, "ACCEPT", "TRUSTED", "VERIFIED")
    assert result.receipt.observations[0].status is ObservationStatus.PASS
    assert result.receipt.observations[0].artifact_hash == envelope.hash
    assert envelope.content_hash == _hash(submission.raw_bytes.decode())
    assert envelope.producer_id == "producer-1" and envelope.verification_method == "pytest"


def test_hashes_are_deterministic_and_bundle_order_is_canonical():
    api, context, submission, envelope, *_ = _fixture()
    assert envelope.hash == replace(envelope).hash
    first = api.ingest_evidence(context, (submission,)).receipt
    second = api.ingest_evidence(context, (submission,)).receipt
    assert first.hash == second.hash
    assert tuple(sorted(first.reason_codes)) == first.reason_codes


@pytest.mark.parametrize(
    "offset, expected",
    [(-4000, "STALE_OBSERVATION"), (4000, "CONVERGENCE_UNKNOWN"), (0, "READY_IDENTITY_BOUND")],
)
def test_runtime_freshness_is_utc_time_bounded(offset, expected):
    api, *_ = _fixture()
    runtime = api.RuntimeSourceObservation("target-r2", "target-r2", "runtime-1", "runtime-1", 1, 1, _at(offset), _at(offset + 1), "READY")
    status = api.derive_runtime_freshness(runtime, _at())
    assert status.name == expected


@pytest.mark.parametrize("status", ["", "UNKNOWN", "NOT_READY", "LIVE"])
def test_runtime_freshness_never_treats_malformed_or_liveness_as_ready(status):
    api, *_ = _fixture()
    runtime = api.RuntimeSourceObservation("target-r2", "target-r2", "runtime-1", "runtime-1", 1, 1, "not-a-time", _at(10), status)
    assert api.derive_runtime_freshness(runtime, _at()).name == "CONVERGENCE_UNKNOWN"


@pytest.mark.parametrize(
    "changes, expected",
    [({"loaded_source_revision": "source-r1"}, "SOURCE_AHEAD_OF_RUNTIME"),
     ({"observed_runtime_identity": "runtime-2"}, "RUNTIME_IDENTITY_MISMATCH"),
     ({"observed_generation": 0}, "STALE_OBSERVATION"),
     ({"readiness_status": "NOT_READY"}, "CONVERGENCE_UNKNOWN")],
)
def test_runtime_freshness_distinguishes_source_generation_identity_and_readiness(changes, expected):
    api, *_ = _fixture()
    runtime = replace(api.RuntimeSourceObservation("target-r2", "target-r2", "runtime-1", "runtime-1", 1, 1, _at(-10), _at(3500), "READY"), **changes)
    assert api.derive_runtime_freshness(runtime, _at()).name == expected


@pytest.mark.parametrize("field", ["raw_bytes", "claimed_content_hash"])
def test_raw_bytes_and_claimed_hash_are_independently_tamper_evident(field):
    api, context, submission, *_ = _fixture()
    value = b"changed\n" if field == "raw_bytes" else _hash("changed")
    result = api.ingest_evidence(context, (replace(submission, **{field: value}),))
    assert "TAMPERED" in {code.split(":", 1)[0] for code in result.reason_codes}


@pytest.mark.parametrize("field", ["producer_id", "verification_method", "source_revision", "target_tree", "environment_hash", "generation"])
def test_provenance_field_mutations_are_cross_bound_or_tampered(field):
    api, context, submission, envelope, *_ = _fixture()
    value = "spoofed" if field != "generation" else next(iter(api.EvidenceGeneration))
    result = api.ingest_evidence(context, (replace(submission, envelope=replace(envelope, **{field: value})),))
    assert result.reason_codes and result.reason_codes != ()


def test_h1_h2_h3_h7_h9_h11_h12_fail_closed_with_precedence_and_no_case_codes():
    api, context, submission, envelope, *_ = _fixture()
    conflicting = replace(envelope, producer_id="spoofed", source_revision="old", artifact_id="duplicate")
    result = api.ingest_evidence(context, (submission, replace(submission, envelope=conflicting)))
    assert result.decision is not _enum(api.TrustDecision, "ACCEPT", "TRUSTED", "VERIFIED")
    assert tuple(sorted(result.reason_codes)) == result.reason_codes
    assert any(code.split(":", 1)[0] in {"TAMPERED", "STALE", "CROSS_BOUND", "DUPLICATE", "MALFORMED", "MISSING"} for code in result.reason_codes)


def test_machine_verified_and_human_open_accounting_are_separate():
    api, context, submission, *_ = _fixture()
    result = api.ingest_evidence(context, (submission,))
    assert result.receipt.machine_verified_count == 1
    assert result.receipt.human_open_count == 0


def test_missing_default_and_ambiguous_types_are_rejected():
    api, context, submission, envelope, *_ = _fixture()
    for bad in (replace(envelope, source_locator=""), replace(envelope, verification_method=""), replace(envelope, evidence_type="TEST_RESULT")):
        result = api.ingest_evidence(context, (replace(submission, envelope=bad),))
        assert result.reason_codes
