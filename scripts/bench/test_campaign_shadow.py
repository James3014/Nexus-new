import os
from pathlib import Path
from nexus.core.campaign_general import CampaignGeneral

def test_campaign_shadow_run():
    root = Path(os.getcwd())
    print(f"🚀 Initializing CampaignGeneral at {root}")
    commander = CampaignGeneral(root)
    
    intent = "Implement a new Rust module for AST scanning and refactor the core logic"
    print(f"🧠 Decomposing intent: {intent}")
    
    # 觸發 Shadow Mode 掃描
    nodes = commander.decompose_intent(intent, seed=42)
    
    print(f"✅ Generated {len(nodes)} task nodes.")
    
    ledger_path = root / ".nexus/reports/rust_mismatch.jsonl"
    if ledger_path.exists():
        print(f"📈 Shadow Ledger found at {ledger_path}")
        with open(ledger_path, "r") as f:
            lines = f.readlines()
            print(f"📝 Total Ledger Entries: {len(lines)}")
    else:
        print("ℹ️ No mismatches detected (Ledger file not created).")

if __name__ == "__main__":
    try:
        test_campaign_shadow_run()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Error during test: {e}")
