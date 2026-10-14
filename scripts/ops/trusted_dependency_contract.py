#!/usr/bin/env python3
"""Trusted dependency-contract check, split out of the trusted controller (#2156).

"Trusted controller (default branch)" also runs the merge-lane gate, which is
red by design on Owner-authored PRs since the 2026-10-14 lane retirement
(#2006), so its ``DEPENDENCY_CONTRACT_DRIFT`` verdict was only read by humans.
This module gives that one rule its own ``pull_request_target`` check.

Trust model:

* It runs only from default-branch YAML and this default-branch file (plus the
  default-branch ``trusted_deletion_anchor`` it imports).  PR-head content is
  read as Git objects in a bare repository; it is never checked out, imported
  or executed.
* The anchor table and product rule are the ones in
  ``trusted_deletion_anchor._validate_trusted_dependency_contract``; this file
  adds no second authority and no new exemption.
* It never reads the PR body, so it does not depend on the merge-lane binding.

Verdicts (anything else fails closed):

* PASS ``DEPENDENCY_FILES_UNTOUCHED``: no commit of the PR changes either file
  since its unique merge-base with the trusted default-branch commit, so a
  merge keeps main's exact bytes.
* PASS ``DEPENDENCY_CONTRACT_UNCHANGED``: head bytes equal main's bytes.
* PASS ``AUTHORIZED_SNAPSHOT_TRANSITION``: an exact one-use anchor for this PR
  number and these four hashes is already on main, and main has not moved
  either file since the merge-base, so the merge result is exactly the head bytes.
* FAIL ``DEPENDENCY_CONTRACT_DRIFT``: everything else.

Limits, shared with the controller: every verdict is computed against main at
event time and is not re-run when main later moves.  UNCHANGED and AUTHORIZED
bind only the final head bytes, so a rebase-merge can still replay intermediate
edits into main's history (never into its final tree).  Closing the
moved-main window takes a ruleset change, which only the Owner can make: make
this check required with "require branches to be up to date".
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ops import trusted_deletion_anchor as anchor  # noqa: E402

SCHEMA_VERSION = "nexus.trusted_dependency_contract.v1"
WORKFLOW_PATH = ".github/workflows/trusted-dependency-contract.yml"
DEPENDENCY_PATHS = ("pyproject.toml", "uv.lock")
PRODUCT_INIT_PATH = "product/__init__.py"
DRIFT = "DEPENDENCY_CONTRACT_DRIFT"
UNTOUCHED = "DEPENDENCY_FILES_UNTOUCHED"
UNCHANGED = "DEPENDENCY_CONTRACT_UNCHANGED"
AUTHORIZED = "AUTHORIZED_SNAPSHOT_TRANSITION"
DRIFT_REMEDY = (
    "merge origin/main into the PR branch; an intended pyproject.toml/uv.lock change "
    "needs an Owner-approved one-use TRUSTED_PR<N>_DEPENDENCY_SNAPSHOT_TRANSITION "
    "anchor on main first (nexus-dependency-anchor skill)"
)


def _log_detail(value: object) -> str:
    """One bounded printable line; defuses the legacy ``##[`` workflow-command form.

    Every printed line starts with a fixed prefix, so it can never begin with ``::``.
    """

    text = anchor._sanitize_failure_detail(str(value))
    while "##[" in text:
        text = text.replace("##[", "# #[")
    return text


class ContractError(ValueError):
    """Fail-closed trust violation (not a drift verdict)."""


def identity(event: dict[str, Any]) -> dict[str, Any]:
    """Trusted PR identity for this workflow; refuses anything not default-branch."""

    if not isinstance(event, dict):
        raise ContractError("event payload is not an object")
    try:
        repository = anchor._event_value(event, "repository", "full_name")
        default_branch = anchor._event_value(event, "repository", "default_branch")
        base_repo = anchor._event_value(event, "pull_request", "base", "repo", "full_name")
        base_ref = anchor._event_value(event, "pull_request", "base", "ref")
        number = anchor._event_value(event, "pull_request", "number")
        head_sha = anchor._exact_sha(
            anchor._event_value(event, "pull_request", "head", "sha"), "head_sha"
        )
        workflow_sha = anchor._exact_sha(event.get("workflow_sha"), "workflow_sha")
    except ValueError as exc:
        raise ContractError(str(exc)) from None
    if not isinstance(repository, str) or not isinstance(default_branch, str):
        raise ContractError("repository identity is malformed")
    expected_ref = f"{repository}/{WORKFLOW_PATH}@refs/heads/{default_branch}"
    if event.get("event_name") != "pull_request_target" or event.get("workflow_ref") != (
        expected_ref
    ):
        raise ContractError("workflow identity is not trusted default-branch pull_request_target")
    if base_repo != repository or base_ref != default_branch:
        raise ContractError("pull request does not target the trusted default branch")
    if type(number) is not int or number <= 0:
        raise ContractError("pull request number must be a positive integer")
    return {
        "repository": repository,
        "default_branch": default_branch,
        "workflow_ref": expected_ref,
        "workflow_sha": workflow_sha,
        "pull_request_number": number,
        "head_sha": head_sha,
    }


def _tree_entry(repo: Path, revision: str, path: str) -> str:
    """The raw ``ls-tree`` entry (mode, type, id, path); empty when absent."""

    entry = anchor._git(repo, "ls-tree", "--full-tree", revision, "--", path)
    assert isinstance(entry, str)
    return entry


def _regular_blob(repo: Path, revision: str, path: str) -> bytes | None:
    """Bytes of a regular (100644) file at ``revision``; None when absent or not regular."""

    if not anchor._tree_has_regular_file(repo, revision, path):
        return None
    content = anchor._git(repo, "cat-file", "blob", f"{revision}:{path}", binary=True)
    assert isinstance(content, bytes)
    return content


def _same_entries(repo: Path, merge_base_sha: str, revision: str) -> bool:
    """Both dependency files have the same non-empty tree entry at both revisions."""

    for path in DEPENDENCY_PATHS:
        base_entry = _tree_entry(repo, merge_base_sha, path)
        if not base_entry or base_entry != _tree_entry(repo, revision, path):
            return False
    return True


def _no_commit_touched_since(repo: Path, merge_base_sha: str, head_sha: str) -> bool:
    """Every PR-side commit carries the merge-base's exact dependency entries.

    Comparing only head with the merge-base is not enough: a merge-commit merge of
    a sibling PR can move the merge-base GitHub uses to a commit inside this PR's
    own history, so an intermediate commit that changed a file would become the
    effective base and the file change would land.  Any later merge-base is an
    ancestor of head that is not an ancestor of the current one, i.e. one of
    these commits, so requiring all of them to be untouched is sound.
    """

    expected = {path: _tree_entry(repo, merge_base_sha, path) for path in DEPENDENCY_PATHS}
    if not all(expected.values()):
        return False
    commits = anchor._git(repo, "rev-list", f"{merge_base_sha}..{head_sha}")
    assert isinstance(commits, str)
    for commit in commits.split():
        anchor._exact_sha(commit, "commit")
        if any(_tree_entry(repo, commit, path) != expected[path] for path in DEPENDENCY_PATHS):
            return False
    return True


def evaluate(repo: Path, ident: dict[str, Any], *, fetch: bool = True) -> dict[str, Any]:
    """Return the verdict record; ``status`` is PASS or FAIL.  Raises ContractError.

    With ``fetch`` (the workflow path), ``repo`` is the workflow's depth-1 bare
    repository and is only read for its ``origin`` URL.  Both commits are fetched,
    once and with full history, into a fresh bare repository with background
    maintenance off (#2213).  The earlier code deepened ``repo`` in place:
    a depth-1 head fetch, then ``fetch --unshallow`` of both commits.  On GitHub
    that failed with "shallow file has changed since we read it", because a
    detached commit-graph/gc write left behind by the previous fetch raced the
    shallow update.  Without ``fetch``, ``repo`` must already hold both commits
    with full history.
    """

    if not fetch:
        return _evaluate(repo, ident)
    origin = anchor._git(repo, "config", "--get", "remote.origin.url")
    assert isinstance(origin, str)
    if not origin:
        raise ContractError("controller repository has no origin remote")
    with tempfile.TemporaryDirectory(prefix="trusted-dependency-contract-") as scratch:
        full = Path(scratch) / "full.git"
        anchor._init_ephemeral_bare_repo(full)
        anchor._git(full, "remote", "add", "origin", origin)
        anchor._git(full, "fetch", "--no-tags", "origin", ident["workflow_sha"], ident["head_sha"])
        return _evaluate(full, ident)


def _evaluate(repo: Path, ident: dict[str, Any]) -> dict[str, Any]:
    workflow_sha = ident["workflow_sha"]
    head_sha = ident["head_sha"]
    number = ident["pull_request_number"]
    for label, revision in (("trusted", workflow_sha), ("head", head_sha)):
        if anchor._git(repo, "cat-file", "-t", revision) != "commit":
            raise ContractError(f"{label} revision is not a commit")
    trusted: dict[str, bytes] = {}
    for path in DEPENDENCY_PATHS:
        content = _regular_blob(repo, workflow_sha, path)
        if content is None:
            raise ContractError("trusted default branch lacks a regular pyproject.toml/uv.lock")
        trusted[path] = content
    head = {path: _regular_blob(repo, head_sha, path) for path in DEPENDENCY_PATHS}
    record: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "pull_request_number": number,
        "head_sha": head_sha,
        "trusted_sha": workflow_sha,
        "trusted_pyproject_sha256": anchor._sha(trusted["pyproject.toml"]),
        "trusted_uv_lock_sha256": anchor._sha(trusted["uv.lock"]),
        "head_pyproject_sha256": None
        if head["pyproject.toml"] is None
        else anchor._sha(head["pyproject.toml"]),
        "head_uv_lock_sha256": None if head["uv.lock"] is None else anchor._sha(head["uv.lock"]),
    }
    if head == trusted:
        # Both sides hold the same regular-file bytes, so every merge keeps them.
        return {**record, "status": "PASS", "reason_code": UNCHANGED}
    if anchor._git(repo, "rev-parse", "--is-shallow-repository") != "false":
        raise ContractError("dependency contract repository remains shallow")
    try:
        merge_base_sha = anchor._unique_merge_base(repo, workflow_sha, head_sha)
    except ValueError as exc:
        raise ContractError(str(exc)) from None
    record["merge_base_sha"] = merge_base_sha
    # Bytes differ, usually because the branch was cut before main moved a file.
    # Pass when no commit of the PR changed either file since its unique
    # merge-base with the trusted commit: then any merge keeps main's bytes.
    if _no_commit_touched_since(repo, merge_base_sha, head_sha):
        return {**record, "status": "PASS", "reason_code": UNTOUCHED}
    # An anchor binds (main bytes, head bytes). It is honoured only when main did
    # not move either file since the merge-base. Otherwise a three-way merge could
    # produce bytes that match neither snapshot. The controller enforces the same
    # thing through MAIN_MOVED_OVER_GATE_SURFACE.
    head_pyproject, head_uv_lock = head["pyproject.toml"], head["uv.lock"]
    if (
        head_pyproject is not None
        and head_uv_lock is not None
        and _same_entries(repo, merge_base_sha, workflow_sha)
    ):
        try:
            anchor._validate_trusted_dependency_contract(
                trusted["pyproject.toml"],
                head_pyproject,
                trusted["uv.lock"],
                head_uv_lock,
                pull_request_number=number,
                head_product_init_is_regular=anchor._tree_has_regular_file(
                    repo, head_sha, PRODUCT_INIT_PATH
                ),
            )
        except ValueError:
            pass
        else:
            return {**record, "status": "PASS", "reason_code": AUTHORIZED}
    return {**record, "status": "FAIL", "reason_code": DRIFT, "remedy": DRIFT_REMEDY}


def _check(args: argparse.Namespace) -> int:
    event = json.loads(Path(args.event_json).read_text(encoding="utf-8"))
    record = evaluate(Path(args.repo_root), identity(event))
    line = anchor._json(record).decode()
    if args.output:
        Path(args.output).write_text(line + "\n", encoding="utf-8")
    print(line)
    if record["status"] != "PASS":
        print(
            f"trusted dependency contract: {DRIFT}: PR #{record['pull_request_number']} "
            f"changes pyproject.toml/uv.lock without an exact authorized transition; "
            f"{DRIFT_REMEDY}",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("--event-json", required=True)
    check.add_argument("--repo-root", required=True)
    check.add_argument("--output")
    check.set_defaults(function=_check)
    args = parser.parse_args(argv)
    try:
        return int(args.function(args))
    except subprocess.CalledProcessError as exc:
        stderr = anchor._bounded_subprocess_output(exc.stderr)
        print(
            f"trusted dependency contract: failed closed: git exited {exc.returncode}: "
            f"{_log_detail(stderr)}",
            file=sys.stderr,
        )
        return 1
    except (ContractError, ValueError, OSError) as exc:
        print(
            f"trusted dependency contract: failed closed: {_log_detail(exc)}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
