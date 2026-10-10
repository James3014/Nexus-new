#!/usr/bin/env python3
"""Bounded GitHub metadata transport for Fast Start v2 trusted workflows."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

RATE_LIMIT_RETRIES = 2
RATE_LIMIT_MAX_WAIT_SECONDS = 60.0
RATE_LIMIT_FALLBACK_WAIT_SECONDS = 1.0
RATE_LIMIT_EXIT = 75


class GitHubTransportError(RuntimeError):
    pass


class GitHubRateLimitExhausted(GitHubTransportError):
    def __init__(self, *, method: str, path: str, retry_after: float) -> None:
        self.method = method
        self.path = path
        self.retry_after = retry_after
        super().__init__(
            f"GITHUB_RATE_LIMIT_EXHAUSTED:{method}:{path}:retry_after_seconds={retry_after:.3f}"
        )


class GitHubWriteOutcomeUnknown(GitHubTransportError):
    pass


def rate_limit_retry_delay(
    exc: urllib.error.HTTPError,
    detail: str,
    *,
    clock: Callable[[], float] = time.time,
) -> float | None:
    if exc.code not in {403, 429}:
        return None
    headers = exc.headers or {}
    remaining = str(headers.get("X-RateLimit-Remaining") or "").strip()
    normalized = detail.casefold()
    limited = (
        exc.code == 429
        or remaining == "0"
        or "rate limit exceeded" in normalized
        or "secondary rate limit" in normalized
    )
    if not limited:
        return None

    retry_after = str(headers.get("Retry-After") or "").strip()
    if retry_after:
        try:
            value = float(retry_after)
            if value >= 0:
                return value
        except ValueError:
            pass

    reset = str(headers.get("X-RateLimit-Reset") or "").strip()
    if reset:
        try:
            return max(0.0, float(reset) - float(clock()) + 1.0)
        except (TypeError, ValueError):
            pass

    return RATE_LIMIT_FALLBACK_WAIT_SECONDS


class GitHubMetadataClient:
    def __init__(
        self,
        token: str,
        *,
        repository: str,
        retries: int = RATE_LIMIT_RETRIES,
        max_wait: float = RATE_LIMIT_MAX_WAIT_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not token:
            raise ValueError("GITHUB_TOKEN_REQUIRED")
        if "/" not in repository:
            raise ValueError("GITHUB_REPOSITORY_INVALID")
        self.token = token
        self.repository = repository
        self.retries = retries
        self.max_wait = max_wait
        self.sleep = sleep
        self.clock = clock

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        if not path.startswith("/"):
            raise ValueError("GitHub path must start with /")
        normalized_method = method.upper()
        if normalized_method not in {"GET", "PATCH", "POST"}:
            raise ValueError("GITHUB_METHOD_UNSUPPORTED")
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")

        max_attempts = self.retries + 1 if normalized_method == "GET" else 1
        for attempt in range(max_attempts):
            request = urllib.request.Request(
                f"https://api.github.com{path}",
                data=data,
                method=normalized_method,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self.token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "nexus-fast-start-v2",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    raw = response.read()
                return None if not raw else json.loads(raw.decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read(8192).decode("utf-8", errors="replace").strip()
                delay = rate_limit_retry_delay(exc, detail, clock=self.clock)
                if delay is not None and normalized_method == "GET":
                    if attempt >= self.retries or delay > self.max_wait:
                        raise GitHubRateLimitExhausted(
                            method=normalized_method,
                            path=path,
                            retry_after=delay,
                        ) from exc
                    self.sleep(delay)
                    continue
                if delay is not None:
                    raise GitHubTransportError(
                        f"GITHUB_WRITE_RATE_LIMITED:{normalized_method}:{path}:"
                        f"retry_after_seconds={delay:.3f}"
                    ) from exc
                raise GitHubTransportError(
                    f"GITHUB_{normalized_method}_FAILED:HTTP_{exc.code}:{path}"
                ) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if normalized_method == "GET":
                    raise GitHubTransportError(f"GITHUB_GET_TRANSPORT_FAILED:{path}:{exc}") from exc
                raise GitHubWriteOutcomeUnknown(
                    f"GITHUB_WRITE_OUTCOME_UNKNOWN:{normalized_method}:{path}:{exc}"
                ) from exc

        raise GitHubTransportError("GITHUB_REQUEST_LOOP_EXHAUSTED")


def collect_pr_changed_paths(
    client: GitHubMetadataClient,
    *,
    repository: str,
    pr_number: int,
    max_pages: int = 30,
) -> list[str]:
    if pr_number <= 0:
        raise ValueError("PR_NUMBER_INVALID")
    paths: set[str] = set()
    for page in range(1, max_pages + 1):
        batch = client.request(
            f"/repos/{repository}/pulls/{pr_number}/files?per_page=100&page={page}"
        )
        if not isinstance(batch, list):
            raise GitHubTransportError("PR_FILES_RESPONSE_MALFORMED")
        for item in batch:
            if not isinstance(item, Mapping):
                continue
            filename = str(item.get("filename") or "").strip()
            if filename:
                paths.add(filename)
        if len(batch) < 100:
            return sorted(paths)
    raise GitHubTransportError("PR_FILES_PAGINATION_EXCEEDED")


def collect_compare_changed_paths(
    client: GitHubMetadataClient,
    *,
    repository: str,
    before_sha: str,
    after_sha: str,
) -> list[str]:
    if not re.fullmatch(r"[0-9a-f]{40}", before_sha):
        raise ValueError("BEFORE_SHA_INVALID")
    if not re.fullmatch(r"[0-9a-f]{40}", after_sha):
        raise ValueError("AFTER_SHA_INVALID")
    payload = client.request(f"/repos/{repository}/compare/{before_sha}...{after_sha}")
    if not isinstance(payload, Mapping):
        raise GitHubTransportError("COMPARE_RESPONSE_MALFORMED")
    files = payload.get("files")
    if not isinstance(files, list):
        raise GitHubTransportError("COMPARE_FILES_RESPONSE_MALFORMED")
    paths = {
        str(item.get("filename") or "").strip()
        for item in files
        if isinstance(item, Mapping) and str(item.get("filename") or "").strip()
    }
    return sorted(paths)


def _write_paths_or_unavailable(
    *,
    output: str,
    repository: str,
    event_subject: Mapping[str, Any],
    producer: Callable[[], list[str]],
) -> int:
    try:
        paths = producer()
    except GitHubRateLimitExhausted as exc:
        Path(output).write_text("", encoding="utf-8")
        witness = {
            "schema": "nexus.fast_start_github_read.v1",
            "status": "UNAVAILABLE",
            "authority": "ADVISORY_CACHE_ONLY",
            "reason": "GITHUB_RATE_LIMIT_EXHAUSTED",
            "retry_after_seconds": exc.retry_after,
            "repository": repository,
            **dict(event_subject),
        }
        print(json.dumps(witness, sort_keys=True))
        return RATE_LIMIT_EXIT

    Path(output).write_text(
        "".join(f"{path}\n" for path in paths),
        encoding="utf-8",
    )
    witness = {
        "schema": "nexus.fast_start_github_read.v1",
        "status": "OK",
        "authority": "ADVISORY_CACHE_ONLY",
        "repository": repository,
        "changed_path_count": len(paths),
        **dict(event_subject),
    }
    print(json.dumps(witness, sort_keys=True))
    return 0


def _cli_changed_paths(args: argparse.Namespace) -> int:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    client = GitHubMetadataClient(token, repository=args.repository)
    return _write_paths_or_unavailable(
        output=args.output,
        repository=args.repository,
        event_subject={"pr_number": args.pr_number},
        producer=lambda: collect_pr_changed_paths(
            client,
            repository=args.repository,
            pr_number=args.pr_number,
        ),
    )


def _cli_compare_paths(args: argparse.Namespace) -> int:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    client = GitHubMetadataClient(token, repository=args.repository)
    return _write_paths_or_unavailable(
        output=args.output,
        repository=args.repository,
        event_subject={
            "before_sha": args.before_sha,
            "after_sha": args.after_sha,
        },
        producer=lambda: collect_compare_changed_paths(
            client,
            repository=args.repository,
            before_sha=args.before_sha,
            after_sha=args.after_sha,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    changed = subparsers.add_parser("changed-paths")
    changed.add_argument("--repository", required=True)
    changed.add_argument("--pr-number", required=True, type=int)
    changed.add_argument("--output", required=True)
    compare = subparsers.add_parser("compare-paths")
    compare.add_argument("--repository", required=True)
    compare.add_argument("--before-sha", required=True)
    compare.add_argument("--after-sha", required=True)
    compare.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "changed-paths":
        return _cli_changed_paths(args)
    if args.command == "compare-paths":
        return _cli_compare_paths(args)
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
