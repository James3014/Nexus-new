#!/usr/bin/env python3
import sys
import os
import click
from pathlib import Path
from nexus.services.continuous_learning import run_protocol_startup_gate

# 🧪 Nexus v23 Eternal Neural Swarm CLI (Self-Evolve Refactored)
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 🔗 Phase 3: 自體演化導入 Service 層 (硬化導入)
from nexus.services.benchmark_service import BenchmarkService
from nexus.services.xray_service import XRayService
from nexus.services.cli_commands_service import CliCommandsService
from nexus.core.skill_compressor import SkillCompressor
from nexus.services.arweave_uploader import upload_lessons_to_arweave
import asyncio
from scripts.eternal.slicer import slice_jsonl
from scripts.eternal.offloader import offload_all_slices
from scripts.eternal.anchor import write_anchors, download_anchor

@click.group()
@click.pass_context
def nexus(ctx):
    """⚖️ Nexus Singularity OS (v23 Eternal Neural Swarm)"""
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("NEXUS_SKIP_PROTOCOL_GATE") == "1":
        return
    command_name = ctx.invoked_subcommand or (sys.argv[1] if len(sys.argv) > 1 else "")
    result = run_protocol_startup_gate(REPO_ROOT, command_name=command_name)
    ctx.ensure_object(dict)
    ctx.obj["protocol_gate"] = result
    if not result.ok:
        raise click.ClickException(
            f"Protocol gate failed: {result.protocol_path} | ci({result.ci_mode})={result.ci_summary or result.ci_exit_code}"
        )

def _get_service():
    return CliCommandsService(REPO_ROOT)

@nexus.command(name="nexus:status")
@click.option("--global", "global_view", is_flag=True)
@click.option("--aos", is_flag=True)
@click.option("--aos-full", is_flag=True)
def status(global_view, aos, aos_full):
    """查看系統狀態與治理指標 (AOS 145+)"""
    _get_service().status(global_view, aos, aos_full)

@nexus.command(name="nexus:probe")
@click.option("--test-spec")
def probe(test_spec):
    """執行環境啟動自檢與投機測試"""
    res = _get_service().probe(test_spec)
    click.echo(f"✅ [Probe] Result: {res}")

@nexus.command(name="nexus:benchmark")
@click.option("--dataset", default="historical_regression")
@click.option("--repeat", default=1)
@click.option("--tasks", "tasks_count", default=10)
@click.option("--output", "output_csv", default=None)
@click.option("--dual-core-physical", is_flag=True)
@click.option("--ablation", is_flag=True)
def benchmark(dataset, repeat, tasks_count, output_csv, dual_core_physical, ablation):
    """🚀 [Phase E/V] AOS 消融實驗 (Service 化)內容、內容及性能內容性能性能"""
    BenchmarkService(REPO_ROOT).run(dataset, repeat, dual_core_physical, ablation, tasks_count, output_csv)
    click.echo("✅ [Benchmark] Complete.")

@nexus.command(name="nexus:learning-sync")
@click.option("--peer", default=None, help="Peer address for P2P sync")
@click.option("--pull-eternal", is_flag=True, help="Fetch shared lessons from Arweave")
def learning_sync(peer, pull_eternal):
    """🛡️ 啟動聯邦經驗同步 (P2P/Arweave)"""
    from nexus.services.federated_learning import sync_federated_lessons
    asyncio.run(sync_federated_lessons(REPO_ROOT, peer=peer, pull_eternal=pull_eternal))

@nexus.group(name="nexus:memory")
def memory():
    """🛡️ 向量記憶體管理 (LanceDB)"""
    pass

@memory.command("rebuild")
@click.option("--workspace", default=".", help="Workspace root")
@click.option("--incremental", is_flag=True, help="Incremental upsert instead of full rebuild (v0.1: Full Only)")
def memory_rebuild(workspace: str, incremental: bool):
    """一鍵重建 LanceDB 向量索引 (P2-A/B)"""
    from nexus.services.memory_indexer import rebuild_memory_index
    from pathlib import Path
    
    if incremental:
        click.echo(json.dumps({"status": "todo", "message": "Incremental mode is planned for v0.2. Using full rebuild."}, indent=2))
        
    result = rebuild_memory_index(Path(workspace))
    click.echo(json.dumps(result, indent=2))

