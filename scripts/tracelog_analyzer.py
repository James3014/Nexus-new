#!/usr/bin/env python3
import json
import os
from pathlib import Path
from collections import defaultdict

TRACELOG = "/Users/jameschen/Downloads/Muse-Nexus/tracelog.jsonl"
WEIGHTS = "/Users/jameschen/Downloads/Muse-Nexus/core/autonomic_weights.json"

def analyze_performance():
    print("📊 [Nexus:Analyzer] Extracting metrics from tracelog...")
    
    if not os.path.exists(TRACELOG):
        print("❌ Error: tracelog.jsonl not found.")
        return

    stats = {
        "total_commands": 0,
        "success_rate": 0.0,
        "total_tokens": 0,
        "fallback_count": 0,
        "avg_score": 0.0
    }
    
    commands = defaultdict(lambda: {"success": 0, "total": 0})
    
    with open(TRACELOG, "r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line)
                stats["total_commands"] += 1
                stats["total_tokens"] += data.get("tokens_used", 0)
                stats["avg_score"] += data.get("flashjudge_score", 0.0)
                
                cmd = data.get("command", "unknown")
                commands[cmd]["total"] += 1
                if data.get("status") == "SUCCESS":
                    commands[cmd]["success"] += 1
            except:
                continue

    if stats["total_commands"] > 0:
        stats["success_rate"] = (sum(c["success"] for c in commands.values()) / stats["total_commands"]) * 100
        stats["avg_score"] /= stats["total_commands"]

    print("\n--- PERFORMANCE SUMMARY ---")
    print(f"✅ Overall Success Rate: {stats['success_rate']:.2f}%")
    print(f"🪙 Total Tokens Consumed: {stats['total_tokens']}")
    print(f"🛡️ Avg Risk/Predict Score: {stats['avg_score']:.2f}")
    
    print("\n--- COMMAND BREAKDOWN ---")
    for cmd, info in commands.items():
        rate = (info["success"] / info["total"]) * 100
        print(f"  - {cmd}: {rate:.1f}% ({info['success']}/{info['total']})")

    # Analyze Crystal Improvement
    if os.path.exists(WEIGHTS):
        print("\n💎 [Crystal] Weight Distribution Analysis:")
        with open(WEIGHTS, "r") as f:
            weights = json.load(f)
            for phase, symbols in weights.items():
                top_skill = max(symbols.items(), key=lambda x: x[1])
                print(f"  - {phase}: Top Skill -> {top_skill[0]} ({top_skill[1]:.2f})")

if __name__ == "__main__":
    analyze_performance()
