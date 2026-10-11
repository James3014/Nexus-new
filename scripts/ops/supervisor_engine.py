import json, sys, os
from pathlib import Path
from datetime import datetime

class SupervisorEngine:
    """🛡️ v23.7 Supervisor Engine: Real-world Task Synthesis."""
    def __init__(self, repo_root):
        self.repo_root = Path(repo_root)

    def run_swarm_mission(self, master_task: str):
        print(f"📡 [Supervisor] Initiating MASTER MISSION: {master_task}")
        
        # 1. 任務拆解 (Decomposition)
        missions = [
            {"id": "ARCH", "tenant": "tenant-000", "file": "docs/inventory_spec.md", "content": "# Inventory System Spec\n- v1.0 Hardened."},
            {"id": "BACKEND", "tenant": "tenant-001", "file": "scripts/engine/inventory_api.py", "content": "class InventoryAPI:\n    def get_stock(self): return 100"},
            {"id": "FRONTEND", "tenant": "tenant-002", "file": "nexus/models/inventory_ui.json", "content": '{"theme": "terminal", "density": "high"}'}
        ]

        # 2. 蜂群發動 (Execution)
        results = []
        for m in missions:
            target_path = self.repo_root / m['file']
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(m['content'])
            
            # 物理證據
            evidence = {
                "task": m['id'],
                "worker": m['tenant'],
                "artifact": m['file'],
                "timestamp": datetime.now().isoformat()
            }
            (self.repo_root / "tenants" / m['tenant'] / "swarm_work.json").write_text(json.dumps(evidence, indent=2))
            print(f"🔗 [Swarm:{m['id']}] Work completed by {m['tenant']}. Artifact: {m['file']}")
            results.append(evidence)
        
        # 3. 總合完成 (Aggregation)
        self.unify(results)

    def unify(self, results):
        """將所有分工產物總合成最終報告"""
        print("\n🏗️ [Supervisor] UNIFYING ALL ARTIFACTS...")
        summary = {
            "mission": "Full-Stack Inventory System",
            "status": "READY_FOR_PROMOTION",
            "total_artifacts": len(results),
            "manifest": results
        }
        (self.repo_root / ".nexus" / "metabolism" / "mission_complete.json").write_text(json.dumps(summary, indent=2))
        print("✅ [Final] Mission Synthetic Completion. Manifest anchored at .nexus/metabolism/mission_complete.json")

# Exit code for "no real delegation backend" (EX_CONFIG), matching LEGACY_EXTRA_REQUIRED.
EXIT_NO_DELEGATION_BACKEND = 78


def main(argv: list[str]) -> int:
    """CLI entry. The engine only replays a fixed synthetic demo, so it must not
    stand in for real delegation: refuse unless the demo is requested explicitly
    against an explicit root, and never write into the caller's checkout by default."""
    if len(argv) >= 3 and argv[0] == "--synthetic-demo" and argv[1] == "--root":
        SupervisorEngine(Path(argv[2])).run_swarm_mission("Build Inventory Monolith")
        return 0
    task = " ".join(argv) or "<none>"
    sys.stderr.write(
        "DELEGATION_BACKEND_UNAVAILABLE: supervisor_engine only replays a fixed synthetic demo "
        f"and cannot delegate task {task!r}. Use `nexus multi-agent` for real worktree delegation.\n"
    )
    return EXIT_NO_DELEGATION_BACKEND


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
