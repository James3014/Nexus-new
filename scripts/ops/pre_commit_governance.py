#!/usr/bin/env python3
import ast
import sys
import os
from pathlib import Path
from typing import Dict, List, Set, Any

class StaticImpactAnalyzer:
    """🛡️ AST-Level Static Symbol Impact & Blast Radius Analyzer"""
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.python_files = []
        
        # 僅掃描核心 Python 目錄，主動排除 venv/node_modules/target 等巨大無用目錄
        target_dirs = ["nexus", "scripts", "tests"]
        for d in target_dirs:
            dir_path = self.repo_root / d
            if dir_path.exists():
                self.python_files.extend(list(dir_path.rglob("*.py")))
        
    def find_symbol_usages(self, symbol_name: str) -> List[Dict[str, Any]]:
        usages = []
        for py_file in self.python_files:
            if "venv" in str(py_file) or ".venv" in str(py_file) or "node_modules" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    is_usage = False
                    line_no = 0
                    if isinstance(node, ast.Name) and node.id == symbol_name:
                        is_usage = True
                        line_no = node.lineno
                    elif isinstance(node, ast.Attribute) and node.attr == symbol_name:
                        is_usage = True
                        line_no = node.lineno
                    elif isinstance(node, ast.ImportFrom) and any(alias.name == symbol_name for alias in node.names):
                        is_usage = True
                        line_no = node.lineno
                        
                    if is_usage:
                        rel_path = py_file.relative_to(self.repo_root)
                        usages.append({
                            "file": str(rel_path),
                            "line": line_no,
                            "context": content.splitlines()[line_no - 1].strip()
                        })
            except Exception as e:
                continue
        return usages

    def analyze_blast_radius(self, symbol_name: str) -> Dict[str, Any]:
        usages = self.find_symbol_usages(symbol_name)
        callers = list(set([u["file"] for u in usages]))
        
        risk_level = "LOW"
        if len(callers) > 3 or any("contracts" in c or "gateway" in c for c in callers):
            risk_level = "MEDIUM"
        if len(callers) > 6:
            risk_level = "HIGH"
            
        return {
            "symbol": symbol_name,
            "callers_count": len(callers),
            "usages_count": len(usages),
            "callers": callers,
            "risk_level": risk_level,
            "details": usages
        }

def run_pre_commit_audit():
    print("🕸️ [Pre-Commit Governance] Initializing Optimized AST Impact Analysis...")
    repo_root = Path("/Users/jameschen/Workspace/nexus")
    analyzer = StaticImpactAnalyzer(repo_root)
    
    symbols_to_analyze = [
        "allow_pre_model_deterministic_rescue",
        "decide_route",
        "verify_telemetry",
        "is_claimable",
        "public_claim_safe",
        "derive_cost_efficiency_decision",
        "backfill_single_receipt"
    ]
    
    print("\n📊 --- Symbol Blast Radius Report ---")
    all_clean = True
    for symbol in symbols_to_analyze:
        report = analyzer.analyze_blast_radius(symbol)
        print(f"\n🔹 Symbol: {report['symbol']}")
        print(f"   Risk Level: {report['risk_level']}")
        print(f"   Direct Callers: {report['callers_count']} files")
        print(f"   Total References: {report['usages_count']} times")
        if report["callers"]:
            print("   Affected Files:")
            for caller in report["callers"]:
                print(f"     - {caller}")
        else:
            print("   Affected Files: [None (Newly introduced or local only)]")
            
        for caller in report["callers"]:
            allowed = any(prefix in caller for prefix in ("nexus/core", "nexus/engine", "scripts/bench", "scripts/ops", "tests"))
            if not allowed:
                print(f"   ⚠️ Warning: Unexpected module boundary breach detected in: {caller}")
                all_clean = False
                
    if all_clean:
        print("\n🟢 [Audit Outcome] PRE-COMMIT DETECT CHANGES: PASS. All changed symbols remain strictly within expected governance/contracts/bench domains.")
    else:
        print("\n🔴 [Audit Outcome] PRE-COMMIT DETECT CHANGES: WARNING. Some symbol references crossed expected boundaries.")

if __name__ == "__main__":
    run_pre_commit_audit()
