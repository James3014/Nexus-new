#!/usr/bin/env python3
"""Surface red governance signals as deduplicated GitHub Issue comments (#1897).

Two subcommands, both driven by scheduled workflows:

``nightly``
    The scheduled Tier 3 full regression failed. Find the one open tracking
    Issue (label ``nightly-regression`` and the fixed title), creating it if
    absent, and comment with the run link once per run id.

``golden-owners``
    ``check_golden_finding_owners.py --strict`` flagged findings. Comment on
    the owner Issue (default #117) once per distinct flag set.

The script only reads and writes Issue metadata through ``gh``. It never adds
merge authority, never blocks a PR and never edits repository content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

NIGHTLY_LABEL = "nightly-regression"
NIGHTLY_TITLE = "Nightly Tier 3 full regression is red"
GOLDEN_OWNER_ISSUE = 117

Runner = Callable[[Sequence[str], str | None], str]


def gh_runner(args: Sequence[str], stdin: str | None = None) -> str:
    completed = subprocess.run(
        ["gh", *args], input=stdin, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip()[-400:] or f"gh {args[0]} failed")
    return completed.stdout


def _comment_bodies(repo: str, issue: int, run: Runner) -> list[str]:
    raw = run(
        ["api", "--paginate", f"repos/{repo}/issues/{issue}/comments", "--jq", ".[].body | @json"],
        None,
    )
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _comment_once(repo: str, issue: int, marker: str, body: str, run: Runner) -> bool:
    if any(marker in existing for existing in _comment_bodies(repo, issue, run)):
        return False
    run(["issue", "comment", str(issue), "-R", repo, "--body-file", "-"], f"{body}\n\n{marker}\n")
    return True


def find_or_create_nightly_issue(repo: str, run: Runner) -> int:
    raw = run(
        [
            "issue",
            "list",
            "-R",
            repo,
            "--state",
            "open",
            "--label",
            NIGHTLY_LABEL,
            "--json",
            "number,title",
            "--limit",
            "100",
        ],
        None,
    )
    matches = sorted(
        int(item["number"])
        for item in json.loads(raw or "[]")
        if item.get("title") == NIGHTLY_TITLE
    )
    if matches:
        return matches[0]
    run(
        [
            "label",
            "create",
            NIGHTLY_LABEL,
            "-R",
            repo,
            "--color",
            "B60205",
            "--description",
            "Scheduled full regression failure tracking (#1897)",
            "--force",
        ],
        None,
    )
    url = run(
        [
            "issue",
            "create",
            "-R",
            repo,
            "--title",
            NIGHTLY_TITLE,
            "--label",
            NIGHTLY_LABEL,
            "--body-file",
            "-",
        ],
        "The scheduled Tier 3 full regression (`.github/workflows/pytest.yml`) failed. "
        "Each red run adds one comment below. Triage each failure: fix it, or add it to "
        "`tests/nightly_quarantine_items/<slug>.py` (one module per entry, with a cause and an Issue; "
        "to retire one set `ENTRY = None`, never delete the file). Refs #1897.\n",
    )
    return int(url.strip().rstrip("/").rsplit("/", 1)[-1])


def report_nightly(repo: str, run_id: str, run_url: str, sha: str, run: Runner) -> dict[str, Any]:
    issue = find_or_create_nightly_issue(repo, run)
    marker = f"<!-- nexus-nightly-run:{run_id} -->"
    body = f"Scheduled full regression failed: {run_url}\n\nHead: `{sha}`"
    commented = _comment_once(repo, issue, marker, body, run)
    return {"issue": issue, "commented": commented, "marker": marker}


def golden_flag_fingerprint(report: dict[str, Any]) -> tuple[str, list[str]]:
    lines = sorted(
        f"{row['case_id']}:{','.join(sorted(row.get('flags') or []))}"
        for row in report.get("findings", [])
        if row.get("flags")
    )
    if report.get("error"):
        lines.append(f"REPORT_ERROR:{report['error']}")
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]
    return digest, lines


def report_golden_owners(
    repo: str, issue: int, report_path: Path, run_url: str, run: Runner
) -> dict[str, Any]:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report = {"error": f"report_unreadable:{type(exc).__name__}"}
    fingerprint, lines = golden_flag_fingerprint(report)
    if not lines:
        return {"issue": issue, "commented": False, "flagged": []}
    marker = f"<!-- nexus-golden-owner-flags:{fingerprint} -->"
    body = (
        "`check_golden_finding_owners.py --strict` flagged Golden findings whose owner "
        f"Issues are closed or unobservable. Re-adjudicate them (#1897).\n\nRun: {run_url}\n\n"
        + "\n".join(f"- `{line}`" for line in lines)
    )
    commented = _comment_once(repo, issue, marker, body, run)
    return {"issue": issue, "commented": commented, "flagged": lines, "marker": marker}


def main(argv: list[str] | None = None, *, run: Runner = gh_runner) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").partition("\n")[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-url", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    nightly = sub.add_parser("nightly")
    nightly.add_argument("--run-id", required=True)
    nightly.add_argument("--sha", required=True)
    golden = sub.add_parser("golden-owners")
    golden.add_argument("--report", type=Path, required=True)
    golden.add_argument("--issue", type=int, default=GOLDEN_OWNER_ISSUE)
    args = parser.parse_args(argv)
    if args.command == "nightly":
        result = report_nightly(args.repo, args.run_id, args.run_url, args.sha, run)
    else:
        result = report_golden_owners(args.repo, args.issue, args.report, args.run_url, run)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
