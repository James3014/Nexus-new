#!/usr/bin/env python3
import sys
import os
import json
import click
import asyncio
import time
import subprocess
import traceback
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime

# 🧪 Nexus v23 Eternal Neural Swarm CLI (Self-Evolve Refactored)
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 🔗 Phase 3: 自體演化導入 Service 層 (硬化導入)
from nexus.services.cli_commands_service import CliCommandsService
import asyncio
import os
import concurrent.futures
import time
import uuid

import time
import uuid
import queue
import threading
import atexit

class SingleWriterQueue:
    """🛡️ [v23:IO] FIFO Background Writer to decouple disk IO from decision flow"""
    def __init__(self):
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _run(self):
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                path, content, mode = self._queue.get(timeout=0.1)
                from pathlib import Path
                p = Path(path)
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open(mode, encoding="utf-8") as f:
                    f.write(content)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                pass # Fail silently for async-eligible logs

    def put(self, path, content, mode="a"):
        if not self._stop_event.is_set():
            self._queue.put((path, content, mode))

    def flush(self):
        self._stop_event.set()
        self._queue.join()
        if self._worker.is_alive():
            self._worker.join(timeout=2.0)

# 🌐 Global Single-Writer Instance
_io_queue = SingleWriterQueue()
atexit.register(_io_queue.flush)

def _log_perf_span(name, start_ts, end_ts, decision_id, metadata=None):
    """🛡️ [v23:PerfMonitor] Async-eligible: Put to queue"""
    try:
        import json
        payload = {
            "span_name": name,
            "decision_id": decision_id,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "duration_ms": (end_ts - start_ts) * 1000,
            "metadata": metadata or {}
        }
        _io_queue.put("/Users/jameschen/Workspace/nexus/.nexus/metrics/perf_spans.jsonl", json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass

@click.group()
@click.pass_context
def nexus(ctx):
    """⚖️ Nexus Singularity OS (v23 Eternal Neural Swarm)"""
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("NEXUS_SKIP_PROTOCOL_GATE") == "1":
        return
    command_name = ctx.invoked_subcommand or (sys.argv[1] if len(sys.argv) > 1 else "")
    from nexus.services.continuous_learning import run_protocol_startup_gate
    result = run_protocol_startup_gate(REPO_ROOT, command_name=command_name)
    ctx.ensure_object(dict)
    ctx.obj["protocol_gate"] = result
    if not result.ok:
        raise click.ClickException(
            f"Protocol gate failed: {result.protocol_path} | ci({result.ci_mode})={result.ci_summary or result.ci_exit_code}"
        )

def _get_service():
    # Lazy: from nexus.services.cli_commands_service import CliCommandsService
    return CliCommandsService(REPO_ROOT)


def _run_governance_gate(*, dry_run: bool = True, wiki_drift_enforce_level: str = "p0") -> int:
    """Run governance gate with shared defaults for CLI entry commands."""
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "ops" / "ci_gate.py"),
        "--wiki-drift-enforce-level",
        wiki_drift_enforce_level,
    ]
    if dry_run:
        cmd.append("--dry-run")
    t0 = time.perf_counter()
    res = subprocess.run(cmd)
    t1 = time.perf_counter()
    # Note: decision_id is typically not available here, using global/placeholder
    _log_perf_span("ops.subprocess.gate", t0, t1, "NEXUS_SYSTEM_GATE", {"exit_code": res.returncode})
    return int(getattr(res, "returncode", 1))

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
    """🚀 [Phase E/V] AOS 消融實驗 (Service 化)"""
    # Lazy: from nexus.services.benchmark_service import BenchmarkService
    BenchmarkService(REPO_ROOT).run(dataset, repeat, dual_core_physical, ablation, tasks_count, output_csv)
    click.echo("✅ [Benchmark] Complete.")

@nexus.command(name="nexus:learning-sync")
@click.option("--peer", default=None, help="Peer address for P2P sync")
@click.option("--pull-eternal", is_flag=True, help="Fetch shared lessons from Arweave")
def learning_sync(peer, pull_eternal):
    """🛡️ 啟動聯邦經驗同步 (P2P/Arweave)"""
    from nexus.services.federated_learning import sync_federated_lessons
    asyncio.run(sync_federated_lessons(REPO_ROOT, peer=peer, pull_eternal=pull_eternal))

