import subprocess
import datetime

def generate_report():
    print("💎 Generating Monthly Brain Evolution Report...")
    
    # 統計最近 30 天的 Commit
    try:
        commits = subprocess.check_output(["git", "log", "--since='1 month ago'", "--oneline"]).decode("utf-8")
        commit_count = len(commits.strip().split("\n"))
    except:
        commit_count = 0

    now = datetime.datetime.now()
    report_name = f"Brain_Evolution_{now.strftime('%Y_%m')}.md"
    
    with open(f"知識庫/01_Operations/{report_name}", "w") as f:
        f.write(f"# 💎 大腦進化月報 - {now.strftime('%Y %B')}\n\n")
        f.write(f"- **總體變更次數**: {commit_count} commits\n")
        f.write(f"- **當前 Lvl 級別**: Lvl 12 (Integrated)\n")
        f.write("\n## 🚀 關鍵達成里程碑\n")
        f.write(commits)

if __name__ == "__main__":
    generate_report()
