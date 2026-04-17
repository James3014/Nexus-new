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

async def async_execute_tactical_node(node, repo_root):
    """異步版本的 L3 調度接口"""
    click.secho(f"\n⚔️ [L4:Executing-Node] {node.node_id}: {node.intent}", fg="blue", bold=True)
    node.status = "EXECUTING"
    
    # 這裡調用現有的 execute_tactical_node (它本身是同步的，所以跑在 executor 中)
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, execute_tactical_node, node, repo_root)
    
    if success:
        node.status = "SUCCESS"
        click.secho(f"✅ [L4:Node-Victory] {node.node_id} PASSED.", fg="green")
    else:
        node.status = "FAIL"
        click.secho(f"❌ [L4:Node-Defeat] {node.node_id} FAILED.", fg="red")
    return success

async def campaign_master_loop(commander, task_nodes, repo_root):
    """L4 史詩級並行調度主循環"""
    while True:
        ready_nodes = commander.get_executable_nodes()
        if not ready_nodes:
            remaining = [n for n in task_nodes if n.status == "PENDING"]
            if remaining:
                click.secho("🛑 [L4:Campaign-Stalled] 戰役卡住，依賴關係未解除。", fg="red")
                break
            else:
                click.secho("🏆 [L4:Campaign-Victory] 戰役圓滿完成，所有節點已結案。", fg="cyan", bold=True)
                break
        
        # 環境屏障分組 (Codex 建議：物理隔離即並行)
        groups = commander.check_environment_fence(ready_nodes)
        for group in groups:
            click.echo(f"   [L4] 發動並行組：{[n.node_id for n in group]}")
            tasks = [async_execute_tactical_node(node, repo_root) for node in group]
            results = await asyncio.gather(*tasks)
            
            if any(not r for r in results):
                click.secho("⚠️ [L4:Batch-Warning] 部分任務失敗，中斷後續調度。", fg="yellow")
                return

def execute_tactical_node(node, repo_root):
    """L4 調用 L3 的神經接口"""
    from nexus.core.speculative_classifier import SpeculativeClassifier
    from nexus.core.project_planner import ProjectPlanner
    from nexus.core.skill_assembler import SkillAssembler
    
    classifier = SpeculativeClassifier(repo_root)
    intake_data = classifier.analyze_and_hydrate(node.intent)
    
    planner = ProjectPlanner(repo_root, envelope=node.envelope)
    strategy = planner.build_campaign(intake_data)
    
    # 🚀 [L3:Self-Assembly] 現場造槍邏輯
    if strategy.assembly_required:
        assembler = SkillAssembler(repo_root)
        new_skill = assembler.assemble_new_skill(node.intent, strategy.gap_reason)
        if new_skill:
            click.secho(f"🔧 [L3:Self-Assembly] New armament forged: {new_skill}", fg="magenta")
            if assembler.verify_skill_jit(new_skill):
                strategy.required_skills.append(new_skill)
                click.secho(f"✅ [L3:Self-Assembly] {new_skill} hot-mounted to current mission.", fg="green")

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
