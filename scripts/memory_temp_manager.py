# 🛡️ Codex-Verified: Lvl13-Master-Seal (2026-03-03)
import subprocess
import os
import datetime


def get_age(file_path):
    try:
        date_str = subprocess.check_output(
            ["git", "log", "-1", "--format=%ai", "--", file_path]
        ).decode("utf-8")
        if not date_str:
            return 999
        last_date = datetime.datetime.strptime(date_str[:10], "%Y-%m-%d")
        return (datetime.datetime.now() - last_date).days
    except:
        return 999


def run_temp_audit():
    print("🌡️ Memory-Temp-Manager: Cataloging brain heat...")
    stats = {"Hot": 0, "Warm": 0, "Cold": 0}

    for root, dirs, files in os.walk("知識庫"):
        dirs[:] = [
            d
            for d in dirs
            if d not in ["00_System_Knowledge", "01_Operations", "scripts", ".git"]
        ]
        for file in files:
            if file.endswith(".md") and file != "README.md":
                age = get_age(os.path.join(root, file))
                if age <= 7:
                    stats["Hot"] += 1
                elif age <= 30:
                    stats["Warm"] += 1
                else:
                    stats["Cold"] += 1

    report_path = "知識庫/01_Operations/Brain_Reports/Brain_Heat_Map.md"
    with open(report_path, "w") as f:
        f.write("# 🌡️ 大腦記憶溫階地圖\n\n")
        f.write(f"- 🔥 **Hot (最近一週)**: {stats['Hot']} 份\n")
        f.write(f"- 🌤️ **Warm (最近一月)**: {stats['Warm']} 份\n")
        f.write(f"- ❄️ **Cold (陳舊資料)**: {stats['Cold']} 份\n")

    print(f"✅ Heat map generated. Hot docs: {stats['Hot']}")


if __name__ == "__main__":
    run_temp_audit()
