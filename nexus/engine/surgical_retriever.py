import subprocess
from pathlib import Path
class SurgicalRetriever:
    def __init__(self, project_root): self.root = Path(project_root)
    def find_definition(self, sym):
        # 排除目錄
        exclude = ["--glob", "!venv*", "--glob", "!.nexus*", "--glob", "!.git*"]
        try:
            # 1. 嘗試精準定義匹配
            cmd = ["rg", "-l"] + exclude + [f"\\b(def|class)\\s+{sym}\\b", str(self.root)]
            res = subprocess.run(cmd, capture_output=True, text=True)
            paths = [Path(p) for p in res.stdout.splitlines() if p.strip()]
            if paths: return paths
            
            # 2. 嘗試全文本匹配
            cmd = ["rg", "-l"] + exclude + [f"\\b{sym}\\b", str(self.root)]
            res = subprocess.run(cmd, capture_output=True, text=True)
            return [Path(p) for p in res.stdout.splitlines() if p.strip()]
        except:
            # Fallback to simple grep if rg missing
            return []
