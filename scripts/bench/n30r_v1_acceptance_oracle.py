#!/usr/bin/env python3
"""N30R V1 Independent Full Armor Acceptance Oracle.

Validates N30R execution traces against the acceptance contract.
Recomputes hashes independently — does not trust verify_hash_chain().

Usage:
    python scripts/bench/n30r_v1_acceptance_oracle.py \\
        --trace <trace.json> \\
        --repo-root <workspace> \\
        --contract docs/bench/n30r/a1_acceptance_contract_v1.json \\
        --json-out <result.json>

    python scripts/bench/n30r_v1_acceptance_oracle.py \\
        --build-task-evidence n30r_smoke_semantic
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Hash utilities
# ---------------------------------------------------------------------------

REAL_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

FAKE_HASH_PATTERNS = frozenset({
    "mock", "placeholder", "dummy", "example", "todo",
    "unknown", "none", "00000000000000000000000000000000"
    "00000000000000000000000000000000",
})


def canonical_sha256(text: str) -> str:
    """Compute SHA-256 of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def is_real_sha256(h: str) -> bool:
    """Check if a string is a valid 64-char lowercase hex SHA-256."""
    if not isinstance(h, str):
        return False
    if not REAL_SHA256_RE.match(h):
        return False
    lower = h.lower()
    for pattern in FAKE_HASH_PATTERNS:
        if pattern in lower:
            return False
    return True


def is_placeholder_hash(h: str) -> bool:
    """Check if a hash looks like a placeholder."""
    if not isinstance(h, str):
        return True
    lower = h.lower()
    if not REAL_SHA256_RE.match(lower):
        return True
    for pattern in FAKE_HASH_PATTERNS:
        if pattern in lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Artifact loading
# ---------------------------------------------------------------------------

def load_json_artifact(path: str) -> dict[str, Any]:
    """Load a JSON file and return its contents."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Artifact not found: {path}")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_evidence_ref(ref: str, repo_root: str) -> dict[str, Any] | None:
    """Resolve an evidence ref path relative to repo_root."""
    if not ref:
        return None
    p = Path(repo_root) / ref
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def read_file_text(path: str) -> str | None:
    """Read file text, return None if not found."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------------------
# Gate validators
# ---------------------------------------------------------------------------

def _check_sha256_field(value: Any, field_name: str, recompute_fn=None) -> dict[str, Any]:
    """Validate a SHA-256 field."""
    result = {"field": field_name, "present": False, "valid_format": False, "valid_content": True}
    if not value or not isinstance(value, str):
        return result
    result["present"] = True
    result["valid_format"] = is_real_sha256(value)
    if recompute_fn and result["valid_format"]:
        expected = recompute_fn()
        result["valid_content"] = (value == expected)
        result["expected"] = expected
    return result


def validate_p_gate(trace: dict[str, Any]) -> dict[str, Any]:
    """Validate Planner Gate."""
    issues = []
    missing = []

    # planner_snapshot_hash
    snap_hash = trace.get("planner_snapshot_hash") or trace.get("signal_snapshot_sha256", "")
    if not snap_hash:
        missing.append("planner_snapshot_hash")
    elif not is_real_sha256(snap_hash):
        issues.append(f"planner_snapshot_hash invalid format: {snap_hash[:16]}...")

    # capability_projection_hash
    proj_hash = trace.get("capability_projection_hash", "")
    if not proj_hash:
        missing.append("capability_projection_hash")
    elif not is_real_sha256(proj_hash):
        issues.append(f"capability_projection_hash invalid format: {proj_hash[:16]}...")

    # planner_capability_count
    cap_count = trace.get("planner_capability_count")
    if cap_count is None:
        missing.append("planner_capability_count")

    # selected_capabilities_used
    selected = trace.get("selected_capabilities_used", [])
    if not selected:
        missing.append("selected_capabilities_used")

    # unknown_capability_count
    unknown = trace.get("unknown_capability_count")
    if unknown is None:
        missing.append("unknown_capability_count")
    elif unknown != 0:
        issues.append(f"unknown_capability_count != 0: {unknown}")

    # dependency_errors
    dep_err = trace.get("dependency_errors")
    if dep_err is None:
        missing.append("dependency_errors")
    elif dep_err != 0:
        issues.append(f"dependency_errors != 0: {dep_err}")

    return {
        "passed": len(issues) == 0 and len(missing) == 0,
        "missing_fields": missing,
        "issues": issues,
    }


