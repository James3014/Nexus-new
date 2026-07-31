#!/usr/bin/env python3
"""
🛡️ Nexus Startup Contract Checker
強制執行啟動前規約檢查，確保 Agent 在可治理環境中運行。
"""
import os
import sys
import json
import hashlib
import time
import subprocess
import tempfile
from pathlib import Path

try:
    from scripts.ops.task_authority_freshness_check import validate as validate_task_authority
except ImportError:  # pragma: no cover - direct script execution
    from task_authority_freshness_check import validate as validate_task_authority

# 強制要求的檔案清單
REQUIRED_FILES = [
    "AGENTS.md",
    "scripts/ops/_nexus_preflight.sh",
    "scripts/engine/nexus_cli.py",
    "nexus/core/hallucination_guard.py",
    "nexus/schemas/hallucination_index_v1.json"
]

# 強制要求的 CLI 命令
REQUIRED_SURFACES = [
    "acceptance-check",
    "contract-check"
]

DEFAULT_TASK_INDEX = "tasks/bootstrap-authority-convergence/INDEX.md"
DEFAULT_POLICY_CONTRACT = "scripts/ops/agent_protocol_contract.json"
DEFAULT_REPORT_DIR = "startup_hardening"


def _default_report_dir(project_root: Path) -> Path:
    """Resolve startup artifacts outside the source checkout by default.

    Operators may still provide an explicit ``NEXUS_STARTUP_REPORT_DIR``.
    Otherwise the shared machine-state directory wins, followed by a stable
    temp-directory namespace derived from the worktree root.
    """
    explicit = os.getenv("NEXUS_STARTUP_REPORT_DIR")
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_absolute() else project_root / path

    machine_state = os.getenv("NEXUS_MACHINE_STATE_DIR") or os.getenv("NEXUS_STATE_DIR")
    if machine_state:
        return Path(machine_state).expanduser() / DEFAULT_REPORT_DIR

    root_key = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "nexus-startup-contract" / root_key / DEFAULT_REPORT_DIR

def check_files(project_root: Path) -> dict:
    results = {}
    for f in REQUIRED_FILES:
        path = project_root / f
        results[f] = path.exists() and os.access(path, os.R_OK)
    return results

def check_cli(project_root: Path) -> dict:
    results = {}
    cli_path = project_root / "scripts/engine/nexus_cli.py"
    try:
        output = subprocess.check_output([sys.executable, str(cli_path), "nexus", "--help"], text=True)
        for cmd in REQUIRED_SURFACES:
            results[cmd] = cmd in output
    except Exception as e:
        results["error"] = str(e)
    return results

def check_worktree(project_root: Path) -> dict:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(project_root), *args], text=True).strip()

    try:
        discovered_root = Path(git("rev-parse", "--show-toplevel")).resolve()
        branch = git("symbolic-ref", "--short", "-q", "HEAD") or "DETACHED"
        head = git("rev-parse", "HEAD")
        porcelain = git("status", "--porcelain=v1")
    except (OSError, subprocess.CalledProcessError) as exc:
        return {
            "root": str(project_root.resolve()),
            "root_match": False,
            "branch": "UNKNOWN",
            "head": "UNKNOWN",
            "clean": False,
            "error": str(exc),
        }
    return {
        "root": str(project_root.resolve()),
        "discovered_root": str(discovered_root),
        "root_match": discovered_root == project_root.resolve(),
        "branch": branch,
        "head": head,
        "clean": not bool(porcelain),
    }


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def run_check(
    project_root: Path | None = None,
    *,
    index_path: Path | None = None,
    state_dir: Path | None = None,
    contract_path: Path | None = None,
    report_dir: Path | None = None,
):
    project_root = (project_root or Path(__file__).parent.parent.parent).resolve()
    index_path = index_path or project_root / os.getenv("NEXUS_TASK_INDEX", DEFAULT_TASK_INDEX)
    if not index_path.is_absolute():
        index_path = project_root / index_path
    state_dir = state_dir or (Path(os.environ["NEXUS_STATE_DIR"]) if os.getenv("NEXUS_STATE_DIR") else None)
    contract_path = contract_path or project_root / os.getenv(
        "NEXUS_POLICY_CONTRACT", DEFAULT_POLICY_CONTRACT
    )
    if not contract_path.is_absolute():
        contract_path = project_root / contract_path
    report_dir = report_dir or _default_report_dir(project_root)
    if not report_dir.is_absolute():
        report_dir = project_root / report_dir

    worktree = check_worktree(project_root)
    file_results = check_files(project_root)
    cli_results = check_cli(project_root)

    freshness = validate_task_authority(project_root, index_path, state_dir=state_dir)
    policy_hash = _sha256(contract_path)
    policy = {"path": str(contract_path), "exists": policy_hash is not None, "sha256": policy_hash}
    all_passed = (
        all(file_results.values())
        and all(cli_results.values())
        and worktree["root_match"]
        and worktree["branch"] != "DETACHED"
        and worktree["clean"]
        and freshness["decision"] == "PASS"
        and policy["exists"]
    )

    current_frontier = freshness.get("current_frontier")
    frontier_card = next(
        (card for card in freshness.get("task_cards", []) if card.get("task_id") == current_frontier),
        None,
    )
    report = {
        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "project_root": str(project_root),
        "file_check": file_results,
        "cli_check": cli_results,
        "worktree": worktree,
        "task_authority": freshness,
        "policy_contract": policy,
        "passed": all_passed,
        "commit_sha": worktree.get("head", "UNKNOWN"),
    }

    check_report_path = report_dir / "startup_contract_check_report.json"
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        check_report_path.write_text(json.dumps(report, indent=2))
    except OSError as exc:
        print(f"❌ Nexus Startup Contract FAILED: cannot persist report: {exc}")
        return 1

    if all_passed:
        ack = {
            "ack_token": hashlib.sha256(
                f"{report['commit_sha']}-{report['timestamp']}".encode()
            ).hexdigest()[:16],
            "status": "ENFORCED",
            "runner": os.getenv("NEXUS_RUNNER", "unknown"),
            "timestamp": report["timestamp"],
            "worktree_root": str(project_root),
            "branch": worktree["branch"],
            "head": worktree["head"],
            "index_path": str(index_path),
            "index_commit": freshness.get("index_commit"),
            "task_id": current_frontier,
            "task_card_hash": frontier_card.get("sha256") if frontier_card else None,
            "policy_contract_sha256": policy_hash,
        }
        try:
            (report_dir / "startup_contract_ack.json").write_text(json.dumps(ack, indent=2))
        except OSError as exc:
            print(f"❌ Nexus Startup Contract FAILED: cannot persist ACK: {exc}")
            return 1
        print(f"✅ Nexus Startup Contract PASSED. Token: {ack['ack_token']}")
        return 0
    else:
        print("❌ Nexus Startup Contract FAILED!")
        for f, res in file_results.items():
            if not res: print(f"  - Missing File: {f}")
        for cmd, res in cli_results.items():
            if not res: print(f"  - Missing CLI Surface: {cmd}")
        if not worktree["root_match"] or worktree["branch"] == "DETACHED" or not worktree["clean"]:
            print("  - Worktree identity is stale, detached, or dirty")
        if freshness["decision"] == "BLOCK":
            print("  - Task authority freshness is BLOCK")
        if not policy["exists"]:
            print(f"  - Missing policy contract: {contract_path}")
        return 1

if __name__ == "__main__":
    sys.exit(run_check())
