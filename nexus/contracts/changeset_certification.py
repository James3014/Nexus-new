"""Provider-neutral v1 ChangeSet certification wire contract."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

CHANGESET_CERTIFICATION_SCHEMA = "nexus.changeset_certification.v1"
CHANGESET_CERTIFICATION_VERSION = 1
CLAIM_CEILING = "LOCAL_CHANGESET_CERTIFICATION_V1_CONTRACT_CANDIDATE_ONLY"
_STATUSES = frozenset({"CERTIFIED", "REJECTED", "BLOCKED"})
_VERIFIER_STATUSES = frozenset({"PASS", "FAIL"})
_HASH_LEN = 71
_REASONS = frozenset({
    "identity_missing",
    "identity_malformed",
    "evidence_missing",
    "evidence_malformed",
    "scope_missing",
    "scope_malformed",
    "candidate_missing",
    "candidate_malformed",
    "verifier_manifest_missing",
    "verifier_manifest_malformed",
    "verifier_missing",
    "verifier_failed",
    "verifier_artifact_missing",
    "verifier_artifact_malformed",
    "verifier_duplicate",
    "artifact_duplicate",
    "hash_mismatch",
    "manifest_hash_mismatch",
    "payload_hash_mismatch",
    "cross_binding_mismatch",
    "status_invalid",
    "reason_invalid",
    "schema_invalid",
    "unknown_field",
    "status_substitution",
    "change_set_missing",
    "identity_diff_hash_invalid",
    "evidence_0_invalid",
    "evidence_duplicate_id",
    "evidence_not_sequence",
})


class CertificationStatus(str, Enum):
    CERTIFIED = "CERTIFIED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ChangeSetIdentity:
    change_set_id: str
    source_revision: str
    target_revision: str
    diff_hash: str


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    kind: str
    content_hash: str
    source: str


@dataclass(frozen=True)
class ChangeSetCertification:
    change_set: ChangeSetIdentity
    evidence: tuple[EvidenceRef, ...] = ()
    status: CertificationStatus = CertificationStatus.BLOCKED
    reason_codes: tuple[str, ...] = ()
    envelope: Mapping[str, Any] | None = None
    schema: str = CHANGESET_CERTIFICATION_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        # Compatibility dataclasses never emit the superseded legacy wire form.
        return _copy(self.envelope) if self.envelope is not None else _minimal(self)

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    def canonical_hash(self) -> str:
        return canonical_hash(self.to_dict())


def canonical_json(value: Any) -> str:
    return json.dumps(
        _normalize(value, ()),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode()).hexdigest()


def certify_changeset(payload: Mapping[str, Any]) -> ChangeSetCertification:
    if not isinstance(payload, Mapping):
        return _blocked("identity_missing")
    if "change_set" in payload:
        return _certify_compatibility_input(payload)
    if any(key not in payload for key in ("task", "repository", "base", "diff")):
        return _result(payload, CertificationStatus.BLOCKED, ("identity_missing",))
    errors = _validate(payload)
    if errors:
        return _result(payload, _status_for(errors), errors)
    manifest = payload["verifier_manifest"]
    disposition = payload["disposition"]
    if disposition == "CERTIFIED" and any(v["status"] == "FAIL" for v in manifest["verifiers"]):
        return _result(payload, CertificationStatus.REJECTED, ("verifier_failed",))
    if disposition == "CERTIFIED" and payload["reasons"]:
        return _result(payload, CertificationStatus.REJECTED, ("status_invalid",))
    if disposition == "BLOCKED" and not payload["reasons"]:
        return _result(payload, CertificationStatus.REJECTED, ("reason_invalid",))
    if not _hashes_match(payload):
        return _result(payload, CertificationStatus.REJECTED, _hash_errors(payload))
    return _result(payload, CertificationStatus(disposition), tuple(payload["reasons"]))


def build_changeset_certification(
    *,
    change_set: Mapping[str, Any],
    evidence: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None,
) -> dict[str, Any]:
    """Build a complete v1 envelope from the compatibility convenience API."""
    if (
        not isinstance(change_set, Mapping)
        or not _texts(change_set, ("change_set_id", "source_revision", "target_revision"))
        or not _hash(change_set.get("diff_hash"))
    ):
        return _minimal_invalid("identity_missing")
    if not isinstance(evidence, (list, tuple)) or not evidence:
        return _minimal_invalid("evidence_missing")
    paths = [f"changeset/{change_set['change_set_id']}"]
    verifiers: list[dict[str, Any]] = []
    for item in evidence:
        if (
            not isinstance(item, Mapping)
            or not _texts(item, ("evidence_id", "kind", "source"))
            or not _hash(item.get("content_hash"))
        ):
            return _minimal_invalid("verifier_artifact_malformed")
        verifiers.append({
            "verifier_id": item["kind"],
            "artifact_id": f"{item['kind']}:attempt-1",
            "artifact_hash": item["content_hash"],
            "status": "PASS",
        })
    source = str(change_set["source_revision"])
    target = str(change_set["target_revision"])
    return _new_envelope(
        task={"task_id": str(change_set["change_set_id"]), "attempt_id": "attempt-1"},
        repository={"repository": "local", "source": source},
        base={"commit": source, "tree": source},
        diff={"hash": change_set["diff_hash"], "paths": paths},
        allowed_scope={"paths": paths, "deletion_policy": "FORBID"},
        candidate={"commit": target, "tree": target, "diff_hash": change_set["diff_hash"]},
        verifiers=verifiers,
        disposition="CERTIFIED",
        reasons=[],
    )


def _certify_compatibility_input(payload: Mapping[str, Any]) -> ChangeSetCertification:
    """Parse the retired convenience shape, but never emit it on the wire."""
    identity = payload.get("change_set")
    if not isinstance(identity, Mapping):
        return _blocked("change_set_missing")
    if payload.get("status") is not None:
        return _reject("status_substitution")
    if payload.get("canonical_hash") is not None:
        return _reject("canonical_hash_mismatch")
    if not _texts(identity, ("change_set_id", "source_revision", "target_revision")):
        return _blocked("identity_malformed")
    if not _hash(identity.get("diff_hash")):
        return _reject("identity_diff_hash_invalid")
    evidence = payload.get("evidence")
    if evidence is None:
        return _blocked("evidence_missing")
    if not isinstance(evidence, (list, tuple)):
        return _reject("evidence_not_sequence")
    if not evidence:
        return _blocked("evidence_empty")
    ids = []
    for item in evidence:
        if (
            not isinstance(item, Mapping)
            or not _texts(item, ("evidence_id", "kind", "source"))
            or not _hash(item.get("content_hash"))
        ):
            return _reject("evidence_0_invalid")
        ids.append(item["evidence_id"])
    if len(ids) != len(set(ids)):
        return _reject("evidence_duplicate_id")
    built = build_changeset_certification(change_set=identity, evidence=evidence)
    result = certify_changeset(built)
    return result


def validate_changeset_certification(
    certification: ChangeSetCertification | Mapping[str, Any],
) -> tuple[str, ...]:
    payload = (
        certification.to_dict()
        if isinstance(certification, ChangeSetCertification)
        else certification
    )
    if not isinstance(payload, Mapping):
        return ("identity_malformed",)
    errors = _validate(payload)
    if errors:
        return errors
    if payload["disposition"] == "CERTIFIED" and any(
        v["status"] == "FAIL" for v in payload["verifier_manifest"]["verifiers"]
    ):
        return ("verifier_failed",)
    if payload["disposition"] == "CERTIFIED" and payload["reasons"]:
        return ("status_invalid",)
    if payload["disposition"] == "BLOCKED" and not payload["reasons"]:
        return ("reason_invalid",)
    return _hash_errors(payload) if not _hashes_match(payload) else ()


def _validate(payload: Mapping[str, Any]) -> tuple[str, ...]:
    allowed = {
        "schema",
        "version",
        "task",
        "repository",
        "base",
        "diff",
        "allowed_scope",
        "candidate",
        "verifier_manifest",
        "disposition",
        "reasons",
        "claim_ceiling",
        "canonical_payload_hash",
    }
    if set(payload) - allowed:
        return ("unknown_field",)
    if (
        payload.get("schema") != CHANGESET_CERTIFICATION_SCHEMA
        or payload.get("version") != CHANGESET_CERTIFICATION_VERSION
    ):
        return ("schema_invalid",)
    task, repo, base, diff, scope = (
        payload.get(k) for k in ("task", "repository", "base", "diff", "allowed_scope")
    )
    if any(v is None for v in (task, repo, base, diff)):
        return ("identity_missing",)
    if (
        not isinstance(task, Mapping)
        or not _exact(task, {"task_id", "attempt_id"})
        or not _texts(task, ("task_id", "attempt_id"))
    ):
        return ("identity_malformed",)
    if (
        not isinstance(repo, Mapping)
        or not _exact(repo, {"repository", "source"})
        or not _texts(repo, ("repository", "source"))
    ):
        return ("identity_malformed",)
    if (
        not isinstance(base, Mapping)
        or not _exact(base, {"commit", "tree"})
        or not _texts(base, ("commit", "tree"))
    ):
        return ("identity_malformed",)
    if (
        not isinstance(diff, Mapping)
        or not _exact(diff, {"hash", "paths"})
        or not _hash(diff.get("hash"))
        or not _paths(diff.get("paths"))
    ):
        return ("identity_malformed",)
    if scope is None:
        return ("scope_missing",)
    if (
        not isinstance(scope, Mapping)
        or not _exact(scope, {"paths", "deletion_policy"})
        or not _paths(scope.get("paths"))
        or scope.get("deletion_policy") not in {"FORBID", "ALLOW"}
    ):
        return ("scope_malformed",)
    if not set(diff["paths"]).issubset(scope["paths"]):
        return ("cross_binding_mismatch",)
    candidate = payload.get("candidate")
    if candidate is not None and (
        not isinstance(candidate, Mapping)
        or not _exact(candidate, {"commit", "tree", "diff_hash"})
        or not _texts(candidate, ("commit", "tree"))
        or not _hash(candidate.get("diff_hash"))
    ):
        return ("candidate_malformed",)
    if candidate is not None and candidate["diff_hash"] != diff["hash"]:
        return ("cross_binding_mismatch",)
    manifest = payload.get("verifier_manifest")
    if manifest is None:
        return ("verifier_manifest_missing",)
    mkeys = {
        "manifest_id",
        "task_id",
        "attempt_id",
        "repository",
        "source",
        "base_commit",
        "base_tree",
        "candidate_commit",
        "candidate_tree",
        "diff_hash",
        "verifiers",
        "manifest_hash",
    }
    if (
        not isinstance(manifest, Mapping)
        or not _exact(manifest, mkeys)
        or not _texts(
            manifest,
            (
                "manifest_id",
                "task_id",
                "attempt_id",
                "repository",
                "source",
                "base_commit",
                "base_tree",
                "candidate_commit",
                "candidate_tree",
            ),
        )
        or not _hash(manifest.get("diff_hash"))
        or not _hash(manifest.get("manifest_hash"))
    ):
        return ("verifier_manifest_malformed",)
    expected = candidate or {"commit": "none", "tree": "none"}
    bindings = (
        manifest["task_id"],
        manifest["attempt_id"],
        manifest["repository"],
        manifest["source"],
        manifest["base_commit"],
        manifest["base_tree"],
        manifest["candidate_commit"],
        manifest["candidate_tree"],
        manifest["diff_hash"],
    )
    actual = (
        task["task_id"],
        task["attempt_id"],
        repo["repository"],
        repo["source"],
        base["commit"],
        base["tree"],
        expected["commit"],
        expected["tree"],
        diff["hash"],
    )
    if bindings != actual:
        return ("cross_binding_mismatch",)
    verifiers = manifest.get("verifiers")
    if not isinstance(verifiers, list) or not verifiers:
        return ("verifier_missing",)
    verifier_ids: set[str] = set()
    artifact_ids: set[str] = set()
    for verifier in verifiers:
        if not isinstance(verifier, Mapping):
            return ("verifier_artifact_malformed",)
        if (
            not _exact(verifier, {"verifier_id", "artifact_id", "artifact_hash", "status"})
            or not _texts(verifier, ("verifier_id", "artifact_id"))
            or not _hash(verifier.get("artifact_hash"))
        ):
            return ("verifier_artifact_missing",)
        if verifier["verifier_id"] in verifier_ids:
            return ("verifier_duplicate",)
        if verifier["artifact_id"] in artifact_ids:
            return ("artifact_duplicate",)
        verifier_ids.add(verifier["verifier_id"])
        artifact_ids.add(verifier["artifact_id"])
        if verifier.get("status") not in _VERIFIER_STATUSES:
            return ("verifier_artifact_malformed",)
        if verifier["artifact_id"] != f"{verifier['verifier_id']}:{task['attempt_id']}":
            return ("cross_binding_mismatch",)
    reasons = payload.get("reasons")
    if (
        not isinstance(reasons, list)
        or len(set(reasons)) != len(reasons)
        or any(not isinstance(r, str) or r not in _REASONS for r in reasons)
    ):
        return ("reason_invalid",)
    if payload.get("disposition") not in _STATUSES:
        return ("status_invalid",)
    if payload.get("claim_ceiling") != CLAIM_CEILING:
        return ("cross_binding_mismatch",)
    if not _hash(payload.get("canonical_payload_hash")):
        return ("payload_hash_mismatch",)
    return ()


def _new_envelope(
    *,
    task: dict[str, Any],
    repository: dict[str, Any],
    base: dict[str, Any],
    diff: dict[str, Any],
    allowed_scope: dict[str, Any],
    candidate: dict[str, Any] | None,
    verifiers: list[dict[str, Any]],
    disposition: str,
    reasons: list[str],
) -> dict[str, Any]:
    candidate = candidate or {"commit": "none", "tree": "none"}
    manifest = {
        "manifest_id": f"manifest:{task['attempt_id']}",
        "task_id": task["task_id"],
        "attempt_id": task["attempt_id"],
        "repository": repository["repository"],
        "source": repository["source"],
        "base_commit": base["commit"],
        "base_tree": base["tree"],
        "candidate_commit": candidate["commit"],
        "candidate_tree": candidate["tree"],
        "diff_hash": diff["hash"],
        "verifiers": verifiers,
    }
    manifest["manifest_hash"] = canonical_hash(manifest)
    payload = {
        "schema": CHANGESET_CERTIFICATION_SCHEMA,
        "version": CHANGESET_CERTIFICATION_VERSION,
        "task": task,
        "repository": repository,
        "base": base,
        "diff": diff,
        "allowed_scope": allowed_scope,
        "candidate": None if candidate["commit"] == "none" else candidate,
        "verifier_manifest": manifest,
        "disposition": disposition,
        "reasons": reasons,
        "claim_ceiling": CLAIM_CEILING,
    }
    payload["canonical_payload_hash"] = canonical_hash(payload)
    return payload


def _result(
    payload: Mapping[str, Any], status: CertificationStatus, reasons: tuple[str, ...]
) -> ChangeSetCertification:
    result = _copy(payload)
    result["schema"] = CHANGESET_CERTIFICATION_SCHEMA
    result["version"] = CHANGESET_CERTIFICATION_VERSION
    result["disposition"] = status.value
    result["reasons"] = list(sorted(set(reasons)))
    if isinstance(result.get("verifier_manifest"), dict):
        result["verifier_manifest"]["manifest_hash"] = canonical_hash(
            _manifest_input(result["verifier_manifest"])
        )
    result["canonical_payload_hash"] = canonical_hash(_payload_input(result))
    task = _as_mapping(result.get("task"))
    base = _as_mapping(result.get("base"))
    candidate = _as_mapping(result.get("candidate"))
    diff = _as_mapping(result.get("diff"))
    identity = ChangeSetIdentity(
        str(task.get("task_id", "")),
        str(base.get("commit", "")),
        str(candidate.get("commit", "")),
        str(diff.get("hash", "")),
    )
    return ChangeSetCertification(
        identity, status=status, reason_codes=tuple(sorted(set(reasons))), envelope=result
    )


def _status_for(errors: tuple[str, ...]) -> CertificationStatus:
    return (
        CertificationStatus.BLOCKED
        if errors[0]
        in {
            "identity_missing",
            "evidence_missing",
            "scope_missing",
            "candidate_missing",
            "verifier_manifest_missing",
            "verifier_missing",
            "verifier_artifact_missing",
        }
        else CertificationStatus.REJECTED
    )


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _hashes_match(payload: Mapping[str, Any]) -> bool:
    manifest = payload.get("verifier_manifest")
    return (
        isinstance(manifest, Mapping)
        and payload.get("canonical_payload_hash") == canonical_hash(_payload_input(payload))
        and manifest.get("manifest_hash") == canonical_hash(_manifest_input(manifest))
    )


def _hash_errors(payload: Mapping[str, Any]) -> tuple[str, ...]:
    out = []
    manifest = payload.get("verifier_manifest")
    if not isinstance(manifest, Mapping) or manifest.get("manifest_hash") != canonical_hash(
        _manifest_input(manifest)
    ):
        out.append("manifest_hash_mismatch")
    if payload.get("canonical_payload_hash") != canonical_hash(_payload_input(payload)):
        out.append("payload_hash_mismatch")
    return tuple(out) or ("hash_mismatch",)


def _payload_input(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _copy(payload)
    value.pop("canonical_payload_hash", None)
    return value


def _manifest_input(manifest: Mapping[str, Any]) -> dict[str, Any]:
    value = _copy(manifest)
    value.pop("manifest_hash", None)
    return value


def _minimal(result: ChangeSetCertification) -> dict[str, Any]:
    return _minimal_invalid(result.reason_codes[0] if result.reason_codes else "identity_missing")


def _minimal_invalid(reason: str) -> dict[str, Any]:
    return _new_envelope(
        task={"task_id": "missing", "attempt_id": "missing"},
        repository={"repository": "missing", "source": "missing"},
        base={"commit": "missing", "tree": "missing"},
        diff={"hash": "sha256:" + "0" * 64, "paths": ["missing"]},
        allowed_scope={"paths": ["missing"], "deletion_policy": "FORBID"},
        candidate=None,
        verifiers=[
            {
                "verifier_id": "missing",
                "artifact_id": "missing:missing",
                "artifact_hash": "sha256:" + "0" * 64,
                "status": "FAIL",
            }
        ],
        disposition="BLOCKED",
        reasons=[reason],
    )


def _blocked(reason: str) -> ChangeSetCertification:
    return ChangeSetCertification(
        ChangeSetIdentity("", "", "", ""),
        status=CertificationStatus.BLOCKED,
        reason_codes=(reason,),
    )


def _reject(reason: str) -> ChangeSetCertification:
    return ChangeSetCertification(
        ChangeSetIdentity("", "", "", ""),
        status=CertificationStatus.REJECTED,
        reason_codes=(reason,),
    )


def _texts(value: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
    return all(isinstance(value.get(k), str) and bool(value[k].strip()) for k in keys)


def _exact(value: Mapping[str, Any], expected: set[str]) -> bool:
    return set(value) == expected


def _hash(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _HASH_LEN
        and value.startswith("sha256:")
        and all(c in "0123456789abcdef" for c in value[7:].lower())
    )


def _paths(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and len(set(value)) == len(value)
        and all(isinstance(p, str) and p and not p.startswith("/") for p in value)
    )


def _normalize(value: Any, path: tuple[str, ...]) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("canonical JSON values must be finite")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(k, str) for k in value):
            raise TypeError("canonical JSON keys must be strings")
        return {k: _normalize(value[k], path + (k,)) for k in sorted(value)}
    if isinstance(value, list):
        items = [_normalize(item, path) for item in value]
        return (
            sorted(items, key=canonical_json)
            if path and path[-1] in {"paths", "reasons", "verifiers", "evidence"}
            else items
        )
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def _copy(value: Any) -> dict[str, Any]:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
