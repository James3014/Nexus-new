import re
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class InkCommand:
    type: str
    target: str
    params: Dict[str, str]

class InkParser:
    """
    🎨 Nexus Ink 語言解析器 (AOS-P5.10)
    負責解析緊湊化的專屬指令集，實現 Token 極低消耗的 Agent 通訊。
    """
    
    # 模式: ink-<cmd><target><param1><param2>...
    INK_PATTERN = r"ink-([a-z]+)<([^>]+)>(?:<([^>]+)>)*"

    def parse(self, content: str) -> List[InkCommand]:
        """🎯 解析文本中的 Ink 指令序列"""
        commands = []
        lines = content.split("\n")
        
        for line in lines:
            line = line.strip()
            if not line.startswith("ink-"): continue
            
            # 使用 Regex 提取各個區塊
            match = re.match(r"ink-([a-z0-9\-]+)<([^>]+)>(.*)", line)
            if match:
                cmd_type = match.group(1)
                target = match.group(2)
                raw_params = match.group(3)
                
                # 提取剩餘參數
                params_list = re.findall(r"<([^>]+)>", raw_params)
                params_dict = {f"p{i}": p for i, p in enumerate(params_list)}
                
                commands.append(InkCommand(
                    type=cmd_type,
                    target=target,
                    params=params_dict
                ))
                logger.info(f"🎨 [Ink:Parsed] {cmd_type} for {target}")
                
        return commands

    def to_formal(self, ink: InkCommand) -> Dict[str, Any]:
        """⚖️ 將 Ink 指令映射回正式模式 (v7 Formal Spec)"""
        mapping = {
            "read": {"tool": "read_file", "args": {"path": ink.target}},
            "edit": {"tool": "edit_file", "args": {"path": ink.target, "search": ink.params.get("p0"), "replace": ink.params.get("p1")}},
            "test": {"tool": "run_test", "args": {"path": ink.target}},
            "patch": {"tool": "safe_patch", "args": {"file": ink.target, "diff": ink.params.get("p0")}}
        }
        return mapping.get(ink.type, {"tool": "unknown", "args": {}})
    
    def compress(self, tool_call: Dict[str, Any]) -> str:
        """📦 將正式指令壓縮為 Ink 語法"""
        tool = tool_call.get("tool")
        args = tool_call.get("args", {})
        
        if tool == "read_file":
            return f"ink-read<{args['path']}>"
        elif tool == "edit_file":
            return f"ink-edit<{args['path']}><{args['search']}><{args['replace']}>"
            
        return f"ink-raw<{tool}>"
