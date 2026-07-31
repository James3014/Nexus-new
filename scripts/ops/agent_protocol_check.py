#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


def _effective_policy(contract: Dict, task_card_path: Optional[Path]) -> Tuple[Dict, Optional[Dict]]:
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
    args = parser.parse_args()

    files = args.check_files.split(",") if args.check_files else None
    sys.exit(
        check_protocol(
            check_files=files,
            check_staged=args.check_staged,
            strict=args.strict_boundary,
            contract_path=Path(args.contract),
            task_card_path=Path(args.task_card) if args.task_card else None,
        )
    )
