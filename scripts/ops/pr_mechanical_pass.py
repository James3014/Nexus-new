#!/usr/bin/env python3
"""Deterministic pre-push mechanical pass for Nexus-new PRs (#2625).

Run it in a PR worktree before pushing. No model is involved and a second run
changes nothing. Against the merge-base with ``--base-ref`` (default
``origin/main``) it:

1. sorts imports (``ruff check --select I``) on changed Python files, applying
   only the fixes whose import block overlaps a changed line;
2. formats only the changed hunks (``ruff format --preview --range``); a file that
   is new in the PR is formatted whole. A legacy file is never reformatted
   outside the lines the PR touched (nexus-new-pr skill, #2315);
3. appends ``docs/testing/test_impact_map.md`` rows for paths the impact planner
   cannot match, through ``pr_impact_gate.py``'s ``--write-rows`` helpers;
4. with ``--pr-body FILE``, lints the PR body markers and bindings with
   ``pr_preflight.py --only bindings`` (read-only).

It prints a short report of what it changed. ``--check`` changes nothing and
exits 1 when the pass would change something. The working tree (committed or
not, plus untracked files) is what gets compared to the merge-base.

This tool holds no authority: it is an authoring aid, and every gate still
judges the pushed result.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "nexus.pr_mechanical_pass.v1"
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)


@dataclass
class PassReport:
    base_sha: str
    check_only: bool
    formatted: dict[str, int] = field(default_factory=dict)
    imports_sorted: list[str] = field(default_factory=list)
    impact_rows: dict[str, list[str]] = field(default_factory=dict)
    impact_unresolved: list[str] = field(default_factory=list)
    impact_unresolved_reasons: dict[str, str] = field(default_factory=dict)
    bindings: str = "SKIP"
    bindings_detail: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.formatted or self.imports_sorted or self.impact_rows)

    @property
    def needs_attention(self) -> bool:
        return bool(self.errors or self.impact_unresolved or self.bindings == "FAIL")


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def changed_paths(repo: Path, base_sha: str) -> tuple[list[str], set[str]]:
    """(paths that differ from base in the working tree, paths that are new)."""
    status = _git(repo, "diff", "--name-status", "--no-renames", "-z", base_sha).stdout
    fields = [item for item in status.split("\0") if item]
    paths: list[str] = []
    added: set[str] = set()
    for code, path in zip(fields[0::2], fields[1::2]):
        paths.append(path)
        if code.startswith("A"):
            added.add(path)
    untracked = _git(repo, "ls-files", "--others", "--exclude-standard", "-z").stdout
    for path in (item for item in untracked.split("\0") if item):
        paths.append(path)
        added.add(path)
    return sorted(dict.fromkeys(paths)), added


def changed_line_ranges(old: str, new: str) -> list[tuple[int, int]]:
    """1-based inclusive line ranges of ``new`` that differ from ``old`` (git's diff)."""
    with tempfile.TemporaryDirectory() as tmp:
        old_path, new_path = Path(tmp, "old"), Path(tmp, "new")
        old_path.write_text(old, encoding="utf-8")
        new_path.write_text(new, encoding="utf-8")
        diff = subprocess.run(
            ["git", "diff", "--no-index", "--no-color", "-U0", str(old_path), str(new_path)],
            text=True,
            capture_output=True,
            check=False,
        ).stdout
    ranges: list[tuple[int, int]] = []
    for match in _HUNK.finditer(diff):
        start, count = int(match.group(1)), int(match.group(2) or "1")
        if count == 0:
            continue
        end = start + count - 1
        if ranges and start <= ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], max(end, ranges[-1][1]))
        else:
            ranges.append((start, end))
    return ranges


def _overlaps(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= r_end and r_start <= end for r_start, r_end in ranges)


def _ruff(
    ruff: str, args: list[str], source: str, filename: str, cwd: Path
) -> subprocess.CompletedProcess:
    # Run inside the repo with an absolute stdin filename, so ruff always resolves
    # the repo's own pyproject config (isort first-party, line length, excludes),
    # whatever directory the pass was started from.
    return subprocess.run(
        [ruff, *args, "--stdin-filename", str((cwd / filename).resolve()), "-"],
        cwd=cwd,
        input=source,
        text=True,
        capture_output=True,
        check=False,
    )


