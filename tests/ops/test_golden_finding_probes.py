"""Positive and negative controls for Issue #117 Golden finding probes."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
import urllib.error
from typing import Any

import pytest

from scripts.ops import run_golden_behavior_eval as evaluator
from scripts.ops.gateway_health_hmac import KEY_FILE_ENV, path_hmac
from tests.golden_behavior.corpus import CASES

EVAL_ROOT = "/srv/nexus/deployments/r1"
HMAC_KEY = bytes(range(32))
EVAL_ROOT_HMAC = path_hmac("repo_root", EVAL_ROOT, HMAC_KEY)
EVALUATED = "1" * 40
OTHER = "2" * 40


@pytest.fixture(autouse=True)
def _health_hmac_key(tmp_path, monkeypatch):
    key_file = tmp_path / "health-hmac.key"
    key_file.write_text(HMAC_KEY.hex() + "\n")
    key_file.chmod(0o600)
    monkeypatch.setenv(KEY_FILE_ENV, str(key_file))


def _health(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "ok",
        "server": "nexus-mcp-gateway",
        "repo_root_hmac_sha256": EVAL_ROOT_HMAC,
        "git_head": EVALUATED,
        "repo_head_at_start": EVALUATED,
        "repo_head_current": EVALUATED,
        "reload_required": False,
        "server_instance_id": "instance-1",
        "tool_manifest_revision": "manifest-1",
        "permission_policy_hash": "policy-1",
        "full_tool_schema_hash": "schema-1",
    }
    payload.update(overrides)
    return payload


def _gb077(payload: Any = None, *, identity: tuple[str | None, bool | None] = (EVALUATED, False)):
    def fetch() -> Any:
        if isinstance(payload, BaseException):
            raise payload
        return _health() if payload is None else payload

    passed, detail = evaluator.probe_gb077_live_gateway_identity(
        fetch_health=fetch,
        evaluated_identity=lambda: identity,
        evaluated_root=lambda: EVAL_ROOT,
    )
    return passed, json.loads(detail)


def test_gb077_positive_exact_loaded_identity_passes_without_promotion() -> None:
    passed, detail = _gb077()
    assert passed is True
    assert detail["result"] == "PASS"
    assert detail["probe_class"] == "RUNTIME_IDENTITY_PROBE"
    assert detail["promotes_status"] is False
    assert detail["reasons"] == []


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (
            _health(git_head=OTHER, repo_head_at_start=OTHER, repo_head_current=OTHER),
            "gateway_loaded_revision_not_evaluated_revision",
        ),
        (_health(repo_head_at_start=OTHER), "gateway_loaded_source_drift"),
        (_health(reload_required=True), "gateway_reload_required_not_false"),
        (_health(reload_required="false"), "gateway_reload_required_not_false"),
        (_health(server="impostor-gateway"), "gateway_server_identity_mismatch"),
        (_health(status="degraded"), "gateway_status_not_ok"),
        (_health(git_head="unknown"), "gateway_field_malformed:git_head"),
        (_health(server_instance_id=""), "gateway_field_malformed:server_instance_id"),
    ],
    ids=[
        "stale_head",
        "loaded_vs_current_drift",
        "reload_required",
        "reload_required_wrong_type",
        "substituted_server",
        "status_not_ok",
        "malformed_head",
        "empty_instance",
    ],
)
def test_gb077_stale_tampered_or_substituted_identity_fails_closed(
    payload: dict[str, Any], reason: str
) -> None:
    passed, detail = _gb077(payload)
    assert passed is False
    assert reason in detail["reasons"]


@pytest.mark.parametrize(
    "field",
    [
        "git_head",
        "repo_head_at_start",
        "repo_head_current",
        "repo_root_hmac_sha256",
        "server_instance_id",
        "tool_manifest_revision",
        "permission_policy_hash",
        "full_tool_schema_hash",
    ],
)
def test_gb077_missing_identity_field_fails_closed(field: str) -> None:
    payload = _health()
    del payload[field]
    passed, detail = _gb077(payload)
    assert passed is False
    assert f"gateway_field_missing:{field}" in detail["reasons"]


def test_gb077_missing_reload_flag_fails_closed() -> None:
    payload = _health()
    del payload["reload_required"]
    passed, detail = _gb077(payload)
    assert passed is False
    assert "gateway_reload_required_missing" in detail["reasons"]


@pytest.mark.parametrize(
    "error",
    [urllib.error.URLError("connection refused"), TimeoutError("timed out"), ValueError("json")],
)
def test_gb077_unreachable_gateway_fails_closed(error: BaseException) -> None:
    passed, detail = _gb077(error)
    assert passed is False
    assert detail["reasons"] == [f"gateway_unreachable:{type(error).__name__}"]


def test_gb077_non_object_health_fails_closed() -> None:
    passed, detail = _gb077(["not", "an", "object"])
    assert passed is False
    assert detail["reasons"] == ["gateway_health_not_object"]


@pytest.mark.parametrize(
    ("identity", "reason"),
    [
        ((EVALUATED, True), "evaluated_source_not_clean"),
        ((EVALUATED, None), "evaluated_source_not_clean"),
        ((None, False), "evaluated_revision_unavailable"),
    ],
)
def test_gb077_unbound_evaluated_source_fails_closed(
    identity: tuple[str | None, bool | None], reason: str
) -> None:
    passed, detail = _gb077(identity=identity)
    assert passed is False
    assert reason in detail["reasons"]


def test_gb077_endpoint_is_fixed_loopback() -> None:
    assert evaluator.GATEWAY_HEALTH_URL == "http://127.0.0.1:8766/health"


def _gb079(api: dict[str, Any] | None = None) -> tuple[bool, dict[str, Any]]:
    passed, detail = evaluator.probe_gb079_continuity_replay(api=api)
    return passed, json.loads(detail)


def test_gb079_positive_replay_passes_without_promotion() -> None:
    passed, detail = _gb079()
    assert passed is True, detail
    assert detail["probe_class"] == "CONTINUITY_REPLAY_PROBE"
    assert detail["promotes_status"] is False
    assert detail["observed"]["protected_field_loss"] == []
    assert detail["observed"]["decoded_types"] == [
        "PLAN_FORMED",
        "ATTEMPT_REJECTED",
        "OBSERVATION_RECORDED",
    ]


def _api(**overrides: Any) -> dict[str, Any]:
    api = evaluator._continuity_api()
    api.update(overrides)
    return api


def test_gb079_fails_when_resume_accepts_stale_snapshot() -> None:
    real = evaluator._continuity_api()["resume"]

    def stale_blind_resume(snapshot: Any, tail: Any, **kwargs: Any) -> Any:
        kwargs["source_revision"] = snapshot.source_revision
        kwargs["contract_revision"] = snapshot.contract_revision
        return real(snapshot, tail, **kwargs)

    passed, detail = _gb079(_api(resume=stale_blind_resume))
    assert passed is False
    assert "negative_accepted:stale_snapshot_source" in detail["reasons"]
    assert "negative_accepted:stale_snapshot_contract" in detail["reasons"]


def test_gb079_fails_when_resume_accepts_substituted_snapshot_hash() -> None:
    real = evaluator._continuity_api()["resume"]

    def hash_blind_resume(snapshot: Any, tail: Any, **kwargs: Any) -> Any:
        kwargs.pop("snapshot_hash", None)
        return real(snapshot, tail, **kwargs)

    passed, detail = _gb079(_api(resume=hash_blind_resume))
    assert passed is False
    assert detail["reasons"] == ["negative_accepted:substituted_snapshot_hash"]


def test_gb079_fails_on_protected_field_loss() -> None:
    real = evaluator._continuity_api()["project"]

    def lossy_project(events: Any) -> Any:
        return dataclasses.replace(real(events), rejected_strategies=())

    passed, detail = _gb079(_api(project=lossy_project))
    assert passed is False
    assert "positive_protected_field_lost:do_not_repeat" in detail["reasons"]


def test_gb079_fails_when_decoder_accepts_cross_task_records() -> None:
    real = evaluator._continuity_api()["events_from_attempt_records"]

    def identity_blind_decode(records: Any, *, task_id: str, attempt_id: str) -> Any:
        first = records[0]["payload"]
        return real(records, task_id=first["task_id"], attempt_id=first["attempt_id"])

    passed, detail = _gb079(_api(events_from_attempt_records=identity_blind_decode))
    assert passed is False
    assert "negative_accepted:cross_task_records" in detail["reasons"]


def test_gb079_fails_when_api_is_unavailable() -> None:
    api = _api()
    del api["resume"]
    passed, detail = _gb079(api)
    assert passed is False
    assert detail["reasons"] == ["continuity_api_unavailable:KeyError"]


def test_probe_registry_is_classified_and_bound_only_to_findings() -> None:
    assert set(evaluator.PROBES) == set(evaluator.PROBE_CLASSES)
    assert set(evaluator.PROBE_CLASSES.values()) <= evaluator.PROBE_CLASS_VALUES
    bound = {case.case_id: case for case in CASES if case.finding_probe}
    assert {case_id: case.finding_probe for case_id, case in bound.items()} == {
        "GB-077": "gb077_live_gateway_identity",
    }
    assert "gb077_live_gateway_identity" in evaluator.PROBES
    # GB-079 was reconciled to covered; its replay probe stays registered but
    # unbound, which validate_corpus permits (it only checks bound probe ids).
    assert "gb079_continuity_replay" in evaluator.PROBES
    assert all(case.status == "finding" for case in bound.values())


def test_validate_corpus_rejects_unclassified_or_covered_probe_binding(monkeypatch) -> None:
    covered = next(case for case in CASES if case.status == "covered")
    finding = next(case for case in CASES if case.case_id == "GB-077")
    monkeypatch.setattr(
        evaluator,
        "CASES",
        (
            dataclasses.replace(covered, finding_probe="gb079_continuity_replay"),
            dataclasses.replace(finding, finding_probe="gb_unclassified"),
        ),
    )
    monkeypatch.setitem(evaluator.PROBES, "gb_unclassified", lambda: (True, "x"))
    errors = evaluator.validate_corpus()
    assert f"{covered.case_id}:finding_probe_on_non_finding" in errors
    assert "GB-077:unclassified_finding_probe" in errors


def test_include_findings_stays_nonzero_even_when_probe_passes(monkeypatch, capsys) -> None:
    monkeypatch.setitem(evaluator.PROBES, "gb077_live_gateway_identity", lambda: (True, "pass"))
    bound_cases = tuple(
        dataclasses.replace(case, finding_probe="gb077_live_gateway_identity")
        if case.case_id == "GB-077"
        else case
        for case in evaluator.CASES
    )
    monkeypatch.setattr(evaluator, "CASES", bound_cases)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_golden_behavior_eval.py",
            "--case",
            "GB-077",
            "--include-findings",
            "--validate-only",
        ],
    )
    exit_code = evaluator.main()
    report = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert report["validation_errors"] == []
    assert report["finding_probe_results"]["GB-077"] == {
        "probe": "gb077_live_gateway_identity",
        "probe_class": "RUNTIME_IDENTITY_PROBE",
        "passed": True,
        "detail": "pass",
        "finding_unresolved": True,
    }
    assert report["case_evidence"][0]["status"] == "finding"


def test_gb077_accepts_legacy_repo_root_from_pre_2217_gateway() -> None:
    payload = _health()
    del payload["repo_root_hmac_sha256"]
    payload["repo_root"] = EVAL_ROOT
    passed, _detail = _gb077(payload)
    assert passed is True


@pytest.mark.parametrize(
    ("overrides", "drop", "reason"),
    [
        ({"repo_root_hmac_sha256": "b" * 64}, (), "gateway_repo_root_not_evaluated_root"),
        ({"repo_root_hmac_sha256": "XYZ"}, (), "gateway_field_malformed:repo_root_hmac_sha256"),
        ({"repo_root_hmac_sha256": "A" * 64}, (), "gateway_field_malformed:repo_root_hmac_sha256"),
        (
            {"repo_root": "/srv/nexus/deployments/other"},
            ("repo_root_hmac_sha256",),
            "gateway_repo_root_not_evaluated_root",
        ),
        ({"repo_root": "  "}, ("repo_root_hmac_sha256",), "gateway_field_malformed:repo_root"),
    ],
)
def test_gb077_repo_root_must_be_the_evaluated_root(overrides, drop, reason) -> None:
    payload = _health(**overrides)
    for name in drop:
        del payload[name]
    passed, detail = _gb077(payload)
    assert passed is False
    assert reason in detail["reasons"]


def test_gb077_accepts_only_the_hmac_of_the_evaluated_root() -> None:
    passed, _detail = _gb077(_health())
    assert passed is True
    wrong = path_hmac("repo_root", "/srv/nexus/deployments/other", HMAC_KEY)
    passed, detail = _gb077(_health(repo_root_hmac_sha256=wrong))
    assert passed is False
    assert "gateway_repo_root_not_evaluated_root" in detail["reasons"]


def test_gb077_rejects_a_guessable_plain_sha256_of_the_root() -> None:
    plain = hashlib.sha256(EVAL_ROOT.encode()).hexdigest()
    passed, detail = _gb077(_health(repo_root_hmac_sha256=plain))
    assert passed is False
    assert "gateway_repo_root_not_evaluated_root" in detail["reasons"]
    # The pre-#2226 field name no longer satisfies the probe.
    payload = _health()
    del payload["repo_root_hmac_sha256"]
    payload["repo_root_sha256"] = plain
    passed, detail = _gb077(payload)
    assert passed is False
    assert "gateway_field_missing:repo_root_hmac_sha256" in detail["reasons"]


def test_gb077_hmac_from_another_host_key_is_rejected() -> None:
    other = path_hmac("repo_root", EVAL_ROOT, bytes(range(1, 33)))
    passed, detail = _gb077(_health(repo_root_hmac_sha256=other))
    assert passed is False
    assert "gateway_repo_root_not_evaluated_root" in detail["reasons"]


def test_gb077_fails_closed_when_the_hmac_key_is_unusable(tmp_path, monkeypatch) -> None:
    bad = tmp_path / "loose.key"
    bad.write_text(HMAC_KEY.hex() + "\n")
    bad.chmod(0o644)
    monkeypatch.setenv(KEY_FILE_ENV, str(bad))
    passed, detail = _gb077()
    assert passed is False
    assert "gateway_health_hmac_key_unavailable" in detail["reasons"]
