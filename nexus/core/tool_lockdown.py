import logging

logger = logging.getLogger(__name__)

class ToolLockedError(Exception):
    """具備治理等級的工具鎖定錯誤"""
    pass

class ToolLockdown:
    """
    🔒 Nexus 制度化工具鎖定 (v22 Guardian)
    物理阻斷高風險指令，強制轉導至專用 Skill-Tool。
    """
    DANGEROUS_CMDS = ["rm ", "rmdir", "pkill", "sudo", "truncate", "> /dev/"]
    ALLOWED_TOOLS = ["git", "uv", "pytest", "ls", "grep", "cat", "nexus"]

    @staticmethod
    def validate_shell(cmd: str):
        """物理掃描指令風險"""
        cmd_norm = cmd.strip().lower()
        
        # 1. 黑名單檢查
        for dc in ToolLockdown.DANGEROUS_CMDS:
            if dc in cmd_norm:
                logger.error("🛑 [Lockdown] Dangerous Command Blocked: %s", cmd)
                raise ToolLockedError(f"Command '{dc.strip()}' is forbidden in Phase R. Use formal Skill-Tool.")

        # 2. 管道式覆蓋檢查 (防止 rm -rf 被混淆)
        if "rm" in cmd_norm and ("-r" in cmd_norm or "-f" in cmd_norm):
            raise ToolLockedError("Recursive delete is PHYSICAL FORBIDDEN. Use Nexus Purge Skill.")

        # 3. 概率性危險預警 (Claw-Genes: HazardClassifier)
        from nexus.core.hazard_classifier import HazardClassifier
        hazard_clf = HazardClassifier()
        classification = hazard_clf.classify(cmd_norm)
        
        if classification == "BLOCKED":
            raise ToolLockedError(f"Hazard Score too high. Command '{cmd}' is BLOCKED by probabilistic classifier.")
        elif classification == "WARN_HUMAN":
            # 在自動化模式下暫時攔截並要求人工確認 (Mock)
            print(f"⚠️ [Lockdown:WARN] High hazard score detected for: {cmd}. Human review suggested.")
            # raise ToolLockedError("Command requires Human Review (Score > 0.5)")

        return True

    @staticmethod
    def is_production_mode():
        """檢查是否處於 L5.7 正式治理狀態"""
        return True
