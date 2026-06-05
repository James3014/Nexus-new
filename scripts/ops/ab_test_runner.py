#!/usr/bin/env python3
import argparse
import subprocess
import time
import os
import sys
import json
import ast
import threading
from pathlib import Path

# 嘗試載入 psutil
try:
    import psutil
except ImportError:
    print("Error: psutil is required. Run 'uv pip install psutil' or run with 'uv run --with psutil'", file=sys.stderr)
    sys.exit(1)

# 設定路徑
NEXUS_ROOT = Path(__file__).resolve().parent.parent.parent
LOCAL_HEAL_PYTHON = os.environ.get("NEXUS_ASTROPY_LEGACY_PYTHON", str(NEXUS_ROOT / ".venv_astropy_39/bin/python"))

class MemoryMonitor(threading.Thread):
    def __init__(self, interval=0.5):
        super().__init__()
        self.interval = interval
        self.keep_running = True
        self.max_rss_gb = 0.0
        self.rss_samples = []
        self._lock = threading.Lock()

    def run(self):
        while self.keep_running:
            current_rss = 0.0
            # 遍歷所有進程，加總 llama-server 與 python 的記憶體
            for proc in psutil.process_iter(['name', 'cmdline']):
                try:
                    name = proc.info['name'] or ''
                    cmdline = proc.info['cmdline'] or []
                    cmdline_str = ' '.join(cmdline)
                    
                    # 鎖定 llama-server 與本專案執行中的 python 腳本
                    if 'llama' in name.lower() or 'llama-server' in cmdline_str or ('python' in name.lower() and 'swe_local_heal' in cmdline_str):
                        current_rss += proc.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            rss_gb = current_rss / (1024 ** 3)
            with self._lock:
                self.rss_samples.append(rss_gb)
                if rss_gb > self.max_rss_gb:
                    self.max_rss_gb = rss_gb
            
            time.sleep(self.interval)

    def stop_and_get_stats(self):
        self.keep_running = False
        self.join()
        with self._lock:
            peak = self.max_rss_gb
            avg = sum(self.rss_samples) / len(self.rss_samples) if self.rss_samples else 0.0
        return peak, avg

def check_syntax(patch_code: str) -> bool:
    if not patch_code.strip():
        return False
    try:
        ast.parse(patch_code)
        return True
    except SyntaxError:
        return False

def reset_workspaces():
    workspaces_dir = NEXUS_ROOT / ".nexus/workspaces"
    if workspaces_dir.exists():
        for ws in workspaces_dir.iterdir():
            if ws.is_dir() and (ws / ".git").exists():
                print(f"🧹 Resetting git workspace: {ws.name}")
                subprocess.run(["git", "checkout", "--", "."], cwd=str(ws))
                subprocess.run(["git", "clean", "-fd"], cwd=str(ws))

def run_arm_task(arm_name: str, model: str, task_id: str, output_dir: Path) -> dict:
    reset_workspaces()
    print(f"\n🚀 Running task [{task_id}] on Arm [{arm_name}] ({model})...")
    output_file = output_dir / f"pred_{arm_name}_{task_id}.jsonl"
    if output_file.exists():
        output_file.unlink()
        
    env = os.environ.copy()
    env["NEXUS_OLLAMA_MODEL"] = model
    env["NEXUS_OLLAMA_SMALL_MODEL"] = "qwen2.5-coder:7b"
    env["NEXUS_ASTROPY_LEGACY_PYTHON"] = LOCAL_HEAL_PYTHON
    env["NEXUS_SEARCH_TIMEOUT_SECONDS"] = "1200"
    env["NEXUS_REPRO_TIMEOUT_SECONDS"] = "1200"
    env["NEXUS_PATCH_TIMEOUT_SECONDS"] = "1200"
    env["NEXUS_REPRO_RUN_TIMEOUT_SECONDS"] = "600"
    env["NEXUS_TEST_TIMEOUT_SECONDS"] = "600"
    env["NEXUS_OLLAMA_NUM_CTX"] = "4096"
    env["NEXUS_OLLAMA_NUM_PREDICT"] = "8192"

    cmd = [
        sys.executable, "-u", "-m", "benchmarking.swebench_lite.swe_local_heal",
        "--instance_id", task_id,
        "--output", str(output_file)
    ]

    # 啟動記憶體監控
    monitor = MemoryMonitor()
    monitor.start()

    start_time = time.time()
    try:
        # 執行修復子進程，將 stderr 與 stdout 都輸出到 console，便於即時除錯
        result = subprocess.run(cmd, env=env, cwd=str(NEXUS_ROOT))
    except Exception as e:
        print(f"❌ Subprocess failed to run: {e}")
        monitor.stop_and_get_stats()
        return {"status": "FAIL", "reason": str(e)}

    wall_time = time.time() - start_time
    peak_mem, avg_mem = monitor.stop_and_get_stats()

    # 解析結果
    solve_eligible = False
    syntax_pass = False
    patch_len = 0
    failure_reason = "NO_OUTPUT"
    
    if output_file.exists():
        try:
            with open(output_file, "r") as f:
                lines = f.readlines()
                if lines:
                    last_line = json.loads(lines[-1])
                    solve_eligible = bool(last_line.get("solve_eligible", False))
                    patch = last_line.get("model_patch", "")
                    patch_len = len(patch)
                    syntax_pass = check_syntax(patch)
                    failure_reason = last_line.get("failure_reason", "SUCCESS" if solve_eligible else "NO_PATCH")
        except Exception as e:
            failure_reason = f"PARSE_ERROR:{str(e)}"
            
    return {
        "status": "SUCCESS" if solve_eligible else "FAIL",
        "solve_eligible": solve_eligible,
        "syntax_pass": syntax_pass,
        "patch_len": patch_len,
        "wall_time": wall_time,
        "peak_mem_gb": peak_mem,
        "avg_mem_gb": avg_mem,
        "failure_reason": failure_reason
    }

