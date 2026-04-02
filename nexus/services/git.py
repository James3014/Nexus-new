from pathlib import Path
import subprocess
import os


class GitManager:
    """負責 Git 倉儲的操作與變更偵測。"""

    def __init__(self, project_root=None):
        self.project_root = project_root or self._get_project_root()
        self.git_dir = self._get_git_dir()

    def _get_project_root(self):
        """獲取 Git 倉庫根目錄 (支援 Worktree)。"""
        try:
            return (
                subprocess.check_output(["git", "rev-parse", "--show-toplevel"])
                .decode()
                .strip()
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return os.getcwd()

    def _get_git_dir(self):
        """獲取 Git 內部目錄 (支援絕對路徑，Git 2.13+)。"""
        try:
            return (
                subprocess.check_output(["git", "rev-parse", "--absolute-git-dir"])
                .decode()
                .strip()
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def get_changes(self, scope="staged", base_ref="HEAD"):
        """
        獲取代碼變更。
        - scope: 'staged', 'unstaged', 'base', 'all'
        """

        def _git_run(args):
            # 強制在專案根目錄執行，確保路徑解析一致
            cmd = ["git", "-C", self.project_root] + args
            return subprocess.check_output(cmd).decode().strip()

        try:
            # 1. 檔案過濾與列表獲取
            if scope == "staged":
                files_out = _git_run(
                    ["diff", "--cached", "--name-only", "--diff-filter=d"]
                )
                diff_text = _git_run(["diff", "--cached"])
            elif scope == "unstaged":
                files_out = _git_run(["diff", "--name-only", "--diff-filter=d"])
                diff_text = _git_run(["diff"])
            elif scope == "base":
                files_out = _git_run(
                    ["diff", base_ref, "--name-only", "--diff-filter=d"]
                )
                diff_text = _git_run(["diff", base_ref])
            else:  # all (追蹤中變動 + 未追蹤)
                # 'all' 模式的 diff 需要手動處理未追蹤檔案
                diff_text = _git_run(["diff", "HEAD"])
                untracked_files = _git_run(
                    ["ls-files", "--others", "--exclude-standard"]
                ).splitlines()
                for uf in untracked_files:
                    full_path = Path(self.project_root) / uf
                    if uf.endswith(".py") and full_path.is_file():
                        try:
                            lines = full_path.read_text(encoding="utf-8").splitlines()
                            header = f"\ndiff --git a/{uf} b/{uf}\nnew file mode 100644\n--- /dev/null\n+++ b/{uf}\n@@ -0,0 +1,{len(lines)} @@\n"
                            diff_text += (
                                header
                                + "\n".join([f"+{line}" for line in lines])
                                + ("\n" if lines else "")
                            )
                        except (UnicodeDecodeError, IOError):
                            pass

                all_files_out = _git_run(
                    ["ls-files", "--modified", "--others", "--exclude-standard"]
                )
                code_files = [
                    f
                    for f in all_files_out.splitlines()
                    if (Path(self.project_root) / f).is_file()
                ]
                return code_files, diff_text

            files = files_out.splitlines()
            return files, diff_text

        except subprocess.CalledProcessError as e:
            print(f"❌ Git Error: {e}")
            return [], ""
