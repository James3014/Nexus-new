
import sys
import json
from pathlib import Path
from nexus.engine.coordinator import NexusEngine
from nexus.core.commander import Commander
from nexus.core.state_io import StateIO
from nexus.core.router import SkillsRouter
from nexus.core.context_hub import ContextHub

def test_v9_hardening():
    print("🧪 [Test] Starting Nexus v9 Hardening Smoke Test...")
    project_root = Path("/tmp/nexus_v9_worker")
    run_dir = project_root / ".runs/test_hardening"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Setup
    state_io = StateIO(str(project_root))
    hub = ContextHub(str(project_root))
    router = SkillsRouter(str(project_root))
    commander = Commander(str(run_dir), state_io=state_io, router=router, context_hub=hub)
    engine = NexusEngine(project_root, run_dir=run_dir, state_io=state_io, commander=commander, router=router)
    
    # 模擬一個需要外部研究的任務 (包含關鍵字 "最新")
    task = "分析最新 Nexus v9 規格並修復與 Felo CLI 的對接問題"
    
    print(f"🏃 Running engine.run_bug for task: {task}")
    # 使用 dry_run 以防執行真實 patch 但保留生命週期流轉
    engine.run_bug(task, dry_run=True)
    
    # 驗證產出物
    print("\n🔍 [Verification] Checking artifacts...")
    
    results = {
        "router_decisions.jsonl": (project_root / "scripts/core/router_decisions.jsonl").exists(),
        "researchpack.json": (run_dir / "researchpack.json").exists(),
        "crystal_lessons.jsonl": (project_root / "obsidian/crystal_lessons.jsonl").exists()
    }
    
    for file, exists in results.items():
        status = "✅ Found" if exists else "❌ MISSING"
        print(f"  - {file}: {status}")
        if exists:
            # 讀取最後一行內容確認
            with open(list(project_root.glob(f"**/{file}"))[0], "r") as f:
                lines = f.readlines()
                print(f"    Content sample: {lines[-1][:120]}...")

    if all(results.values()):
        print("\n✨ [SUCCESS] All v9 hardening features verified!")
    else:
        print("\n⚠️ [FAILED] Some features are missing artifacts.")
        sys.exit(1)

if __name__ == "__main__":
    test_v9_hardening()
