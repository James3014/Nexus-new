from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

DEFAULT_API_URL = "https://api.github.com"
DEFAULT_MAX_RETRIES = 2
DEFAULT_MAX_WAIT_SECONDS = 60.0
DEFAULT_FALLBACK_WAIT_SECONDS = 1.0


class GitHubReadError(RuntimeError):
    """Terminal error from a read-only GitHub API request."""


class GitHubReadRateLimitExhausted(GitHubReadError):
    """Bounded read retry could not outwait a GitHub rate limit."""


def _read_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read(8192).decode("utf-8", errors="replace").strip()
    except Exception:
        return str(exc.reason or "")


def _rate_limit_delay(
    exc: urllib.error.HTTPError,
    detail: str,
    *,
    clock_fn: Callable[[], float],
) -> float | None:
    if exc.code != 403:
        return None

    headers = exc.headers or {}
    lowered = detail.casefold()
    remaining = str(headers.get("X-RateLimit-Remaining") or "").strip()
    if not (
        remaining == "0"
        or "rate limit exceeded" in lowered
        or "secondary rate limit" in lowered
    ):
        return None

    retry_after = str(headers.get("Retry-After") or "").strip()
    if retry_after:
        try:
            delay = float(retry_after)
        except ValueError:
            delay = -1.0
        if delay >= 0:
            return delay

    reset = str(headers.get("X-RateLimit-Reset") or "").strip()
    if reset:
        try:
            return max(0.0, float(reset) - float(clock_fn()) + 1.0)
        except (TypeError, ValueError):
            pass

    return DEFAULT_FALLBACK_WAIT_SECONDS


def github_json_get(
    path: str,
    *,
    token: str,
    api_url: str = DEFAULT_API_URL,
    user_agent: str = "nexus-github-read",
    timeout: float = 20.0,
    max_retries: int = DEFAULT_MAX_RETRIES,
    max_wait_seconds: float = DEFAULT_MAX_WAIT_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
    clock_fn: Callable[[], float] = time.time,
) -> Any:
    """GET one GitHub JSON resource with bounded rate-limit-only retry.

    Only read-only GET requests are supported. Ordinary authorization failures
    and non-rate-limit HTTP failures remain terminal. A retry budget exhaustion
    is surfaced distinctly so advisory callers can safely choose a no-op.
    """

    if not path.startswith("/"):
        raise ValueError("GitHub path must start with /")
    if not token:
        raise ValueError("GitHub token is required")
    if not api_url.startswith("https://"):
        raise ValueError("GitHub API URL must use https")
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    if max_wait_seconds < 0:
        raise ValueError("max_wait_seconds must be non-negative")

    url = f"{api_url.rstrip('/')}{path}"
    for attempt in range(max_retries + 1):
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": user_agent,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            detail = _read_http_error(exc)
            delay = _rate_limit_delay(exc, detail, clock_fn=clock_fn)
            if delay is None:
                raise GitHubReadError(
                    f"GitHub GET failed: HTTP {exc.code} {path}: "
                    f"{detail or exc.reason}"
                ) from exc
            if attempt >= max_retries or delay > max_wait_seconds:
                raise GitHubReadRateLimitExhausted(
                    "GITHUB_READ_RATE_LIMIT_EXHAUSTED: "
                    f"path={path}; retry_after_seconds={delay:.3f}; "
                    f"attempt={attempt + 1}; max_retries={max_retries}"
                ) from exc
            print(
                json.dumps(
                    {
                        "status": "GITHUB_READ_RATE_LIMIT_RETRYING",
                        "path": path,
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "wait_seconds": delay,
                    },
                    sort_keys=True,
                )
            )
            sleep_fn(delay)
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GitHubReadError(f"GitHub GET failed: {path}: {exc}") from exc

        if len(raw) > 4 * 1024 * 1024:
            raise GitHubReadError(f"GitHub GET response too large: {path}")
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubReadError(f"GitHub GET returned invalid JSON: {path}") from exc

    raise GitHubReadRateLimitExhausted(
        f"GITHUB_READ_RATE_LIMIT_EXHAUSTED: path={path}; retry loop exhausted"
    )
