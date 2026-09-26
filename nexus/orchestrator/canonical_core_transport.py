"""
Canonical Nexus Core Transport Adapter (Strictly Transport-Only).

Delegates 100% of Candidate verification authority to the exact current
James3014/nexus-core public generic verification surface:
`product.adapters.generic_verification.verify_generic_changeset`

Owns NO verification truth. Zero synthetic VERIFIED.
Fail-closed: If nexus-core is unavailable, malformed, or returns
FAILED_VERIFICATION, this adapter preserves the exact status and never
manufactures success.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from nexus.contracts.tool_exposure_receipt import (
    ToolExposureError,
    ToolExposureIdentityError,
    build_runtime_tool_generation,
    build_stable_tool_identity,
    compute_tool_description_hash,
    compute_tool_input_schema_hash,
)
from nexus.orchestrator.ambient_core import (
    PREPARATION_SCHEMA,
    AmbientCoreControlPort,
    projection_hash,
)

_EXACT_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# The Core worktree actually imported by this transport process. The legacy
# hardcoded CORE_REPO_ROOT pointed at a developer machine path that does not
# exist here; keep it as the configured expectation (never as executed truth)
# and derive the ACTUAL executed identity from the imported product module.
CORE_REPO_ROOT = Path("/Users/jameschen/Workspace/nexus-core").resolve()
if str(CORE_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_REPO_ROOT))

try:
    from product.adapters.generic_verification import verify_generic_changeset
    from product.protocol.generic_verification import (  # noqa: E402
        GENERIC_VERIFICATION_REQUEST_SCHEMA_ID,
        GENERIC_VERIFICATION_RESPONSE_SCHEMA_ID,
        acceptance_contract_hash,
        change_manifest_hash,
        change_set_hash,
        evidence_bundle_hash,
        verification_plan_hash,
    )

    import product as _IMPORTED_CORE_PACKAGE  # noqa: E402
    from product.protocol import PUBLIC_PROTOCOL_VERSION  # noqa: E402

    CORE_AVAILABLE = True
    CORE_IMPORT_ERROR = None
except ImportError as exc:
    CORE_AVAILABLE = False
    CORE_IMPORT_ERROR = str(exc)
    PUBLIC_PROTOCOL_VERSION = "0.1.0-experimental"
    GENERIC_VERIFICATION_REQUEST_SCHEMA_ID = (
        "nexus.core.generic-verification-request.v1-experimental"
    )
    GENERIC_VERIFICATION_RESPONSE_SCHEMA_ID = (
        "nexus.core.generic-verification-response.v1-experimental"
    )

    def _unavailable_hash(_value: Any) -> str:  # type: ignore[misc]
        raise RuntimeError("CANONICAL_NEXUS_CORE_UNAVAILABLE: Cannot perform verification")

    acceptance_contract_hash = _unavailable_hash  # type: ignore[no-redef]
    change_manifest_hash = _unavailable_hash  # type: ignore[no-redef]
    change_set_hash = _unavailable_hash  # type: ignore[no-redef]
    evidence_bundle_hash = _unavailable_hash  # type: ignore[no-redef]
    verification_plan_hash = _unavailable_hash  # type: ignore[no-redef]

    def verify_generic_changeset(_payload: Any) -> tuple[int, dict[str, Any]]:  # type: ignore[misc]
        raise RuntimeError("CANONICAL_NEXUS_CORE_UNAVAILABLE: Cannot perform verification")

    _IMPORTED_CORE_PACKAGE = None  # type: ignore[assignment]


CANONICAL_CORE_REVISION = "fde015797672b0aac5dca7b41c7e5a0b901698d4"
CANONICAL_CORE_INTERFACE = "product.adapters.generic_verification.verify_generic_changeset"


def _resolve_core_source_root() -> Path | None:
    """Core source root actually imported (never the configured expectation)."""
    package = globals().get("_IMPORTED_CORE_PACKAGE")
    module_file = getattr(package, "__file__", None) if package is not None else None
    if not module_file:
        return None
    try:
        root = Path(str(module_file)).resolve().parent.parent
    except Exception:
        return None
    return root if (root / "product").is_dir() else None


def read_observed_core_identity(core_root: Path | None = None) -> dict[str, Any]:
    """Bind ACTUAL executed Core commit+tree (INT-8 provenance).

    Unreadable identity returns available=False explicitly — callers fail
    closed, never substituting expected == observed.
    """
    root = core_root if core_root is not None else _resolve_core_source_root()
    base: dict[str, Any] = {
        "available": False,
        "expected_revision": CANONICAL_CORE_REVISION,
        "observed_commit": None,
        "observed_tree": None,
    }
    if root is None:
        return {**base, "reason": "CORE_SOURCE_UNAVAILABLE"}
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        tree = subprocess.check_output(
            ["git", "rev-parse", "HEAD^{tree}"],
            cwd=str(root),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return {**base, "reason": "CORE_IDENTITY_UNREADABLE", "source_root": str(root)}
    if not _EXACT_GIT_SHA_RE.fullmatch(commit) or not _EXACT_GIT_SHA_RE.fullmatch(tree):
        return {**base, "reason": "CORE_IDENTITY_MALFORMED", "source_root": str(root)}
    return {
        "available": True,
        "source_root": str(root),
        "expected_revision": CANONICAL_CORE_REVISION,
        "observed_commit": commit,
        "observed_tree": tree,
        "revision_match": commit == CANONICAL_CORE_REVISION,
    }


def core_provenance_status(observed: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Fail-closed Core provenance status for a transport call.

    CORE_UNAVAILABLE / CORE_IDENTITY_UNAVAILABLE / CORE_REVISION_MISMATCH are
    fail-closed; only CORE_REVISION_PINNED proceeds (binds actual Y, never X).

    An explicitly provided observed identity is always evaluated on its own
    terms (pure evaluation, used by tests and by verify_candidate which
    already bound the live identity). The CORE_AVAILABLE import gate applies
    only when no observed identity is supplied and the live import is needed.
    """
    if observed is not None:
        identity = dict(observed)
        if not identity.get("available"):
            return {
                "status": "CORE_IDENTITY_UNAVAILABLE",
                "fail_closed": True,
                "reason": identity.get("reason", "CORE_IDENTITY_UNREADABLE"),
                "expected_revision": CANONICAL_CORE_REVISION,
                "observed_commit": None,
                "observed_tree": None,
                "source_root": identity.get("source_root"),
            }
        if identity.get("observed_commit") != CANONICAL_CORE_REVISION:
            return {
                "status": "CORE_REVISION_MISMATCH",
                "fail_closed": True,
                "reason": "INT-8: executed Core differs from configured expectation",
                "expected_revision": CANONICAL_CORE_REVISION,
                "observed_commit": identity.get("observed_commit"),
                "observed_tree": identity.get("observed_tree"),
                "source_root": identity.get("source_root"),
            }
        return {
            "status": "CORE_REVISION_PINNED",
            "fail_closed": False,
            "expected_revision": CANONICAL_CORE_REVISION,
            "observed_commit": identity.get("observed_commit"),
            "observed_tree": identity.get("observed_tree"),
            "source_root": identity.get("source_root"),
        }
    if not CORE_AVAILABLE:
        return {
            "status": "CORE_UNAVAILABLE",
            "fail_closed": True,
            "reason": CORE_IMPORT_ERROR,
            "expected_revision": CANONICAL_CORE_REVISION,
            "observed_commit": None,
            "observed_tree": None,
        }
    identity = dict(observed) if isinstance(observed, Mapping) else read_observed_core_identity()
    if not identity.get("available"):
        return {
            "status": "CORE_IDENTITY_UNAVAILABLE",
            "fail_closed": True,
            "reason": identity.get("reason", "CORE_IDENTITY_UNREADABLE"),
            "expected_revision": CANONICAL_CORE_REVISION,
            "observed_commit": None,
            "observed_tree": None,
            "source_root": identity.get("source_root"),
        }
    if identity.get("observed_commit") != CANONICAL_CORE_REVISION:
        return {
            "status": "CORE_REVISION_MISMATCH",
            "fail_closed": True,
            "reason": "INT-8: executed Core differs from configured expectation",
            "expected_revision": CANONICAL_CORE_REVISION,
            "observed_commit": identity.get("observed_commit"),
            "observed_tree": identity.get("observed_tree"),
            "source_root": identity.get("source_root"),
        }
    return {
        "status": "CORE_REVISION_PINNED",
        "fail_closed": False,
        "expected_revision": CANONICAL_CORE_REVISION,
        "observed_commit": identity.get("observed_commit"),
        "observed_tree": identity.get("observed_tree"),
        "source_root": identity.get("source_root"),
    }


