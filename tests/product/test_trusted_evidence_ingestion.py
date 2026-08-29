import hashlib
import itertools
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone

import pytest

from product.evidence import AcceptanceContract, ChangeSet, ObservationStatus, VerificationPlan, _hash


def _api():
    from product.evidence import ingestion
    return ingestion


def _at(seconds=0):
    return (datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _runtime(api, **changes):
    values = dict(generation=api.EvidenceGeneration.RUNTIME, desired_source_revision="target-r2", loaded_source_revision="target-r2", desired_generation=7, observed_generation=7, observed_at=_at(-10), expires_at=_at(3500), expected_runtime_identity="runtime-1", observed_runtime_identity="runtime-1", readiness_status="READY")
    values.update(changes)
    return api.RuntimeSourceObservation(**values)


def _fixture():
    api = _api()
    contract = AcceptanceContract("ac-1", _hash("requirements"), ("unit",), ("src/a.py",), "FORBID")
    change = ChangeSet("cs-1", "source-r1", "target-r2", _hash("diff"), ("src/a.py",))
    plan = VerificationPlan("plan-1", contract.hash, change.hash, ("unit",))
    producer = api.ProducerGrant("producer-1", api.ProducerRole.VERIFIER, _hash("producer-software"), ("pytest",))
    issuer = api.IssuerGrant("issuer-1", (api.TrustRole.AUTHORITY,), ("merge",), ("pytest",))
    profile = api.IngestionProfile("profile-1", (producer,), (issuer,), 3600)
    raw = b"unit passed\n"
    runtime = _runtime(api)
    envelope = api.ProvenanceEnvelope("product.evidence.provenance.v1", "evidence-1", api.EvidenceType.VERIFIER_RESULT, "unit", "artifact-1", "producer-1", api.ProducerRole.VERIFIER, producer.software_hash, "repo-1", "source-r1", "tree-source", "target-r2", "tree-target", change.hash, change.diff_hash, _at(-10), "tests/test_a.py", "sha256:" + hashlib.sha256(raw).hexdigest(), "pytest", "exec-1", "attempt-1", _hash("environment"), api.EvidenceGeneration.RUNTIME, runtime)
    submission = api.EvidenceSubmission(raw, ObservationStatus.PASS, envelope)
    requirement = api.EvidenceRequirement("unit", "artifact-1", api.EvidenceType.VERIFIER_RESULT, api.EvidenceGeneration.RUNTIME, "producer-1", "exec-1", "attempt-1", _hash("environment"), "sha256:" + hashlib.sha256(raw).hexdigest(), envelope.hash, True, False)
    reference = api.TrustReference(api.TrustRole.AUTHORITY, "evidence-1", "issuer-1", _hash("subject"), "merge", api.TrustDecision.ALLOW, _at(-20), _at(3500), None, _hash("payload"), _hash("signed-payload"), "pytest", b"external receipt", "sha256:" + hashlib.sha256(b"external receipt").hexdigest())
    context = api.TrustedIngestionContext(contract, change, plan, "repo-1", "tree-source", "tree-target", _at(), profile, profile.hash, (requirement,), "merge", ((api.TrustRole.AUTHORITY, reference.payload_hash),))
    return api, context, submission, envelope


def test_public_api_and_exact_enum_members_are_frozen():
    api = _api()
    assert set(api.EvidenceType.__members__) == {"VERIFIER_RESULT", "CI_CHECK", "MANUAL_REVIEW", "RUNTIME_OBSERVATION", "LEGACY_RECORD"}
    assert set(api.ProducerRole.__members__) == {"VERIFIER", "CI", "REVIEWER", "OWNER", "SIGNER", "RUNTIME"}
    assert set(api.EvidenceGeneration.__members__) == {"SOURCE", "EXECUTION", "RUNTIME", "LEGACY_NARRATIVE"}
    assert set(api.FreshnessStatus.__members__) == {"SOURCE_ALIGNED", "SOURCE_AHEAD_OF_RUNTIME", "RUNTIME_IDENTITY_MISMATCH", "STALE_OBSERVATION", "READY_IDENTITY_BOUND", "CONVERGENCE_UNKNOWN"}
    assert set(api.TrustRole.__members__) == {"POLICY", "AUTHORITY", "APPROVAL", "SIGNING"}
    assert set(api.TrustDecision.__members__) == {"ALLOW", "DENY"}


def test_exact_dataclass_fields_and_order_are_frozen():
    api = _api()
    expected = {"ProducerGrant": ("producer_id", "role", "software_hash", "verification_methods"), "IssuerGrant": ("issuer_id", "roles", "actions", "verification_methods"), "IngestionProfile": ("profile_id", "producers", "issuers", "max_age_seconds"), "EvidenceRequirement": ("verifier_id", "artifact_id", "evidence_type", "generation", "producer_id", "execution_id", "attempt_id", "environment_hash", "content_hash", "provenance_hash", "runtime_ready_required", "human_semantic_review_required"), "EvidenceSubmission": ("content", "status", "provenance"), "IngestionResult": ("bundle", "receipt", "condition", "reason_codes")}
    for name, names in expected.items():
        assert tuple(field.name for field in fields(getattr(api, name))) == names
    assert tuple(field.name for field in fields(api.RuntimeSourceObservation)) == ("generation", "desired_source_revision", "loaded_source_revision", "desired_generation", "observed_generation", "observed_at", "expires_at", "expected_runtime_identity", "observed_runtime_identity", "readiness_status")
    assert tuple(field.name for field in fields(api.ProvenanceEnvelope)) == ("schema", "evidence_id", "evidence_type", "verifier_id", "artifact_id", "producer_id", "producer_role", "producer_software_hash", "repository_id", "source_revision", "source_tree", "target_revision", "target_tree", "change_set_hash", "diff_hash", "generated_at", "source_locator", "content_hash", "verification_method", "execution_id", "attempt_id", "environment_hash", "generation", "runtime")
    assert tuple(field.name for field in fields(api.TrustedIngestionContext)) == ("contract", "change_set", "plan", "repository_id", "source_tree", "target_tree", "observed_at", "profile", "expected_profile_hash", "requirements", "required_action", "prerequisite_payload_hashes")
    assert tuple(field.name for field in fields(api.IngestionReceipt)) == ("context_hash", "profile_hash", "bundle_hash", "raw_content_hashes", "provenance_hashes", "observations", "freshness", "machine_verified_artifact_ids", "human_open_artifact_ids", "human_open_reasons", "missing_verifier_ids", "reason_codes", "receipt_hash")
    assert tuple(field.name for field in fields(api.TrustReference)) == ("role", "evidence_id", "issuer_id", "subject_hash", "action", "decision", "issued_at", "expires_at", "revoked_at", "payload_hash", "signed_payload_hash", "verification_method", "external_verification_receipt", "external_verification_receipt_hash")


def test_every_frozen_ingestion_contract_is_immutable():
    api = _api()
    names = ("ProducerGrant", "IssuerGrant", "IngestionProfile", "EvidenceRequirement", "RuntimeSourceObservation", "ProvenanceEnvelope", "EvidenceSubmission", "TrustReference", "TrustedIngestionContext", "IngestionReceipt", "IngestionResult")
    assert all(getattr(api, name).__dataclass_params__.frozen for name in names)


def test_valid_ingestion_binds_raw_hash_and_provenance_envelope_hash():
    api, context, submission, envelope = _fixture()
    result = api.ingest_evidence(context, (submission,))
    assert result.bundle is not None
    assert result.condition is api.IntegrityStatus.VALID and result.reason_codes == ()
    assert result.receipt.observations[0].status is ObservationStatus.PASS
    assert result.receipt.observations[0].artifact_hash == envelope.hash
    assert result.receipt.raw_content_hashes == (envelope.content_hash,)
    assert result.receipt.provenance_hashes == (envelope.hash,)
    assert envelope.content_hash == "sha256:" + hashlib.sha256(submission.content).hexdigest()


def test_deterministic_hashes_and_sorted_reasons():
    api, context, submission, envelope = _fixture()
    assert envelope.hash == replace(envelope).hash
    assert api.ingest_evidence(context, (submission,)).receipt.hash == api.ingest_evidence(context, (submission,)).receipt.hash
    failed = api.ingest_evidence(context, (replace(submission, content=b"changed"), submission))
    assert tuple(sorted(set(failed.reason_codes))) == failed.reason_codes
    assert failed.bundle is None
    assert not any("required_verifier=" in reason for reason in failed.reason_codes)


@pytest.mark.parametrize("changes", [{"observed_at": _at(4000)}, {"expires_at": _at(-1)}, {"observed_generation": 6}])
def test_future_expired_or_generation_stale_is_stale(changes):
    api, *_ = _fixture()
    assert api.derive_runtime_freshness(_runtime(api, **changes), _at()).name == "STALE_OBSERVATION"


@pytest.mark.parametrize("changes", [{"observed_at": "not-utc"}, {"observed_at": "2026-08-29T12:00:00"}])
def test_missing_or_non_utc_time_is_unknown(changes):
    api, *_ = _fixture()
    assert api.derive_runtime_freshness(_runtime(api, **changes), _at()).name == "CONVERGENCE_UNKNOWN"


def test_freshness_truth_table_covers_source_runtime_and_ready_identity():
    api, *_ = _fixture()
    assert api.derive_runtime_freshness(_runtime(api, loaded_source_revision="source-r1"), _at()).name == "SOURCE_AHEAD_OF_RUNTIME"
    assert api.derive_runtime_freshness(_runtime(api, observed_runtime_identity="runtime-2"), _at()).name == "RUNTIME_IDENTITY_MISMATCH"
    assert api.derive_runtime_freshness(_runtime(api, generation=api.EvidenceGeneration.SOURCE, expected_runtime_identity=None, observed_runtime_identity=None, readiness_status=None), _at()).name == "SOURCE_ALIGNED"
    assert api.derive_runtime_freshness(_runtime(api, readiness_status="LIVE"), _at()).name == "CONVERGENCE_UNKNOWN"
    assert api.derive_runtime_freshness(_runtime(api), _at()).name == "READY_IDENTITY_BOUND"


@pytest.mark.parametrize("generation", ["EXECUTION", "LEGACY_NARRATIVE"])
def test_non_runtime_generation_observation_is_rejected(generation):
    api, *_ = _fixture()
    with pytest.raises(ValueError):
        _runtime(api, generation=getattr(api.EvidenceGeneration, generation))


def test_condition_helper_has_closed_vocabulary_and_exact_precedence():
    api = _api()
    assert api.condition_for_ingestion_reasons(()) is api.IntegrityStatus.VALID
    ordered = ["TAMPERED:content_hash", "STALE:observation", "CROSS_BOUND:runtime", "DUPLICATE:artifact", "MALFORMED:submission", "MISSING:prerequisite"]
    for index, reason in enumerate(ordered):
        assert api.condition_for_ingestion_reasons(tuple(ordered[index:])) is getattr(api.IntegrityStatus, reason.split(":")[0])
    for invalid in ("UNKNOWN:reason", "MALFORMED:unknown", "CROSS_BOUND:unknown", "TAMPERED:unknown"):
        with pytest.raises(ValueError):
            api.condition_for_ingestion_reasons((invalid,))
    for permutation in itertools.permutations(ordered):
        assert api.condition_for_ingestion_reasons(permutation) is api.IntegrityStatus.TAMPERED
    for index, higher in enumerate(ordered):
        for lower in ordered[index + 1:]:
            assert api.condition_for_ingestion_reasons((lower, higher)) is getattr(api.IntegrityStatus, higher.split(":")[0])


def test_content_and_envelope_hash_mutations_are_independently_tampered():
    api, context, submission, envelope = _fixture()
    content_result = api.ingest_evidence(context, (replace(submission, content=b"changed\n"),))
    envelope_result = api.ingest_evidence(context, (replace(submission, provenance=replace(envelope, content_hash=_hash("changed"))),))
    assert content_result.condition is api.IntegrityStatus.TAMPERED and "TAMPERED:content_hash" in content_result.reason_codes
    assert envelope_result.condition is api.IntegrityStatus.TAMPERED and "TAMPERED:provenance_hash" in envelope_result.reason_codes


def test_requirement_content_and_provenance_trust_roots_are_independently_pinned():
    api, context, submission, _ = _fixture()
    content = replace(context.requirements[0], content_hash=_hash("wrong"))
    provenance = replace(context.requirements[0], provenance_hash=_hash("wrong"))
    content_result = api.ingest_evidence(replace(context, requirements=(content,)), (submission,))
    provenance_result = api.ingest_evidence(replace(context, requirements=(provenance,)), (submission,))
    assert content_result.condition is api.IntegrityStatus.TAMPERED and "TAMPERED:content_hash" in content_result.reason_codes
    assert provenance_result.condition is api.IntegrityStatus.TAMPERED and "TAMPERED:provenance_hash" in provenance_result.reason_codes


def test_combined_raw_and_claimed_hash_attack_has_no_bundle():
    api, context, submission, envelope = _fixture()
    forged = replace(submission, content=b"forged", provenance=replace(envelope, content_hash="sha256:" + hashlib.sha256(b"forged").hexdigest()))
    result = api.ingest_evidence(context, (forged,))
    assert result.bundle is None and result.condition is api.IntegrityStatus.TAMPERED
    assert "TAMPERED:content_hash" in result.reason_codes


@pytest.mark.parametrize("field, condition, reason", [("artifact_id", "TAMPERED", "TAMPERED:provenance_hash"), ("target_revision", "TAMPERED", "TAMPERED:provenance_hash"), ("producer_id", "TAMPERED", "TAMPERED:provenance_hash")])
def test_h1_h2_h3_h9_h11_are_separate_fail_closed_cases(field, condition, reason):
    api, context, submission, envelope = _fixture()
    value = "other" if field != "evidence_type" else "VERIFIER_RESULT"
    result = api.ingest_evidence(context, (replace(submission, provenance=replace(envelope, **{field: value})),))
    assert result.condition is getattr(api.IntegrityStatus, condition) and reason in result.reason_codes
    assert result.bundle is None


def test_h7_old_readiness_generation_is_stale():
    api, context, submission, envelope = _fixture()
    result = api.ingest_evidence(context, (replace(submission, provenance=replace(envelope, runtime=_runtime(api, observed_generation=6))),))
    assert result.condition is api.IntegrityStatus.TAMPERED and "TAMPERED:provenance_hash" in result.reason_codes
    assert result.bundle is None


@pytest.mark.parametrize("field, value, reason", [
    ("producer_software_hash", _hash("other-software"), "CROSS_BOUND:producer"),
    ("producer_role", "CI", "CROSS_BOUND:producer"),
    ("verification_method", "other-method", "CROSS_BOUND:producer"),
    ("repository_id", "other-repo", "CROSS_BOUND:repository"),
    ("source_revision", "old-source", "STALE:subject"),
    ("target_revision", "old-target", "STALE:subject"),
    ("source_tree", "other-source-tree", "CROSS_BOUND:tree"),
    ("target_tree", "other-target-tree", "CROSS_BOUND:tree"),
    ("change_set_hash", _hash("other-change"), "CROSS_BOUND:changeset"),
    ("diff_hash", _hash("other-diff"), "CROSS_BOUND:changeset"),
    ("artifact_id", "other-artifact", "CROSS_BOUND:artifact"),
    ("execution_id", "other-execution", "CROSS_BOUND:execution"),
    ("attempt_id", "other-attempt", "CROSS_BOUND:execution"),
    ("environment_hash", _hash("other-environment"), "CROSS_BOUND:execution"),
    ("runtime", _runtime, "CROSS_BOUND:runtime"),
])
def test_updating_requirement_hash_cannot_bypass_semantic_binding(field, value, reason):
    api, context, submission, envelope = _fixture()
    if field == "producer_role":
        value = api.ProducerRole.CI
    if field == "runtime":
        value = value(api, observed_runtime_identity="runtime-2")
    mutated = replace(envelope, **{field: value})
    requirement = replace(context.requirements[0], content_hash=mutated.content_hash, provenance_hash=mutated.hash)
    result = api.ingest_evidence(replace(context, requirements=(requirement,)), (replace(submission, provenance=mutated),))
    assert result.condition is getattr(api.IntegrityStatus, reason.split(":")[0])
    assert reason in result.reason_codes


@pytest.mark.parametrize("field", ["schema", "evidence_id", "evidence_type", "verifier_id", "artifact_id", "producer_id", "producer_role", "producer_software_hash", "repository_id", "source_revision", "source_tree", "target_revision", "target_tree", "change_set_hash", "diff_hash", "generated_at", "source_locator", "content_hash", "verification_method", "execution_id", "attempt_id", "environment_hash", "generation", "runtime"])
def test_every_provenance_field_mutation_is_rejected(field):
    api, context, submission, envelope = _fixture()
    value = _hash("mutated") if field.endswith("_hash") or field == "content_hash" else (_at(-5) if field == "generated_at" else api.EvidenceGeneration.SOURCE if field == "generation" else _runtime(api, observed_generation=8) if field == "runtime" else api.EvidenceType.CI_CHECK if field == "evidence_type" else api.ProducerRole.CI if field == "producer_role" else "mutated")
    result = api.ingest_evidence(context, (replace(submission, provenance=replace(envelope, **{field: value})),))
    assert result.condition is api.IntegrityStatus.TAMPERED
    assert "TAMPERED:provenance_hash" in result.reason_codes


def test_h12_identical_and_conflicting_duplicates_are_distinct():
    api, context, submission, envelope = _fixture()
    identical = api.ingest_evidence(context, (submission, submission))
    conflicting = api.ingest_evidence(context, (submission, replace(submission, provenance=replace(envelope, verifier_id="other"))))
    assert identical.condition is api.IntegrityStatus.DUPLICATE and "DUPLICATE:artifact" in identical.reason_codes
    assert conflicting.condition is api.IntegrityStatus.TAMPERED and "TAMPERED:provenance_hash" in conflicting.reason_codes


def test_condition_precedence_is_tampered_over_lower_conditions():
    api, context, submission, *_ = _fixture()
    result = api.ingest_evidence(context, (replace(submission, content=b"changed\n"), submission))
    assert result.condition is api.IntegrityStatus.TAMPERED


def test_machine_and_human_semantic_review_accounting_are_separate():
    api, context, submission, *_ = _fixture()
    machine = api.ingest_evidence(context, (submission,))
    human_context = replace(context, requirements=(replace(context.requirements[0], human_semantic_review_required=True),))
    human = api.ingest_evidence(human_context, (submission,))
    assert machine.receipt.machine_verified_count == 1 and machine.receipt.human_open_count == 0
    assert human.receipt.machine_verified_count == 1 and human.receipt.human_open_count == 1
    assert human.reason_codes == ()
    assert human.receipt.human_open_reasons == (("artifact-1", "semantic_review_required"),)


def test_constructor_type_bounds_sorted_and_duplicate_guards_fail_closed():
    api = _api()
    with pytest.raises((TypeError, ValueError)):
        api.IngestionProfile("p", [], (), 0)
    with pytest.raises((TypeError, ValueError)):
        api.ProducerGrant("p", api.ProducerRole.VERIFIER, _hash("x"), ("m", "m"))


def test_empty_locator_and_string_enum_are_rejected_by_the_envelope_constructor():
    api, _, _, envelope = _fixture()
    with pytest.raises((TypeError, ValueError)):
        replace(envelope, source_locator="")
    with pytest.raises((TypeError, ValueError)):
        replace(envelope, evidence_type="VERIFIER_RESULT")


def _hostile_envelope(envelope, **changes):
    forged = object.__new__(type(envelope))
    for field in fields(envelope):
        object.__setattr__(forged, field.name, changes.get(field.name, getattr(envelope, field.name)))
    return forged


def test_h9_forged_blank_locator_is_missing_at_admission():
    api, context, submission, envelope = _fixture()
    forged = _hostile_envelope(envelope, source_locator="")
    requirement = replace(context.requirements[0], provenance_hash=forged.hash)
    result = api.ingest_evidence(replace(context, requirements=(requirement,)), (api.EvidenceSubmission(submission.content, submission.status, forged),))
    assert result.bundle is None
    assert result.condition is api.IntegrityStatus.MISSING
    assert "MISSING:source_locator" in result.reason_codes


def test_h11_forged_string_enum_is_malformed_before_hash_admission():
    api, context, submission, envelope = _fixture()
    forged = _hostile_envelope(envelope, evidence_type="VERIFIER_RESULT")
    result = api.ingest_evidence(context, (api.EvidenceSubmission(submission.content, submission.status, forged),))
    assert result.bundle is None
    assert result.condition is api.IntegrityStatus.MALFORMED
    assert "MALFORMED:evidence_type" in result.reason_codes


def test_required_constructor_argument_cannot_be_omitted():
    api = _api()
    with pytest.raises(TypeError):
        api.EvidenceSubmission(b"content", ObservationStatus.PASS)


def test_multi_submission_attack_keeps_all_reason_codes_sorted_unique_and_top_condition():
    api, context, submission, envelope = _fixture()
    stale = replace(submission, provenance=replace(envelope, target_revision="stale"))
    forged = replace(submission, content=b"forged")
    result = api.ingest_evidence(context, (forged, stale, submission, submission))
    assert result.bundle is None and result.condition is api.IntegrityStatus.TAMPERED
    assert tuple(sorted(set(result.reason_codes))) == result.reason_codes
