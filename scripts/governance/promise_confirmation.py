#!/usr/bin/env python3
"""CLI for the per-promise confirmation report (#2532 stage 3). Read-only.

Fetches the live Issue, its comments, edit history and PRs with ``gh api`` GET
calls (binary from NEXUS_GH_BIN, default ``gh``) and prints the report from
``nexus.services.promise_confirmation``. It changes nothing on GitHub.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nexus.orchestrator.task_contract import (
    issue_promise_set_identity,
    parse_issue_promise_set,
)
from nexus.services.promise_confirmation import (
    build_promise_confirmation_report,
    emit_promise_blocks,
    emit_witness_templates,
)


class Gh:
    def __init__(self, repo: str) -> None:
        self.repo, self.bin = repo, os.environ.get("NEXUS_GH_BIN", "gh")

    def api(self, *args: str) -> Any:
        out = subprocess.run([self.bin, "api", *args], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def issue(self, n: int) -> dict:
        return self.api(f"repos/{self.repo}/issues/{n}")

    def comments(self, n: int) -> list[dict]:
        data = self.api("--paginate", "--slurp", f"repos/{self.repo}/issues/{n}/comments?per_page=100")
        flat = [c for part in data for c in (part if isinstance(part, list) else [part])]
        return [{"body": c.get("body") or "", "created_at": c.get("created_at"),
                 "author": (c.get("user") or {}).get("login", "")} for c in flat]

    def history(self, n: int) -> list[dict] | None:
        """userContentEdits.diff holds the FULL body of each version (newest first);
        the oldest node is the original. None when it cannot be fetched completely."""
        owner, name = self.repo.split("/")
        query = ('query{repository(owner:"%s",name:"%s"){issue(number:%d){userContentEdits(first:100)'
                 "{totalCount nodes{editedAt diff}}}}}") % (owner, name, n)
        try:
            edits = self.api("graphql", "-f", f"query={query}")["data"]["repository"]["issue"]["userContentEdits"]
        except (subprocess.CalledProcessError, KeyError, TypeError, ValueError):
            return None
        if edits["totalCount"] > len(edits["nodes"]) or any(e.get("diff") is None for e in edits["nodes"]):
            return None
        return [{"edited_at": e["editedAt"], "body": e["diff"]} for e in edits["nodes"]]

    def pr(self, m: int) -> tuple[dict, str]:
        p = self.api(f"repos/{self.repo}/pulls/{m}")
        return ({"number": p["number"], "head_sha": p["head"]["sha"], "merge_sha": p.get("merge_commit_sha") if p.get("merged_at") else None,
                 "created_at": p["created_at"], "merged_at": p.get("merged_at")},
                (p.get("user") or {}).get("login", ""))

    def contains(self, ancestor: str, commit: str) -> bool | None:
        try:
            status = self.api(f"repos/{self.repo}/compare/{ancestor}...{commit}").get("status")
        except (subprocess.CalledProcessError, ValueError):
            return None
        return True if status in ("ahead", "identical") else False if status in ("behind", "diverged") else None


def _markdown(rep: dict) -> str:
    lines = [f"Recommendation: {rep['recommendation']}  (input only, grants nothing)", ""]
    if rep.get("promises"):
        lines += ["| promise | phase/risk | status | reasons | confirmer |", "|---|---|---|---|---|"]
        for r in rep["promises"]:
            v = r["confirmer_verdict"]
            verdict = "-" if not v else v["verdict"] + (" (ignored)" if v["ignored"] else "")
            lines.append(f"| {r['promise_id']} | {r['phase']}/{r['risk']} | {r['status']} | "
                         f"{', '.join(r['reason_codes']) or '-'} | {verdict} |")
        lines.append("")
    if rep.get("reason_codes"):
        lines += ["Reasons: " + ", ".join(rep["reason_codes"]), ""]
    return "\n".join(lines) + "\n" + json.dumps(rep, indent=2, sort_keys=True)


def _emit(path: str, generation: int) -> int:
    items = json.loads(Path(path).read_text())["statements"]
    pr_map = {i["promise_id"]: (i.pop("phase"), i.pop("risk")) for i in items}
    blocks = emit_promise_blocks(items, generation, pr_map)
    parsed = parse_issue_promise_set(blocks)
    if parsed is None:
        raise SystemExit("emitted blocks did not parse")
    identity = issue_promise_set_identity(parsed)
    print(blocks)
    print(emit_witness_templates(items, identity, pr_map))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default="James3014/Nexus-new")
    ap.add_argument("--issue", type=int)
    ap.add_argument("--pr", type=int, action="append", default=[])
    ap.add_argument("--author-session", action="append", default=[])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--now")
    ap.add_argument("--offline-input")
    ap.add_argument("--emit-blocks")
    ap.add_argument("--generation", type=int, default=1)
    args = ap.parse_args(argv)
    if args.emit_blocks:
        return _emit(args.emit_blocks, args.generation)
    if args.offline_input:
        d = json.loads(Path(args.offline_input).read_text())
        table = {(a, c): v for a, c, v in d.get("contains", [])}
        rep = build_promise_confirmation_report(
            issue_body=d["issue_body"], body_history=d.get("body_history"), comments=d["comments"],
            prs=d["prs"], contains=lambda a, c: table.get((a, c)), now=d["now"],
            author_identities=d.get("author_identities", []))
    else:
        if args.issue is None:
            ap.error("--issue is required")
        gh = Gh(args.repo)
        issue = gh.issue(args.issue)
        prs, authors = [], [(issue.get("user") or {}).get("login", ""), *args.author_session]
        for m in args.pr:
            listed, login = gh.pr(m)
            prs.append(listed)
            authors.append(login)
        now = args.now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rep = build_promise_confirmation_report(
            issue_body=issue.get("body") or "", body_history=gh.history(args.issue),
            comments=gh.comments(args.issue), prs=prs, contains=gh.contains, now=now,
            author_identities=[a for a in authors if a])
    print(json.dumps(rep, indent=2, sort_keys=True) if args.json else _markdown(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
