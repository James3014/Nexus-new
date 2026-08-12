#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_CONTRACT_PATH = Path("scripts/ops/agent_protocol_contract.json")
OVERLAY_HEADING = "## Machine policy overlay"


def _normalize(path: str) -> str:
    p = path.strip().replace("\\", "/")
    p = p.lstrip("./")
    return p


def _get_staged_files() -> List[str]:
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.splitlines()
    except subprocess.CalledProcessError:
        return []


class ContractError(ValueError):
    """Raised when a machine policy source is missing or malformed."""


COMPLETION_DISPOSITIONS = {
    "DONE_NO_FOLLOW_UP",
    "KEEP_OPEN",
    "CONTRACT_DELTA",
    "FOLLOW_UP_REQUIRED",
    "BLOCKED_EVIDENCE",
}
TERMINAL_COMPLETION_DISPOSITIONS = {
    "DONE_NO_FOLLOW_UP",
    "FOLLOW_UP_REQUIRED",
}


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


def _git_object_exists(repo_root: Path, sha: object, object_type: str = "commit") -> bool:
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40,64}", sha):
        return False
    return _git(repo_root, "cat-file", "-e", f"{sha}^{{{object_type}}}").returncode == 0


def _is_ancestor(repo_root: Path, ancestor: object, descendant: object) -> bool:
    if not _git_object_exists(repo_root, ancestor) or not _git_object_exists(repo_root, descendant):
        return False
    return (
        _git(repo_root, "merge-base", "--is-ancestor", str(ancestor), str(descendant)).returncode
        == 0
    )


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _canonical_github_remote_url(repository: str) -> str:
    return f"https://github.com/{repository}.git"


