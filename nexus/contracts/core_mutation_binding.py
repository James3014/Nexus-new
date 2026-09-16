"""Core mutation binding contracts and generic verification helpers for Issue #957.

Ensures every repository mutation entrypoint (Direct, Delegated, Governed)
is bound to a canonical Nexus Core acceptance contract and deterministic
physical ChangeSet verification substrate.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.adapters.generic_verification import verify_generic_changeset
from product.evidence import (
    AcceptanceContract,
    ChangeSet,
    EvidenceBundle,
    Observation,
    ObservationStatus,
    VerificationPlan,
)
from product.protocol.generic_verification import (
    ACCEPTANCE_CONTRACT_SCHEMA_ID,
    CHANGE_MANIFEST_SCHEMA_ID,
    CHANGE_SET_SCHEMA_ID,
    GENERIC_VERIFICATION_REQUEST_SCHEMA_ID,
    OBSERVATION_SCHEMA_ID,
    PUBLIC_PROTOCOL_VERSION,
    VERIFICATION_PLAN_SCHEMA_ID,
    acceptance_contract_hash,
    canonical_hash,
    canonical_json,
    change_manifest_canonical_value,
    change_manifest_hash,
    change_set_hash,
    evidence_bundle_hash,
    verification_plan_hash,
)
from product.verification import VerificationResult, VerificationStatus, verify

CORE_MUTATION_BINDING_SCHEMA = "nexus.repository_mutation_binding.v1"
CORE_CHANGE_MANIFEST_SCHEMA = CHANGE_MANIFEST_SCHEMA_ID
NEXUS_CORE_PROTOCOL_VERSION = "0.1.0-experimental"

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CoreAcceptanceContractWire:
    contract_id: str
    requirements_hash: str
    required_verifier_ids: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    deletion_policy: str = "FORBID"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "requirements_hash": self.requirements_hash,
            "required_verifier_ids": list(self.required_verifier_ids),
            "allowed_paths": list(self.allowed_paths),
            "deletion_policy": self.deletion_policy,
        }

    @property
    def hash(self) -> str:
        return acceptance_contract_hash(self.to_dict())


@dataclass(frozen=True)
class CoreChangeManifestEntry:
    path: str
    change_type: str  # "ADD" | "MODIFY" | "DELETE"
    before_oid: str | None
    after_oid: str | None
    before_mode: str | None
    after_mode: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "change_type": self.change_type,
            "before_oid": self.before_oid,
            "after_oid": self.after_oid,
            "before_mode": self.before_mode,
            "after_mode": self.after_mode,
        }


@dataclass(frozen=True)
class CoreChangeSetWire:
    change_set_id: str
    source_revision: str
    target_revision: str
    diff_hash: str
    paths: tuple[str, ...]
    deleted_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_set_id": self.change_set_id,
            "source_revision": self.source_revision,
            "target_revision": self.target_revision,
            "diff_hash": self.diff_hash,
            "paths": list(self.paths),
            "deleted_paths": list(self.deleted_paths),
        }

    @property
    def hash(self) -> str:
        return change_set_hash(self.to_dict())


@dataclass(frozen=True)
class RepositoryMutationBinding:
    schema: str
    binding_id: str
    operation_id: str
    attempt_id: str
    repository: dict[str, Any]
    integration_authority: dict[str, Any]
    capability_discovery: dict[str, Any]
    core: dict[str, Any]
    freshness: dict[str, Any]
    binding_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "binding_id": self.binding_id,
            "operation_id": self.operation_id,
            "attempt_id": self.attempt_id,
            "repository": self.repository,
            "integration_authority": self.integration_authority,
            "capability_discovery": self.capability_discovery,
            "core": self.core,
            "freshness": self.freshness,
            "binding_hash": self.binding_hash,
        }


def compute_binding_hash(payload: Mapping[str, Any]) -> str:
    """Compute deterministic SHA-256 over binding payload excluding binding_hash itself."""
    canonical_copy = {k: v for k, v in payload.items() if k != "binding_hash"}
    return canonical_hash(canonical_copy)


def create_repository_mutation_binding(
    *,
    operation_id: str,
    attempt_id: str,
    repo_root: Path | str,
    execution_lane: str = "DIRECT_CANONICAL",
    allowed_files: Sequence[str],
    verifier_commands: Sequence[str] = (),
    deletion_policy: str = "FORBID",
    workspace_identity: str = "canonical_checkout",
    workspace_mode: str = "checkout",
    authority_ref: str = "",
    base_revision: str | None = None,
) -> RepositoryMutationBinding:
    """Derive and freeze a canonical RepositoryMutationBinding before mutation."""
    root = Path(repo_root).resolve()
    rev = base_revision or "HEAD"
    head_sha = subprocess.run(
        ["git", "rev-parse", rev],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    tree_sha = subprocess.run(
        ["git", "rev-parse", f"{rev}^{{tree}}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    try:
        origin_url = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip() or "local"
    except Exception:
        origin_url = "local"

    # Requirements hash binds what & why / verifiers
    normalized_allowed = tuple(sorted(set(str(f).lstrip("./") for f in allowed_files if str(f).strip())))
    normalized_verifiers = tuple(str(cmd).strip() for cmd in verifier_commands if str(cmd).strip())
    if not normalized_verifiers:
        normalized_verifiers = ("git diff --check",)

    req_payload = {
        "operation_id": operation_id,
        "execution_lane": execution_lane,
        "allowed_paths": list(normalized_allowed),
        "required_verifier_ids": list(normalized_verifiers),
        "deletion_policy": deletion_policy,
    }
    req_hash = canonical_hash(req_payload)

    contract_wire = CoreAcceptanceContractWire(
        contract_id=f"contract-{operation_id[:16]}",
        requirements_hash=req_hash,
        required_verifier_ids=normalized_verifiers,
        allowed_paths=normalized_allowed,
        deletion_policy=deletion_policy,
    )
    contract_hash = contract_wire.hash

    binding_id = f"bind-{operation_id[:16]}-{attempt_id[:8]}"
    authority_hash = canonical_hash({
        "execution_lane": execution_lane,
        "authority_ref": authority_ref or f"lane:{execution_lane}",
    })

    binding_data = {
        "schema": CORE_MUTATION_BINDING_SCHEMA,
        "binding_id": binding_id,
        "operation_id": operation_id,
        "attempt_id": attempt_id,
        "repository": {
            "canonical_id": root.name,
            "origin": origin_url,
            "source_revision": head_sha,
            "source_tree": tree_sha,
            "workspace_identity": workspace_identity,
            "workspace_mode": workspace_mode,
        },
        "integration_authority": {
            "execution_lane": execution_lane,
            "authority_ref": authority_ref or f"lane:{execution_lane}",
            "authority_hash": authority_hash,
        },
        "capability_discovery": {
            "required": True,
            "receipt_hash": canonical_hash({"status": "PASS", "lane": execution_lane}),
            "index_revision": head_sha,
        },
        "core": {
            "protocol_version": NEXUS_CORE_PROTOCOL_VERSION,
            "acceptance_contract": contract_wire.to_dict(),
            "acceptance_contract_hash": contract_hash,
        },
        "freshness": {
            "created_at": _utc_now_iso(),
            "valid_until": None,
            "revalidate_before_first_effect": True,
        },
    }
    b_hash = compute_binding_hash(binding_data)
    binding_data["binding_hash"] = b_hash

    return RepositoryMutationBinding(**binding_data)


def _tree_entry(repo_root: Path, tree_ish: str, path: str) -> tuple[str | None, str | None]:
    """Return (mode, oid) of path in tree_ish, or (None, None) if not present."""
    res = subprocess.run(
        ["git", "ls-tree", tree_ish, "--", path],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0 and res.stdout.strip():
        parts = res.stdout.strip().split()
        if len(parts) >= 3:
            return parts[0].zfill(6), parts[2]  # mode, oid
    return None, None


def derive_physical_change_manifest(
    repo_root: Path | str,
    source_tree: str,
    target_tree: str,
) -> tuple[list[CoreChangeManifestEntry], str]:
    """Derive deterministic physical change manifest and diff_hash via git diff-tree."""
    root = Path(repo_root).resolve()
    # Normalize tree refs to 40-char hex
    s_tree = source_tree.removeprefix("git-tree:")
    t_tree = target_tree.removeprefix("git-tree:")

    res = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", "-z", "--no-renames", s_tree, t_tree],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    fields = [f for f in res.stdout.split("\0") if f]
    changes: list[tuple[str, str]] = []
    idx = 0
    while idx < len(fields):
        status_code = fields[idx]
        idx += 1
        if idx >= len(fields):
            break
        path = fields[idx]
        idx += 1
        changes.append((status_code, path))

    entries: list[CoreChangeManifestEntry] = []
    for status_code, path in changes:
        before_mode, before_oid = _tree_entry(root, s_tree, path)
        after_mode, after_oid = _tree_entry(root, t_tree, path)
        if status_code.startswith("A"):
            change_type = "ADD"
        elif status_code.startswith("D"):
            change_type = "DELETE"
        else:
            change_type = "MODIFY"

        entries.append(
            CoreChangeManifestEntry(
                path=path,
                change_type=change_type,
                before_oid=before_oid,
                after_oid=after_oid,
                before_mode=before_mode,
                after_mode=after_mode,
            )
        )
    entries.sort(key=lambda e: e.path)

    manifest_dict = {
        "source_tree": f"git-tree:{s_tree}",
        "target_tree": f"git-tree:{t_tree}",
        "entries": [e.to_dict() for e in entries],
    }
    manifest_hash_val = change_manifest_hash(manifest_dict)
    return entries, manifest_hash_val


def derive_physical_changeset(
    repo_root: Path | str,
    source_revision: str,
    target_revision: str,
    source_tree: str,
    target_tree: str,
    change_set_id: str,
) -> tuple[CoreChangeSetWire, list[CoreChangeManifestEntry]]:
    """Derive ChangeSetWire and manifest entries between two trees."""
    entries, diff_hash = derive_physical_change_manifest(repo_root, source_tree, target_tree)
    changed_paths = tuple(e.path for e in entries)
    deleted_paths = tuple(e.path for e in entries if e.change_type == "DELETE")

    cs_wire = CoreChangeSetWire(
        change_set_id=change_set_id,
        source_revision=f"git-tree:{source_tree.removeprefix('git-tree:')}",
        target_revision=f"git-tree:{target_tree.removeprefix('git-tree:')}",
        diff_hash=diff_hash,
        paths=changed_paths,
        deleted_paths=deleted_paths,
    )
    return cs_wire, entries


def verify_core_mutation_completion(
    *,
    binding: RepositoryMutationBinding | Mapping[str, Any],
    repo_root: Path | str,
    target_tree: str,
    verifier_results: Mapping[str, bool],  # verifier_id -> passed
    verifier_artifacts: Mapping[str, tuple[str, str]] | None = None,  # verifier_id -> (artifact_id, hash)
) -> dict[str, Any]:
    """Execute deterministic Core verification on an observed mutation.

    Returns a structured verification verdict:
    {
        "status": "VERIFIED" | "FAILED_VERIFICATION" | "UNVERIFIABLE",
        "reason_codes": [...],
        "integrity": "VALID" | ...,
        "hashes": {...},
    }
    """
    if isinstance(binding, RepositoryMutationBinding):
        binding_dict = binding.to_dict()
    else:
        binding_dict = dict(binding)

    # 1. Re-verify binding self-integrity
    expected_binding_hash = compute_binding_hash(binding_dict)
    if binding_dict.get("binding_hash") != expected_binding_hash:
        return {
            "status": "UNVERIFIABLE",
            "reason_codes": ["BINDING_HASH_TAMPERED"],
            "integrity": "TAMPERED",
            "hashes": {},
        }

    core_info = binding_dict.get("core") or {}
    ac_dict = core_info.get("acceptance_contract") or {}
    source_tree = binding_dict.get("repository", {}).get("source_tree", "")

    # 2. Derive physical ChangeSet
    cs_wire, entries = derive_physical_changeset(
        repo_root=repo_root,
        source_revision=binding_dict.get("repository", {}).get("source_revision", ""),
        target_revision=target_tree,
        source_tree=source_tree,
        target_tree=target_tree,
        change_set_id=f"cs-{binding_dict.get('operation_id', '')[:16]}",
    )

    # 3. Build verification plan
    plan_dict = {
        "plan_id": f"plan-{binding_dict.get('operation_id', '')[:16]}",
        "acceptance_contract_hash": ac_dict.get("hash") or acceptance_contract_hash(ac_dict),
        "change_set_hash": cs_wire.hash,
        "required_verifier_ids": ac_dict.get("required_verifier_ids", []),
    }
    vp_hash = verification_plan_hash(plan_dict)

    # 4. Build EvidenceBundle from verifier results
    observations: list[dict[str, Any]] = []
    artifacts = verifier_artifacts or {}
    for vid in ac_dict.get("required_verifier_ids", []):
        passed = verifier_results.get(vid, False)
        art_id, art_hash = artifacts.get(vid, (f"art-{vid[:8]}", "sha256:" + "0" * 64))
        observations.append({
            "verifier_id": vid,
            "artifact_id": art_id,
            "artifact_hash": art_hash,
            "status": "PASS" if passed else "FAIL",
        })

    eb_dict = {
        "bundle_id": f"eb-{binding_dict.get('operation_id', '')[:16]}",
        "acceptance_contract_hash": plan_dict["acceptance_contract_hash"],
        "change_set_hash": cs_wire.hash,
        "verification_plan_hash": vp_hash,
        "observations": observations,
    }
    eb_hash = evidence_bundle_hash(eb_dict)
    eb_dict["claimed_bundle_hash"] = eb_hash

    # 5. Build generic verification request payload
    change_manifest_dict = {
        "source_tree": f"git-tree:{source_tree.removeprefix('git-tree:')}",
        "target_tree": f"git-tree:{target_tree.removeprefix('git-tree:')}",
        "entries": [e.to_dict() for e in entries],
    }

    payload = {
        "protocol_version": PUBLIC_PROTOCOL_VERSION,
        "schema": GENERIC_VERIFICATION_REQUEST_SCHEMA_ID,
        "acceptance_contract": ac_dict,
        "change_set": cs_wire.to_dict(),
        "change_manifest": change_manifest_dict,
        "verification_plan": plan_dict,
        "evidence_bundle": eb_dict,
        "certification_policy": None,  # Direct/delegated stops at VERIFIED
    }

    status_code, result = verify_generic_changeset(payload)
    if status_code != 200:
        return {
            "status": "UNVERIFIABLE",
            "reason_codes": [f"HTTP_{status_code}", result.get("error", {}).get("code", "MALFORMED")],
            "integrity": "MALFORMED",
            "hashes": {},
        }

    return {
        "status": result["verification"]["status"],
        "reason_codes": result["verification"]["reason_codes"],
        "integrity": result["verification"]["integrity"],
        "hashes": result["hashes"],
        "change_set": cs_wire.to_dict(),
        "changed_files": list(cs_wire.paths),
        "deleted_files": list(cs_wire.deleted_paths),
    }
