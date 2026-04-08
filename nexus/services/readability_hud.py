import json
from typing import Any, Dict, List
from pathlib import Path
import requests
from datetime import datetime

class ReadabilityHUD:
    """
    ⚔️ Work Order D: Readability HUD (Imperial HUD)
    帝國 HUD：即時在終端顯示 Score 指標與 Ambiguity 熱圖。
    """
    
    # 帝國色系 (ANSI Colors)
    GOLD = "\033[38;2;255;215;0m"
    CRIMSON = "\033[38;2;220;20;60m"
    GREEN = "\033[38;2;50;205;50m"
    CYAN = "\033[38;2;0;255;255m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def __init__(self, audit_report: Dict[str, Any]):
        self.report = audit_report

    def display(self):
        """
        繪製終端 HUD。
        """
        score = self.report.get("readability_score", 0)
        jargon = self.report.get("jargon_list", [])
        unmapped = self.report.get("unmapped_fields", [])
        
        # 1. 標題與 Score (帝國徽章風格)
        print(f"\n{self.GOLD}{self.BOLD}=== ⚔️ NEXUS IMPERIAL HUD: READABILITY AUDIT ==={self.RESET}")
        
        color = self.GREEN if score >= 95 else (self.GOLD if score >= 80 else self.CRIMSON)
        bar_len = int(score / 5)
        bar = ("█" * bar_len).ljust(20, "░")
        
        print(f"{self.BOLD}Score: {color}{score:3}/100{self.RESET} [{color}{bar}{self.RESET}]")
        
        # 2. Ambiguity Heatmap (熱圖分析)
        print(f"\n{self.CYAN}📡 AMBIGUITY HEATMAP:{self.RESET}")
        
        if not jargon and not unmapped:
            print(f" {self.GREEN}● Crystal Clear (0 Ambiguity Detected){self.RESET}")
        else:
            if jargon:
                print(f" {self.CRIMSON}⚡ Jargon Peak:{self.RESET} {', '.join(jargon)}")
            if unmapped:
                print(f" {self.GOLD}⚠️ Shadow Fields:{self.RESET} {', '.join(unmapped)}")
        
        # 3. 系統決定 (Decision)
        status = self.report.get("status", "FAIL")
        highlight = self.GREEN if status == "PASS" else self.CRIMSON
        print(f"\n{self.BOLD}PROMOTION STATUS: {highlight}{status}{self.RESET}")
        
        if score > 95 and not jargon:
            print(f"{self.GOLD}⚓ HIGH-QUALITY PACK DETECTED. AUTO-TAGGING ARMED.{self.RESET}")
            
        print(f"{self.GOLD}{self.BOLD}================================================{self.RESET}\n")

    def sync_to_cockpit(self, project_root: Path):
        """
        將稽核熱圖物理同步至 Nexus Desk Cockpit。
        """
        # 1. 讀取配置
        config_path = project_root / ".nexus" / "config" / "hud_endpoint"
        endpoint = "http://localhost:8080/imperial-hud"
        if config_path.exists():
            endpoint = config_path.read_text().strip()
            
        # 2. 封裝 Payload (帝國標格)
        payload = {
            "score": self.report.get("readability_score", 0),
            "issues": self.report.get("unmapped_fields", []) + self.report.get("jargon_list", []),
            "proxies": self.report.get("source_of_truth_map", {}),
            "status": self.report.get("status", "FAIL"),
            "timestamp": datetime.now().isoformat()
        }
        
        # 3. 物理傳輸
        print(f"📡 [HUD:Sync] Syncing to Cockpit at {endpoint}...")
        try:
            response = requests.post(endpoint, json=payload, timeout=2)
            if response.status_code == 200:
                print(f"🟢 [HUD:Sync] 200 OK. Cockpit Updated.")
            else:
                print(f"⚠️ [HUD:Sync] Failed: {response.status_code}")
        except Exception as e:
            print(f"❌ [HUD:Sync] Connection Error: {e}")

if __name__ == "__main__":
    # 測試
    mock_report = {
        "readability_score": 98,
        "jargon_count": 0,
        "jargon_list": [],
        "unmapped_fields": ["User.age_raw"],
        "status": "PASS"
    }
    hud = ReadabilityHUD(mock_report)
    hud.display()
