#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Dict, List, Any
import sys

# Ensure nexus package is in path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

class DrClawAnalyst:
    """🦖 DrClaw v22: RCA & Regression Analyst"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.runs_dir = self.project_root / ".nexus" / "runs"

    def analyze(self, input_file: str, output_file: str):
        print(f"🦖 DrClaw: Starting RCA analysis on {input_file}...")
        
        if not Path(input_file).exists():
            print(f"❌ Input file {input_file} not found.")
            return

        fails = []
        with open(input_file, "r") as f:
            for line in f:
                if line.strip():
                    fails.append(json.loads(line))

        results = []
        for fail in fails:
            # 優先使用 decision_id 作為索引
            task_id = fail.get("decision_id") or fail.get("task_id")
            # 尋找對應的 .musestate
            state_files = list(self.runs_dir.glob(f"task-*/.musestate"))
            matched_state = None
            if task_id:
                for sf in state_files:
                    try:
                        content = json.loads(sf.read_text())
                        # 比對 task_id 或相關 ID
                        if content.get("task_id") == task_id or content.get("decision_id") == task_id:
                            matched_state = content
                            break
                    except:
                        continue
            
            category = self._classify(fail, matched_state)
            results.append({
                "task_id": task_id,
                "category": category,
                "details": fail,
                "state": matched_state
            })

        self._write_report(results, output_file)
        print(f"✅ RCA Report generated: {output_file}")

    def _classify(self, fail: Dict, state: Dict) -> str:
        # A: 路由錯誤 (Routing)
        # 如果是 nexus:research 但任務內容與研究無關
        if state:
            desc = state.get("metadata", {}).get("task_description", "").lower()
            if "fix" in desc or "bug" in desc or "patch" in desc:
                return "Category A: Routing Error (Research triggered for BugFix)"
        
        # B: Handoff 錯誤 (Handoff)
        # 如果步驟為空且 token 為 0
        if fail.get("regression_pass_rate") == 0.0 and state and not state.get("steps_history"):
            return "Category B: Handoff/Typed Pipeline Error (Task setup failed)"
            
        # C: 環境錯誤 (Environment)
        return "Category C: Environment/Other"

    def _write_report(self, results: List[Dict], output_file: str):
        report = [
            "# RCA Report: Nexus v22 Regression Analysis",
            f"Generated At: {Path('.').absolute()}",
            "",
            "| Task ID | Category | Summary |",
            "| --- | --- | --- |"
        ]
        
        counts = {"A": 0, "B": 0, "C": 0}
        for r in results:
            cat = r["category"]
            if "Category A" in cat: counts["A"] += 1
            elif "Category B" in cat: counts["B"] += 1
            else: counts["C"] += 1
            
            summary = r["state"].get("metadata", {}).get("task_description", "N/A") if r["state"] else "State Missing"
            report.append(f"| {r['task_id']} | {cat} | {summary} |")
        
        report.extend([
            "",
            "## Summary Statistics",
            f"- **Category A (Routing)**: {counts['A']}",
            f"- **Category B (Handoff)**: {counts['B']}",
            f"- **Category C (Environment)**: {counts['C']}",
            "",
            "## Conclusion",
            "Based on the analysis, the major bottleneck is **Category " + ("B" if counts["B"] > counts["A"] else "A") + "**.",
            "Suggested Fix: Check `swarm_orchestrator.py` TypedHandoffAdapter logic."
        ])
        
        Path(output_file).write_text("\n".join(report))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="rca_report.md")
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    
    analyst = DrClawAnalyst(args.project_root)
    analyst.analyze(args.input, args.output)
