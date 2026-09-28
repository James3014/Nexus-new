from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

EVIDENCE_SCHEMA = "nexus.clm_candidate_evidence.v1"
COLLECTION_RESULT_SCHEMA = "nexus.clm_candidate_evidence_collection.v1"
GROUP_MANIFEST_SCHEMA = "nexus.clm_candidate_evidence_group_manifest.v1"
DEFAULT_RELATIVE_ROOT = Path(".nexus") / "research" / "clm_system_one" / "candidate_evidence"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _identity_sha256(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str) and not value.strip():
        return ""
    if isinstance(value, (Mapping, Sequence, set, frozenset)) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        if len(value) == 0:
            return ""
    return _sha256_json(value)


def _normalized_sha256(value: str) -> str:
    raw = str(value or "").strip().lower()
    if raw.startswith("sha256:"):
        raw = raw.split(":", 1)[1]
    if len(raw) == 64 and all(ch in "0123456789abcdef" for ch in raw):
        return raw
    return ""


def _normalized_git_oid(value: str) -> str:
    raw = str(value or "").strip().lower()
    if len(raw) in {40, 64} and all(ch in "0123456789abcdef" for ch in raw):
        return raw
    return ""


def _normalize_verifier_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in {"pass", "passed", "verified", "success", "succeeded"}:
        return "PASS"
    if status in {"fail", "failed", "rejected", "failure"}:
        return "FAIL"
    return "UNKNOWN"


def _env_enabled() -> bool:
    raw = os.getenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ENABLED", "1").strip().lower()
    return raw not in {"0", "false", "off", "no", "disabled"}


def _env_rate_percent() -> int:
    raw = os.getenv("NEXUS_CLM_CANDIDATE_EVIDENCE_RATE_PERCENT", "100").strip()
    try:
        rate = int(raw)
    except ValueError:
        return 100
    return max(0, min(100, rate))


