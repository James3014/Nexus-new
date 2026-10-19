"""Pre-registered candidate hygiene for #2721 (prereg v0.2 §8).

* ``strip_test_hunks``: every file block of a candidate diff that touches a
  test path is removed before scoring (both arms alike); the hidden tests are
  applied by the scorer and must not collide with model edits.
* ``lookup_signals`` / ``FLAG_UPSTREAM_LOOKUP``: evidence that the agent used
  a web tool (search or URL read), so the row is flagged rather than trusted.

Agy (as of 2026-10-19) offers no switch that removes ``search_web``; URL reads
(``read_url`` / ``execute_url``) can only be denied through the run settings
the shared Nexus ``agy_run_settings`` writes.  The ``--output-format json``
envelope carries no tool trace, only ``denied_actions`` and the reply text, so
these signals are a lower bound on web use.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Optional

from scripts.bench.measure_2721.scope import is_test_path

FLAG_UPSTREAM_LOOKUP = "UPSTREAM_LOOKUP"
FLAG_TIMEOUT = "TIMEOUT_AT_CAP"
FLAG_TEST_HUNKS_STRIPPED = "TEST_HUNKS_STRIPPED"
WEB_TOOL_NAMES = ("search_web", "read_url_content", "read_url", "execute_url", "web_search", "web_fetch",
                  "browser_subagent", "ReadUrlContent", "SearchWeb")
_WEB_TOOL_RE = re.compile(r"\b(" + "|".join(re.escape(name) for name in WEB_TOOL_NAMES) + r")\b")
_FILE_BLOCK_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)$")


def split_file_blocks(diff: str) -> list[tuple[str, str]]:
    """``[(path, block_text)]`` for each ``diff --git`` block, order preserved."""
    blocks: list[tuple[str, str]] = []
    current: list[str] = []
    path: Optional[str] = None
    for line in diff.splitlines(keepends=True):
        match = _FILE_BLOCK_RE.match(line.rstrip("\n"))
        if match:
            if path is not None:
                blocks.append((path, "".join(current)))
            path, current = match.group(2), [line]
        elif path is not None:
            current.append(line)
    if path is not None:
        blocks.append((path, "".join(current)))
    return blocks


def strip_test_hunks(diff: str) -> tuple[str, list[str]]:
    """The diff without file blocks on test paths (either side), and those paths."""
    kept: list[str] = []
    removed: list[str] = []
    for path, block in split_file_blocks(diff):
        first = block.splitlines()[0]
        old = _FILE_BLOCK_RE.match(first).group(1)  # type: ignore[union-attr]
        if is_test_path(path) or is_test_path(old):
            removed.append(path)
        else:
            kept.append(block)
    return "".join(kept), removed


def lookup_signals(texts: Iterable[str], *, repo: str = "", denied_actions: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Web-tool and upstream-URL evidence found in the run's visible output."""
    tools: set[str] = set()
    upstream_urls: set[str] = set()
    repo_url = re.compile(r"github\.com/" + re.escape(repo) + r"(/[^\s)\"'`]*)?", re.I) if repo else None
    for text in texts:
        if not text:
            continue
        tools.update(_WEB_TOOL_RE.findall(text))
        if repo_url is not None:
            upstream_urls.update(match.group(0) for match in repo_url.finditer(text))
    denied = sorted({str(item.get("action") or item.get("display_name") or "") for item in denied_actions} - {""})
    flagged = bool(tools or upstream_urls or any(_WEB_TOOL_RE.search(name) for name in denied))
    return {"web_tools_seen": sorted(tools), "web_actions_denied": denied,
            "upstream_urls_seen": sorted(upstream_urls), "flag": FLAG_UPSTREAM_LOOKUP if flagged else None}