def evaluate_completion_snapshot(
    snapshot: object,
    *,
    repo_root: Path,
    main_ref: str,
    expected_bindings: object,
) -> dict[str, Any]:
    """Classify a governed Issue completion snapshot against physical Git state.

    This is a fail-closed consumer of the repository completion contract. It
    does not mutate Issues, create follow-ups, or store a second Issue database.
    """
    failures: list[str] = []
    if not isinstance(snapshot, Mapping):
        return {
            "disposition": "BLOCKED_EVIDENCE",
            "terminal": False,
            "downstream_ready": False,
            "failures": ["snapshot_must_be_object"],
        }
    if not isinstance(expected_bindings, Mapping):
        expected_bindings = {}
        failures.append("expected_bindings_missing")
    if snapshot.get("schema") != "nexus.issue_completion_snapshot.v1":
        failures.append("snapshot_schema_invalid")
    expected_repository = expected_bindings.get("repository")
    if not isinstance(expected_repository, str) or not expected_repository:
        failures.append("expected_repository_invalid")
    if snapshot.get("repository") != expected_repository:
        failures.append("repository_identity_mismatch")

    issue = _mapping(snapshot.get("issue"))
    candidate = _mapping(snapshot.get("candidate"))
    pull_request = _mapping(snapshot.get("pull_request"))
    current_main = _mapping(snapshot.get("current_main"))

    issue_number = issue.get("number")
    if not isinstance(issue_number, int) or isinstance(issue_number, bool) or issue_number < 1:
        failures.append("issue_number_invalid")
    if issue_number != expected_bindings.get("issue_number"):
        failures.append("issue_identity_mismatch")
    if candidate.get("issue_number") != issue_number:
        failures.append("candidate_issue_mismatch")
    if pull_request.get("issue_number") != issue_number:
        failures.append("pull_request_issue_mismatch")
    candidate_pr_number = candidate.get("pr_number")
    pull_request_number = pull_request.get("number")
    if (
        not isinstance(candidate_pr_number, int)
        or isinstance(candidate_pr_number, bool)
        or candidate_pr_number < 1
        or not isinstance(pull_request_number, int)
        or isinstance(pull_request_number, bool)
        or pull_request_number < 1
    ):
        failures.append("pull_request_number_invalid")
    if candidate_pr_number != pull_request_number:
        failures.append("candidate_pr_number_mismatch")
    if pull_request_number != expected_bindings.get("pr_number"):
        failures.append("pull_request_identity_mismatch")
    if candidate.get("head_sha") != pull_request.get("head_sha"):
        failures.append("candidate_pr_head_mismatch")
    if candidate.get("head_sha") != expected_bindings.get("candidate_head_sha"):
        failures.append("candidate_head_identity_mismatch")
    if pull_request.get("state") != "MERGED":
        failures.append("pull_request_not_merged")

    contract_revision = issue.get("contract_revision")
    if not isinstance(contract_revision, str) or not re.fullmatch(
        r"[0-9a-f]{40,64}", contract_revision
    ):
        failures.append("issue_contract_revision_invalid")
    if contract_revision != expected_bindings.get("issue_contract_revision"):
        failures.append("issue_contract_revision_mismatch")
    latest_comment_id = issue.get("latest_comment_id")
    if not isinstance(latest_comment_id, str) or not latest_comment_id:
        failures.append("latest_issue_comment_missing")
    if latest_comment_id != expected_bindings.get("latest_comment_id"):
        failures.append("latest_issue_comment_mismatch")

    canonical_main_ref = "refs/remotes/nexus-new/main"
    if main_ref != canonical_main_ref or expected_bindings.get("main_ref") != canonical_main_ref:
        failures.append("default_main_ref_invalid")
        main_ref = "__invalid_default_main_ref__"
    remote_result = _git(repo_root, "remote", "get-url", "nexus-new")
    expected_remote_url = _canonical_github_remote_url(expected_repository or "")
    if (
        remote_result.returncode != 0
        or remote_result.stdout.strip().removesuffix("/") != expected_remote_url
        or expected_bindings.get("remote_url") != expected_remote_url
    ):
        failures.append("collaboration_remote_identity_mismatch")
    actual_head_result = _git(repo_root, "rev-parse", "--verify", main_ref)
    actual_tree_result = _git(repo_root, "rev-parse", "--verify", f"{main_ref}^{{tree}}")
    if actual_head_result.returncode != 0 or actual_tree_result.returncode != 0:
        failures.append("current_repository_identity_unavailable")
        actual_head = ""
        actual_tree = ""
    else:
        actual_head = actual_head_result.stdout.strip()
        actual_tree = actual_tree_result.stdout.strip()
    if current_main.get("head_sha") != actual_head:
        failures.append("current_main_head_mismatch")
    if current_main.get("tree_sha") != actual_tree:
        failures.append("current_main_tree_mismatch")
    if current_main.get("head_sha") != expected_bindings.get("current_main_head_sha"):
        failures.append("expected_current_main_head_mismatch")
    if current_main.get("tree_sha") != expected_bindings.get("current_main_tree_sha"):
        failures.append("expected_current_main_tree_mismatch")

    candidate_head = candidate.get("head_sha")
    merge_commit = pull_request.get("merge_commit_sha")
    if merge_commit != expected_bindings.get("merge_commit_sha"):
        failures.append("merge_commit_identity_mismatch")
    if not _is_ancestor(repo_root, candidate_head, merge_commit):
        failures.append("candidate_not_in_merge_commit")
    if not _is_ancestor(repo_root, merge_commit, actual_head):
        failures.append("merge_commit_not_in_current_main")

    required_evidence = snapshot.get("required_evidence_ids")
    evidence = snapshot.get("evidence")
    if not isinstance(required_evidence, list) or not all(
        isinstance(item, str) and item for item in required_evidence
    ):
        failures.append("required_evidence_ids_invalid")
        required_evidence = []
    expected_evidence = expected_bindings.get("required_evidence_ids")
    if (
        not isinstance(expected_evidence, list)
        or not expected_evidence
        or not all(isinstance(item, str) and item for item in expected_evidence)
    ):
        failures.append("expected_required_evidence_invalid")
        expected_evidence = []
    if len(expected_evidence) != len(set(expected_evidence)):
        failures.append("duplicate_expected_evidence_id")
    if sorted(required_evidence) != sorted(expected_evidence):
        failures.append("required_evidence_set_mismatch")
    if not isinstance(evidence, list) or not all(isinstance(item, Mapping) for item in evidence):
        failures.append("evidence_invalid")
        evidence = []
    evidence_by_id: dict[str, Mapping[str, Any]] = {}
    for item in evidence:
        evidence_id = item.get("id")
        if not isinstance(evidence_id, str) or not evidence_id:
            failures.append("evidence_id_invalid")
        elif evidence_id in evidence_by_id:
            failures.append(f"duplicate_evidence_id:{evidence_id}")
        else:
            evidence_by_id[evidence_id] = item
    if sorted(evidence_by_id) != sorted(expected_evidence):
        failures.append("evidence_set_mismatch")
    for evidence_id in required_evidence:
        item = evidence_by_id.get(evidence_id)
        if item is None:
            failures.append(f"required_evidence_missing:{evidence_id}")
        elif item.get("status") != "PASS":
            failures.append(f"required_evidence_not_passed:{evidence_id}")
    post_merge_evidence = [
        item
        for item in evidence
        if item.get("kind") == "POST_MERGE_CURRENT_MAIN"
        and item.get("status") == "PASS"
        and item.get("bound_sha") == actual_head
        and item.get("bound_tree_sha") == actual_tree
    ]
    if not post_merge_evidence:
        failures.append("post_merge_current_main_evidence_missing")

    prerequisite_open_failures: list[str] = []
    prerequisite_identity_failures: list[str] = []
    prerequisites = snapshot.get("hard_prerequisites", [])
    if not isinstance(prerequisites, list) or not all(
        isinstance(item, Mapping) for item in prerequisites
    ):
        failures.append("hard_prerequisites_invalid")
        prerequisites = []
    expected_predecessor_bindings = expected_bindings.get("required_predecessors")
    if not isinstance(expected_predecessor_bindings, list) or not all(
        isinstance(item, Mapping) for item in expected_predecessor_bindings
    ):
        failures.append("expected_predecessors_invalid")
        expected_predecessor_bindings = []
    expected_predecessors: dict[int, Mapping[str, Any]] = {}
    for item in expected_predecessor_bindings:
        number = item.get("issue_number")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            failures.append("expected_predecessor_issue_number_invalid")
        elif number in expected_predecessors:
            failures.append("duplicate_expected_predecessor_issue")
        else:
            expected_predecessors[number] = item
    predecessor_numbers: list[int] = []
    for prerequisite in prerequisites:
        number = prerequisite.get("issue_number")
        disposition = prerequisite.get("disposition")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            failures.append("predecessor_issue_number_invalid")
            continue
        predecessor_numbers.append(number)
        expected_predecessor = expected_predecessors.get(number)
        if expected_predecessor is None or dict(prerequisite) != dict(expected_predecessor):
            failures.append(f"predecessor_binding_mismatch:{number}")
        if disposition not in COMPLETION_DISPOSITIONS:
            failures.append(f"predecessor_disposition_invalid:{number}")
        if disposition not in TERMINAL_COMPLETION_DISPOSITIONS:
            prerequisite_open_failures.append(f"predecessor_not_terminal:{number}")
        if prerequisite.get("bound_main_sha") != actual_head:
            prerequisite_identity_failures.append(f"predecessor_revision_mismatch:{number}")
    if len(predecessor_numbers) != len(set(predecessor_numbers)):
        failures.append("duplicate_predecessor_issue")
    if sorted(predecessor_numbers) != sorted(expected_predecessors):
        failures.append("required_predecessor_set_mismatch")

    original_satisfied = snapshot.get("original_contract_satisfied")
    contract_delta = snapshot.get("contract_delta_required")
    distinct_follow_up = snapshot.get("distinct_follow_up_required")
    owner_checked = snapshot.get("existing_durable_owner_checked")
    requested_downstream = snapshot.get("requested_downstream_ready")
    semantic_flags = (
        original_satisfied,
        contract_delta,
        distinct_follow_up,
        owner_checked,
        requested_downstream,
    )
    if not all(type(flag) is bool for flag in semantic_flags):
        failures.append("completion_semantic_flags_invalid")
    if contract_delta and distinct_follow_up:
        failures.append("completion_signals_contradictory")
    if distinct_follow_up and original_satisfied is False:
        failures.append("follow_up_requires_original_completion")

    failures.extend(prerequisite_identity_failures)
    if failures:
        disposition = "BLOCKED_EVIDENCE"
    elif contract_delta:
        disposition = "CONTRACT_DELTA"
    elif not original_satisfied or prerequisite_open_failures:
        disposition = "KEEP_OPEN"
    elif distinct_follow_up:
        disposition = "FOLLOW_UP_REQUIRED" if owner_checked else "BLOCKED_EVIDENCE"
        if not owner_checked:
            failures.append("existing_durable_owner_not_checked")
    else:
        disposition = "DONE_NO_FOLLOW_UP"

    failures.extend(prerequisite_open_failures)
    terminal = disposition in TERMINAL_COMPLETION_DISPOSITIONS
    downstream_ready = requested_downstream is True and terminal and not failures
    return {
        "disposition": disposition,
        "terminal": terminal,
        "downstream_ready": downstream_ready,
        "failures": failures,
    }