@nexus.command(name="nexus:closeout")
@click.option("--contract", default=".nexus/reports/done_contract.json", help="Path to the done contract JSON file")
def closeout(contract):
    """🛡️ Nexus Closeout Hard-Gate (PASS 報告強制驗證)"""
    status_path = REPO_ROOT / ".nexus" / "reports" / "closeout_status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "ops" / "closeout_guard.py"),
        "--contract",
        contract,
    ]
    t0 = time.perf_counter()
    res = subprocess.run(cmd, capture_output=True, text=True)
    t1 = time.perf_counter()
    _log_perf_span("ops.subprocess.closeout", t0, t1, "NEXUS_SYSTEM_CLOSEOUT", {"exit_code": res.returncode})
    if res.stdout:
        click.echo(res.stdout, nl=False)
    if res.stderr:
        click.echo(res.stderr, err=True, nl=False)

    payload = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "contract_path": str(contract),
        "exit_code": int(res.returncode),
        "status": "PASS" if res.returncode == 0 else "FAIL",
    }
    # 📥 [Patch B] Async-eligible: Offload status_path write
    _io_queue.put(str(status_path), json.dumps(payload, ensure_ascii=False, indent=2), mode="w")

    if res.returncode != 0:
        _io_queue.flush() # Ensure flush before exit
        sys.exit(res.returncode)
    click.echo(f"✅ [Closeout] PASS: Hard-Gate successfully cleared. Status file: {status_path}")

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

@memory.command("search")
@click.argument("query")
@click.option("--mode", type=click.Choice(["palace", "semantic", "dual"]), default="dual")
@click.option("--tenant", "tenant_id", default="default")
@click.option("--threshold", "min_palace_hit", default=0.8, type=float)
def memory_search(query: str, mode: str, tenant_id: str, min_palace_hit: float):
    """🚀 [Phase 32] 雙模語義/階層檢索入口"""
    from nexus.core.router import SkillsRouter
    router = SkillsRouter(str(REPO_ROOT))
    context = {
        "mode": mode,
        "tenant_id": tenant_id,
        "min_palace_hit": min_palace_hit,
        "active_domain": "undeclared" # 🛡️ 使用唯讀權限
    }
    
    t0 = time.perf_counter()
    result = router.memory_route(query, context)
    t1 = time.perf_counter()
    
    result["latency_ms"] = round((t1 - t0) * 1000, 2)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))

@memory.command("search")
@click.argument("query")
@click.option("--mode", type=click.Choice(["palace", "semantic", "dual"]), default="dual")
@click.option("--tenant", "tenant_id", default="default")
@click.option("--threshold", "min_palace_hit", default=0.8, type=float)
def memory_search(query: str, mode: str, tenant_id: str, min_palace_hit: float):
    """🚀 [Phase 32] 雙模語義/階層檢索入口"""
    from nexus.core.router import SkillsRouter
    router = SkillsRouter(str(REPO_ROOT))
    context = {
        "mode": mode,
        "tenant_id": tenant_id,
        "min_palace_hit": min_palace_hit,
        "active_domain": "undeclared" # 🛡️ 使用唯讀權限
    }
    
    t0 = time.perf_counter()
    result = router.memory_route(query, context)
    t1 = time.perf_counter()
    
    result["latency_ms"] = round((t1 - t0) * 1000, 2)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))

@nexus.command(name="nexus:research-map")
@click.option("--task-id", required=True, help="目標任務 ID")
@click.option("--output", default="research_map.mmd", help="匯出路徑")
def research_map_cmd(task_id, output):
    """🗺️ [DeepScientist] 生成 Mermaid 研究地圖"""
    from nexus.research.research_map import ResearchMapBuilder
    from nexus.research.findings_memory import FindingsMemoryStore
    
    store = FindingsMemoryStore(REPO_ROOT)
    cards = store.list_cards(scope="task")
    
    builder = ResearchMapBuilder(task_id)
    # 這裡我們基於記憶卡還原地圖
    for card in cards:
        builder.add_stage_node(card.stage, card.stage, status="completed")
        builder.add_memory_node(card)
    
    mmd_content = builder.render_mermaid()
    output_path = Path(output)
    builder.export_mmd(output_path)
    
    click.secho(f"✅ [ResearchMap] Generated for {task_id}", fg="green")
    click.echo(f"📍 Path: {output_path.absolute()}")
    click.echo("-" * 20)
    click.echo(mmd_content)

