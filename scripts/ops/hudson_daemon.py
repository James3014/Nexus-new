import time
import json
import os
import sys
from pathlib import Path

# [AOS 140.0] HUD Daemon: Persistent Bottom Row Monitoring
# Implementation based on MUSE-NEXUS-Engine-Specification-v22-Eternal.

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_FILE = REPO_ROOT / ".nexus" / "metrics" / "latest_state.json"

def get_status_line():
    try:
        if not STATE_FILE.exists():
            return "AOS: ??? | REGR: ??? | FP: ??? | MODE: BOOTING"
        
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            
        aos = data.get("aos_score", 0.0)
        regr = data.get("regression_rate", 0.0)
        fp = data.get("phantom_fp", 0.0)
        mode = data.get("mode", "UNKNOWN")
        
        # 色彩化邏輯 (ANSI)
        color_aos = "\033[1;32m" if aos >= 140 else "\033[1;33m"
        color_regr = "\033[1;32m" if regr >= 100 else "\033[1;31m"
        color_fp = "\033[1;32m" if fp == 0 else "\033[1;31m"
        reset = "\033[0m"
        
        tag_prefix = f"\033[1;45m [v23 SOTA] \033[0m " if aos >= 152 else ""
        return f"{tag_prefix}{color_aos}AOS: {aos:.1f}{reset} | {color_regr}REGR: {regr:.1f}%{reset} | {color_fp}FP: {fp:.1f}%{reset} | MODE: {mode}"
    except Exception as e:
        return f"HUD ERROR: {str(e)}"

def run_hud_daemon():
    # 使用 ANSI 指令鎖定底行 (v23 Hardened)
    # \033[s: Save cursor | \033[1000H: Move to bottom | \033[u: Restore cursor
    repo_root = Path(__file__).resolve().parents[2]
    lock_path = repo_root / ".nexus" / "maintenance.lock"
    
    while True:
        # 🧪 [Hardening] 維護鎖檢查：若開發者正在操作，暫停 HUD 渲染以釋放資源
        if lock_path.exists():
            time.sleep(10)
            continue
            
        status = get_status_line()
        # 🚀 行動 1: 定位鎖定與背景渲染
        sys.stdout.write("\033[s")           # Save
        sys.stdout.write("\033[1000H")       # Move to row 1000
        sys.stdout.write("\033[K")           # Clear
        sys.stdout.write(f"\033[1;44m [v23] {status} \033[0m") # SOTA Status Line
        sys.stdout.write("\033[u")           # Restore
        sys.stdout.flush()
        
        # 🧪 [Pulse Mode] 降低更新頻率至 5s (原 2s) 以減少 IO 競爭
        time.sleep(5)

if __name__ == "__main__":
    try:
        print("📊 [HUD] Daemon started. Monitoring AOS status in bottom row...")
        run_hud_daemon()
    except KeyboardInterrupt:
        sys.stdout.write("\033[1000H\033[K") # 清除底行
        sys.stdout.flush()
        print("\n📊 [HUD] Daemon stopped.")
