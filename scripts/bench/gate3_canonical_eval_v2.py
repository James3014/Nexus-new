"""N30R-V3 Gate 3 v2: Canonical 3-arm evaluation proof.

Arms:
  Bare        — run_bare_row (direct Ollama, no Nexus armor)
  Adaptive    — run_core_row (planner decides profile)
  Forced_Full — NEXUS_FORCE_FULL_ARMOR=1 + run_core_row

Gate 3 PASS criteria:
  1. All 3 arms return telemetry (no error crash)
  2. Bare arm: solved field present
  3. Adaptive arm: profile_selected not in (unknown, error, MISSING, "")
  4. Forced_Full arm: profile_selected == "FULL" (initial_execution_profile=FULL)
"""
import sys, os, time, json

sys.path.insert(0, "/Users/jameschen/Workspace/nexus-n30r-v3")

TASK = {
    "task_id": "gate3_syntax_easy",
    "tier": "easy",
    "source_relpath": "tests/fixtures/n30r/smoke/syntax_task.py",
    "task_statement": "Fix the syntax error in greet: missing colon after function signature.",
    "verifier_command": ["python3", "-m", "pytest", "-x", "-q"],
}

print("=" * 68)
print("N30R-V3 Gate 3 v2: Canonical 3-arm evaluation")
print(f"Task: {TASK['task_id']}")
print("=" * 68)

from scripts.bench.n30r_v2_runner import run_bare_row, run_core_row

# ── Arm 1: Bare ───────────────────────────────────────────────────────────────
print("\n[1/3] ARM: Bare (direct Ollama, no armor)")
try:
    t0 = time.monotonic()
    row_bare = run_bare_row(task_dict=TASK, seed=42, run_id="gate3_v2_bare")
    row_bare["arm_name"] = "Bare"
    row_bare["elapsed"] = round(time.monotonic() - t0, 2)
    print(f"  terminal_status  : {row_bare.get('terminal_status', 'MISSING')}")
    print(f"  solved           : {row_bare.get('solved')}")
    print(f"  wall_time_sec    : {row_bare.get('wall_time_sec', '?'):.1f}s")
except Exception as e:
    import traceback
    print(f"  ERROR: {e}")
    traceback.print_exc()
    row_bare = {"arm_name": "Bare", "error": str(e), "solved": False,
                "terminal_status": "ERROR", "profile_selected": "error"}

# ── Arm 2: Adaptive ───────────────────────────────────────────────────────────
print("\n[2/3] ARM: Adaptive (planner resolves profile)")
try:
    t0 = time.monotonic()
    row_adaptive = run_core_row(task_dict=TASK, seed=42, run_id="gate3_v2_adaptive")
    row_adaptive["arm_name"] = "Adaptive"
    row_adaptive["elapsed"] = round(time.monotonic() - t0, 2)
    print(f"  solved           : {row_adaptive.get('solved')}")
    print(f"  profile_selected : {row_adaptive.get('profile_selected', 'MISSING')}")
    print(f"  final_profile    : {row_adaptive.get('final_profile', 'MISSING')}")
    print(f"  escalation_count : {row_adaptive.get('escalation_count', 'MISSING')}")
    print(f"  llm_call_total   : {row_adaptive.get('llm_call_total', 'MISSING')}")
    print(f"  wall_time_sec    : {row_adaptive.get('wall_time_sec', '?'):.1f}s")
except Exception as e:
    import traceback
    print(f"  ERROR: {e}")
    traceback.print_exc()
    row_adaptive = {"arm_name": "Adaptive", "error": str(e),
                    "profile_selected": "error", "solved": False}

# ── Arm 3: Forced_Full ────────────────────────────────────────────────────────
print("\n[3/3] ARM: Forced_Full (NEXUS_FORCE_FULL_ARMOR=1)")
TASK_FULL = dict(TASK)
TASK_FULL["task_id"] = "gate3_syntax_forced_full"
os.environ["NEXUS_FORCE_FULL_ARMOR"] = "1"
try:
    t0 = time.monotonic()
    row_full = run_core_row(task_dict=TASK_FULL, seed=43, run_id="gate3_v2_forced_full")
    row_full["arm_name"] = "Forced_Full"
    row_full["elapsed"] = round(time.monotonic() - t0, 2)
    print(f"  solved           : {row_full.get('solved')}")
    print(f"  profile_selected : {row_full.get('profile_selected', 'MISSING')}")
    print(f"  final_profile    : {row_full.get('final_profile', 'MISSING')}")
    print(f"  escalation_count : {row_full.get('escalation_count', 'MISSING')}")
    print(f"  llm_call_total   : {row_full.get('llm_call_total', 'MISSING')}")
    print(f"  wall_time_sec    : {row_full.get('wall_time_sec', '?'):.1f}s")
