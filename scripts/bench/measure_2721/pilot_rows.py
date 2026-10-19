"""Build task rows for pilots/dry runs from rejected-but-verified candidates.

Only candidates that the bank's selection run verified (``results.jsonl``
status ``ok``) and that are **not** in the held-out ``tasks.jsonl`` are
eligible, so a pilot never touches a held-out task.  The row carries only
what the harness needs (id, repo, base, issue text); no gold or test patch.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.bench.measure_2721.common import read_jsonl, write_jsonl


def pilot_rows(bank: Path, ids: Sequence[str]) -> list[dict[str, Any]]:
    held_out = {row["id"] for row in read_jsonl(bank / "tasks.jsonl")}
    results = {row["id"]: row for row in read_jsonl(bank / "results.jsonl")}
    rows = []
    for task_id in ids:
        if task_id in held_out:
            raise ValueError(f"{task_id} is a held-out task; pilots may not use it")
        result = results.get(task_id)
        if result is None or result.get("status") != "ok":
            raise ValueError(f"{task_id} is not a verified candidate")
        repo = result["repo"]
        cands = json.loads((bank / "cand" / f"{repo.replace('/', '__')}.json").read_text(encoding="utf-8"))
        cand = next(c for c in cands if int(c["pr"]) == int(result["pr"]))
        issues = cand.get("issues") or []
        if len(issues) != 1:
            raise ValueError(f"{task_id}: needs exactly one linked issue, has {len(issues)}")
        statement = f"{issues[0]['title']}\n\n{issues[0].get('body') or ''}".strip()
        rows.append({"id": task_id, "set": "PILOT", "repo": repo, "base_commit": result["base_commit"],
                     "problem_statement": statement, "test_patch": ""})
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bank", required=True, help="taskbank-2721 directory (read only)")
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    rows = pilot_rows(Path(args.bank), args.ids)
    write_jsonl(Path(args.out), rows)
    print(json.dumps({"rows": len(rows), "out": args.out}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
