import ast
import textwrap
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Set, Any

from nexus.engine.value_flow_scorer import ValueFlowScorer

@dataclass
class SliceResult:
    code_content: str
    dependencies: List[str]
    token_estimate: int
    scores: Dict[str, float] = None # type: ignore
    shadow_rank: List[str] = None # type: ignore
    start_line: int = 0
    end_line: int = 0

class SurgicalSlicer:
    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)
        self.source = self.file_path.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def slice_function(self, target_name: str, max_depth: int = 5, criteria: Set[str] = None) -> SliceResult:
        collected = {}
        target = self._find(target_name)
        
        start_line = 0
        end_line = 0
        if target:
            start_line = target.lineno if hasattr(target, "lineno") else 0
            end_line = target.end_lineno if hasattr(target, "end_lineno") else 0
            self._collect(target, collected, 0, max_depth)
        
        # --- Value-Flow Reranking (Shadow Mode) ---
        scorer = ValueFlowScorer(criteria or {target_name})
        node_scores = {}
        for name, node in collected.items():
            reasons = []
            node_scores[name] = scorer.score_node(node, reasons)
            
        # 排序節點：分數高者優先
        sorted_names = sorted(collected.keys(), key=lambda n: node_scores[n], reverse=True)
        
        imps = [ast.unparse(n) for n in self.tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        
        # 組合代碼 (依據排名)
        code_parts = ["\n".join(imps), "\n# --- Value-Flow Sorted Slice ---"]
        for name in sorted_names:
            code_parts.append(f"# Score: {node_scores[name]} | Symbol: {name}")
            code_parts.append(ast.unparse(collected[name]))
            
        code = "\n\n".join(code_parts)
        return SliceResult(
            code_content=code,
            dependencies=list(collected.keys()),
            token_estimate=len(code)//4,
            scores=node_scores,
            shadow_rank=sorted_names,
            start_line=start_line,
            end_line=end_line
        )

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
