#!/usr/bin/env python3
import sys
import json
import argparse
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, Any, List

# 🛡️ Nexus Closeout Guard (Hard-Gate Enforcement)
# [NEXUS CONFIG: FAIL-CLOSED RELEASE CONTRACT]

def _git_head_short(cwd: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(cwd)).decode().strip()
    except Exception:
        return ""


def _git_out(repo_root: Path, *args: str) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(["git", *args], cwd=str(repo_root), capture_output=True, text=True, check=False)


def compute_changed_files(repo_root: Path, base_ref: str = "origin/main"):
    """Files changed relative to merge-base(HEAD, base_ref), plus working-tree and untracked files.

    Returns (files, base_description); (None, None) when no base resolves, so the result
    stays "unknown" instead of silently being [] or the last commit's file list.
    """
    for ref in dict.fromkeys([base_ref, "origin/main", "main"]):
        if not ref:
            continue
        mb = _git_out(repo_root, "merge-base", "HEAD", ref)
        base_sha = mb.stdout.strip()
        if mb.returncode != 0 or not base_sha:
            continue
        diff = _git_out(repo_root, "diff", "--name-only", base_sha)
        if diff.returncode != 0:
            continue
        files = {line.strip() for line in diff.stdout.splitlines() if line.strip()}
        untracked = _git_out(repo_root, "ls-files", "--others", "--exclude-standard")
        files.update(line.strip() for line in untracked.stdout.splitlines() if line.strip())
        return sorted(files), f"merge-base({ref})={base_sha[:9]}"
    return None, None


def build_attestation(value: Any, evidence_path: "Path | None", repo_root: Path) -> Dict[str, Any]:
    """Attestation entry: not_run (value unknown), caller_supplied (no evidence) or measured."""
    if value is None:
        return {"source": "not_run", "evidence_ref": None, "evidence_sha256": None}
    if evidence_path is None:
        return {"source": "caller_supplied", "evidence_ref": None, "evidence_sha256": None}
    resolved = evidence_path.resolve()
    try:
        ref = str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        ref = str(resolved)
    return {
        "source": "measured",
        "evidence_ref": ref,
        "evidence_sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
    }


_ATTESTED_FIELDS = ("linter_exit_code", "ci_gate_exit_code", "required_tests_passed")
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _attestation_failures(data: Dict[str, Any], contract_path: Path) -> List[str]:
    """Reject results that are unknown/NOT_RUN or merely caller-asserted without evidence.

    Contracts without an ``attestation`` block are hand-authored legacy contracts and are
    judged on their values alone. Snapshots always carry the block.
    """
    attestation = data.get("attestation")
    if attestation is None:
        return []
    if not isinstance(attestation, dict):
        return ["attestation is not an object"]
    failures: List[str] = []
    for field in _ATTESTED_FIELDS:
        raw_entry = attestation.get(field)
        entry: Dict[str, Any] = raw_entry if isinstance(raw_entry, dict) else {}
        source = entry.get("source")
        if data.get(field) is None or source == "not_run":
            failures.append(f"{field} is unknown/NOT_RUN")
            continue
        if source != "measured":
            failures.append(f"{field} is self-asserted (source={source!r}) without evidence; pass --evidence-ref")
            continue
        ref = str(entry.get("evidence_ref") or "").strip()
        if not ref:
            failures.append(f"{field} is marked measured but has no evidence_ref")
            continue
        for base in (_REPO_ROOT, contract_path.resolve().parent):
            candidate = Path(ref) if Path(ref).is_absolute() else base / ref
            if candidate.is_file():
                expected = str(entry.get("evidence_sha256") or "").strip()
                if expected and hashlib.sha256(candidate.read_bytes()).hexdigest() != expected:
                    failures.append(f"{field} evidence {ref} does not match recorded sha256")
                break
        else:
            failures.append(f"{field} evidence {ref} not found")
    return failures


