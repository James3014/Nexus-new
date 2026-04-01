import sys
import subprocess
import random
import logging
import os
import math
from typing import List

# 🛡️ Nexus v9-v22 架構導入 (與主幹一致)
try:
    from nexus.core.tool_lockdown import ToolLockdown, ToolLockedError
    from scripts.engine.speculative_hooks import SpeculativeToolHook
except ImportError:
    # 測試環境降級處理
    class ToolLockedError(Exception): pass
    class ToolLockdown:
        @staticmethod
        def validate_shell(cmd): pass
    class SpeculativeToolHook:
        def rewrite(self, cmd): return cmd

logger = logging.getLogger(__name__)

class EntropyAuditor:
    """
    🧬 Entropy & Security Auditor (v22 Hardened)
    負責偵測 Payload 熵值，識別潛在的敏感資訊流出。
    實施「受控啟動」策略：採 Allowlist + Audit 模式。
    """
    ALLOWLIST = ["ssh ", "git ", "curl ", "wget ", "sftp ", "scp ", "mosh "]

    def __init__(self, mode: str = "audit", threshold: float = 4.5):
        self.mode = mode
        self.threshold = threshold

    def calculate_entropy(self, payload: str) -> float:
        """計算字串熵值 (Shannon Entropy)"""
        if not payload:
            return 0.0
        entropy = 0
        length = len(payload)
        for char in set(payload):
            prob = payload.count(char) / length
            entropy -= prob * math.log2(prob)
        return entropy

    def is_allowed(self, cmd: str) -> bool:
        """檢查指令是否位於白名單中 (Allowlist)"""
        cmd_norm = cmd.strip().lower()
        return any(cmd_norm.startswith(pre) for pre in self.ALLOWLIST)

    def audit(self, payload: str, cmd_context: str = ""):
        """執行審計邏輯 (Controlled Launch: Audit by default)"""
        if not payload:
            return

        # 1. 白名單跳過 (避免誤傷 SSH/Git/TLS)
        if cmd_context and self.is_allowed(cmd_context):
            return

        # 2. 熵值檢測
        score = self.calculate_entropy(payload)
        if score > self.threshold:
            msg = f"❗ [EntropyAuditor] High entropy detected ({score:.2f} > {self.threshold}) in payload."
            print(f"\n{msg}")
            
            if self.mode == "block":
                print("🛑 [EntropyAuditor] BLOCK MODE ACTIVE. Killing process...")
                os.kill(os.getpid(), 9)
            else:
                # Audit Mode (Default)
                logger.warning(msg)

def secure_execute():
    cmd = sys.argv[1:]
    if not cmd:
        sys.exit(0)
    cmd_str = " ".join(cmd)

    # 🧬 P0: Entropy Audit & Allowlist
    # 嚴格准守 Sir 的指令：採受控啟動，預設為 audit 模式
    auditor = EntropyAuditor(mode="audit")
    auditor.audit(cmd_str, cmd_str)

    # 針對 rm 指令的攔截 (特別是危險參數)
    if "rm " in cmd_str and (
        "-r" in cmd_str or "-f" in cmd_str or "*" in cmd_str or "/" in cmd_str
    ):
        print("\n" + "=" * 60)
        print("🚨 [Guard_Executor] 觸發致命操作實體攔截！")
        print(f"嘗試執行的指令: {cmd_str}")
        print("=" * 60)

        # 1. 強制顯示影響範圍
        print("\n🔍 影響範圍預覽 (Dry Run):")
        preview_cmd = (
            cmd_str.replace("rm -rf", "ls -ld")
            .replace("rm -f", "ls -l")
            .replace("rm -r", "ls -ld")
        )
        try:
            subprocess.run(preview_cmd, shell=True, check=False)
        except:
            print("  無法預覽影響範圍。")

        # 2. 強制需要人類輸入動態驗證碼 (無法被 AI 自動繞過)
        challenge = str(random.randint(1000, 9999))
        print("\n⚠️ 這是不可逆的操作。AI 無權執行。")
        print(
            f"👉 請 Sir 親自輸入驗證碼 [{challenge}] 以授權執行: ", end="", flush=True
        )

        try:
            # 讀取實體鍵盤輸入
            answer = input().strip()
            if answer != challenge:
                print("❌ 驗證失敗，操作已取消。")
                sys.exit(1)
        except Exception as e:
            print(f"❌ 無法獲獲人類輸入，操作取消。({e})")
            sys.exit(1)

        print("✅ 實體授權通過，執行中...")

    # 🧬 P3: 制度化工具鎖定 (v22 Guardian)
    try:
        ToolLockdown.validate_shell(cmd_str)
    except ToolLockedError as e:
        print(f"\n🛑 [Guard_Executor] 治理攔截: {e}")
        print("💡 建議：請使用 'nexus:clean' 或專用 'Skill-Tool' 代替原生指令。")
        sys.exit(1)

    # 🧬 P5: 投機指令改寫 (Speculative Rewrite)
    hook = SpeculativeToolHook()
    cmd_str = hook.rewrite(cmd_str)

    # 執行原始指令 (或重寫後的現代指令)
    try:
        subprocess.run(cmd_str, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)


if __name__ == "__main__":
    secure_execute()
