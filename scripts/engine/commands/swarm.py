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
        print(f"🧬 [Nexus:Swarm] Initiating mission for task: {task_name}")
        
        # 🛡️ 物理化認知注入 (Self-Awareness)
        if verbose_prompt:
            try:
                from nexus.core.agent_awareness import NexusSelfAwareness
                awareness = NexusSelfAwareness()
                print("--- DEBUG: Injected Self-Awareness Prompt ---")
                print(awareness.get_self_awareness_prompt())
                print("--------------------------------------------")
            except ImportError:
                print("⚠️  [Nexus:Swarm] Self-Awareness module not found, skipping injection.")

        # 🚀 執行真實任務 (接入 NexusEngine)
        try:
            from nexus.engine.coordinator import NexusEngine
            from nexus.engine.config import EngineConfig
            
            config = EngineConfig(project_root=REPO_ROOT, delivery_mode=delivery_mode)
            engine = NexusEngine(config=config)
            
            print(f"📡 [Nexus:Swarm] Dispatching task '{task_name}' to engine (Mode: {delivery_mode})...")
            # 實行 run_bug 作為實體任務測試
            success = engine.run_bug(bug_id=task_name)
            
            if success:
                print("✅ [Nexus:Swarm] Mission Succeeded.")
            else:
                print("❌ [Nexus:Swarm] Mission Failed.")
        except Exception as e:
            print(f"❌ [Nexus:Swarm] Critical execution error: {e}")
            sys.exit(1)