def main():
    parser = argparse.ArgumentParser(description="Nexus LLM A/B Test Runner")
    parser.add_argument("--tasks", default="astropy__astropy-13033,astropy__astropy-14096,astropy__astropy-14365", help="Comma-separated task list")
    parser.add_argument("--output-dir", default=".nexus/reports/ab_test_v1", help="Output directory for reports")
    args = parser.parse_args()

    task_list = [t.strip() for t in args.tasks.split(",") if t.strip()]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    arms = [
        {"name": "ArmA_Qwen14b", "model": "qwen2.5-coder:14b"},
        {"name": "ArmB_Gemma12b", "model": "gemma4:12b"}
    ]

    results = {}
    
    for arm in arms:
        results[arm["name"]] = {}
        for task in task_list:
            res = run_arm_task(arm["name"], arm["model"], task, output_dir)
            results[arm["name"]][task] = res
            
    # 生成報告
    report_file = output_dir / "ab_test_report.md"
    
    # 統計指標
    summary = {}
    for arm in arms:
        name = arm["name"]
        arm_tasks = results[name]
        total = len(task_list)
        successes = sum(1 for t in arm_tasks.values() if t.get("solve_eligible"))
        syntax_passes = sum(1 for t in arm_tasks.values() if t.get("syntax_pass"))
        total_time = sum(t.get("wall_time", 0.0) for t in arm_tasks.values())
        max_peak_mem = max((t.get("peak_mem_gb", 0.0) for t in arm_tasks.values()), default=0.0)
        
        summary[name] = {
            "solve_rate": successes / total if total > 0 else 0.0,
            "syntax_pass_rate": syntax_passes / total if total > 0 else 0.0,
            "avg_time": total_time / total if total > 0 else 0.0,
            "peak_mem": max_peak_mem
        }

    # Markdown 渲染
    md = []
    md.append("# 📊 Nexus Model A/B Test Report")
    md.append(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    md.append("## 🏆 Summary Comparison")
    md.append("| Metric | Arm A (Qwen-14b) | Arm B (Gemma-12b) |")
    md.append("| :--- | :--- | :--- |")
    md.append(f"| **Solve Rate (Patch 成功率)** | {summary['ArmA_Qwen14b']['solve_rate']:.2%} | {summary['ArmB_Gemma12b']['solve_rate']:.2%} |")
    md.append(f"| **Syntax Pass Rate (語法通過率)** | {summary['ArmA_Qwen14b']['syntax_pass_rate']:.2%} | {summary['ArmB_Gemma12b']['syntax_pass_rate']:.2%} |")
    md.append(f"| **Avg Wall Time (平均耗時)** | {summary['ArmA_Qwen14b']['avg_time']:.1f}s | {summary['ArmB_Gemma12b']['avg_time']:.1f}s |")
    md.append(f"| **Peak Memory (記憶體尖峰)** | {summary['ArmA_Qwen14b']['peak_mem']:.2f} GB | {summary['ArmB_Gemma12b']['peak_mem']:.2f} GB |")
    md.append("\n## 📝 Detailed Task Trace")
    
    for task in task_list:
        md.append(f"### 🔍 Task: `{task}`")
        md.append("| Metric | Arm A (Qwen-14b) | Arm B (Gemma-12b) |")
        md.append("| :--- | :--- | :--- |")
        r_a = results["ArmA_Qwen14b"][task]
        r_b = results["ArmB_Gemma12b"][task]
        md.append(f"| Solve Eligible | {r_a.get('solve_eligible')} | {r_b.get('solve_eligible')} |")
        md.append(f"| Syntax Pass | {r_a.get('syntax_pass')} | {r_b.get('syntax_pass')} |")
        md.append(f"| Wall Time | {r_a.get('wall_time', 0.0):.1f}s | {r_b.get('wall_time', 0.0):.1f}s |")
        md.append(f"| Peak Memory | {r_a.get('peak_mem_gb', 0.0):.2f} GB | {r_b.get('peak_mem_gb', 0.0):.2f} GB |")
        md.append(f"| Failure Reason | `{r_a.get('failure_reason')}` | `{r_b.get('failure_reason')}` |")
        md.append("")

    report_content = "\n".join(md)
    report_file.write_text(report_content)
    
    print("\n" + "="*60)
    print("🎉 A/B TEST COMPLETE! Report saved to:", report_file)
    print("="*60)
    print(report_content)

if __name__ == "__main__":
    main()
