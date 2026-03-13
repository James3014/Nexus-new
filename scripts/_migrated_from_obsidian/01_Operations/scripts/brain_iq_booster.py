import os
import subprocess

def boost_iq(target_name):
    print(f"🚀 Boosting IQ for: {target_name}")
    # 這裡整合我們之前的工具
    # 1. 強制重刷屬性
    subprocess.run(["python3", "知識庫/01_Operations/scripts/librarian_ingest.py"])
    # 2. 強制神經織網
    subprocess.run(["python3", "知識庫/01_Operations/scripts/auto_linker.py"])
    print(f"✅ Target {target_name} intelligence enhanced.")

if __name__ == "__main__":
    target_file = "/Users/jameschen/Downloads/scripts/booster_targets.txt"
    if os.path.exists(target_file):
        with open(target_file, "r") as f:
            targets = f.readlines()
        for t in targets:
            name = t.strip().split("[[")[1].split("]]")[0]
            boost_iq(name)
