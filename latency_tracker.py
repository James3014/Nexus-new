import time
import json
import os

LOG_FILE = "/Users/jameschen/Workspace/nexus/artifacts/latency_log.json"

def log_start(article_id):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    data = {}
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f: data = json.load(f)
    data[str(article_id)] = {"start": time.time(), "end": None, "duration": None}
    with open(LOG_FILE, "w") as f: json.dump(data, f)

def log_end(article_id):
    if not os.path.exists(LOG_FILE): return
    with open(LOG_FILE, "r") as f: data = json.load(f)
    if str(article_id) in data:
        data[str(article_id)]["end"] = time.time()
        data[str(article_id)]["duration"] = round(data[str(article_id)]["end"] - data[str(article_id)]["start"], 2)
    with open(LOG_FILE, "w") as f: json.dump(data, f)

def get_report():
    if not os.path.exists(LOG_FILE): return "No data."
    with open(LOG_FILE, "r") as f: data = json.load(f)
    report = "### ⏱️ Nexus 結晶耗時匯報 (PAL Report)\n\n| Article | Duration (s) |\n| :--- | :--- |\n"
    for k in sorted(data.keys(), key=int):
        v = data[k]
        if v["duration"]:
            report += f"| {k} | {v['duration']}s |\n"
    return report

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2: sys.exit(0)
    if sys.argv[1] == "start": log_start(sys.argv[2])
    elif sys.argv[1] == "end": log_end(sys.argv[2])
    elif sys.argv[1] == "report": print(get_report())
