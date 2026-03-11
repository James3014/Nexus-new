import subprocess
import os


def extract_proven_paths():
    print("💎 Reflective-Healer: Extracting proven success paths...")
    try:
        # 從 Git Log 中提取最近 5 條成功的變更紀錄
        log = subprocess.check_output(["git", "log", "-5", "--oneline"]).decode("utf-8")
        with open("知識庫/02_Arsenal/Proven_Workflows.md", "w") as f:
            f.write("# 🏆 實戰成功路徑紀錄 (Proven Workflows)\n\n")
            f.write(
                "> [!success] 核心價值\n> 自動紀錄經過驗證的指令組合，減少重複探索。\n\n---\n"
            )
            f.write(log)
    except:
        pass


def log_failure_pattern():
    print("🏥 Reflective-Healer: Logging failure patterns...")
    # 這裡未來會接一個全局 Error Hook，目前先建立骨架
    path = "知識庫/01_Operations/Protocols/Pitfall_Registry.md"
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write("# ⚠️ 避坑與失敗學習註冊表 (Pitfall Registry)\n\n")
            f.write(
                "- **[2026-03-02]**: `sed` 在處理帶有空格與 `#` 的檔案名時會失效。**對策**: 優先使用 Python `os.walk` 進行物理替換。\n"
            )
            f.write(
                "- **[2026-03-02]**: `re.sub` 刪除標籤後綴時會誤傷 WikiLink 括號。**對策**: 使用非貪婪匹配或 Python 精確語義比對。\n"
            )


if __name__ == "__main__":
    extract_proven_paths()
    log_failure_pattern()
