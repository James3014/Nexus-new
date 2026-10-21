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

import json
import re
from typing import Any, Iterable, Mapping, Optional

from scripts.bench.measure_2721.scope import is_test_path

FLAG_UPSTREAM_LOOKUP = "UPSTREAM_LOOKUP"
FLAG_TIMEOUT = "TIMEOUT_AT_CAP"
FLAG_TEST_HUNKS_STRIPPED = "TEST_HUNKS_STRIPPED"
FLAG_NETWORK_ATTEMPT = "NETWORK_ATTEMPT_BLOCKED"
FLAG_HARNESS_TAMPER = "HARNESS_TAMPER"
FLAG_OUT_OF_SCOPE_STRIPPED = "OUT_OF_SCOPE_STRIPPED"
FLAG_PATCH_DOES_NOT_APPLY = "PATCH_DOES_NOT_APPLY"
# S0.4: edits to test configuration count as harness tampering (never a solve).
HARNESS_TAMPER_NAMES = frozenset({"conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini"})
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


def tamper_paths(diff: str) -> list[str]:
    """Paths of file blocks (either side) that touch test configuration."""
    found: list[str] = []
    for path, block in split_file_blocks(diff):
        old = _FILE_BLOCK_RE.match(block.splitlines()[0]).group(1)  # type: ignore[union-attr]
        if any(p.rsplit("/", 1)[-1] in HARNESS_TAMPER_NAMES for p in (path, old)):
            found.append(path)
    return found


def strip_out_of_scope(diff: str, scope: Iterable[str]) -> tuple[str, list[str]]:
    """The diff without file blocks outside ``scope`` (either side), and those paths."""
    from scripts.bench.measure_2721.scope import in_scope

    entries = list(scope)
    kept: list[str] = []
    removed: list[str] = []
    for path, block in split_file_blocks(diff):
        old = _FILE_BLOCK_RE.match(block.splitlines()[0]).group(1)  # type: ignore[union-attr]
        if in_scope(path, entries) and in_scope(old, entries):
            kept.append(block)
        else:
            removed.append(path)
    return "".join(kept), removed


# pytest's temporary base (``pytest-of-<user>/``, ``pytest-current``) when a run falls back
# to the working directory for its temp dir: tool output, never a candidate edit.
_TOOL_ARTIFACT_RE = re.compile(r"^(pytest-of-[^/]+(/|$)|pytest-current(/|$))")
# Revision 15: a top-level ``tempfile`` name (``tmp`` + 8 of [a-z0-9_]) the tools left
# in the worktree, dropped only when the block adds an untracked path (``new file mode``),
# never when it edits a file that is in the base commit.
_TMP_ARTIFACT_RE = re.compile(r"^tmp[a-z0-9_]{8}[^/]*")


def _is_new_file(block: str) -> bool:
    for line in block.splitlines()[1:]:
        if line.startswith(("--- ", "+++ ", "@@", "GIT binary patch", "Binary files ")):
            return False
        if line.startswith("new file mode "):
            return True
    return False


def _is_tool_artifact(path: str, old: str, block: str) -> bool:
    if _TOOL_ARTIFACT_RE.match(path) and _TOOL_ARTIFACT_RE.match(old):
        return True
    return bool(_TMP_ARTIFACT_RE.match(path) and old == path and _is_new_file(block))


def drop_tool_artifacts(diff: str) -> tuple[str, list[str], str]:
    """Remove pytest temp-dir file blocks from a captured diff, the same in every arm
    (35, formal M-main2: a NEXUS row carried pytest-of-<user>/... with a .env file), and
    untracked top-level ``tmp<8 of [a-z0-9_]>...`` paths (revision 15).
    Returns the diff, the removed paths (recorded on the row, never scorer-visible) and
    the removed text (for the secret scan).  Fails closed: a ``diff --git`` header this
    parser cannot read (a quoted or spaced path) leaves the diff as it is."""
    if any(line.startswith("diff --git ") and not _FILE_BLOCK_RE.match(line.rstrip("\n"))
           for line in diff.splitlines()):
        return diff, [], ""
    kept: list[str] = []
    removed: list[str] = []
    removed_text: list[str] = []
    for path, block in split_file_blocks(diff):
        old = _FILE_BLOCK_RE.match(block.splitlines()[0]).group(1)  # type: ignore[union-attr]
        if _is_tool_artifact(path, old, block):
            removed.append(path)
            removed_text.append(block)
        else:
            kept.append(block)
    if not removed:
        return diff, [], ""
    return "".join(kept), removed, "".join(removed_text)


