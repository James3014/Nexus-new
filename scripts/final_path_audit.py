import os
import re


def audit_all_skills():
    skills_dir = os.path.expanduser("~/.openclaw/skills")
    print(f"🔍 Starting Deep Path Audit in: {skills_dir}")

    found_paths = []
    # 掃描所有技能腳本
    for root, dirs, files in os.walk(skills_dir):
        for file in files:
            if file.endswith((".py", ".sh", ".json")):
                path = os.path.join(root, file)
                try:
                    with open(path, "r", errors="ignore") as f:
                        content = f.read()
                    # 搜尋絕對路徑模式
                    matches = re.findall(r"\"(/Users/jameschen/[^\"]+)\"", content)
                    for m in matches:
                        found_paths.append((file, m))
                except:
                    continue

    # 驗證並報告
    report_path = "知識庫/01_Operations/Brain_Reports/Final_Path_Audit_Report.md"
    with open(report_path, "w") as f:
        f.write("# 🛡️ 全局路徑對位終極診斷報告\n\n")
        f.write("| 來源檔案 | 檢測路徑 | 物理狀態 | 建議 |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")

        fail_count = 0
        for source, p in sorted(list(set(found_paths))):
            exists = os.path.exists(p)
            status = "✅ OK" if exists else "❌ BROKEN"
            if not exists:
                fail_count += 1
            f.write(
                f"| {source} | `{p}` | {status} | {'-' if exists else '需修正至 01_Operations'} |\n"
            )

    print(
        f"🏁 Audit complete. Broken paths found: {fail_count}. Report at {report_path}"
    )


if __name__ == "__main__":
    audit_all_skills()
