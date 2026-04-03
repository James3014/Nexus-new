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

@nexus.command(name="nexus:skills-health")
@click.option("--workspace", default=".")
def skills_health(workspace):
    """🧬 [Skills-Health] 執行技能健康度掃描"""
    _get_service().skills_health(workspace)

if __name__ == "__main__":
    nexus()
