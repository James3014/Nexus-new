from typing import Dict, List, Any
import re

class TaskPredictor:
    """
    🔮 Nexus 任務預測器 (TaskPredictor)
    職責: 分析任務特徵、語言需求與環境複雜度，為調度器提供特徵矩陣。
    """
    
    LANG_MAP = {
        "python": [".py", "python", "pip", "uv", "django", "flask"],
        "rust": [".rs", "rust", "cargo", "tonic", "reflex"],
        "go": [".go", "golang", "go mod", "gin", "swarm"],
        "js": [".js", "javascript", "node", "npm", "nextjs", "react"],
        "shell": [".sh", "bash", "zsh", "scripts"]
    }

    def analyze(self, task: str, codebase: str = "") -> Dict[str, Any]:
        """
        🧬 語義分析。
        提取任務特徵: 語言 (lang), 複雜度 (complexity: 1-10), 延遲需求 (lat_req: urgent/standard)。
        """
        task_lower = task.lower()
        
        # 1. 語言檢測
        lang = "unknown"
        for l, keywords in self.LANG_MAP.items():
            if any(kw in task_lower for kw in keywords):
                lang = l
                break
        
        # 2. 複雜度估算 (Heuristic)
        complexity = 3 # Default
        if any(kw in task_lower for kw in ["refactor", "architect", "overhaul", "migrate", "swarm"]):
            complexity = 8
        elif any(kw in task_lower for kw in ["fix", "bug", "tweak", "align"]):
            complexity = 5
        elif any(kw in task_lower for kw in ["read", "check", "verify"]):
            complexity = 2
            
        # 3. 延遲需求
        lat_req = "standard"
        if any(kw in task_lower for kw in ["urgent", "hotfix", "immediate", "prod", "now"]):
            lat_req = "urgent"

        return {
            "lang": lang.capitalize(),
            "complexity": complexity,
            "lat_req": lat_req,
            "raw_task_len": len(task)
        }
