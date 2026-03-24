#!/usr/bin/env python3
import sys

def execute(cli, args):
    """🧪 Test 3: Self-Awareness Proof"""
    print(f"🧬 [Nexus:Swarm] Initiating mission for task: {args.task}")
    
    # 設置 Swarm 模式內容分組內容分組
    cli.multi_agent = True
    
    # 若 args 具備 verbose_prompt，則物理顯示自省注入內容分組
    if getattr(args, "verbose_prompt", False):
        from nexus.core.agent_awareness import NexusSelfAwareness
        awareness = NexusSelfAwareness()
        print("--- DEBUG: Injected Self-Awareness Prompt ---")
        print(awareness.get_awareness_prompt())
        print("--------------------------------------------")

    # 執行任務管線內容分組內容分組
    try:
        success = cli.engine.run_bug(args.task)
        if success:
            print("✅ [Nexus:Swarm] Mission Succeeded.")
        else:
            print("❌ [Nexus:Swarm] Mission Failed.")
    except Exception as e:
        print(f"❌ [Nexus:Swarm] Critical error: {e}")
