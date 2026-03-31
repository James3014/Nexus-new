import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import argparse

# Config
POLICY_MEMORY_PATH = Path(".nexus/knowledge/policy_memory.jsonl")
OUTCOME_EVENTS_PATH = Path(".nexus/metrics/skill_outcome_events.jsonl")
DEFAULT_ARCHIVE_DIR = Path(".nexus/archive/policy_memory/")
DEFAULT_REPORT_JSON = Path(".nexus/reports/audit_integrity_report.json")
DEFAULT_REPORT_MD = Path(".nexus/reports/audit_integrity_report.md")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("skills_policy_audit")

class PolicyAudit:
    def __init__(self, project_root: Path, archive_dir: Path, min_confidence: float = 0.90):
        self.project_root = project_root
        self.archive_dir = archive_dir
        self.min_confidence = min_confidence
        self.policy_path = project_root / POLICY_MEMORY_PATH
        self.outcome_path = project_root / OUTCOME_EVENTS_PATH
        self.outcome_lookup: Dict[str, Dict[str, Any]] = {}

    def _load_outcome_indices(self):
        if not self.outcome_path.exists():
            return
        with self.outcome_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    event = json.loads(line)
                    did = event.get("decision_id")
                    if did:
                        if did not in self.outcome_lookup or event.get("source") == "pipeline.crystallize":
                            self.outcome_lookup[did] = event
                except: continue
        logger.info(f"Indexed {len(self.outcome_lookup)} outcome events.")

    def run_audit(self, apply: bool, quarantine_tasks: Set[str], quarantine_sources: Set[str]):
        self._load_outcome_indices()
        stats = self._init_stats()
        
        if not self.policy_path.exists(): return stats

        active_rows, archive_cal, archive_noise, archive_legacy = [], [], [], []
        audit_time = datetime.now(timezone.utc).isoformat()

        with self.policy_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    stats["total_records_seen"] += 1
                    stats["active_records_before"] += 1
                    
                    # 1. Base Coverage (Before)
                    if row.get("source"): stats["source_coverage_before"] += 1
                    if row.get("phase"): stats["phase_coverage_before"] += 1
                    if row.get("updated_at") or row.get("created_at"): stats["updated_at_coverage_before"] += 1

                    # 2. Heuristic Enrichment
                    did = row.get("decision_id")
                    evidence = self.outcome_lookup.get(did) if did else None
                    enriched = False
                    confidence = 1.0

                    # A) Use evidence if available
                    if evidence:
                        if not row.get("source"):
                            row["source"] = evidence.get("source", "pipeline.crystallize")
                            enriched = True
                        if not row.get("phase"):
                            row["phase"] = evidence.get("phase", "global")
                            enriched = True
                        if not row.get("updated_at"):
                            row["updated_at_inferred"] = evidence.get("timestamp_utc")
                            row["heuristic_estimate"] = True
                            row["enrichment_method"] = "decision_id_lookup"
                            row["enrichment_confidence"] = 1.0
                            row["enriched_at"] = audit_time
                            enriched = True
                    
                    # B) Static Rule Fallback
                    elif not row.get("source"):
                        row["source"] = "static.governance"
                        row["phase"] = row.get("phase") or "global"
                        row["updated_at_inferred"] = audit_time
                        row["heuristic_estimate"] = True
                        row["enrichment_method"] = "static_rule_defaults"
                        row["enrichment_confidence"] = 0.8
                        row["enriched_at"] = audit_time
                        enriched = True
                        confidence = 0.8

                    if enriched:
                        stats["heuristically_enriched_records"] += 1
                        if confidence >= self.min_confidence:
                            stats["high_confidence_enriched_records"] += 1
                        else:
                            stats["low_confidence_enriched_records"] += 1

                    # 3. Quarantine Filter
                    source = row.get("source", "")
                    task_id = row.get("task_id") or (evidence.get("task_id") if evidence else None)
                    
                    if source in quarantine_sources:
                        archive_cal.append(row)
                        stats["archived_calibration_records"] += 1
                        continue
                    if task_id and any(n in task_id for n in quarantine_tasks):
                        archive_noise.append(row)
                        stats["archived_environment_noise_records"] += 1
                        continue
                    
                    # 4. Integrity Check for Active
                    if row.get("skill_id") or row.get("rule_id"):
                        if row.get("source") and row.get("phase"):
                            active_rows.append(row)
                            stats["active_records_after"] += 1
                            stats["source_coverage_after"] += 1
                            stats["phase_coverage_after"] += 1
                            if row.get("updated_at") or row.get("updated_at_inferred") or row.get("created_at"):
                                stats["updated_at_coverage_after"] += 1
                        else:
                            archive_legacy.append(row)
                            stats["archived_unknown_legacy_records"] += 1
                    else:
                        archive_legacy.append(row)
                        stats["archived_unknown_legacy_records"] += 1

                except: continue

        stats["archived_records_total"] = len(archive_cal) + len(archive_noise) + len(archive_legacy)
        if apply: self._apply_changes(active_rows, archive_cal, archive_noise, archive_legacy)
        return stats

    def _init_stats(self):
        return {k: 0 for k in [
            "total_records_seen", "active_records_before", "active_records_after",
            "archived_records_total", "archived_calibration_records",
            "archived_environment_noise_records", "archived_unknown_legacy_records",
            "source_coverage_before", "source_coverage_after",
            "phase_coverage_before", "phase_coverage_after",
            "updated_at_coverage_before", "updated_at_coverage_after",
            "heuristically_enriched_records", "high_confidence_enriched_records",
            "low_confidence_enriched_records"
        ]}

    def _apply_changes(self, active, cal, noise, legacy):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.policy_path.exists():
            self.policy_path.rename(self.policy_path.with_suffix(f".bak.{ts}"))
        with self.policy_path.open("w", encoding="utf-8") as f:
            for r in active: f.write(json.dumps(r, ensure_ascii=False) + "\n")
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        for cat, rows in [("calibration_sim", cal), ("environment_noise_OFF001", noise), ("unknown_legacy", legacy)]:
            if rows:
                p = self.archive_dir / f"{cat}_{ts}.jsonl"
                with p.open("w", encoding="utf-8") as f:
                    for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")

