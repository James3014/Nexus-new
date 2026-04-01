import ast
import re
from pathlib import Path
from typing import List, Dict, Any

class CritiqueEngine:
    """🕵️ Nexus L6.1 毒舌審核引擎 (The Critique Sub-agent)
    
    執行 AST 靜態分析與平庸度 (Slop Density) 偵測。
    對照 .nexus-soul.md 標準：Slop < 1%, Naming Descriptive, Google Style.
    """

    SLOP_KEYWORDS = [
        "placeholder", "TODO", "generic_function", "temp_list", "data1", 
        "modern", "clean", "minimal", "sleek", "dynamic", "user_auth_handler",
        "boilerplate", "dummy", "implement_me", "logic_goes_here"
    ]

    def __init__(self, soul_path: Path):
        self.soul_path = soul_path

    def analyze_node_density(self, content: str) -> float:
        """偵測代碼實體與 Slop 的密度比"""
        words = content.split()
        slop_count = sum(1 for w in words if w.lower() in self.SLOP_KEYWORDS)
        return slop_count / len(words) if words else 0

    def critique_file(self, file_path: Path) -> Dict[str, Any]:
        with open(file_path, "r") as f:
            content = f.read()
        
        score = 100
        issues = []

        # 1. Slop Density Check (Hardened)
        density = self.analyze_node_density(content)
        if density > 0.01: # 容忍度 1%
            deduction = min(50, int(density * 1000))
            score -= deduction
            issues.append(f"❌ [Slop-Density] 平庸度過高 ({density:.2%})，攔截 (-{deduction})")

        # 2. AST Naming Audit (Strict)
        try:
            tree = ast.parse(content)
            long_names = 0
            total_vars = 0
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    total_vars += 1
                    if len(node.id) < 4 and node.id not in ["i", "j", "k", "f", "x", "e"]:
                        score -= 2
                        issues.append(f"❌ [Naming] '{node.id}' 長度低於 4 字，非規範命名")
                    elif len(node.id) >= 8:
                        long_names += 1
            
            # 核驗描述性豐富度
            if total_vars > 0 and (long_names / total_vars) < 0.2:
                score -= 10
                issues.append("❌ [Aesthetics] 變量命名描述性比率過低，需更換為具體描述性名詞 (-10)")
        except SyntaxError:
            score -= 50
            issues.append("❌ [Syntax] 代碼解析失敗")

        # 3. Google Style Docstring (Regex check)
        if ".py" in str(file_path):
            if not re.search(r'"""[\s\S]*?Args:[\s\S]*?Returns:[\s\S]*?"""', content):
                score -= 10
                issues.append("❌ [Style] Docstring 缺少 Args/Returns (Google Style) (-10)")

        return {
            "file": str(file_path),
            "critique_score": max(0, score),
            "status": "PASS" if score >= 90 else "FAIL",
            "issues": issues
        }

if __name__ == "__main__":
    # 簡單自測
    engine = CritiqueEngine(Path(".nexus-soul.md"))
    # 假設測試自己
    result = engine.critique_file(Path(__file__))
    print(f"🕵️ Critique Score: {result['critique_score']} | Status: {result['status']}")
    for issue in result['issues']:
        print(f"  -> {issue}")
