#!/usr/bin/env -S uv run --with requests
# 🛡️ Brain-B 健康監控器 V1.0 (2026-03-10)
import os
import subprocess
import json
import time
from datetime import datetime
from pathlib import Path

# --- 配置 ---
LAB_DIR = Path("/Users/jameschen/Downloads/Brain_B_Lab")
STATUS_PATH = LAB_DIR / "services_status.json"

def get_service_info(label):
    try:
        res = subprocess.run(["launchctl", "list", label], capture_output=True, text=True)
        active = res.returncode == 0
        # 這裡簡單模擬錯誤數與心跳，實務上可解析 /tmp/*.err
        err_file = f"/tmp/{label.split('.')[-1]}.err"
        error_count = 0
        if os.path.exists(err_file):
            error_count = len(open(err_file).readlines())
        
        return {
            "active": active,
            "errors": error_count,
            "updated_at": datetime.now().isoformat()
        }
    except:
        return {"active": False, "errors": 0, "updated_at": datetime.now().isoformat()}

def update_status():
    services = {
        "tgbridge": "com.musecore.tgbridge",
        "dream": "com.musecore.brainb.dream",
        "push": "com.musecore.brainb.push",
        "evolve": "com.musecore.brainb.evolve",
        "incubate": "com.musecore.brainb.incubate"
    }
    
    status_data = {}
    for name, label in services.items():
        status_data[name] = get_service_info(label)
    
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status_data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    while True:
        update_status()
        time.sleep(10) # 每 10 秒更新一次