def _offset(lines: list[str], row: int, column: int) -> int:
    return sum(len(line) for line in lines[: row - 1]) + column - 1


def sort_imports(
    ruff: str, source: str, filename: str, ranges: list[tuple[int, int]] | None, cwd: Path
) -> str:
    """Apply ruff's isort fixes whose span overlaps ``ranges`` (None = whole file)."""
    lint = _ruff(
        ruff,
        ["check", "--select", "I", "--output-format", "json", "--force-exclude", "--exit-zero"],
        source,
        filename,
        cwd,
    )
    if lint.returncode != 0:
        raise RuntimeError(f"ruff check failed on {filename}: {lint.stderr.strip()}")
    edits: list[tuple[int, int, str]] = []
    lines = re.findall(r"[^\n]*\n|[^\n]+$", source)
    for finding in json.loads(lint.stdout or "[]"):
        fix = finding.get("fix") or {}
        start, end = finding["location"]["row"], finding["end_location"]["row"]
        if not fix.get("edits") or (ranges is not None and not _overlaps(start, end, ranges)):
            continue
        for edit in fix["edits"]:
            begin = _offset(lines, edit["location"]["row"], edit["location"]["column"])
            finish = _offset(lines, edit["end_location"]["row"], edit["end_location"]["column"])
            edits.append((begin, finish, edit.get("content") or ""))
    for begin, finish, content in sorted(edits, reverse=True):
        source = source[:begin] + content + source[finish:]
    return source


def format_ranges(
    ruff: str, source: str, filename: str, ranges: list[tuple[int, int]] | None, cwd: Path
) -> str:
    """``ruff format --preview`` on ``ranges`` bottom-up (None = whole file)."""
    spans: list[list[str]] = (
        [[]] if ranges is None else [[f"--range={s}:1-{e + 1}:1"] for s, e in reversed(ranges)]
    )
    for span in spans:
        result = _ruff(
            ruff, ["format", "--preview", "--force-exclude", *span], source, filename, cwd
        )
        if result.returncode != 0:
            raise RuntimeError(f"ruff format failed on {filename}: {result.stderr.strip()}")
        source = result.stdout
    return source


def _base_text(repo: Path, base_sha: str, path: str) -> str:
    result = _git(repo, "show", f"{base_sha}:{path}", check=False)
    return result.stdout if result.returncode == 0 else ""


def ruff_step(
    repo: Path, base_sha: str, paths: list[str], added: set[str], ruff: str, report: PassReport
) -> None:
    for path in paths:
        target = repo / path
        if not path.endswith(".py") or not target.is_file() or target.is_symlink():
            continue
        try:
            original = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        base = "" if path in added else _base_text(repo, base_sha, path)
        whole = path in added or not base
        try:
            ranges = None if whole else changed_line_ranges(base, original)
            if ranges == []:
                continue
            text = sort_imports(ruff, original, path, ranges, repo)
            if text != original:
                report.imports_sorted.append(path)
            ranges = None if whole else changed_line_ranges(base, text)
            if ranges == []:
                formatted = text
            else:
                formatted = format_ranges(ruff, text, path, ranges, repo)
        except (RuntimeError, ValueError, KeyError) as exc:
            report.errors.append(str(exc))
            continue
        if formatted != text:
            report.formatted[path] = 1 if ranges is None else len(ranges)
        if formatted != original and not report.check_only:
            target.write_text(formatted, encoding="utf-8")


def impact_step(repo: Path, paths: list[str], report: PassReport) -> None:
    from scripts.ops import pr_impact_gate as gate

    plan = gate.build_impact_plan(paths, root=repo)
    unmatched = list(plan.unmatched_paths)
    if not unmatched:
        return
    if report.check_only:
        proposal = gate.propose_impact_rows(unmatched, root=repo)
    else:
        proposal = gate.write_missing_impact_rows(unmatched, root=repo)
    report.impact_rows = proposal.mapped
    report.impact_unresolved = proposal.unresolved
    report.impact_unresolved_reasons = proposal.unresolved_reasons


