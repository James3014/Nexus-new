import os
import time
import ast
from pathlib import Path

def test_ast():
    repo_dir = Path("/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy")
    py_files = list(repo_dir.rglob("*.py"))
    print(f"Total py files: {len(py_files)}")
    
    start = time.time()
    count = 0
    for pyfile in py_files:
        rel_path = str(pyfile.relative_to(repo_dir))
        if any(p in rel_path.lower() for p in ("test", "__pycache__", ".tox", "build", "dist", "cextern", "docs")):
            continue
        count += 1
        try:
            content = pyfile.read_text(encoding="utf-8", errors="replace")
            # Simulate localizer reading first 8k or whole content
            # Localizer reads whole content for _symbol_score
            tree = ast.parse(content)
            defined_names = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    defined_names.add(node.name)
        except Exception as e:
            pass
            
    print(f"Parsed {count} files in {time.time() - start:.2f} seconds")

if __name__ == "__main__":
    test_ast()