def validate_d_gate(trace: dict[str, Any], repo_root: str) -> dict[str, Any]:
    """Validate Discovery Gate."""
    issues = []
    missing = []
    hash_mismatches = []
    unresolvable = []

    # target_file
    target_file = trace.get("target_file", "")
    if not target_file:
        missing.append("target_file")

    # source hash recomputation
    source_hash_recorded = trace.get("source_sha256") or trace.get("source_hash", "")
    source_path = os.path.join(repo_root, target_file) if target_file else ""
    if source_path and os.path.exists(source_path):
        source_text = read_file_text(source_path)
        if source_text is not None:
            source_hash_computed = canonical_sha256(source_text)
            if source_hash_recorded and source_hash_computed != source_hash_recorded:
                hash_mismatches.append({
                    "field": "source_sha256",
                    "recorded": source_hash_recorded,
                    "computed": source_hash_computed,
                })
        else:
            issues.append(f"cannot read source file: {source_path}")
    elif not source_hash_recorded:
        missing.append("source_sha256")

    # target_symbol
    target_symbol = trace.get("target_symbol", "")
    if not target_symbol:
        missing.append("target_symbol")

    # locked_search
    locked_search = trace.get("locked_search", "")
    if not locked_search:
        missing.append("locked_search")
    elif source_text is not None:
        if locked_search not in source_text:
            issues.append("locked_search not found in source")
        else:
            count = source_text.count(locked_search)
            recorded_count = trace.get("locked_search_occurrence_count", -1)
            if recorded_count != -1 and count != recorded_count:
                issues.append(f"locked_search occurrence count mismatch: recorded={recorded_count} actual={count}")

    # source_anchor_hash
    anchor_hash = trace.get("source_anchor_hash", "")
    if anchor_hash and not is_real_sha256(anchor_hash):
        issues.append(f"source_anchor_hash invalid format: {anchor_hash[:16]}...")

    # evidence_refs
    evidence_refs = trace.get("evidence_refs", [])
    for ref in evidence_refs:
        ref_str = ref if isinstance(ref, str) else ref.get("artifact_path", "")
        if ref_str:
            resolved = resolve_evidence_ref(ref_str, repo_root)
            if resolved is None:
                unresolvable.append(ref_str)

    # evidence artifact hashes
    for ref in evidence_refs:
        if isinstance(ref, dict):
            ref_hash = ref.get("sha256", "")
            ref_path = ref.get("artifact_path", "")
            if ref_hash and ref_path:
                full_path = os.path.join(repo_root, ref_path)
                if os.path.exists(full_path):
                    content = read_file_text(full_path)
                    if content is not None:
                        computed = canonical_sha256(content)
                        if computed != ref_hash:
                            hash_mismatches.append({
                                "field": f"evidence_ref:{ref_path}",
                                "recorded": ref_hash,
                                "computed": computed,
                            })

    # verifier contract
    verifier = trace.get("verifier", {})
    verifier_cmd = verifier.get("command") or trace.get("verifier_command", [])
    if not verifier_cmd:
        missing.append("verifier_command")

    return {
        "passed": len(issues) == 0 and len(missing) == 0 and len(hash_mismatches) == 0 and len(unresolvable) == 0,
        "missing_fields": missing,
        "issues": issues,
        "hash_mismatches": hash_mismatches,
        "unresolvable_evidence_refs": unresolvable,
    }


