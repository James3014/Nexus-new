import ast
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class SliceResult:
    code_content: str
    dependencies: List[str]
    token_estimate: int

class SurgicalSlicer:
    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)
        self.source = self.file_path.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def slice_function(self, target_name: str, max_depth: int = 5) -> SliceResult:
        collected = {}
        target = self._find(target_name)
        if target: self._collect(target, collected, 0, max_depth)
        imps = [ast.unparse(n) for n in self.tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        code = "\n".join(imps) + "\n\n# Slice\n" + "\n\n".join([ast.unparse(n) for n in collected.values()])
        return SliceResult(code, list(collected.keys()), len(code)//4)

    def _find(self, name):
        for n in ast.walk(self.tree):
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name: return n
        return None

    def _collect(self, node, coll, d, m):
        if not node or d > m or getattr(node, "name", "") in coll: return
        coll[getattr(node, "name", "")] = node
        for c in ast.walk(node):
            if isinstance(c, ast.Name) and isinstance(c.ctx, ast.Load):
                dep = self._find(c.id)
                if dep: self._collect(dep, coll, d+1, m)