except Exception as e:
    import traceback
    print(f"  ERROR: {e}")
    traceback.print_exc()
    row_full = {"arm_name": "Forced_Full", "error": str(e),
                "profile_selected": "error", "solved": False}
finally:
    os.environ.pop("NEXUS_FORCE_FULL_ARMOR", None)

# ── Gate 3 Verification ───────────────────────────────────────────────────────
print("\n" + "=" * 68)
print("Gate 3 v2 Verification")
print("=" * 68)

gate_pass = True
evidence = {}

# --- Bare arm check ---
arm_bare = row_bare.get("arm_name", "Bare")
bare_terminal = row_bare.get("terminal_status", "MISSING")
bare_solved = row_bare.get("solved", "MISSING")
bare_error = row_bare.get("error", None)
bare_ok = bare_terminal not in ("ERROR", "MISSING") and bare_error is None
print(f"\n  [Bare]")
print(f"    terminal_status  : {bare_terminal!r}  {'✅' if bare_ok else '❌'}")
print(f"    solved           : {bare_solved}")
if bare_error:
    print(f"    error            : {bare_error}")
evidence["Bare"] = {
    "terminal_status": bare_terminal,
    "solved": bare_solved,
    "elapsed_sec": row_bare.get("elapsed", "?"),
    "telemetry_present": bare_ok,
}
if not bare_ok:
    gate_pass = False

# --- Core arm checks ---
for row in [row_adaptive, row_full]:
    arm = row.get("arm_name", "?")
    ps  = row.get("profile_selected", "error")
    fp  = row.get("final_profile", "?")
    esc = row.get("escalation_count", "?")
    llt = row.get("llm_call_total", "?")
    solved  = row.get("solved", False)
    elapsed = row.get("elapsed", "?")
    error   = row.get("error", None)

    telemetry_ok = ps not in ("unknown", "error", "MISSING", "", None)
    print(f"\n  [{arm}]")
    print(f"    profile_selected : {ps!r}  {'✅' if telemetry_ok else '❌ (telemetry missing)'}")
    print(f"    final_profile    : {fp}")
    print(f"    escalation_count : {esc}")
    print(f"    llm_call_total   : {llt}")
    print(f"    solved           : {solved}")
    print(f"    elapsed          : {elapsed}s")
    if error:
        print(f"    error            : {error}")

    evidence[arm] = {
        "profile_selected": ps, "final_profile": fp,
        "escalation_count": esc, "llm_call_total": llt,
        "solved": solved, "elapsed_sec": elapsed,
        "telemetry_present": telemetry_ok,
    }
    if not telemetry_ok:
        gate_pass = False

# --- Forced_Full must be FULL ---
fp_arm_ps = evidence.get("Forced_Full", {}).get("profile_selected", "?")
if fp_arm_ps == "FULL":
    print(f"\n  ✅ Forced_Full profile_selected = FULL (correct)")
else:
    print(f"\n  ❌ Forced_Full profile_selected = {fp_arm_ps!r} — expected FULL")
    gate_pass = False

# --- Adaptive profile check ---
ap = evidence.get("Adaptive", {}).get("profile_selected", "?")
if ap in ("LITE", "STANDARD", "FULL"):
    print(f"  ✅ Adaptive profile_selected = {ap!r}")
else:
    print(f"  ❌ Adaptive profile_selected = {ap!r} — Gate 3 FAIL")
    gate_pass = False

print("\n" + ("✅ Gate 3 v2 PASS" if gate_pass else "❌ Gate 3 v2 FAIL"))

# ── Save evidence ─────────────────────────────────────────────────────────────
out_path = "/Users/jameschen/.gemini/antigravity/brain/f7ce0d57-66b6-4d03-aa82-ead1108294d5/scratch/gate3_canonical_evidence.json"
with open(out_path, "w") as f:
    json.dump({
        "task": TASK["task_id"],
        "arms": evidence,
        "gate3_pass": gate_pass,
        "version": "v2",
    }, f, indent=2, default=str)
print(f"Evidence saved → {out_path}")
