#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from statistics import mean, quantiles

def main() -> int:
    input_path = Path(".nexus/metrics/learning_gate_calibration.jsonl")
    report_json_path = Path(".nexus/metrics/learning_gate_calibration_report.json")
    report_md_path = Path(".nexus/metrics/learning_gate_calibration_report.md")

    if not input_path.exists():
        print(f"No calibration data found at {input_path}")
        return 1

    rows = []
    for line in input_path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))

    if not rows:
        print("Calibration data is empty.")
        return 1

    total_runs = len(rows)
    # Join Key Integrity Check
    missing_task_ids = [r.get("run_id") for r in rows if not r.get("task_id")]
    if missing_task_ids:
        print(f"⚠️ Warning: Runs {missing_task_ids} are missing task_id! Joinability impaired.")

    pattern_reuses = [r.get("pattern_reuse", 0.0) for r in rows]
    next_run_hits = [r.get("next_run_hit", 0.0) for r in rows]
    
    learning_fails = [r for r in rows if not r.get("learning_gate_pass", False)]
    
    # False Pain: Learning fails, but it was actually a good run (repair success & acceptance pass)
    false_pains = [r for r in learning_fails if r.get("repair_success", False) and r.get("acceptance_pass", False)]
    
    learning_passes = [r for r in rows if r.get("learning_gate_pass", False)]
    
    # Leak Risk: Learning passes, but it's a risky/bad run (retry > 2 or phantom blocked)
    leak_risks = [r for r in learning_passes if r.get("retry_count", 0) > 2 or r.get("phantom_blocked", False)]

    def _stats(arr):
        if not arr:
            return {"mean": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0}
        if len(arr) < 4: # Not enough data for quartiles easily
            return {"mean": round(mean(arr), 2), "p25": min(arr), "p50": min(arr), "p75": max(arr)}
        q = quantiles(arr, n=4)
        return {
            "mean": round(mean(arr), 2),
            "p25": round(q[0], 2),
            "p50": round(q[1], 2),
            "p75": round(q[2], 2),
        }

    report = {
        "total_runs": total_runs,
        "learning_gate_fail_rate": round(len(learning_fails) / total_runs * 100, 2),
        "false_pain_rate": round(len(false_pains) / total_runs * 100, 2),
        "leak_risk_rate": round(len(leak_risks) / total_runs * 100, 2),
        "stats": {
            "pattern_reuse": _stats(pattern_reuses),
            "next_run_hit": _stats(next_run_hits),
        },
        "correlations": {
            "warn_vs_repair_fail": round(len([r for r in learning_fails if not r.get("repair_success", False)]) / max(1, len(learning_fails)) * 100, 2),
            "warn_vs_retry_spike": round(len([r for r in learning_fails if r.get("retry_count", 0) > 0]) / max(1, len(learning_fails)) * 100, 2),
            "warn_vs_long_duration": 0.0, # Will compute below
        },
        "recommendation": "",
    }

    # Duration correlation: Is duration of fails higher than passes?
    pass_durations = [r.get("duration_secs", 0.0) for r in learning_passes]
    fail_durations = [r.get("duration_secs", 0.0) for r in learning_fails]
    if pass_durations and fail_durations:
        avg_pass = mean(pass_durations)
        avg_fail = mean(fail_durations)
        report["correlations"]["warn_vs_long_duration"] = round((avg_fail / avg_pass - 1) * 100, 2) if avg_pass > 0 else 0.0


    # Decide recommendation
    if total_runs < 30:
        report["recommendation"] = f"Insufficient data ({total_runs} runs). Need at least 30 for baseline."
    elif report["false_pain_rate"] > 5.0:
        report["recommendation"] = "DO NOT UPGRADE. False Pain rate is too high. Tuning required."
    elif report["leak_risk_rate"] > 5.0:
        report["recommendation"] = "DO NOT UPGRADE. Leak Risk is too high. Learning Gate is too loose."
    else:
        report["recommendation"] = "READY FOR UPGRADE to Soft Signal (Stage 1)."

    report_json_path.write_text(json.dumps(report, indent=2) + "\n")

    md_lines = [
        "# Learning Gate Calibration Report",
        "",
        f"- **Total Runs Analyzed**: {total_runs}",
        f"- **Learning Gate Fail Rate**: {report['learning_gate_fail_rate']}%",
        f"- **False Pain Rate**: {report['false_pain_rate']}%  *(Learning blocked a good lesson)*",
        f"- **Leak Risk Rate**: {report['leak_risk_rate']}%  *(Learning accepted a risky lesson)*",
        f"- **Joinability**: {'OK' if not missing_task_ids else 'PARTIAL'} (Missing task_id in {len(missing_task_ids)} runs)",
        "",
        "## Distribution Stats",
        "*(Note: lesson_quality source is C-Phase Health Metrics)*",

        "",
        "| Metric | Mean | P25 | Median (P50) | P75 |",
        "|---|---|---|---|---|",
        f"| Pattern Reuse | {report['stats']['pattern_reuse']['mean']} | {report['stats']['pattern_reuse']['p25']} | {report['stats']['pattern_reuse']['p50']} | {report['stats']['pattern_reuse']['p75']} |",
        f"| Next Run Hit | {report['stats']['next_run_hit']['mean']} | {report['stats']['next_run_hit']['p25']} | {report['stats']['next_run_hit']['p50']} | {report['stats']['next_run_hit']['p75']} |",
        "",
        "## Correlation Analysis (Stage 1 Warning Signals)",
        "",
        "| Correlation Metric | Value | Interpretation |",
        "|---|---|---|",
        f"| Warning vs. Repair Fail | {report['correlations']['warn_vs_repair_fail']}% | % of warnings that had `repair_success=False` |",
        f"| Warning vs. Retry > 0 | {report['correlations']['warn_vs_retry_spike']}% | % of warnings that required retries |",
        f"| Warning vs. Duration Boost | {report['correlations']['warn_vs_long_duration']}% | How much longer failed-learning runs took vs. passes |",
        "",
        "## Recommendation",
        f"> **{report['recommendation']}**",
    ]

    report_md_path.write_text("\n".join(md_lines) + "\n")
    print(f"Analysis saved to {report_md_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
