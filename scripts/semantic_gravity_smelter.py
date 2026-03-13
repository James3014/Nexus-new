import os
import glob
from datetime import datetime
from pathlib import Path

# Semantic Gravity Smelter
# 功能：掃描碎片化筆記，識別低熵檔案並提出熔煉計畫。
# 支援 Obsidian Vault 模式（預設）與 Brain_B_Lab 舊模式（相容）。


def resolve_base_path() -> Path:
    env_root = os.getenv("SMELTER_BASE_PATH") or os.getenv("MUSE_VAULT_ROOT")
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if p.exists():
            return p

    vault = Path("/Users/jameschen/Downloads/obsidian/知識庫")
    if vault.exists():
        return vault

    legacy = Path("/Users/jameschen/Downloads/Brain_B_Lab")
    if legacy.exists():
        return legacy

    return Path.cwd()


class BrainBSmelter:
    def __init__(self, base_path=None):
        self.base_path = Path(base_path).resolve() if base_path else resolve_base_path()
        self.is_legacy_lab = (self.base_path / "99_Experiments/Brain_B").exists()

        if self.is_legacy_lab:
            self.logs_globs = [str(self.base_path / "99_Experiments/Brain_B/*.md")]
            self.output_dir = self.base_path / "Future_Ops"
        else:
            self.logs_globs = [
                str(self.base_path / "01_Operations/Inbox/**/*.md"),
                str(self.base_path / "01_Operations/History/**/*.md"),
            ]
            self.output_dir = self.base_path / "01_Operations/Strategy"

    def scan_for_redundancy(self):
        """掃描重複性高、內容短、且超過 24 小時未更新的碎片筆記。"""
        files = []
        for pattern in self.logs_globs:
            files.extend(glob.glob(pattern, recursive=True))

        candidates = []
        for f in files:
            if f.endswith("README.md"):
                continue

            stats = os.stat(f)
            age_hours = (datetime.now().timestamp() - stats.st_mtime) / 3600
            if age_hours <= 24:
                continue

            with open(f, "r", encoding="utf-8", errors="ignore") as file:
                content = file.read()

            if self.is_legacy_lab:
                if ("DREAM_" in f or "EVOLUTION_LOG" in f) and len(content) < 500:
                    candidates.append(f)
            else:
                # Vault 模式：偏向短文本碎片
                if len(content) < 800:
                    candidates.append(f)

        return candidates

    def generate_smelt_plan(self, candidates):
        """產出熔煉計畫，準備將碎片轉化為高維結論。"""
        if not candidates:
            return "目前語義引力穩定，無須熔煉。"

        self.output_dir.mkdir(parents=True, exist_ok=True)
        plan_name = f"SMELT_PLAN_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        plan_path = self.output_dir / plan_name

        with open(plan_path, "w", encoding="utf-8") as f:
            f.write("# 🌀 語義熔煉計畫\n\n")
            f.write(f"**執行時間**: {datetime.now().isoformat()}\n")
            f.write(f"**待熔煉碎片數**: {len(candidates)}\n")
            f.write(
                f"**模式**: {'Brain_B_Lab Legacy' if self.is_legacy_lab else 'Obsidian Vault'}\n\n"
            )
            f.write("## 候選清單\n")
            for c in candidates:
                f.write(f"- {os.path.basename(c)}\n")
            f.write("\n## 預期產出\n")
            f.write("- [ ] 提取跨域雜交關鍵詞\n")
            f.write("- [ ] 更新演化日誌總表\n")
            f.write("- [ ] 合併重複碎片並補回核心索引\n")

        return f"熔煉計畫已生成：{plan_name}"


if __name__ == "__main__":
    smelter = BrainBSmelter()
    candidates = smelter.scan_for_redundancy()
    result = smelter.generate_smelt_plan(candidates)
    print(result)
