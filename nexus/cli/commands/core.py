import click
import json
import time
import subprocess
import asyncio
import sys
from pathlib import Path
from typing import Dict, Any, List
from nexus.cli.utils import _get_service, REPO_ROOT, _log_perf_span, _io_queue
from datetime import datetime

@click.command(name="status")
@click.option("--global", "global_view", is_flag=True)
@click.option("--aos", is_flag=True)
@click.option("--aos-full", is_flag=True)
def status(global_view, aos, aos_full):
    """查看系統狀態與治理指標 (AOS 145+)"""
    _get_service().status(global_view, aos, aos_full)

@click.command(name="probe")
@click.option("--test-spec")
def probe(test_spec):
    """執行環境啟動自檢與投機測試"""
    res = _get_service().probe(test_spec)
    click.echo(f"✅ [Probe] Result: {res}")

@click.command(name="benchmark")
@click.option("--dataset", default="historical_regression")
@click.option("--repeat", default=1)
@click.option("--tasks", "tasks_count", default=10)
@click.option("--output", "output_csv", default=None)
@click.option("--dual-core-physical", is_flag=True)
@click.option("--ablation", is_flag=True)
def benchmark(dataset, repeat, tasks_count, output_csv, dual_core_physical, ablation):
    """🚀 [Phase E/V] AOS 消融實驗 (Service 化)"""
    from nexus.services.benchmark_service import BenchmarkService
    BenchmarkService(REPO_ROOT).run(dataset, repeat, dual_core_physical, ablation, tasks_count, output_csv)
    click.echo("✅ [Benchmark] Complete.")

@click.command(name="learning-sync")
@click.option("--peer", default=None, help="Peer address for P2P sync")
@click.option("--pull-eternal", is_flag=True, help="Fetch shared lessons from Arweave")
def learning_sync(peer, pull_eternal):
    """🛡️ 啟動聯邦經驗同步 (P2P/Arweave)"""
    from nexus.services.federated_learning import sync_federated_lessons
    asyncio.run(sync_federated_lessons(REPO_ROOT, peer=peer, pull_eternal=pull_eternal))

@click.command(name="closeout")
@click.option("--contract", default=".nexus/reports/done_contract.json", help="Path to the done contract JSON file")
def closeout(contract):
    """🛡️ Nexus Closeout Hard-Gate (PASS 報告強制驗證)"""
    status_path = REPO_ROOT / ".nexus" / "reports" / "closeout_status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "ops" / "closeout_guard.py"), "--contract", contract]
    t0 = time.perf_counter()
    res = subprocess.run(cmd, capture_output=True, text=True)
    t1 = time.perf_counter()
    _log_perf_span("ops.subprocess.closeout", t0, t1, "NEXUS_SYSTEM_CLOSEOUT", {"exit_code": res.returncode})
    if res.stdout: click.echo(res.stdout, nl=False)
    if res.stderr: click.echo(res.stderr, err=True, nl=False)
    payload = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "contract_path": str(contract),
        "exit_code": int(res.returncode),
        "status": "PASS" if res.returncode == 0 else "FAIL",
    }
    _io_queue.put(str(status_path), json.dumps(payload, ensure_ascii=False, indent=2), mode="w")
    if res.returncode != 0:
        _io_queue.flush()
        sys.exit(res.returncode)
    click.echo(f"✅ [Closeout] PASS: Hard-Gate successfully cleared. Status file: {status_path}")