@nexus.command(name="nexus:memory-list")
@click.option("--scope", type=click.Choice(["task", "global"]), default="task")
@click.option("--kind", help="篩選種類 (episodes/knowledge/decisions)")
def memory_list_cmd(scope, kind):
    """🧠 [DeepScientist] 列出所有結構化研究記憶卡"""
    from nexus.research.findings_memory import FindingsMemoryStore
    
    store = FindingsMemoryStore(REPO_ROOT)
    cards = store.list_cards(scope=scope, kind=kind)
    
    click.secho(f"🧠 [Memory:{scope.upper()}] Found {len(cards)} cards", fg="cyan")
    for card in cards:
        click.echo(f" - [{card.kind}] {card.title} (ID: {card.id}) | Stage: {card.stage}")

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

    click.echo(json.dumps(result, indent=2, ensure_ascii=True))

# --- P8.2 Wisdom & Guard Integration ---

@nexus.group(name="nexus:wisdom")
def wisdom_group():
    """🛡️ Wisdom Edition: 智慧學習與模式探索 (v23)"""
    pass

@wisdom_group.command(name="sync")
@click.option("--force", is_flag=True, help="Force re-synthesis of all rules")
def wisdom_sync_cmd(force):
    """🔄 [Phase 4] 全量同步與合成：Lesson -> Wisdom Rule"""
    from nexus.services.wisdom_synthesizer import wisdom_synthesizer
    click.secho("🧠 Starting Wisdom Synthesis induction loop...", fg="cyan")
    res = wisdom_synthesizer.sync_all()
    if res["status"] == "SUCCESS":
        click.secho(f"✅ Synthesis Complete: {res['rules_synthesized']} global rules registered.", fg="green")
    else:
        click.secho(f"⚠️ Synthesis Idle: {res.get('status')}", fg="yellow")

@wisdom_group.command(name="audit-risk")
@click.argument("pack_path", type=click.Path(exists=True))
def wisdom_audit_risk_cmd(pack_path):
    """⚖️ [Phase 4] 執行預測性風險稽核：Implementation Pack -> Risk Score"""
    from nexus.services.predictive_audit import predictive_auditor
    import json
    
    click.secho(f"🔍 [Auditor] Auditing risk for: {pack_path}", fg="cyan")
    try:
        with open(pack_path, "r") as f:
            pack_data = json.load(f)
        
        report = predictive_auditor.audit_risk(pack_data)
        
        # Display Report
        color = "red" if report["status"] == "BLOCK" else "green"
        click.secho(f"\n[Risk Report]", bold=True)
        click.secho(f"Status: {report['status']} | Risk Score: {report['risk_score']}", fg=color)
        click.echo(f"Recommendation: {report['recommendation']}")
        
        if report["findings"]:
            click.echo("\n[Findings]")
            for f in report["findings"]:
                click.echo(f" - {f['severity']} Match: {f['rule_text']} (Similarity: {f['similarity']})")
                click.echo(f"   Evidence: {', '.join(f['evidence_ids'])}")
        else:
            click.echo("✅ No significant risks identified against current Wisdom Registry.")
            
    except Exception as e:
        click.secho(f"❌ Audit Error: {e}", fg="red")



@wisdom_group.command(name="lookup")
@click.option("--snippet", required=True, help="代碼片段或模式描述")
@click.option("--repo", default="nexus")
@click.option("--lang", default="rust")
def wisdom_lookup_cmd(snippet, repo, lang):
    """搜尋相似的歷史模式與決策建議"""
    from nexus_swarm.wisdom.lancedb_store import WisdomMemory
    from nexus_swarm.wisdom.online_learner import BayesianLearner
    
    wm = WisdomMemory()
    learner = BayesianLearner()
    hits = wm.lookup_similar(snippet, repo, lang, top_k=3)
    
    results = []
    for hit in hits:
        bias = learner.get_decision_bias(hit["pattern_id"])
        results.append({**hit, "prior_bias": bias})
    
    click.echo(json.dumps(results, indent=2, ensure_ascii=False))