def validate_contract(contract_path: Path, *, require_head_match: bool = True) -> Dict[str, Any]:
    if not contract_path.exists():
        return {
            "ok": False,
            "error": f"Contract file missing: {contract_path}",
            "details": {}
        }
    
    try:
        with open(contract_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return {
            "ok": False,
            "error": f"Invalid JSON in contract: {str(e)}",
            "details": {}
        }

    required_fields = [
        "linter_exit_code",
        "ci_gate_exit_code",
        "required_tests_passed",
        "commit_sha",
        "changed_files"
    ]
    
    missing = [f for f in required_fields if f not in data]
    if missing:
        return {
            "ok": False,
            "error": f"Missing required fields: {', '.join(missing)}",
            "details": data
        }

    expected_sha = str(data.get("commit_sha") or "").strip()
    current_sha = _git_head_short(contract_path.parent) or _git_head_short(_REPO_ROOT)
    attestation_failures = _attestation_failures(data, contract_path)
    consulted_agents = data.get("consulted_agents", [])
    delivery_profile = str(data.get("delivery_profile", "mock_only") or "mock_only")
    proposal_required = bool(data.get("proposal_required", False))
    proposal_ref = str(data.get("proposal_ref", "") or "").strip()
    adr_checked = bool(data.get("adr_checked", False))
    human_approval = bool(data.get("human_approval", False)) or bool(str(data.get("human_approval_ref", "") or "").strip())
    live_evidence = data.get("live_evidence_paths", [])

    checks = {
        "linter_ok": data.get("linter_exit_code") == 0,
        "ci_gate_ok": data.get("ci_gate_exit_code") == 0,
        "tests_ok": data.get("required_tests_passed") is True,
        "attestation_ok": not attestation_failures,
        "commit_ok": bool(expected_sha) if not require_head_match else (bool(current_sha) and current_sha == expected_sha),
        "files_ok": isinstance(data.get("changed_files"), list) and len(data.get("changed_files")) > 0,
        "consulted_agents_ok": isinstance(consulted_agents, list) and len(consulted_agents) <= 2,
        "delivery_profile_ok": delivery_profile in {"mock_only", "live_browser", "live_api"},
        "proposal_ok": (not proposal_required) or (bool(proposal_ref) and adr_checked),
        "live_evidence_ok": (
            delivery_profile == "mock_only"
            or (human_approval and isinstance(live_evidence, list) and len(live_evidence) > 0)
        ),
    }
    
    all_ok = all(checks.values())
    
    if require_head_match and not checks["commit_ok"]:
        print(f"❌ SHA MISMATCH: current={current_sha or 'unknown'}, expected={expected_sha}", file=sys.stderr)

    for reason in attestation_failures:
        print(f"❌ ATTESTATION: {reason}", file=sys.stderr)

    return {
        "ok": all_ok,
        "checks": checks,
        "attestation_failures": attestation_failures,
        "details": {
            **data,
            "current_head_sha": current_sha,
            "require_head_match": require_head_match,
        },
    }

def main():
    parser = argparse.ArgumentParser(description="Nexus Closeout Hard-Gate Guard")
    parser.add_argument("--contract", type=str, default=".nexus/reports/done_contract.json",
                        help="Path to the done contract JSON file")
    parser.add_argument(
        "--require-head-match",
        dest="require_head_match",
        action="store_true",
        help="Require contract commit_sha to match current git HEAD.",
    )
    parser.add_argument(
        "--no-require-head-match",
        dest="require_head_match",
        action="store_false",
        help="Disable contract commit_sha to git HEAD enforcement.",
    )
    parser.set_defaults(require_head_match=True)
    args = parser.parse_args()

    contract_path = Path(args.contract)
    result = validate_contract(contract_path, require_head_match=bool(args.require_head_match))
    
    # Output machine-readable JSON
    print(json.dumps(result, indent=2))
    
    if result["ok"]:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
