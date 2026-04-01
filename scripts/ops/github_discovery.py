import os
import subprocess
import logging
from typing import List

logger = logging.getLogger(__name__)

class GitHubDiscovery:
    """
    🔍 Nexus GitHub 專案發現器
    負責自動檢索本地 Workspace 中具備 GitHub 遠端的 Git 倉庫。
    """
    
    def __init__(self, workspace_root: str = "/Users/jameschen/Workspace"):
        self.root = workspace_root

    def find_github_projects(self) -> List[str]:
        """🎯 物理檢索 GitHub 專案路徑"""
        projects = []
        logger.info(f"🔍 [Discovery] Scanning {self.root} for GitHub projects...")
        
        try:
            # 遍歷一級子目錄
            for item in os.listdir(self.root):
                full_path = os.path.join(self.root, item)
                if os.path.isdir(full_path) and os.path.exists(os.path.join(full_path, ".git")):
                    # 核驗 git remote
                    if self._is_github_repo(full_path):
                        projects.append(full_path)
        except Exception as e:
            logger.error(f"❌ [Discovery:Error] {e}")
            
        return projects

    def _is_github_repo(self, path: str) -> bool:
        """🎯 核驗是否具備 github.com 遠端真值"""
        try:
            res = subprocess.run(
                ["git", "-C", path, "remote", "-v"],
                capture_output=True, text=True
            )
            return "github.com" in res.stdout
        except:
            return False

if __name__ == "__main__":
    discovery = GitHubDiscovery()
    projects = discovery.find_github_projects()
    print("\n🚀 [Discovery:Complete] Found GitHub Projects:")
    for p in projects:
        print(f"  -> {p}")
