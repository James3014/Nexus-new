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
import logging
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import types
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from nexus.orchestrator.ambient_core import (
    PREPARATION_SCHEMA,
    AmbientCoreControlPort,
    projection_hash,
)

_EXACT_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# `nexus-certify` is not a declared dependency of this package. Its identity is
# Core's own git-free `core_identity()` (#2246): an installed wheel carries an
# embedded build stamp; a checkout is pinned by its source digest, which the
# deployer supplies in NEXUS_CORE_SOURCE_DIGEST. A local Core checkout is placed ahead of any installed
# package only when explicitly configured via NEXUS_CORE_REPO_ROOT; no
# developer-machine path is hardcoded. The ACTUAL executed identity is always
# derived from the imported product module (see _resolve_core_source_root).
_configured_core_root = os.environ.get("NEXUS_CORE_REPO_ROOT", "").strip()
_core_repo_root: Path | None = None
if _configured_core_root:
    _core_repo_root = Path(_configured_core_root).expanduser().resolve()
    if str(_core_repo_root) not in sys.path:
        sys.path.insert(0, str(_core_repo_root))


def _core_shadow_reason(core_root: Path | None, module: Any) -> str | None:
    """Why ``module`` (a ``product`` package) is not the configured Core, or None.

    This repository ships its own top-level ``product/`` package. Once that one
    is in ``sys.modules``, ``import product...`` never reaches the configured
    Core checkout, so a configured root must own the imported package (#2181).
    """
    if core_root is None or module is None:
        return None
    module_file = getattr(module, "__file__", None)
    try:
        resolved = Path(str(module_file)).resolve() if module_file else None
    except Exception:
        resolved = None
    if resolved is not None and core_root in resolved.parents:
        return None
    return (
        f"CORE_PRODUCT_SHADOWED: product is imported from {module_file!r}, "
        f"outside NEXUS_CORE_REPO_ROOT {str(core_root)!r}"
    )


def _loaded_core_shadow_reason(core_root: Path | None) -> str | None:
    """First loaded ``product`` / ``product.*`` module that is not the configured Core."""
    for name, module in list(sys.modules.items()):
        if name == "product" or name.startswith("product."):
            reason = _core_shadow_reason(core_root, module)
            if reason:
                return f"{reason} (module {name})"
    return None


try:
    _shadowed = _loaded_core_shadow_reason(_core_repo_root)
    if _shadowed:
        raise ImportError(_shadowed)
    from product.adapters.generic_verification import verify_generic_changeset
    from product.protocol.generic_verification import (  # noqa: E402
        GENERIC_VERIFICATION_REQUEST_SCHEMA_ID,
        GENERIC_VERIFICATION_RESPONSE_SCHEMA_ID,
        acceptance_contract_hash,
        change_manifest_hash,
        change_set_hash,
        evidence_bundle_hash,
        expected_universe_identity,
        verification_plan_hash,
    )

    import product as _IMPORTED_CORE_PACKAGE  # noqa: E402
    from product.protocol import PUBLIC_PROTOCOL_VERSION  # noqa: E402

    _shadowed = _loaded_core_shadow_reason(_core_repo_root)
    if _shadowed:
        raise ImportError(_shadowed)
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
    expected_universe_identity = _unavailable_hash  # type: ignore[no-redef]

    def verify_generic_changeset(_payload: Any) -> tuple[int, dict[str, Any]]:  # type: ignore[misc]
        raise RuntimeError("CANONICAL_NEXUS_CORE_UNAVAILABLE: Cannot perform verification")

    _IMPORTED_CORE_PACKAGE = None  # type: ignore[assignment]


# Owner-decided expected canonical nexus-core revision (NN-1). Single source of
# truth for the runtime check; it must equal the nexus-certify SHA pinned in
# .github/workflows/nexus-core-issue-completion.yml (a test asserts the two
# agree).
# scripts/ops/nexus_gateway_auto_deploy.py text-parses this exact one-line
# `CANONICAL_CORE_REVISION = "<40-hex sha>"` form (it never imports this file);
# keep that shape when bumping the pin.
CANONICAL_CORE_REVISION = "b07ae36d64501af761e8f2069830b79f89ac733b"
CANONICAL_CORE_DISTRIBUTION = "nexus-certify"
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


# Git-free Core identity (#2246, nexus-core #267/#270). The deployer computes
# the expected source digest of the pinned checkout and exports it with the
# revision it was computed from; an installed wheel instead carries Core's
# embedded build stamp.
CORE_SOURCE_DIGEST_ENV = "NEXUS_CORE_SOURCE_DIGEST"
CORE_SOURCE_DIGEST_REVISION_ENV = "NEXUS_CORE_SOURCE_DIGEST_REVISION"
CORE_BUILD_IDENTITY_RELPATH = ("product", "protocol", "build_identity.py")
_CORE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_BUILD_EMBEDDED = "EMBEDDED"
_BUILD_UNSTAMPED = "UNSTAMPED"
_BUILD_INVALID = "INVALID_STAMP"
# Identity fields carried from read_observed_core_identity into the status.
_IDENTITY_DETAIL_FIELDS = (
    "identity_source",
    "build_identity",
    "observed_source_digest",
    "expected_source_digest",
)


