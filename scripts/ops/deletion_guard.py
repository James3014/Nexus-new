#!/usr/bin/env python3
"""Deletion guard: PRs that delete or rename tracked files need an Owner OK label.

Stdlib only. Reads the PR file list and labels via the GitHub REST API and
fails closed (exit 1) on any error, on hitting the API's 3000-file cap, or on
deletions/renames without the ``owner-approved-deletion`` label.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

APPROVAL_LABEL = "owner-approved-deletion"
API_ROOT = "https://api.github.com"
PER_PAGE = 100
FILE_CAP = 3000
HINT = f"ask the Owner; once they OK it in chat, add label {APPROVAL_LABEL}"


class GuardError(Exception):
    """Raised for any condition that must fail closed."""


def _get_json(url: str, token: str):
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nexus-deletion-guard",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _paginate(fetch, url: str, token: str, limit: int | None = None) -> list:
    items: list = []
    page = 1
    while True:
        batch = fetch(f"{url}?per_page={PER_PAGE}&page={page}", token)
        if not isinstance(batch, list):
            raise GuardError("unexpected API response shape")
        items.extend(batch)
        if limit is not None and len(items) >= limit:
            raise GuardError(f"PR file list reached the API cap of {limit} files; cannot verify")
        if len(batch) < PER_PAGE:
            return items
        page += 1


def collect_deletions(files: list) -> list[str]:
    paths: list[str] = []
    for entry in files:
        status = entry.get("status")
        if status == "removed":
            paths.append(f"deleted: {entry.get('filename')}")
        elif status == "renamed":
            paths.append(f"renamed: {entry.get('previous_filename')} -> {entry.get('filename')}")
    return paths


def run(repo: str, pr: int, token: str, fetch=_get_json) -> int:
    try:
        files = _paginate(fetch, f"{API_ROOT}/repos/{repo}/pulls/{pr}/files", token, FILE_CAP)
        deletions = collect_deletions(files)
        if not deletions:
            print("deletion-guard: no deletions or renames")
            return 0
        labels = _paginate(fetch, f"{API_ROOT}/repos/{repo}/issues/{pr}/labels", token)
    except GuardError as exc:
        print(f"deletion-guard: FAIL (closed): {exc}")
        return 1
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"deletion-guard: FAIL (closed): GitHub API error ({type(exc).__name__})")
        return 1
    if any(label.get("name") == APPROVAL_LABEL for label in labels):
        print(f"deletion-guard: {len(deletions)} deletion(s)/rename(s) approved by label")
        return 0
    print("deletion-guard: FAIL: this PR deletes or renames files:")
    for line in deletions:
        print(f"  {line}")
    print(f"hint: {HINT}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=int)
    args = parser.parse_args(argv)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        print("deletion-guard: FAIL (closed): GH_TOKEN is not set")
        return 1
    return run(args.repo, args.pr, token)


if __name__ == "__main__":
    sys.exit(main())