def bindings_step(repo: Path, base_ref: str, body_file: Path, report: PassReport) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts/ops/pr_preflight.py"),
            "--repo",
            str(repo),
            "--base-ref",
            base_ref,
            "--no-fetch",
            "--only",
            "bindings",
            "--body-file",
            str(body_file),
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    report.bindings = "PASS" if result.returncode == 0 else "FAIL"
    report.bindings_detail = [
        line for line in lines if not line.startswith(("nexus-pr-preflight", "RESULT:"))
    ][:20]
    if result.returncode not in (0, 1):
        report.bindings_detail.append(result.stderr.strip()[-500:])


def _resolve_ruff(repo: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    venv_ruff = repo / ".venv" / "bin" / "ruff"
    if venv_ruff.is_file() and os.access(venv_ruff, os.X_OK):
        return str(venv_ruff)
    found = shutil.which("ruff")
    if not found:
        raise SystemExit("ruff not found: run `uv sync --frozen --all-extras` or pass --ruff")
    return found


def render(report: PassReport) -> str:
    verb = "would " if report.check_only else ""
    lines = [f"pr_mechanical_pass  base={report.base_sha[:12]}  check_only={report.check_only}"]
    for path in report.imports_sorted:
        lines.append(f"imports:  {verb}sort imports in {path}")
    for path, hunks in sorted(report.formatted.items()):
        lines.append(f"format:   {verb}format {hunks} changed hunk(s) in {path}")
    for path, targets in sorted(report.impact_rows.items()):
        lines.append(f"impact:   {verb}add map row {path} -> {', '.join(targets)}")
    why = {
        "deleted": "the PR deletes it; the gate will run the full suite unless it is mapped",
        "too_many_candidates": "more candidate tests than a row may list; map it by hand",
        "unsafe_path": "path cannot be written into the Markdown table",
    }
    for path in report.impact_unresolved:
        reason = report.impact_unresolved_reasons.get(path, "")
        detail = why.get(reason, "no test names, imports or mentions it")
        lines.append(f"impact:   NO ROW for {path}: {detail}")
    lines.append(f"bindings: {report.bindings}")
    lines.extend(f"          {line}" for line in report.bindings_detail)
    lines.extend(f"error:    {error}" for error in report.errors)
    state = (
        "NEEDS_ATTENTION" if report.needs_attention else "CHANGED" if report.changed else "CLEAN"
    )
    lines.append(f"RESULT: {state}")
    return "\n".join(lines)


def run_pass(
    repo: Path,
    *,
    base_ref: str = "origin/main",
    check_only: bool = False,
    pr_body: Path | None = None,
    ruff: str | None = None,
    skip_ruff: bool = False,
    skip_impact: bool = False,
) -> PassReport:
    repo = repo.resolve()
    base_sha = _git(repo, "merge-base", base_ref, "HEAD").stdout.strip()
    report = PassReport(base_sha=base_sha, check_only=check_only)
    paths, added = changed_paths(repo, base_sha)
    # A docs-only diff needs no ruff at all.
    if not skip_ruff and any(path.endswith(".py") for path in paths):
        ruff_step(repo, base_sha, paths, added, _resolve_ruff(repo, ruff), report)
    if not skip_impact:
        impact_step(repo, paths, report)
    if pr_body is not None:
        bindings_step(repo, base_ref, pr_body, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pr_mechanical_pass", description=(__doc__ or "").split("\n")[0]
    )
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--pr-body", type=Path, help="PR body file to lint (bindings)")
    parser.add_argument("--check", action="store_true", help="change nothing; exit 1 if needed")
    parser.add_argument("--ruff", help="ruff executable (default REPO/.venv/bin/ruff)")
    parser.add_argument("--skip-ruff", action="store_true")
    parser.add_argument("--skip-impact", action="store_true")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(_git(args.repo, "rev-parse", "--show-toplevel").stdout.strip())
    if repo.resolve() != ROOT.resolve() and not args.skip_impact:
        raise SystemExit(
            f"the impact step reads {ROOT}'s impact map; run this repo's own copy or --skip-impact"
        )
    report = run_pass(
        repo,
        base_ref=args.base_ref,
        check_only=args.check,
        pr_body=args.pr_body,
        ruff=args.ruff,
        skip_ruff=args.skip_ruff,
        skip_impact=args.skip_impact,
    )
    if args.json:
        payload = {"schema": SCHEMA, **asdict(report)}
        payload["changed"], payload["needs_attention"] = report.changed, report.needs_attention
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render(report))
    if report.needs_attention or (args.check and report.changed):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
