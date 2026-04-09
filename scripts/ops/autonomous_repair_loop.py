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
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nexus.core.decorators import nexus_metabolize
from scripts.ops.rollback_guard import RollbackGuard
from nexus.services.memory import MemoryService, FaultLesson

SUMMARY_FILE = ROOT / ".nexus" / "reports" / "last_failure_summary.txt"
INVOKE_SCRIPT = ROOT / "scripts" / "ops" / "gemini_nexus_invoke.py"
CI_GATE_SCRIPT = ROOT / "scripts" / "ops" / "ci_gate.py"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
MAX_ROUNDS = 5
ROLLBACK_TRIGGER_ROUND = 3


def _recall_prior_wisdom(failure_context: str, mem: MemoryService) -> str:
    """🧠 [Anamnesis] Search knowledge base for similar prior failures."""
    # Extract simple signature: First 'error' or 'failed' line
    sig = "unknown_fault"
    for line in failure_context.splitlines():
        if "error" in line.lower() or "fail" in line.lower():
            sig = line.strip()[:100]
            break
    
    lessons = mem.lookup_fault_lessons(sig, limit=2)
    if not lessons:
        return ""
    
    wisdom = ["\n[PRIOR WISDOM — 你老早就有解答]"]
    for l in lessons:
        content = l.get("content", {})
        wisdom.append(f"- 教訓: {content.get('lesson')}")
        wisdom.append(f"  建議策略: {content.get('repair_patch')}")
    
    return "\n".join(wisdom)


def _deep_breath(failure_context: str, root_path: Path) -> str:
    """🧘 [DeepBreath] Pause and observe — global grep for error signatures."""
    sig = None
    for line in failure_context.splitlines():
        if "error" in line.lower() or "fail" in line.lower():
            # Skip the generic prefix and find the next symbol
            words = re.findall(r'([a-zA-Z_][a-zA-Z0-9_\-./]{3,})', line)
            generic_keywords = [
                "ERROR", "FAILED", "FAIL", "EXCEPTION", "ASSERTIONERROR",
                "MODULENOTFOUNDERROR", "IMPORTERROR", "NAMEERROR", "TYPEERROR",
                "VALUEERROR", "INDEXERROR", "KEYERROR", "FILENOTFOUNDERROR",
                "RUNTIMEERROR", "ATTRIBUTEERROR", "NOTIMPLEMENTEDERROR",
                "MODULE", "NAMED", "INITIALIZE"
            ]
            for word in words:
                if word.upper() not in generic_keywords:
                    sig = word
                    break
            if sig: break
    
    if not sig or len(sig) < 4:
        return ""
    
    print(f"🧘 [DeepBreath] Observing global context for: {sig}")
    try:
        # Grep for the symbol, excluding common junk
        cmd = ["grep", "-rn", sig, str(root_path), "--include=*.py", "--include=*.rs", "--max-count=10"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.stdout:
            obs = ["\n[OBSERVATION CONTEXT — 深呼吸觀察所得]"]
            obs.append(f"全庫搜索結果 ({sig}):")
            obs.append(res.stdout[:2000])  # Limit size
            return "\n".join(obs)
    except Exception as e:
        print(f"⚠️ [DeepBreath] Observation failed: {e}")
    
    return ""


@nexus_metabolize(task_name="Autonomous Repair Loop")
def run_repair_loop():
    print("🧠 [Autonomous-Repair] Initializing ReAct Healing Cycle...")

    guard = RollbackGuard(ROOT)
    guard.capture_state()
    
    mem = MemoryService(str(ROOT))
    repair_history = []
    current_round = 1

    while current_round <= MAX_ROUNDS:
        print(f"\n🌀 [Round {current_round}/{MAX_ROUNDS}] Starting repair attempt...")

        if not SUMMARY_FILE.exists():
            print("✅ No failure summary found. System appears healthy.")
            break

        failure_context = SUMMARY_FILE.read_text(encoding="utf-8")

        # 1. Recall prior wisdom (Phase 9: Anamnesis)
        wisdom = _recall_prior_wisdom(failure_context, mem)

        # 2. Construct the Repair Prompt
        prompt = (
            "NEXUS AUTONOMOUS REPAIR MISSION\n"
            f"{wisdom}\n\n"
            "The system failed a CI check. Here is the context:\n"
            f"{failure_context}\n\n"
            "GOAL: Fix the issue identified in the STDERR.\n"
        )
        
        if repair_history:
            prompt += "\n[RECENT ATTEMPTS (Failure History)]\n"
            for i, h in enumerate(repair_history[-2:]):
                prompt += f"- Attempt {i+1}: {h}\n"
            prompt += "⚠️ 注意：以上嘗試已驗證無效，請更換思路、深挖 Root Cause。\n"

        prompt += (
            "\nINSTRUCTIONS:\n"
            "- Output ONLY the shell commands required to fix it, one per line.\n"
            "- Do not explain yourself.\n"
            "- Focus on minimal, precise changes.\n"
        )

        if current_round >= ROLLBACK_TRIGGER_ROUND:
            print(
                f"🚨 [Round {current_round}] Persistence detected. "
                "Triggering Deep Breath & Observation..."
            )
            if current_round == ROLLBACK_TRIGGER_ROUND:
                guard.reset_to_head()
                prompt += "\nNOTE: Last attempts failed. Environment has been restored.\n"
            
            obs = _deep_breath(failure_context, ROOT)
            prompt += f"{obs}\n"
            prompt += "⚠️ 注意：你已進入「深呼吸模式」。請基於觀察結果而非猜測進行修復。\n"
            
        # 3. Invoke Gemini for Fixes
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
        strategy_summary = "; ".join([c for c in repair_commands if not c.startswith("#")])[:200]
        repair_history.append(strategy_summary)

        # 4. Execute Repairs
        print(f"🛠️ Executing {len(repair_commands)} repair commands...")
        for cmd in repair_commands:
            if cmd.strip() and not cmd.startswith("#"):
                print(f"  > {cmd}")
                subprocess.run(cmd, shell=True, cwd=str(ROOT))

        # 5. Verify with CI Gate (Dry-run)
        print("🔎 Verifying repair...")
        verify_cmd = [str(VENV_PYTHON), str(CI_GATE_SCRIPT), "--dry-run"]
        v_res = subprocess.run(verify_cmd)

        if v_res.returncode == 0:
            print(f"🎉 [SUCCESS] System repaired in {current_round} round(s)!")
            # 閉環：記錄成功的教訓
            new_lesson = FaultLesson(
                fault_hash=failure_context[:50],  # Simple hash proxy
                error_type="healing_success",
                diagnosis_kind="R",
                lesson=f"Round {current_round} success",
                repair_patch=strategy_summary,
                audit_pass_rate=1.0
            )
            mem.record_fault_lesson(new_lesson)
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
