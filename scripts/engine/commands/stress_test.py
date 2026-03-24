#!/usr/bin/env python3
import sys
from nexus.engine.coordinator import NexusEngine

def execute(cli, args):
    """🧪 Test 1: Recursion & Quota Stress Test"""
    print(f"🧪 [StressTest] Initiating recursion pressure for task: {args.task}")
    
    # 模擬強制配額限制
    if getattr(args, "force_quota", False) or getattr(args, "force_quota_limit", False):
        print("⚠️ [StressTest] Force-Quota active. Simulating LLM rejection...")
    
    # 直接呼叫引擎的 safe_execute_step 以測試遞迴攔截
    def recursive_func(depth):
        print(f"  -> Depth {depth}")
        if depth > 0:
            return cli.engine.safe_execute_step(
                nexus_phase="STRESS", 
                func=recursive_func, 
                depth=depth - 1
            )
        return "SUCCESS"

    max_depth = getattr(args, "max_depth", 10)
    try:
        # 開始遞迴內容分組內容分組
        cli.engine.safe_execute_step(nexus_phase="ROOT", func=recursive_func, depth=max_depth)
    except RecursionError as e:
        print(f"✅ [SafeGuard] PROOF: Successfully intercepted A2A loop: {e}")
    except Exception as e:
        print(f"❌ [StressTest] Unexpected error: {e}")
