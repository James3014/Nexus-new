"""Deterministic packet-mode review contracts for direct RDC -> Agy review.

This module owns review subject/evidence identity and receipt construction only.
It does not own reviewer routing, acceptance authority, merge, release, or production.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REVIEW_PACKET_SCHEMA = "nexus.agy_review_packet.v1"
REVIEW_RECEIPT_SCHEMA = "nexus.agy_review_receipt.v1"
REVIEW_PROFILE_VERSION = "nexus.rdc_agy_packet_review.v1"
REVIEW_CLAIM_CEILING = "REVIEW_EVIDENCE_ONLY_NOT_ACCEPTANCE_AUTHORITY"
TERMINAL_VERDICTS = frozenset({
    "ACCEPT",
    "REPAIR_REQUIRED",
    "OWNER_DECISION_REQUIRED",
    "EVIDENCE_INSUFFICIENT",
})
_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_EVIDENCE_FILE_BYTES = 2 * 1024 * 1024
MAX_PACKET_INPUT_BYTES = 8 * 1024 * 1024


class AgyReviewError(RuntimeError):
    """Review subject, packet, verdict, or receipt contract failure."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical(value).encode("utf-8"))


def _git_bytes(root: Path, *args: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).decode("utf-8", errors="replace").strip()
        raise AgyReviewError(f"GIT_COMMAND_FAILED:{args[0]}:{detail[:500]}")
    return proc.stdout


def _git_text(root: Path, *args: str) -> str:
    try:
        return _git_bytes(root, *args).decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise AgyReviewError(f"GIT_OUTPUT_NOT_UTF8:{args[0]}") from exc


def normalize_repository(value: str) -> str:
    text = str(value or "").strip().rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    for pattern in (
        r"^https://github\.com/([^/]+/[^/]+)$",
        r"^git@github\.com:([^/]+/[^/]+)$",
        r"^ssh://git@github\.com/([^/]+/[^/]+)$",
        r"^([^/]+/[^/]+)$",
    ):
        match = re.match(pattern, text)
        if match:
            return match.group(1).lower()
    raise AgyReviewError("REPOSITORY_IDENTITY_INVALID")


def _decode_nul_list(raw: bytes, *, label: str) -> list[str]:
    values: list[str] = []
    for part in raw.split(b"\0"):
        if not part:
            continue
        try:
            text = part.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AgyReviewError(f"{label}_PATH_NOT_UTF8") from exc
        if "\x00" in text:
            raise AgyReviewError(f"{label}_PATH_INVALID")
        values.append(text)
    return values