def _load_core_identity_function(root: Path) -> Any:
    """Core's ``core_identity`` from ``root``'s own ``product/protocol/build_identity.py``.

    ``build_identity`` is a leaf module (it imports nothing from ``product``);
    ``product.protocol.core_identity`` re-exports it. It is compiled from the
    file at ``root`` and executed in a private module, so the identity is
    always computed by the Core that lives at the observed root, whatever
    ``product`` won ``sys.modules``, and no bytecode is written into the
    checkout.
    """
    path = root.joinpath(*CORE_BUILD_IDENTITY_RELPATH)
    source = path.read_bytes()
    module = types.ModuleType("_nexus_core_build_identity")
    module.__file__ = str(path)
    exec(compile(source, str(path), "exec"), module.__dict__)  # noqa: S102  # nosec B102 - the imported Core
    function = module.__dict__.get("core_identity")
    if not callable(function):
        raise RuntimeError("core_identity missing")
    return function


def _expected_source_digest() -> tuple[str | None, str | None, str | None]:
    """``(digest, revision, problem)`` the deployer pinned for a Core checkout."""
    digest = os.environ.get(CORE_SOURCE_DIGEST_ENV, "")
    revision = os.environ.get(CORE_SOURCE_DIGEST_REVISION_ENV, "")
    if not digest and not revision:
        return None, None, "CORE_SOURCE_DIGEST_UNPINNED"
    if not _CORE_DIGEST_RE.fullmatch(digest) or not _EXACT_GIT_SHA_RE.fullmatch(revision):
        return None, None, "CORE_SOURCE_DIGEST_PIN_MALFORMED"
    return digest, revision, None


