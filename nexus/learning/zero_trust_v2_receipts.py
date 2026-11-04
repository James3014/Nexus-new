from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Mapping

# Fixed purpose inside the signed content, so a value signed as another kind with the same
# key cannot verify as a receipt (#3362).
RECEIPT_SIGNATURE_PURPOSE = "nexus.zero_trust_v2.runtime_receipt"


def canonical_json_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_runtime_signed_receipt(
    *,
    run_id: str,
    row_id: str,
    arm_id: str,
    capability_id: str,
    skill_id: str,
    artifact_hash: str,
    raw_observation: Mapping[str, Any],
    secret: str,
    observer_version: str = "mock-v1",
    source_skill_id: str | None = None,
    evidence_kind: str | None = None,
) -> dict[str, Any]:
    """``source_skill_id`` and ``evidence_kind`` are signed when given, so a reader can
    derive what a row proves from signed content instead of its own columns (#3355)."""
    raw_observation_hash = canonical_json_hash(raw_observation)
    signature_inputs = {
        "run_id": run_id,
        "row_id": row_id,
        "arm_id": arm_id,
        "capability_id": capability_id,
        "skill_id": skill_id,
        "artifact_hash": artifact_hash,
        "raw_observation_hash": raw_observation_hash,
        "signature_purpose": RECEIPT_SIGNATURE_PURPOSE,
    }
    if source_skill_id is not None:
        signature_inputs["source_skill_id"] = source_skill_id
    if evidence_kind is not None:
        signature_inputs["evidence_kind"] = evidence_kind
    receipt_hash = canonical_json_hash(signature_inputs)
    signature = hmac.new(secret.encode("utf-8"), receipt_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "receipt_provenance": "runtime_signed",
        "receipt_signature": signature,
        "receipt_signature_algorithm": "hmac-sha256",
        "receipt_signature_inputs": {**signature_inputs, "receipt_hash": receipt_hash},
        "observer": {"issuer": "nexus.runtime_observer", "version": observer_version},
    }


def _digest_equal(expected: str, claimed: Any) -> bool:
    """Constant-time compare on bytes, so a non-ASCII claimed value is a plain mismatch."""
    return hmac.compare_digest(
        expected.encode("utf-8", "surrogatepass"),
        str(claimed or "").encode("utf-8", "surrogatepass"),
    )