def _read_text_file(path: Path, *, label: str) -> tuple[str, str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AgyReviewError(f"{label}_READ_FAILED:{path.name}") from exc
    if len(raw) > MAX_EVIDENCE_FILE_BYTES:
        raise AgyReviewError(f"{label}_TOO_LARGE:{path.name}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AgyReviewError(f"{label}_NOT_UTF8:{path.name}") from exc
    return text, _sha256_bytes(raw)


def _safe_untracked(root: Path, relative: str) -> dict[str, str]:
    source = root / relative
    if source.is_symlink():
        raise AgyReviewError(f"UNTRACKED_FILE_UNSUPPORTED:{relative}")
    target = source.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise AgyReviewError(f"UNTRACKED_PATH_ESCAPE:{relative}") from exc
    if not target.is_file():
        raise AgyReviewError(f"UNTRACKED_FILE_UNSUPPORTED:{relative}")
    text, digest = _read_text_file(target, label="UNTRACKED_FILE")
    return {"path": relative, "sha256": digest, "content": text}


@dataclass(frozen=True)
class ReviewSubject:
    repository: str
    repo_root: str
    repo_root_sha256: str
    base_revision: str
    current_head: str
    changed_paths: tuple[str, ...]
    tracked_diff: str
    tracked_diff_sha256: str
    untracked_files: tuple[dict[str, str], ...]
    candidate_digest: str

    def identity_payload(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "base_revision": self.base_revision,
            "current_head": self.current_head,
            "changed_paths": list(self.changed_paths),
            "tracked_diff_sha256": self.tracked_diff_sha256,
            "untracked_files": [
                {"path": item["path"], "sha256": item["sha256"]} for item in self.untracked_files
            ],
        }


def collect_review_subject(
    repo_path: str | os.PathLike[str],
    *,
    expected_repository: str,
    base_revision: str,
) -> ReviewSubject:
    requested = Path(repo_path).expanduser().resolve()
    root_text = _git_text(requested, "rev-parse", "--show-toplevel")
    root = Path(root_text).resolve()
    remote = _git_text(root, "remote", "get-url", "origin")
    repository = normalize_repository(remote)
    expected = normalize_repository(expected_repository)
    if repository != expected:
        raise AgyReviewError(f"REPOSITORY_IDENTITY_MISMATCH:{repository}:{expected}")

    base = str(base_revision or "").strip().lower()
    if not _SHA1_RE.fullmatch(base):
        raise AgyReviewError("BASE_REVISION_INVALID")
    resolved_base = _git_text(root, "rev-parse", f"{base}^{{commit}}").lower()
    if resolved_base != base:
        raise AgyReviewError("BASE_REVISION_NOT_EXACT")
    current_head = _git_text(root, "rev-parse", "HEAD").lower()
    ancestor = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", base, current_head],
        capture_output=True,
        check=False,
    )
    if ancestor.returncode != 0:
        raise AgyReviewError("BASE_REVISION_NOT_ANCESTOR")

    diff_raw = _git_bytes(root, "diff", "--binary", "--no-ext-diff", base)
    try:
        tracked_diff = diff_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AgyReviewError("TRACKED_DIFF_NOT_UTF8") from exc
    tracked_paths = _decode_nul_list(
        _git_bytes(root, "diff", "--name-only", "-z", base),
        label="TRACKED",
    )
    untracked_paths = sorted(
        set(
            _decode_nul_list(
                _git_bytes(root, "ls-files", "--others", "--exclude-standard", "-z"),
                label="UNTRACKED",
            )
        )
    )
    untracked = tuple(_safe_untracked(root, path) for path in untracked_paths)
    changed_paths = tuple(sorted(set(tracked_paths) | set(untracked_paths)))
    if not changed_paths:
        raise AgyReviewError("EMPTY_REVIEW_SUBJECT")

    tracked_diff_sha256 = _sha256_bytes(diff_raw)
    candidate_material = {
        "repository": repository,
        "base_revision": base,
        "current_head": current_head,
        "changed_paths": list(changed_paths),
        "tracked_diff_sha256": tracked_diff_sha256,
        "untracked_files": [{"path": item["path"], "sha256": item["sha256"]} for item in untracked],
    }
    return ReviewSubject(
        repository=repository,
        repo_root=str(root),
        repo_root_sha256=_sha256_bytes(str(root).encode("utf-8")),
        base_revision=base,
        current_head=current_head,
        changed_paths=changed_paths,
        tracked_diff=tracked_diff,
        tracked_diff_sha256=tracked_diff_sha256,
        untracked_files=untracked,
        candidate_digest=sha256_json(candidate_material),
    )


def _document(path: str | os.PathLike[str], *, kind: str) -> dict[str, str]:
    target = Path(path).expanduser().resolve()
    text, digest = _read_text_file(target, label=kind.upper())
    return {"name": target.name, "sha256": digest, "content": text}


def _documents(paths: Iterable[str | os.PathLike[str]], *, kind: str) -> list[dict[str, str]]:
    docs = [_document(path, kind=kind) for path in paths]
    docs.sort(key=lambda item: (item["sha256"], item["name"]))
    return docs


def _effect_material(
    *,
    subject: ReviewSubject,
    acceptance_contract_sha256: str,
    reviewer_role: str,
    evidence_inputs_sha256: str,
) -> dict[str, str]:
    return {
        "repository": subject.repository,
        "base_revision": subject.base_revision,
        "candidate_digest": subject.candidate_digest,
        "acceptance_contract_sha256": acceptance_contract_sha256,
        "reviewer_role": reviewer_role,
        "evidence_inputs_sha256": evidence_inputs_sha256,
    }


def operation_id_for_effect(review_effect_id: str) -> str:
    if not _SHA256_RE.fullmatch(str(review_effect_id or "")):
        raise AgyReviewError("REVIEW_EFFECT_ID_INVALID")
    return "agyop_" + review_effect_id[:32]


def build_review_packet(
    subject: ReviewSubject,
    *,
    acceptance_contract_file: str | os.PathLike[str],
    reviewer_role: str,
    verification_receipt_files: Sequence[str | os.PathLike[str]] = (),
    authority_excerpt_files: Sequence[str | os.PathLike[str]] = (),
) -> dict[str, Any]:
    role = str(reviewer_role or "").strip()
    if not role or len(role) > 120:
        raise AgyReviewError("REVIEWER_ROLE_INVALID")

    contract = _document(acceptance_contract_file, kind="acceptance_contract")
    verification = _documents(verification_receipt_files, kind="verification_receipt")
    authority = _documents(authority_excerpt_files, kind="authority_excerpt")
    evidence_bytes = sum(
        len(item["content"].encode("utf-8")) for item in [contract, *verification, *authority]
    )
    candidate_bytes = len(subject.tracked_diff.encode("utf-8")) + sum(
        len(item["content"].encode("utf-8")) for item in subject.untracked_files
    )
    if candidate_bytes + evidence_bytes > MAX_PACKET_INPUT_BYTES:
        raise AgyReviewError("REVIEW_PACKET_INPUT_TOO_LARGE")

    evidence_inputs = {
        "verification_receipts": [
            {"name": item["name"], "sha256": item["sha256"]} for item in verification
        ],
        "authority_excerpts": [
            {"name": item["name"], "sha256": item["sha256"]} for item in authority
        ],
    }
    evidence_inputs_sha256 = sha256_json(evidence_inputs)
    review_effect_id = sha256_json(
        _effect_material(
            subject=subject,
            acceptance_contract_sha256=contract["sha256"],
            reviewer_role=role,
            evidence_inputs_sha256=evidence_inputs_sha256,
        )
    )

    packet: dict[str, Any] = {
        "schema": REVIEW_PACKET_SCHEMA,
        "claim_ceiling": REVIEW_CLAIM_CEILING,
        "review_profile_version": REVIEW_PROFILE_VERSION,
        "review_effect_id": review_effect_id,
        "reviewer_role": role,
        "repository": subject.repository,
        "repo_root_sha256": subject.repo_root_sha256,
        "base_revision": subject.base_revision,
        "current_head": subject.current_head,
        "candidate_digest": subject.candidate_digest,
        "changed_paths": list(subject.changed_paths),
        "tracked_diff_sha256": subject.tracked_diff_sha256,
        "tracked_diff": subject.tracked_diff,
        "untracked_files": list(subject.untracked_files),
        "acceptance_contract": contract,
        "acceptance_contract_sha256": contract["sha256"],
        "verification_receipts": verification,
        "authority_excerpts": authority,
        "evidence_inputs_sha256": evidence_inputs_sha256,
    }
    packet["packet_sha256"] = sha256_json(packet)
    verify_review_packet(packet)
    return packet


def verify_review_packet(packet: Mapping[str, Any]) -> None:
    if packet.get("schema") != REVIEW_PACKET_SCHEMA:
        raise AgyReviewError("REVIEW_PACKET_SCHEMA_INVALID")
    packet_hash = packet.get("packet_sha256")
    if not isinstance(packet_hash, str) or not _SHA256_RE.fullmatch(packet_hash):
        raise AgyReviewError("REVIEW_PACKET_HASH_INVALID")
    body = dict(packet)
    body.pop("packet_sha256", None)
    if sha256_json(body) != packet_hash:
        raise AgyReviewError("REVIEW_PACKET_HASH_MISMATCH")

    tracked_diff = packet.get("tracked_diff")
    if not isinstance(tracked_diff, str):
        raise AgyReviewError("REVIEW_PACKET_TRACKED_DIFF_INVALID")
    if _sha256_bytes(tracked_diff.encode("utf-8")) != packet.get("tracked_diff_sha256"):
        raise AgyReviewError("REVIEW_PACKET_TRACKED_DIFF_HASH_MISMATCH")

    untracked_rows = packet.get("untracked_files")
    if not isinstance(untracked_rows, list):
        raise AgyReviewError("REVIEW_PACKET_UNTRACKED_INVALID")
    untracked_identity = []
    for row in untracked_rows:
        if not isinstance(row, Mapping):
            raise AgyReviewError("REVIEW_PACKET_UNTRACKED_INVALID")
        content, path, digest = row.get("content"), row.get("path"), row.get("sha256")
        if not isinstance(content, str) or not isinstance(path, str):
            raise AgyReviewError("REVIEW_PACKET_UNTRACKED_INVALID")
        if _sha256_bytes(content.encode("utf-8")) != digest:
            raise AgyReviewError("REVIEW_PACKET_UNTRACKED_HASH_MISMATCH")
        untracked_identity.append({"path": path, "sha256": digest})

    contract = packet.get("acceptance_contract")
    if not isinstance(contract, Mapping) or not isinstance(contract.get("content"), str):
        raise AgyReviewError("REVIEW_PACKET_CONTRACT_INVALID")
    contract_sha = _sha256_bytes(contract["content"].encode("utf-8"))
    if contract_sha != contract.get("sha256") or contract_sha != packet.get(
        "acceptance_contract_sha256"
    ):
        raise AgyReviewError("REVIEW_PACKET_CONTRACT_HASH_MISMATCH")

    for key in ("verification_receipts", "authority_excerpts"):
        rows = packet.get(key)
        if not isinstance(rows, list):
            raise AgyReviewError("REVIEW_PACKET_EVIDENCE_INVALID")
        for row in rows:
            if not isinstance(row, Mapping) or not isinstance(row.get("content"), str):
                raise AgyReviewError("REVIEW_PACKET_EVIDENCE_INVALID")
            if _sha256_bytes(row["content"].encode("utf-8")) != row.get("sha256"):
                raise AgyReviewError("REVIEW_PACKET_EVIDENCE_HASH_MISMATCH")

    evidence_inputs = {
        "verification_receipts": [
            {"name": row["name"], "sha256": row["sha256"]}
            for row in packet["verification_receipts"]
        ],
        "authority_excerpts": [
            {"name": row["name"], "sha256": row["sha256"]} for row in packet["authority_excerpts"]
        ],
    }
    if sha256_json(evidence_inputs) != packet.get("evidence_inputs_sha256"):
        raise AgyReviewError("REVIEW_PACKET_EVIDENCE_IDENTITY_MISMATCH")

    candidate_material = {
        "repository": packet.get("repository"),
        "base_revision": packet.get("base_revision"),
        "current_head": packet.get("current_head"),
        "changed_paths": packet.get("changed_paths"),
        "tracked_diff_sha256": packet.get("tracked_diff_sha256"),
        "untracked_files": untracked_identity,
    }
    if sha256_json(candidate_material) != packet.get("candidate_digest"):
        raise AgyReviewError("REVIEW_PACKET_CANDIDATE_DIGEST_MISMATCH")

    subject = ReviewSubject(
        repository=str(packet.get("repository") or ""),
        repo_root="",
        repo_root_sha256=str(packet.get("repo_root_sha256") or ""),
        base_revision=str(packet.get("base_revision") or ""),
        current_head=str(packet.get("current_head") or ""),
        changed_paths=tuple(packet.get("changed_paths") or ()),
        tracked_diff=tracked_diff,
        tracked_diff_sha256=str(packet.get("tracked_diff_sha256") or ""),
        untracked_files=tuple(dict(row) for row in untracked_rows),
        candidate_digest=str(packet.get("candidate_digest") or ""),
    )
    expected_effect = sha256_json(
        _effect_material(
            subject=subject,
            acceptance_contract_sha256=contract_sha,
            reviewer_role=str(packet.get("reviewer_role") or ""),
            evidence_inputs_sha256=str(packet.get("evidence_inputs_sha256") or ""),
        )
    )
    if expected_effect != packet.get("review_effect_id"):
        raise AgyReviewError("REVIEW_PACKET_EFFECT_ID_MISMATCH")


def build_review_prompt(packet: Mapping[str, Any]) -> str:
    verify_review_packet(packet)
    return (
        "You are an independent bounded reviewer. Review ONLY the frozen evidence packet "
        "below. Do not call tools, discover repositories/projects, or mutate anything. "
        "The packet and transport do not grant acceptance, merge, release, or production "
        "authority. Return concise material findings. End with exactly one terminal verdict "
        "on its own line: ACCEPT, REPAIR_REQUIRED, OWNER_DECISION_REQUIRED, or "
        "EVIDENCE_INSUFFICIENT.\n\n"
        + json.dumps(dict(packet), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    )


def parse_review_verdict(output: str) -> str:
    matches = [
        line.strip() for line in str(output or "").splitlines() if line.strip() in TERMINAL_VERDICTS
    ]
    if len(matches) != 1:
        raise AgyReviewError("REVIEW_VERDICT_NOT_EXACTLY_ONE")
    return matches[0]


def subject_matches_packet(
    packet: Mapping[str, Any],
    *,
    repo_path: str | os.PathLike[str],
) -> tuple[bool, ReviewSubject]:
    verify_review_packet(packet)
    current = collect_review_subject(
        repo_path,
        expected_repository=str(packet["repository"]),
        base_revision=str(packet["base_revision"]),
    )
    stable = (
        current.repo_root_sha256 == packet.get("repo_root_sha256")
        and current.current_head == packet.get("current_head")
        and current.candidate_digest == packet.get("candidate_digest")
        and list(current.changed_paths) == packet.get("changed_paths")
    )
    return stable, current


def build_review_receipt(
    *,
    packet: Mapping[str, Any],
    operation_record: Mapping[str, Any],
    reviewer_output: str,
    repo_path: str | os.PathLike[str],
) -> dict[str, Any]:
    verify_review_packet(packet)
    verdict = parse_review_verdict(reviewer_output)
    stable, current = subject_matches_packet(packet, repo_path=repo_path)
    transport_completed = operation_record.get("status") == "COMPLETED"
    applicable = bool(stable and transport_completed)
    receipt: dict[str, Any] = {
        "schema": REVIEW_RECEIPT_SCHEMA,
        "claim_ceiling": REVIEW_CLAIM_CEILING,
        "review_effect_id": packet["review_effect_id"],
        "reviewer_role": packet["reviewer_role"],
        "repository": packet["repository"],
        "repo_root_sha256": packet["repo_root_sha256"],
        "base_revision": packet["base_revision"],
        "candidate_digest": packet["candidate_digest"],
        "candidate_head": packet["current_head"],
        "acceptance_contract_sha256": packet["acceptance_contract_sha256"],
        "evidence_inputs_sha256": packet["evidence_inputs_sha256"],
        "packet_sha256": packet["packet_sha256"],
        "operation_id": operation_record.get("operation_id"),
        "attempt_id": operation_record.get("attempt_id"),
        "provider": operation_record.get("observed_provider") or operation_record.get("provider"),
        "model": operation_record.get("observed_model") or operation_record.get("model"),
        "provider_session_id": operation_record.get("provider_session_id"),
        "review_launch_catalog_version": operation_record.get("review_launch_catalog_version"),
        "review_launch_profile_id": operation_record.get("review_launch_profile_id"),
        "review_launch_profile_sha256": operation_record.get("review_launch_profile_sha256"),
        "review_launch_mode": operation_record.get("review_launch_mode"),
        "review_launch_requested_effort": operation_record.get("review_launch_requested_effort"),
        "verdict": verdict,
        "subject_stable": stable,
        "review_applicable": applicable,
        "current_candidate_digest": current.candidate_digest,
        "transport_status": operation_record.get("status"),
        "completed_at": operation_record.get("finished_at"),
    }
    receipt["receipt_sha256"] = sha256_json(receipt)
    return receipt


def verify_review_receipt(receipt: Mapping[str, Any], packet: Mapping[str, Any]) -> None:
    if receipt.get("schema") != REVIEW_RECEIPT_SCHEMA:
        raise AgyReviewError("REVIEW_RECEIPT_SCHEMA_INVALID")
    digest = receipt.get("receipt_sha256")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise AgyReviewError("REVIEW_RECEIPT_HASH_INVALID")
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    if sha256_json(body) != digest:
        raise AgyReviewError("REVIEW_RECEIPT_HASH_MISMATCH")
    for key in (
        "review_effect_id",
        "repository",
        "repo_root_sha256",
        "base_revision",
        "candidate_digest",
        "acceptance_contract_sha256",
        "packet_sha256",
    ):
        if receipt.get(key) != packet.get(key):
            raise AgyReviewError(f"REVIEW_RECEIPT_BINDING_MISMATCH:{key}")
    if receipt.get("verdict") not in TERMINAL_VERDICTS:
        raise AgyReviewError("REVIEW_RECEIPT_VERDICT_INVALID")


def atomic_private_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def atomic_private_json(path: Path, value: Mapping[str, Any]) -> None:
    atomic_private_text(
        path,
        json.dumps(dict(value), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def load_review_packet(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgyReviewError("REVIEW_PACKET_READ_FAILED") from exc
    if not isinstance(value, dict):
        raise AgyReviewError("REVIEW_PACKET_INVALID")
    verify_review_packet(value)
    return value
