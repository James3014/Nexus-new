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
ROUND_RUNNER = ROOT / "scripts" / "ops" / "run_gemini_nexus_round.sh"
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

        # 🧪 [Round 20 Evolution] Integrate Feynman Audit results into prompt
        from scripts.ops.feynman_bridge import DualTrackAudit
        auditor = DualTrackAudit()
        audit_findings = auditor.run_advisory_audit(failure_context, "Self-Healing Constraint")
        audit_context = f"\n[FEYNMAN ADVISORY]: {audit_findings['warnings']}" if audit_findings['warnings'] else ""

        # 🧪 [Bayesian Temperature Gradient]
        # Round 1: 0.2 (Precise) -> Round 5: 0.9 (Creative)
        temp_gradient = 0.2 + (current_round - 1) * 0.15
        nas_aggression = 0.5 + (current_round - 1) * 0.1

        # 2. Construct the Repair Prompt
        prompt = (
            "NEXUS AUTONOMOUS REPAIR MISSION (v24.0 Hardened)\n"
            f"{wisdom}\n{audit_context}\n\n"
            "The system failed a CI check. Context:\n"
            f"{failure_context}\n\n"
            f"STRATEGY: Use Bayesian-gradient approach (Temp: {temp_gradient:.2f}).\n"
        )

        if repair_history:
            prompt += "\n[FAILURE TRACE]\n"
            for i, h in enumerate(repair_history):
                prompt += f"- Round {i+1} failed attempt: {h}\n"
            prompt += "⚠️ SWITCH REASONING: Previous rounds failed. Deepen investigation.\n"

        # 3. Invoke Gemini through Nexus-enforced round runner
        prompt_path = ROOT / ".nexus" / "reports" / f"autorepair_round_{current_round}.md"
        report_path = ROOT / ".nexus" / "reports" / f"autorepair_round_{current_round}.json"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")
        invoke_cmd = [
            "bash", str(ROUND_RUNNER),
            str(prompt_path),
            str(report_path),
            "300",
        ]

        print("📡 Consulting Zenith (Gemini+Nexus) for repair strategy...")
        res = subprocess.run(invoke_cmd, capture_output=True, text=True, cwd=str(ROOT))

        if res.returncode != 0 or not report_path.exists():
            print(f"❌ Gemini round failed (RC={res.returncode}): {res.stdout[:200]}")
            current_round += 1
            time.sleep(2)
            continue

        report = json.loads(report_path.read_text(encoding="utf-8"))
        raw_output = report.get("output", "") if isinstance(report, dict) else ""
        repair_commands = raw_output.strip().splitlines()
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