def read_observed_core_identity(core_root: Path | None = None) -> dict[str, Any]:
    """Bind ACTUAL executed Core identity (INT-8 provenance), without git.

    Uses Core's own ``core_identity()`` for the observed Core root (the
    imported package's root, or an explicit ``core_root``). Host rule, as the
    ``core_identity`` docstring prescribes:

    - ``EMBEDDED`` (installed wheel): the stamp's ``git_commit`` is the
      observed commit, and only when ``git_dirty is False`` and
      ``source_matches_build is True``. When the deployer pinned a digest the
      stamp is ignored and the checkout rule below applies.
    - ``UNSTAMPED`` (checkout): ``source_digest`` must equal the digest the
      deployer computed for ``CANONICAL_CORE_REVISION`` and exported as
      ``NEXUS_CORE_SOURCE_DIGEST`` / ``NEXUS_CORE_SOURCE_DIGEST_REVISION``.
      Missing or malformed pin: unavailable. Different digest: the executed
      Core is not the pinned one (no observed commit).
    - ``INVALID_STAMP``: unavailable.

    Bytecode never enters the digest, so a stray ``__pycache__`` does not
    change provenance (2026-10-15). Unreadable identity returns
    available=False explicitly; callers fail closed and never substitute
    expected == observed.
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
    base["source_root"] = str(root)
    try:
        identity = _load_core_identity_function(root)(root / "product")
    except (Exception, SystemExit):  # Core code: never let it end the Gateway
        return {**base, "reason": "CORE_IDENTITY_UNREADABLE"}
    if not isinstance(identity, Mapping):
        return {**base, "reason": "CORE_IDENTITY_MALFORMED"}
    state = identity.get("build_identity")
    observed_digest = identity.get("source_digest")
    if not isinstance(observed_digest, str) or not _CORE_DIGEST_RE.fullmatch(observed_digest):
        return {**base, "reason": "CORE_IDENTITY_MALFORMED", "build_identity": state}
    base.update(build_identity=state, observed_source_digest=observed_digest)
    if state == _BUILD_INVALID:
        return {**base, "reason": "CORE_BUILD_STAMP_INVALID"}
    # A deployer that pinned a digest declared a checkout: the digest decides,
    # and a build stamp found there (which is outside the digest) never does.
    digest_pinned = bool(
        os.environ.get(CORE_SOURCE_DIGEST_ENV) or os.environ.get(CORE_SOURCE_DIGEST_REVISION_ENV)
    )
    if state == _BUILD_EMBEDDED and not digest_pinned:
        commit, tree = identity.get("git_commit"), identity.get("git_tree")
        if not isinstance(commit, str) or not _EXACT_GIT_SHA_RE.fullmatch(commit):
            return {**base, "reason": "CORE_BUILD_STAMP_WITHOUT_COMMIT"}
        if identity.get("git_dirty") is not False:
            return {**base, "reason": "CORE_BUILD_DIRTY"}
        if identity.get("source_matches_build") is not True:
            return {**base, "reason": "CORE_SOURCE_NOT_AS_BUILT"}
        return {
            **base,
            "available": True,
            "identity_source": "build_stamp",
            "observed_commit": commit,
            "observed_tree": tree if isinstance(tree, str) else None,
            "revision_match": commit == CANONICAL_CORE_REVISION,
        }
    if state in (_BUILD_UNSTAMPED, _BUILD_EMBEDDED):
        expected, revision, problem = _expected_source_digest()
        if problem is not None:
            return {**base, "reason": problem}
        if revision != CANONICAL_CORE_REVISION:
            return {
                **base,
                "reason": "CORE_SOURCE_DIGEST_PIN_FOR_OTHER_REVISION",
                "expected_source_digest": expected,
            }
        matched = observed_digest == expected
        return {
            **base,
            "available": True,
            "identity_source": "source_digest",
            "expected_source_digest": expected,
            # Only a matching digest attests the pinned revision.
            "observed_commit": revision if matched else None,
            "revision_match": matched,
            **({} if matched else {"reason": "CORE_SOURCE_DIGEST_MISMATCH"}),
        }
    return {**base, "reason": "CORE_IDENTITY_MALFORMED"}


def _provenance_from_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    details = {k: identity.get(k) for k in _IDENTITY_DETAIL_FIELDS if k in identity}
    if not identity.get("available"):
        return {
            "status": "CORE_IDENTITY_UNAVAILABLE",
            "fail_closed": True,
            "reason": identity.get("reason", "CORE_IDENTITY_UNREADABLE"),
            "expected_revision": CANONICAL_CORE_REVISION,
            "observed_commit": None,
            "observed_tree": None,
            "source_root": identity.get("source_root"),
            **details,
        }
    if identity.get("observed_commit") != CANONICAL_CORE_REVISION:
        return {
            "status": "CORE_REVISION_MISMATCH",
            "fail_closed": True,
            "reason": identity.get("reason")
            or "INT-8: executed Core differs from configured expectation",
            "expected_revision": CANONICAL_CORE_REVISION,
            "observed_commit": identity.get("observed_commit"),
            "observed_tree": identity.get("observed_tree"),
            "source_root": identity.get("source_root"),
            **details,
        }
    return {
        "status": "CORE_REVISION_PINNED",
        "fail_closed": False,
        "expected_revision": CANONICAL_CORE_REVISION,
        "observed_commit": identity.get("observed_commit"),
        "observed_tree": identity.get("observed_tree"),
        "source_root": identity.get("source_root"),
        **details,
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
        return _provenance_from_identity(dict(observed))
    if not CORE_AVAILABLE:
        return {
            "status": "CORE_UNAVAILABLE",
            "fail_closed": True,
            "reason": CORE_IMPORT_ERROR,
            "expected_revision": CANONICAL_CORE_REVISION,
            "observed_commit": None,
            "observed_tree": None,
        }
    return _provenance_from_identity(read_observed_core_identity())


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

        entries.append({
            "path": path,
            "change_type": change_type,
            "before_oid": before_oid,
            "after_oid": after_oid,
            "before_mode": before_mode,
            "after_mode": after_mode,
        })
    return {
        "source_tree": f"git-tree:{src_tree}",
        "target_tree": f"git-tree:{tgt_tree}",
        "entries": entries,
    }


def _exact_sha(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if _EXACT_GIT_SHA_RE.fullmatch(text) and text != "0" * 40 else None


def _acceptance_contract_payload(
    contract: Any, request: Mapping[str, Any], *, fallback_contract_id: str | None = None
) -> dict[str, Any]:
    """One Core acceptance contract for both binding and verification.

    Every field comes from the bound task contract (or, for a contract-less
    caller, its request). Missing identity, scope or verifier set fails
    closed; nothing is defaulted (#2181).
    """
    contract_id = (
        getattr(contract, "contract_id", None)
        or getattr(contract, "task_id", None)
        or request.get("contract_id")
        or request.get("task_id")
        or fallback_contract_id
    )
    if not contract_id:
        raise RuntimeError("CANONICAL_CORE_CONTRACT_IDENTITY_MISSING")
    allowed_paths = sorted(
        set(
            getattr(contract, "allowed_paths", None)
            or getattr(contract, "allowed_files", None)
            or request.get("allowed_files")
            or ()
        )
    )
    if not allowed_paths:
        raise RuntimeError("CANONICAL_CORE_ALLOWED_PATHS_MISSING")
    required_verifier_ids = sorted(
        set(
            getattr(contract, "required_verifier_ids", None)
            or getattr(contract, "verifier_commands", None)
            or request.get("verifier_commands")
            or ()
        )
    )
    if not required_verifier_ids:
        raise RuntimeError("CANONICAL_CORE_VERIFIERS_MISSING")
    deletion_policy = _normalize_deletion_policy(
        getattr(contract, "deletion_policy", None) or request.get("deletion_policy") or "FORBID"
    )
    requirements_hash = _sha256(
        json.dumps(
            {
                "contract_id": str(contract_id),
                "allowed_paths": allowed_paths,
                "required_verifier_ids": required_verifier_ids,
            },
            sort_keys=True,
        )
    )
    payload: dict[str, Any] = {
        "contract_id": str(contract_id),
        "requirements_hash": requirements_hash,
        "required_verifier_ids": required_verifier_ids,
        "allowed_paths": allowed_paths,
        "deletion_policy": deletion_policy,
    }
    universe = (
        project_expected_evidence_universe(contract)
        if contract is not None
        else project_expected_evidence_universe(request)
    )
    if universe is not None:
        # Verbatim projection of the producer declaration: sorted, no drops,
        # no rewrites.
        payload["expected_subjects"] = universe["expected_subjects"]
        payload["universe_generation"] = universe["universe_generation"]
    return payload


# #2776: one row per Core verification, never one row per session. A crash
# resume of the same attempt (``RESUME_CANDIDATE_VERIFICATION``) re-verifies
# the persisted session, so a later verdict must not erase an earlier one.
_MIGRATE_PRE2776_ROWS_SQL = """
    INSERT INTO core_mutation_verifications
    (session_id, binding_hash, candidate_state_hash, core_status, change_set_hash,
     verification_plan_hash, evidence_bundle_hash, change_manifest_hash, projection_hash,
     core_reason_codes_json, verified_at)
    SELECT session_id, binding_hash, candidate_state_hash, core_status, change_set_hash,
     verification_plan_hash, evidence_bundle_hash, change_manifest_hash, projection_hash,
     core_reason_codes_json, verified_at
    FROM core_mutation_verifications_pre2776
    WHERE session_id IS NOT NULL
    ORDER BY verified_at, rowid
"""
# A pre-#2776 row with a NULL ``session_id`` (the old ``TEXT PRIMARY KEY`` allowed it)
# cannot enter the NOT NULL table. It is moved here, with the same columns, instead of
# failing the migration (which would leave the database unopenable) or being dropped.
_QUARANTINE_PRE2776_TABLE = "core_mutation_verifications_quarantine_pre2776"
_QUARANTINE_PRE2776_DDL = """
    CREATE TABLE IF NOT EXISTS core_mutation_verifications_quarantine_pre2776 (
        session_id TEXT,
        binding_hash TEXT,
        candidate_state_hash TEXT,
        core_status TEXT,
        change_set_hash TEXT,
        verification_plan_hash TEXT,
        evidence_bundle_hash TEXT,
        change_manifest_hash TEXT,
        projection_hash TEXT,
        core_reason_codes_json TEXT,
        verified_at TIMESTAMP
    )
"""
_QUARANTINE_PRE2776_ROWS_SQL = """
    INSERT INTO core_mutation_verifications_quarantine_pre2776
    (session_id, binding_hash, candidate_state_hash, core_status, change_set_hash,
     verification_plan_hash, evidence_bundle_hash, change_manifest_hash, projection_hash,
     core_reason_codes_json, verified_at)
    SELECT session_id, binding_hash, candidate_state_hash, core_status, change_set_hash,
     verification_plan_hash, evidence_bundle_hash, change_manifest_hash, projection_hash,
     core_reason_codes_json, verified_at
    FROM core_mutation_verifications_pre2776
    WHERE session_id IS NULL
    ORDER BY verified_at, rowid
"""
_LOG = logging.getLogger(__name__)
_APPEND_ONLY_TRIGGERS_SQL = (
    """
    CREATE TRIGGER IF NOT EXISTS core_mutation_verifications_no_update
    BEFORE UPDATE ON core_mutation_verifications BEGIN
    SELECT RAISE(ABORT, 'CORE_MUTATION_VERIFICATION_APPEND_ONLY'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS core_mutation_verifications_no_delete
    BEFORE DELETE ON core_mutation_verifications BEGIN
    SELECT RAISE(ABORT, 'CORE_MUTATION_VERIFICATION_APPEND_ONLY'); END
    """,
)
_VERIFICATIONS_DDL = """
    CREATE TABLE IF NOT EXISTS core_mutation_verifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
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
"""


def _ensure_append_only_verifications(conn: sqlite3.Connection) -> int:
    """Create or migrate ``core_mutation_verifications`` to append-only (#2776).

    A database created before #2776 keyed the table by ``session_id``. Its
    rows are copied, in order, into the new table inside one IMMEDIATE
    transaction, so a concurrent opener sees either the old or the new table.
    Rows with a NULL ``session_id`` are moved to
    ``core_mutation_verifications_quarantine_pre2776`` instead (never dropped).

    Returns the number of rows quarantined by this call (0 when nothing migrated).
    """
    quarantined = 0
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(core_mutation_verifications)")]
        if columns and "id" not in columns:
            conn.execute(
                "ALTER TABLE core_mutation_verifications "
                "RENAME TO core_mutation_verifications_pre2776"
            )
            conn.execute(_VERIFICATIONS_DDL)
            conn.execute(_MIGRATE_PRE2776_ROWS_SQL)
            quarantined = conn.execute(
                "SELECT COUNT(*) FROM core_mutation_verifications_pre2776 WHERE session_id IS NULL"
            ).fetchone()[0]
            if quarantined:
                conn.execute(_QUARANTINE_PRE2776_DDL)
                conn.execute(_QUARANTINE_PRE2776_ROWS_SQL)
            conn.execute("DROP TABLE core_mutation_verifications_pre2776")
        conn.execute(_VERIFICATIONS_DDL)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_core_mutation_verifications_session "
            "ON core_mutation_verifications(session_id, id)"
        )
        for trigger_sql in _APPEND_ONLY_TRIGGERS_SQL:
            conn.execute(trigger_sql)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    if quarantined:
        _LOG.warning(
            "core_mutation_verifications migration (#2776): %d row(s) with NULL session_id "
            "moved to %s",
            quarantined,
            _QUARANTINE_PRE2776_TABLE,
        )
    return quarantined


class CanonicalNexusCoreTransportPort(AmbientCoreControlPort):
    """
    Host transport boundary that delegates Candidate verification
    directly to canonical product.adapters.generic_verification.verify_generic_changeset
    at the pinned CANONICAL_CORE_REVISION.
    It does NOT evaluate verifiers or manufacture VERIFIED: missing evidence is
    sent to Core as missing, never as a synthetic PASS.
    """

    def __init__(
        self,
        db_path: str | Path,
        simulate_core_unavailable: bool = False,
    ):
        # The session DB lives under the caller's state root. There is no
        # shared /tmp default (#2181); it is created on first use.
        self.db_path = Path(db_path)
        self.simulate_core_unavailable = simulate_core_unavailable
        self._db_ready = False
        # Rows with a NULL session_id quarantined when this port migrated a pre-#2776 DB.
        self.pre2776_quarantined_rows = 0

    def _ensure_db(self) -> None:
        if self._db_ready:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._db_ready = True

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
            self.pre2776_quarantined_rows = _ensure_append_only_verifications(conn)
            # #2346: a declared-universe task that ended without a Candidate.
            # One row per (task, attempt); additive, so existing rows and
            # readers are unchanged.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS core_terminal_records (
                    task_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    terminal_status TEXT NOT NULL,
                    core_status TEXT NOT NULL,
                    integrity TEXT NOT NULL,
                    core_reason_codes_json TEXT NOT NULL,
                    acceptance_contract_hash TEXT NOT NULL,
                    universe_identity TEXT NOT NULL,
                    universe_generation INTEGER NOT NULL,
                    coverage_json TEXT NOT NULL,
                    core_provenance_status TEXT NOT NULL,
                    projection_hash TEXT NOT NULL,
                    projection_json TEXT NOT NULL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (task_id, attempt_id)
                )
            """)
            conn.commit()

    def record_terminal_not_covered(self, **kwargs: Any) -> Mapping[str, Any]:
        """Certify a declared-universe task that ended with no Candidate (#2346).

        Nothing was produced, so there is no change set and there are no
        observations: the pinned Core's public wire request requires both, so
        it cannot be used here. Core's own coverage reconciliation
        (``derive_coverage``) runs over the declared universe and the
        observations that exist (none), and Core's reducer turns that into a
        result for the "candidate missing" condition, as Core's change-set
        certification adapter does for a missing candidate. Every REQUIRED
        subject is therefore NOT_COVERED with UNVERIFIABLE + MISSING. The host
        authors no category, status or identity.

        The record is never a pass: it carries no change set, no candidate
        and no commit permission. Raises on any Core failure; the caller
        records the failure instead.
        """
        if self.simulate_core_unavailable or not CORE_AVAILABLE:
            raise RuntimeError("CANONICAL_NEXUS_CORE_UNAVAILABLE: Cannot record terminal coverage")
        task_id = str(kwargs.get("task_id") or "").strip()
        attempt_id = str(kwargs.get("attempt_id") or "").strip()
        terminal_status = str(kwargs.get("terminal_status") or "").strip()
        if not task_id or not attempt_id or not terminal_status:
            raise RuntimeError("CANONICAL_CORE_ATTEMPT_IDENTITY_MISSING")
        request = kwargs.get("request") or {}
        contract_payload = _acceptance_contract_payload(
            kwargs.get("contract"), request, fallback_contract_id=task_id
        )
        if "expected_subjects" not in contract_payload:
            # Legacy (no-universe) tasks are never recorded.
            raise RuntimeError("CORE_TERMINAL_RECORD_UNIVERSE_MISSING")
        # Resolved at run time from the configured Core: the in-tree
        # ``product`` package that static analysis sees is not Core.
        try:
            import importlib

            core_evidence: Any = importlib.import_module("product.evidence")
            core_verification: Any = importlib.import_module("product.verification")
            Applicability = core_evidence.Applicability
            ExpectedEvidenceSubject = core_evidence.ExpectedEvidenceSubject
            IntegrityStatus = core_evidence.IntegrityStatus
            RequirementMode = core_evidence.RequirementMode
            derive_coverage = core_verification.derive_coverage
            reduce_verification = core_verification.reduce_verification
        except (ImportError, AttributeError) as exc:
            raise RuntimeError(f"CANONICAL_NEXUS_CORE_UNAVAILABLE: {exc}") from exc
        shadowed = _loaded_core_shadow_reason(_core_repo_root)
        if shadowed:
            raise RuntimeError(f"CANONICAL_NEXUS_CORE_UNAVAILABLE: {shadowed}")

        universe_identity = expected_universe_identity(contract_payload)
        subjects = tuple(
            ExpectedEvidenceSubject(
                subject["logical_subject_id"],
                subject["evidence_kind"],
                RequirementMode(subject["requirement_mode"]),
                Applicability(subject["applicability"]),
            )
            for subject in contract_payload["expected_subjects"]
        )
        # No Candidate means no verifier ran: the observations are empty.
        coverage = derive_coverage(
            subjects,
            (),
            universe_generation=contract_payload["universe_generation"],
            universe_identity=universe_identity,
        )
        reasons = {"MISSING", "CANDIDATE_MISSING"}
        if coverage.unresolved:
            reasons.add("COVERAGE_UNRESOLVED")
        result = reduce_verification(
            IntegrityStatus.MISSING, reasons=tuple(sorted(reasons)), coverage=coverage
        )
        if result.status.value == "VERIFIED":  # unreachable by Core's invariants
            raise RuntimeError("CORE_TERMINAL_RECORD_UNEXPECTED_VERIFIED")
        contract_hash = acceptance_contract_hash(contract_payload)
        verification = {
            "status": result.status.value,
            "reason_codes": list(result.reason_codes),
            "integrity": result.integrity.value,
            "coverage": coverage.to_dict(),
        }
        core_source = read_observed_core_identity()
        provenance = core_provenance_status(dict(core_source))
        projection_payload = {
            "schema": "nexus.ambient-core-terminal-record.v1",
            "task_id": task_id,
            "attempt_id": attempt_id,
            "terminal_status": terminal_status,
            # Not Core's public wire: no change set exists to send over it.
            "core_entrypoint": "product.verification.derive_coverage+reduce_verification",
            "core_response": {
                "schema": GENERIC_VERIFICATION_RESPONSE_SCHEMA_ID,
                "protocol_version": PUBLIC_PROTOCOL_VERSION,
                "verification": verification,
                "hashes": {
                    "acceptance_contract_hash": contract_hash,
                    "universe_identity": universe_identity,
                },
                "certification": None,
            },
            "raw_core_request": {"acceptance_contract": contract_payload, "observations": []},
            "expected_evidence_projection": {
                "expected_subjects": contract_payload["expected_subjects"],
                "universe_generation": contract_payload["universe_generation"],
            },
            "core_source_identity": core_source,
            "core_provenance": provenance,
        }
        if provenance.get("status") != "CORE_REVISION_PINNED":
            # Only a pinned Core may write the durable record; the host
            # records this as a failure and may record again once Core is fixed.
            raise RuntimeError(
                f"CORE_PROVENANCE_NOT_PINNED:{provenance.get('status') or 'MISSING'}"
            )
        proj_hash = projection_hash(projection_payload)
        projection_json = json.dumps(projection_payload, sort_keys=True, default=str)

        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO core_terminal_records
                (task_id, attempt_id, terminal_status, core_status, integrity,
                 core_reason_codes_json, acceptance_contract_hash, universe_identity,
                 universe_generation, coverage_json, core_provenance_status, projection_hash,
                 projection_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    task_id,
                    attempt_id,
                    terminal_status,
                    verification["status"],
                    verification["integrity"],
                    json.dumps(verification["reason_codes"]),
                    contract_hash,
                    str(universe_identity),
                    int(contract_payload["universe_generation"]),
                    json.dumps(verification["coverage"], sort_keys=True),
                    str(provenance.get("status") or ""),
                    proj_hash,
                    projection_json,
                ),
            )
            conn.commit()
            cursor.execute(
                "SELECT universe_identity, acceptance_contract_hash, projection_hash,"
                " projection_json FROM core_terminal_records"
                " WHERE task_id = ? AND attempt_id = ?",
                (task_id, attempt_id),
            )
            row = cursor.fetchone()
        # One durable record per attempt: a replay returns exactly the stored
        # record, which must describe the same contract and universe.
        if row is None or (row[0], row[1]) != (str(universe_identity), contract_hash):
            raise RuntimeError("CORE_TERMINAL_RECORD_CONFLICT")
        stored = json.loads(row[3])
        if projection_hash(stored) != row[2]:
            raise RuntimeError("CORE_TERMINAL_RECORD_TAMPERED")
        return stored

    def readback_terminal_record(self, task_id: str, attempt_id: str) -> dict[str, Any] | None:
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM core_terminal_records WHERE task_id = ? AND attempt_id = ?",
                (task_id, attempt_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def open_or_reuse_mutation_binding(self, **kwargs: Any) -> Mapping[str, Any]:
        request = kwargs.get("request") or {}
        contract_arg = kwargs.get("contract")
        task_id = (
            kwargs.get("task_id")
            or getattr(contract_arg, "task_id", None)
            or request.get("task_id")
        )
        attempt_id = kwargs.get("attempt_id") or request.get("attempt_id")
        if not task_id or not attempt_id:
            raise RuntimeError("CANONICAL_CORE_ATTEMPT_IDENTITY_MISSING")

        lane = request.get("execution_lane") or "GOVERNED"

        base_sha = _exact_sha(
            kwargs.get("base_sha")
            or request.get("controller_revision")
            or getattr(contract_arg, "controller_revision", None)
        )
        if base_sha is None:
            raise RuntimeError("CANONICAL_CORE_SOURCE_REVISION_MISSING")
        base_tree = _exact_sha(kwargs.get("base_tree"))
        if base_tree is None:
            repo_root = (
                request.get("controller_repo_root")
                or getattr(contract_arg, "controller_repo_root", None)
                or kwargs.get("repo_root")
            )
            try:
                base_tree = (
                    _exact_sha(
                        subprocess.check_output(
                            ["git", "rev-parse", f"{base_sha}^{{tree}}"],
                            cwd=str(repo_root),
                            text=True,
                            stderr=subprocess.DEVNULL,
                            timeout=10,
                        ).strip()
                    )
                    if repo_root
                    else None
                )
            except (OSError, subprocess.SubprocessError):
                base_tree = None
        if base_tree is None:
            raise RuntimeError("CANONICAL_CORE_SOURCE_TREE_UNRESOLVED")

        session_id = f"cms_{uuid.uuid4().hex}"
        operation_id = kwargs.get("operation_id") or f"op-{uuid.uuid4().hex[:12]}"
        binding_id = f"binding-{uuid.uuid4().hex[:12]}"

        contract_payload = _acceptance_contract_payload(
            contract_arg, request, fallback_contract_id=str(task_id)
        )
        if CORE_AVAILABLE:
            contract_hash = acceptance_contract_hash(contract_payload)
        else:
            contract_hash = _sha256(json.dumps(contract_payload, sort_keys=True))

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

        # Record session in SQLite
        self._ensure_db()
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
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM core_mutation_sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                raise RuntimeError(f"CANONICAL_CORE_SESSION_NOT_FOUND: {session_id}")

    def verify_candidate(self, **kwargs: Any) -> Mapping[str, Any]:
        """
        Pure transport: passes candidate evidence directly to canonical
        product.adapters.generic_verification.verify_generic_changeset.
        Never fabricates VERIFIED and never invents evidence or a change set.
        """
        if self.simulate_core_unavailable or not CORE_AVAILABLE:
            raise RuntimeError("CANONICAL_NEXUS_CORE_UNAVAILABLE: Cannot perform verification")

        prep = kwargs.get("preparation") or {}
        candidate = kwargs.get("candidate")
        request = kwargs.get("request") or {}
        session_id = prep.get("session_id")
        binding_hash = prep.get("binding_hash")
        if not session_id or not binding_hash:
            raise RuntimeError("CANONICAL_CORE_PREPARATION_MISSING")

        candidate_state_hash = None
        if candidate is not None:
            candidate_state_hash = getattr(candidate, "candidate_state_hash", None)
            if candidate_state_hash is None and isinstance(candidate, Mapping):
                candidate_state_hash = candidate.get("candidate_state_hash")
        if candidate_state_hash is None:
            candidate_state_hash = kwargs.get("candidate_state_hash")
        if not candidate_state_hash:
            raise RuntimeError("CANONICAL_CORE_CANDIDATE_STATE_MISSING")

        base_commit = _exact_sha(str(prep.get("source_revision") or "").replace("git-commit:", ""))
        target_commit = "HEAD"
        if (
            candidate is not None
            and hasattr(candidate, "candidate_commit_sha")
            and candidate.candidate_commit_sha
        ):
            target_commit = candidate.candidate_commit_sha

        # The change manifest is derived from the candidate's own worktree.
        # An explicit manifest is accepted only from an in-process caller; a
        # missing worktree or base revision fails closed (#2181).
        if "change_manifest" in kwargs:
            manifest = kwargs["change_manifest"]
        else:
            lease = kwargs.get("lease")
            repo_dir = (
                getattr(lease, "target_worktree", None)
                or request.get("target_repo_root")
                or kwargs.get("repo_dir")
            )
            if not repo_dir or not Path(str(repo_dir)).is_dir():
                raise RuntimeError("CANONICAL_CORE_CANDIDATE_WORKTREE_MISSING")
            if base_commit is None:
                raise RuntimeError("CANONICAL_CORE_SOURCE_REVISION_MISSING")
            manifest = extract_git_manifest(str(repo_dir), base_commit, target_commit)
        if base_commit is None:
            base_commit = ""

        manifest_entries = manifest["entries"]
        changed_paths = sorted(list(set(row["path"] for row in manifest_entries)))
        deleted_paths = sorted(
            list(set(row["path"] for row in manifest_entries if row["change_type"] == "DELETE"))
        )

        manifest_hash = change_manifest_hash(manifest)

        contract_arg = kwargs.get("contract")
        contract_payload = _acceptance_contract_payload(contract_arg, request)
        required_verifier_ids = contract_payload["required_verifier_ids"]
        universe_projection = (
            {
                "expected_subjects": contract_payload["expected_subjects"],
                "universe_generation": contract_payload["universe_generation"],
            }
            if "expected_subjects" in contract_payload
            else None
        )
        # Fail closed on observed Core source identity: bind ACTUAL executed
        # commit+tree; unreadable -> marked unavailable; mismatch -> flagged.
        # INT-8: never report the configured expectation as executed truth.
        core_source = read_observed_core_identity()
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
            "required_verifier_ids": list(required_verifier_ids),
        }
        computed_plan_hash = verification_plan_hash(plan_payload)

        # Build EvidenceBundle from the evidence actually produced. Absent
        # evidence stays absent, so Core reports it as MISSING.
        raw_evidence = kwargs.get("verifier_evidence") or ()
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

        # A verifier observation carries a logical subject only when the
        # declared universe names that exact verifier id (the contract's
        # verifier coupling rule). Namespaced subjects need their own producer.
        subject_kinds = {
            str(subject.get("logical_subject_id")): str(subject.get("evidence_kind"))
            for subject in (universe_projection or {}).get("expected_subjects") or ()
        }

        observations = []
        for vid in required_verifier_ids:
            v_res = evidence_by_id.get(vid)
            if v_res is None:
                continue
            exit_code = None
            status_str = ""
            if hasattr(v_res, "exit_code"):
                exit_code = getattr(v_res, "exit_code", None)
                status_str = str(getattr(v_res, "status", "")).upper()
            elif isinstance(v_res, Mapping):
                exit_code = v_res.get("exit_code")
                status_str = str(v_res.get("status", "")).upper()

            is_pass = exit_code == 0 and status_str in {"COMPLETED", "PASSED", "PASS", "CLEAN"}
            obs_status = "PASS" if is_pass else "FAIL"

            if vid == "tool_exposure" and isinstance(v_res, Mapping) and "artifact_hash" in v_res:
                art_id = v_res.get("artifact_id", f"art-{vid}")
                art_hash = v_res["artifact_hash"]
                if not art_hash.startswith("sha256:"):
                    art_hash = "sha256:" + art_hash
                observation = {
                    "verifier_id": vid,
                    "artifact_id": art_id,
                    "artifact_hash": art_hash,
                    "status": obs_status,
                }
                if v_res.get("reason") is not None:
                    observation["reason"] = v_res["reason"]
            else:
                observation = {
                    "verifier_id": vid,
                    "artifact_id": f"art-{vid}",
                    "artifact_hash": _sha256(json.dumps(_to_serializable(v_res), sort_keys=True)),
                    "status": obs_status,
                }
            if vid in subject_kinds:
                observation["logical_subject_id"] = vid
                observation["evidence_kind"] = subject_kinds[vid]
            observations.append(observation)

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
            "core_provenance": core_provenance_status(dict(core_source)),
        }

        proj_hash = projection_hash(projection_payload)

        # Record verification in SQLite
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO core_mutation_verifications
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
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM core_mutation_sessions WHERE id = ?", (session_id,))
            s_row = cursor.fetchone()
            cursor.execute(
                "SELECT * FROM core_mutation_verifications WHERE session_id = ? ORDER BY id",
                (session_id,),
            )
            history = [dict(row) for row in cursor.fetchall()]
            # ``verification_row`` stays the latest verdict; earlier verdicts
            # for the same session are kept beside it, never dropped (#2776).
            return {
                "db_path": str(self.db_path),
                "session_row": dict(s_row) if s_row else None,
                "verification_row": history[-1] if history else None,
                "verification_count": len(history),
                "verification_history": history,
                "prior_core_statuses": [row["core_status"] for row in history[:-1]],
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

        repo_dir = data.get("repo_dir") or ""
        base_commit = (
            change_set_data.get("source_revision", "").replace("git-commit:", "") or "HEAD~1"
        )
        target_commit = (
            change_set_data.get("target_revision", "").replace("git-commit:", "") or "HEAD"
        )

        manifest = data.get("change_manifest")
        if not manifest and repo_dir and Path(repo_dir).exists():
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
            observations.append({
                "verifier_id": obs["verifier_id"],
                "artifact_id": obs["artifact_id"],
                "artifact_hash": obs["artifact_hash"],
                "status": obs["status"],
            })

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
