#!/usr/bin/env python3
"""
🧠 Nexus Autonomous Repair Loop — ReAct Self-Healing Engine (v23.8)

Orchestrates the self-healing process:
1. Reads failure summary from ci_gate
2. Invokes Gemini for repair strategy
3. Executes repairs
4. Re-verifies via ci_gate --dry-run
5. Rolls back on persistent failure
"""
import subprocess
import os
import sys
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nexus.core.decorators import nexus_metabolize
from scripts.ops.rollback_guard import RollbackGuard

SUMMARY_FILE = ROOT / ".nexus" / "reports" / "last_failure_summary.txt"
INVOKE_SCRIPT = ROOT / "scripts" / "ops" / "gemini_nexus_invoke.py"
CI_GATE_SCRIPT = ROOT / "scripts" / "ops" / "ci_gate.py"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
MAX_ROUNDS = 5
ROLLBACK_TRIGGER_ROUND = 3


@nexus_metabolize(task_name="Autonomous Repair Loop")
def run_repair_loop():
    print("🧠 [Autonomous-Repair] Initializing ReAct Healing Cycle...")

    guard = RollbackGuard(ROOT)
    guard.capture_state()

    current_round = 1

    while current_round <= MAX_ROUNDS:
        print(f"\n🌀 [Round {current_round}/{MAX_ROUNDS}] Starting repair attempt...")

        if not SUMMARY_FILE.exists():
            print("✅ No failure summary found. System appears healthy.")
            break

        failure_context = SUMMARY_FILE.read_text(encoding="utf-8")

        # 1. Construct the Repair Prompt
        prompt = (
            "NEXUS AUTONOMOUS REPAIR MISSION\n\n"
            "The system failed a CI check. Here is the context:\n"
            f"{failure_context}\n\n"
            "GOAL: Fix the issue identified in the STDERR.\n\n"
            "INSTRUCTIONS:\n"
            "- Output ONLY the shell commands required to fix it, one per line.\n"
            "- Do not explain yourself.\n"
            "- Focus on minimal, precise changes.\n"
        )

        if current_round == ROLLBACK_TRIGGER_ROUND:
            print(
                f"🚨 [Round {ROLLBACK_TRIGGER_ROUND}] Persistence detected. "
                "Rolling back tracked changes for a fresh start..."
            )
            guard.reset_to_head()
            prompt += (
                "\nNOTE: Last attempts failed. Environment has been restored. "
                "Approach from a completely different angle.\n"
            )

        # 2. Invoke Gemini for Fixes
        invoke_cmd = [
            str(VENV_PYTHON), str(INVOKE_SCRIPT),
            "--prompt", prompt,
            "--preflight",
        ]

        print("📡 Consulting Zenith (Gemini) for repair strategy...")
        res = subprocess.run(invoke_cmd, capture_output=True, text=True)

        if res.returncode != 0:
            print(f"❌ Gemini invocation failed (RC={res.returncode}): {res.stdout[:200]}")
            current_round += 1
            time.sleep(2)
            continue

        repair_commands = res.stdout.strip().splitlines()

        # 3. Execute Repairs
        print(f"🛠️ Executing {len(repair_commands)} repair commands...")
        for cmd in repair_commands:
            if cmd.strip() and not cmd.startswith("#"):
                print(f"  > {cmd}")
                subprocess.run(cmd, shell=True, cwd=str(ROOT))

        # 4. Verify with CI Gate (Dry-run)
        print("🔎 Verifying repair...")
        verify_cmd = [str(VENV_PYTHON), str(CI_GATE_SCRIPT), "--dry-run"]
        v_res = subprocess.run(verify_cmd)

        if v_res.returncode == 0:
            print(f"🎉 [SUCCESS] System repaired in {current_round} round(s)!")
            SUMMARY_FILE.unlink(missing_ok=True)
            return 0

        current_round += 1
        time.sleep(2)  # Cooldown

    print(
        "❌ [FAILURE] Autonomous repair exhausted all rounds. "
        "Human intervention required."
    )
    return 1


if __name__ == "__main__":
    sys.exit(run_repair_loop())
