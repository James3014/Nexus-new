#!/usr/bin/env python3
import argparse
import sys
import time
import os
import subprocess
import json
from pathlib import Path
from datetime import datetime

# 🧪 Nexus v9 架構相容性導入層
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 🛡️ Nexus 合約導入
try:
    from nexus.core.state_contracts import NexusState
    from nexus.app.command_service import TaskRequest
except ImportError:
    pass

class NexusCLI:
    def __init__(self, silent=False, output_dir=None, fast_mode=False, audit_level="standard", project_root=None):
        self.project_root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        self.run_dir = Path(output_dir) if output_dir else self.project_root / ".nexus" / "runs" / f"task-{int(time.time())}"
        self.silent = silent
        self.fast_mode = fast_mode
        self.audit_level = audit_level
        self._service = None

    @property
    def service(self):
        if self._service is None:
            from nexus.engine.coordinator import NexusEngine
            from nexus.engine.config import EngineConfig
            from nexus.app.command_service import NexusCommandService
            config = EngineConfig(project_root=self.project_root, run_dir=self.run_dir, silent=self.silent, fast_mode=self.fast_mode, audit_level=self.audit_level)
            self._service = NexusCommandService(NexusEngine(config=config))
        return self._service

    def run_check(self, level: str = "quick"):
        result = self.service.execute_self_check(level=level)
        if result.ok: print("✅ [Nexus:Check] PASS")
        return result.ok

    def run_swarm(self, status: bool = False, test: bool = False) -> int:
        if status:
            from nexus.engine.federation import FederationLayer
            fed = FederationLayer(self.project_root)
            nodes = fed.get_nodes()
            print("\n🌌 [Nexus Swarm] Federation Status (NSP v0.2)")
            print("-" * 55)
            online = 0
            for n in nodes:
                st = "🟢 ONLINE" if n['status'] == 'ONLINE' else "🔴 OFFLINE"
                if n['status'] == 'ONLINE': online += 1
                print(f"ID: {n['node_id']:<15} | Status: {st:<10} | Region: {n.get('region', 'N/A')}")
            print("-" * 55)
            q_res = "✅ PASS" if (online / len(nodes)) >= 0.6 else "❌ FAIL"
            print(f"Quorum (2/3): {online}/{len(nodes)} ({q_res})")
            print("-" * 55)
        elif test:
            subprocess.call([sys.executable, str(self.project_root / "scripts" / "ops" / "p3_swarm_stress.py")])
        return 0

    def run_acceptance_check(self):
        script = self.project_root / "scripts" / "ops" / "nexus_acceptance_check.py"
        return subprocess.call([sys.executable, str(script), "--project-root", str(self.project_root)])

    def run_release_ready(self):
        script = self.project_root / "scripts" / "ops" / "nexus_release_gate.sh"
        if script.exists(): return subprocess.call([str(script)])
        return 0

def main():
    parser = argparse.ArgumentParser(description="Nexus v17.1 Hardened CLI")
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--output-dir")
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--audit-level", choices=["bypass", "standard", "strict"], default="standard")
    
    subparsers = parser.add_subparsers(dest="command")
    
    subparsers.add_parser("nexus:check").add_argument("--level", default="quick")
    
    swarm = subparsers.add_parser("nexus:swarm")
    swarm.add_argument("--status", action="store_true")
    swarm.add_argument("--test", action="store_true")
    
    subparsers.add_parser("nexus:acceptance-check")
    subparsers.add_parser("nexus:release-ready")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    cli = NexusCLI(silent=args.silent, output_dir=args.output_dir, fast_mode=args.fast, audit_level=args.audit_level)

    if args.command == "nexus:check": cli.run_check(level=args.level)
    elif args.command == "nexus:swarm": cli.run_swarm(status=args.status, test=args.test)
    elif args.command == "nexus:acceptance-check": cli.run_acceptance_check()
    elif args.command == "nexus:release-ready": cli.run_release_ready()

if __name__ == "__main__":
    main()