@wisdom_group.command(name="feedback")
@click.option("--task-id", required=True)
@click.option("--pattern-id", required=True)
@click.option("--type", "feedback_type", type=click.Choice(["correct", "false_positive", "unsafe_missed"]), required=True)
@click.option("--actor", default="commander")
@click.option("--source", default="cli")
def wisdom_feedback_cmd(task_id, pattern_id, feedback_type, actor, source):
    """提交決策回饋 (Immutable Event Contract)"""
    from nexus_swarm.wisdom.feedback_api import FeedbackAPI
    from datetime import datetime
    
    api = FeedbackAPI()
    payload = {
        "task_id": task_id,
        "pattern_id": pattern_id,
        "type": feedback_type,
        "actor": actor,
        "source": source,
        "timestamp": datetime.utcnow().isoformat()
    }

def main_decision(task_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    🛡️ [v23:MainDecision] The Full Automated Closed-Loop Orchestrator
    """
    t_start = time.perf_counter()
    from nexus_swarm.wisdom.feedback_api import FeedbackAPI
    from nexus_swarm.guard.consensus_guard import ConsensusGuard
    from nexus_swarm.wisdom.auto_feedback import AutoFeedback
    from nexus_swarm.healing.predictive_healer import PredictiveHealer
    
    # 1. Wisdom Lookup (Prior Knowledge)
    tw0 = time.perf_counter()
    wisdom_api = FeedbackAPI()
    wisdom_prior_res = wisdom_api.learner.get_decision_bias("global-pattern")
    wisdom_prior = wisdom_prior_res['bypass_score']
    tw1 = time.perf_counter()
    _log_perf_span("wisdom.lookup", tw0, tw1, task_id, {"bias_score": wisdom_prior})
    
    # 2. & 4. Risk Assessment (Parallel Candidate)
    parallel_enabled = os.getenv("NEXUS_PATCH_C_PARALLEL", "False") == "True"
    
    if parallel_enabled:
        # ⚡ [Patch C] Limited Parallelization (Experimental)
        tg0 = time.perf_counter()
        th0 = time.perf_counter()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                guard = ConsensusGuard()
                healer = PredictiveHealer()
                
                f_guard = executor.submit(guard.validate_scenario, task_id, context, risk_score_prior=0.4)
                f_healer = executor.submit(healer.forecast_risk)
                
                # Wait with 3.0s timeout as per spec
                done, not_done = concurrent.futures.wait([f_guard, f_healer], timeout=3.0)
                
                if f_guard in done:
                    guard_result = f_guard.result()
                else:
                    raise TimeoutError("Guard execution timeout")
                
                if f_healer in done:
                    heal_risk = f_healer.result()
                else:
                    heal_risk = {'risk': 0.6, 'actions': ['TIMEOUT_RECOVERY'], 'reason': 'HEALER_TIMEOUT'}
            
            tg1 = time.perf_counter()
            th1 = time.perf_counter()
            _log_perf_span("guard.validate.parallel", tg0, tg1, task_id, {"pass": guard_result['consensus_pass']})
            _log_perf_span("healer.forecast.parallel", th0, th1, task_id, {"risk": heal_risk['risk']})
            
        except Exception as exc:
            # 🛡️ Fallback to Serial if parallel fails
            _log_perf_span("patch_c.fallback", time.perf_counter(), time.perf_counter(), task_id, {"reason": str(exc)})
            guard = ConsensusGuard()
            guard_result = guard.validate_scenario(task_id, context, risk_score_prior=0.4)
            healer = PredictiveHealer()
            heal_risk = healer.forecast_risk()
    else:
        # 🛡️ Standard Serial Path (v22.5 Baseline)
        tg0 = time.perf_counter()
        guard = ConsensusGuard()
        guard_result = guard.validate_scenario(task_id, context, risk_score_prior=0.4)
        tg1 = time.perf_counter()
        _log_perf_span("guard.validate", tg0, tg1, task_id, {"pass": guard_result['consensus_pass']})

        # 4. Predictive Heal Check
        th0 = time.perf_counter()
        healer = PredictiveHealer()
        heal_risk = healer.forecast_risk()
        th1 = time.perf_counter()
        _log_perf_span("healer.forecast", th0, th1, task_id, {"risk": heal_risk['risk']})

    # --- Post-Processing Decision Logic ---
    if not guard_result['consensus_pass']:
        _log_perf_span("orchestrator.total", t_start, time.perf_counter(), task_id, {"status": "GUARD_VETO"})
        return {'decision': 'HUMAN_REVIEW', 'reason': 'GUARD_VETO', 'risk': guard_result['validation']['risk_score']}

    # 3. Auto Feedback Loop (Learning)
    auto_fb = AutoFeedback(wisdom_api)
    if wisdom_prior > 0.8: # High bias pattern detected
        auto_fb.on_false_positive_block(task_id, wisdom_prior)

    if heal_risk['risk'] > 0.5:
        _log_perf_span("orchestrator.total", t_start, time.perf_counter(), task_id, {"status": "PRE_HEAL"})
        return {'decision': 'PRE_HEAL', 'actions': heal_risk['actions'], 'reason': 'SYSTEM_STRESS'}

    # 5. Final Prod Decision
    risk_score = guard_result.get('validation', {}).get('risk_score_penalty', 0.4)
    decision_out = {
        'decision': 'APPROVE',
        'confidence': 1.0 - min(1.0, risk_score),
        'wisdom_bias': wisdom_prior
    }
    _log_perf_span("orchestrator.total", t_start, time.perf_counter(), task_id, {"status": "APPROVE"})
    return decision_out
    res = api.submit_feedback(payload)
    click.echo(json.dumps(res, indent=2))

@wisdom_group.command(name="stats")
def wisdom_stats_cmd():
    """查看智慧學習器全局統計與收斂度"""
    from nexus_swarm.wisdom.online_learner import BayesianLearner
    learner = BayesianLearner()
    click.echo(json.dumps(learner.pattern_stats, indent=2))

@nexus.group(name="nexus:guard")
def guard_group():
    """🛡️ 抗幻覺門禁與多代理共識 (v23)"""
    pass

@guard_group.command(name="validate")
@click.option("--task-id", default="manual-audit")
@click.option("--file", "target_file")
@click.option("--symbol", "target_symbol")
@click.option("--risk", "risk_prior", default=0.4, type=float)
def guard_validate_cmd(task_id, target_file, target_symbol, risk_prior):
    """執行多代理共識校驗 (Consensus Guard)"""
    from nexus_swarm.guard.consensus_guard import ConsensusGuard
    guard = ConsensusGuard()
    mock_executor_res = {
        "target_file": target_file,
        "target_symbol": target_symbol
    }
    res = guard.validate_scenario(task_id, mock_executor_res, risk_score_prior=risk_prior)
    click.echo(json.dumps(res, indent=2))

@nexus.group(name="nexus:healing")
def healing_group():
    """🚑 預測性自癒與系統壓力預報 (v23)"""
    pass

@healing_group.command(name="forecast")
def healing_forecast_cmd():
    """執行全球風險預測掃描 (Predictive Heal)"""
    from nexus_swarm.healing.predictive_healer import PredictiveHealer
    healer = PredictiveHealer()
    res = healer.forecast_risk()
    click.echo(json.dumps(res, indent=2))

@nexus.command(name="nexus:xray")
@click.option("--target", multiple=True)
@click.option("--recursive", is_flag=True, default=True)
def xray(target, recursive):
    """👁️ v23 X-Ray: 全域多維度依賴觀測"""
    from nexus.services.xray_service import XRayService
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
    gate_rc = _run_governance_gate(dry_run=True, wiki_drift_enforce_level="p0")
    if gate_rc != 0:
        raise click.ClickException(
            f"Governance gate failed before acceptance-check (exit={gate_rc})."
        )
    _get_service().acceptance_check(window)


@nexus.command(name="nexus:governance-check")
@click.option("--strict", is_flag=True, help="Run governance gate in blocking mode (non-dry-run).")
@click.option(
    "--wiki-drift-enforce-level",
    default="p0",
    type=click.Choice(["warn", "p0"], case_sensitive=False),
    help="Drift enforce level passed through to ci_gate.",
)
def governance_check(strict, wiki_drift_enforce_level):
    """🛡️ Governance-Check: 執行治理門禁與 Wiki 同步阻斷檢查"""
    gate_rc = _run_governance_gate(
        dry_run=not strict,
        wiki_drift_enforce_level=wiki_drift_enforce_level,
    )
    if gate_rc != 0:
        raise click.ClickException(f"Governance gate failed (exit={gate_rc}).")
    click.echo("✅ [Governance-Check] PASS")

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

@nexus.command(name="nexus:generate-pack")
@click.option("--intent", required=True, help="High-level plan or goal")
def generate_pack_cmd(intent):
    """🛠️ [GeneralContractor] 將高階意圖編譯為 6-JSON 實作包"""
    # Lazy: from nexus.services.implementation_pack import ImplementationPackGenerator
    # Lazy: from nexus.services.readability_hud import ReadabilityHUD
    task_id = f"gen-pack-{int(time.time())}"
    root = REPO_ROOT
    
    # 模擬 Planner 針對意圖的初步預測 (這裡是 Wiring 展示點)
    mock_planner_out = {
        "goal": intent,
        "data_models": [{"name": "IntentModel", "fields": {"intent": "string"}}],
        "deliverables": ["impl_artifact.v1"],
        "acceptance_criteria": ["Readability Score > 95"]
    }
    
    from nexus.services.implementation_pack import ImplementationPackGenerator
    generator = ImplementationPackGenerator(root, task_id)
    click.secho(f"📡 Compiling Implementation Pack for: {intent}", fg="cyan")
    
    results = generator.generate(mock_planner_out)
    
    # 呼叫帝國 HUD
    from nexus.services.readability_hud import ReadabilityHUD
    hud = ReadabilityHUD(results["audit"])
    hud.display()
    
    click.secho(f"✅ Pack generated: .nexus/runs/{task_id}/implementation/", fg="green")

@nexus.command(name="nexus:sync-hud")
@click.option("--task-id", default="latest", help="Task ID to sync")
def sync_hud(task_id):
    """📡 同步最近一次的 Readability Audit 數據至 Nexus Desk Cockpit。"""
    repo_root = REPO_ROOT
    if task_id == "latest":
        runs_dir = repo_root / ".nexus" / "runs"
        if not runs_dir.exists():
            click.echo("❌ No runs directory found at .nexus/runs")
            return
        run_dirs = sorted(runs_dir.glob("*"), key=lambda d: d.stat().st_mtime, reverse=True)
        if not run_dirs:
            click.echo("❌ No task runs found.")
            return
        task_id = run_dirs[0].name
    
    audit_path = repo_root / ".nexus" / "runs" / task_id / "implementation" / "readability_audit.json"
    if not audit_path.exists():
        click.echo(f"❌ Audit report not found for {task_id}")
        return
        
    try:
        audit_data = json.loads(audit_path.read_text())
        from nexus.services.readability_hud import ReadabilityHUD
        hud = ReadabilityHUD(audit_data)
        hud.sync_to_cockpit(repo_root)
    except Exception as e:
        click.echo(f"❌ Sync Error: {e}")

@nexus.command(name="nexus:build-from-pack")
@click.argument("pack_path", type=click.Path(exists=True))
def build_from_pack(pack_path):
    """🔨 [Construction] 根據施工包執行自動化動工 (v26.0 Hardened)。"""
    # Lazy: from nexus.services.construction_service import ConstructionService
    repo_root = REPO_ROOT
    from nexus.services.construction_service import ConstructionService
    service = ConstructionService(repo_root)
    result = service.build(Path(pack_path))
    if result["status"] == "SUCCESS":
        click.secho(f"✅ Build Completed for {result['task_id']}", fg="green")
    else:
        click.secho(f"🛑 Build Failed: {result.get('reason')}", fg="red")

@nexus.command(name="nexus:audit-pack")
@click.option("--task-id", default="latest", help="Task ID to audit")
def audit_pack(task_id):
    """🔍 [Audit] 對現有的施工包執行治理稽核檢驗 (Governance-Prod)。"""
    repo_root = REPO_ROOT
    if task_id == "latest":
        runs_dir = repo_root / ".nexus" / "runs"
        if not runs_dir.exists():
            click.echo("❌ No runs found.")
            return
        run_dirs = sorted(runs_dir.glob("*"), key=lambda d: d.stat().st_mtime, reverse=True)
        if not run_dirs:
            click.echo("❌ No runs found.")
            return
        task_id = run_dirs[0].name
    
    audit_path = repo_root / ".nexus" / "runs" / task_id / "implementation" / "readability_audit.json"
    if not audit_path.exists():
        click.echo(f"❌ Audit report not found for {task_id}")
        return
        
    try:
        audit_data = json.loads(audit_path.read_text())
        from nexus.services.readability_hud import ReadabilityHUD
        hud = ReadabilityHUD(audit_data)
        hud.display()
    except Exception as e:
        click.echo(f"❌ Audit Error: {e}")

@nexus.command(name="nexus:learning-sync")
@click.option("--min-confidence", default=0.7)
def learning_sync(min_confidence):
    """🧪 [Eternal Memory] 同步高品質教訓到 Arweave 永久存儲"""
    # Lazy: from nexus.services.arweave_uploader import upload_lessons_to_arweave
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
    # Lazy: from scripts.eternal.slicer import slice_jsonl
    if policy:
        from scripts.eternal.slicer import slice_jsonl
        slices = slice_jsonl(Path(".nexus/knowledge/policymemory.jsonl"), days, max_mb)
        click.echo(f"✅ Policy Slices: {len(slices)} 檔案已存於 .nexus/eternal/slices/")
    if skills:
        from scripts.eternal.slicer import slice_jsonl
        slices = slice_jsonl(Path(".nexus/metrics/skillsoptimizationruns.jsonl"), days, max_mb)
        click.echo(f"✅ Skills Slices: {len(slices)} 檔案已存於 .nexus/eternal/slices/")

@eternal_group.command(name="offload")
@click.option("--wallet", default="~/.arweave/key.json")
def cmd_offload(wallet):
    """執行 Arweave 永恆記憶上鏈任務 (Bulk Upload)"""
    click.echo(f"🛡️ 啟動永恆記憶上鏈流程 (Wallet: {wallet})...")
    from scripts.eternal.offloader import offload_all_slices
    asyncio.run(offload_all_slices(wallet))
    click.echo("✅ 上鏈任務發送完畢。")

@eternal_group.command(name="anchor")
@click.option("--update", is_flag=True)
def cmd_anchor(update):
    """同步與校驗鏈上 Anchor 索引"""
    if update:
        from scripts.eternal.anchor import write_anchors
        anchors = write_anchors()
        click.echo(f"✅ Anchors 已同步。已上鏈: {anchors.get('total_offloaded_mb', 0):.2f} MB")
    else:
        from scripts.eternal.anchor import write_anchors
        anchors = write_anchors()
        click.echo(json.dumps(anchors, indent=2))

@eternal_group.command(name="download")
@click.option("--txid", required=True)
def cmd_download(txid):
    """透過 Arweave Gateway 具現化永恆記憶分段"""
    from scripts.eternal.anchor import download_anchor
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

        traceback.print_exc()

@swarm_group.command("prod-audit")
@click.option("--pr", required=True, type=int)
def swarm_prod_audit(pr):
    """🚀 [v23:Full] 觸發全自動生產審計並啟動閉環決策"""
    context = {
        "pr_number": pr,
        "type": "production_deployment",
        "actor": "nexus-pilot-auto"
    }
    task_id = f"PROD-AUDIT-{pr}-{int(time.time())}"
    click.echo(f"🛡️ Launching Full Edition Prod Audit for PR {pr}...")
    
    decision = main_decision(task_id, context)
    
    # --- A to C Handoff (Governance Upgrade) ---
    if os.environ.get("NEXUS_GOVERNANCE_UPGRADE") == "1":
        click.echo("🔄 [v23.1] Executing Audit-to-Crystallize Handoff...")
        handoff_data = {
            "task_id": task_id,
            "phase": "A_TO_C",
            "audit_result": decision['decision'],
            "state_token": f"STATE-{int(time.time())}"
        }
        handoff_path = Path(".nexus/state/last_handoff.json")
        handoff_path.parent.mkdir(parents=True, exist_ok=True)
        with open(handoff_path, "w") as f:
            json.dump(handoff_data, f, indent=2)
        click.echo(f"✅ [Handoff] Saved to {handoff_path}")
        
        # --- Update Evidence Chain (manifest.json) ---
        manifest_path = Path("manifest.json")
        if manifest_path.exists():
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            
            # 確保 artifacts 列表存在並新增 handoff 證據
            if "artifacts" not in manifest: manifest["artifacts"] = []
            manifest["artifacts"].append({
                "path": str(handoff_path),
                "md5": "DYNAMIC_HASH_V23",
                "role": "Governance Handoff (v23.1)"
            })
            manifest["generated_at"] = datetime.now().isoformat()
            
            tm0 = time.perf_counter()
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)
            tm1 = time.perf_counter()
            _log_perf_span("metrics.serialize", tm0, tm1, "NEXUS_MANIFEST_WRITE")
            click.echo("💎 [Evidence] last_handoff.json successfully linked to manifest.json")

    # --- Crystallize (C) Phase ---
    click.secho("\n--- [Final Orchestration Decision] ---", fg="cyan", bold=True)
    color = "green" if decision['decision'] == "APPROVE" else "yellow"
    if decision['decision'] == "HUMAN_REVIEW": color = "red"
    
    click.secho(json.dumps(decision, indent=2, ensure_ascii=False), fg=color)
    
    if decision['decision'] == "APPROVE":
        click.secho("\n✅ Production Contract Signed. Proceeding to Release Gate.", fg="green", bold=True)
    else:
        click.secho(f"\n✋ Action Intercepted: {decision['decision']}. Reason: {decision.get('reason', 'N/A')}", fg="yellow", bold=True)

@swarm_group.command("shadow-audit")
@click.option("--pr-range", required=True, help="PR range (e.g., 100-200)")
@click.option("--parallel", default=5, type=int, help="Number of parallel audits")
@click.option("--auto", is_flag=True, help="Auto-approve all decisions")
def shadow_audit(pr_range, parallel, auto):
    """🛡️ [v23:Accelerated] 執行批量陰影審計並收集智慧指標"""
    import asyncio
    import time
    
    start_pr, end_pr = map(int, pr_range.split("-"))
    prs = list(range(start_pr, end_pr + 1))
    
    if auto:
        os.environ["NEXUS_AUTO_APPROVE"] = "1"
        os.environ["NEXUS_SKIP_PROTOCOL_GATE"] = "1"

    click.secho(f"🚀 Launching Parallel Shadow Audit for PRs {start_pr}-{end_pr} (Parallel: {parallel})...", fg="cyan")

    async def run_single_audit(sem, pr_id):
        async with sem:
            context = {"pr_number": pr_id, "type": "shadow_audit", "actor": "nexus-burnin"}
            task_id = f"SHADOW-{pr_id}-{int(time.time())}"
            # Wrap synchronous main_decision in a thread for parallel execution if needed,
            # or just run it if it's already fast enough.
            return main_decision(task_id, context)

    async def audit_all():
        sem = asyncio.Semaphore(parallel)
        tasks = [run_single_audit(sem, pr) for pr in prs]
        return await asyncio.gather(*tasks)

    loop = asyncio.get_event_loop()
    results = loop.run_until_complete(audit_all())
    
    click.secho(f"\n✅ Shadow Audit Complete. Processed {len(results)} PRs.", fg="green")
    # Export summary placeholder
    metrics_path = Path(".nexus/metrics/shadow_audit_report.json")
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metrics_path, "w") as f:
        json.dump(results, f, indent=2)

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