@memory.command("stats")
@click.option("--workspace", default=".", help="Workspace root")
def memory_stats(workspace: str):
    """查看向量索引統計數據 (P2-B)"""
    from nexus.services.memory_indexer import connect_memory_db, TABLE_NAME
    from pathlib import Path
    import pandas as pd
    
    try:
        db = connect_memory_db(Path(workspace))
        table = db.open_table(TABLE_NAME)
        # 轉為 pandas 進行快速統計
        df = table.to_pandas()
        stats = df.groupby("record_type").size().to_dict()
        
        click.echo(json.dumps({
            "status": "ok",
            "total_records": len(df),
            "distribution": stats,
            "db_path": str(Path(workspace) / ".nexus/memory/memory_index.lancedb")
        }, indent=2))
    except Exception as e:
        click.echo(json.dumps({"status": "error", "message": str(e)}, indent=2))

@nexus.group(name="nexus:health")
def health():
    """🛡️ 生產健康監控與 Bug 指紋 (P2-C)"""
    pass

@health.command("report")
@click.option("--workspace", default=".", help="Workspace root")
@click.option("--phase", default="all", help="Target phase or 'all'")
@click.option("--days", default=90, help="Window days")
def health_report(workspace, phase, days):
    """查看 Phase 健康指標報告 (Success/Phantom Rate)"""
    from nexus.services.health_analyzer import compute_overall_health, compute_phase_health
    from pathlib import Path
    
    repo_root = Path(workspace)
    if phase == "all":
        result = compute_overall_health(repo_root)
    else:
        result = compute_phase_health(repo_root, phase, days)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))

@health.command("bug-lookup")
@click.option("--workspace", default=".", help="Workspace root")
@click.argument("traceback")
@click.option("--top-k", default=3, help="相似 Bug 數量")
def health_bug_lookup(workspace, traceback, top_k):
    """根據 Traceback 搜尋歷史成功修復模板"""
    from nexus.services.bug_fingerprint import get_repair_recommendations
    from pathlib import Path
    
    repo_root = Path(workspace)
    diagnosis = {"traceback_snippet": traceback}
    result = get_repair_recommendations(repo_root, diagnosis)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))

@nexus.command(name="nexus:xray")
@click.option("--target", multiple=True)
@click.option("--recursive", is_flag=True, default=True)
def xray(target, recursive):
    """👁️ v23 X-Ray: 全域多維度依賴觀測"""
    path = XRayService(REPO_ROOT).run(list(target), recursive)
    click.echo(f"✅ [X-Ray] Report: {path}")

@nexus.command(name="nexus:compress-skills")
@click.option("--skill-root", default="~/.agents/skills")
def compress_skills(skill_root):
    """⚡ v23 Nono: 指令集壓縮 (160 -> 10 Atoms)"""
    _get_service().swarm_wave1() # Wave 1 包含此動作
    click.echo("✅ [Nono] Skills crystallized.")

# --- P3 Swarm Orchestration ---
@nexus.group(name="nexus:swarm")
def swarm_group():
    """🛡️ Swarm Orchestration: 蜂群調度與路由管理"""
    pass

@swarm_group.command(name="route-report")
@click.option("--workspace", default=".", help="工作區路徑")
@click.option("--phase", default="R", help="檢核階段 (P/X/D/R/A/C)")
def swarm_route_report(workspace, phase):
    """📊 生成路由權重與最佳路徑審計報告"""
    from scripts.learning.compute_route_weights import main as route_main
    from pathlib import Path
    
    repo_root = str(Path(workspace).absolute())
    route_main(repo_root, phase)

@swarm_group.command(name="gate-report")
@click.option("--workspace", default=".", help="工作區路徑")
@click.option("--phase", default="R", help="檢核階段 (P/X/D/R/A/C)")
def swarm_gate_report(workspace, phase):
    """🛡️ 生成分層治理 (Gate) 決策報告"""
    from scripts.learning.compute_route_weights import main as route_main
    from pathlib import Path
    
    repo_root = str(Path(workspace).absolute())
    route_main(repo_root, phase)

