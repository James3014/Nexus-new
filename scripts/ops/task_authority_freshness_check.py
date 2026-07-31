#!/usr/bin/env python3
"""Fail-closed freshness checks for a Git-tracked campaign INDEX and cards."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA = "nexus.task_authority_freshness.v1"
HEX_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
CARD_LINK_RE = re.compile(
    r"^\s*\d+\.\s+\[[^]]+\]\(([^)]+)\)\s+-\s+`([^`]+)`\s*$"
)
COMMIT_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
TASK_RE = re.compile(r"`([^`]+)`")
TERMINAL_STATUSES = {
    "FINAL_BLOCK",
    "RETAINED_FOR_REVIEW",
    "REJECTED",
    "SUPERSEDED",
    "CANCELLED",
    "INTEGRATED",
}


def _git(repo_root: Path, *args: str) -> tuple[bool, str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, result.stdout.strip()


def _section(text: str, heading: str) -> list[str]:
    marker = f"## {heading}"
    lines = text.splitlines()
    try:
        start = lines.index(marker) + 1
    except ValueError:
        return []
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return lines[start:end]


def _frontmatter_value(text: str, key: str) -> str | None:
    patterns = (
        rf"^\s*-\s+{re.escape(key)}:\s*`([^`]+)`\s*$",
        rf"^\s*\*\*{re.escape(key)}:\*\*\s*`([^`]+)`\s*$",
        rf"^\s*-\s+{re.escape(key)}:\s*([^\s]+)\s*$",
        rf"^\s*\*\*{re.escape(key)}:\*\*\s*([^\s]+)\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            return match.group(1).strip()
    return None


def _card_status(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    return {
        "path": str(path),
        "task_id": _frontmatter_value(text, "task_id"),
        "status": _frontmatter_value(text, "status"),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _finding(findings: list[dict[str, str]], severity: str, code: str, detail: str) -> None:
    findings.append({"severity": severity, "code": code, "detail": detail})


def _is_ancestor(repo_root: Path, commit: str, head: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, head],
        cwd=repo_root,
        capture_output=True,
    )
    return result.returncode == 0


def validate(
    repo_root: Path,
    index_path: Path,
    *,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    index_path = index_path.resolve()
    findings: list[dict[str, str]] = []

    ok, discovered_root = _git(repo_root, "rev-parse", "--show-toplevel")
    if not ok:
        _finding(findings, "BLOCK", "NOT_A_GIT_WORKTREE", str(repo_root))
        discovered_root = str(repo_root)
    else:
        discovered_root = str(Path(discovered_root).resolve())
        if Path(discovered_root) != repo_root:
            _finding(
                findings,
                "BLOCK",
                "WORKTREE_ROOT_MISMATCH",
                f"requested={repo_root} discovered={discovered_root}",
            )

    _, branch = _git(repo_root, "symbolic-ref", "--short", "-q", "HEAD")
    _, head = _git(repo_root, "rev-parse", "HEAD")
    _, porcelain = _git(repo_root, "status", "--porcelain=v1")
    dirty = bool(porcelain)

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "repo_root": str(repo_root),
        "branch": branch or "DETACHED",
        "head": head,
        "dirty": dirty,
        "index_path": str(index_path),
        "index_exists": index_path.is_file(),
        "index_commit": None,
        "current_frontier": None,
        "ordered_cards": [],
        "completed": [],
        "blocked": [],
        "task_cards": [],
        "lifecycle_checks": [],
        "findings": findings,
    }

    if not index_path.is_file():
        _finding(findings, "BLOCK", "INDEX_MISSING", str(index_path))
        result["decision"] = "BLOCK"
        return result
    try:
        index_text = index_path.read_text(encoding="utf-8")
    except OSError as exc:
        _finding(findings, "BLOCK", "INDEX_UNREADABLE", str(exc))
        result["decision"] = "BLOCK"
        return result

    relative_index = index_path.relative_to(repo_root).as_posix()
    ok, index_commit = _git(repo_root, "log", "-1", "--format=%H", "--", relative_index)
    if ok:
        result["index_commit"] = index_commit
        if head and not _is_ancestor(repo_root, index_commit, head):
            _finding(findings, "BLOCK", "INDEX_COMMIT_NOT_ANCESTOR", index_commit)
    else:
        _finding(findings, "BLOCK", "INDEX_NOT_GIT_TRACKED", relative_index)

    frontier_match = re.search(
        r"^\s*##\s+`?Current Frontier`?\s*\n\s*`([^`]+)`",
        index_text,
        re.MULTILINE,
    )
    if frontier_match:
        result["current_frontier"] = frontier_match.group(1).strip()
    else:
        _finding(findings, "BLOCK", "CURRENT_FRONTIER_MISSING", relative_index)

    ordered_lines = _section(index_text, "Ordered Cards")
    ordered: list[dict[str, str]] = []
    for line in ordered_lines:
        match = CARD_LINK_RE.match(line)
        if not match:
            continue
        ordered.append({"path": match.group(1), "task_id": match.group(2)})
    result["ordered_cards"] = ordered
    if not ordered:
        _finding(findings, "BLOCK", "ORDERED_CARDS_MISSING", relative_index)

    completed_lines = _section(index_text, "Completed Cards")
    completed: list[dict[str, Any]] = []
    for line in completed_lines:
        task_match = TASK_RE.search(line)
        if not task_match:
            continue
        commits = COMMIT_RE.findall(line)
        entry = {"task_id": task_match.group(1), "commits": commits}
        completed.append(entry)
        if not commits:
            _finding(findings, "BLOCK", "COMPLETED_COMMIT_MISSING", task_match.group(1))
            continue
        for commit in commits[:1]:
            if not HEX_COMMIT_RE.fullmatch(commit):
                _finding(findings, "BLOCK", "COMPLETED_COMMIT_MALFORMED", f"{task_match.group(1)}:{commit}")
                continue
            exists, _ = _git(repo_root, "cat-file", "-e", f"{commit}^{{commit}}")
            if not exists:
                _finding(findings, "BLOCK", "COMPLETED_COMMIT_MISSING", f"{task_match.group(1)}:{commit}")
            elif head and not _is_ancestor(repo_root, commit, head):
                _finding(findings, "BLOCK", "COMPLETED_COMMIT_NOT_ANCESTOR", f"{task_match.group(1)}:{commit}")
    result["completed"] = completed

    blocked_lines = _section(index_text, "Blocked Cards")
    blocked_ids = []
    for line in blocked_lines:
        match = TASK_RE.search(line)
        if match:
            blocked_ids.append(match.group(1))
    result["blocked"] = blocked_ids

    ordered_by_id = {entry["task_id"]: entry for entry in ordered}
    completed_ids = {entry["task_id"] for entry in completed}
    frontier = result["current_frontier"]
    if frontier in completed_ids:
        _finding(findings, "BLOCK", "CURRENT_FRONTIER_ALREADY_COMPLETED", frontier)
    elif frontier and frontier not in ordered_by_id and frontier not in blocked_ids:
        _finding(findings, "BLOCK", "CURRENT_FRONTIER_UNDECLARED", frontier)

    for entry in ordered:
        card_path = (index_path.parent / entry["path"]).resolve()
        card_result: dict[str, Any] = {"expected_task_id": entry["task_id"], "path": str(card_path)}
        if not card_path.is_file():
            card_result["exists"] = False
            _finding(findings, "BLOCK", "TASK_CARD_MISSING", entry["task_id"])
            result["task_cards"].append(card_result)
            continue
        card = _card_status(card_path)
        card_result.update(card)
        if card["task_id"] != entry["task_id"]:
            _finding(
                findings,
                "BLOCK",
                "TASK_ID_MISMATCH",
                f"index={entry['task_id']} card={card['task_id']}",
            )
        if entry["task_id"] in completed_ids and "INTEGRATED" not in str(card["status"] or "") and "COMPLETED" not in str(card["status"] or ""):
            _finding(findings, "BLOCK", "COMPLETED_CARD_STATUS_MISMATCH", entry["task_id"])
        result["task_cards"].append(card_result)

    if state_dir is not None:
        state_dir = state_dir.resolve()
        if not state_dir.is_dir():
            _finding(findings, "WARN", "STATE_DIR_MISSING", str(state_dir))
        else:
            card_by_task = {card["task_id"]: card for card in result["task_cards"] if card.get("task_id")}
            campaign_card_paths = {
                Path(card["path"]).resolve()
                for card in result["task_cards"]
                if card.get("path")
            }
            for path in sorted(state_dir.glob("*.json")):
                try:
                    state = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    _finding(findings, "BLOCK", "STATE_UNREADABLE", f"{path.name}:{exc}")
                    continue
                task_id = str(state.get("task_id") or path.stem)
                card_path_raw = str(state.get("task_card_path") or "")
                card_hash = str(state.get("task_card_hash") or "")
                if not card_path_raw and not card_hash:
                    continue
                if task_id not in card_by_task and card_path_raw:
                    state_card_path = Path(card_path_raw).expanduser().resolve()
                    if state_card_path not in campaign_card_paths and index_path.parent not in state_card_path.parents:
                        # The canonical state directory is shared by many
                        # campaigns; unrelated task receipts are out of scope.
                        continue
                elif task_id not in card_by_task and not card_path_raw:
                    continue
                current_card = card_by_task.get(task_id)
                status = str(state.get("status") or "")
                historical = status in TERMINAL_STATUSES
                check = {"task_id": task_id, "status": status, "historical": historical}
                if current_card is None:
                    check["decision"] = "WARN" if historical else "BLOCK"
                    _finding(findings, "WARN" if historical else "BLOCK", "STATE_CARD_NOT_IN_INDEX", task_id)
                else:
                    if card_path_raw and Path(card_path_raw).resolve() != Path(current_card["path"]).resolve():
                        _finding(findings, "WARN" if historical else "BLOCK", "STATE_CARD_PATH_MISMATCH", task_id)
                        check["path_match"] = False
                    else:
                        check["path_match"] = True
                    if card_hash and card_hash != current_card["sha256"]:
                        _finding(findings, "WARN" if historical else "BLOCK", "STATE_CARD_HASH_MISMATCH", task_id)
                        check["hash_match"] = False
                    else:
                        check["hash_match"] = True
                result["lifecycle_checks"].append(check)

    if any(item["severity"] == "BLOCK" for item in findings):
        result["decision"] = "BLOCK"
    elif findings:
        result["decision"] = "WARN"
    else:
        result["decision"] = "PASS"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", type=Path)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--state-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    index_path = args.index if args.index.is_absolute() else repo_root / args.index
    state_dir = args.state_dir
    if state_dir is not None and not state_dir.is_absolute():
        state_dir = repo_root / state_dir
    result = validate(repo_root, index_path, state_dir=state_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["decision"] != "BLOCK" else 1


if __name__ == "__main__":
    sys.exit(main())
