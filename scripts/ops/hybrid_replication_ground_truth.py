#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any, Mapping


def derive_ground_truth(
    *,
    repository: str,
    issue: Mapping[str, Any],
    pull_requests: list[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if str(issue.get("state") or "") != "closed":
        return None
    merged = [item for item in pull_requests if item.get("merged_at")]
    issue_number = int(issue.get("number") or 0)
    issue_url = f"https://github.com/{repository}/issues/{issue_number}"
    if merged:
        chosen = sorted(
            merged,
            key=lambda item: (str(item.get("merged_at") or ""), int(item.get("number") or 0)),
        )[-1]
        return {
            "terminal_state": "MERGED",
            "terminal_at": str(chosen.get("merged_at") or issue.get("closed_at") or ""),
            "evidence_refs": [
                issue_url,
                str(chosen.get("html_url") or ""),
                f"merge_commit:{chosen.get('merge_commit_sha') or ''}",
            ],
        }
    return {
        "terminal_state": "CLOSED_NO_MERGED_PR",
        "terminal_at": str(issue.get("closed_at") or ""),
        "evidence_refs": [issue_url],
    }


def _gh_json(*args: str) -> Any:
    completed = subprocess.run(
        ["gh", "api", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"gh_api_failed:{completed.returncode}:{completed.stderr.strip()}")
    return json.loads(completed.stdout)


def _linked_pull_requests(repository: str, issue_number: int) -> list[dict[str, Any]]:
    numbers: set[int] = set()
    for page in range(1, 11):
        batch = _gh_json(
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{repository}/issues/{issue_number}/timeline?per_page=100&page={page}",
        )
        if not isinstance(batch, list):
            raise RuntimeError("issue_timeline_response_not_list")
        for item in batch:
            if not isinstance(item, dict) or item.get("event") != "cross-referenced":
                continue
            source = item.get("source") if isinstance(item.get("source"), dict) else {}
            source_issue = source.get("issue") if isinstance(source.get("issue"), dict) else {}
            if "pull_request" not in source_issue:
                continue
            if str(source_issue.get("repository_url") or "") != (
                f"https://api.github.com/repos/{repository}"
            ):
                continue
            number = source_issue.get("number")
            if isinstance(number, int):
                numbers.add(number)
        if len(batch) < 100:
            break
    return [
        _gh_json(f"repos/{repository}/pulls/{number}")
        for number in sorted(numbers)
    ]


def main() -> int:
    state = json.load(sys.stdin)
    task_key = str(state.get("task_key") or "")
    if "#" not in task_key:
        raise SystemExit("task_key_missing")
    repository, issue_text = task_key.rsplit("#", 1)
    issue_number = int(issue_text)
    issue = _gh_json(f"repos/{repository}/issues/{issue_number}")
    pull_requests = _linked_pull_requests(repository, issue_number)
    result = derive_ground_truth(
        repository=repository,
        issue=issue,
        pull_requests=pull_requests,
    )
    if result is None:
        return 3
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
