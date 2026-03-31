import logging
import shutil

logger = logging.getLogger(__name__)

class SpeculativeToolHook:
    """
    🧬 Nexus 投機指令改寫器 (v22 Speculative)
    自動將 Agent 生成的慢速/冗餘指令改寫為高效替代品，壓縮 Context 噪音。
    """
    # 物理映射字典：Legacy -> Modern
    CMD_UPGRADES = {
        "grep": "rg --ignore-file .gitignore",
        "find": "fd --hidden",
        "cat":  "bat --style=plain --paging=never",
        "ls":   "eza --tree --level=2"
    }

    def rewrite(self, cmd_str: str) -> str:
        """實施指令物理重寫與躍遷"""
        # 僅在指令開頭匹配以防誤傷參數
        parts = cmd_str.strip().split(maxsplit=1)
        if not parts:
            return cmd_str
            
        base_cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        if base_cmd in self.CMD_UPGRADES:
            modern_cmd = self.CMD_UPGRADES[base_cmd]
            
            # 驗證現代工具是否存在於環境中
            modern_base = modern_cmd.split()[0]
            if shutil.which(modern_base):
                logger.info("⚡ [Speculative] Rewriting: %s -> %s", base_cmd, modern_base)
                # 組合新指令
                return f"{modern_cmd} {args}".strip()
            else:
                logger.debug("⚪ [Speculative] Modern tool '%s' not found. Falling back to legacy.", modern_base)
        
        return cmd_str
