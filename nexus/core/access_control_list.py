from typing import Any, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class AccessControlList:
    """
    🔐 Nexus ACL (v25 Matrix)
    負責細粒度的工具與資產訪問控制，實現 L6.0 Eternal 級別的安全性。
    """
    
    def __init__(self):
        self.rules = {
            "root": ["*"],
            "agent": ["read_file", "search_web", "grep_search", "view_file"],
            "executor": ["write_to_file", "run_command", "replace_file_content"]
        }
        # 具現化：受保護的敏感資源真值
        self.protected_ports = [8000, 5000, 5432, 27017]
        self.forbidden_commands = [r"kill\s+-9", r"rm\s+-rf\s+/"]

    def check_system_integrity(self, cmd: str) -> bool:
        """🎯 核驗指令是否觸發系統誠信保護 (Anti-Sloppy)"""
        import re
        cmd_norm = cmd.lower()
        for pattern in self.forbidden_commands:
            if re.search(pattern, cmd_norm):
                logger.error(f"🚫 [ACL:Integrity] Forbidden destructive command: {cmd}")
                return False
        return True

    def check_permission(self, role: str, tool: str, cmd: Optional[str] = None) -> bool:
        """🎯 核驗物理訪問權限與指令誠信"""
        if tool == "run_command" and cmd:
            if not self.check_system_integrity(cmd):
                return False

        allowed = self.rules.get(role, [])
        if "*" in allowed or tool in allowed:
            logger.info(f"✅ [ACL:Pass] Role '{role}' authorized for tool '{tool}'.")
            return True
        logger.warning(f"🚫 [ACL:Denied] Role '{role}' restricted from tool '{tool}'.")
        return False

    def add_rule(self, role: str, tool: str):
        """🎯 動態注入權限規則"""
        if role not in self.rules:
            self.rules[role] = []
        if tool not in self.rules[role]:
            self.rules[role].append(tool)
            logger.info(f"➕ [ACL:Update] Added tool '{tool}' to role '{role}'.")