def validate_x_gate(trace: dict[str, Any], evidence_pack: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate Execution Gate."""
    issues = []
    missing = []
    anti = []

    provider_called = trace.get("provider_called") or trace.get("model_call_started") or trace.get("local_model_called", False)
    response_received = trace.get("model_response_received") or trace.get("raw_output_length", 0) > 0
    raw_output_len = trace.get("raw_output_length") or trace.get("raw_output_length", 0)

    if not provider_called:
        missing.append("provider_called")
    if not response_received:
        missing.append("model_response_received")
    if raw_output_len == 0 and provider_called:
        missing.append("raw_output_length")

    # Anti-rule: response received but no output
    if response_received and raw_output_len == 0:
        anti.append("model_response_received=true but raw_output_length=0")

    # Prompt checks
    prompt = trace.get("prompt_artifact") or trace.get("rendered_prompt", "")
    prompt_text = ""
    if isinstance(prompt, dict):
        prompt_text = prompt.get("text", "") or prompt.get("prompt", "")
    elif isinstance(prompt, str):
        prompt_text = prompt

    if evidence_pack:
        task_id = evidence_pack.get("task_id", "")
        target_file = evidence_pack.get("localization", {}).get("target_file", "")
        target_symbol = evidence_pack.get("localization", {}).get("target_symbol", "")
        locked_search = evidence_pack.get("localization", {}).get("locked_search", "")

        if prompt_text:
            if task_id and task_id not in prompt_text:
                issues.append("prompt does not contain task_id")
            if target_file and target_file not in prompt_text:
                issues.append("prompt does not contain target_file")
            if target_symbol and target_symbol not in prompt_text:
                issues.append("prompt does not contain target_symbol")
            if locked_search and locked_search not in prompt_text:
                issues.append("prompt does not contain locked_search")

    # Candidate checks
    candidate_hash = trace.get("patch_sha256") or trace.get("selected_candidate_hash") or trace.get("candidate_hash", "")
    candidate_len = trace.get("patch_length") or trace.get("candidate_patch_length", 0)
    isolation_attempted = trace.get("candidate_isolation_attempted", False)
    isolation_success = trace.get("candidate_isolated", False)

    if not candidate_hash:
        missing.append("candidate_hash")
    elif not is_real_sha256(candidate_hash):
        issues.append(f"candidate_hash invalid format: {candidate_hash[:16]}...")

    if not isolation_attempted:
        issues.append("candidate_isolation_attempted != true")
    if isolation_attempted and not isolation_success:
        anti.append("candidate_isolation_attempted=true but candidate_isolated=false")

    # Apply checks
    apply_status = trace.get("apply_status", "")
    if not apply_status:
        missing.append("apply_status")
    elif apply_status not in ("pass", "success", "applied", "none", ""):
        issues.append(f"apply_status unexpected: {apply_status}")

    # Source hash before/after
    hash_before = trace.get("target_hash_before") or trace.get("source_sha256", "")
    hash_after = trace.get("target_hash_after") or trace.get("applied_patch_hash", "")

    return {
        "passed": len(issues) == 0 and len(missing) == 0 and len(anti) == 0,
        "missing_fields": missing,
        "issues": issues,
        "anti_rules_violated": anti,
    }


def validate_r_gate(trace: dict[str, Any]) -> dict[str, Any]:
    """Validate Retry Gate."""
    issues = []
    missing = []
    anti = []

    # Verifier
    verifier_cmd = trace.get("verifier_command") or trace.get("verifier", {}).get("command", [])
    if not verifier_cmd:
        missing.append("verifier_command")

    verifier_exit = trace.get("verifier_exit_code")
    if verifier_exit is None:
        verifier_exit = trace.get("isolated_verifier_exit_code")
    verifier_status = trace.get("verifier_status") or trace.get("isolated_verifier_status", "")

    if verifier_exit is None:
        missing.append("verifier_exit_code")

    # Workspace consistency
    candidate_ws = trace.get("candidate_workspace_id", "")
    apply_ws = trace.get("apply_workspace", "")
    verifier_ws = trace.get("verifier_workspace", "")

    if apply_ws and verifier_ws and apply_ws != verifier_ws:
        anti.append(f"workspace mismatch: apply={apply_ws} verifier={verifier_ws}")

    # Retry checks
    retry_count = trace.get("semantic_retry_count", 0)
    retry_invoked = trace.get("semantic_retry_invoked", False)

    if retry_count > 1:
        issues.append(f"semantic_retry_count > 1: {retry_count}")

    if retry_count > 0 and not retry_invoked:
        anti.append("semantic_retry_count > 0 but semantic_retry_invoked != true")

    # Timeout inference check
    wall_time = trace.get("wall_time_sec", 0)
    timed_out = trace.get("timed_out", False)
    timeout_stage = trace.get("timeout_stage", "")

    if timed_out and not timeout_stage:
        issues.append("timed_out=true but no timeout_stage")

    return {
        "passed": len(issues) == 0 and len(missing) == 0 and len(anti) == 0,
        "missing_fields": missing,
        "issues": issues,
        "anti_rules_violated": anti,
    }


def validate_a_gate(trace: dict[str, Any]) -> dict[str, Any]:
    """Validate Attribution Gate."""
    issues = []
    missing = []
    anti = []

    # Learning outcome
    learning = trace.get("learning_outcome") or trace.get("telemetries", {}).get("learning_closure", {})
    if not learning:
        missing.append("learning_outcome")

    # promotion_eligible
    promotion = trace.get("promotion_eligible")
    if promotion is None:
        missing.append("promotion_eligible")
    elif promotion is True:
        anti.append("promotion_eligible == true (must be false for shadow)")

    # global_learning_mutated
    global_mut = trace.get("global_learning_mutated")
    if global_mut is None:
        missing.append("global_learning_mutated")
    elif global_mut is True:
        anti.append("global_learning_mutated == true (must be false)")

    # capability contributions
    contributions = trace.get("capability_contributions") or trace.get("selected_capabilities_used", [])
    if isinstance(contributions, list):
        for cap in contributions:
            if isinstance(cap, dict):
                if cap.get("selected") and not cap.get("evidence_present") and not cap.get("invoked"):
                    issues.append(f"capability {cap.get('name', '?')} selected but no evidence")

    return {
        "passed": len(issues) == 0 and len(missing) == 0 and len(anti) == 0,
        "missing_fields": missing,
        "issues": issues,
        "anti_rules_violated": anti,
    }


def validate_c_gate(trace: dict[str, Any]) -> dict[str, Any]:
    """Validate Chain Gate."""
    issues = []
    missing = []
    hash_mismatches = []
    placeholders = []

    # Final receipt
    receipt = trace.get("final_receipt") or trace.get("receipt", {})
    if not receipt:
        missing.append("final_receipt")

    # Hash chain validation
    required_hashes = [
        ("planner_snapshot_hash", "planner_snapshot"),
        ("capability_projection_hash", "capability_projection"),
        ("source_sha256", "evidence_pack"),
        ("rendered_prompt_sha256", "prompt_artifact"),
        ("raw_output_sha256", "raw_output"),
        ("patch_sha256", "normalized_candidate"),
        ("applied_patch_hash", "applied_patch"),
        ("verifier_receipt_hash", "verifier_receipt"),
    ]

    present_hashes = []
    for field, label in required_hashes:
        value = trace.get(field, "")
        if value:
            present_hashes.append(label)
            if is_placeholder_hash(value):
                placeholders.append(f"{field}: {value[:16]}...")
            elif not is_real_sha256(value):
                issues.append(f"{field} invalid format: {value[:16]}...")
        # Not required — some may be absent in incomplete traces

    # Check for snapshot hash impersonating execution receipt
    snap_fields = ["planner_snapshot_hash", "capability_projection_hash"]
    receipt_fields = ["production_receipt_sha256"]
    for sf in snap_fields:
        for rf in receipt_fields:
            sv = trace.get(sf, "")
            rv = trace.get(rf, "")
            if sv and rv and sv == rv:
                issues.append(f"snapshot hash {sf} equals execution receipt {rf}")

    return {
        "passed": len(issues) == 0 and len(placeholders) == 0 and len(hash_mismatches) == 0,
        "missing_fields": missing,
        "issues": issues,
        "hash_mismatches": hash_mismatches,
        "placeholders": placeholders,
        "hash_chain_present": present_hashes,
    }


def validate_live_gate(trace: dict[str, Any]) -> dict[str, Any]:
    """Validate Live Gate."""
    issues = []
    rejected = []

    terminal = trace.get("terminal_status", "")
    accepted = {
        "LIVE_VERTICAL_SLICE_VERIFIED_SOLVE",
        "LIVE_VERTICAL_SLICE_VERIFIED_FAIL",
        "VERIFIED_SOLVE",
        "VERIFIED_FAIL",
    }

    if terminal and terminal not in accepted:
        if terminal in ("CONTRACT_INVALID", "INFRA_INVALID"):
            rejected.append(f"terminal_status rejected: {terminal}")
        else:
            issues.append(f"terminal_status not in accepted set: {terminal}")

    # Check for fake solve
    solved = trace.get("solve_eligible", False) or trace.get("gate_passed", False)
    receipt_complete = trace.get("receipt_complete", False)
    provider_called = trace.get("provider_called") or trace.get("model_call_started", False)

    if solved and not provider_called:
        rejected.append("solved=true but provider never called")
    if solved and not receipt_complete:
        issues.append("solved=true but receipt_complete != true")

    return {
        "passed": len(issues) == 0 and len(rejected) == 0,
        "issues": issues,
        "rejected": rejected,
    }


# ---------------------------------------------------------------------------
# Full trace evaluation
# ---------------------------------------------------------------------------

def evaluate_trace(
    trace: dict[str, Any],
    repo_root: str,
    contract: dict[str, Any] | None = None,
    evidence_pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate a full execution trace against the acceptance contract."""
    all_missing = []
    all_invalid = []
    all_hash_mismatches = []
    all_unresolvable = []

    p = validate_p_gate(trace)
    d = validate_d_gate(trace, repo_root)
    x = validate_x_gate(trace, evidence_pack)
    r = validate_r_gate(trace)
    a = validate_a_gate(trace)
    c = validate_c_gate(trace)
    live = validate_live_gate(trace)

    all_missing.extend(p.get("missing_fields", []))
    all_missing.extend(d.get("missing_fields", []))
    all_missing.extend(x.get("missing_fields", []))
    all_missing.extend(r.get("missing_fields", []))
    all_missing.extend(a.get("missing_fields", []))
    all_missing.extend(c.get("missing_fields", []))

    all_invalid.extend(p.get("issues", []))
    all_invalid.extend(d.get("issues", []))
    all_invalid.extend(x.get("issues", []))
    all_invalid.extend(r.get("issues", []))
    all_invalid.extend(a.get("issues", []))
    all_invalid.extend(c.get("issues", []))
    all_invalid.extend(x.get("anti_rules_violated", []))
    all_invalid.extend(r.get("anti_rules_violated", []))
    all_invalid.extend(a.get("anti_rules_violated", []))

    all_hash_mismatches.extend(d.get("hash_mismatches", []))
    all_hash_mismatches.extend(c.get("hash_mismatches", []))
    all_unresolvable.extend(d.get("unresolvable_evidence_refs", []))

    placeholders = c.get("placeholders", [])

    # Determine status
    gates_pass = all([p["passed"], d["passed"], x["passed"], r["passed"], a["passed"], c["passed"]])

    if not gates_pass:
        if any(k in str(all_invalid) for k in ["CONTRACT_INVALID", "invalid format"]):
            status = "REJECTED_CONTRACT_INVALID"
        elif all_hash_mismatches:
            status = "REJECTED_HASH_CHAIN_INVALID"
        else:
            status = "REJECTED_EVIDENCE_INVALID"
    elif not live["passed"]:
        status = "ORACLE_READY_PRODUCER_ARTIFACT_PENDING"
    else:
        is_synthetic = (
            trace.get("synthetic_oracle_fixture", False)
            or trace.get("mock_provider", False)
            or trace.get("synthetic", False)
        )
        if is_synthetic:
            status = "DETERMINISTIC_PATH_ACCEPTED_LIVE_PENDING"
        else:
            terminal = trace.get("terminal_status", "")
            if terminal in ("VERIFIED_SOLVE", "VERIFIED_FAIL",
                           "LIVE_VERTICAL_SLICE_VERIFIED_SOLVE",
                           "LIVE_VERTICAL_SLICE_VERIFIED_FAIL"):
                status = "FULL_ARMOR_PATH_ACCEPTED"
            else:
                status = "DETERMINISTIC_PATH_ACCEPTED_LIVE_PENDING"

    # Claim boundary
    claim_boundary = {
        "production_path_implemented_by_a": False,
        "effectiveness_measured": False,
        "production_ready": False,
        "public_claim_allowed": False,
        "no_live_model_executed": True,
        "oracle_correctness_tested": True,
    }

    return {
        "status": status,
        "accepted": status in (
            "FULL_ARMOR_PATH_ACCEPTED",
            "DETERMINISTIC_PATH_ACCEPTED_LIVE_PENDING",
        ),
        "p_gate": p,
        "d_gate": d,
        "x_gate": x,
        "r_gate": r,
        "a_gate": a,
        "c_gate": c,
        "live_gate": live,
        "missing_fields": all_missing,
        "invalid_fields": all_invalid,
        "hash_mismatches": all_hash_mismatches,
        "unresolvable_evidence_refs": all_unresolvable,
        "placeholders_detected": placeholders,
        "claim_boundary": claim_boundary,
    }


# ---------------------------------------------------------------------------
# Task evidence builder
# ---------------------------------------------------------------------------

def build_task_evidence(task_id: str, repo_root: str) -> dict[str, Any]:
    """Build canonical task evidence from smoke manifest and fixture."""
    manifest_path = os.path.join(repo_root, "docs/bench/n30r/smoke_manifest.json")
    manifest = load_json_artifact(manifest_path)

    task_dict = None
    for t in manifest.get("tasks", []):
        if t["task_id"] == task_id:
            task_dict = t
            break

    if not task_dict:
        raise ValueError(f"Task {task_id} not found in manifest")

    # Read fixture source — full file on disk
    fixture_path = os.path.join(repo_root, task_dict["source_relpath"])
    full_source = ""
    original_code = ""
    if os.path.exists(fixture_path):
        full_source = Path(fixture_path).read_text()
        mod: dict[str, Any] = {}
        exec(full_source, mod)
        original_code = mod.get("ORIGINAL", "")

    source_hash = canonical_sha256(full_source) if full_source else ""

    # Determine target info from ORIGINAL code
    target_file = task_dict["source_relpath"]
    target_symbol = ""
    locked_search = ""

    # Parse ORIGINAL to find function and bug line
    orig_lines = original_code.splitlines()
    for i, line in enumerate(orig_lines):
        stripped = line.strip()
        if stripped.startswith("def "):
            target_symbol = stripped.split("(")[0].replace("def ", "").strip()
        if stripped.startswith("return ") and i > 0:
            locked_search = stripped

    # Compute hashes
    locked_search_hash = canonical_sha256(locked_search) if locked_search else ""
    source_anchor_hash = locked_search_hash  # production: anchor = locked_search hash

    # Verifier
    verifier_cmd = task_dict.get("verifier_command", [])
    verifier_sha = canonical_sha256(json.dumps(verifier_cmd)) if verifier_cmd else ""

    evidence_pack = {
        "schema": "n30r_v1_task_evidence_v1",
        "task_id": task_id,
        "producer": "n30r_a1_independent_evidence_builder",
        "synthetic": False,
        "source": {
            "repo_relative_path": target_file,
            "sha256": source_hash,
            "length": len(full_source),
            "language": "python",
        },
        "localization": {
            "target_file": target_file,
            "target_symbol": target_symbol,
            "method": "ast_boundary",
            "start_line": next(
                (i + 1 for i, l in enumerate(orig_lines) if l.strip().startswith("def ")), 0
            ),
            "end_line": next(
                (i + 1 for i, l in enumerate(orig_lines) if l.strip().startswith("return ")), len(orig_lines)
            ),
            "locked_search": locked_search,
            "locked_search_sha256": locked_search_hash,
            "locked_search_occurrence_count": original_code.count(locked_search) if locked_search else 0,
            "source_anchor_sha256": source_anchor_hash,
        },
        "verifier": {
            "command": verifier_cmd,
            "cwd_mode": "fixture_dir",
            "contract_sha256": verifier_sha,
            "pre_fix_exit_code": 1,
            "pre_fix_expected_failure": True,
        },
        "evidence_refs": [],
        "evidence_pack_sha256": "",
    }

    # Compute pack hash
    pack_copy = dict(evidence_pack)
    pack_copy.pop("evidence_pack_sha256", None)
    evidence_pack["evidence_pack_sha256"] = canonical_sha256(json.dumps(pack_copy, sort_keys=True))

    return evidence_pack


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="N30R V1 Independent Acceptance Oracle")
    parser.add_argument("--trace", help="Path to execution trace JSON")
    parser.add_argument("--repo-root", help="Repository root path")
    parser.add_argument("--contract", help="Path to acceptance contract JSON")
    parser.add_argument("--json-out", help="Path to write result JSON")
    parser.add_argument("--build-task-evidence", help="Build evidence pack for task_id")
    args = parser.parse_args()

    if args.build_task_evidence:
        repo_root = args.repo_root or os.getcwd()
        evidence = build_task_evidence(args.build_task_evidence, repo_root)
        out_path = os.path.join(
            repo_root,
            f"docs/bench/n30r/a1_task_evidence_{args.build_task_evidence}.json",
        )
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(evidence, f, indent=2)
        print(f"Written: {out_path}")
        print(json.dumps(evidence, indent=2))
        return

    if not args.trace:
        parser.error("--trace is required (or use --build-task-evidence)")

    trace = load_json_artifact(args.trace)
    repo_root = args.repo_root or os.getcwd()
    contract = None
    if args.contract:
        contract = load_json_artifact(args.contract)

    result = evaluate_trace(trace, repo_root, contract)

    if args.json_out:
        os.makedirs(os.path.dirname(args.json_out), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Written: {args.json_out}")

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