@swarm_group.command(name="dashboard")
@click.option("--workspace", default=".", help="工作區路徑")
def swarm_dashboard(workspace):
    """🚀 [Swarm:Cockpit] 啟動 nexus-desk 桌面監控中心 (Unified)"""
    import subprocess
    from pathlib import Path
    
    desk_dir = Path(workspace) / "nexus-desk"
    if not desk_dir.exists():
        click.echo(f"🛑 Error: nexus-desk project not found at {desk_dir}")
        return
        
    click.echo(f"🛡️ Launching Swarm Cockpit in {desk_dir}...")
    # NOTE: In production, URL params can be passed via deep links or config.
    subprocess.run(["npm", "run", "tauri", "dev"], cwd=str(desk_dir))

    decision = select_self_heal_route(repo_root, phase, diagnosis)
    print(json.dumps(decision, indent=2, ensure_ascii=False))

@swarm_group.command(name="cleanup")
@click.option("--workspace", default=".", help="工作區路徑")
@click.option("--ttl-days", default=90, type=int, help="保留天數 (TTL)")
def swarm_cleanup(workspace, ttl_days):
    """🧹 [Memory:Hygiene] 執行政策記憶 TTL 清理與磁碟維護"""
    from scripts.learning.cleanup_policy_memory import cleanup_policy_memory
    from pathlib import Path
    result = cleanup_policy_memory(Path(workspace), ttl_days)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))

@swarm_group.command(name="autotune")
@click.option("--workspace", default=".", help="工作區路徑")
@click.option("--window-days", default=7, type=int, help="學習窗口天數")
def swarm_autotune(workspace, window_days):
    """🧠 [Route:Autotune] 根據歷史表現動態微調路由權重"""
    from scripts.learning.autotune_route_weights import autotune_from_history
    from pathlib import Path
    weights = autotune_from_history(Path(workspace), window_days)
    click.echo(json.dumps(weights, indent=2, ensure_ascii=False))

@nexus.command(name="nexus:swarm")
@click.option("--wave", default=1)
@click.option("--features", default="hud,dual_d,distill,paperclip,nono")
def swarm(wave, features):
    """⚡ [Swarm] 啟動大規模 ROI 具現化波次"""
    if wave == 1:
        _get_service().swarm_wave1()
    elif wave == 2:
        _get_service().swarm_wave2()
    elif wave == 3:
        _get_service().swarm_wave3()
    else:
        click.echo(f"⚠️ Wave {wave} not yet implemented.")

@nexus.command(name="nexus:distill")
@click.option("--recent", default=1)
def distill(recent):
    """🧪 [Distiller] 從近期變更中自動蒸餾技能"""
    _get_service().swarm_wave1() # Wave 1 執行序列已包含
    click.echo("✅ [Distiller] New skill crystallized.")

@nexus.command(name="nexus:heartbeat")
@click.option("--test", is_flag=True)
def heartbeat(test):
    """🛸 [Paperclip] 啟動心跳監控與 RBAC 驗證"""
    _get_service().heartbeat(test)

@nexus.command(name="nexus:acceptance-check")
@click.option("--window", default=50)
def acceptance_check(window):
    """🧪 Acceptance-Check: 執行正式驗收門禁 (AOS Crystal Gate)"""
    _get_service().acceptance_check(window)

@nexus.command(name="nexus:hud")
@click.option("--refresh", default=2)
@click.option("--daemon", is_flag=True)
def hud(refresh, daemon):
    """📊 [HUD] 鎖定底行狀態顯示 (v23 永久化)"""
    _get_service().hud(refresh, daemon)

@nexus.command(name="nexus:release")
@click.option("--tag", required=True)
@click.option("--aos", required=True, type=int)
def release(tag, aos):
    """🚀 [Release] 正式發布掛籤與 SOTA 結晶封裝 (v23 Final Gate)"""
    _get_service().release(tag, aos)

@nexus.command(name="nexus:release")
@click.option("--tag", required=True)
@click.option("--aos", required=True, type=int)
def release(tag, aos):
    """🚀 [Release] 正式發布掛籤與 SOTA 結晶封裝 (v23 Final Gate)"""
    _get_service().release(tag, aos)

@nexus.command(name="nexus:spec-lock")
@click.argument("file_path")
def spec_lock(file_path):
    """🛡️ [Spec-Lock] 執行違憲攔截校驗"""
    _get_service().spec_lock(file_path)

@nexus.command(name="nexus:feature")
@click.argument("roadmap_str", required=False, default="v23-sota")
def feature(roadmap_str):
    """🌲 [Feature] 執行洞察路徑任務化"""
    _get_service().feature(roadmap_str)