def _validate_boundaries(boundaries: Dict, source: str) -> Dict:
    if not isinstance(boundaries, dict):
        raise ContractError(f"{source}: boundaries must be an object")
    for key in ("allowed_paths", "forbidden_paths"):
        value = boundaries.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ContractError(f"{source}: {key} must be a string array")
    max_files = boundaries.get("max_files_touched")
    if not isinstance(max_files, int) or isinstance(max_files, bool) or max_files < 1:
        raise ContractError(f"{source}: max_files_touched must be a positive integer")
    return boundaries


def _load_contract(contract_path: Path) -> Dict:
    if not contract_path.exists():
        raise ContractError(f"baseline contract missing: {contract_path}")
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"baseline contract unreadable: {contract_path}: {exc}") from exc
    if not isinstance(contract, dict):
        raise ContractError("baseline contract must be a JSON object")
    required_terms = contract.get("required_terms")
    if not isinstance(required_terms, list) or not all(
        isinstance(term, str) and term for term in required_terms
    ):
        raise ContractError("baseline contract: required_terms must be a non-empty string array")
    contract["boundaries"] = _validate_boundaries(contract.get("boundaries"), "baseline contract")
    return contract


def _load_task_card_overlay(task_card_path: Path) -> Dict:
    if not task_card_path.exists():
        raise ContractError(f"task card missing: {task_card_path}")
    try:
        content = task_card_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"task card unreadable: {task_card_path}: {exc}") from exc
    match = re.search(
        rf"{re.escape(OVERLAY_HEADING)}\s*```json\s*(.*?)\s*```",
        content,
        flags=re.DOTALL,
    )
    if not match:
        raise ContractError(f"task card missing {OVERLAY_HEADING} JSON block: {task_card_path}")
    try:
        overlay = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ContractError(f"task card overlay is invalid JSON: {exc}") from exc
    if not isinstance(overlay, dict):
        raise ContractError("task card overlay must be a JSON object")
    return {"boundaries": _validate_boundaries(overlay, "task card overlay")}


