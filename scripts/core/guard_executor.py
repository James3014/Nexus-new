import sys
import subprocess
import random
import logging
import os
import math
from pathlib import Path
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

def preview_argv_for_rm(cmd: List[str]) -> List[str] | None:
    """Map an ``rm`` argv to a read-only ``ls`` argv, or None if it is not one."""
    if not cmd or os.path.basename(cmd[0]) != "rm":
        return None
    recursive = False
    operands: List[str] = []
    end_of_options = False
    for arg in cmd[1:]:
        if not end_of_options and arg == "--":
            end_of_options = True
        elif not end_of_options and arg.startswith("--"):
            recursive = recursive or arg == "--recursive"
        elif not end_of_options and arg.startswith("-") and arg != "-":
            recursive = recursive or "r" in arg[1:].lower()
        else:
            operands.append(arg)
    return ["ls", "-ld" if recursive else "-l", "--", *operands]


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
        # #2635 SEC-007: the preview runs before the human challenge, so it
        # must never go through a shell (a file name such as "x; evil" would
        # otherwise execute unconfirmed). Build an ls argv from the operands.
        preview_argv = preview_argv_for_rm(cmd)
        try:
            if preview_argv is None:
                raise ValueError("not a plain rm invocation")
            subprocess.run(preview_argv, check=False)
        except Exception:
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
    original_cmd_str = cmd_str
    rewritten = hook.rewrite(cmd_str)

    # 執行原始指令 (或重寫後的現代指令)。#2635 SEC-007: no shell. The
    # original argv keeps its quoting; a rewritten string is tokenized and run
    # without a shell (unsupported operators are refused).
    if rewritten == original_cmd_str:
        try:
            subprocess.run(list(cmd), check=True)
        except subprocess.CalledProcessError as e:
            sys.exit(e.returncode)
        except FileNotFoundError:
            sys.exit(127)
    else:
        repo_root = str(Path(__file__).resolve().parents[2])
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from nexus.core.argv_command import run_command_string

        result = run_command_string(rewritten, capture_output=False)
        if result.returncode != 0:
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            sys.exit(result.returncode)


if __name__ == "__main__":
    secure_execute()