@nexus.command(name="nexus:reach")
@click.option("--url", required=True)
@click.option("--tier", default=1, type=int)
def reach(url, tier):
    """📡 [Phase 1] Reach: UCC 萬能爬蟲核心入口"""
    _get_service().reach(url, tier)

@nexus.command(name="nexus:bug")
@click.argument("task")
@click.option("--dry-run", is_flag=True)
def bug(task, dry_run):
    """🐛 [Fix] 啟動實體 NexusEngine 修復任務 (v23 Eternal)"""
    _get_service().bug(task, dry_run)
    click.echo("✅ [Fix] Task completed.")

@nexus.command(name="nexus:learning-sync")
@click.option("--min-confidence", default=0.7)
def learning_sync(min_confidence):
    """🧪 [Eternal Memory] 同步高品質教訓到 Arweave 永久存儲"""
    result = asyncio.run(upload_lessons_to_arweave(
        REPO_ROOT, min_confidence
    ))
    if result["status"] == "uploaded":
        click.secho(f"✅ [Sync:Success] TX ID: {result['tx_id']}", fg="green")
    elif result["status"] == "cached":
        click.secho(f"⚪ [Sync:Cached] Already on Arweave: {result['tx_id']}", fg="yellow")
    elif result["status"] == "skip":
        click.echo(f"⚪ [Sync:Skip] {result['reason']}")
    else:
        click.secho(f"🛑 [Sync:Error] {result.get('reason', 'Unknown error')}", fg="red")

@nexus.group(name="nexus:eternal")
def eternal_group():
    """🛡️ Arweave 永恆記憶管理 (v23 Eternal Neural Swarm)"""
    pass

@eternal_group.command(name="slice")
@click.option("--policy", is_flag=True, default=True)
@click.option("--skills", is_flag=True)
@click.option("--days", default=30, type=int)
@click.option("--max-mb", default=1.0, type=float)
def cmd_slice(policy, skills, days, max_mb):
    """將治理回憶切分為上鏈分段 (Slice)"""
    if policy:
        slices = slice_jsonl(Path(".nexus/knowledge/policymemory.jsonl"), days, max_mb)
        click.echo(f"✅ Policy Slices: {len(slices)} 檔案已存於 .nexus/eternal/slices/")
    if skills:
        slices = slice_jsonl(Path(".nexus/metrics/skillsoptimizationruns.jsonl"), days, max_mb)
        click.echo(f"✅ Skills Slices: {len(slices)} 檔案已存於 .nexus/eternal/slices/")

@eternal_group.command(name="offload")
@click.option("--wallet", default="~/.arweave/key.json")
def cmd_offload(wallet):
    """執行 Arweave 永恆記憶上鏈任務 (Bulk Upload)"""
    click.echo(f"🛡️ 啟動永恆記憶上鏈流程 (Wallet: {wallet})...")
    asyncio.run(offload_all_slices(wallet))
    click.echo("✅ 上鏈任務發送完畢。")

@eternal_group.command(name="anchor")
@click.option("--update", is_flag=True)
def cmd_anchor(update):
    """同步與校驗鏈上 Anchor 索引"""
    if update:
        anchors = write_anchors()
        click.echo(f"✅ Anchors 已同步。已上鏈: {anchors.get('total_offloaded_mb', 0):.2f} MB")
    else:
        anchors = write_anchors()
        click.echo(json.dumps(anchors, indent=2))

@eternal_group.command(name="download")
@click.option("--txid", required=True)
def cmd_download(txid):
    """透過 Arweave Gateway 具現化永恆記憶分段"""
    file_path = asyncio.run(download_anchor(txid))
    if file_path:
        click.echo(f"✅ 下載完成：{file_path}")
    else:
        click.echo("🛑 下載失敗。")

@nexus.group(name="nexus:swarm")
def swarm_group():
    """🛡️ 分佈式蜂群治理 (NSP v0.1 Distributed Cluster)"""
    pass

@swarm_group.command("start-cluster")
def swarm_start_cluster():
    """啟動 Swarm Manager (Go) 核心控制面"""
    import subprocess
    import os
    
    manager_dir = os.path.join(os.getcwd(), "nexus-swarm")
    # In Batch 4A, manager is in nexus-swarm/manager/
    print(f"[NEXUS v22] Starting Swarm Manager (Go) at {manager_dir}...")
    # Run manager in background
    subprocess.Popen(["go", "run", "./manager"], cwd=manager_dir)
    print("✅ Swarm Manager (Go) is booting on :9000 (Control) and :9100 (Metrics)")

