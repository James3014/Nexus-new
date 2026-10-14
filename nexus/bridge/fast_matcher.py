import fnmatch
import os
from pathlib import Path
from typing import List


class FastMatcherBridge:
    """Project file scanner (pure Python).

    The Rust ``nexus_core`` shadow path was retired with the extension (#1927).
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def py_scan(self, root: str, patterns: List[str]) -> List[str]:
        """與 Rust 等價的 Python 實作 (用於比對)"""
        results = []

        # 讀取 .gitignore 中被忽略的樣式
        ignore_patterns = []
        gitignore_path = os.path.join(root, ".gitignore")
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        ignore_patterns.append(line)

        for root_dir, dirs, files in os.walk(root):
            # 1. inplace 過濾目錄以避免 os.walk 遍歷它們
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".")
                and d not in ["__pycache__", "node_modules", "target", "scratch", "perplexity"]
                and not any(ip.strip("/") == d for ip in ignore_patterns if ip.endswith("/"))
            ]

            for filename in files:
                # 2. 過濾隱藏檔案
                if filename.startswith("."):
                    continue

                full_path = os.path.join(root_dir, filename)
                rel_path = os.path.relpath(full_path, root)

                # 3. 過濾路徑組件中包含被忽略目錄的項目
                parts = Path(rel_path).parts
                if any(
                    p.startswith(".") or p in ["target", "scratch", "perplexity"] for p in parts
                ):
                    continue

                # 4. 過濾符合 .gitignore 的檔案和通配符
                is_ignored = False
                for ip in ignore_patterns:
                    if ip.endswith("/"):
                        clean_ip = ip.strip("/")
                        if rel_path.startswith(clean_ip) or f"/{clean_ip}/" in rel_path:
                            is_ignored = True
                            break
                    else:
                        if fnmatch.fnmatch(rel_path, ip) or fnmatch.fnmatch(filename, ip):
                            is_ignored = True
                            break
                if is_ignored:
                    continue

                if not patterns:
                    results.append(rel_path)
                else:
                    if any(fnmatch.fnmatch(rel_path, p) for p in patterns):
                        results.append(rel_path)
        return sorted(results)

    def scan(self, patterns: List[str]) -> List[str]:
        """Scan the project root and return sorted relative paths matching patterns."""
        return self.py_scan(str(self.project_root.absolute()), patterns)
