from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class XRayService:
    """👁️ v23 X-Ray Service: 全域多維度依賴觀測 (Cross-Repo/Multi-Dir)"""
    
    def __init__(self, project_root: str, report_path: str | None = None):
        self.project_root = Path(project_root)
        self.report_path = Path(report_path) if report_path else self.project_root / "xray_report_full.md"

    def run(self, targets: List[str], recursive: bool = True, docker: bool = False) -> str:
        """執行掃描並產出報告"""
        from nexus.core.xray_observer import XRayObserver
        
        if not targets:
            targets = ["nexus/core", "benchmarks", "Autoresearch"]
            
        observer = XRayObserver(targets)
        report = observer.scan(recursive=recursive)
        
        # 產出報告
        with open(self.report_path, "w") as f:
            f.write(f"# v23 X-Ray Full Analysis Report\n\n")
            f.write(f"## Summary\n{report.summary}\n\n")
            f.write(f"## Symbols ({len(report.symbols)})\n")
            
            for s in report.symbols[:50]: f.write(f"- {s}\n")
            if len(report.symbols) > 50: f.write(f"- ... and {len(report.symbols)-50} more\n")
            
            f.write(f"\n## Crossings ({len(report.crossings)})\n")
            for c in report.crossings[:50]: f.write(f"- {c['source']} -> {c['target']}\n")
            if len(report.crossings) > 50: f.write(f"- ... and {len(report.crossings)-50} more\n")
            
            f.write(f"\n## Risks Detected ({len(report.risks)})\n")
            for r in report.risks: f.write(f"⚠️ {r}\n")
            
        return str(self.report_path)