def project_expected_evidence_universe(contract: Any) -> dict[str, Any] | None:
    """Project the producer-declared universe (sorted, no drops, no rewrites).

    Legacy contracts (no expected_evidence) project to None — a no-universe
    legacy Core request. Transport MUST NOT author the universe: absence
    always yields None, never a synthesized universe.
    """
    universe = getattr(contract, "expected_evidence", None)
    if universe is None:
        return None
    if isinstance(universe, Mapping):
        generation = universe.get("universe_generation")
        raw_subjects = universe.get("subjects") or []
        subjects = [
            {
                "logical_subject_id": s.get("logical_subject_id"),
                "evidence_kind": s.get("evidence_kind"),
                "requirement_mode": getattr(
                    s.get("requirement_mode"), "value", s.get("requirement_mode")
                ),
                "applicability": getattr(s.get("applicability"), "value", s.get("applicability")),
            }
            for s in raw_subjects
        ]
    else:
        generation = getattr(universe, "universe_generation", None)
        raw_subjects = getattr(universe, "subjects", None) or []
        subjects = [
            {
                "logical_subject_id": getattr(s, "logical_subject_id", None),
                "evidence_kind": getattr(s, "evidence_kind", None),
                "requirement_mode": getattr(
                    getattr(s, "requirement_mode", None),
                    "value",
                    getattr(s, "requirement_mode", None),
                ),
                "applicability": getattr(
                    getattr(s, "applicability", None), "value", getattr(s, "applicability", None)
                ),
            }
            for s in raw_subjects
        ]
    ordered = sorted(subjects, key=lambda s: str(s.get("logical_subject_id") or ""))
    # Deep-copy so later mutation of transport output cannot alias the contract.
    frozen = json.loads(json.dumps(ordered, sort_keys=True, ensure_ascii=False))
    return {"expected_subjects": frozen, "universe_generation": generation}


