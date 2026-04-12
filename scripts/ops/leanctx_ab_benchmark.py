#!/usr/bin/env python3
import argparse
import json
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Case:
    name: str
    baseline_cmd: List[str]
    leanctx_cmd: Optional[List[str]]  # If None, case is skipped for lean-ctx mode.


def _run(cmd: List[str], timeout_sec: float) -> Dict[str, object]:
    start = time.perf_counter()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        out = p.stdout or ""
        err = p.stderr or ""
        return {
            "ok": p.returncode == 0,
            "returncode": p.returncode,
            "elapsed_ms": round(elapsed_ms, 3),
            "stdout_bytes": len(out.encode("utf-8", errors="ignore")),
            "stdout_lines": out.count("\n"),
            "stderr_bytes": len(err.encode("utf-8", errors="ignore")),
            # Simple heuristic: ~4 chars/token, plus small constant.
            "stdout_tokens_est": int(len(out) / 4) + (10 if out else 0),
        }
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return {
            "ok": False,
            "returncode": None,
            "elapsed_ms": round(elapsed_ms, 3),
            "stdout_bytes": 0,
            "stdout_lines": 0,
            "stderr_bytes": 0,
            "stdout_tokens_est": 0,
            "timeout": True,
        }


def _case_set(repo_root: str) -> List[Case]:
    # Keep the list stable and representative of "AI coding workflow" I/O.
    return [
        Case(
            name="git_status",
            baseline_cmd=["git", "status"],
            leanctx_cmd=["lean-ctx", "-c", "git status"],
        ),
        Case(
            name="git_diff_stat",
            baseline_cmd=["git", "diff", "--stat"],
            leanctx_cmd=["lean-ctx", "-c", "git diff --stat"],
        ),
        Case(
            name="rg_python_defs",
            baseline_cmd=["rg", "-n", "def ", "nexus"],
            leanctx_cmd=["lean-ctx", "-c", "rg -n \"def \" nexus"],
        ),
        Case(
            name="rg_repo_files",
            baseline_cmd=["rg", "--files", "nexus"],
            leanctx_cmd=["lean-ctx", "-c", "rg --files nexus"],
        ),
        Case(
            name="find_nexus_depth2",
            baseline_cmd=["find", "nexus", "-maxdepth", "2", "-type", "f"],
            leanctx_cmd=["lean-ctx", "-c", "find nexus -maxdepth 2 -type f"],
        ),
        Case(
            name="ls_repo_root",
            baseline_cmd=["ls", "-la", repo_root],
            leanctx_cmd=["lean-ctx", "-c", f"ls -la {shlex.quote(repo_root)}"],
        ),
        Case(
            name="read_context_adapter",
            baseline_cmd=["sed", "-n", "1,200p", os.path.join(repo_root, "nexus/core/context_adapter.py")],
            # lean-ctx read uses its own compression modes; default output is still comparable in size.
            leanctx_cmd=["lean-ctx", "read", os.path.join(repo_root, "nexus/core/context_adapter.py"), "-m", "map"],
        ),
    ]


def _summarize(rows: List[Dict[str, object]]) -> Dict[str, object]:
    # Aggregate by case+mode across iterations.
    buckets: Dict[str, Dict[str, List[Dict[str, object]]]] = {}
    for r in rows:
        buckets.setdefault(str(r["case"]), {}).setdefault(str(r["mode"]), []).append(r)

    def avg(items: List[Dict[str, object]], key: str) -> float:
        vals = [float(it.get(key, 0.0) or 0.0) for it in items]
        return sum(vals) / len(vals) if vals else 0.0

    summary: Dict[str, object] = {"cases": [], "deltas": []}
    for case_name, modes in sorted(buckets.items()):
        baseline_rows = modes.get("baseline", [])
        leanctx_rows = modes.get("leanctx", [])
        baseline = {
            "ok_rate": avg([{"ok": 1 if r.get("ok") else 0} for r in baseline_rows], "ok"),
            "elapsed_ms_avg": round(avg(baseline_rows, "elapsed_ms"), 3),
            "stdout_bytes_avg": round(avg(baseline_rows, "stdout_bytes"), 3),
            "stdout_tokens_est_avg": round(avg(baseline_rows, "stdout_tokens_est"), 3),
        }
        leanctx = None
        if leanctx_rows:
            leanctx = {
                "ok_rate": avg([{"ok": 1 if r.get("ok") else 0} for r in leanctx_rows], "ok"),
                "elapsed_ms_avg": round(avg(leanctx_rows, "elapsed_ms"), 3),
                "stdout_bytes_avg": round(avg(leanctx_rows, "stdout_bytes"), 3),
                "stdout_tokens_est_avg": round(avg(leanctx_rows, "stdout_tokens_est"), 3),
            }

        summary["cases"].append({"case": case_name, "baseline": baseline, "leanctx": leanctx})

        if leanctx is not None and baseline["stdout_bytes_avg"] > 0:
            b = float(baseline["stdout_bytes_avg"])
            l = float(leanctx["stdout_bytes_avg"])
            delta_pct = ((l - b) / b) * 100.0
            summary["deltas"].append(
                {
                    "case": case_name,
                    "stdout_bytes_baseline_avg": round(b, 3),
                    "stdout_bytes_leanctx_avg": round(l, 3),
                    "stdout_bytes_delta_pct": round(delta_pct, 3),
                    "elapsed_ms_baseline_avg": baseline["elapsed_ms_avg"],
                    "elapsed_ms_leanctx_avg": leanctx["elapsed_ms_avg"],
                }
            )

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="A/B benchmark: baseline vs lean-ctx wrapped I/O")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--timeout-sec", type=float, default=10.0)
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    repo_root = os.getcwd()
    leanctx_path = shutil.which("lean-ctx")

    cases = _case_set(repo_root)
    rows: List[Dict[str, object]] = []
    meta = {
        "repo_root": repo_root,
        "iterations": args.iterations,
        "timeout_sec": args.timeout_sec,
        "leanctx_path": leanctx_path,
    }

    for i in range(max(1, int(args.iterations))):
        for c in cases:
            b = _run(c.baseline_cmd, args.timeout_sec)
            rows.append({"iteration": i, "case": c.name, "mode": "baseline", **b})
            if leanctx_path and c.leanctx_cmd:
                l = _run(c.leanctx_cmd, args.timeout_sec)
                rows.append({"iteration": i, "case": c.name, "mode": "leanctx", **l})

    out = {"meta": meta, "rows": rows, "summary": _summarize(rows)}
    payload = json.dumps(out, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    print(payload)


if __name__ == "__main__":
    main()
