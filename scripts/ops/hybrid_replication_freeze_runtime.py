#!/usr/bin/env python3
"""Freeze the hybrid-replication runtime as an immutable artifact outside ``main``.

Authority: RESEARCH_OBSERVATION_ONLY. Decision D1: the runtime under test is a
detached git worktree at one revision plus a pinned, read-only copy of
``nexus-agy-dispatch`` inside the live root. The live binding JSON is the identity
authority; this script writes a new binding whose ``strong_online`` pin points at the
pinned copy, so later commits to ``main`` cannot move the execution identity.

The output binding is always written ``NOT_READY``; opening a generation is a separate
manifest step (see ``docs/research/hybrid_replication_v2/RUNBOOK.md``).
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any, Sequence

RECEIPT_SCHEMA = "nexus.hybrid_replication.runtime_freeze.v1"
BINDING_SCHEMA = "nexus.hybrid_replication.live_binding.v1"
DISPATCH_NAME = "nexus-agy-dispatch"
DISPATCH_RELATIVE = Path("scripts") / "ops" / DISPATCH_NAME
# Kept equal to nexus.hybrid_replication_live.AGY_EXECUTION_GENERATION_PATTERN.
GENERATION_PATTERN = re.compile(r"^AGY_[A-Z0-9_]+_V\d+$")
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")

EXIT_USAGE = 1
EXIT_REFUSED = 2


class FreezeError(Exception):
    """A refusal; ``code`` is the process exit code."""

    def __init__(self, message: str, code: int = EXIT_REFUSED) -> None:
        super().__init__(message)
        self.code = code


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 B607
        ["git", *args], check=False, capture_output=True, text=True
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _worktree_head(runtime: Path) -> str | None:
    completed = _git("-C", str(runtime), "rev-parse", "HEAD")
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _validate_revision(source: Path, revision: str) -> None:
    if not REVISION_PATTERN.fullmatch(revision):
        raise FreezeError("revision_must_be_40_hex", EXIT_USAGE)
    completed = _git("-C", str(source), "rev-parse", "--verify", f"{revision}^{{commit}}")
    if completed.returncode != 0 or completed.stdout.strip() != revision:
        raise FreezeError(f"revision_not_a_commit_in_source_repo:{revision}", EXIT_USAGE)


def _build_binding(
    base: dict[str, Any],
    *,
    revision: str,
    generation: str,
    runtime: Path,
    pin: Path,
    pin_sha256: str,
) -> dict[str, Any]:
    binding = copy.deepcopy(base)
    for key in ("agy_dispatch_path", "agy_dispatch_sha256"):
        binding.pop(key, None)
    agy = binding.get("agy")
    if isinstance(agy, dict):
        agy.pop("dispatch_path", None)
        agy.pop("dispatch_sha256", None)
    online = binding.get("strong_online")
    if not isinstance(online, dict):
        online = {}
        binding["strong_online"] = online
    online.pop("dispatch_path", None)
    online.pop("dispatch_sha256", None)
    online["provider"] = "agy"
    online["agy_dispatch_path"] = str(pin)
    online["agy_dispatch_sha256"] = pin_sha256
    online["execution_generation"] = generation
    binding["source_revision"] = revision
    binding["runtime_root"] = str(runtime)
    binding["activation_state"] = "NOT_READY"
    return binding


def freeze(
    *,
    source_repo: Path,
    revision: str,
    live_root: Path,
    generation: str,
    base_binding: Path,
    output_binding: Path,
    dry_run: bool,
) -> dict[str, Any]:
    if not GENERATION_PATTERN.fullmatch(generation):
        raise FreezeError("generation_must_match_AGY_<LABEL>_V<N>", EXIT_USAGE)
    _validate_revision(source_repo, revision)
    if output_binding.exists() or output_binding.is_symlink():
        raise FreezeError(f"output_binding_exists:{output_binding}")
    try:
        base = json.loads(base_binding.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeError(f"base_binding_unreadable:{exc}", EXIT_USAGE) from exc
    if not isinstance(base, dict) or base.get("schema") != BINDING_SCHEMA:
        raise FreezeError("base_binding_schema_mismatch", EXIT_USAGE)

    live_root = live_root.resolve()
    runtime = live_root / "runtime" / revision
    pin_dir = live_root / "runtime-pins" / generation
    pin = pin_dir / DISPATCH_NAME
    output_binding = output_binding.resolve()

    reused_worktree = False
    if runtime.exists():
        head = _worktree_head(runtime)
        if head != revision:
            raise FreezeError(f"runtime_exists_at_other_head:{runtime}:{head}")
        reused_worktree = True

    reused_pin = False
    if dry_run:
        # Nothing is created, so the dispatcher is read from the source repo object store
        # (reuse) or reported from the existing pin; the receipt is a plan.
        if reused_worktree:
            source_dispatch = runtime / DISPATCH_RELATIVE
            if not source_dispatch.is_file():
                raise FreezeError(f"dispatcher_missing_in_runtime:{source_dispatch}")
            planned_sha = _sha256_file(source_dispatch)
        else:
            shown = subprocess.run(  # nosec B603 B607
                [
                    "git",
                    "-C",
                    str(source_repo),
                    "show",
                    f"{revision}:{DISPATCH_RELATIVE.as_posix()}",
                ],
                check=False,
                capture_output=True,
            )
            if shown.returncode != 0:
                raise FreezeError(f"dispatcher_missing_at_revision:{DISPATCH_RELATIVE}")
            planned_sha = hashlib.sha256(shown.stdout).hexdigest()
        if pin.exists():
            if _sha256_file(pin) != planned_sha:
                raise FreezeError(f"pin_exists_with_different_content:{pin}")
            reused_pin = True
        return _receipt(
            revision,
            generation,
            runtime,
            pin,
            planned_sha,
            output_binding,
            None,
            reused_worktree,
            reused_pin,
            planned=True,
        )

    if not reused_worktree:
        runtime.parent.mkdir(parents=True, exist_ok=True)
        added = _git("-C", str(source_repo), "worktree", "add", "--detach", str(runtime), revision)
        if added.returncode != 0:
            raise FreezeError(f"git_worktree_add_failed:{added.stderr.strip()}")
    source_dispatch = runtime / DISPATCH_RELATIVE
    if not source_dispatch.is_file():
        raise FreezeError(f"dispatcher_missing_in_runtime:{source_dispatch}")

    source_sha = _sha256_file(source_dispatch)
    if pin.exists():
        if _sha256_file(pin) != source_sha:
            raise FreezeError(f"pin_exists_with_different_content:{pin}")
        reused_pin = True
    else:
        pin_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_dispatch, pin)
    os.chmod(pin, 0o555)
    pin_sha = _sha256_file(pin)

    binding = _build_binding(
        base,
        revision=revision,
        generation=generation,
        runtime=runtime,
        pin=pin,
        pin_sha256=pin_sha,
    )
    text = json.dumps(binding, indent=2, sort_keys=True) + "\n"
    output_binding.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_binding.open("x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError as exc:
        raise FreezeError(f"output_binding_exists:{output_binding}") from exc
    output_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return _receipt(
        revision,
        generation,
        runtime,
        pin,
        pin_sha,
        output_binding,
        output_sha,
        reused_worktree,
        reused_pin,
        planned=False,
    )


def _receipt(
    revision: str,
    generation: str,
    runtime: Path,
    pin: Path,
    pin_sha256: str,
    output_binding: Path,
    output_sha256: str | None,
    reused_worktree: bool,
    reused_pin: bool,
    *,
    planned: bool,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "revision": revision,
        "generation": generation,
        "runtime_root": str(runtime),
        "dispatcher_pin_path": str(pin),
        "dispatcher_sha256": pin_sha256,
        "output_binding": str(output_binding),
        "output_binding_sha256": output_sha256,
        "reused": {"worktree": reused_worktree, "pin": reused_pin},
    }
    if planned:
        receipt["dry_run"] = True
    return receipt


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", required=True, type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--live-root", required=True, type=Path)
    parser.add_argument("--generation", required=True)
    parser.add_argument("--base-binding", required=True, type=Path)
    parser.add_argument("--output-binding", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        receipt = freeze(
            source_repo=args.source_repo,
            revision=args.revision,
            live_root=args.live_root,
            generation=args.generation,
            base_binding=args.base_binding,
            output_binding=args.output_binding,
            dry_run=args.dry_run,
        )
    except FreezeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return exc.code
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
