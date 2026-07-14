import argparse
import csv
import json
import sys
from pathlib import Path
from datetime import datetime


def generate_summary(csv_path: str) -> dict:
    p = Path(csv_path)
    if not p.exists():
        print(json.dumps({"error": f"input not found: {csv_path}"}), file=sys.stderr)
        sys.exit(1)

    results = []
    with open(p, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(row)

    if not results:
        return {"status": "EMPTY", "total": 0}

    total = len(results)
    successes = sum(1 for r in results if r.get("status") == "PASS")
    fail_count = total - successes
    avg_velocity = sum(float(r.get("learning_velocity") or 1.0) for r in results) / total
    policy_hits = sum(1 for r in results if r.get("policy_hit", "").strip())

    failures = []
    for r in results:
        if r.get("status") != "PASS":
            failures.append({
                "task_id": r.get("task_id", "unknown"),
                "status": r.get("status", "FAIL"),
                "phase_path": r.get("phase_path", "N/A"),
            })

    return {
        "status": "PASS",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total": total,
        "successes": successes,
        "fail_count": fail_count,
        "avg_velocity": round(avg_velocity, 2),
        "policy_hits": policy_hits,
        "failures": failures,
    }


def render_markdown(summary: dict) -> str:
    if summary["status"] == "EMPTY":
        return "# Night Shift Summary\n\nNo results to summarize.\n"
    lines = [
        f"# Nexus Night Shift Report - {summary['date']}",
        "",
        "## Key Indicators",
        f"- **Success Rate**: {summary['successes']}/{summary['total']} ({summary['successes']/summary['total']*100:.1f}%)",
        f"- **Avg Learning Velocity**: {summary['avg_velocity']}v",
        f"- **Policy Hit Rate**: {summary['policy_hits']}/{summary['total']} ({summary['policy_hits']/summary['total']*100:.1f}%)",
        "",
        "## Failures",
    ]
    if summary["failures"]:
        lines.append("| Task ID | Status | Phase Path |")
        lines.append("| :--- | :--- | :--- |")
        for f in summary["failures"]:
            lines.append(f"| {f['task_id']} | {f['status']} | {f['phase_path']} |")
    else:
        lines.append("All cases passed.")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nexus Night Shift Summary Generator")
    parser.add_argument("--input", required=True, help="Path to CSV input file")
    parser.add_argument("--output", default=None, help="Output path (omit for stdout)")
    args = parser.parse_args(argv)

    summary = generate_summary(args.input)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(render_markdown(summary), encoding="utf-8")
        print(json.dumps({"status": summary["status"], "output": args.output}))
    else:
        print(render_markdown(summary))

    return 0 if summary["status"] != "EMPTY" or summary.get("total", 0) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
