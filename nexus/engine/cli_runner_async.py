import asyncio
import time
from pathlib import Path

import click


def _infer_task_kind(task_text: str) -> str:
    text = str(task_text or "").strip().lower()
    feature_keywords = (
        "build",
        "create",
        "add",
        "implement",
        "feature",
        "新增",
        "建立",
        "實作",
        "開發",
    )
    if any(keyword in text for keyword in feature_keywords):
        return "feature"
    return "bug"


def _execute_via_canonical_service(task_text: str, repo_root: Path) -> bool:
    from nexus.app.command_service import NexusCommandService, TaskRequest
    from nexus.engine.config import EngineConfig
    from nexus.engine.coordinator import NexusEngine

    service = NexusCommandService(NexusEngine(EngineConfig(project_root=repo_root)))
    request = TaskRequest(task=task_text, delivery_mode="standard")
    if _infer_task_kind(task_text) == "feature":
        return bool(service.execute_feature(request))
    return bool(service.execute_bug(request))


async def async_execute_tactical_node(node, repo_root, commander=None):
    """Async tactical executor for campaign nodes."""
    click.secho(f"\n⚔️ [L4:Executing-Node] {node.node_id}: {node.intent}", fg="blue", bold=True)
    node.status = "EXECUTING"

    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, execute_tactical_node, node, repo_root)

    if success:
        node.status = "SUCCESS"
        click.secho(f"✅ [L4:Node-Victory] {node.node_id} PASSED.", fg="green")
        from nexus.core.skill_promotion import SkillPromotionEngine

        promoter = SkillPromotionEngine(repo_root)
        promoter.record_usage("auto-gen-2258", True)
    else:
        if commander and getattr(node, "complexity_score", 0) > 0.7:
            node.status = "BURSTING"
            commander.trigger_burst(node.node_id)
            click.secho(
                f"💥 [L4:Self-Healing] {node.node_id} failed with high complexity. Bursting triggered.",
                fg="magenta",
            )
        else:
            node.status = "FAIL"
            click.secho(f"❌ [L4:Node-Defeat] {node.node_id} FAILED.", fg="red")

    return success


async def campaign_master_loop(commander, task_nodes, repo_root):
    """
    L4 orchestrator for campaign DAG scheduling.

    Single-task execution is delegated to the canonical command-service seam
    through `execute_tactical_node`.
    """
    while True:
        if commander.is_milestone_reached():
            click.secho("🚧 [L4:Milestone] Checkpoint reached. Syncing global beliefs...", fg="yellow")
            time.sleep(1)

        ready_nodes = commander.get_executable_nodes()
        if not ready_nodes:
            remaining = [
                node for node in commander.campaign_map.values() if node.status in ["PENDING", "EXECUTING", "BURSTING"]
            ]
            if remaining:
                if any(node.status == "BURSTING" for node in commander.campaign_map.values()):
                    continue
                click.secho("🛑 [L4:Campaign-Stalled] 戰役卡住。", fg="red")
                break
            click.secho("🏆 [L4:Campaign-Victory] 戰役圓滿完成。", fg="cyan", bold=True)
            break

        groups = commander.check_environment_fence(ready_nodes)
        for group in groups:
            tasks = [async_execute_tactical_node(node, repo_root, commander) for node in group]
            results = await asyncio.gather(*tasks)
            if any(not result for result in results) and not any(node.status == "BURSTING" for node in group):
                click.secho("⚠️ [L4:Batch-Warning] 部分任務不可修復，中斷調度。", fg="yellow")
                return


def execute_tactical_node(node, repo_root):
    """Route tactical work through the canonical command-service seam."""
    return _execute_via_canonical_service(node.intent, Path(repo_root))