def _effective_policy(
    contract: Dict, task_card_path: Optional[Path]
) -> Tuple[Dict, Optional[Dict]]:
    overlay = _load_task_card_overlay(task_card_path) if task_card_path else None
    return contract, overlay


def _is_under(path: str, prefix: str) -> bool:
    n_path = _normalize(path)
    n_prefix = _normalize(prefix)
    if n_prefix in ("", "."):
        return True
    return n_path == n_prefix or n_path.startswith(n_prefix.rstrip("/") + "/")


def check_protocol(
    check_files: Optional[List[str]] = None,
    check_staged: bool = False,
    strict: bool = False,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    task_card_path: Optional[Path] = None,
):
    agents_md = Path("AGENTS.md")
    if not agents_md.exists():
        print("❌ AGENTS.md missing")
        return 1

    content = agents_md.read_text(encoding="utf-8")
    try:
        contract, overlay = _effective_policy(_load_contract(contract_path), task_card_path)
    except ContractError as exc:
        print(f"❌ Protocol check FAILED: {exc}")
        return 1
    required_terms = contract.get("required_terms", [])
    boundaries = contract.get("boundaries", {})
    policy_layers = [("baseline contract", boundaries)]
    if overlay:
        policy_layers.append(("task card overlay", overlay["boundaries"]))

    max_files = min(int(layer["max_files_touched"]) for _, layer in policy_layers)

    missing = [term for term in required_terms if term not in content]
    if missing:
        print(f"❌ Protocol check FAILED. Missing: {', '.join(missing)}")
        return 1

    files_to_check = []
    if check_files:
        files_to_check.extend(check_files)
    if check_staged:
        files_to_check.extend(_get_staged_files())

    if files_to_check:
        files = [_normalize(f) for f in files_to_check if f.strip()]
        # Unique files
        files = list(set(files))

        if len(files) > max_files:
            print(
                f"❌ Boundary check FAILED: Touched {len(files)} files, exceeds max_files_touched={max_files}"
            )
            return 1

        for file_path in files:
            for layer_name, layer in policy_layers:
                if any(_is_under(file_path, forbidden) for forbidden in layer["forbidden_paths"]):
                    print(
                        f"❌ Boundary check FAILED: File {file_path} is in {layer_name} forbidden_paths"
                    )
                    return 1

        if strict:
            for file_path in files:
                for layer_name, layer in policy_layers:
                    if not any(_is_under(file_path, allowed) for allowed in layer["allowed_paths"]):
                        print(
                            f"❌ Boundary check FAILED: File {file_path} is not in "
                            f"{layer_name} allowed_paths (Strict Mode)"
                        )
                        return 1

    print("✅ Protocol check PASSED")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent Protocol & Boundary Checker")
    parser.add_argument("--check-files", help="Comma-separated paths of files touched")
    parser.add_argument("--check-staged", action="store_true", help="Check git staged files")
    parser.add_argument(
        "--strict-boundary", action="store_true", help="Enforce strict allowed_paths check"
    )
    parser.add_argument(
        "--contract",
        default=str(DEFAULT_CONTRACT_PATH),
        help="Path to JSON contract file",
    )
    parser.add_argument(
        "--task-card",
        help="Path to a Task Card containing a Machine policy overlay JSON block",
    )
    parser.add_argument(
        "--completion-snapshot",
        help="Path to a revision-bound governed Issue completion snapshot",
    )
    parser.add_argument(
        "--completion-bindings",
        help="Path to freshly fetched repository, Issue, PR, evidence, and predecessor bindings",
    )
    parser.add_argument(
        "--main-ref",
        default="refs/remotes/nexus-new/main",
        help="Canonical default-branch ref used for physical current-main verification",
    )
    args = parser.parse_args()

    files = args.check_files.split(",") if args.check_files else None
    if args.completion_snapshot:
        if not args.completion_bindings:
            print("❌ Completion bindings are required")
            sys.exit(1)
        try:
            snapshot = json.loads(Path(args.completion_snapshot).read_text(encoding="utf-8"))
            bindings = json.loads(Path(args.completion_bindings).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"❌ Completion snapshot unreadable: {exc}")
            sys.exit(1)
        result = evaluate_completion_snapshot(
            snapshot,
            repo_root=Path.cwd(),
            main_ref=args.main_ref,
            expected_bindings=bindings,
        )
        print(json.dumps(result, sort_keys=True))
        sys.exit(0 if result["terminal"] and not result["failures"] else 1)
    sys.exit(
        check_protocol(
            check_files=files,
            check_staged=args.check_staged,
            strict=args.strict_boundary,
            contract_path=Path(args.contract),
            task_card_path=Path(args.task_card) if args.task_card else None,
        )
    )
