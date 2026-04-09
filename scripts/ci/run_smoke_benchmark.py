#!/usr/bin/env python3
import json
import os
import sys
import shutil
import csv
import subprocess
from pathlib import Path
from datetime import datetime, timezone

# Add the project root to sys.path so we can import nexus
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from nexus.engine.coordinator import NexusEngine
from nexus.engine.config import EngineConfig
import logging

logger = logging.getLogger("SmokeBenchmark")
logging.basicConfig(level=logging.INFO)

BENCHMARK_SCHEMA_VERSION = "v1.0"

class SmokeBenchmarkRunner:
    SMOKE_CASES_VERSION = "v1.0"
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.catalog_path = self.project_root / "cases" / "catalog.json"
        self.backup_path = self.project_root / "cases" / "catalog.json.bak"
        self.manifest_path = self.project_root / "cases" / "smoke_manifest.json"
        self.reports_dir = self.project_root / ".nexus" / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.output_csv = "smoke_benchmark.csv"
        
    def run(self) -> dict:
        """Execute smoke benchmark subset and produce fingerprinted report."""
        if not self.manifest_path.exists():
            logger.error("Smoke manifest not found at %s", self.manifest_path)
            sys.exit(1)
            
        manifest = json.loads(self.manifest_path.read_text())
        smoke_ids = set(manifest.get("cases", []))
        
        if not self.catalog_path.exists():
            logger.error("Full catalog not found at %s", self.catalog_path)
            sys.exit(1)
            
        # 1. Backup and mock catalog
        logger.info("Backing up catalog and generating smoke subset...")
        shutil.copy2(self.catalog_path, self.backup_path)
        
        try:
            full_catalog = json.loads(self.catalog_path.read_text())
            smoke_cases = [c for c in full_catalog.get("cases", []) if c.get("id") in smoke_ids]
            full_catalog["cases"] = smoke_cases
            full_catalog["slots"]["target_count"] = len(smoke_cases)
            self.catalog_path.write_text(json.dumps(full_catalog, indent=2))
            
            # 2. Run Benchmark
            logger.info("Initializing NexusEngine for smoke run...")
            os.environ["NEXUS_SANDBOX_MODE"] = "smoke-ci"
            engine = NexusEngine(EngineConfig(project_root=self.project_root, benchmark_mode=True))
            results = engine.run_benchmark(framework="smoke", task_count=len(smoke_cases), output_csv=self.output_csv)
            
            # 3. Collect Governance Metrics
            metrics = self._collect_governance_metrics(results)
            
            report = {
                "smoke_version": self.SMOKE_CASES_VERSION,
                "environment": self._capture_fingerprint(),
                "governance_metrics": metrics,
                "results": results,
            }
            
            # 4. Save JSON Report
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            report_file = self.reports_dir / f"smoke_{timestamp}.json"
            report_file.write_text(json.dumps(report, indent=2))
            logger.info("Smoke report written to %s", report_file)
            
            # 5. Save Markdown Report
            md_report_file = self.reports_dir / "NEXUS_BENCHMARK_REPORT.md"
            md_report_file.write_text(self._render_markdown_report(report))
            logger.info("Markdown report written to %s", md_report_file)
            
            # Check PASS threshold (expect 100% for smoke)
            if metrics["pass_rate"] < 1.0:
                logger.error("Smoke tests failed! Pass rate is %.1f%%", metrics["pass_rate"] * 100)
                sys.exit(1)
            else:
                logger.info("Smoke tests passed successfully!")
                
            return report
            
        finally:
            # Always restore catalog
            logger.info("Restoring original catalog...")
            shutil.copy2(self.backup_path, self.catalog_path)
            self.backup_path.unlink()
            
    def _capture_fingerprint(self) -> dict:
        commit_sha = "unknown"
        try:
            commit_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=self.project_root
            ).decode().strip()
        except Exception:
            pass

        manifest_version = "unknown"
        if self.manifest_path.exists():
            try:
                manifest_version = json.loads(self.manifest_path.read_text()).get("version", "unknown")
            except Exception:
                pass
            
        return {
            "benchmark_schema_version": BENCHMARK_SCHEMA_VERSION,
            "problem_set_version": manifest_version,
            "python_version": sys.version.split()[0],
            "model_version": os.environ.get("NEXUS_MODEL", "unknown"),
            "sandbox_mode": os.environ.get("NEXUS_SANDBOX_MODE", "unknown"),
            "commit_sha": commit_sha,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _render_markdown_report(self, report: dict) -> str:
        env = report.get("environment", {})
        metrics = report.get("governance_metrics", {})
        lines = [
            "# Nexus Benchmark Report",
            "",
            "## Environment Fingerprint",
            f"| Field | Value |",
            f"|---|---|",
            f"| Benchmark Schema | `{env.get('benchmark_schema_version', 'n/a')}` |",
            f"| Problem Set Version | `{env.get('problem_set_version', 'n/a')}` |",
            f"| Model Version | `{env.get('model_version', 'n/a')}` |",
            f"| Commit SHA | `{env.get('commit_sha', 'n/a')}` |",
            f"| Sandbox Mode | `{env.get('sandbox_mode', 'n/a')}` |",
            f"| Timestamp | {env.get('timestamp', 'n/a')} |",
            "",
            "## Governance Metrics",
            f"| Metric | Rate |",
            f"|---|---|",
            f"| ✅ Pass Rate | `{metrics.get('pass_rate', 0)*100:.1f}%` |",
            f"| 👻 Phantom Rate | `{metrics.get('phantom_rate', 0)*100:.1f}%` |",
            f"| ⛔ Pregate Skip Rate | `{metrics.get('pregate_skip_rate', 0)*100:.1f}%` |",
            f"| 🧑‍💻 Human Review Rate | `{metrics.get('human_review_rate', 0)*100:.1f}%` |",
            "",
            "> Report generated by `scripts/ci/run_smoke_benchmark.py`",
        ]
        return "\n".join(lines)
        
    def _collect_governance_metrics(self, results: list) -> dict:
        if not results:
            return {"pass_rate": 0.0, "phantom_rate": 0.0, "pregate_skip_rate": 0.0, "human_review_rate": 0.0}
            
        total = len(results)
        passed = sum(1 for r in results if r.get("status") == "SUCCESS")
        
        # Determine phantoms if they are passed as metrics
        phantoms = sum(1 for r in results if r.get("phantom_detected", False))
        pregate_skips = sum(1 for r in results if r.get("pregate_skip", False))
        human_reviews = sum(1 for r in results if r.get("review_status") == "HUMAN_REVIEW" or "HUMAN" in str(r.get("status", "")))
        
        return {
            "pass_rate": passed / total,
            "phantom_rate": phantoms / total,
            "pregate_skip_rate": pregate_skips / total,
            "human_review_rate": human_reviews / total,
        }

if __name__ == "__main__":
    runner = SmokeBenchmarkRunner(Path.cwd())
    runner.run()
