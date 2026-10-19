"""Pilot-only oracle for rejected-but-verified candidates (NOT the prereg scorer).

The prereg scorer (``real_outcome_scorer`` 1.2.4 ``--sandbox os``) reads the
#1216 sealed store and cannot ingest taskbank rows yet.  For a pilot this
replays the bank's own verification procedure (VERIFY_LOG.md): base commit +
the bank's ``test.patch`` + the candidate diff (test-path blocks stripped),
then the confirm-run node ids in the bank's per-repo venv:

* FAIL_TO_PASS = failed in ``confirm_before`` and passed in ``confirm_after``;
* PASS_TO_PASS = passed in both.

Label mapping follows S0: RESOLVED / PARTIAL / UNRESOLVED / BROKE_EXISTING /
NO_CANDIDATE.  No sandbox: pilot candidates are trusted only because a person
reads them first; never use this for held-out tasks.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.bench.measure_2721.common import git, sha256_text
from scripts.bench.measure_2721.leakage import strip_test_hunks
from scripts.bench.measure_2721.materialize import checkout_base


def node_sets(run_dir: Path) -> tuple[list[str], list[str]]:
    before = json.loads((run_dir / "confirm_before.json").read_text())["tests"]
    after = json.loads((run_dir / "confirm_after.json").read_text())["tests"]
    f2p = sorted(n for n, o in after.items() if o == "PASSED" and before.get(n) != "PASSED")
    p2p = sorted(n for n, o in after.items() if o == "PASSED" and before.get(n) == "PASSED")
    return f2p, p2p


def label(f2p: dict[str, str], p2p: dict[str, str], empty: bool) -> str:
    if empty:
        return "NO_CANDIDATE"
    f2p_ok = all(o == "PASSED" for o in f2p.values())
    p2p_ok = all(o == "PASSED" for o in p2p.values())
    if f2p_ok and p2p_ok:
        return "RESOLVED"
    if not p2p_ok:
        return "BROKE_EXISTING"
    return "PARTIAL" if any(o == "PASSED" for o in f2p.values()) else "UNRESOLVED"


def score(bank: Path, task_id: str, repo: str, base: str, diff: str, work: Path) -> dict[str, Any]:
    run_dir = bank / "runs" / task_id
    f2p_ids, p2p_ids = node_sets(run_dir)
    scored, stripped = strip_test_hunks(diff)
    name = repo.split("/", 1)[1]
    tree = work / "tree"
    checkout_base(bank / "repos" / name, base, tree)
    git(tree, "apply", "--binary", str(run_dir / "test.patch"))
    applied = True
    if scored.strip():
        with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=False) as handle:
            handle.write(scored)
        check = subprocess.run(["git", "apply", "--binary", handle.name], cwd=tree, capture_output=True, text=True)
        os.unlink(handle.name)
        applied = check.returncode == 0
    venv = bank / "venvs" / name
    env = {**os.environ, "PATH": f"{venv}/bin:{os.environ['PATH']}", "VIRTUAL_ENV": str(venv),
           "PYTHONPATH": os.pathsep.join([str(tree / "src"), str(tree), str(bank / "tools" / "plugin")]),
           "TB_REPORT": str(work / "report.json")}
    result = subprocess.run([str(venv / "bin" / "python"), "-m", "pytest", "-p", "tbreport", "-p", "no:cacheprovider",
                             "-rA", "--tb=short", "-q", "--color=no", *f2p_ids, *p2p_ids],
                            cwd=tree, env=env, capture_output=True, text=True, timeout=900)
    outcomes = json.loads((work / "report.json").read_text())["tests"] if (work / "report.json").is_file() else {}
    f2p = {n: outcomes.get(n, "NOT_RUN") for n in f2p_ids}
    p2p = {n: outcomes.get(n, "NOT_RUN") for n in p2p_ids}
    return {
        "schema": "nexus.measure_2721.pilot_oracle.v1",
        "task_id": task_id,
        "label": label(f2p, p2p, not scored.strip()) if applied else "PATCH_DID_NOT_APPLY",
        "f2p_passed": sum(o == "PASSED" for o in f2p.values()), "f2p_total": len(f2p),
        "p2p_passed": sum(o == "PASSED" for o in p2p.values()), "p2p_total": len(p2p),
        "stripped_test_paths": stripped,
        "scored_diff_sha256": sha256_text(scored),
        "pytest_exit": result.returncode,
        "not_prereg_scorer": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bank", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--diff", required=True, help="candidate diff file")
    parser.add_argument("--work", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    held_out = {json.loads(line)["id"] for line in Path(args.bank, "tasks.jsonl").read_text().splitlines() if line}
    if args.task_id in held_out:
        parser.error("held-out task: the pilot oracle never scores tasks.jsonl tasks")
    result = score(Path(args.bank), args.task_id, args.repo, args.base, Path(args.diff).read_text(), Path(args.work))
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
