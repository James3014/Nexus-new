#!/usr/bin/env python3
import sys
import click
import subprocess
from pathlib import Path

def register(nexus_group, REPO_ROOT):
    """
    🧬 註冊 Swarm 認知模組。
    負責任務分發與 $AWARENESS 注入。
    """
    @nexus_group.group(name="swarm")
    def swarm():
        """🧬 [v24.2] Multi-Agent Swarm with Self-Awareness Injection"""
        pass

    @swarm.command(name="run")
    @click.argument("task_name")
    @click.option("--verbose-prompt", is_flag=True, help="Display injected self-awareness prompt")
    @click.option("--delivery-mode", default="standard", help="Execution priority: low|standard|high")
    def swarm_run(task_name, verbose_prompt, delivery_mode):
        """🚀 Initiate swarm mission with cognitive awareness."""
        # 🛡️ 物理化任務 ID 安全化 (防止檔名衝突與特殊字元)
        import hashlib
        task_slug = task_name[:20].replace("/", "_").replace(" ", "_")
        task_hash = hashlib.md5(task_name.encode()).hexdigest()[:8]
        safe_task_id = f"swarm_{task_slug}_{task_hash}"
        
        print(f"🧬 [Nexus:Swarm] Initiating mission: {safe_task_id}")
        print(f"📄 Task Description: {task_name}")
        
        # 🛡️ 物理化認知注入 (Self-Awareness)
        if verbose_prompt:
            try:
                from nexus.core.agent_awareness import NexusSelfAwareness
                awareness = NexusSelfAwareness()
                print("--- DEBUG: Injected Self-Awareness Prompt ---")
                # 修正 API 呼叫名稱
                print(awareness.get_self_awareness_prompt())
                print("--------------------------------------------")
            except (ImportError, AttributeError) as e:
                print(f"⚠️  [Nexus:Swarm] Self-Awareness injection failed: {e}")

        # 🚀 執行真實任務 (接入 NexusEngine)
        try:
            from nexus.engine.coordinator import NexusEngine
            from nexus.engine.config import EngineConfig
            
            config = EngineConfig(project_root=REPO_ROOT, delivery_mode=delivery_mode)
            engine = NexusEngine(config=config)
            run_bug = getattr(engine, "run_bug")
            
            print(f"📡 [Nexus:Swarm] Dispatching task '{safe_task_id}' to engine (Mode: {delivery_mode})...")
            # 使用安全 ID 呼叫引擎
            success = run_bug(bug_id=safe_task_id, desc=task_name)
            
            if success:
                print("✅ [Nexus:Swarm] Mission Succeeded.")
            else:
                print("❌ [Nexus:Swarm] Mission Failed.")
        except Exception as e:
            print(f"❌ [Nexus:Swarm] Critical execution error: {e}")
            sys.exit(1)