def verify_runtime_signed_receipt(
    receipt: Mapping[str, Any], *, secret: str, expected: Mapping[str, Any] | None = None
) -> bool:
    """``expected`` (e.g. run_id, row_id, capability_id) binds the receipt to the item the
    caller plans to credit: each given field must equal the signed input (#3366)."""
    if receipt.get("receipt_provenance") != "runtime_signed":
        return False
    if receipt.get("receipt_signature_algorithm") != "hmac-sha256":
        return False
    inputs = receipt.get("receipt_signature_inputs")
    if not isinstance(inputs, Mapping):
        return False
    if inputs.get("signature_purpose") != RECEIPT_SIGNATURE_PURPOSE:
        return False
    receipt_hash = str(inputs.get("receipt_hash") or "")
    if not receipt_hash:
        return False
    # The signature covers the hash only; the inputs a reader acts on must hash to it (#3355).
    signed_inputs = {key: value for key, value in inputs.items() if key != "receipt_hash"}
    if canonical_json_hash(signed_inputs) != receipt_hash:
        return False
    for key, value in (expected or {}).items():
        if key not in signed_inputs or signed_inputs[key] != value:
            return False
    signature = hmac.new(secret.encode("utf-8"), receipt_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    return _digest_equal(signature, receipt.get("receipt_signature"))


def stamp_runtime_signed_behavior_bundle(
    bundle: Mapping[str, Any],
    *,
    run_id: str,
    capability_id: str,
    skill_id: str,
    secret: str,
    observer_version: str = "zero-trust-v2-behavior-hook-v1",
) -> dict[str, Any]:
    row_counts = bundle.get("row_counts") if isinstance(bundle.get("row_counts"), Mapping) else {}
    rubric = bundle.get("rubric_contract") if isinstance(bundle.get("rubric_contract"), Mapping) else {}
    with_rubric = rubric.get("with_nexus") if isinstance(rubric.get("with_nexus"), Mapping) else {}
    hard_failures = list(with_rubric.get("hard_fail_reasons") or [])
    eligible_rows = int(row_counts.get("eligible_with_nexus") or 0)
    infra_invalid_rows = int(row_counts.get("infra_invalid_with_nexus") or 0)
    blockers: list[str] = []
    if eligible_rows <= 0:
        blockers.append("no_eligible_behavior_row")
    if infra_invalid_rows > 0:
        blockers.append("infra_invalid_behavior_row")
    blockers.extend(str(item) for item in hard_failures if str(item))
    if blockers:
        return {"status": "BLOCKED", "blockers": sorted(set(blockers)), "bundle": dict(bundle)}

    raw_files = bundle.get("raw_files") if isinstance(bundle.get("raw_files"), Mapping) else {}
    with_file = raw_files.get("with_nexus") if isinstance(raw_files.get("with_nexus"), Mapping) else {}
    artifact_hash = str(with_file.get("sha256") or canonical_json_hash(bundle))
    raw_observation = {
        "row_counts": dict(row_counts),
        "raw_files": dict(raw_files),
        "rubric_contract": dict(rubric),
        "run_identity": bundle.get("run_identity") if isinstance(bundle.get("run_identity"), Mapping) else {},
        "task_manifest": bundle.get("task_manifest") if isinstance(bundle.get("task_manifest"), Mapping) else {},
    }
    receipt = build_runtime_signed_receipt(
        run_id=run_id,
        row_id=f"{run_id}:with_nexus",
        arm_id="candidate_skill_v2",
        capability_id=capability_id,
        skill_id=skill_id,
        artifact_hash=artifact_hash,
        raw_observation=raw_observation,
        secret=secret,
        observer_version=observer_version,
    )
    stamped = dict(bundle)
    stamped["zero_trust_v2_runtime_receipt"] = receipt
    stamped["zero_trust_v2_runtime_receipt_export"] = {
        "status": "PASS",
        "observer_version": observer_version,
        "capability_id": capability_id,
        "skill_id": skill_id,
        "artifact_hash": artifact_hash,
    }
    return {"status": "PASS", "blockers": [], "bundle": stamped, "receipt": receipt}


# Intermediate-report signatures (#3374). A purpose different from receipts and attestations, and
# a report kind inside the signed content, so a signature made for one thing cannot verify as
# another. The signature covers only the fields the combining report acts on.
REPORT_SIGNATURE_PURPOSE = "nexus.zero_trust_v2.report"
REPORT_SIGNING_SECRET_ENV = "NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET"
REPORT_KIND_M45_M52 = "m45_m52_completion"
REPORT_KIND_MANUAL_TRIAL = "manual_trial"
REPORT_KIND_ROLLOUT = "p0_rollout"
REPORT_KIND_RUNTIME_APPLY = "runtime_apply_decision"
REPORT_KIND_POST_APPLY_SMOKE = "post_apply_smoke"
REPORT_KINDS = (
    REPORT_KIND_M45_M52,
    REPORT_KIND_MANUAL_TRIAL,
    REPORT_KIND_ROLLOUT,
    REPORT_KIND_RUNTIME_APPLY,
    REPORT_KIND_POST_APPLY_SMOKE,
)


def load_signing_secret(path: str | None = None) -> str:
    """Environment variable first, then the named file; empty when neither gives a key. Never
    creates a key."""
    import os
    from pathlib import Path

    env_secret = os.environ.get(REPORT_SIGNING_SECRET_ENV, "").strip()
    if env_secret:
        return env_secret
    if path and Path(path).is_file():
        return Path(path).read_text(encoding="utf-8").strip()
    return ""


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def report_signed_fields(kind: str, report: Mapping[str, Any]) -> dict[str, Any] | None:
    """The fields of ``report`` that the combining report uses, or None for an unknown kind."""
    summary = _dict(report.get("summary"))
    if kind == REPORT_KIND_M45_M52:
        blockers: set[str] = set()
        for item in _list(report.get("m45_behavior_run_results")):
            if isinstance(item, Mapping):
                blockers.update(str(b) for b in _list(item.get("blockers")) if str(b))
        for item in _list(_dict(report.get("m46_receipt_import_gate")).get("dominant_blockers")):
            if isinstance(item, Mapping) and item.get("reason"):
                blockers.add(str(item["reason"]))
        return {
            "blockers": sorted(blockers),
            "m45_clean_v2_receipt_count": summary.get("m45_clean_v2_receipt_count"),
            "m51_v2_ready_capability_count": summary.get("m51_v2_ready_capability_count"),
        }
    if kind == REPORT_KIND_MANUAL_TRIAL:
        return {
            "status": report.get("status"),
            "manual_apply_trial_ready": summary.get("manual_apply_trial_ready"),
            "blockers": report.get("blockers"),
        }
    if kind == REPORT_KIND_ROLLOUT:
        return {
            "status": report.get("status"),
            "p0_rollout_complete": summary.get("p0_rollout_complete"),
            "p1_p2_rollout_complete": summary.get("p1_p2_rollout_complete"),
        }
    if kind == REPORT_KIND_RUNTIME_APPLY:
        return {
            "status": report.get("status"),
            "runtime_update_allowed": summary.get("runtime_update_allowed"),
            "v2_default_applied_count": summary.get("v2_default_applied_count"),
            "blockers": report.get("blockers"),
        }
    if kind == REPORT_KIND_POST_APPLY_SMOKE:
        return {
            "status": report.get("status"),
            "case_count": summary.get("case_count"),
            "pass_count": summary.get("pass_count"),
        }
    return None


def _report_signature_value(
    kind: str, fields: Mapping[str, Any], secret: str, purpose: str = REPORT_SIGNATURE_PURPOSE
) -> str:
    digest = canonical_json_hash({
        "signature_purpose": purpose,
        "report_kind": kind,
        "fields": dict(fields),
    })
    return hmac.new(secret.encode("utf-8"), digest.encode("utf-8"), hashlib.sha256).hexdigest()


def sign_report(report: Mapping[str, Any], *, kind: str, secret: str) -> dict[str, Any]:
    """A copy of ``report`` with ``report_signature`` over the fields the combining report uses."""
    fields = report_signed_fields(kind, report)
    if fields is None or not secret:
        raise ValueError("cannot sign report: unknown kind or empty key")
    signed = {key: value for key, value in report.items() if key != "report_signature"}
    signed["report_signature"] = {
        "signature_purpose": REPORT_SIGNATURE_PURPOSE,
        "report_kind": kind,
        "algorithm": "hmac-sha256",
        "fields": fields,
        "signature": _report_signature_value(kind, fields, secret),
    }
    return signed


def sign_report_if_keyed(
    report: Mapping[str, Any], *, kind: str, secret: str | None
) -> dict[str, Any]:
    """Unchanged copy when no key is given; otherwise signed."""
    if not secret:
        return dict(report)
    return sign_report(report, kind=kind, secret=secret)


def verify_report_signature(report: Any, *, kind: str, secret: str | None) -> bool:
    """True only when the signature has the report purpose and the expected kind, the signed
    fields equal what the report holds now, and the HMAC matches."""
    if not secret or not isinstance(report, Mapping):
        return False
    sig = report.get("report_signature")
    if not isinstance(sig, Mapping):
        return False
    if sig.get("signature_purpose") != REPORT_SIGNATURE_PURPOSE:
        return False
    if sig.get("report_kind") != kind or sig.get("algorithm") != "hmac-sha256":
        return False
    current = report_signed_fields(kind, report)
    if current is None or sig.get("fields") != current:
        return False
    # The digest covers the purpose and kind the signature declares, so the two checks above are
    # what bind it to this use.
    expected = _report_signature_value(
        str(sig.get("report_kind")), current, secret, str(sig.get("signature_purpose"))
    )
    return _digest_equal(expected, sig.get("signature"))
