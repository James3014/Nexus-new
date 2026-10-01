#!/usr/bin/env python3
"""Validate nexus.candidate_acceptance.v4 with explicit executor/verification evidence unions."""
from __future__ import annotations

import argparse, copy, hashlib, importlib.util, json, re, stat, subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = "nexus.candidate_acceptance.v4"
VALIDATION_SCHEMA = "nexus.candidate_acceptance.validation.v4"
DIRECT_SCHEMA = "devspace.direct_candidate_execution.v1"
CORE_RESPONSE_SCHEMA = "nexus.core.generic-verification-response.v1-experimental"
MCP_RECEIPT_SCHEMAS = {"nexus.mcp_execution_receipt.v2", "nexus.mcp_execution_receipt.v1"}
EXECUTOR_KINDS = {"NEXUS_MCP_RECEIPT", "DEVSPACE_DIRECT_EVIDENCE"}
VERIFICATION_KINDS = {"MCP_VERIFIED_RECEIPT", "CORE_GENERIC_VERIFICATION_RESPONSE"}
VERDICTS = {"ACCEPT_CANDIDATE", "REJECT_CANDIDATE", "ACCEPTANCE_BLOCKED", "OWNER_DECISION_REQUIRED"}
CONTRACT_KINDS = {"TRACKED_TASK_CARD", "OWNER_INLINE"}
AXES = {"authority", "subject_identity", "lineage", "independent_behavior", "provenance", "claim_discipline"}
AXIS_VERDICTS = {"PASS", "FAIL", "BLOCKED", "NOT_REQUIRED"}
TRANSPORT_MODES = {"LIVE_MCP", "LOCAL_READ_ONLY", "SOURCE_BOUNDED"}
HOST_BINDING = {"AVAILABLE", "HOST_ACTION_BINDING_GAP", "ACTION_RESOLUTION_FAILURE", "SERVER_ACTION_NOT_FOUND", "NOT_APPLICABLE", "UNKNOWN"}
VERIFY_SURFACES = {"FULL_VERIFY", "OBSERVE_ONLY", "UNAVAILABLE"}
INDEPENDENCE = {"INDEPENDENT_REVIEWER", "PARTIAL_INDEPENDENCE", "UNVERIFIED"}
COMMAND_RESULTS = {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}
APPROVAL_STATES = {"READY_FOR_OWNER_APPROVAL", "BLOCKED_BY_TRANSPORT_FRESHNESS", "BLOCKED_BY_HOST_BINDING", "BLOCKED_BY_LIFECYCLE_STATE", "NOT_EVALUATED"}
NEXT_GATE_BY_APPROVAL = {
    "READY_FOR_OWNER_APPROVAL": "OWNER_CANDIDATE_APPROVAL",
    "BLOCKED_BY_TRANSPORT_FRESHNESS": "REFRESH_OWNER_APPROVAL_BINDING",
    "BLOCKED_BY_HOST_BINDING": "RESTORE_OWNER_APPROVAL_ACTION_BINDING",
    "BLOCKED_BY_LIFECYCLE_STATE": "RECONCILE_CANDIDATE_LIFECYCLE_STATE",
    "NOT_EVALUATED": "OWNER_REVIEW_ACCEPTANCE_RESULT",
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HASH_REF = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_OID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$")
SECRET_RE = re.compile(r"(?i)(bearer\s+[a-z0-9._~-]+|api[_-]?key\s*[:=]|password\s*[:=]|private[_-]?key\s*[:=])")
GIT_TREE_REF = re.compile(r"^git-tree:[0-9a-f]{40}$")
GIT_PATH = re.compile(r"^(?!/)(?!.*\\)(?!.*//)(?!.*(?:^|/)\.\.?/)(?!.*(?:^|/)\.\.?$).+$")
CORE_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
FORBIDDEN_CLAIM = re.compile(
    r"(?i)(?:certif(?:y|ied|ication)|owner\s+approv(?:al|ed|e)|\bmerge(?:d|s)?\b|"
    r"\brelease(?:d|s)?\b|\bdeploy(?:ed|ment|s)?\b|production(?:[- ]readiness|[- ]ready)?|"
    r"public\s+claim)"
)
REQUIRED_AXES = frozenset(AXES)
CORE_PROTOCOL_VERSION = "0.1.0-experimental"
MCP_MIN_APPROVAL_BINDINGS = {
    "contract_kind", "contract_hash", "task_id", "attempt_id", "lifecycle_revision",
    "server_instance_id", "tool_manifest_hash", "full_tool_schema_hash", "permission_policy_hash",
    "candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash",
}

class DuplicateKeyError(ValueError): pass

def no_duplicate_pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out: raise DuplicateKeyError(k)
        out[k] = v
    return out

def canonical_sha256(data: dict[str, Any]) -> str:
    cloned = copy.deepcopy(data)
    cloned.setdefault("integrity", {})["sha256"] = "0" * 64
    raw = json.dumps(cloned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def direct_integrity_sha256(data: dict[str, Any]) -> str:
    cloned = copy.deepcopy(data)
    cloned["integrity"] = {"sha256": "0" * 64}
    return _producer_canonical_sha256(cloned)

def file_sha256(path: Path) -> str:
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 16 * 1024 * 1024:
        raise OSError(f"unsafe bound source: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_pairs)
    if not isinstance(value, dict): raise ValueError(f"bound source must be object: {path}")
    return value

def nonempty(v): return isinstance(v, str) and bool(v.strip())
def exact(v, keys): return isinstance(v, dict) and set(v) == set(keys)
def nullable_nonempty(v): return v is None or nonempty(v)
def validate_nullable_bool(errors, path, value):
    if value is not None and not isinstance(value, bool):
        errors.append(f"{path}: boolean or null required")
def add_hash(errors, path, value, nullable=False):
    if value is None and nullable: return
    if not isinstance(value, str) or not HEX64.fullmatch(value): errors.append(f"{path}: lowercase SHA-256 required")
def add_git(errors, path, value, nullable=False):
    if value is None and nullable: return
    if not isinstance(value, str) or not GIT_OID.fullmatch(value): errors.append(f"{path}: full Git OID required")
def hash_ref_to_hex(v): return v[7:] if isinstance(v, str) and HASH_REF.fullmatch(v) else None

def validate(data: Any) -> dict[str, Any]:
    e, w = [], []
    if not isinstance(data, dict): return {"schema": VALIDATION_SCHEMA, "valid": False, "errors": ["$: object required"], "warnings": []}
    top = {"schema","acceptance_id","created_at","verdict","source","repository","transport","axes","review","approval_readiness","approval_boundary","maximum_supportable_claim","next_gate","blockers","integrity"}
    if set(data) != top: e.append("$: exact v4 top-level fields required")
    if data.get("schema") != SCHEMA: e.append(f"$.schema: expected {SCHEMA}")
    try:
        if datetime.fromisoformat(str(data.get("created_at", "")).replace("Z", "+00:00")).tzinfo is None: raise ValueError
    except ValueError: e.append("$.created_at: timezone-aware ISO-8601 required")
    if not isinstance(data.get("acceptance_id"), str) or not ID_RE.fullmatch(data.get("acceptance_id", "")): e.append("$.acceptance_id: invalid identifier")
    verdict = data.get("verdict")
    if verdict not in VERDICTS: e.append("$.verdict: invalid")

    source_keys = {"contract_kind","campaign_id","task_id","contract_hash","task_card_path","task_card_sha256","compiled_packet_sha256","execution_manifest_sha256","implementer_attempt_id","reviewer_attempt_id","executor_evidence_kind","executor_evidence_sha256","verification_evidence_kind","verification_evidence_sha256"}
    source = data.get("source")
    if not exact(source, source_keys): e.append("$.source: exact v4 source fields required"); source = {}
    kind, vkind = source.get("executor_evidence_kind"), source.get("verification_evidence_kind")
    if source.get("contract_kind") not in CONTRACT_KINDS: e.append("$.source.contract_kind: invalid")
    if kind not in EXECUTOR_KINDS: e.append("$.source.executor_evidence_kind: invalid")
    if vkind not in VERIFICATION_KINDS: e.append("$.source.verification_evidence_kind: invalid")
    for k in ("task_id","implementer_attempt_id","reviewer_attempt_id"):
        if not nonempty(source.get(k)):
            e.append(f"$.source.{k}: required")
    if source.get("reviewer_attempt_id") == source.get("implementer_attempt_id"): e.append("$.source.reviewer_attempt_id: must differ from implementer")
    for k in ("contract_hash","executor_evidence_sha256","verification_evidence_sha256"): add_hash(e, f"$.source.{k}", source.get(k))
    for k in ("task_card_sha256","compiled_packet_sha256","execution_manifest_sha256"): add_hash(e, f"$.source.{k}", source.get(k), True)
    if not nullable_nonempty(source.get("campaign_id")): e.append("$.source.campaign_id: string or null required")
    if source.get("task_card_path") is not None and not nonempty(source.get("task_card_path")): e.append("$.source.task_card_path: string or null required")
    if source.get("contract_kind") == "TRACKED_TASK_CARD":
        if not nonempty(source.get("campaign_id")): e.append("$.source.campaign_id: required for TRACKED_TASK_CARD")
        if not nonempty(source.get("task_card_path")): e.append("$.source.task_card_path: required for TRACKED_TASK_CARD")
        if source.get("task_card_sha256") is None: e.append("$.source.task_card_sha256: required for TRACKED_TASK_CARD")
    elif source.get("contract_kind") == "OWNER_INLINE":
        if source.get("task_card_path") is not None: e.append("$.source.task_card_path: must be null for OWNER_INLINE")
        if source.get("task_card_sha256") is not None: e.append("$.source.task_card_sha256: must be null for OWNER_INLINE")

    if kind == "DEVSPACE_DIRECT_EVIDENCE":
        if source.get("contract_kind") != "OWNER_INLINE": e.append("$.source.contract_kind: DEVSPACE_DIRECT_EVIDENCE requires OWNER_INLINE")
        if source.get("campaign_id") is not None: e.append("$.source.campaign_id: direct evidence requires null")
        for k in ("task_card_path","task_card_sha256","compiled_packet_sha256","execution_manifest_sha256"):
            if source.get(k) is not None: e.append(f"$.source.{k}: direct evidence forbids synthetic MCP/Task Card lineage")
        if vkind != "CORE_GENERIC_VERIFICATION_RESPONSE": e.append("$.source.verification_evidence_kind: direct evidence requires CORE_GENERIC_VERIFICATION_RESPONSE")
    if kind == "NEXUS_MCP_RECEIPT" and vkind != "MCP_VERIFIED_RECEIPT": e.append("$.source.verification_evidence_kind: MCP branch requires MCP_VERIFIED_RECEIPT")

    repo_keys = {"root","branch","executor_observed_head","audit_start_head","audit_end_head","expected_base_commit","candidate_commit_sha","candidate_tree_sha","candidate_state_hash","candidate_diff_sha256","verified_receipt_hash","dirty_state","candidate_integrated","repository_drift_during_audit"}
    repo = data.get("repository")
    if not exact(repo, repo_keys): e.append("$.repository: exact v4 repository fields required"); repo = {}
    for k in ("root","branch","dirty_state"):
        if not nonempty(repo.get(k)): e.append(f"$.repository.{k}: required")
    for k in ("executor_observed_head","audit_start_head","audit_end_head","expected_base_commit","candidate_commit_sha","candidate_tree_sha"): add_git(e, f"$.repository.{k}", repo.get(k))
    add_hash(e, "$.repository.candidate_diff_sha256", repo.get("candidate_diff_sha256"))
    add_hash(e, "$.repository.candidate_state_hash", repo.get("candidate_state_hash"), kind == "DEVSPACE_DIRECT_EVIDENCE")
    add_hash(e, "$.repository.verified_receipt_hash", repo.get("verified_receipt_hash"), kind == "DEVSPACE_DIRECT_EVIDENCE")
    if kind == "DEVSPACE_DIRECT_EVIDENCE" and (repo.get("candidate_state_hash") is not None or repo.get("verified_receipt_hash") is not None): e.append("$.repository: direct branch must not fabricate state/verified-receipt hashes")
    if not isinstance(repo.get("candidate_integrated"), bool) or not isinstance(repo.get("repository_drift_during_audit"), bool): e.append("$.repository: boolean state fields required")

    transport_keys = {"mode","server_instance_id","canonical_root","action_contract_hash","tool_manifest_hash","full_tool_schema_hash","permission_policy_hash","lifecycle_revision","host_binding_status","verification_surface","reload_required","action_review_required","permission_review_required","runtime_source_drift","transport_stable","start_evidence_ref","end_evidence_ref"}
    transport = data.get("transport")
    if not exact(transport, transport_keys): e.append("$.transport: exact transport fields required"); transport = {}
    mode = transport.get("mode")
    if mode not in TRANSPORT_MODES: e.append("$.transport.mode: invalid")
    if transport.get("host_binding_status") not in HOST_BINDING: e.append("$.transport.host_binding_status: invalid")
    if transport.get("verification_surface") not in VERIFY_SURFACES: e.append("$.transport.verification_surface: invalid")
    if not isinstance(transport.get("transport_stable"), bool): e.append("$.transport.transport_stable: boolean required")
    for k in ("reload_required","action_review_required","permission_review_required","runtime_source_drift"): validate_nullable_bool(e, f"$.transport.{k}", transport.get(k))
    for k in ("server_instance_id","canonical_root","lifecycle_revision"):
        if not nullable_nonempty(transport.get(k)): e.append(f"$.transport.{k}: string or null required")
    for k in ("action_contract_hash","tool_manifest_hash","full_tool_schema_hash","permission_policy_hash"): add_hash(e, f"$.transport.{k}", transport.get(k), True)
    for k in ("start_evidence_ref","end_evidence_ref"):
        if not nonempty(transport.get(k)): e.append(f"$.transport.{k}: required")
    if mode == "LIVE_MCP":
        for k in ("server_instance_id","canonical_root","lifecycle_revision"):
            if not nonempty(transport.get(k)): e.append(f"$.transport.{k}: required for LIVE_MCP")
        for k in ("action_contract_hash","tool_manifest_hash","full_tool_schema_hash","permission_policy_hash"): add_hash(e, f"$.transport.{k}", transport.get(k))
        for k in ("reload_required","action_review_required","permission_review_required","runtime_source_drift"):
            if not isinstance(transport.get(k), bool): e.append(f"$.transport.{k}: boolean required for LIVE_MCP")

    axes = data.get("axes")
    req = []
    if not isinstance(axes, dict) or set(axes) != AXES: e.append("$.axes: exact six axes required"); axes = {}
    for name in AXES:
        item = axes.get(name, {})
        if not exact(item, {"required","verdict","reason","evidence_refs"}): e.append(f"$.axes.{name}: invalid shape"); continue
        if not isinstance(item.get("required"), bool): e.append(f"$.axes.{name}.required: boolean required")
        if item.get("verdict") not in AXIS_VERDICTS: e.append(f"$.axes.{name}.verdict: invalid")
        if not nonempty(item.get("reason")): e.append(f"$.axes.{name}.reason: required")
        refs = item.get("evidence_refs")
        if not isinstance(refs, list) or not all(nonempty(x) for x in refs): e.append(f"$.axes.{name}.evidence_refs: string array required")
        if item.get("required") is not True:
            e.append(f"$.axes.{name}.required: every v4 evidence axis is mandatory")
        req.append(item.get("verdict"))
        if item.get("verdict") == "NOT_REQUIRED": e.append(f"$.axes.{name}: required axis cannot be NOT_REQUIRED")
        if item.get("verdict") in {"PASS","FAIL","BLOCKED"} and (not isinstance(refs, list) or not refs): e.append(f"$.axes.{name}: evidence required")

    review = data.get("review", {})
    if not exact(review, {"reviewer_distinct","independence_class","commands","anti_false_green","transport_failures"}): e.append("$.review: exact review fields required"); review = {}
    if review.get("reviewer_distinct") is not True or source.get("reviewer_attempt_id") == source.get("implementer_attempt_id"): e.append("$.review.reviewer_distinct: must be true")
    if review.get("independence_class") not in INDEPENDENCE: e.append("$.review.independence_class: invalid")
    commands = review.get("commands", [])
    if not isinstance(commands, list): e.append("$.review.commands: array required"); commands = []
    for i, cmd in enumerate(commands):
        keys = {"id","cwd","argv","result_class","exit_code","duration_ms","changed_paths","evidence_ref"}
        if not exact(cmd, keys): e.append(f"$.review.commands[{i}]: exact command fields required"); continue
        for k in ("id","cwd","evidence_ref"):
            if not nonempty(cmd.get(k)): e.append(f"$.review.commands[{i}].{k}: required")
        if not isinstance(cmd.get("argv"), list) or not cmd.get("argv") or not all(nonempty(x) for x in cmd.get("argv")): e.append(f"$.review.commands[{i}].argv: non-empty string array required")
        if cmd.get("result_class") not in COMMAND_RESULTS: e.append(f"$.review.commands[{i}].result_class: invalid")
        if cmd.get("exit_code") is not None and not isinstance(cmd.get("exit_code"), int): e.append(f"$.review.commands[{i}].exit_code: integer or null required")
        if cmd.get("duration_ms") is not None and (not isinstance(cmd.get("duration_ms"), int) or cmd.get("duration_ms") < 0): e.append(f"$.review.commands[{i}].duration_ms: non-negative integer or null required")
        if not isinstance(cmd.get("changed_paths"), list) or not all(nonempty(x) for x in cmd.get("changed_paths")): e.append(f"$.review.commands[{i}].changed_paths: string array required")
        if cmd.get("result_class") == "PASS" and cmd.get("exit_code") != 0: e.append(f"$.review.commands[{i}]: PASS requires exit 0")
        if cmd.get("result_class") in {"BLOCKED","NOT_RUN"} and cmd.get("exit_code") is not None: w.append(f"$.review.commands[{i}]: blocked/not-run command normally has null exit")
    if not nonempty(review.get("anti_false_green")): e.append("$.review.anti_false_green: required")
    if not isinstance(review.get("transport_failures"), list) or not all(nonempty(x) for x in review.get("transport_failures")): e.append("$.review.transport_failures: string array required")
    if axes.get("independent_behavior", {}).get("required") is True and axes.get("independent_behavior", {}).get("verdict") == "PASS" and not any(isinstance(c, dict) and c.get("result_class") == "PASS" for c in commands): e.append("$.review.commands: independent behavior PASS requires PASS command")

    readiness = data.get("approval_readiness", {})
    readiness_keys = {"status","task_pending_acceptance","exact_binding_match","approval_action_available","approval_contract_created","candidate_already_approved","candidate_already_integrated","required_binding_fields","blockers","evidence_refs"}
    if not exact(readiness, readiness_keys): e.append("$.approval_readiness: exact fields required"); readiness = {}
    if readiness.get("status") not in APPROVAL_STATES: e.append("$.approval_readiness.status: invalid")
    for k in ("task_pending_acceptance","exact_binding_match","approval_action_available","candidate_already_approved","candidate_already_integrated"): validate_nullable_bool(e, f"$.approval_readiness.{k}", readiness.get(k))
    if readiness.get("approval_contract_created") is not False: e.append("$.approval_readiness.approval_contract_created: must be false")
    binding_fields = readiness.get("required_binding_fields")
    if not isinstance(binding_fields, list) or not all(nonempty(x) for x in binding_fields): e.append("$.approval_readiness.required_binding_fields: string array required"); binding_fields = []
    minimum_fields = {"contract_kind","contract_hash","task_id","attempt_id","candidate_commit_sha","candidate_tree_sha"}
    if not minimum_fields.issubset(set(binding_fields)): e.append("$.approval_readiness.required_binding_fields: missing " + ", ".join(sorted(minimum_fields - set(binding_fields))))
    if kind == "NEXUS_MCP_RECEIPT" and not MCP_MIN_APPROVAL_BINDINGS.issubset(set(binding_fields)):
        e.append("$.approval_readiness.required_binding_fields: MCP branch must preserve v3 approval bindings")
    if source.get("contract_kind") == "TRACKED_TASK_CARD" and "task_card_hash" not in binding_fields: e.append("$.approval_readiness.required_binding_fields: TRACKED_TASK_CARD requires task_card_hash")
    readiness_blockers = readiness.get("blockers")
    if not isinstance(readiness_blockers, list) or not all(nonempty(x) for x in readiness_blockers): e.append("$.approval_readiness.blockers: string array required"); readiness_blockers = []
    readiness_refs = readiness.get("evidence_refs")
    if not isinstance(readiness_refs, list) or not all(nonempty(x) for x in readiness_refs): e.append("$.approval_readiness.evidence_refs: string array required"); readiness_refs = []
    if readiness.get("status") != "NOT_EVALUATED" and not readiness_refs: e.append("$.approval_readiness.evidence_refs: evidence required")
    if readiness.get("status") == "READY_FOR_OWNER_APPROVAL":
        ready = {"task_pending_acceptance": readiness.get("task_pending_acceptance") is True, "exact_binding_match": readiness.get("exact_binding_match") is True, "approval_action_available": readiness.get("approval_action_available") is True, "candidate_already_approved": readiness.get("candidate_already_approved") is False, "candidate_already_integrated": readiness.get("candidate_already_integrated") is False, "candidate_integrated": repo.get("candidate_integrated") is False, "transport_stable": transport.get("transport_stable") is True, "host_binding": transport.get("host_binding_status") == "AVAILABLE", "reload_required": transport.get("reload_required") is False, "action_review_required": transport.get("action_review_required") is False, "permission_review_required": transport.get("permission_review_required") is False, "runtime_source_drift": transport.get("runtime_source_drift") is False}
        for name, ok in ready.items():
            if not ok: e.append(f"$.approval_readiness: READY_FOR_OWNER_APPROVAL requires {name}")
        if readiness_blockers: e.append("$.approval_readiness.blockers: ready state requires no blockers")
    elif readiness.get("status") != "NOT_EVALUATED" and not readiness_blockers:
        e.append("$.approval_readiness.blockers: blocked readiness requires blockers")
    if readiness.get("status") == "BLOCKED_BY_HOST_BINDING" and transport.get("host_binding_status") not in {"HOST_ACTION_BINDING_GAP","ACTION_RESOLUTION_FAILURE","UNKNOWN"}: e.append("$.approval_readiness.status: host-binding block requires matching host status")
    if readiness.get("status") == "BLOCKED_BY_TRANSPORT_FRESHNESS" and not (transport.get("transport_stable") is False or transport.get("reload_required") is True or transport.get("action_review_required") is True or transport.get("permission_review_required") is True or transport.get("runtime_source_drift") is True): e.append("$.approval_readiness.status: transport freshness block lacks freshness evidence")
    if readiness.get("status") == "BLOCKED_BY_LIFECYCLE_STATE" and not (readiness.get("task_pending_acceptance") is not True or readiness.get("exact_binding_match") is not True or readiness.get("candidate_already_approved") is True or readiness.get("candidate_already_integrated") is True or repo.get("candidate_integrated") is True): e.append("$.approval_readiness.status: lifecycle block lacks lifecycle evidence")

    boundary = data.get("approval_boundary", {})
    if not exact(boundary, {"acceptance_recommendation_only","candidate_approved","approval_contract_created","integrated","public_claim_allowed","owner_action_required"}): e.append("$.approval_boundary: invalid shape"); boundary = {}
    if boundary.get("acceptance_recommendation_only") is not True or boundary.get("owner_action_required") is not True: e.append("$.approval_boundary: recommendation-only owner-action boundary required")
    for k in ("candidate_approved","approval_contract_created","integrated","public_claim_allowed"):
        if boundary.get(k) is not False: e.append(f"$.approval_boundary.{k}: must be false")

    blockers = data.get("blockers")
    if not isinstance(blockers, list) or not all(nonempty(x) for x in blockers): e.append("$.blockers: string array required"); blockers = []
    if not nonempty(data.get("maximum_supportable_claim")) or not nonempty(data.get("next_gate")): e.append("$: maximum_supportable_claim and next_gate required")
    if nonempty(data.get("maximum_supportable_claim")) and FORBIDDEN_CLAIM.search(data["maximum_supportable_claim"]):
        e.append("$.maximum_supportable_claim: certification/approval/integration/release/deployment/production/public claims are forbidden")
    if verdict == "ACCEPT_CANDIDATE" and (len(req) != len(AXES) or any(x != "PASS" for x in req)):
        e.append("$.verdict: ACCEPT_CANDIDATE requires all six mandatory axes PASS")
    if verdict == "ACCEPT_CANDIDATE":
        if any(x != "PASS" for x in req): e.append("$.verdict: ACCEPT_CANDIDATE requires all required axes PASS")
        if blockers: e.append("$.blockers: accepted Candidate requires none")
        if review.get("independence_class") != "INDEPENDENT_REVIEWER": e.append("$.review.independence_class: ACCEPT requires independent reviewer")
        expected = NEXT_GATE_BY_APPROVAL.get(readiness.get("status"))
        if expected and data.get("next_gate") != expected: e.append(f"$.next_gate: expected {expected}")
    elif verdict == "REJECT_CANDIDATE":
        if "FAIL" not in req or not blockers or data.get("next_gate") != "OWNER_REJECT_OR_REWORK_CANDIDATE": e.append("$.verdict: malformed rejection")
    elif verdict == "ACCEPTANCE_BLOCKED":
        if "BLOCKED" not in req or not blockers or data.get("next_gate") != "RESOLVE_ACCEPTANCE_BLOCKER": e.append("$.verdict: malformed blocked result")
    elif verdict == "OWNER_DECISION_REQUIRED":
        if any(x in {"FAIL","BLOCKED"} for x in req) or not blockers or data.get("next_gate") != "OWNER_POLICY_DECISION": e.append("$.verdict: malformed owner-decision result")

    integrity = data.get("integrity")
    if not exact(integrity, {"sha256"}) or integrity.get("sha256") != canonical_sha256(data): e.append("$.integrity.sha256: canonical integrity mismatch")
    if SECRET_RE.search(json.dumps(data, ensure_ascii=False)): e.append("$: possible secret material detected")
    return {"schema": VALIDATION_SCHEMA, "valid": not e, "errors": e, "warnings": w}

def record(data, errors, warnings, msg, axis):
    verdict = data.get("axes", {}).get(axis, {}).get("verdict") if isinstance(data.get("axes"), dict) else None
    if data.get("verdict") == "ACCEPT_CANDIDATE" or verdict not in {"FAIL","BLOCKED"}: errors.append(msg)
    else: warnings.append(f"physical finding reflected by {axis}: {msg}")

def _obj(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _alias(value: dict[str, Any] | None, *names: str) -> Any:
    if not value:
        return None
    for name in names:
        if name in value:
            return value[name]
    return None


def _hex_or_ref(value: Any) -> str | None:
    if isinstance(value, str) and HEX64.fullmatch(value):
        return value
    return hash_ref_to_hex(value)


def _producer_canonical_json(value: Any) -> str:
    script = r'''const fs=require("fs");
const sortJson=(v)=>Array.isArray(v)?v.map(sortJson):(v&&typeof v==="object"?Object.fromEntries(Object.entries(v).filter(([,c])=>c!==undefined).sort(([a],[b])=>a.localeCompare(b)).map(([k,c])=>[k,sortJson(c)])):v);
process.stdout.write(JSON.stringify(sortJson(JSON.parse(fs.readFileSync(0,"utf8")))));'''
    proc = subprocess.run(
        ["node", "-e", script], input=json.dumps(value, ensure_ascii=False),
        text=True, capture_output=True, timeout=10,
    )
    if proc.returncode != 0:
        raise OSError(proc.stderr.strip() or "Node producer canonicalization failed")
    return proc.stdout


def _producer_canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_producer_canonical_json(value).encode("utf-8")).hexdigest()


def _producer_locale_order(paths: list[str]) -> list[str]:
    script = r'''const fs=require("fs"); const p=JSON.parse(fs.readFileSync(0,"utf8")); p.sort((a,b)=>a.localeCompare(b)); process.stdout.write(JSON.stringify(p));'''
    proc = subprocess.run(
        ["node", "-e", script], input=json.dumps(paths, ensure_ascii=False),
        text=True, capture_output=True, timeout=10,
    )
    if proc.returncode != 0:
        raise OSError(proc.stderr.strip() or "Node localeCompare ordering failed")
    ordered = json.loads(proc.stdout)
    if not isinstance(ordered, list) or not all(isinstance(item, str) for item in ordered):
        raise OSError("Node localeCompare ordering returned malformed output")
    return ordered


def _producer_codeunit_order(values: list[str]) -> list[str]:
    script = r'''const fs=require("fs"); const p=JSON.parse(fs.readFileSync(0,"utf8")); p.sort(); process.stdout.write(JSON.stringify(p));'''
    proc = subprocess.run(
        ["node", "-e", script], input=json.dumps(values, ensure_ascii=False),
        text=True, capture_output=True, timeout=10,
    )
    if proc.returncode != 0:
        raise OSError(proc.stderr.strip() or "Node code-unit ordering failed")
    ordered = json.loads(proc.stdout)
    if not isinstance(ordered, list) or not all(isinstance(item, str) for item in ordered):
        raise OSError("Node code-unit ordering returned malformed output")
    return ordered


def _producer_date_parseable(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    script = 'const v=process.argv[1]; process.exit(typeof v==="string" && v.length>0 && Number.isFinite(Date.parse(v)) ? 0 : 1);'
    try:
        proc = subprocess.run(["node", "-e", script, value], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _producer_trim(value: str) -> str:
    script = r'''const fs=require("fs"); const v=JSON.parse(fs.readFileSync(0,"utf8")); if(typeof v!=="string") process.exit(2); process.stdout.write(JSON.stringify(v.trim()));'''
    proc = subprocess.run(
        ["node", "-e", script], input=json.dumps(value, ensure_ascii=False),
        text=True, capture_output=True, timeout=5,
    )
    if proc.returncode != 0:
        raise OSError(proc.stderr.strip() or "Node String.trim replay failed")
    trimmed = json.loads(proc.stdout)
    if not isinstance(trimmed, str):
        raise OSError("Node String.trim replay returned malformed output")
    return trimmed


def _producer_trim_array(values: list[str]) -> list[str]:
    script = r'''const fs=require("fs"); const v=JSON.parse(fs.readFileSync(0,"utf8")); if(!Array.isArray(v)||!v.every(x=>typeof x==="string")) process.exit(2); process.stdout.write(JSON.stringify(v.map(x=>x.trim())));'''
    proc = subprocess.run(
        ["node", "-e", script], input=json.dumps(values, ensure_ascii=False),
        text=True, capture_output=True, timeout=5,
    )
    if proc.returncode != 0:
        raise OSError(proc.stderr.strip() or "Node String.trim array replay failed")
    trimmed = json.loads(proc.stdout)
    if not isinstance(trimmed, list) or not all(isinstance(item, str) for item in trimmed):
        raise OSError("Node String.trim array replay returned malformed output")
    return trimmed


def _producer_nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(_producer_trim(value))


def _producer_normalize_remote_identity(value: str) -> str:
    script = r'''const fs=require("fs"); const v=JSON.parse(fs.readFileSync(0,"utf8")); if(typeof v!=="string") process.exit(2); const t=v.trim(); const scp=/^git@([^:]+):(.+)$/.exec(t); let out; if(scp){out=`${scp[1].toLowerCase()}/${scp[2].replace(/\.git$/,"").replace(/^\/+|\/+$/g,"")}`;}else{try{const u=new URL(t); out=`${u.hostname.toLowerCase()}/${u.pathname.replace(/\.git$/,"").replace(/^\/+|\/+$/g,"")}`;}catch{out=t.replace(/\.git$/,"").replace(/\/+$/g,"");}} process.stdout.write(JSON.stringify(out));'''
    proc = subprocess.run(
        ["node", "-e", script], input=json.dumps(value, ensure_ascii=False),
        text=True, capture_output=True, timeout=5,
    )
    if proc.returncode != 0:
        raise OSError(proc.stderr.strip() or "Node remote identity replay failed")
    normalized = json.loads(proc.stdout)
    if not isinstance(normalized, str):
        raise OSError("Node remote identity replay returned malformed output")
    return normalized


def _normalize_dispatch_intent(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("dispatch_intent must be an object")
    intent: dict[str, Any] = {
        "taskId": value.get("taskId"),
        "attemptId": value.get("attemptId"),
        "objective": value.get("objective"),
        "roleIntent": value.get("roleIntent"),
        "exclusiveOwnership": value.get("exclusiveOwnership"),
        "acceptanceCriteria": value.get("acceptanceCriteria", []),
        "verificationRequired": value.get("verificationRequired"),
        "claimCeiling": value.get("claimCeiling"),
    }
    optional_arrays = ("context", "readScope", "writeScope", "forbiddenChanges", "expectedArtifacts", "expectedEvidence")
    for key in optional_arrays:
        if key in value:
            raw = value[key]
            if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
                raise ValueError(f"dispatch_intent.{key} must be an array of strings")
            intent[key] = _producer_trim_array(raw)

    for key in ("taskId", "attemptId", "objective"):
        if not isinstance(intent[key], str) or not _producer_trim(intent[key]):
            raise ValueError(f"dispatch_intent.{key} must be non-empty text")
    if intent["roleIntent"] not in {"EVIDENCE_COLLECTOR", "MECHANICAL_EXECUTOR", "DEEP_ENGINEERING", "TEST_VERIFIER", "INDEPENDENT_REVIEWER", "RECOVERY_RECONCILER"}:
        raise ValueError("dispatch_intent.roleIntent is unsupported")
    if intent["claimCeiling"] not in {"RESULT_RETURNED", "IMPLEMENTED", "CANDIDATE_READY"}:
        raise ValueError("dispatch_intent.claimCeiling is unsupported")
    criteria = intent["acceptanceCriteria"]
    if not isinstance(criteria, list) or not criteria or not all(isinstance(item, str) for item in criteria):
        raise ValueError("dispatch_intent.acceptanceCriteria must be a non-empty string array")
    normalized_criteria = _producer_trim_array(criteria)
    if not all(normalized_criteria):
        raise ValueError("dispatch_intent.acceptanceCriteria must be a non-empty string array")
    intent["acceptanceCriteria"] = normalized_criteria
    if not isinstance(intent["verificationRequired"], bool) or not isinstance(intent["exclusiveOwnership"], bool):
        raise ValueError("dispatch_intent verificationRequired/exclusiveOwnership must be boolean")
    for key in ("context", "forbiddenChanges", "expectedArtifacts", "expectedEvidence"):
        if key in intent and not all(item for item in intent[key]):
            raise ValueError(f"dispatch_intent.{key} entries must be non-empty")
    for key, allow_root in (("readScope", True), ("writeScope", False)):
        for item in intent.get(key, []):
            if not item:
                raise ValueError(f"dispatch_intent.{key} entries must be non-empty")
            normalized = item.replace("\\", "/")
            if (not allow_root and normalized == ".") or normalized.startswith("/") or ".." in normalized.split("/"):
                raise ValueError(f"dispatch_intent.{key} contains an invalid workspace-relative path")
    mutating = bool(intent.get("writeScope"))
    if mutating != bool(intent["exclusiveOwnership"]):
        raise ValueError("dispatch_intent exclusiveOwnership does not match mutation scope")
    return intent


def core_value_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def core_acceptance_contract_hash(contract: dict[str, Any]) -> str:
    value = [
        contract.get("contract_id"),
        contract.get("requirements_hash"),
        _producer_codeunit_order(list(contract.get("required_verifier_ids", []))),
        _producer_codeunit_order(list(contract.get("allowed_paths", []))),
        contract.get("deletion_policy"),
    ]
    return core_value_hash(value)


def core_binding_hash(binding: dict[str, Any]) -> str:
    value = copy.deepcopy(binding)
    value.pop("binding_hash", None)
    return core_value_hash(value)


def core_workspace_identity(workspace_id: str, repository: dict[str, Any]) -> str:
    return core_value_hash([
        "devspace.core-mutation-workspace.v1",
        workspace_id,
        repository.get("canonical_id"),
        repository.get("source_revision"),
        repository.get("source_tree"),
        repository.get("workspace_mode"),
    ])


def _core_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == _producer_trim(value) and "\x00" not in value


def _core_relative_path(value: Any) -> bool:
    if not _core_text(value) or value.startswith("/") or "\\" in value:
        return False
    return not any(segment in {"", ".", ".."} for segment in value.split("/"))


def _validate_core_binding_shape(binding: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    top = {"schema", "binding_id", "operation_id", "attempt_id", "repository", "integration_authority", "capability_discovery", "core", "freshness", "binding_hash"}
    if set(binding) != top:
        issues.append("embedded Core binding top-level shape mismatch")
        return issues
    if binding.get("schema") != "nexus.repository_mutation_binding.v1":
        issues.append("embedded Core binding schema mismatch")
    for key in ("binding_id", "operation_id", "attempt_id"):
        if not _core_text(binding.get(key)):
            issues.append(f"embedded Core binding {key} is malformed")
    if not isinstance(binding.get("binding_hash"), str) or not CORE_HASH.fullmatch(binding.get("binding_hash", "")):
        issues.append("embedded Core binding_hash is malformed")

    repository = _obj(binding.get("repository"))
    authority = _obj(binding.get("integration_authority"))
    discovery = _obj(binding.get("capability_discovery"))
    core = _obj(binding.get("core"))
    freshness = _obj(binding.get("freshness"))
    if repository is None or authority is None or discovery is None or core is None or freshness is None:
        issues.append("embedded Core binding nested objects are required")
        return issues

    if set(repository) != {"canonical_id", "origin", "source_revision", "source_tree", "workspace_identity", "workspace_mode"}:
        issues.append("embedded Core repository shape mismatch")
    else:
        for key in ("canonical_id", "origin"):
            if not _core_text(repository.get(key)):
                issues.append(f"embedded Core repository {key} is malformed")
        if not isinstance(repository.get("source_revision"), str) or not re.fullmatch(r"git-commit:[0-9a-f]{40}", repository.get("source_revision", "")):
            issues.append("embedded Core repository source_revision is malformed")
        if not isinstance(repository.get("source_tree"), str) or not re.fullmatch(r"git-tree:[0-9a-f]{40}", repository.get("source_tree", "")):
            issues.append("embedded Core repository source_tree is malformed")
        if not isinstance(repository.get("workspace_identity"), str) or not CORE_HASH.fullmatch(repository.get("workspace_identity", "")):
            issues.append("embedded Core repository workspace_identity is malformed")
        if repository.get("workspace_mode") not in {"checkout", "managed_worktree", "target"}:
            issues.append("embedded Core repository workspace_mode is invalid")

    if set(authority) != {"execution_lane", "authority_ref", "authority_hash"}:
        issues.append("embedded Core integration_authority shape mismatch")
    else:
        if authority.get("execution_lane") not in {"DIRECT_CANONICAL", "DIRECT_DELEGATED", "GOVERNED"}:
            issues.append("embedded Core execution lane is invalid")
        if not _core_text(authority.get("authority_ref")):
            issues.append("embedded Core authority_ref is malformed")
        if not isinstance(authority.get("authority_hash"), str) or not CORE_HASH.fullmatch(authority.get("authority_hash", "")):
            issues.append("embedded Core authority_hash is malformed")

    if set(discovery) != {"required", "receipt_hash", "index_revision"}:
        issues.append("embedded Core capability_discovery shape mismatch")
    else:
        if discovery.get("required") is not True:
            issues.append("embedded Core capability discovery must be required")
        if not isinstance(discovery.get("receipt_hash"), str) or not CORE_HASH.fullmatch(discovery.get("receipt_hash", "")):
            issues.append("embedded Core capability discovery receipt_hash is malformed")
        if not isinstance(discovery.get("index_revision"), str) or not re.fullmatch(r"git-commit:[0-9a-f]{40}", discovery.get("index_revision", "")):
            issues.append("embedded Core capability discovery index_revision is malformed")

    if set(core) != {"protocol_version", "acceptance_contract", "acceptance_contract_hash"}:
        issues.append("embedded Core core shape mismatch")
    else:
        if core.get("protocol_version") != CORE_PROTOCOL_VERSION:
            issues.append("embedded Core protocol version mismatch")
        contract = _obj(core.get("acceptance_contract"))
        if contract is None or set(contract) != {"contract_id", "requirements_hash", "required_verifier_ids", "allowed_paths", "deletion_policy"}:
            issues.append("embedded Core AcceptanceContract shape mismatch")
        else:
            if not _core_text(contract.get("contract_id")):
                issues.append("embedded Core AcceptanceContract contract_id is malformed")
            if not isinstance(contract.get("requirements_hash"), str) or not CORE_HASH.fullmatch(contract.get("requirements_hash", "")):
                issues.append("embedded Core AcceptanceContract requirements_hash is malformed")
            verifiers = contract.get("required_verifier_ids")
            if not isinstance(verifiers, list) or not verifiers or not all(_core_text(item) for item in verifiers) or len(set(verifiers)) != len(verifiers):
                issues.append("embedded Core AcceptanceContract required_verifier_ids are malformed")
            paths = contract.get("allowed_paths")
            if not isinstance(paths, list) or not paths or not all(_core_relative_path(item) for item in paths) or len(set(paths)) != len(paths):
                issues.append("embedded Core AcceptanceContract allowed_paths are malformed")
            if contract.get("deletion_policy") not in {"FORBID", "ALLOW"}:
                issues.append("embedded Core AcceptanceContract deletion_policy is invalid")
            if not issues or not any("AcceptanceContract" in issue for issue in issues):
                if core.get("acceptance_contract_hash") != core_acceptance_contract_hash(contract):
                    issues.append("embedded Core AcceptanceContract canonical hash mismatch")
        if not isinstance(core.get("acceptance_contract_hash"), str) or not CORE_HASH.fullmatch(core.get("acceptance_contract_hash", "")):
            issues.append("embedded Core acceptance_contract_hash is malformed")

    if set(freshness) != {"created_at", "valid_until", "revalidate_before_first_effect"}:
        issues.append("embedded Core freshness shape mismatch")
    else:
        if not _producer_date_parseable(freshness.get("created_at")):
            issues.append("embedded Core freshness created_at is malformed")
        if freshness.get("valid_until") is not None and not _producer_date_parseable(freshness.get("valid_until")):
            issues.append("embedded Core freshness valid_until is malformed")
        if freshness.get("revalidate_before_first_effect") is not True:
            issues.append("embedded Core freshness must require revalidation")
    return issues


def core_manifest_hash(manifest: dict[str, Any]) -> str:
    by_path = {row["path"]: row for row in manifest["entries"]}
    entries = [by_path[path] for path in _producer_locale_order(list(by_path))]
    value = [
        "nexus.core.git-change-manifest.v1-experimental",
        manifest["source_tree"],
        manifest["target_tree"],
        [[
            row["path"], row["change_type"], row["before_oid"], row["after_oid"],
            row["before_mode"], row["after_mode"],
        ] for row in entries],
    ]
    return core_value_hash(value)


def _validate_manifest(manifest: Any, source_tree: str | None, target_tree: str | None,
                       errors: list[str], prefix: str = "candidate.change_manifest") -> bool:
    if not isinstance(manifest, dict) or set(manifest) != {"source_tree", "target_tree", "entries"}:
        errors.append(f"{prefix}: exact source_tree/target_tree/entries object required")
        return False
    if not GIT_TREE_REF.fullmatch(manifest["source_tree"]):
        errors.append(f"{prefix}.source_tree: git-tree:<40 hex> required")
    if not GIT_TREE_REF.fullmatch(manifest["target_tree"]):
        errors.append(f"{prefix}.target_tree: git-tree:<40 hex> required")
    if source_tree and manifest["source_tree"] != f"git-tree:{source_tree}":
        errors.append(f"{prefix}.source_tree: must bind to candidate source tree")
    if target_tree and manifest["target_tree"] != f"git-tree:{target_tree}":
        errors.append(f"{prefix}.target_tree: must bind to candidate tree")
    entries = manifest["entries"]
    if not isinstance(entries, list) or not entries:
        errors.append(f"{prefix}.entries: non-empty array required")
        return False
    if all(isinstance(row, dict) and isinstance(row.get("path"), str) for row in entries):
        paths = [row["path"] for row in entries]
        if paths != _producer_locale_order(paths.copy()):
            errors.append(f"{prefix}.entries: order must match producer path.localeCompare semantics")
    seen: set[str] = set()
    for index, row in enumerate(entries):
        path = f"{prefix}.entries[{index}]"
        if not isinstance(row, dict) or set(row) != {"path", "change_type", "before_oid", "after_oid", "before_mode", "after_mode"}:
            errors.append(f"{path}: exact change entry required")
            continue
        if not isinstance(row["path"], str) or not GIT_PATH.fullmatch(row["path"]) or row["path"] in seen:
            errors.append(f"{path}.path: unique repository-relative path required")
        seen.add(row["path"] if isinstance(row["path"], str) else f"#{index}")
        if row["change_type"] not in {"ADD", "MODIFY", "DELETE"}:
            errors.append(f"{path}.change_type: ADD/MODIFY/DELETE required")
        for field in ("before_oid", "after_oid"):
            if row[field] is not None and (not isinstance(row[field], str) or not GIT_OID.fullmatch(row[field])):
                errors.append(f"{path}.{field}: Git OID or null required")
        for field in ("before_mode", "after_mode"):
            if row[field] is not None and (not isinstance(row[field], str) or not re.fullmatch(r"[0-7]{6}", row[field])):
                errors.append(f"{path}.{field}: six-digit Git mode or null required")
        shape = (row["before_oid"], row["before_mode"], row["after_oid"], row["after_mode"])
        if row["change_type"] == "ADD" and not (shape[0] is None and shape[1] is None and shape[2] is not None and shape[3] is not None):
            errors.append(f"{path}: ADD requires only after object/mode")
        if row["change_type"] == "DELETE" and not (shape[0] is not None and shape[1] is not None and shape[2] is None and shape[3] is None):
            errors.append(f"{path}: DELETE requires only before object/mode")
        if row["change_type"] == "MODIFY" and not (shape[0] is not None and shape[1] is not None and shape[2] is not None and shape[3] is not None and shape[0:2] != shape[2:4]):
            errors.append(f"{path}: MODIFY requires differing before/after object or mode")
    return not any(item.startswith(prefix) for item in errors)


def _git(root: str, *argv: str) -> str:
    proc = subprocess.run(["git", "-C", root, *argv], text=True, capture_output=True, timeout=10)
    if proc.returncode != 0:
        raise OSError(proc.stderr.strip() or f"git {' '.join(argv)} failed")
    return proc.stdout.strip()


def _git_tree_entry(root: str, tree: str, path: str) -> tuple[str, str] | None:
    raw = _git(root, "ls-tree", "-r", tree, "--", path)
    if not raw:
        return None
    fields = raw.splitlines()[0].split("\t", 1)[0].split()
    if len(fields) != 3:
        raise OSError(f"cannot parse git tree entry for {path}")
    return fields[0], fields[2]


def _physical_manifest(root: str, source_commit: str, candidate_commit: str) -> dict[str, Any]:
    source_tree = _git(root, "rev-parse", f"{source_commit}^{{tree}}")
    target_tree = _git(root, "rev-parse", f"{candidate_commit}^{{tree}}")
    raw = _git(root, "diff-tree", "--no-commit-id", "--name-status", "-r", "-z", "--no-renames", source_commit, candidate_commit)
    fields = [item for item in raw.split("\0") if item]
    entries: list[dict[str, Any]] = []
    for index in range(0, len(fields), 2):
        status, path = fields[index:index + 2]
        if not path:
            raise OSError("malformed Git name-status output")
        before = _git_tree_entry(root, source_tree, path)
        after = _git_tree_entry(root, target_tree, path)
        change_type = "ADD" if status.startswith("A") else "DELETE" if status.startswith("D") else "MODIFY"
        entries.append({
            "path": path,
            "change_type": change_type,
            "before_oid": before[1] if before else None,
            "after_oid": after[1] if after else None,
            "before_mode": before[0] if before else None,
            "after_mode": after[0] if after else None,
        })
    by_path = {row["path"]: row for row in entries}
    ordered = [by_path[path] for path in _producer_locale_order(list(by_path))]
    return {"source_tree": f"git-tree:{source_tree}", "target_tree": f"git-tree:{target_tree}", "entries": ordered}


def _direct_identity(evidence: dict[str, Any]) -> dict[str, Any]:
    auth, execution, core, candidate = (_obj(evidence.get(name)) for name in ("authority", "execution", "core_binding", "candidate"))
    return {
        "task_id": auth.get("task_id") if auth else None,
        "attempt_id": auth.get("attempt_id") if auth else None,
        "contract_hash": _hex_or_ref(core.get("acceptance_contract_hash")) if core else None,
        "root": execution.get("workspace_root") if execution else None,
        "source_commit": candidate.get("source_commit") if candidate else None,
        "source_tree": candidate.get("source_tree") if candidate else None,
        "candidate_commit": candidate.get("commit_sha") if candidate else None,
        "candidate_tree": candidate.get("tree_sha") if candidate else None,
        "diff_hash": candidate.get("diff_hash") if candidate else None,
        "changed_paths": candidate.get("changed_paths") if candidate else None,
        "deleted_paths": candidate.get("deleted_paths") if candidate else None,
        "core_contract_hash": core.get("acceptance_contract_hash") if core else None,
    }


def _mcp_identity(receipt: dict[str, Any]) -> dict[str, Any]:
    source = _obj(receipt.get("source")) or {}
    attempt = _obj(receipt.get("attempt")) or {}
    repository = _obj(receipt.get("repository")) or {}
    effects = _obj(receipt.get("effects")) or {}
    candidate = _obj(receipt.get("candidate")) or {}
    verification = _obj(receipt.get("verification")) or {}
    return {
        "contract_kind": source.get("contract_kind"), "campaign_id": source.get("campaign_id"),
        "task_id": receipt.get("task_id") or source.get("task_id"),
        "contract_hash": source.get("contract_hash"),
        "attempt_id": attempt.get("attempt_id"),
        "root": repository.get("root"), "branch": repository.get("branch"),
        "executor_observed_head": repository.get("observed_head"),
        "expected_base_commit": repository.get("expected_head"),
        "candidate_commit_sha": candidate.get("commit_sha"), "candidate_tree_sha": candidate.get("tree_sha"),
        "candidate_state_hash": candidate.get("state_hash"),
        "candidate_diff_sha256": effects.get("candidate_diff_sha256"),
        "verified_receipt_hash": verification.get("verified_receipt_hash"),
        "implementer_attempt_id": attempt.get("attempt_id"),
    }


def _check_mcp_receipt(data: dict[str, Any], receipt: Any, errors: list[str], warnings: list[str], *, label: str) -> dict[str, Any] | None:
    if not isinstance(receipt, dict):
        record(data, errors, warnings, f"{label}: object required", "authority")
        return None
    if receipt.get("schema") not in MCP_RECEIPT_SCHEMAS:
        record(data, errors, warnings, f"{label}: unsupported MCP receipt schema", "authority")
    integrity = receipt.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("sha256") != canonical_sha256(receipt):
        record(data, errors, warnings, f"{label}: integrity mismatch", "subject_identity")
    source, attempt, repository, effects, candidate, verification = (_obj(receipt.get(name)) for name in ("source", "attempt", "repository", "effects", "candidate", "verification"))
    for name, value in (("source", source), ("attempt", attempt), ("repository", repository), ("effects", effects), ("candidate", candidate), ("verification", verification)):
        if value is None:
            record(data, errors, warnings, f"{label}.{name}: object required", "subject_identity")
    if source is None or attempt is None or repository is None or effects is None or candidate is None or verification is None:
        return None
    authority = _obj(receipt.get("authority")) or {}
    if any(authority.get(key) is True for key in ("worker_may_approve", "worker_may_integrate", "worker_may_push", "worker_may_cleanup", "authority_expansion")):
        record(data, errors, warnings, f"{label}: forbidden worker authority", "authority")
    claim = _obj(receipt.get("claim")) or {}
    if claim.get("public_claim_allowed") is not False or (receipt.get("schema") == "nexus.mcp_execution_receipt.v2" and claim.get("claim_amplified") is not False):
        record(data, errors, warnings, f"{label}: claim ceiling is amplified", "claim_discipline")
    if label == "MCP executor" and receipt.get("status") != "IMPLEMENTER_PASS_PENDING_ACCEPTANCE":
        record(data, errors, warnings, "MCP executor: status must be IMPLEMENTER_PASS_PENDING_ACCEPTANCE", "authority")
    if label == "MCP executor" and (candidate.get("present") is not True or candidate.get("required") is not True):
        record(data, errors, warnings, "MCP executor: required present Candidate missing", "subject_identity")
    return _mcp_identity(receipt)


def _validate_git_cross_binding(data: dict[str, Any], direct: dict[str, Any], manifest: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    execution = _obj(direct.get("execution")) or {}
    candidate = _obj(direct.get("candidate")) or {}
    core_binding = _obj(direct.get("core_binding")) or {}
    binding = _obj(core_binding.get("binding")) or {}
    binding_repository = _obj(binding.get("repository"))
    root = execution.get("workspace_root")
    source_commit = candidate.get("source_commit")
    candidate_commit = candidate.get("commit_sha")
    if not _producer_nonempty_text(root) or not all(isinstance(item, str) and GIT_OID.fullmatch(item) for item in (source_commit, candidate_commit)):
        record(data, errors, warnings, "direct evidence Git subject fields are missing or malformed", "subject_identity")
        return
    try:
        actual_root = _git(root, "rev-parse", "--show-toplevel")
        if binding_repository is None or not isinstance(binding_repository.get("origin"), str):
            raise OSError("embedded Core repository origin is missing")
        actual_origin = _git(root, "remote", "get-url", "origin")
        if _producer_normalize_remote_identity(actual_origin) != _producer_normalize_remote_identity(binding_repository["origin"]):
            raise OSError("physical Git origin does not match embedded Core repository binding")
        actual_source_commit = _git(root, "rev-parse", f"{source_commit}^{{commit}}")
        actual_candidate_commit = _git(root, "rev-parse", f"{candidate_commit}^{{commit}}")
        source_tree = _git(root, "rev-parse", f"{source_commit}^{{tree}}")
        candidate_tree = _git(root, "rev-parse", f"{candidate_commit}^{{tree}}")
        if actual_source_commit != source_commit or actual_candidate_commit != candidate_commit:
            raise OSError("Git subject is not the supplied immutable commit")
        ancestry = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", source_commit, candidate_commit], capture_output=True, timeout=10)
        if ancestry.returncode != 0:
            raise OSError("candidate commit is not descended from source commit")
        if candidate.get("source_tree") != source_tree or candidate.get("tree_sha") != candidate_tree:
            raise OSError("candidate commit/tree does not match physical Git object")
        physical = _physical_manifest(root, source_commit, candidate_commit)
        if physical != manifest:
            raise OSError("direct evidence manifest does not match physical Git diff")
        if candidate.get("diff_hash") != core_manifest_hash(physical):
            raise OSError("direct evidence diff_hash does not match the physical Core change manifest")
        warnings.append(f"physical Git subject verified at {actual_root}")
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        record(data, errors, warnings, f"physical Git cross-binding failed: {exc}", "subject_identity")


def validate_direct(data, evidence, verification, errors, warnings):
    source, repository = data["source"], data["repository"]
    if not isinstance(evidence, dict) or evidence.get("schema") != DIRECT_SCHEMA:
        record(data, errors, warnings, "direct executor evidence schema mismatch", "authority")
        return
    expected_keys = {"schema", "evidence_id", "created_at", "authority", "execution", "core_binding", "candidate", "claim", "integrity"}
    if set(evidence) != expected_keys:
        record(data, errors, warnings, "direct executor evidence top-level shape mismatch", "authority")
    if not _producer_nonempty_text(evidence.get("evidence_id")):
        record(data, errors, warnings, "direct executor evidence_id must be non-empty", "subject_identity")
    if not _producer_date_parseable(evidence.get("created_at")):
        record(data, errors, warnings, "direct executor created_at is not producer-parseable", "subject_identity")
    integrity = _obj(evidence.get("integrity"))
    if not exact(integrity, {"sha256"}) or integrity.get("sha256") != direct_integrity_sha256(evidence):
        record(data, errors, warnings, "direct executor evidence integrity mismatch", "subject_identity")
    identity = _direct_identity(evidence)
    auth, execution, core, candidate, claim = (_obj(evidence.get(name)) for name in ("authority", "execution", "core_binding", "candidate", "claim"))
    if not all((auth, execution, core, candidate, claim)):
        record(data, errors, warnings, "direct executor evidence nested groups must be objects", "authority")
        return
    auth_keys = {"authority_mode","execution_lane","task_id","attempt_id","dispatch_intent","dispatch_intent_hash","authority_ref","core_authority_hash"}
    execution_keys = {"protocol","execution_binding_hash","agent_id","profile","provider","model","effort","provider_session_id","execution_generation","workspace_id","workspace_root","state","terminal_reason","retry_safe","reconciliation_required","scope_state","started_at","completed_at"}
    core_keys = {"session_id","binding","binding_hash","acceptance_contract_hash"}
    candidate_keys = {"present","required","source_commit","source_tree","commit_sha","tree_sha","changed_paths","deleted_paths","diff_hash","change_manifest","provenance_created_at"}
    claim_keys = {"status","claim_ceiling","core_verified","certified","accepted","approved","merged","released","deployed","public_claim_allowed"}
    for label, value, keys in (("authority", auth, auth_keys), ("execution", execution, execution_keys), ("core_binding", core, core_keys), ("candidate", candidate, candidate_keys), ("claim", claim, claim_keys)):
        if not exact(value, keys):
            record(data, errors, warnings, f"direct executor evidence {label} shape mismatch", "authority" if label in {"authority", "core_binding"} else "subject_identity")
    if auth.get("authority_mode") != "OWNER_DIRECT" or auth.get("execution_lane") != "DIRECT_DELEGATED":
        record(data, errors, warnings, "direct evidence authority/lane mismatch", "authority")
    raw_intent = auth.get("dispatch_intent")
    dispatch_hash = auth.get("dispatch_intent_hash")
    try:
        intent = _normalize_dispatch_intent(raw_intent)
    except (ValueError, TypeError) as exc:
        intent = None
        record(data, errors, warnings, f"direct evidence dispatch_intent is invalid: {exc}", "authority")
    if intent is not None:
        if raw_intent != intent:
            record(data, errors, warnings, "direct evidence dispatch_intent is not in the committed producer-normalized shape", "authority")
        expected_dispatch_hash = _producer_canonical_sha256(intent)
        if dispatch_hash != expected_dispatch_hash:
            record(data, errors, warnings, "direct evidence dispatch_intent_hash mismatch", "authority")
        if auth.get("task_id") != intent.get("taskId") or auth.get("attempt_id") != intent.get("attemptId"):
            record(data, errors, warnings, "direct evidence authority task/attempt does not match dispatch intent", "authority")
        if intent.get("claimCeiling") != "CANDIDATE_READY":
            record(data, errors, warnings, "direct dispatch intent claim ceiling mismatch", "claim_discipline")
    if not isinstance(dispatch_hash, str) or not HEX64.fullmatch(dispatch_hash) or auth.get("core_authority_hash") != f"sha256:{dispatch_hash}":
        record(data, errors, warnings, "direct evidence Core authority hash mismatch", "authority")
    if not _producer_nonempty_text(auth.get("authority_ref")):
        record(data, errors, warnings, "direct evidence authority_ref is required", "authority")

    if execution.get("protocol") != "devspace.execution.v1" or execution.get("state") != "completed" or execution.get("reconciliation_required") is not False or execution.get("scope_state") != "WITHIN_SCOPE":
        record(data, errors, warnings, "direct execution is not durably completed within scope", "authority")
    if execution.get("terminal_reason") != "completed":
        record(data, errors, warnings, "direct execution terminal_reason must match committed producer value completed", "subject_identity")
    if execution.get("retry_safe") is not False:
        record(data, errors, warnings, "direct execution retry safety is not false", "authority")
    if not isinstance(execution.get("execution_binding_hash"), str) or not HEX64.fullmatch(execution.get("execution_binding_hash", "")):
        record(data, errors, warnings, "direct execution binding hash is malformed", "subject_identity")
    for key in ("agent_id", "profile", "provider", "workspace_id", "workspace_root", "terminal_reason"):
        if not _producer_nonempty_text(execution.get(key)):
            record(data, errors, warnings, f"direct execution {key} must be non-empty", "subject_identity")
    for key in ("model", "effort", "provider_session_id"):
        value = execution.get(key)
        if value is not None and not _producer_nonempty_text(value):
            record(data, errors, warnings, f"direct execution {key} must be null or non-empty", "subject_identity")
    for key in ("started_at", "completed_at"):
        value = execution.get(key)
        if not _producer_date_parseable(value):
            record(data, errors, warnings, f"direct execution {key} must be present and producer-parseable", "subject_identity")

    generation = _obj(execution.get("execution_generation"))
    if generation is None:
        record(data, errors, warnings, "direct execution_generation must be an object", "subject_identity")
    else:
        required_generation = ("profileCatalogGeneration", "provider", "executionIdentity", "devspaceBuildId", "devspaceSourceCommit", "capabilitySurfaceDigest", "executionBindingHash")
        optional_generation = {"model", "runtimeVersion"}
        allowed_generation = set(required_generation) | optional_generation
        if not set(required_generation).issubset(generation) or set(generation) - allowed_generation:
            record(data, errors, warnings, "direct execution_generation shape does not match committed producer binding", "subject_identity")
        if any(not isinstance(generation.get(key), str) for key in required_generation):
            record(data, errors, warnings, "direct execution_generation required fields must be strings", "subject_identity")
        for key in optional_generation:
            if key in generation and not isinstance(generation.get(key), str):
                record(data, errors, warnings, f"direct execution_generation {key} must be a string when present", "subject_identity")
        generation_payload = {key: generation[key] for key in required_generation[:-1] if key in generation}
        for key in ("model", "runtimeVersion"):
            if key in generation:
                generation_payload[key] = generation[key]
        if all(key in generation for key in required_generation):
            expected_capability_digest = _producer_canonical_sha256({
                "profileCatalogGeneration": generation.get("profileCatalogGeneration"),
                "devspaceBuildId": generation.get("devspaceBuildId"),
                "devspaceSourceCommit": generation.get("devspaceSourceCommit"),
            })
            if generation.get("capabilitySurfaceDigest") != expected_capability_digest:
                record(data, errors, warnings, "direct execution_generation capabilitySurfaceDigest does not match committed resolveExecutionGeneration path", "subject_identity")
            expected_generation_hash = _producer_canonical_sha256(generation_payload)
            if generation.get("executionBindingHash") != expected_generation_hash:
                record(data, errors, warnings, "direct execution_generation canonical hash mismatch", "subject_identity")
        if generation.get("executionBindingHash") != execution.get("execution_binding_hash"):
            record(data, errors, warnings, "direct execution generation hash does not cross-bind", "subject_identity")
        if isinstance(generation.get("provider"), str) and generation.get("provider") != execution.get("provider"):
            record(data, errors, warnings, "direct execution generation provider mismatch", "subject_identity")
        execution_model = execution.get("model")
        if execution_model is None:
            if "model" in generation:
                record(data, errors, warnings, "direct execution generation must omit model when execution.model is null", "subject_identity")
        elif generation.get("model") != execution_model:
            record(data, errors, warnings, "direct execution generation model mismatch or omission", "subject_identity")

    if candidate.get("present") is not True or candidate.get("required") is not True:
        record(data, errors, warnings, "direct Candidate must be present and required", "subject_identity")
    for key in ("source_commit", "source_tree", "commit_sha", "tree_sha"):
        value = candidate.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
            record(data, errors, warnings, f"direct Candidate {key} must be lowercase 40-hex", "subject_identity")
    if not _producer_date_parseable(candidate.get("provenance_created_at")):
        record(data, errors, warnings, "direct Candidate provenance_created_at is not producer-parseable", "subject_identity")
    if candidate.get("provenance_created_at") != evidence.get("created_at"):
        record(data, errors, warnings, "direct evidence created_at must equal Candidate provenance_created_at", "subject_identity")
    evidence_id_inputs = (execution.get("agent_id"), auth.get("attempt_id"), candidate.get("commit_sha"), candidate.get("diff_hash"))
    if all(isinstance(item, str) for item in evidence_id_inputs):
        expected_evidence_id = "dce_" + hashlib.sha256(":".join(evidence_id_inputs).encode("utf-8")).hexdigest()[:32]
        if evidence.get("evidence_id") != expected_evidence_id:
            record(data, errors, warnings, "direct evidence_id does not match committed producer identity projection", "subject_identity")
    if not isinstance(candidate.get("diff_hash"), str) or not CORE_HASH.fullmatch(candidate.get("diff_hash", "")):
        record(data, errors, warnings, "direct Candidate diff_hash must be sha256:<64 hex>", "subject_identity")
    if not isinstance(candidate.get("changed_paths"), list) or not all(isinstance(path, str) for path in candidate.get("changed_paths", [])):
        record(data, errors, warnings, "direct Candidate changed_paths must be a string array", "subject_identity")
    if not isinstance(candidate.get("deleted_paths"), list) or not all(isinstance(path, str) for path in candidate.get("deleted_paths", [])):
        record(data, errors, warnings, "direct Candidate deleted_paths must be a string array", "subject_identity")

    if claim.get("status") != "CANDIDATE_CAPTURED_PENDING_CORE_VERIFICATION_AND_ACCEPTANCE" or claim.get("claim_ceiling") != "CANDIDATE_READY":
        record(data, errors, warnings, "direct evidence claim ceiling/status mismatch", "claim_discipline")
    for key in ("core_verified", "certified", "accepted", "approved", "merged", "released", "deployed", "public_claim_allowed"):
        if claim.get(key) is not False:
            record(data, errors, warnings, f"direct evidence illegally asserts {key}", "claim_discipline")
    binding = _obj(core.get("binding"))
    if not isinstance(core.get("session_id"), str) or re.fullmatch(r"cms_[0-9a-f]{32}", core.get("session_id", "")) is None:
        record(data, errors, warnings, "direct Core session_id must match committed Core session identity", "authority")
    if not isinstance(core.get("binding_hash"), str) or not CORE_HASH.fullmatch(core.get("binding_hash", "")):
        record(data, errors, warnings, "direct Core binding_hash is malformed", "authority")
    if core.get("acceptance_contract_hash") != f"sha256:{source.get('contract_hash')}":
        record(data, errors, warnings, "direct Core binding contract hash mismatch", "authority")
    if binding is None:
        record(data, errors, warnings, "direct Core binding payload must be an object", "authority")
    else:
        for issue in _validate_core_binding_shape(binding):
            record(data, errors, warnings, issue, "authority")
        if binding.get("schema") != "nexus.repository_mutation_binding.v1":
            record(data, errors, warnings, "direct Core binding schema mismatch", "authority")
        if binding.get("operation_id") != auth.get("task_id") or binding.get("attempt_id") != auth.get("attempt_id"):
            record(data, errors, warnings, "direct Core binding task/attempt mismatch", "authority")
        binding_authority = _obj(binding.get("integration_authority"))
        if binding_authority is None or binding_authority.get("execution_lane") != "DIRECT_DELEGATED" or binding_authority.get("authority_hash") != auth.get("core_authority_hash") or binding_authority.get("authority_ref") != auth.get("authority_ref"):
            record(data, errors, warnings, "direct Core integration authority mismatch", "authority")
        if binding.get("binding_hash") != core.get("binding_hash"):
            record(data, errors, warnings, "direct Core binding hash does not match embedded binding", "authority")
        if core.get("binding_hash") != core_binding_hash(binding):
            record(data, errors, warnings, "direct Core binding canonical hash mismatch", "authority")
        binding_core = _obj(binding.get("core"))
        if binding_core is None or binding_core.get("acceptance_contract_hash") != core.get("acceptance_contract_hash"):
            record(data, errors, warnings, "direct Core acceptance contract does not match embedded binding", "authority")
        else:
            acceptance_contract = _obj(binding_core.get("acceptance_contract"))
            if acceptance_contract is None or binding_core.get("acceptance_contract_hash") != core_acceptance_contract_hash(acceptance_contract):
                record(data, errors, warnings, "direct Core AcceptanceContract canonical hash mismatch", "authority")
        binding_repository = _obj(binding.get("repository"))
        if binding_repository is None or binding_repository.get("source_revision") != f"git-commit:{candidate.get('source_commit')}" or binding_repository.get("source_tree") != f"git-tree:{candidate.get('source_tree')}":
            record(data, errors, warnings, "direct Candidate source does not match embedded Core repository binding", "subject_identity")
        elif isinstance(execution.get("workspace_id"), str):
            expected_workspace_identity = core_workspace_identity(execution["workspace_id"], binding_repository)
            if binding_repository.get("workspace_identity") != expected_workspace_identity:
                record(data, errors, warnings, "direct Core workspace_identity does not match exact workspace/source identity", "subject_identity")

    checks = {
        "task_id": (source.get("task_id"), identity["task_id"]),
        "attempt_id": (source.get("implementer_attempt_id"), identity["attempt_id"]),
        "contract_hash": (source.get("contract_hash"), identity["contract_hash"]),
        "root": (repository.get("root"), identity["root"]),
        "executor_observed_head": (repository.get("executor_observed_head"), identity["source_commit"]),
        "expected_base_commit": (repository.get("expected_base_commit"), identity["source_commit"]),
        "candidate_commit_sha": (repository.get("candidate_commit_sha"), identity["candidate_commit"]),
        "candidate_tree_sha": (repository.get("candidate_tree_sha"), identity["candidate_tree"]),
        "candidate_diff_sha256": (repository.get("candidate_diff_sha256"), _hex_or_ref(identity["diff_hash"])),
    }
    for name, (left, right) in checks.items():
        if left != right:
            record(data, errors, warnings, f"direct evidence {name} mismatch", "subject_identity" if name not in {"task_id", "attempt_id", "contract_hash"} else "authority")
    if identity["core_contract_hash"] not in {source.get("contract_hash"), f"sha256:{source.get('contract_hash')}"}:
        record(data, errors, warnings, "direct Core binding contract hash mismatch", "authority")
    manifest = candidate.get("change_manifest") or evidence.get("change_manifest")
    manifest_errors: list[str] = []
    source_tree = identity["source_tree"]
    candidate_tree = identity["candidate_tree"]
    if not _validate_manifest(manifest, source_tree, candidate_tree, manifest_errors):
        for item in manifest_errors:
            record(data, errors, warnings, item, "subject_identity")
    elif manifest is not None:
        _validate_git_cross_binding(data, evidence, manifest, errors, warnings)
        manifest_paths = [row["path"] for row in manifest.get("entries", []) if isinstance(row, dict) and isinstance(row.get("path"), str)]
        deleted_manifest_paths = [row["path"] for row in manifest.get("entries", []) if isinstance(row, dict) and row.get("change_type") == "DELETE" and isinstance(row.get("path"), str)]
        if identity["changed_paths"] != manifest_paths:
            record(data, errors, warnings, "direct evidence changed paths do not match physical manifest", "subject_identity")
        if identity["deleted_paths"] != deleted_manifest_paths:
            record(data, errors, warnings, "direct evidence deleted paths do not match physical manifest", "subject_identity")
        bound_core = _obj(binding.get("core")) if isinstance(binding, dict) else None
        bound_contract = _obj(bound_core.get("acceptance_contract")) if bound_core else None
        if bound_contract is not None:
            allowed_paths = bound_contract.get("allowed_paths")
            if isinstance(allowed_paths, list):
                escaped = [path for path in manifest_paths if path not in set(allowed_paths)]
                if escaped:
                    record(data, errors, warnings, "direct Candidate physical manifest escapes AcceptanceContract allowed_paths: " + ", ".join(escaped), "authority")
            if bound_contract.get("deletion_policy") == "FORBID" and deleted_manifest_paths:
                record(data, errors, warnings, "direct Candidate deletes paths while AcceptanceContract deletion_policy=FORBID", "authority")
    if not isinstance(verification, dict) or verification.get("schema") != CORE_RESPONSE_SCHEMA:
        record(data, errors, warnings, "Core generic verification schema mismatch", "authority")
        return
    if set(verification) != {"protocol_version", "schema", "verification", "hashes", "certification"}:
        record(data, errors, warnings, "Core generic verification response shape mismatch", "authority")
    if verification.get("protocol_version") != CORE_PROTOCOL_VERSION:
        record(data, errors, warnings, "Core generic verification protocol version mismatch", "authority")
    ver, hashes = _obj(verification.get("verification")), _obj(verification.get("hashes"))
    if not ver or not hashes:
        record(data, errors, warnings, "Core generic verification nested groups must be objects", "authority")
        return
    if set(ver) != {"status", "reason_codes", "integrity"}:
        record(data, errors, warnings, "Core generic verification payload shape mismatch", "authority")
    if ver.get("status") != "VERIFIED":
        record(data, errors, warnings, "Core generic verification is not VERIFIED", "independent_behavior")
    if ver.get("reason_codes") != [] or ver.get("integrity") != "VALID":
        record(data, errors, warnings, "Core VERIFIED response must have empty reason_codes and VALID integrity", "independent_behavior")
    expected_hash_keys = {"acceptance_contract_hash", "change_set_hash", "verification_plan_hash", "evidence_bundle_hash", "change_manifest_hash"}
    if set(hashes) != expected_hash_keys or not all(isinstance(hashes.get(key), str) and CORE_HASH.fullmatch(hashes.get(key, "")) for key in expected_hash_keys):
        record(data, errors, warnings, "Core generic verification hash set is malformed or has unexpected fields", "subject_identity")
    if hashes.get("acceptance_contract_hash") != f"sha256:{source.get('contract_hash')}":
        record(data, errors, warnings, "Core verification contract hash mismatch", "authority")
    if isinstance(manifest, dict) and _validate_manifest(manifest, source_tree, candidate_tree, [], prefix="candidate.change_manifest") and hashes.get("change_manifest_hash") != core_manifest_hash(manifest):
        record(data, errors, warnings, "Core verification change manifest mismatch", "subject_identity")
    certification = verification.get("certification")
    if certification is not None:
        if not isinstance(certification, dict) or set(certification) != {"disposition", "receipt"} or certification.get("disposition") not in {"CERTIFIED", "REJECTED", "BLOCKED"} or not isinstance(certification.get("receipt"), dict):
            record(data, errors, warnings, "Core generic verification certification payload violates committed response schema", "authority")
        else:
            warnings.append("Core response includes separate certification material; Candidate Acceptance does not inherit certification authority")


def _validate_v3_report(data: dict[str, Any], report: Any, executor_path: Path, errors: list[str], warnings: list[str]) -> None:
    """Require the real historical report shape and re-run the unchanged v3 oracle.

    The historical validator emits only schema/valid/errors/warnings.  v4 therefore
    does not invent a ``bound_inputs`` extension; instead it projects the exact v4
    result into the v3 contract and rechecks the physical MCP receipt with the
    unchanged validator.  This closes the forged-minimal-report hole while keeping
    legitimate historical reports compatible.
    """
    if not isinstance(report, dict) or set(report) != {"schema", "valid", "errors", "warnings"}:
        record(data, errors, warnings, "v3 compatibility report is not an emitted historical report", "authority")
        return
    if report.get("schema") != "nexus.candidate_acceptance.validation.v3" or report.get("valid") is not True:
        record(data, errors, warnings, "v3 compatibility validation did not pass", "authority")
        return
    if not isinstance(report.get("errors"), list) or not isinstance(report.get("warnings"), list):
        record(data, errors, warnings, "v3 compatibility report errors/warnings must be arrays", "authority")
        return
    validator_path = Path(__file__).with_name("validate_acceptance_result.py")
    spec = importlib.util.spec_from_file_location("nexus_candidate_acceptance_v3", validator_path)
    if spec is None or spec.loader is None:
        record(data, errors, warnings, "unchanged v3 validator could not be loaded", "authority")
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    projected = copy.deepcopy(data)
    projected["schema"] = "nexus.candidate_acceptance.v3"
    projected_source = projected["source"]
    projected_source.pop("executor_evidence_kind", None)
    projected_source.pop("executor_evidence_sha256", None)
    projected_source.pop("verification_evidence_kind", None)
    projected_source.pop("verification_evidence_sha256", None)
    projected_source["executor_receipt_sha256"] = data["source"]["executor_evidence_sha256"]
    projected["integrity"]["sha256"] = module.canonical_sha256(projected)
    fresh = module.validate(projected)
    if fresh.get("valid"):
        bind_errors, bind_warnings = module.validate_source_bindings(
            projected,
            task_card=None,
            packet_path=None,
            manifest_path=None,
            receipt_path=executor_path,
            runtime_admission_path=None,
        )
        fresh["errors"].extend(bind_errors)
        fresh["warnings"].extend(bind_warnings)
        fresh["valid"] = not fresh["errors"]
    if fresh.get("valid") is not True or report.get("errors") != fresh.get("errors", []):
        record(data, errors, warnings, "v3 compatibility report does not match the unchanged v3 oracle for these exact inputs", "authority")


def validate_mcp(data, executor, verification, args, errors, warnings):
    executor_id = _check_mcp_receipt(data, executor, errors, warnings, label="MCP executor")
    verification_id = _check_mcp_receipt(data, verification, errors, warnings, label="MCP verified receipt")
    if executor_id is None or verification_id is None:
        return
    source, repository = data["source"], data["repository"]
    expected = {
        "contract_kind": source.get("contract_kind"), "campaign_id": source.get("campaign_id"),
        "task_id": source.get("task_id"), "contract_hash": source.get("contract_hash"),
        "attempt_id": source.get("implementer_attempt_id"), "root": repository.get("root"),
        "executor_observed_head": repository.get("executor_observed_head"), "expected_base_commit": repository.get("expected_base_commit"),
        "candidate_commit_sha": repository.get("candidate_commit_sha"), "candidate_tree_sha": repository.get("candidate_tree_sha"),
        "candidate_state_hash": repository.get("candidate_state_hash"), "candidate_diff_sha256": repository.get("candidate_diff_sha256"),
        "verified_receipt_hash": repository.get("verified_receipt_hash"),
    }
    for key, value in expected.items():
        if executor_id.get(key) != value:
            record(data, errors, warnings, f"MCP executor {key} mismatch", "subject_identity" if key not in {"contract_kind", "campaign_id", "task_id", "contract_hash", "attempt_id"} else "authority")
        if verification_id.get(key) != executor_id.get(key):
            record(data, errors, warnings, f"MCP verification {key} does not cross-bind to executor", "subject_identity")
    if args.v3_validation_report is None:
        errors.append("NEXUS_MCP_RECEIPT requires --v3-validation-report proving unchanged v3 lineage semantics")
    else:
        _validate_v3_report(data, read_json(args.v3_validation_report), args.executor_evidence, errors, warnings)


def validate_physical(data, args):
    errors, warnings = [], []
    source = data.get("source", {}) if isinstance(data.get("source"), dict) else {}
    try:
        if args.executor_evidence is None:
            errors.append("--executor-evidence is required for v4 physical binding")
            return errors, warnings
        if args.verification_evidence is None:
            errors.append("--verification-evidence is required for v4 physical binding")
            return errors, warnings
        executor_digest = file_sha256(args.executor_evidence)
        verification_digest = file_sha256(args.verification_evidence)
        if executor_digest != source.get("executor_evidence_sha256"):
            record(data, errors, warnings, "executor evidence digest mismatch", "subject_identity")
        if verification_digest != source.get("verification_evidence_sha256"):
            record(data, errors, warnings, "verification evidence digest mismatch", "subject_identity")
        executor, verification = read_json(args.executor_evidence), read_json(args.verification_evidence)
        if source.get("executor_evidence_kind") == "DEVSPACE_DIRECT_EVIDENCE":
            validate_direct(data, executor, verification, errors, warnings)
        elif source.get("executor_evidence_kind") == "NEXUS_MCP_RECEIPT":
            validate_mcp(data, executor, verification, args, errors, warnings)
        else:
            record(data, errors, warnings, "unsupported executor evidence branch", "authority")
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateKeyError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        record(data, errors, warnings, f"physical binding failed: {type(exc).__name__}: {exc}", "authority")
    return errors, warnings

def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("result", type=Path); p.add_argument("--executor-evidence", type=Path); p.add_argument("--verification-evidence", type=Path); p.add_argument("--v3-validation-report", type=Path); p.add_argument("--report", type=Path)
    return p.parse_args()

def main():
    args = parse_args()
    try: data = read_json(args.result)
    except Exception as exc: report = {"schema": VALIDATION_SCHEMA,"valid":False,"errors":[f"malformed result: {type(exc).__name__}: {exc}"],"warnings":[]}
    else:
        try:
            report = validate(data)
            if report["valid"]:
                pe, pw = validate_physical(data, args)
                report["errors"].extend(pe)
                report["warnings"].extend(pw)
                report["valid"] = not report["errors"]
        except Exception as exc:
            report = {"schema": VALIDATION_SCHEMA,"valid":False,"errors":[f"malformed nested input: {type(exc).__name__}: {exc}"],"warnings":[]}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True)); return 0 if report["valid"] else 2

if __name__ == "__main__": raise SystemExit(main())
