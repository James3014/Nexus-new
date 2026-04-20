import os
import sys
import subprocess
import time
import json
import click
import logging
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional

# --- 這裡僅展示 run 相關的重構區塊 ---

async def async_execute_tactical_node(node, repo_root, commander=None):
    """異步版本的 L3 調度接口，整合 L1-L6 閉環"""
    click.secho(f"\n⚔️ [L4:Executing-Node] {node.node_id}: {node.intent}", fg="blue", bold=True)
    node.status = "EXECUTING"
    
    loop = asyncio.get_event_loop()
    # 傳遞 commander 以便執行時反饋
    success = await loop.run_in_executor(None, execute_tactical_node, node, repo_root)
    
    if success:
        node.status = "SUCCESS"
        click.secho(f"✅ [L4:Node-Victory] {node.node_id} PASSED.", fg="green")
        # 🚀 [L3:Promotion] 成功則記錄技能表現
        from nexus.core.skill_promotion import SkillPromotionEngine
        promoter = SkillPromotionEngine(repo_root)
        # 獲取本任務使用的技能（模擬）
        promoter.record_usage("auto-gen-2258", True)
    else:
        # 🚀 [L4:Bursting] 失敗則觸發自癒閉環：判定是否需要爆破
        if commander and getattr(node, "complexity_score", 0) > 0.7:
            node.status = "BURSTING"
            commander.trigger_burst(node.node_id)
            click.secho(f"💥 [L4:Self-Healing] {node.node_id} failed with high complexity. Bursting triggered.", fg="magenta")
        else:
            node.status = "FAIL"
            click.secho(f"❌ [L4:Node-Defeat] {node.node_id} FAILED.", fg="red")
            
    return success

async def campaign_master_loop(commander, task_nodes, repo_root):
    """
    [L4 Campaign Orchestrator] 史詩級並行調度主循環 (Hardened)
    
    Architectural boundary:
    - This function is strictly an **L4 Orchestrator** responsible for DAG scheduling, bursting, and parallel node execution (P/X level macroscopic planning).
    - It does **NOT** run the P-X-D-R-A-C pipeline natively. 
    - The actual single-task P-X-D-R-A-C lifecycle (Plan, eXplore, Diagnose, Repair, Audit, Crystallize) is handled inside the L3 Task Pipeline (`NexusPipeline` in `nexus/engine/pipeline.py`), which is invoked under the hood by `execute_tactical_node`.
    """
    while True:
        # 🚧 [L4:Milestone] 里程碑檢查
        if commander.is_milestone_reached():
            click.secho("🚧 [L4:Milestone] Checkpoint reached. Syncing global beliefs...", fg="yellow")
            time.sleep(1) # 模擬人工審閱時間
            
        ready_nodes = commander.get_executable_nodes()
        if not ready_nodes:
            remaining = [n for n in commander.campaign_map.values() if n.status in ["PENDING", "EXECUTING", "BURSTING"]]
            if remaining:
                # 檢查是否有正在爆破的節點（這會產生新 PENDING）
                if any(n.status == "BURSTING" for n in commander.campaign_map.values()):
                    continue # 等待分裂完成
                click.secho("🛑 [L4:Campaign-Stalled] 戰役卡住。", fg="red")
                break
            else:
                click.secho("🏆 [L4:Campaign-Victory] 戰役圓滿完成。", fg="cyan", bold=True)
                break
        
        groups = commander.check_environment_fence(ready_nodes)
        for group in groups:
            tasks = [async_execute_tactical_node(node, repo_root, commander) for node in group]
            results = await asyncio.gather(*tasks)
            
            # 若有嚴重失敗且無法爆破，則終止戰役
            if any(not r for r in results) and not any(n.status == "BURSTING" for n in group):
                click.secho("⚠️ [L4:Batch-Warning] 部分任務不可修復，中斷調度。", fg="yellow")
                return

def execute_tactical_node(node, repo_root):
    """L4 調用 L3 的神經接口 (L1-L2 Hardened)"""
    from nexus.core.speculative_classifier import SpeculativeClassifier
    from nexus.core.project_planner import ProjectPlanner
    from nexus.core.skill_assembler import SkillAssembler
    from nexus.core.criteria_builder import CriteriaBuilder
    
    # 🚀 [L1:Clarify-Manager]
    classifier = SpeculativeClassifier(repo_root)
    intake_data = classifier.analyze_and_hydrate(node.intent)
    
    if intake_data.get("clarify_required"):
        click.secho(f"❓ [L1:Clarify] Intent fuzzy: {intake_data['clarify_suggestions'][0]}", fg="yellow")
        # 這裡模擬自動補全以維持自動化流
        intake_data["dimensions"]["logic_scope"] = "refactor"

    # 🚀 [L2:Criteria-Builder]
    cb = CriteriaBuilder(repo_root)
    criteria = cb.build_custom_criteria(node.intent)
    # 實體化驗收 Artifact
    cb.materialize_test_scripts(criteria, repo_root / ".nexus" / "tmp")
    
    planner = ProjectPlanner(repo_root, envelope=node.envelope)
    strategy = planner.build_campaign(intake_data)
    
    # 🚀 [L3:Self-Assembly]
    if strategy.assembly_required:
        assembler = SkillAssembler(repo_root)
        new_skill = assembler.assemble_new_skill(node.intent, strategy.gap_reason)
        if new_skill:
            if assembler.verify_skill_jit(new_skill):
                strategy.required_skills.append(new_skill)

    return _run_engine_flow(node.node_id, node.intent, strategy, repo_root)



def _run_engine_flow(run_id, task_id, strategy, repo_root):
    # 實體引擎執行邏輯...
    from nexus.core.swarm import NexusSwarmOrchestrator
    from nexus.engine.coordinator import NexusEngine
    from nexus.engine.config import EngineConfig
    
    config = EngineConfig(project_root=repo_root)
    engine = NexusEngine(config)
    
    orchestrator = NexusSwarmOrchestrator(engine=engine, task=task_id, allocation=strategy.swarm_config)
    swarm_result = orchestrator.run()
    return swarm_result["status"] != "FAIL"