def generate_reports(stats: Dict[str, Any], json_path: Path, md_path: Path):
    stats["timestamp"] = datetime.now(timezone.utc).isoformat()
    with json_path.open("w", encoding="utf-8") as f: json.dump(stats, f, indent=4)
    with md_path.open("w", encoding="utf-8") as f:
        f.write("# Policy Memory Integrity Audit Report\n\n")
        f.write(f"- **Timestamp**: {stats['timestamp']}\n")
        f.write(f"- **Total Records Seen**: {stats['total_records_seen']}\n\n")
        f.write("## 1. Coverage Summary\n\n| Metric | Before (%) | After (%) |\n| :--- | :---: | :---: |\n")
        t, a = max(1, stats['active_records_before']), max(1, stats['active_records_after'])
        f.write(f"| Source | {stats['source_coverage_before']*100/t:.1f}% | {stats['source_coverage_after']*100/a:.1f}% |\n")
        f.write(f"| Phase | {stats['phase_coverage_before']*100/t:.1f}% | {stats['phase_coverage_after']*100/a:.1f}% |\n")
        f.write(f"| Updated_at | {stats['updated_at_coverage_before']*100/t:.1f}% | {stats['updated_at_coverage_after']*100/a:.1f}% |\n\n")
        f.write(f"## 2. Quarantine\n- **Active**: {stats['active_records_after']}\n- **Total Archived**: {stats['archived_records_total']}\n")
        f.write(f"  - Calibration: {stats['archived_calibration_records']}\n  - Noise: {stats['archived_environment_noise_records']}\n  - Legacy: {stats['archived_unknown_legacy_records']}\n\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--archive-dir", type=Path, default=DEFAULT_ARCHIVE_DIR)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_MD)
    parser.add_argument("--min-confidence", type=float, default=0.9)
    args = parser.parse_args()
    audit = PolicyAudit(Path("."), args.archive_dir, args.min_confidence)
    stats = audit.run_audit(args.apply, {"OFF-001"}, {"calibration.sim"})
    generate_reports(stats, args.report_json, args.report_md)
    print(f"Audit completed. Report at {args.report_md}")
