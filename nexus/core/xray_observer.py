import ast
import os
from typing import Dict, List, Any, Set
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
        """執行全域/多目錄靜態掃描"""
        for target in self.target_dirs:
            target_path = os.path.expanduser(target)
            if not os.path.exists(target_path):
                continue
            
            if os.path.isfile(target_path):
                self._analyze_file(os.path.basename(target_path), target_path)
            else:
                self._scan_dir(target_path, recursive)
                
        self.results.summary = f"v23 X-Ray Full Scan complete. Symbols: {len(self.results.symbols)} | Crossings: {len(self.results.crossings)}"
        return self.results

    def _scan_dir(self, directory: str, recursive: bool):
        """掃描目錄（支援遞歸與負載控制）"""
        for root, dirs, files in os.walk(directory):
            # 排除大型非代碼目錄以加速
            if any(p in root for p in ['__pycache__', 'node_modules', '.git', '.venv']):
                continue
                
            for filename in files:
                if filename.endswith('.py'):
                    file_path = os.path.join(root, filename)
                    # 拓撲壓縮：僅記錄相對路徑作為 Source
                    rel_name = os.path.relpath(file_path, directory)
                    self._analyze_file(rel_name, file_path)
            
            if not recursive:
                break

    def _analyze_file(self, filename: str, path: str):
        """分析單一檔案內容（支援 Python 與 Dockerfile）"""
        try:
            # 負載控制：忽略大於 1MB 的單體檔案
            if os.path.getsize(path) > 1024 * 1024:
                return

            if filename.endswith('.py'):
                with open(path, 'r', encoding='utf-8') as f:
                    tree = ast.parse(f.read())
                self._analyze_python_tree(filename, tree)
            elif 'Dockerfile' in filename:
                self._analyze_dockerfile(filename, path)
        except Exception as e:
            self.results.risks.append(f"{filename}: Scan failed: {str(e)}")

    def _analyze_python_tree(self, filename: str, tree: ast.AST):
        """解析 Python AST 樹中的符號與導入"""
        for node in ast.walk(tree):
            # 1. 偵測 Import (Crossings)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                self._process_import(filename, node)
            
            # 2. 偵測 Subprocess (Risks)
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr in ['run', 'Popen', 'call']:
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == 'subprocess':
                        self.results.risks.append(f"{filename}: Potential subprocess execution detected.")
                        
            # 3. 偵測 Class/Func (Symbols)
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                self.results.symbols.append(f"{filename}::{node.name}")

    def _analyze_dockerfile(self, filename: str, path: str):
        """解析 Dockerfile 中的 Base Image 與安裝依賴"""
        try:
            with open(path, 'r') as f:
                lines = f.readlines()
            for line in lines:
                if line.startswith('FROM'):
                    base_image = line.split()[1]
                    self.results.crossings.append({"source": filename, "target": f"docker://{base_image}"})
                if 'apt-get install' in line or 'pip install' in line:
                    self.results.risks.append(f"{filename}: Network-active installation detected.")
        except Exception as e:
            self.results.risks.append(f"{filename}: Scan failed: {str(e)}")

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