@swarm_group.command("start-node")
@click.option("--manager", default="localhost:9000")
@click.option("--region", default="local")
def swarm_start_node(manager, region):
    """啟動 Swarm Mission Node (Python)"""
    import subprocess
    import os
    
    node_script = os.path.join(os.getcwd(), "nexus-swarm", "node", "main.py")
    print(f"[NEXUS v22] Starting Swarm Node (Region: {region})...")
    subprocess.Popen(["uv", "run", "python", node_script, "--manager", manager, "--region", region])
    print(f"✅ Node Agent linked to {manager}")

@swarm_group.command("status")
def swarm_status():
    """查詢叢集即時狀態"""
    import requests
    try:
        resp = requests.get("http://localhost:9100/cluster/status")
        if resp.status_code == 200:
            status = resp.json()
            print(f"\n🛡️ Nexus Swarm Cluster Status")
            print(f"Nodes: {status.get('healthy_nodes', 0)}/{status.get('total_nodes', 0)} Healthy")
            for node in status.get('nodes', []):
                print(f" - {node['node_id']} [{node['region']}]: {node['health']} | CPU: {node['cpuPercent']}% | RAM: {node['memoryPercent']}%")
        else:
            print("❌ Failed to fetch cluster status.")
    except Exception as e:
        print(f"❌ Swarm Manager not reachable: {e}")

@swarm_group.command("shadow-audit")
@click.option("--pr", required=True, type=int)
def swarm_shadow_audit(pr):
    """手動觸發影子審計 (Shadow Audit)"""
    import requests
    from datetime import datetime
    payload = {
        "pr_number": pr,
        "repository": "nexus-v22",
        "branch": "main",
        "author": "nexus-pilot",
        "timestamp": datetime.now().isoformat()
    }
    try:
        resp = requests.post("http://localhost:8081/shadow-audit", json=payload)
        if resp.status_code == 200:
            print(f"✅ Shadow Audit for PR {pr} accepted. Check Desk for progress.")
        else:
            print(f"❌ Shadow Webhook error: {resp.text}")
    except Exception as e:
        import traceback
        print(f"❌ Shadow Webhook error: {e}")
        traceback.print_exc()

# --- P6 Federated Swarm ---
@swarm_group.group(name="federation")
def swarm_federation():
    """🛡️ Federated Swarm: 多叢集聯邦管理 (SFP v0.1)"""
    pass

@swarm_federation.command("peers")
def federation_peers():
    """查看聯邦叢集列表"""
    import requests
    try:
        resp = requests.get("http://localhost:9100/federation/peers")
        if resp.status_code == 200:
            peers = resp.json().get('peers', [])
            print(f"\n🛡️ Federated Swarm Peers")
            for p in peers:
                print(f" - {p['cluster_id']} [{p['region']}]: {p['manager_endpoint']} | Load: {p['available_capacity']}/{p['total_capacity']}")
        else:
            print("❌ Failed to fetch federation peers.")
    except Exception as e:
        print(f"❌ Connection failed: {e}")

@swarm_federation.command("leader")
def federation_leader():
    """查看全域 Leader 狀態"""
    import requests
    try:
        resp = requests.get("http://localhost:9100/federation/leader")
        if resp.status_code == 200:
            data = resp.json()
            print(f"\n👑 Global Leader Election (Term: {data.get('term', 0)})")
            print(f"Leader Cluster: {data.get('leader_cluster', 'PENDING')}")
        else:
            print("❌ Failed to fetch leader status.")
    except Exception as e:
        print(f"❌ Connection failed: {e}")

@swarm_federation.command("route-test")
@click.option("--task-id", default="fed-test-01")
@click.option("--region", default="us-east")
def federation_route_test(task_id, region):
    """測試跨叢集任務路由"""
    import requests
    payload = {"task_id": task_id, "preferred_region": region}
    try:
        resp = requests.post("http://localhost:9100/swarm/dispatch", json=payload)
        print(json.dumps(resp.json(), indent=2))
    except Exception as e:
        print(f"❌ Route test failed: {e}")

@nexus.command(name="nexus:skills-health")
@click.option("--workspace", default=".")
def skills_health(workspace):
    """🧬 [Skills-Health] 執行技能健康度掃描"""
    _get_service().skills_health(workspace)

if __name__ == "__main__":
    nexus()
