import json
import os
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone

# Config
PROJECT_ROOT = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))
OUTCOME_EVENTS = PROJECT_ROOT / ".nexus/metrics/skill_outcome_events.jsonl"
BASELINE_FILE = PROJECT_ROOT / ".nexus/reports/baseline/baseline_manifest.json"

class ObsWindowTracker:
    def __init__(self, target_samples=30):
        self.target_samples = target_samples
        self.report_json = PROJECT_ROOT / ".nexus/reports/observation_window_report.json"
        self.report_md = PROJECT_ROOT / ".nexus/reports/observation_window_report.md"

    def get_crystallize_samples(self, start_ts=None):
        samples = []
        if not OUTCOME_EVENTS.exists(): return samples
        
        with OUTCOME_EVENTS.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    event = json.loads(line)
                    if event.get("source") == "pipeline.crystallize":
                        # If we have a start_ts (new window), filter by time
                        if start_ts and event.get("updated_at", "") < start_ts:
                            continue
                        samples.append(event)
                except: continue
        return samples

    def run_report(self):
        # Load baseline for start_ts
        start_ts = None
        baseline_commit = "unknown"
        if BASELINE_FILE.exists():
            with BASELINE_FILE.open("r") as f:
                config = json.load(f)
                start_ts = config.get("created_at")
                baseline_commit = config.get("baseline_commit", "unknown")

        samples = self.get_crystallize_samples(start_ts)
        count = len(samples)
        
        status = "IN_PROGRESS"
        if count >= self.target_samples:
            status = "COMPLETED"

        report = {
            "count": count,
            "target": self.target_samples,
            "status": status,
            "baseline": baseline_commit,
            "started_at": start_ts,
            "latest_samples": samples[-10:] if samples else []
        }

        # Save JSON
        with self.report_json.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        # Save MD
        with self.report_md.open("w", encoding="utf-8") as f:
            f.write(f"# Observation Window Report: {count}/{self.target_samples}\n\n")
            f.write(f"- **Baseline**: {baseline_commit}\n")
            f.write(f"- **Started At**: {start_ts}\n")
            f.write(f"- **Status**: {status}\n\n")
            f.write("## 1. Top 10 Samples (Latest)\n\n")
            f.write("| Index | Timestamp | Decision ID | Skill | Result |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- |\n")
            for idx, s in enumerate(report["latest_samples"]):
                ts = s.get("updated_at", "N/A")
                did = s.get("decision_id", "N/A")
                sk = s.get("skill_id", "N/A")
                res = "PASS" if s.get("pass") else "FAIL"
                f.write(f"| {idx+1} | {ts} | {did} | {sk} | {res} |\n")
        
        print(f"Status: {count}/{self.target_samples} samples collected.")

    def abort_window(self, reason):
        print(f"🚩 Aborting Observation Window due to: {reason}")
        if self.report_json.exists():
            with self.report_json.open("r") as f:
                report = json.load(f)
            report["status"] = "ABORTED"
            report["abort_reason"] = reason
            
            # Archive it
            archive_path = PROJECT_ROOT / f".nexus/reports/observation_window_report_aborted_{int(datetime.now().timestamp())}.json"
            with archive_path.open("w") as f:
                json.dump(report, f, indent=2)
            print(f"  + Archived to: {archive_path.name}")
        
    def reset_window(self):
        print("🔄 Resetting Observation Window Sequence...")
        if self.report_json.exists(): self.report_json.unlink()
        if self.report_md.exists(): self.report_md.unlink()
        print("  + Status: 0/30 (Report Cleaned for new sequence)")

    def update_baseline(self):
        print("📊 Updating Observation Baseline (Machine-Truth Alignment)...")
        try:
            curr_git = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        except: curr_git = "unknown"
        
        # We also lock the timestamp to define the start of the window
        baseline = {
            "baseline_commit": curr_git,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "target_samples": 30
        }
        with open(BASELINE_FILE, "w") as f:
            json.dump(baseline, f, indent=2)
        print(f"  + New Baseline & Start TS Locked: {curr_git}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--abort", action="store_true")
    parser.add_argument("--reason", type=str, default="manual_abort")
    args = parser.parse_args()

    tracker = ObsWindowTracker()
    
    if args.abort:
        tracker.abort_window(args.reason)
        return

    if args.reset:
        tracker.reset_window()
    if args.baseline:
        tracker.update_baseline()
    
    # Always show status after commands
    tracker.run_report()

if __name__ == "__main__":
    main()