def _resolve_source_revision(repo_root: Path, explicit: str) -> str:
    value = str(explicit or "").strip()
    if value:
        normalized = _normalized_git_oid(value)
        if not normalized:
            raise ValueError("invalid source revision")
        return normalized
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def _write_create_only(path: Path, payload: bytes) -> bool:
    """Atomically publish immutable content.

    The temporary file is fully written and fsynced before it is hard-linked
    into the content-addressed final path.  Concurrent writers therefore see
    either no final object or a complete one, never a partially written file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing != payload:
            raise RuntimeError(f"immutable evidence collision: {path}")
        return False

    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp_path, path)
        except FileExistsError:
            existing = path.read_bytes()
            if existing != payload:
                raise RuntimeError(f"immutable evidence collision: {path}")
            return False
        return True
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def _preflight_create_only(path: Path, payload: bytes) -> None:
    if not path.exists():
        return
    if path.read_bytes() != payload:
        raise RuntimeError(f"immutable evidence collision: {path}")


def _relative_ref(root: Path, path: Path) -> str:
    return str(path.relative_to(root)).replace(os.sep, "/")


@dataclass(frozen=True)
class CandidateEvidenceCollectionResult:
    schema: str
    status: str
    group_sha256: str
    row_refs: tuple[str, ...]
    row_sha256: tuple[str, ...]
    collected_count: int
    eligible_count: int
    skipped_reason: str = ""
    manifest_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "status": self.status,
            "group_sha256": self.group_sha256,
            "row_refs": list(self.row_refs),
            "row_sha256": list(self.row_sha256),
            "collected_count": self.collected_count,
            "eligible_count": self.eligible_count,
            "skipped_reason": self.skipped_reason,
            "manifest_ref": self.manifest_ref,
        }


def _collection_root(repo_root: Path) -> Path:
    override = os.getenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (repo_root / DEFAULT_RELATIVE_ROOT).resolve()


def collect_candidate_group(
    *,
    repo_root: str | Path,
    task_id: str,
    attempt_id: str,
    collector_source: str,
    source_revision: str = "",
    contract_identity: Any,
    verifier_identity: Any,
    candidates: Sequence[Mapping[str, Any]],
    winner_id: str = "",
) -> CandidateEvidenceCollectionResult:
    """Persist one same-task, same-verifier candidate group as immutable sidecar evidence.

    This function is intentionally authority-free. It never selects a candidate,
    runs a verifier, mutates source files, or changes delivery state.
    """
    repo = Path(repo_root).expanduser().resolve()
    root = _collection_root(repo)
    normalized_task_id = str(task_id or "").strip()
    normalized_attempt_id = str(attempt_id or "").strip() or "attempt-unknown"
    normalized_source = str(collector_source or "").strip()
    revision = _resolve_source_revision(repo, source_revision)
    contract_sha256 = _identity_sha256(contract_identity)
    verifier_bundle_sha256 = _identity_sha256(verifier_identity)

    base_group_identity = {
        "task_id": normalized_task_id,
        "attempt_id": normalized_attempt_id,
        "collector_source": normalized_source,
        "source_revision": revision,
        "task_contract_sha256": contract_sha256,
        "verifier_bundle_sha256": verifier_bundle_sha256,
    }
    sampling_sha256 = _sha256_json(base_group_identity)

    if not _env_enabled():
        return CandidateEvidenceCollectionResult(
            schema=COLLECTION_RESULT_SCHEMA,
            status="SKIPPED",
            group_sha256=sampling_sha256,
            row_refs=(),
            row_sha256=(),
            collected_count=0,
            eligible_count=0,
            skipped_reason="disabled",
        )

    rate = _env_rate_percent()
    bucket = int(sampling_sha256[:8], 16) % 100
    if bucket >= rate:
        return CandidateEvidenceCollectionResult(
            schema=COLLECTION_RESULT_SCHEMA,
            status="SKIPPED",
            group_sha256=sampling_sha256,
            row_refs=(),
            row_sha256=(),
            collected_count=0,
            eligible_count=0,
            skipped_reason="deterministic_sampling",
        )

    prepared: list[dict[str, Any]] = []
    seen_candidate_ids: set[str] = set()

    for index, candidate in enumerate(candidates):
        candidate_id = str(candidate.get("candidate_id") or f"candidate-{index + 1}").strip()
        if candidate_id in seen_candidate_ids:
            raise ValueError(f"duplicate candidate_id: {candidate_id}")
        seen_candidate_ids.add(candidate_id)
        payload = str(candidate.get("candidate_payload") or "")
        computed_payload_sha = _sha256_bytes(payload.encode("utf-8")) if payload else ""
        asserted_payload_raw = str(candidate.get("candidate_payload_sha256") or "").strip()
        asserted_payload_sha = _normalized_sha256(asserted_payload_raw)
        if asserted_payload_raw and not asserted_payload_sha:
            raise ValueError(f"invalid candidate payload hash: {candidate_id}")
        if (
            asserted_payload_sha
            and computed_payload_sha
            and asserted_payload_sha != computed_payload_sha
        ):
            raise ValueError(f"candidate payload hash mismatch: {candidate_id}")
        payload_sha256 = computed_payload_sha or asserted_payload_sha
        state_hash_raw = str(candidate.get("candidate_state_hash") or "").strip()
        state_hash = _normalized_sha256(state_hash_raw)
        if state_hash_raw and not state_hash:
            raise ValueError(f"invalid candidate state hash: {candidate_id}")

        candidate_verifier_bundle_raw = str(candidate.get("verifier_bundle_sha256") or "").strip()
        if candidate_verifier_bundle_raw:
            candidate_verifier_bundle = _normalized_sha256(candidate_verifier_bundle_raw)
            if not candidate_verifier_bundle:
                raise ValueError(f"invalid candidate verifier bundle hash: {candidate_id}")
            if candidate_verifier_bundle != verifier_bundle_sha256:
                raise ValueError(f"candidate verifier bundle mismatch: {candidate_id}")

        verifier_evidence = candidate.get("verifier_evidence")
        verifier_evidence_sha256 = ""
        verifier_evidence_body: dict[str, Any] = {}
        evidence_bytes = b""
        if isinstance(verifier_evidence, Mapping) and verifier_evidence:
            verifier_evidence_body = dict(verifier_evidence)
            verifier_evidence_sha256 = _sha256_json(verifier_evidence_body)
            evidence_bytes = (
                json.dumps(
                    verifier_evidence_body,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")

        verifier_status = _normalize_verifier_status(candidate.get("verifier_status"))
        label_quality = str(candidate.get("label_quality") or "UNSPECIFIED").strip().upper()
        prepared.append({
            "candidate_id": candidate_id,
            "candidate_model": str(
                candidate.get("candidate_model") or candidate.get("model") or ""
            ),
            "candidate_source": str(candidate.get("candidate_source") or normalized_source),
            "candidate_state_hash": state_hash,
            "candidate_payload": payload,
            "candidate_payload_sha256": payload_sha256,
            "verifier_status": verifier_status,
            "label_quality": label_quality,
            "verifier_evidence": verifier_evidence_body,
            "verifier_evidence_sha256": verifier_evidence_sha256,
            "verifier_evidence_bytes": evidence_bytes,
            "failure_reason_codes": sorted({
                str(value) for value in (candidate.get("failure_reason_codes") or []) if str(value)
            }),
            "selected": bool(candidate.get("selected", False)),
        })

    candidate_set_identity = [
        {
            "candidate_id": item["candidate_id"],
            "candidate_model": item["candidate_model"],
            "candidate_source": item["candidate_source"],
            "candidate_state_hash": item["candidate_state_hash"],
            "candidate_payload_sha256": item["candidate_payload_sha256"],
        }
        for item in sorted(prepared, key=lambda value: value["candidate_id"])
    ]
    candidate_set_sha256 = _sha256_json(candidate_set_identity)
    group_identity = {
        **base_group_identity,
        "candidate_set_sha256": candidate_set_sha256,
    }
    group_sha256 = _sha256_json(group_identity)

    row_refs: list[str] = []
    row_hashes: list[str] = []
    eligible_count = 0
    planned_writes: dict[Path, bytes] = {}

    def _plan_write(path: Path, payload: bytes) -> None:
        existing = planned_writes.get(path)
        if existing is not None and existing != payload:
            raise RuntimeError(f"conflicting planned evidence object: {path}")
        planned_writes[path] = payload

    for item in prepared:
        payload = item["candidate_payload"]
        payload_sha256 = item["candidate_payload_sha256"]
        payload_ref = ""
        if payload:
            blob_path = root / "blobs" / payload_sha256[:2] / f"{payload_sha256}.txt"
            _plan_write(blob_path, payload.encode("utf-8"))
            payload_ref = _relative_ref(root, blob_path)

        verifier_evidence_ref = ""
        verifier_evidence_sha256 = item["verifier_evidence_sha256"]
        if verifier_evidence_sha256:
            evidence_path = (
                root
                / "verifier"
                / verifier_evidence_sha256[:2]
                / f"{verifier_evidence_sha256}.json"
            )
            _plan_write(evidence_path, item["verifier_evidence_bytes"])
            verifier_evidence_ref = _relative_ref(root, evidence_path)

        binding_complete = bool(
            normalized_task_id
            and revision
            and contract_sha256
            and verifier_bundle_sha256
            and (payload_sha256 or item["candidate_state_hash"])
        )
        label_quality = item["label_quality"]
        verifier_evidence_present = bool(verifier_evidence_ref)
        if label_quality == "ISOLATED_VERIFIER":
            evidence_status = _normalize_verifier_status(
                item["verifier_evidence"].get("verifier_status")
            )
            strong_verifier_evidence = bool(
                verifier_evidence_present
                and item["verifier_evidence"].get("verifier_invoked") is True
                and evidence_status == item["verifier_status"]
            )
        elif label_quality == "MECHANICAL_GATE":
            gate_results = item["verifier_evidence"].get("gate_results")
            gates_well_formed = bool(
                isinstance(gate_results, list)
                and gate_results
                and all(
                    isinstance(gate, Mapping)
                    and bool(_normalized_sha256(str(gate.get("cmd_sha256") or "")))
                    and isinstance(gate.get("passed"), bool)
                    for gate in gate_results
                )
            )
            aggregate_gate_status = (
                "PASS"
                if gates_well_formed and all(bool(gate["passed"]) for gate in gate_results)
                else "FAIL"
                if gates_well_formed
                else "UNKNOWN"
            )
            strong_verifier_evidence = bool(
                verifier_evidence_present
                and gates_well_formed
                and aggregate_gate_status == item["verifier_status"]
            )
        else:
            strong_verifier_evidence = False
        dataset_eligible = (
            binding_complete
            and item["verifier_status"] in {"PASS", "FAIL"}
            and bool(payload_ref)
            and label_quality in {"ISOLATED_VERIFIER", "MECHANICAL_GATE"}
            and strong_verifier_evidence
        )
        if dataset_eligible:
            eligible_count += 1

        row_body = {
            "schema": EVIDENCE_SCHEMA,
            "task_id": normalized_task_id,
            "attempt_id": normalized_attempt_id,
            "collector_source": normalized_source,
            "source_revision": revision,
            "task_contract_sha256": contract_sha256,
            "verifier_bundle_sha256": verifier_bundle_sha256,
            "candidate_set_sha256": candidate_set_sha256,
            "comparison_group_sha256": group_sha256,
            "candidate_id": item["candidate_id"],
            "candidate_model": item["candidate_model"],
            "candidate_source": item["candidate_source"],
            "candidate_state_hash": item["candidate_state_hash"],
            "candidate_payload_sha256": payload_sha256,
            "candidate_payload_ref": payload_ref,
            "verifier_status": item["verifier_status"],
            "label_quality": label_quality,
            "verifier_evidence_sha256": verifier_evidence_sha256,
            "verifier_evidence_ref": verifier_evidence_ref,
            "failure_reason_codes": item["failure_reason_codes"],
            "selected": item["selected"],
            "winner_id": str(winner_id or ""),
            "binding_complete": binding_complete,
            "dataset_eligible": dataset_eligible,
        }
        row_sha256 = _sha256_json(row_body)
        row = dict(row_body)
        row["record_sha256"] = row_sha256
        row_path = root / "groups" / group_sha256 / f"{row_sha256}.json"
        row_bytes = (json.dumps(row, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        )
        _plan_write(row_path, row_bytes)
        row_refs.append(_relative_ref(root, row_path))
        row_hashes.append(row_sha256)

    manifest_body = {
        "schema": GROUP_MANIFEST_SCHEMA,
        "comparison_group_sha256": group_sha256,
        "candidate_set_sha256": candidate_set_sha256,
        "candidate_count": len(prepared),
        "row_sha256": sorted(row_hashes),
        "eligible_count": eligible_count,
    }
    manifest = dict(manifest_body)
    manifest["manifest_sha256"] = _sha256_json(manifest_body)
    manifest_path = root / "groups" / group_sha256 / ".complete"
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")

    # Validate the full group before writing any new object.  The completion
    # marker is preflighted with the rows, but written last.  A crash before
    # that final create can leave orphaned content-addressed objects, never a
    # group that appears complete.
    for path, payload in planned_writes.items():
        _preflight_create_only(path, payload)
    _preflight_create_only(manifest_path, manifest_bytes)
    for path, payload in planned_writes.items():
        _write_create_only(path, payload)
    _write_create_only(manifest_path, manifest_bytes)

    return CandidateEvidenceCollectionResult(
        schema=COLLECTION_RESULT_SCHEMA,
        status="COLLECTED",
        group_sha256=group_sha256,
        row_refs=tuple(row_refs),
        row_sha256=tuple(row_hashes),
        collected_count=len(row_refs),
        eligible_count=eligible_count,
        manifest_ref=_relative_ref(root, manifest_path),
    )
