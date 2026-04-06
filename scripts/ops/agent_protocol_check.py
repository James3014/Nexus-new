#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_CONTRACT_PATH = Path("scripts/ops/agent_protocol_contract.json")


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


def _load_contract(contract_path: Path) -> Dict:
    if not contract_path.exists():
        return {
            "required_terms": [
                "allowed_paths",
                "forbidden_paths",
                "max_files_touched",
                "Semantic Completion Criteria",
                "Evidence Reporting Format",
                "Failure-to-Lesson Writeback",
            ],
            "boundaries": {
                "allowed_paths": ["."],
                "forbidden_paths": [],
                "max_files_touched": 10,
            },
        }
    return json.loads(contract_path.read_text(encoding="utf-8"))


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
):
    agents_md = Path("AGENTS.md")
    if not agents_md.exists():
        print("❌ AGENTS.md missing")
        return 1

    content = agents_md.read_text(encoding="utf-8")
    contract = _load_contract(contract_path)
    required_terms = contract.get("required_terms", [])
    boundaries = contract.get("boundaries", {})

    allowed_paths = boundaries.get("allowed_paths", ["."])
    forbidden_paths = boundaries.get("forbidden_paths", [])
    max_files = int(boundaries.get("max_files_touched", 10))

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
            if any(_is_under(file_path, forbidden) for forbidden in forbidden_paths):
                print(f"❌ Boundary check FAILED: File {file_path} is in forbidden_paths")
                return 1

        if strict:
            for file_path in files:
                if not any(_is_under(file_path, allowed) for allowed in allowed_paths):
                    print(
                        f"❌ Boundary check FAILED: File {file_path} is not in allowed_paths (Strict Mode)"
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
    args = parser.parse_args()

    files = args.check_files.split(",") if args.check_files else None
    sys.exit(
        check_protocol(
            check_files=files,
            check_staged=args.check_staged,
            strict=args.strict_boundary,
            contract_path=Path(args.contract),
        )
    )