def filter_candidate(diff: str, scope: Iterable[str]) -> dict[str, Any]:
    """Pre-registered order (both arms): tamper check -> test blocks -> scope.

    Tampering is judged on the raw diff (so a conftest edit is never hidden by
    the test strip); the scored diff is the raw diff minus test-path blocks,
    then minus out-of-scope blocks.
    """
    tamper = tamper_paths(diff)
    without_tests, test_paths = strip_test_hunks(diff)
    scored, scope_paths = strip_out_of_scope(without_tests, scope)
    flags = [flag for flag, hit in ((FLAG_HARNESS_TAMPER, tamper), (FLAG_TEST_HUNKS_STRIPPED, test_paths),
                                    (FLAG_OUT_OF_SCOPE_STRIPPED, scope_paths)) if hit]
    return {"scored_diff": scored, "tamper_paths": tamper, "stripped_test_paths": test_paths,
            "stripped_out_of_scope_paths": scope_paths, "flags": flags}


# A prompt piece shorter than this is not cut out of the scanned text (it would cut
# ordinary words out of a reply); a URL-bearing statement is always longer.
_PROMPT_PIECE_MIN = 16


def prompt_scope_texts(task: Mapping[str, Any]) -> list[str]:
    """The task's own prompt text, which neither arm's lookup scan may read: the rendered
    base prompt and its WHAT / WHY statement (the NEXUS worker prompt embeds both)."""
    from scripts.bench.measure_2721.task_text import render_worker_prompt

    text = task.get("text") or {}
    pieces = [str(text.get(key) or "") for key in ("what", "why")]
    if pieces[0] or pieces[1]:
        try:
            pieces.insert(0, render_worker_prompt(text))
        except (KeyError, TypeError):
            pass
    return [piece for piece in pieces if piece]


def without_prompt(text: str, prompt_texts: Iterable[str]) -> str:
    """``text`` with every copy of the prompt pieces cut out, raw or JSON-escaped (the
    NEXUS state and both arms' tool inputs are scanned as JSON dumps)."""
    forms: set[str] = set()
    for piece in prompt_texts:
        if len(piece) < _PROMPT_PIECE_MIN:
            continue
        forms.update((piece, json.dumps(piece)[1:-1], json.dumps(piece, ensure_ascii=False)[1:-1]))
    for form in sorted(forms, key=len, reverse=True):
        text = text.replace(form, " ")
    return text


def lookup_signals(
    texts: Iterable[str],
    *,
    repo: str = "",
    denied_actions: Iterable[Mapping[str, Any]] = (),
    prompt_texts: Iterable[str] = (),
) -> dict[str, Any]:
    """Web-tool and upstream-URL evidence found in the run's visible output.

    Both arms scan the same scope: the task's own prompt text (``prompt_texts``, from
    ``prompt_scope_texts``) is cut out first, so a URL that only the task statement
    carries is never counted, in BARE or NEXUS."""
    tools: set[str] = set()
    upstream_urls: set[str] = set()
    repo_url = re.compile(r"github\.com/" + re.escape(repo) + r"(/[^\s)\"'`]*)?", re.I) if repo else None
    prompt_texts = list(prompt_texts)
    for text in texts:
        if not text:
            continue
        text = without_prompt(text, prompt_texts)
        tools.update(_WEB_TOOL_RE.findall(text))
        if repo_url is not None:
            upstream_urls.update(match.group(0) for match in repo_url.finditer(text))
    denied = sorted({str(item.get("action") or item.get("display_name") or "") for item in denied_actions} - {""})
    flagged = bool(tools or upstream_urls or any(_WEB_TOOL_RE.search(name) for name in denied))
    return {"web_tools_seen": sorted(tools), "web_actions_denied": denied,
            "upstream_urls_seen": sorted(upstream_urls), "flag": FLAG_UPSTREAM_LOOKUP if flagged else None}
