from typing import Any, Dict, List, Optional, Set, Tuple
import ast
import os
from dataclasses import dataclass, field

@dataclass
class XRayResult:
    symbols: List[str] = field(default_factory=list)
    crossings: List[Dict[str, str]] = field(default_factory=list) # source -> target
    risks: List[str] = field(default_factory=list)
    summary: str = ""

class XRayObserver:
    """
    👁️ v23 X-Ray Observer (POC)
    功能：靜態掃描 Python 檔案依賴關係，生成多維觀測圖。
    限制：當前版本僅限於單一目錄靜態分析。
    """
    
    def __init__(self, target_dirs: List[str]):
        self.target_dirs = target_dirs
        self.results = XRayResult()

    def scan(self, recursive: bool = True) -> XRayResult:
        """執行全域/多目錄靜態掃描 (v23 Cross-Repo Hardened)"""
        for target in self.target_dirs:
            target_path = os.path.abspath(os.path.expanduser(target))
            if not os.path.exists(target_path):
                continue
            
            # 使用目錄名稱作為 Repo 前綴
            repo_id = os.path.basename(target_path) if os.path.isdir(target_path) else "standalone"
            
            if os.path.isfile(target_path):
                self._analyze_file(repo_id, os.path.basename(target_path), target_path)
            else:
                self._scan_dir(repo_id, target_path, recursive)
                
        self.results.summary = f"v23 X-Ray Cross-Repo Scan complete. Symbols: {len(self.results.symbols)} | Crossings: {len(self.results.crossings)}"
        return self.results

    def _scan_dir(self, repo_id: str, directory: str, recursive: bool):
        """掃描目錄（支援多 Repo 名稱空間分離）"""
        for root, dirs, files in os.walk(directory):
            if any(p in root for p in ['__pycache__', 'node_modules', '.git', '.venv']):
                continue
                
            for filename in files:
                if filename.endswith('.py') or 'Dockerfile' in filename:
                    file_path = os.path.join(root, filename)
                    rel_name = os.path.relpath(file_path, directory)
                    # 注入 Repo 識別碼
                    self._analyze_file(repo_id, rel_name, file_path)
            
            if not recursive:
                break

    def _analyze_file(self, repo_id: str, filename: str, path: str):
        """分析單一檔案內容（支援 Repo Prefix）"""
        try:
            if os.path.getsize(path) > 1024 * 1024:
                return

            # 通用的 Source 識別格式: repo::filename
            source_id = f"{repo_id}::{filename}"

            if filename.endswith('.py'):
                with open(path, 'r', encoding='utf-8') as f:
                    tree = ast.parse(f.read())
                self._analyze_python_tree(source_id, tree)
            elif 'Dockerfile' in filename:
                self._analyze_dockerfile(source_id, path)
        except Exception as e:
            self.results.risks.append(f"{repo_id}::{filename}: Scan failed: {str(e)}")

    def _analyze_python_tree(self, source_id: str, tree: ast.AST):
        """解析 Python AST 樹中的符號與跨域導入"""
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                self._process_import(source_id, node)
            
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr in ['run', 'Popen', 'call']:
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == 'subprocess':
                        self.results.risks.append(f"{source_id}: Potential subprocess execution detected.")
                        
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                self.results.symbols.append(f"{source_id}::{node.name}")

    def _analyze_dockerfile(self, source_id: str, path: str):
        """解析 Dockerfile"""
        try:
            with open(path, 'r') as f:
                lines = f.readlines()
            for line in lines:
                if line.startswith('FROM'):
                    base_image = line.split()[1]
                    self.results.crossings.append({"source": source_id, "target": f"docker://{base_image}"})
        except Exception as e:
            self.results.risks.append(f"{source_id}: Scan failed: {str(e)}")

    def _process_import(self, source: str, node: Any):
        if isinstance(node, ast.Import):
            for alias in node.names:
                self.results.crossings.append({"source": source, "target": alias.name})
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            self.results.crossings.append({"source": source, "target": module})

if __name__ == "__main__":
    # POC 自我測試
    observer = XRayObserver("nexus/core")
    report = observer.scan()
    print(f"Symbols: {len(report.symbols)}")
    print(f"Crossings: {len(report.crossings)}")
    print(report.summary)
