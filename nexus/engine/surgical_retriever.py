import subprocess
from pathlib import Path
class SurgicalRetriever:
    def __init__(self, project_root): self.root = Path(project_root)
    def find_definition(self, sym):
        try:
            res = subprocess.run(["rg", "-l", f"\\b(def|class)\\s+{sym}\\b", str(self.root)], capture_output=True, text=True)
            return [Path(p) for p in res.stdout.splitlines() if p.strip()]
        except:
            res = subprocess.run(["grep", "-rl", f"\\b(def|class)\\s\\+{sym}\\b", str(self.root)], capture_output=True, text=True)
            return [Path(p) for p in res.stdout.splitlines() if p.strip()]
