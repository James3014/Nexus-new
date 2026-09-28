#!/usr/bin/env python3
"""Validate Candidate Acceptance v4 plus the transport-neutral v5 successor."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

_RUN_AS_MAIN = __name__ == "__main__"
_ORIGINAL_NAME = __name__
_SOURCE = Path(__file__).with_name("archive") / "validate_acceptance_result_v4_current.source.txt"
_CODE = compile(_SOURCE.read_text(encoding="utf-8"), str(_SOURCE), "exec")

# Load the frozen/current v4 implementation without triggering its CLI entry point.
__name__ = "_nexus_candidate_acceptance_v4_core"
exec(_CODE, globals(), globals())
__name__ = _ORIGINAL_NAME

_v4_namespace = globals()
_v4_validate = _v4_namespace["validate"]
_v4_validate_physical = _v4_namespace["validate_physical"]
_V4_VALIDATION_SCHEMA = _v4_namespace["VALIDATION_SCHEMA"]

canonical_sha256 = _v4_namespace["canonical_sha256"]
record = _v4_namespace["record"]
nonempty = _v4_namespace["nonempty"]
file_sha256 = _v4_namespace["file_sha256"]
read_json = _v4_namespace["read_json"]
parse_args = _v4_namespace["parse_args"]
_hex_or_ref = _v4_namespace["_hex_or_ref"]
_git = _v4_namespace["_git"]
_physical_manifest = _v4_namespace["_physical_manifest"]
_validate_manifest = _v4_namespace["_validate_manifest"]
core_manifest_hash = _v4_namespace["core_manifest_hash"]
HEX64 = _v4_namespace["HEX64"]
GIT_OID = _v4_namespace["GIT_OID"]
GIT_PATH = _v4_namespace["GIT_PATH"]
CORE_HASH = _v4_namespace["CORE_HASH"]
COMMAND_RESULTS = _v4_namespace["COMMAND_RESULTS"]
DuplicateKeyError = _v4_namespace["DuplicateKeyError"]

V5_SCHEMA = "nexus.candidate_acceptance.v5"
V5_VALIDATION_SCHEMA = "nexus.candidate_acceptance.validation.v5"
V5_DIRECT_KIND = "TRANSPORT_NEUTRAL_DIRECT_EVIDENCE"
V5_REVIEW_KIND = "INDEPENDENT_REVIEW_EVIDENCE"
V5_DIRECT_SCHEMA = "nexus.transport_neutral_direct_execution.v1"
V5_REVIEW_SCHEMA = "nexus.independent_candidate_review_evidence.v1"


def _v5_date(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _v5_task_card_from_git(
    root: str, base_commit: str, path: str
) -> tuple[str, str, list[str], str]:
    if not GIT_PATH.fullmatch(path):
        raise OSError("Task Card path is not repository-relative")
    raw = subprocess.run(
        ["git", "-C", root, "show", f"{base_commit}:{path}"],
        capture_output=True,
        timeout=10,
    )
    if raw.returncode != 0:
        raise OSError("Task Card is not present in the authorized base")
    card_bytes = raw.stdout
    text = card_bytes.decode("utf-8")
    card_sha = hashlib.sha256(card_bytes).hexdigest()
    task_match = re.search(r"(?m)^task_id:\s*\`([^\`]+)\`\s*$", text)
    if task_match is None:
        raise OSError("Task Card task_id is missing")
    section = re.search(
        r"(?ms)^## Allowed files\s*\n(?P<body>.*?)(?=^## |\Z)", text
    )
    if section is None:
        raise OSError("Task Card Allowed files section is missing")
    allowed = re.findall(r"(?m)^-\s*\`([^\`]+)\`\s*$", section.group("body"))
    if not allowed or len(set(allowed)) != len(allowed):
        raise OSError("Task Card allowed files are missing or duplicated")
    if not all(GIT_PATH.fullmatch(path) for path in allowed):
        raise OSError("Task Card contains invalid allowed path")
    required_controls = {
        "artifact_authority": "current",
        "status": "ACTIVE",
        "commit_required": "true",
        "candidate_required": "true",
        "worker_may_approve": "false",
        "worker_may_integrate": "false",
        "worker_may_push": "false",
        "AUTO_CHAIN": "false",
    }
    for key, expected in required_controls.items():
        control = re.search(
            rf"(?m)^{re.escape(key)}:\s*\`?([^\s\`]+)\`?\s*$",
            text,
        )
        if control is None or control.group(1) != expected:
            raise OSError(f"Task Card {key} must be {expected}")
    deletion = re.search(r"(?m)^deletion_policy:\s*\`?(ALLOW|FORBID)\`?\s*$", text)
    deletion_policy = deletion.group(1) if deletion else "FORBID"
    return card_sha, task_match.group(1), allowed, deletion_policy


def _v5_review_record_hash(evidence: dict[str, object]) -> str:
    payload = {
        "schema": V5_REVIEW_SCHEMA,
        "review_id": evidence.get("review_id"),
        "reviewer_id": evidence.get("reviewer_id"),
        "reviewer_attempt_id": evidence.get("reviewer_attempt_id"),
        "independence_class": evidence.get("independence_class"),
        "repository": evidence.get("repository"),
        "commands": evidence.get("commands"),
        "claim": evidence.get("claim"),
    }
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _v5_fetch_github_comment(repository_full_name: str, comment_id: int) -> dict[str, object]:
    proc = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repository_full_name}/issues/comments/{comment_id}",
        ],
        text=True,
        capture_output=True,
        timeout=20,
    )
    if proc.returncode != 0:
        raise OSError(proc.stderr.strip() or "GitHub review comment lookup failed")
    value = json.loads(proc.stdout)
    if not isinstance(value, dict):
        raise OSError("GitHub review comment response is malformed")
    return value


def _v5_normalize_remote(value: str) -> str:
    text = value.strip()
    scp = re.fullmatch(r"git@([^:]+):(.+)", text)
    if scp:
        host = scp.group(1).lower()
        repo = scp.group(2).strip("/").removesuffix(".git")
        return f"{host}/{repo}"
    parsed = urlparse(text)
    if parsed.scheme and parsed.hostname:
        repo = parsed.path.strip("/").removesuffix(".git")
        return f"{parsed.hostname.lower()}/{repo}"
    return text.rstrip("/").removesuffix(".git")


def _v5_result_projection(data: dict[str, object]) -> dict[str, object]:
    """Project only the shared result envelope into v4 for structural validation."""
    projected = copy.deepcopy(data)
    projected["schema"] = "nexus.candidate_acceptance.v4"
    source = projected.get("source")
    if isinstance(source, dict):
        # This projection exists only to reuse v4 envelope checks. It deliberately
        # removes v5 authority lineage and must never be emitted as evidence.
        source["contract_kind"] = "OWNER_INLINE"
        source["campaign_id"] = None
        source["task_card_path"] = None
        source["task_card_sha256"] = None
        source["executor_evidence_kind"] = "DEVSPACE_DIRECT_EVIDENCE"
        source["verification_evidence_kind"] = "CORE_GENERIC_VERIFICATION_RESPONSE"
    integrity = projected.get("integrity")
    if isinstance(integrity, dict):
        integrity["sha256"] = canonical_sha256(projected)
    return projected


def validate_v5(data: object) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return {
            "schema": V5_VALIDATION_SCHEMA,
            "valid": False,
            "errors": ["$: object required"],
            "warnings": [],
        }

    projected_report = _v4_validate(_v5_result_projection(data))
    errors.extend(projected_report.get("errors", []))
    warnings.extend(projected_report.get("warnings", []))

    if data.get("schema") != V5_SCHEMA:
        errors.append(f"$.schema: expected {V5_SCHEMA}")
    source = data.get("source")
    if not isinstance(source, dict):
        errors.append("$.source: object required")
        source = {}
    if source.get("executor_evidence_kind") != V5_DIRECT_KIND:
        errors.append(
            "$.source.executor_evidence_kind: v5 direct work requires "
            "TRANSPORT_NEUTRAL_DIRECT_EVIDENCE"
        )
    if source.get("verification_evidence_kind") != V5_REVIEW_KIND:
        errors.append(
            "$.source.verification_evidence_kind: v5 direct work requires "
            "INDEPENDENT_REVIEW_EVIDENCE"
        )
    if source.get("contract_kind") != "TRACKED_TASK_CARD":
        errors.append(
            "$.source.contract_kind: v5 governed transport-neutral evidence "
            "requires TRACKED_TASK_CARD"
        )
    if not nonempty(source.get("campaign_id")):
        errors.append("$.source.campaign_id: required for v5 governed work")
    if not nonempty(source.get("task_card_path")):
        errors.append("$.source.task_card_path: required for v5 governed work")
    task_card_sha = source.get("task_card_sha256")
    if not isinstance(task_card_sha, str) or not HEX64.fullmatch(task_card_sha):
        errors.append("$.source.task_card_sha256: lowercase SHA-256 required")
    if source.get("contract_hash") != task_card_sha:
        errors.append(
            "$.source.contract_hash: v5 governed work binds contract_hash to "
            "the immutable Task Card SHA-256"
        )
    for key in ("compiled_packet_sha256", "execution_manifest_sha256"):
        if source.get(key) is not None:
            errors.append(f"$.source.{key}: v5 direct execution forbids synthetic MCP lineage")

    repository = data.get("repository")
    if isinstance(repository, dict):
        if repository.get("candidate_state_hash") is not None:
            errors.append("$.repository.candidate_state_hash: v5 direct branch requires null")
        if repository.get("verified_receipt_hash") is not None:
            errors.append("$.repository.verified_receipt_hash: v5 direct branch requires null")

    integrity = data.get("integrity")
    if not isinstance(integrity, dict) or set(integrity) != {"sha256"}:
        errors.append("$.integrity: exact sha256 object required")
    elif integrity.get("sha256") != canonical_sha256(data):
        errors.append("$.integrity.sha256: canonical v5 integrity mismatch")

    return {
        "schema": V5_VALIDATION_SCHEMA,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def _v5_validate_direct_evidence(
    data: dict[str, object],
    evidence: object,
    errors: list[str],
    warnings: list[str],
) -> None:
    source = data["source"]
    repository = data["repository"]
    if not isinstance(source, dict) or not isinstance(repository, dict):
        errors.append("v5 result source/repository must be objects")
        return
    if not isinstance(evidence, dict) or evidence.get("schema") != V5_DIRECT_SCHEMA:
        record(data, errors, warnings, "transport-neutral executor evidence schema mismatch", "authority")
        return
    top_keys = {
        "schema",
        "evidence_id",
        "created_at",
        "authority",
        "execution",
        "candidate",
        "claim",
        "integrity",
    }
    if set(evidence) != top_keys:
        record(data, errors, warnings, "transport-neutral executor evidence top-level shape mismatch", "authority")
    if not nonempty(evidence.get("evidence_id")):
        record(data, errors, warnings, "transport-neutral evidence_id is required", "subject_identity")
    if not _v5_date(evidence.get("created_at")):
        record(data, errors, warnings, "transport-neutral created_at is invalid", "subject_identity")
    evidence_integrity = evidence.get("integrity")
    if not isinstance(evidence_integrity, dict) or set(evidence_integrity) != {"sha256"}:
        record(data, errors, warnings, "transport-neutral evidence integrity shape mismatch", "subject_identity")
    elif evidence_integrity.get("sha256") != canonical_sha256(evidence):
        record(data, errors, warnings, "transport-neutral evidence integrity mismatch", "subject_identity")

    authority = evidence.get("authority")
    execution = evidence.get("execution")
    candidate = evidence.get("candidate")
    claim = evidence.get("claim")
    if not all(isinstance(item, dict) for item in (authority, execution, candidate, claim)):
        record(data, errors, warnings, "transport-neutral nested evidence groups must be objects", "authority")
        return

    authority_keys = {
        "contract_kind",
        "task_id",
        "attempt_id",
        "task_card_path",
        "task_card_sha256",
        "allowed_paths",
        "deletion_policy",
        "claim_ceiling",
    }
    execution_keys = {
        "executor_id",
        "executor_kind",
        "transport",
        "workspace_root",
        "started_at",
        "completed_at",
        "state",
        "terminal_reason",
    }
    candidate_keys = {
        "repository_origin",
        "source_commit",
        "commit_sha",
        "tree_sha",
        "changed_paths",
        "deleted_paths",
        "change_manifest",
        "diff_hash",
    }
    claim_keys = {
        "status",
        "claim_ceiling",
        "verified",
        "certified",
        "accepted",
        "approved",
        "merged",
        "released",
        "deployed",
        "public_claim_allowed",
    }
    for label, value, keys in (
        ("authority", authority, authority_keys),
        ("execution", execution, execution_keys),
        ("candidate", candidate, candidate_keys),
        ("claim", claim, claim_keys),
    ):
        if set(value) != keys:
            record(data, errors, warnings, f"transport-neutral {label} shape mismatch", "authority")

    if authority.get("contract_kind") != "TRACKED_TASK_CARD":
        record(
            data,
            errors,
            warnings,
            "transport-neutral governed work requires TRACKED_TASK_CARD authority",
            "authority",
        )
    for key in ("task_id", "attempt_id", "task_card_path"):
        if not nonempty(authority.get(key)):
            record(
                data,
                errors,
                warnings,
                f"transport-neutral authority {key} is required",
                "authority",
            )
    if not isinstance(authority.get("task_card_sha256"), str) or not HEX64.fullmatch(
        authority.get("task_card_sha256", "")
    ):
        record(
            data,
            errors,
            warnings,
            "transport-neutral task_card_sha256 is malformed",
            "authority",
        )
    allowed_paths = authority.get("allowed_paths")
    if (
        not isinstance(allowed_paths, list)
        or not allowed_paths
        or len(set(allowed_paths)) != len(allowed_paths)
        or not all(isinstance(path, str) and GIT_PATH.fullmatch(path) for path in allowed_paths)
    ):
        record(data, errors, warnings, "transport-neutral allowed_paths are malformed", "authority")
        allowed_paths = []
    if authority.get("deletion_policy") not in {"ALLOW", "FORBID"}:
        record(data, errors, warnings, "transport-neutral deletion_policy is invalid", "authority")
    if authority.get("claim_ceiling") != "CANDIDATE_READY":
        record(data, errors, warnings, "transport-neutral authority claim ceiling is invalid", "claim_discipline")

    for key in ("executor_id", "executor_kind", "transport", "workspace_root"):
        if not nonempty(execution.get(key)):
            record(data, errors, warnings, f"transport-neutral execution {key} is required", "subject_identity")
    for key in ("started_at", "completed_at"):
        if not _v5_date(execution.get(key)):
            record(data, errors, warnings, f"transport-neutral execution {key} is invalid", "subject_identity")
    if execution.get("state") != "completed" or execution.get("terminal_reason") != "completed":
        record(data, errors, warnings, "transport-neutral execution is not terminal completed", "authority")

    for key in ("source_commit", "commit_sha", "tree_sha"):
        if not isinstance(candidate.get(key), str) or not GIT_OID.fullmatch(candidate.get(key, "")):
            record(data, errors, warnings, f"transport-neutral Candidate {key} is malformed", "subject_identity")
    if not nonempty(candidate.get("repository_origin")):
        record(data, errors, warnings, "transport-neutral repository_origin is required", "subject_identity")
    for key in ("changed_paths", "deleted_paths"):
        paths = candidate.get(key)
        if not isinstance(paths, list) or not all(
            isinstance(path, str) and GIT_PATH.fullmatch(path) for path in paths
        ):
            record(data, errors, warnings, f"transport-neutral Candidate {key} is malformed", "subject_identity")
    if not isinstance(candidate.get("diff_hash"), str) or not CORE_HASH.fullmatch(
        candidate.get("diff_hash", "")
    ):
        record(data, errors, warnings, "transport-neutral Candidate diff_hash is malformed", "subject_identity")

    if claim.get("status") != "CANDIDATE_READY_PENDING_ACCEPTANCE":
        record(data, errors, warnings, "transport-neutral claim status must remain pending acceptance", "claim_discipline")
    if claim.get("claim_ceiling") != "CANDIDATE_READY":
        record(data, errors, warnings, "transport-neutral claim ceiling mismatch", "claim_discipline")
    for key in (
        "verified",
        "certified",
        "accepted",
        "approved",
        "merged",
        "released",
        "deployed",
        "public_claim_allowed",
    ):
        if claim.get(key) is not False:
            record(data, errors, warnings, f"transport-neutral evidence illegally asserts {key}", "claim_discipline")

    checks = {
        "task_id": (source.get("task_id"), authority.get("task_id")),
        "attempt_id": (source.get("implementer_attempt_id"), authority.get("attempt_id")),
        "task_card_path": (source.get("task_card_path"), authority.get("task_card_path")),
        "task_card_sha256": (
            source.get("task_card_sha256"),
            authority.get("task_card_sha256"),
        ),
        "contract_hash": (
            source.get("contract_hash"),
            authority.get("task_card_sha256"),
        ),
        "root": (repository.get("root"), execution.get("workspace_root")),
        "executor_observed_head": (repository.get("executor_observed_head"), candidate.get("source_commit")),
        "expected_base_commit": (repository.get("expected_base_commit"), candidate.get("source_commit")),
        "candidate_commit_sha": (repository.get("candidate_commit_sha"), candidate.get("commit_sha")),
        "candidate_tree_sha": (repository.get("candidate_tree_sha"), candidate.get("tree_sha")),
        "candidate_diff_sha256": (
            repository.get("candidate_diff_sha256"),
            _hex_or_ref(candidate.get("diff_hash")),
        ),
    }
    for name, (left, right) in checks.items():
        if left != right:
            axis = (
                "authority"
                if name
                in {
                    "task_id",
                    "attempt_id",
                    "task_card_path",
                    "task_card_sha256",
                    "contract_hash",
                }
                else "subject_identity"
            )
            record(data, errors, warnings, f"transport-neutral {name} mismatch", axis)

    evidence_id_parts = (
        authority.get("task_id"),
        authority.get("attempt_id"),
        candidate.get("commit_sha"),
        candidate.get("diff_hash"),
    )
    if all(isinstance(item, str) for item in evidence_id_parts):
        expected_evidence_id = "tnde_" + hashlib.sha256(
            ":".join(evidence_id_parts).encode("utf-8")
        ).hexdigest()[:32]
        if evidence.get("evidence_id") != expected_evidence_id:
            record(data, errors, warnings, "transport-neutral evidence_id mismatch", "subject_identity")

    root = execution.get("workspace_root")
    source_commit = candidate.get("source_commit")
    candidate_commit = candidate.get("commit_sha")
    tree_sha = candidate.get("tree_sha")
    manifest = candidate.get("change_manifest")
    if not (
        isinstance(root, str)
        and isinstance(source_commit, str)
        and GIT_OID.fullmatch(source_commit)
        and isinstance(candidate_commit, str)
        and GIT_OID.fullmatch(candidate_commit)
        and isinstance(tree_sha, str)
        and GIT_OID.fullmatch(tree_sha)
    ):
        return

    try:
        actual_root = _git(root, "rev-parse", "--show-toplevel")
        actual_origin = _git(root, "remote", "get-url", "origin")
        if Path(actual_root).resolve() != Path(root).resolve():
            raise OSError("workspace_root is not the physical Git toplevel")
        if _v5_normalize_remote(actual_origin) != _v5_normalize_remote(candidate["repository_origin"]):
            raise OSError("physical Git origin does not match executor evidence")
        card_sha, card_task, card_paths, card_deletion = _v5_task_card_from_git(
            root,
            source_commit,
            authority["task_card_path"],
        )
        if card_sha != authority.get("task_card_sha256"):
            raise OSError("Task Card SHA-256 does not match the authorized base")
        if card_task != authority.get("task_id"):
            raise OSError("Task Card task_id does not match executor evidence")
        if card_paths != authority.get("allowed_paths"):
            raise OSError("Task Card allowed paths do not match executor evidence")
        if card_deletion != authority.get("deletion_policy"):
            raise OSError("Task Card deletion policy does not match executor evidence")
        if _git(root, "rev-parse", f"{source_commit}^{{commit}}") != source_commit:
            raise OSError("source commit is not the supplied immutable Git object")
        if _git(root, "rev-parse", f"{candidate_commit}^{{commit}}") != candidate_commit:
            raise OSError("Candidate commit is not the supplied immutable Git object")
        ancestry = subprocess.run(
            ["git", "-C", root, "merge-base", "--is-ancestor", source_commit, candidate_commit],
            capture_output=True,
            timeout=10,
        )
        if ancestry.returncode != 0:
            raise OSError("Candidate is not descended from the authorized base")
        if _git(root, "rev-parse", f"{candidate_commit}^{{tree}}") != tree_sha:
            raise OSError("Candidate tree does not match physical Git")
        physical = _physical_manifest(root, source_commit, candidate_commit)
        manifest_errors: list[str] = []
        source_tree = _git(root, "rev-parse", f"{source_commit}^{{tree}}")
        if not _validate_manifest(manifest, source_tree, tree_sha, manifest_errors):
            raise OSError("; ".join(manifest_errors))
        if physical != manifest:
            raise OSError("executor evidence manifest does not match physical Git diff")
        if candidate.get("diff_hash") != core_manifest_hash(physical):
            raise OSError("executor evidence diff_hash does not match physical Git manifest")
        physical_paths = [row["path"] for row in physical["entries"]]
        physical_deleted = [
            row["path"] for row in physical["entries"] if row["change_type"] == "DELETE"
        ]
        if candidate.get("changed_paths") != physical_paths:
            raise OSError("changed_paths do not match physical Git manifest")
        if candidate.get("deleted_paths") != physical_deleted:
            raise OSError("deleted_paths do not match physical Git manifest")
        escaped = [path for path in physical_paths if path not in set(allowed_paths)]
        if escaped:
            raise OSError("physical Candidate escapes allowed_paths: " + ", ".join(escaped))
        if authority.get("deletion_policy") == "FORBID" and physical_deleted:
            raise OSError("physical Candidate contains forbidden deletions")
        warnings.append(f"v5 physical Git subject verified at {actual_root}")
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        record(data, errors, warnings, f"v5 physical Git cross-binding failed: {exc}", "subject_identity")


def _v5_validate_review_evidence(
    data: dict[str, object],
    evidence: object,
    errors: list[str],
    warnings: list[str],
) -> None:
    source = data["source"]
    repository = data["repository"]
    review_result = data["review"]
    if not all(isinstance(item, dict) for item in (source, repository, review_result)):
        errors.append("v5 result source/repository/review must be objects")
        return
    if not isinstance(evidence, dict) or evidence.get("schema") != V5_REVIEW_SCHEMA:
        record(data, errors, warnings, "independent review evidence schema mismatch", "independent_behavior")
        return
    top_keys = {
        "schema",
        "review_id",
        "created_at",
        "reviewer_id",
        "reviewer_attempt_id",
        "independence_class",
        "repository",
        "commands",
        "provenance",
        "claim",
        "integrity",
    }
    if set(evidence) != top_keys:
        record(data, errors, warnings, "independent review evidence top-level shape mismatch", "independent_behavior")
    if not nonempty(evidence.get("review_id")) or not nonempty(evidence.get("reviewer_id")):
        record(data, errors, warnings, "independent review identity is required", "independent_behavior")
    if not _v5_date(evidence.get("created_at")):
        record(data, errors, warnings, "independent review created_at is invalid", "independent_behavior")
    if evidence.get("reviewer_attempt_id") != source.get("reviewer_attempt_id"):
        record(data, errors, warnings, "independent review attempt does not bind result", "independent_behavior")
    if evidence.get("reviewer_attempt_id") == source.get("implementer_attempt_id"):
        record(data, errors, warnings, "implementer and reviewer attempts must differ", "independent_behavior")
    if evidence.get("independence_class") != "INDEPENDENT_REVIEWER":
        record(data, errors, warnings, "review evidence is not independently classified", "independent_behavior")
    if review_result.get("independence_class") != evidence.get("independence_class"):
        record(data, errors, warnings, "review independence class mismatch", "independent_behavior")

    bound_repo = evidence.get("repository")
    repo_keys = {
        "root",
        "origin",
        "expected_base_commit",
        "candidate_commit_sha",
        "candidate_tree_sha",
    }
    if not isinstance(bound_repo, dict) or set(bound_repo) != repo_keys:
        record(data, errors, warnings, "independent review repository shape mismatch", "subject_identity")
        bound_repo = {}
    checks = {
        "root": (repository.get("root"), bound_repo.get("root")),
        "expected_base_commit": (
            repository.get("expected_base_commit"),
            bound_repo.get("expected_base_commit"),
        ),
        "candidate_commit_sha": (
            repository.get("candidate_commit_sha"),
            bound_repo.get("candidate_commit_sha"),
        ),
        "candidate_tree_sha": (
            repository.get("candidate_tree_sha"),
            bound_repo.get("candidate_tree_sha"),
        ),
    }
    for name, (left, right) in checks.items():
        if left != right:
            record(data, errors, warnings, f"independent review {name} mismatch", "subject_identity")
    if nonempty(bound_repo.get("root")) and nonempty(bound_repo.get("origin")):
        try:
            review_root = bound_repo["root"]
            review_base = bound_repo.get("expected_base_commit")
            review_candidate = bound_repo.get("candidate_commit_sha")
            review_tree = bound_repo.get("candidate_tree_sha")
            actual_root = _git(review_root, "rev-parse", "--show-toplevel")
            if Path(actual_root).resolve() != Path(review_root).resolve():
                raise OSError("review root is not the physical Git toplevel")
            actual_origin = _git(review_root, "remote", "get-url", "origin")
            if _v5_normalize_remote(actual_origin) != _v5_normalize_remote(bound_repo["origin"]):
                raise OSError("review repository origin mismatch")
            if not all(
                isinstance(value, str) and GIT_OID.fullmatch(value)
                for value in (review_base, review_candidate, review_tree)
            ):
                raise OSError("review Git subjects are malformed")
            if _git(review_root, "rev-parse", f"{review_base}^{{commit}}") != review_base:
                raise OSError("review base is not the supplied immutable commit")
            if _git(review_root, "rev-parse", f"{review_candidate}^{{commit}}") != review_candidate:
                raise OSError("review Candidate is not the supplied immutable commit")
            ancestry = subprocess.run(
                ["git", "-C", review_root, "merge-base", "--is-ancestor", review_base, review_candidate],
                capture_output=True,
                timeout=10,
            )
            if ancestry.returncode != 0:
                raise OSError("review Candidate is not descended from review base")
            if _git(review_root, "rev-parse", f"{review_candidate}^{{tree}}") != review_tree:
                raise OSError("review Candidate tree does not match physical Git")
        except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
            record(data, errors, warnings, f"independent review Git binding failed: {exc}", "subject_identity")

    commands = evidence.get("commands")
    command_keys = {
        "id",
        "cwd",
        "argv",
        "result_class",
        "exit_code",
        "duration_ms",
        "changed_paths",
        "evidence_ref",
    }
    commands_valid = isinstance(commands, list) and bool(commands)
    if commands_valid:
        for index, command in enumerate(commands):
            if not isinstance(command, dict) or set(command) != command_keys:
                record(data, errors, warnings, f"independent review command {index} shape mismatch", "independent_behavior")
                commands_valid = False
                continue
            if command.get("result_class") not in COMMAND_RESULTS:
                record(data, errors, warnings, f"independent review command {index} result invalid", "independent_behavior")
                commands_valid = False
            if command.get("result_class") == "PASS" and command.get("exit_code") != 0:
                record(data, errors, warnings, f"independent review command {index} PASS requires exit 0", "independent_behavior")
                commands_valid = False
    else:
        record(data, errors, warnings, "independent review commands are required", "independent_behavior")
    if commands_valid and not any(
        isinstance(command, dict) and command.get("result_class") == "PASS"
        for command in commands
    ):
        record(data, errors, warnings, "independent review requires at least one PASS command", "independent_behavior")
    if commands != review_result.get("commands"):
        record(data, errors, warnings, "independent review commands do not match acceptance result", "independent_behavior")

    provenance = evidence.get("provenance")
    provenance_keys = {
        "kind",
        "repository_full_name",
        "issue_number",
        "comment_id",
        "author_login",
        "review_record_sha256",
        "body_sha256",
    }
    if not isinstance(provenance, dict) or set(provenance) != provenance_keys:
        record(
            data,
            errors,
            warnings,
            "independent review provenance shape mismatch",
            "provenance",
        )
    else:
        if provenance.get("kind") != "GITHUB_ISSUE_COMMENT":
            record(
                data,
                errors,
                warnings,
                "independent review provenance must be GITHUB_ISSUE_COMMENT",
                "provenance",
            )
        for key in ("repository_full_name", "author_login"):
            if not nonempty(provenance.get(key)):
                record(
                    data,
                    errors,
                    warnings,
                    f"independent review provenance {key} is required",
                    "provenance",
                )
        if not isinstance(provenance.get("issue_number"), int) or provenance.get(
            "issue_number"
        ) <= 0:
            record(
                data,
                errors,
                warnings,
                "independent review provenance issue_number is invalid",
                "provenance",
            )
        if not isinstance(provenance.get("comment_id"), int) or provenance.get(
            "comment_id"
        ) <= 0:
            record(
                data,
                errors,
                warnings,
                "independent review provenance comment_id is invalid",
                "provenance",
            )
        for key in ("review_record_sha256", "body_sha256"):
            if not isinstance(provenance.get(key), str) or not HEX64.fullmatch(
                provenance.get(key, "")
            ):
                record(
                    data,
                    errors,
                    warnings,
                    f"independent review provenance {key} is malformed",
                    "provenance",
                )
        expected_record = _v5_review_record_hash(evidence)
        if provenance.get("review_record_sha256") != expected_record:
            record(
                data,
                errors,
                warnings,
                "independent review provenance does not bind the review record",
                "provenance",
            )
        try:
            comment = _v5_fetch_github_comment(
                provenance["repository_full_name"],
                provenance["comment_id"],
            )
            body = comment.get("body")
            user = comment.get("user")
            issue_url = comment.get("issue_url")
            if not isinstance(body, str) or not isinstance(user, dict):
                raise OSError("GitHub review comment response is incomplete")
            if user.get("login") != provenance.get("author_login"):
                raise OSError("GitHub review comment author mismatch")
            if evidence.get("reviewer_id") != provenance.get("author_login"):
                raise OSError("reviewer_id is not authenticated by GitHub author")
            repo_full_name = provenance.get("repository_full_name")
            if not isinstance(repo_full_name, str) or not _v5_normalize_remote(
                bound_repo.get("origin", "")
            ).endswith("/" + repo_full_name):
                raise OSError("GitHub review repository does not match Candidate origin")
            if hashlib.sha256(body.encode("utf-8")).hexdigest() != provenance.get(
                "body_sha256"
            ):
                raise OSError("GitHub review comment body hash mismatch")
            if not isinstance(issue_url, str) or not issue_url.endswith(
                f"/issues/{provenance['issue_number']}"
            ):
                raise OSError("GitHub review comment issue binding mismatch")
            markers = {
                "NEXUS_REVIEW_RECORD_SHA256": provenance.get("review_record_sha256"),
                "NEXUS_CANDIDATE_SHA": repository.get("candidate_commit_sha"),
                "NEXUS_TASK_CARD_SHA256": source.get("task_card_sha256"),
                "NEXUS_REVIEWER_ATTEMPT": evidence.get("reviewer_attempt_id"),
                "NEXUS_REVIEWER_ID": evidence.get("reviewer_id"),
            }
            for label, value in markers.items():
                if f"{label}: {value}" not in body:
                    raise OSError(
                        f"GitHub review comment lacks exact {label} marker"
                    )
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            record(
                data,
                errors,
                warnings,
                f"independent review provenance verification failed: {exc}",
                "provenance",
            )

    claim = evidence.get("claim")
    claim_keys = {
        "claim_ceiling",
        "certified",
        "accepted",
        "approved",
        "merged",
        "released",
        "deployed",
        "public_claim_allowed",
    }
    if not isinstance(claim, dict) or set(claim) != claim_keys:
        record(data, errors, warnings, "independent review claim shape mismatch", "claim_discipline")
    else:
        if claim.get("claim_ceiling") != "INDEPENDENT_BEHAVIOR_EVIDENCE_ONLY":
            record(data, errors, warnings, "independent review claim ceiling mismatch", "claim_discipline")
        for key in (
            "certified",
            "accepted",
            "approved",
            "merged",
            "released",
            "deployed",
            "public_claim_allowed",
        ):
            if claim.get(key) is not False:
                record(data, errors, warnings, f"independent review illegally asserts {key}", "claim_discipline")
    integrity = evidence.get("integrity")
    if not isinstance(integrity, dict) or set(integrity) != {"sha256"}:
        record(data, errors, warnings, "independent review integrity shape mismatch", "subject_identity")
    elif integrity.get("sha256") != canonical_sha256(evidence):
        record(data, errors, warnings, "independent review integrity mismatch", "subject_identity")


def validate_physical_v5(
    data: dict[str, object], args: object
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    try:
        executor_path = getattr(args, "executor_evidence", None)
        verification_path = getattr(args, "verification_evidence", None)
        if executor_path is None:
            errors.append("--executor-evidence is required for v5 physical binding")
            return errors, warnings
        if verification_path is None:
            errors.append("--verification-evidence is required for v5 physical binding")
            return errors, warnings
        if file_sha256(executor_path) != source.get("executor_evidence_sha256"):
            record(data, errors, warnings, "executor evidence digest mismatch", "subject_identity")
        if file_sha256(verification_path) != source.get("verification_evidence_sha256"):
            record(data, errors, warnings, "verification evidence digest mismatch", "subject_identity")
        executor = read_json(executor_path)
        verification = read_json(verification_path)
        if source.get("executor_evidence_kind") != V5_DIRECT_KIND:
            record(data, errors, warnings, "unsupported v5 executor evidence branch", "authority")
        else:
            _v5_validate_direct_evidence(data, executor, errors, warnings)
        if source.get("verification_evidence_kind") != V5_REVIEW_KIND:
            record(data, errors, warnings, "unsupported v5 verification evidence branch", "authority")
        else:
            _v5_validate_review_evidence(data, verification, errors, warnings)
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        DuplicateKeyError,
        ValueError,
        TypeError,
        KeyError,
        subprocess.SubprocessError,
    ) as exc:
        record(
            data,
            errors,
            warnings,
            f"v5 physical binding failed: {type(exc).__name__}: {exc}",
            "authority",
        )
    return errors, warnings

def validate(data: object) -> dict[str, object]:
    if isinstance(data, dict) and data.get("schema") == V5_SCHEMA:
        return validate_v5(data)
    return _v4_validate(data)


def validate_physical(
    data: dict[str, object], args: object
) -> tuple[list[str], list[str]]:
    if data.get("schema") == V5_SCHEMA:
        return validate_physical_v5(data, args)
    return _v4_validate_physical(data, args)


def main() -> int:
    args = parse_args()
    try:
        data = read_json(args.result)
    except Exception as exc:
        report = {
            "schema": _V4_VALIDATION_SCHEMA,
            "valid": False,
            "errors": [f"malformed result: {type(exc).__name__}: {exc}"],
            "warnings": [],
        }
    else:
        validation_schema = (
            V5_VALIDATION_SCHEMA
            if data.get("schema") == V5_SCHEMA
            else _V4_VALIDATION_SCHEMA
        )
        try:
            report = validate(data)
            if report["valid"]:
                physical_errors, physical_warnings = validate_physical(data, args)
                report["errors"].extend(physical_errors)
                report["warnings"].extend(physical_warnings)
                report["valid"] = not report["errors"]
        except Exception as exc:
            report = {
                "schema": validation_schema,
                "valid": False,
                "errors": [
                    f"malformed nested input: {type(exc).__name__}: {exc}"
                ],
                "warnings": [],
            }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 2


if _RUN_AS_MAIN:
    raise SystemExit(main())