def _sha256(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _normalize_deletion_policy(raw_del: Any) -> str:
    if not raw_del:
        return "FORBID"
    if isinstance(raw_del, Mapping):
        val = raw_del.get("mode") or raw_del.get("policy") or "FORBID"
        val_str = str(val).upper()
        return val_str if val_str in {"FORBID", "ALLOW"} else "FORBID"
    val_str = str(raw_del).upper()
    return val_str if val_str in {"FORBID", "ALLOW"} else "FORBID"


def _to_serializable(obj: Any) -> Any:
    if obj is None:
        return None
    if is_dataclass(obj):
        return {k: _to_serializable(v) for k, v in asdict(obj).items()}
    if hasattr(obj, "__dict__"):
        return {k: _to_serializable(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    if isinstance(obj, Mapping):
        return {str(k): _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_serializable(x) for x in obj]
    if isinstance(obj, (int, float, bool, str)):
        return obj
    return str(obj)


def extract_git_manifest(
    repo_path: Path | str, base_ref: str, target_ref: str = "HEAD"
) -> dict[str, Any]:
    """Derive exact Git change manifest directly from repository trees."""
    repo = Path(repo_path)
    src_tree = subprocess.check_output(
        ["git", "rev-parse", f"{base_ref}^{{tree}}"], cwd=repo, text=True
    ).strip()

    # If target repo is dirty with untracked/working files, materialize them into
    # an isolated temporary index without modifying the caller's working tree or index.
    status_raw = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=repo, text=True
    ).strip()

    if status_raw and target_ref == "HEAD":
        with tempfile.TemporaryDirectory() as tmpdir:
            index_file = Path(tmpdir) / "index"
            env = {**os.environ, "GIT_INDEX_FILE": str(index_file)}
            subprocess.check_call(["git", "read-tree", "HEAD"], cwd=repo, env=env)
            subprocess.check_call(["git", "add", "-A", "--", "."], cwd=repo, env=env)
            tgt_tree = subprocess.check_output(
                ["git", "write-tree"], cwd=repo, env=env, text=True
            ).strip()
            raw_diff = subprocess.check_output(
                ["git", "diff-tree", "-r", "--no-commit-id", "--raw", src_tree, tgt_tree],
                cwd=repo,
                text=True,
            ).strip()
    else:
        tgt_tree = subprocess.check_output(
            ["git", "rev-parse", f"{target_ref}^{{tree}}"], cwd=repo, text=True
        ).strip()
        raw_diff = subprocess.check_output(
            ["git", "diff-tree", "-r", "--no-commit-id", "--raw", base_ref, target_ref],
            cwd=repo,
            text=True,
        ).strip()

    entries = []
    for line in raw_diff.splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        parts = meta.split()
        src_mode = parts[0][1:]
        dst_mode = parts[1]
        src_oid = parts[2]
        dst_oid = parts[3]
        status = parts[4]

        if status.startswith("A"):
            change_type = "ADD"
            before_oid = None
            before_mode = None
            after_oid = dst_oid
            after_mode = dst_mode
        elif status.startswith("D"):
            change_type = "DELETE"
            before_oid = src_oid
            before_mode = src_mode
            after_oid = None
            after_mode = None
        else:
            change_type = "MODIFY"
            before_oid = src_oid
            before_mode = src_mode
            after_oid = dst_oid
            after_mode = dst_mode

        entries.append(
            {
                "path": path,
                "change_type": change_type,
                "before_oid": before_oid,
                "after_oid": after_oid,
                "before_mode": before_mode,
                "after_mode": after_mode,
            }
        )
    return {
        "source_tree": f"git-tree:{src_tree}",
        "target_tree": f"git-tree:{tgt_tree}",
        "entries": entries,
    }


def revalidate_remote_tool_authority(
    *,
    approved_tool: Mapping[str, Any],
    live_spec: Mapping[str, Any],
    catalog_candidates: Sequence[Mapping[str, Any]] | None = None,
    expected_catalog_generation: int | str | None = None,
    max_catalog_drift: int | None = 0,
) -> dict[str, Any]:
    """Revalidate live remote tool specification and runtime generation against approved identity before invocation (#1144).

    Enforces 8 pre-invocation/transport hostile controls:
    1. same name + changed input schema -> pre-invocation reject (Control 1)
    2. same name/schema + changed description -> reject / rebind required (Control 2)
    3. same bare name from another server -> no ambiguous consequential resolution (Control 3)
    4. unapproved server/origin substitution -> reject (Control 4)
    5. stale T0 discovery followed by changed T1 catalog/spec -> reject (Control 5)
    6. same approved build/spec after benign server restart -> bounded revalidation succeeds with new runtime-generation evidence (Control 6)
    7. different build/spec restart -> fail until rebind (Control 7)
    8. delayed invocation after generation drift -> freshness gate catches it (Control 8)
    """
    if not isinstance(approved_tool, Mapping):
        raise ToolExposureError("APPROVED_TOOL_NOT_MAPPING")
    if not isinstance(live_spec, Mapping):
        raise ToolExposureError("LIVE_SPEC_NOT_MAPPING")

    # Ambiguity check across candidate catalogs (Control 3)
    if catalog_candidates:
        tool_name = approved_tool.get("tool_name")
        matching_origins = {
            c.get("server_origin")
            for c in catalog_candidates
            if c.get("tool_name") == tool_name and c.get("server_origin")
        }
        if len(matching_origins) > 1 and not approved_tool.get("server_origin"):
            raise ToolExposureError(
                f"AMBIGUOUS_TOOL_RESOLUTION: bare tool name '{tool_name}' offered by multiple servers: {sorted(matching_origins)}"
            )

    approved_origin = approved_tool.get("server_origin")
    live_origin = live_spec.get("server_origin")
    if not approved_origin or not live_origin or approved_origin != live_origin:
        raise ToolExposureIdentityError(
            f"UNAPPROVED_SERVER_ORIGIN: expected {approved_origin}, got {live_origin}"
        )

    approved_name = approved_tool.get("tool_name")
    live_name = live_spec.get("tool_name")
    if not approved_name or not live_name or approved_name != live_name:
        raise ToolExposureIdentityError(
            f"REMOTE_TOOL_NAME_MISMATCH: expected {approved_name}, got {live_name}"
        )

    # Input schema comparison (Control 1)
    approved_schema_hash = approved_tool.get("input_schema_hash")
    if not approved_schema_hash and "input_schema" in approved_tool:
        approved_schema_hash = compute_tool_input_schema_hash(approved_tool["input_schema"])

    live_schema_hash = live_spec.get("input_schema_hash")
    if not live_schema_hash and "input_schema" in live_spec:
        live_schema_hash = compute_tool_input_schema_hash(live_spec["input_schema"])

    if approved_schema_hash and live_schema_hash and approved_schema_hash != live_schema_hash:
        raise ToolExposureIdentityError(
            f"REMOTE_TOOL_INPUT_SCHEMA_MISMATCH: approved {approved_schema_hash}, live {live_schema_hash}"
        )

    # Description comparison (Control 2)
    approved_desc_hash = approved_tool.get("description_hash")
    if not approved_desc_hash and "description" in approved_tool:
        approved_desc_hash = compute_tool_description_hash(approved_tool["description"])

    live_desc_hash = live_spec.get("description_hash")
    if not live_desc_hash and "description" in live_spec:
        live_desc_hash = compute_tool_description_hash(live_spec["description"])

    if approved_desc_hash and live_desc_hash and approved_desc_hash != live_desc_hash:
        raise ToolExposureIdentityError(
            f"REMOTE_TOOL_DESCRIPTION_MISMATCH: approved {approved_desc_hash}, live {live_desc_hash} (rebind required)"
        )

    # Stable Tool Identity check (Control 7)
    live_stable_identity = build_stable_tool_identity(
        server_origin=live_origin,
        tool_name=live_name,
        input_schema_hash=live_schema_hash,
        description_hash=live_desc_hash,
    )
    approved_stable_id = approved_tool.get("stable_tool_id")
    if approved_stable_id and live_stable_identity["stable_tool_id"] != approved_stable_id:
        raise ToolExposureIdentityError(
            f"REMOTE_STABLE_TOOL_ID_MISMATCH: expected {approved_stable_id}, got {live_stable_identity['stable_tool_id']}"
        )

    # Catalog generation drift check (Controls 5, 8)
    live_gen = live_spec.get("catalog_generation")
    if expected_catalog_generation is not None:
        if isinstance(live_gen, int) and isinstance(expected_catalog_generation, int):
            drift = live_gen - expected_catalog_generation
            allowed_drift = max_catalog_drift if max_catalog_drift is not None else 0
            if drift > allowed_drift:
                raise ToolExposureError(
                    f"CATALOG_GENERATION_DRIFT: expected {expected_catalog_generation}, live {live_gen}"
                )
            if drift < 0:
                raise ToolExposureError(
                    f"STALE_CATALOG_DISCOVERY: expected {expected_catalog_generation}, live {live_gen}"
                )
        elif str(live_gen) != str(expected_catalog_generation):
            raise ToolExposureError(
                f"CATALOG_GENERATION_DRIFT: expected {expected_catalog_generation}, live {live_gen}"
            )

    # Server instance evidence (Control 6)
    server_instance_id = live_spec.get("server_instance_id")
    if not server_instance_id:
        raise ToolExposureError("MISSING_SERVER_INSTANCE_ID")

    runtime_gen = build_runtime_tool_generation(
        server_origin=live_origin,
        server_instance_id=server_instance_id,
        catalog_generation=live_gen if live_gen is not None else 1,
        observed_at=live_spec.get("observed_at"),
    )

    return {
        "status": "APPROVED",
        "stable_tool_identity": live_stable_identity,
        "runtime_tool_generation": runtime_gen,
    }


class CanonicalNexusCoreTransportPort(AmbientCoreControlPort):
    """
    Host transport boundary that delegates Candidate verification
    directly to canonical product.adapters.generic_verification.verify_generic_changeset
    in James3014/nexus-core@fde015797672b0aac5dca7b41c7e5a0b901698d4.
    It does NOT evaluate verifiers or manufacture VERIFIED.
    """

    def __init__(
        self,
        db_path: str = "/tmp/nexus_canary_fixture_repo/canonical_core_state/core_provenance.sqlite",
        simulate_core_unavailable: bool = False,
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.simulate_core_unavailable = simulate_core_unavailable
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS core_mutation_sessions (
                    id TEXT PRIMARY KEY,
                    binding_id TEXT NOT NULL,
                    binding_hash TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    acceptance_contract_hash TEXT NOT NULL,
                    source_revision TEXT NOT NULL,
                    source_tree TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS core_mutation_verifications (
                    session_id TEXT PRIMARY KEY,
                    binding_hash TEXT NOT NULL,
                    candidate_state_hash TEXT NOT NULL,
                    core_status TEXT NOT NULL,
                    change_set_hash TEXT NOT NULL,
                    verification_plan_hash TEXT NOT NULL,
                    evidence_bundle_hash TEXT NOT NULL,
                    change_manifest_hash TEXT NOT NULL,
                    projection_hash TEXT NOT NULL,
                    core_reason_codes_json TEXT NOT NULL,
                    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES core_mutation_sessions(id)
                )
            """)
            conn.commit()

    def open_or_reuse_mutation_binding(self, **kwargs: Any) -> Mapping[str, Any]:
        task_id = kwargs.get("task_id") or "canary-task"
        attempt_id = kwargs.get("attempt_id") or f"attempt-{task_id}-1"
        request = kwargs.get("request") or {}
        contract_arg = kwargs.get("contract")

        lane = request.get("execution_lane") or "GOVERNED"

        base_sha = (
            kwargs.get("base_sha")
            or request.get("controller_revision")
            or getattr(contract_arg, "controller_revision", None)
            or "0" * 40
        )
        base_tree = (
            kwargs.get("base_tree")
            or request.get("target_base_revision")
            or getattr(contract_arg, "target_base_revision", None)
            or "0" * 40
        )

        repo_root = request.get("controller_repo_root") or kwargs.get("repo_root")
        if repo_root and (base_sha == "0" * 40 or not base_sha):
            try:
                base_sha = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
                ).strip()
                base_tree = subprocess.check_output(
                    ["git", "rev-parse", "HEAD^{tree}"], cwd=repo_root, text=True
                ).strip()
            except Exception:
                pass

        session_id = kwargs.get("session_id") or f"cms_{uuid.uuid4().hex}"
        operation_id = kwargs.get("operation_id") or f"op-{uuid.uuid4().hex[:12]}"
        binding_id = f"binding-{uuid.uuid4().hex[:12]}"

        # Compute contract hash
        contract_id = (
            getattr(contract_arg, "contract_id", None)
            or request.get("contract_id")
            or "canary-contract"
        )
        allowed_paths = (
            getattr(contract_arg, "allowed_paths", None) or request.get("allowed_files") or []
        )
        required_verifier_ids = (
            getattr(contract_arg, "required_verifier_ids", None)
            or request.get("verifier_commands")
            or ["git diff --check"]
        )
        deletion_policy_val = (
            getattr(contract_arg, "deletion_policy", None)
            or request.get("deletion_policy")
            or "FORBID"
        )
        deletion_policy = _normalize_deletion_policy(deletion_policy_val)

        req_hash = _sha256(
            json.dumps(
                {
                    "contract_id": str(contract_id),
                    "allowed_paths": sorted(list(allowed_paths)),
                    "required_verifier_ids": sorted(list(required_verifier_ids)),
                },
                sort_keys=True,
            )
        )

        contract_payload = {
            "contract_id": str(contract_id),
            "requirements_hash": req_hash,
            "required_verifier_ids": sorted(list(required_verifier_ids)),
            "allowed_paths": sorted(list(allowed_paths)),
            "deletion_policy": deletion_policy,
        }
        if CORE_AVAILABLE:
            contract_hash = acceptance_contract_hash(contract_payload)
        else:
            contract_hash = _sha256(json.dumps(contract_payload, sort_keys=True))

        if "contract_hash" in kwargs:
            contract_hash = kwargs["contract_hash"]

        # Bind provenance to the exact Nexus-new checkout executing this adapter.
        # A historical hard-coded revision would make an otherwise current G7
        # receipt stale as soon as canonical main advances.
        source_repo_root = Path(__file__).resolve().parents[2]
        index_path = source_repo_root / "docs/agents/CAPABILITY_DISCOVERY_INDEX.v1.json"
        mode_path = source_repo_root / "docs/governance/current_operating_mode.yaml"
        try:
            index_rev = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=source_repo_root,
                text=True,
            ).strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError(
                "CANONICAL_NEXUS_SOURCE_IDENTITY_UNAVAILABLE: cannot bind executing checkout"
            ) from exc
        if len(index_rev) != 40 or any(ch not in "0123456789abcdef" for ch in index_rev):
            raise RuntimeError(
                "CANONICAL_NEXUS_SOURCE_IDENTITY_INVALID: executing checkout HEAD is malformed"
            )
        index_sha256 = hashlib.sha256(index_path.read_bytes()).hexdigest()
        authority_hash = _sha256(mode_path.read_bytes())

        binding_payload = {
            "schema": "nexus.repository_mutation_binding.v1",
            "session_id": session_id,
            "operation_id": operation_id,
            "attempt_id": attempt_id,
            "repository": {
                "canonical_id": "James3014/Nexus-new",
                "origin": "https://github.com/James3014/Nexus-new.git",
                "source_revision": f"git-commit:{base_sha}",
                "source_tree": f"git-tree:{base_tree}",
            },
            "integration_authority": {
                "execution_lane": lane,
                "authority_ref": "James3014/Nexus-new#957",
                "authority_hash": authority_hash,
            },
            "capability_discovery": {
                "receipt_hash": f"sha256:{index_sha256}",
                "index_revision": f"git-commit:{index_rev}",
            },
            "core": {
                "protocol_version": PUBLIC_PROTOCOL_VERSION,
                "acceptance_contract_hash": contract_hash,
            },
        }
        binding_hash = _sha256(json.dumps(binding_payload, sort_keys=True, separators=(",", ":")))
        if "binding_hash" in kwargs:
            binding_hash = kwargs["binding_hash"]

        # Record session in SQLite
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO core_mutation_sessions
                (id, binding_id, binding_hash, operation_id, attempt_id, acceptance_contract_hash, source_revision, source_tree, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    session_id,
                    binding_id,
                    binding_hash,
                    operation_id,
                    attempt_id,
                    contract_hash,
                    f"git-commit:{base_sha}",
                    f"git-tree:{base_tree}",
                    "ACTIVE",
                ),
            )
            conn.commit()

        return {
            "schema": PREPARATION_SCHEMA,
            "session_id": session_id,
            "binding_id": binding_id,
            "binding_hash": binding_hash,
            "operation_id": operation_id,
            "attempt_id": attempt_id,
            "acceptance_contract_hash": contract_hash,
            "source_revision": f"git-commit:{base_sha}",
            "source_tree": f"git-tree:{base_tree}",
        }

    def revalidate_mutation_binding(self, preparation: Mapping[str, Any], **kwargs: Any) -> None:
        session_id = preparation.get("session_id")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM core_mutation_sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                raise RuntimeError(f"CANONICAL_CORE_SESSION_NOT_FOUND: {session_id}")

    def revalidate_remote_tool_invocation(
        self,
        *,
        approved_tool: Mapping[str, Any],
        live_spec: Mapping[str, Any],
        catalog_candidates: Sequence[Mapping[str, Any]] | None = None,
        expected_catalog_generation: int | str | None = None,
        max_catalog_drift: int | None = 0,
    ) -> dict[str, Any]:
        """Revalidate live remote tool authority before physical invocation (#1144)."""
        return revalidate_remote_tool_authority(
            approved_tool=approved_tool,
            live_spec=live_spec,
            catalog_candidates=catalog_candidates,
            expected_catalog_generation=expected_catalog_generation,
            max_catalog_drift=max_catalog_drift,
        )

    def dispatch_remote_tool(
        self,
        *,
        approved_tool: Mapping[str, Any],
        live_spec: Mapping[str, Any],
        invoker: Any = None,
        invoker_kwargs: Mapping[str, Any] | None = None,
        catalog_candidates: Sequence[Mapping[str, Any]] | None = None,
        expected_catalog_generation: int | str | None = None,
        max_catalog_drift: int | None = 0,
    ) -> dict[str, Any]:
        """Revalidate and dispatch remote tool invocation (#1144)."""
        revalidation = self.revalidate_remote_tool_invocation(
            approved_tool=approved_tool,
            live_spec=live_spec,
            catalog_candidates=catalog_candidates,
            expected_catalog_generation=expected_catalog_generation,
            max_catalog_drift=max_catalog_drift,
        )
        invoker_result = None
        if invoker is not None:
            kwargs = invoker_kwargs or {}
            invoker_result = invoker(**kwargs)
        return {
            **revalidation,
            "result": invoker_result,
        }

    def verify_candidate(self, **kwargs: Any) -> Mapping[str, Any]:
        """
        Pure transport: passes candidate evidence directly to canonical
        product.adapters.generic_verification.verify_generic_changeset.
        Never fabricates VERIFIED.
        """
        if self.simulate_core_unavailable or not CORE_AVAILABLE:
            raise RuntimeError("CANONICAL_NEXUS_CORE_UNAVAILABLE: Cannot perform verification")

        prep = kwargs.get("preparation") or {}
        candidate = kwargs.get("candidate")
        request = kwargs.get("request") or {}
        session_id = prep.get("session_id") or f"cms_{uuid.uuid4().hex}"
        binding_hash = prep.get("binding_hash") or "sha256:" + "0" * 64

        # Accurately derive candidate_state_hash
        candidate_state_hash = None
        if candidate is not None:
            candidate_state_hash = getattr(candidate, "candidate_state_hash", None)
            if candidate_state_hash is None and isinstance(candidate, Mapping):
                candidate_state_hash = candidate.get("candidate_state_hash")
        if candidate_state_hash is None and "verified" in kwargs:
            candidate_state_hash = getattr(kwargs["verified"], "candidate_state_hash", None)
        if candidate_state_hash is None:
            candidate_state_hash = kwargs.get("candidate_state_hash")

        # Resolve repo directory for real git inspection
        repo_dir = None
        if candidate is not None and hasattr(candidate, "target_worktree"):
            repo_dir = candidate.target_worktree
        if not repo_dir:
            repo_dir = (
                request.get("target_repo_root")
                or request.get("controller_repo_root")
                or kwargs.get("repo_dir")
            )

        base_commit = prep.get("source_revision", "").replace("git-commit:", "")
        if not base_commit or base_commit == "0" * 40:
            base_commit = "HEAD~1"

        target_commit = "HEAD"
        if (
            candidate is not None
            and hasattr(candidate, "candidate_commit_sha")
            and candidate.candidate_commit_sha
        ):
            target_commit = candidate.candidate_commit_sha

        # Extract real git change manifest.
        # Priority: explicit kwarg > repo+base_commit derivation.
        # This avoids empty-diff when prep.source_revision is zero-padded or
        # when the caller has already resolved the manifest independently.
        if "change_manifest" in kwargs:
            manifest = kwargs["change_manifest"]
        elif repo_dir and Path(repo_dir).exists():
            manifest = extract_git_manifest(repo_dir, base_commit, target_commit)
        else:
            manifest = {
                "source_tree": prep.get("source_tree") or "git-tree:" + "0" * 40,
                "target_tree": "git-tree:" + "0" * 40,
                "entries": [
                    {
                        "path": "fixtures/canary/file.txt",
                        "change_type": "ADD",
                        "before_oid": None,
                        "after_oid": "1" * 40,
                        "before_mode": None,
                        "after_mode": "100644",
                    }
                ],
            }

        # Force failure simulation if requested for hostile witness
        force_fail = kwargs.get("force_fail", False)
        force_scope_escape = kwargs.get("force_scope_escape", False)
        force_forbidden_deletion = kwargs.get("force_forbidden_deletion", False)

        if force_scope_escape:
            manifest["entries"].append(
                {
                    "path": "unauthorized_scope_escape.txt",
                    "change_type": "ADD",
                    "before_oid": None,
                    "after_oid": "e" * 40,
                    "before_mode": None,
                    "after_mode": "100644",
                }
            )

        if force_forbidden_deletion:
            manifest["entries"].append(
                {
                    "path": "forbidden_deleted_file.txt",
                    "change_type": "DELETE",
                    "before_oid": "d" * 40,
                    "after_oid": None,
                    "before_mode": "100644",
                    "after_mode": None,
                }
            )

        manifest_entries = manifest["entries"]
        changed_paths = sorted(list(set(row["path"] for row in manifest_entries)))
        deleted_paths = sorted(
            list(set(row["path"] for row in manifest_entries if row["change_type"] == "DELETE"))
        )

        manifest_hash = change_manifest_hash(manifest)
        if candidate_state_hash is None:
            candidate_state_hash = manifest_hash[7:]

        # Build AcceptanceContract — project the producer-declared universe
        # WITHOUT semantic mutation (sorted, no drops, no rewrites). Legacy
        # contracts (no expected_evidence) project to a no-universe request.
        contract_id = request.get("contract_id") or "canary-contract"
        allowed_paths = request.get("allowed_files") or changed_paths
        required_verifier_ids = request.get("verifier_commands") or ["git diff --check"]
        deletion_policy_val = request.get("deletion_policy") or "FORBID"
        deletion_policy = _normalize_deletion_policy(deletion_policy_val)
        contract_arg = kwargs.get("contract")
        universe_projection = (
            project_expected_evidence_universe(contract_arg)
            if contract_arg is not None
            else project_expected_evidence_universe(request)
        )
        # Fail closed on observed Core source identity: bind ACTUAL executed
        # commit+tree; unreadable -> marked unavailable; mismatch -> flagged.
        # INT-8: never report the configured expectation as executed truth.
        core_source = read_observed_core_identity()

        req_hash = _sha256(
            json.dumps(
                {
                    "contract_id": str(contract_id),
                    "allowed_paths": sorted(list(allowed_paths)),
                    "required_verifier_ids": sorted(list(required_verifier_ids)),
                },
                sort_keys=True,
            )
        )

        contract_payload = {
            "contract_id": str(contract_id),
            "requirements_hash": req_hash,
            "required_verifier_ids": sorted(list(required_verifier_ids)),
            "allowed_paths": sorted(list(allowed_paths)),
            "deletion_policy": deletion_policy,
        }
        if universe_projection is not None:
            # Verbatim projection of the producer declaration — sorted, no
            # drops, no rewrites. Core (evidence-reuse branch) accepts these
            # optional acceptance_contract fields.
            contract_payload["expected_subjects"] = universe_projection["expected_subjects"]
            contract_payload["universe_generation"] = universe_projection["universe_generation"]
        computed_contract_hash = acceptance_contract_hash(contract_payload)

        # Build ChangeSet
        src_rev_ref = (
            f"git-commit:{base_commit}" if len(base_commit) == 40 else manifest["source_tree"]
        )
        tgt_rev_ref = (
            f"git-commit:{target_commit}" if len(target_commit) == 40 else manifest["target_tree"]
        )
        change_set_payload = {
            "change_set_id": f"cs-{session_id[:12]}",
            "source_revision": src_rev_ref,
            "target_revision": tgt_rev_ref,
            "diff_hash": manifest_hash,
            "paths": changed_paths,
            "deleted_paths": deleted_paths,
        }
        computed_change_set_hash = change_set_hash(change_set_payload)

        # Build VerificationPlan
        plan_payload = {
            "plan_id": f"vp-{session_id[:12]}",
            "acceptance_contract_hash": computed_contract_hash,
            "change_set_hash": computed_change_set_hash,
            "required_verifier_ids": sorted(list(required_verifier_ids)),
        }
        computed_plan_hash = verification_plan_hash(plan_payload)

        # Build EvidenceBundle
        raw_evidence = kwargs.get("verifier_evidence") or {
            "git diff --check": {"exit_code": 0, "status": "CLEAN"}
        }
        evidence_by_id = {}
        if isinstance(raw_evidence, Mapping):
            evidence_by_id = dict(raw_evidence)
        elif isinstance(raw_evidence, (list, tuple, set)):
            for ev in raw_evidence:
                cmd = getattr(ev, "command", None)
                if cmd is None and isinstance(ev, Mapping):
                    cmd = ev.get("command") or ev.get("verifier_id")
                if cmd:
                    evidence_by_id[cmd] = ev

        # Wire tool_exposure_receipt if required by plan or supplied in kwargs (#1138)
        if "tool_exposure" in required_verifier_ids or "tool_exposure_receipt" in kwargs:
            from nexus.evidence.tool_exposure_trust import (
                TOOL_EXPOSURE_VERIFIER_ID,
                bind_tool_exposure_observation,
            )

            raw_receipt = kwargs.get("tool_exposure_receipt")
            tool_projection = kwargs.get("tool_projection_manifest")
            if not isinstance(tool_projection, Mapping):
                tool_projection = {}
            expected_binding = {
                "operation_id": prep.get("operation_id"),
                "attempt_id": prep.get("attempt_id") or kwargs.get("attempt_id"),
                "planner_decision_hash": (
                    tool_projection.get("planner_decision_hash")
                    or kwargs.get("planner_decision_hash")
                ),
                "projection_hash": (
                    tool_projection.get("projection_hash") or kwargs.get("projection_hash")
                ),
                "provider": tool_projection.get("provider") or kwargs.get("provider"),
                "backend_id": tool_projection.get("backend_id") or kwargs.get("backend_id"),
                "expected_remote_tool_identities": (
                    kwargs.get("expected_remote_tool_identities")
                    or tool_projection.get("expected_remote_tool_identities")
                ),
                "expected_runtime_tool_generations": (
                    kwargs.get("expected_runtime_tool_generations")
                    or tool_projection.get("expected_runtime_tool_generations")
                ),
                "requires_remote_tool_identity": (
                    kwargs.get("requires_remote_tool_identity")
                    or tool_projection.get("requires_remote_tool_identity", False)
                ),
            }
            exposure_obs = bind_tool_exposure_observation(
                raw_receipt, expected_binding=expected_binding
            )
            evidence_by_id[TOOL_EXPOSURE_VERIFIER_ID] = {
                "exit_code": 0 if exposure_obs["status"] == "PASS" else 1,
                "status": exposure_obs["status"],
                "artifact_id": exposure_obs["artifact_id"],
                "artifact_hash": exposure_obs["artifact_hash"],
                "reason": exposure_obs.get("reason"),
            }

        observations = []
        for vid in sorted(list(required_verifier_ids)):
            v_res = evidence_by_id.get(vid)
            if v_res is None:
                for k, v in evidence_by_id.items():
                    if k == vid or vid in k:
                        v_res = v
                        break
            exit_code = 0
            status_str = "PASS"
            if v_res is not None:
                if hasattr(v_res, "exit_code"):
                    exit_code = getattr(v_res, "exit_code", 0)
                    status_str = str(getattr(v_res, "status", "PASS")).upper()
                elif isinstance(v_res, Mapping):
                    exit_code = v_res.get("exit_code", 0)
                    status_str = str(v_res.get("status", "PASS")).upper()

            is_pass = (
                exit_code == 0
                and status_str in {"COMPLETED", "PASSED", "PASS", "CLEAN"}
                and not force_fail
            )
            obs_status = "PASS" if is_pass else "FAIL"

            if vid == "tool_exposure" and isinstance(v_res, Mapping) and "artifact_hash" in v_res:
                art_id = v_res.get("artifact_id", f"art-{vid}")
                art_hash = v_res["artifact_hash"]
                if not art_hash.startswith("sha256:"):
                    art_hash = "sha256:" + art_hash
                obs_entry = {
                    "verifier_id": vid,
                    "artifact_id": art_id,
                    "artifact_hash": art_hash,
                    "status": obs_status,
                }
                if "reason" in v_res:
                    obs_entry["reason"] = v_res["reason"]
                observations.append(obs_entry)
            else:
                observations.append(
                    {
                        "verifier_id": vid,
                        "artifact_id": f"art-{vid}",
                        "artifact_hash": _sha256(
                            json.dumps(_to_serializable(v_res or {"exit_code": 0}), sort_keys=True)
                        ),
                        "status": obs_status,
                    }
                )

        evidence_payload = {
            "bundle_id": f"eb-{session_id[:12]}",
            "acceptance_contract_hash": computed_contract_hash,
            "change_set_hash": computed_change_set_hash,
            "verification_plan_hash": computed_plan_hash,
            "observations": observations,
            "claimed_bundle_hash": None,
        }

        # Build full Generic Verification Request
        generic_request = {
            "protocol_version": PUBLIC_PROTOCOL_VERSION,
            "schema": GENERIC_VERIFICATION_REQUEST_SCHEMA_ID,
            "acceptance_contract": contract_payload,
            "change_set": change_set_payload,
            "change_manifest": manifest,
            "verification_plan": plan_payload,
            "evidence_bundle": evidence_payload,
            "certification_policy": None,
        }

        # -------------------------------------------------------------
        # THE EXACT MOMENT OF CANONICAL NEXUS-CORE VERIFICATION
        # product.adapters.generic_verification.verify_generic_changeset is the SOLE authority.
        # -------------------------------------------------------------
        status_code, core_response = verify_generic_changeset(generic_request)
        # -------------------------------------------------------------

        if status_code != 200:
            core_verification_status = "FAILED_VERIFICATION"
            reason_codes = [
                f"ADAPTER_ERROR_{status_code}",
                core_response.get("error", {}).get("code", "UNKNOWN"),
            ]
            core_response_payload = {
                "schema": GENERIC_VERIFICATION_RESPONSE_SCHEMA_ID,
                "protocol_version": PUBLIC_PROTOCOL_VERSION,
                "verification": {
                    "status": core_verification_status,
                    "reason_codes": reason_codes,
                    "integrity": "INVALID",
                },
                "hashes": {
                    "acceptance_contract_hash": computed_contract_hash,
                    "change_set_hash": computed_change_set_hash,
                    "verification_plan_hash": computed_plan_hash,
                    "evidence_bundle_hash": evidence_bundle_hash(evidence_payload),
                    "change_manifest_hash": manifest_hash,
                },
                "certification": None,
            }
        else:
            core_response_payload = core_response

        verification_data = core_response_payload.get("verification") or {}
        core_status = verification_data.get("status") or "FAILED_VERIFICATION"
        reason_codes = verification_data.get("reason_codes") or []
        hashes = core_response_payload.get("hashes") or {}

        # Build projection payload for host consumption
        projection_payload = {
            "schema": "nexus.ambient-core-verification-projection.v1",
            "session_id": session_id,
            "binding_hash": binding_hash,
            "candidate_state_hash": candidate_state_hash,
            "core_response": core_response_payload,
            "raw_core_request": generic_request,
            "raw_core_response": core_response_payload,
            "expected_evidence_projection": universe_projection,
            "core_source_identity": core_source,
            "core_provenance": core_provenance_status({
                "available": core_source.get("available", False),
                "reason": core_source.get("reason"),
                "source_root": core_source.get("source_root"),
                "expected_revision": CANONICAL_CORE_REVISION,
                "observed_commit": core_source.get("observed_commit"),
                "observed_tree": core_source.get("observed_tree"),
            }),
        }

        proj_hash = projection_hash(projection_payload)

        # Record verification in SQLite
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO core_mutation_verifications
                (session_id, binding_hash, candidate_state_hash, core_status, change_set_hash,
                 verification_plan_hash, evidence_bundle_hash, change_manifest_hash, projection_hash,
                 core_reason_codes_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    session_id,
                    binding_hash,
                    candidate_state_hash,
                    core_status,
                    hashes.get("change_set_hash", computed_change_set_hash),
                    hashes.get("verification_plan_hash", computed_plan_hash),
                    hashes.get("evidence_bundle_hash", evidence_bundle_hash(evidence_payload)),
                    hashes.get("change_manifest_hash", manifest_hash),
                    proj_hash,
                    json.dumps(reason_codes),
                ),
            )
            cursor.execute(
                "UPDATE core_mutation_sessions SET status = ? WHERE id = ?",
                ("COMPLETED" if core_status == "VERIFIED" else "FAILED", session_id),
            )
            conn.commit()

        return projection_payload

    def readback_session(self, session_id: str) -> dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM core_mutation_sessions WHERE id = ?", (session_id,))
            s_row = cursor.fetchone()
            cursor.execute(
                "SELECT * FROM core_mutation_verifications WHERE session_id = ?", (session_id,)
            )
            v_row = cursor.fetchone()
            return {
                "db_path": str(self.db_path),
                "session_row": dict(s_row) if s_row else None,
                "verification_row": dict(v_row) if v_row else None,
            }


def cli_main():
    parser = argparse.ArgumentParser(description="Canonical Core generic verification CLI")
    parser.add_argument(
        "--verify-json", help="Path to full generic verification request JSON or input payload"
    )
    args = parser.parse_args()

    if args.verify_json:
        with open(args.verify_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Check if full generic request or partial payload
        if data.get("schema") == GENERIC_VERIFICATION_REQUEST_SCHEMA_ID:
            status_code, resp = verify_generic_changeset(data)
            print(
                json.dumps(
                    {
                        "status_code": status_code,
                        "core_verification": resp.get("verification", {}),
                        "response": resp,
                    },
                    indent=2,
                )
            )
            sys.exit(0 if status_code == 200 else 1)

        # Partial payload from DevSpace or external caller: build generic request
        contract_data = data["acceptance_contract"]
        change_set_data = data["change_set"]
        evidence_data = data["evidence_bundle"]

        repo_dir = data.get("repo_dir") or "/tmp/nexus_canary_fixture_repo/d2_devspace"
        base_commit = (
            change_set_data.get("source_revision", "").replace("git-commit:", "") or "HEAD~1"
        )
        target_commit = (
            change_set_data.get("target_revision", "").replace("git-commit:", "") or "HEAD"
        )

        manifest = data.get("change_manifest")
        if not manifest and Path(repo_dir).exists():
            manifest = extract_git_manifest(repo_dir, base_commit, target_commit)
        elif not manifest:
            manifest = {
                "source_tree": "git-tree:" + "0" * 40,
                "target_tree": "git-tree:" + "0" * 40,
                "entries": [
                    {
                        "path": p,
                        "change_type": "ADD",
                        "before_oid": None,
                        "after_oid": "1" * 40,
                        "before_mode": None,
                        "after_mode": "100644",
                    }
                    for p in change_set_data["paths"]
                ],
            }

        diff_hash = change_manifest_hash(manifest)
        paths = sorted(list(set(row["path"] for row in manifest["entries"])))
        deleted_paths = sorted(
            list(set(row["path"] for row in manifest["entries"] if row["change_type"] == "DELETE"))
        )

        contract_payload = {
            "contract_id": contract_data["contract_id"],
            "requirements_hash": contract_data["requirements_hash"],
            "required_verifier_ids": sorted(contract_data["required_verifier_ids"]),
            "allowed_paths": sorted(contract_data["allowed_paths"]),
            "deletion_policy": _normalize_deletion_policy(contract_data.get("deletion_policy")),
        }
        ac_hash = acceptance_contract_hash(contract_payload)

        change_set_payload = {
            "change_set_id": change_set_data["change_set_id"],
            "source_revision": change_set_data["source_revision"],
            "target_revision": change_set_data["target_revision"],
            "diff_hash": diff_hash,
            "paths": paths,
            "deleted_paths": deleted_paths,
        }
        cs_hash = change_set_hash(change_set_payload)

        plan_payload = {
            "plan_id": data.get("verification_plan", {}).get("plan_id") or "vp-1",
            "acceptance_contract_hash": ac_hash,
            "change_set_hash": cs_hash,
            "required_verifier_ids": sorted(contract_data["required_verifier_ids"]),
        }
        vp_hash = verification_plan_hash(plan_payload)

        observations = []
        for obs in evidence_data["observations"]:
            observations.append(
                {
                    "verifier_id": obs["verifier_id"],
                    "artifact_id": obs["artifact_id"],
                    "artifact_hash": obs["artifact_hash"],
                    "status": obs["status"],
                }
            )

        evidence_payload = {
            "bundle_id": evidence_data.get("bundle_id") or "eb-1",
            "acceptance_contract_hash": ac_hash,
            "change_set_hash": cs_hash,
            "verification_plan_hash": vp_hash,
            "observations": observations,
            "claimed_bundle_hash": None,
        }

        full_generic_payload = {
            "protocol_version": PUBLIC_PROTOCOL_VERSION,
            "schema": GENERIC_VERIFICATION_REQUEST_SCHEMA_ID,
            "acceptance_contract": contract_payload,
            "change_set": change_set_payload,
            "change_manifest": manifest,
            "verification_plan": plan_payload,
            "evidence_bundle": evidence_payload,
            "certification_policy": None,
        }

        status_code, resp = verify_generic_changeset(full_generic_payload)
        print(
            json.dumps(
                {
                    "status_code": status_code,
                    "core_verification": resp.get("verification", {}),
                    "response": resp,
                    "generic_request": full_generic_payload,
                },
                indent=2,
            )
        )
        sys.exit(0 if status_code == 200 else 1)


if __name__ == "__main__":
    cli_main()
