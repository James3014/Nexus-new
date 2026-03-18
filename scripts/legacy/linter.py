"""
⚠️ LEGACY / ARCHIVED SCRIPT
This script is part of the legacy Muse-Nexus implementation and is no longer actively maintained.
Please use the corresponding module in `scripts/core/` or `nexus/` instead.
---
⚠️ 舊版 / 封存腳本
此腳本為舊版 Muse-Nexus 實作，已不再主動維護。
請改用 `scripts/core/` 或 `nexus/` 中的對應模組。
"""
import subprocess
import shutil

class Linter:
    """封裝靜態分析工具 (Ruff) 的執行。"""

    def __init__(self):
        self.paths_to_try = [
            shutil.which("ruff"),
            f"{shutil.which('uv') or 'uv'} run --with ruff ruff",
            "ruff"
        ]

    def scan(self, files):
        """執行掃描並返回結構化違規列表。"""
        if not files: return []
        
        for base in self.paths_to_try:
            if not base: continue
            try:
                cmd_parts = base.split()
                # 雙重格式旗標試錯 (Fix detected by self-review)
                for format_flag in ["--output-format", "--format"]:
                    full_cmd = cmd_parts + ["check", format_flag, "json"] + files
                    res = subprocess.run(full_cmd, capture_output=True, text=True)
                    if res.returncode in [0, 1] and res.stdout.strip().startswith("["):
                        return res.stdout.strip()
            except Exception: continue
        return "[]"

    def heal(self, files):
        """執行自動自癒 (Pre-emptive Healing) (Phase 2)。"""
        if not files: return
        print(f"🧬 [Self-Healer] Attempting to pre-emptively heal {len(files)} files...")
        
        for base in self.paths_to_try:
            if not base: continue
            try:
                cmd_parts = base.split()
                # 執行 ruff check --fix
                full_cmd = cmd_parts + ["check", "--fix", "--exit-zero"] + files
                subprocess.run(full_cmd, capture_output=True, text=True)
                
                # 執行 ruff format (確保排版一致)
                full_cmd_fmt = cmd_parts + ["format"] + files
                subprocess.run(full_cmd_fmt, capture_output=True, text=True)
                break
            except Exception: continue
