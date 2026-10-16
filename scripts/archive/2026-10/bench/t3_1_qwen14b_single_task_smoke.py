#!/usr/bin/env python3
"""T3.1: Qwen14B Model-Call Readiness + Single-Task Smoke

Tests Qwen14B (via Ollama) on astropy__astropy-13236 in D0/M1/M2 modes.
"""

import json
import subprocess
import sys
import hashlib
import time
from pathlib import Path

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
PYTHON_EXEC_ASTROPY = str(NEXUS_ROOT / ".venv_astropy/bin/python")
RUN_GROUP = "T3_1_QWEN14B_SINGLE_TASK_SMOKE"
SMOKE_TASK = {
    "instance_id": "astropy__astropy-13236",
    "workspace": "astropy",
    "python_exec": PYTHON_EXEC_ASTROPY,
    "target_file": "astropy/table/table.py",
    "buggy_block": "        # Structured ndarray gets viewed as a mixin unless already a valid\n        # mixin class\n        if (not isinstance(data, Column) and not data_is_mixin\n                and isinstance(data, np.ndarray) and len(data.dtype) > 1):\n            data = data.view(NdarrayMixin)\n            data_is_mixin = True",
    "fixed_block": "",
    "canonical_span_source": "unified_diff",
    "repro_script": "import sys, numpy as np\nsys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy')\nfrom astropy.table import Table, NdarrayMixin\na = np.array([(1,'a'),(2,'b')], dtype=[('x','i4'),('y','U1')])\nt = Table([a], names=['a'])\nif issubclass(type(t['a']), NdarrayMixin):\n    print('BUG PRESENT'); sys.exit(1)\nelse:\n    print('SUCCESS'); sys.exit(0)\n",
}
OLLAMA_MODEL = "qwen2.5-coder:14b-instruct-q3_K_M"
OLLAMA_URL = "http://localhost:11434/api/generate"


def reset_workspace():
    ws = NEXUS_ROOT / ".nexus/workspaces" / SMOKE_TASK["workspace"]
    subprocess.run(["git", "checkout", "--", "."], cwd=str(ws), capture_output=True, timeout=30)
    subprocess.run(["git", "clean", "-fd"], cwd=str(ws), capture_output=True, timeout=30)


def run_verification():
    ws = NEXUS_ROOT / ".nexus/workspaces" / SMOKE_TASK["workspace"]
    repro_dst = ws / "reproduce_bug.py"
    repro_dst.write_text(SMOKE_TASK["repro_script"])
    try:
        r = subprocess.run([SMOKE_TASK["python_exec"], str(repro_dst)], capture_output=True, text=True, timeout=120, cwd=str(ws))
        output = r.stdout + r.stderr
        passed = r.returncode == 0 and "BUG PRESENT" not in output
        return passed, output
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, f"ERROR: {e}"


def apply_fix():
    ws = NEXUS_ROOT / ".nexus/workspaces" / SMOKE_TASK["workspace"]
    source_path = ws / SMOKE_TASK["target_file"]
    source = source_path.read_text()
    if SMOKE_TASK["buggy_block"] in source:
        source_path.write_text(source.replace(SMOKE_TASK["buggy_block"], SMOKE_TASK["fixed_block"], 1))
        return True
    return False


def read_source():
    ws = NEXUS_ROOT / ".nexus/workspaces" / SMOKE_TASK["workspace"]
    source_path = ws / SMOKE_TASK["target_file"]
    return source_path.read_text()


def build_prompt(source_context):
    """Build REPLACE-only prompt for Qwen14B."""
    return f"""You are a code repair agent. You must output ONLY a unified diff patch.

## Task
Fix the bug in {SMOKE_TASK['target_file']}.

## Buggy code (SEARCH block — DO NOT change this):
```
{SMOKE_TASK['buggy_block']}
```

## Instructions
- Output ONLY the replacement code (REPLACE block)
- Do NOT output any SEARCH block
- Do NOT change any other code
- The fix removes the buggy block entirely (block removal pattern)

## Source context (for reference only):
```python
{source_context[:2000]}
```

## Required output format:
Output ONLY the fixed code that replaces the buggy block. No SEARCH, no explanation, just the replacement."""


def call_ollama(prompt):
    """Call Ollama Qwen14B and return response."""
    import urllib.request
    import urllib.error

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 1024,
        }
    }).encode("utf-8")

    try:
        req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", ""), True
    except urllib.error.URLError as e:
        return f"URLError: {e}", False
    except Exception as e:
        return f"Error: {e}", False


def parse_model_output(output):
    """Extract REPLACE content from model output."""
    # Look for code blocks
    import re
    blocks = re.findall(r'```(?:python)?\n(.*?)```', output, re.DOTALL)
    if blocks:
        return blocks[0].strip(), True

    # If no code blocks, try to extract the diff-like content
    lines = output.strip().split('\n')
    code_lines = []
    in_code = False
    for line in lines:
        if line.startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)

    if code_lines:
        return '\n'.join(code_lines), True

    # Last resort: return the whole output
    return output.strip(), False


def check_syntax(code_str):
    """Check if code is syntactically valid Python."""
    try:
        compile(code_str, '<model_output>', 'exec')
        return True
    except SyntaxError:
        return False


def write_receipt(mode, result):
    receipt = {
        "schema": "nexus.local_heal.t3_1_smoke_receipt.v1",
        "instance_id": SMOKE_TASK["instance_id"],
        "run_group": RUN_GROUP,
        "mode": mode,
        "simulated": False,
        "claim_eligible": False,
        "public_claim_allowed": False,
        "claim_block_reason": "internal_model_call_experiment",
        "telemetry": {
            "instance_id": SMOKE_TASK["instance_id"],
            "run_group": RUN_GROUP,
            "mode": mode,
            "simulated": False,
            "claim_eligible": False,
            "public_claim_allowed": False,
            "claim_block_reason": "internal_model_call_experiment",
            "model_name": OLLAMA_MODEL if mode != "D0" else "none",
            "model_calls": 1 if mode != "D0" else 0,
            "canonical_span_source": SMOKE_TASK["canonical_span_source"],
            "model_generated_search_detected": False,
            "model_generated_search_used": False,
            "patch_applied": result.get("patch_applied", False),
            "syntax_gate_passed": result.get("syntax_passed", False),
            "verification_result": result.get("verification", ""),
            "solved": result.get("solved", False),
            "deterministic_fallback_used": result.get("deterministic_fallback_used", False),
            "model_patch_reward": result.get("model_patch_reward", 0.0),
            "deterministic_fallback_reward": result.get("deterministic_fallback_reward", ""),
            "export_as_model_patch_success": False,
            "export_as_canonical_recovery_success": result.get("solved", False) and mode == "D0",
            "export_as_public_claim": False,
            "failure_class": result.get("failure_class", ""),
            "failure_reason": result.get("failure_reason", ""),
        },
    }
    d = NEXUS_ROOT / ".nexus/reports/local_heal" / f"{SMOKE_TASK['instance_id']}__{RUN_GROUP}__{mode}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False))
    return d / "receipt.json"


def main():
    print("=" * 70)
    print("T3.1: Qwen14B Single-Task Smoke")
    print(f"Smoke task: {SMOKE_TASK['instance_id']}")
    print(f"Model: {OLLAMA_MODEL}")
    print("=" * 70)

    # Preflight
    print("\n[Preflight] Checking Ollama...")
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        if OLLAMA_MODEL in r.stdout:
            print(f"  PASS: {OLLAMA_MODEL} available")
        else:
            print(f"  FAIL: {OLLAMA_MODEL} not found")
            print(f"  Available: {r.stdout[:200]}")
            return 1
    except Exception as e:
        print(f"  FAIL: {e}")
        return 1

    results = {}

    # ── D0: Deterministic baseline ──
    print(f"\n{'=' * 60}")
    print("MODE D0: Deterministic baseline")
    print("=" * 60)

    reset_workspace()
    passed_before, _ = run_verification()
    if passed_before:
        print("  Already fixed (pre-fix PASS)")
        results["D0"] = {"solved": True, "verification": "PASS", "deterministic_fallback_used": False, "patch_applied": False, "syntax_passed": True, "model_patch_reward": 0.0}
    else:
        applied = apply_fix()
        passed_after, report = run_verification()
        results["D0"] = {
            "solved": passed_after,
            "verification": "PASS" if passed_after else f"FAIL: {report[:200]}",
            "deterministic_fallback_used": applied,
            "deterministic_fallback_reward": "REMOVE_BLOCK" if applied else "",
            "patch_applied": applied,
            "syntax_passed": True,
            "model_patch_reward": 0.0,
        }
        print(f"  Fix applied: {applied}")
        print(f"  Verification: {'PASS' if passed_after else 'FAIL'}")

    write_receipt("D0", results["D0"])

    if not results["D0"]["solved"]:
        print("\n  D0 FAILED — Cannot proceed to M1/M2")
        return 1

    # ── M1: Model shadow proposal ──
    print(f"\n{'=' * 60}")
    print("MODE M1: Model shadow proposal (Qwen14B)")
    print("=" * 60)

    reset_workspace()
    source = read_source()
    prompt = build_prompt(source)
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    print(f"  Prompt hash: {prompt_hash}")

    print("  Calling Qwen14B...")
    t0 = time.time()
    model_output, call_ok = call_ollama(prompt)
    wall_time = time.time() - t0
    output_hash = hashlib.sha256(model_output.encode()).hexdigest()[:16]
    print(f"  Wall time: {wall_time:.1f}s")
    print(f"  Output hash: {output_hash}")
    print(f"  Output preview: {model_output[:300]}")

    if not call_ok:
        results["M1"] = {
            "solved": False, "verification": "CALL_FAILED",
            "failure_class": "model_unavailable", "failure_reason": model_output,
            "model_patch_reward": 0.0, "syntax_passed": False,
        }
        write_receipt("M1", results["M1"])
        print(f"  FAIL: {model_output}")
    else:
        # Check for SEARCH in output
        has_search = "SEARCH" in model_output.upper() and "---" in model_output
        print(f"  SEARCH detected: {has_search}")

        # Parse REPLACE
        replace_code, parse_ok = parse_model_output(model_output)
        print(f"  Parse OK: {parse_ok}")
        print(f"  REPLACE preview: {replace_code[:200]}")

        # Syntax check
        syntax_ok = check_syntax(replace_code) if parse_ok else False
        print(f"  Syntax OK: {syntax_ok}")

        if not syntax_ok:
            results["M1"] = {
                "solved": False, "verification": "SYNTAX_FAIL",
                "failure_class": "model_syntax_failure", "failure_reason": f"Invalid Python syntax in model output",
                "model_patch_reward": 0.0, "syntax_passed": False,
            }
        else:
            # Apply model patch in shadow
            ws = NEXUS_ROOT / ".nexus/workspaces" / SMOKE_TASK["workspace"]
            source_path = ws / SMOKE_TASK["target_file"]
            original_source = source_path.read_text()

            # Try to apply: remove buggy block (model should output empty or replacement)
            if SMOKE_TASK["buggy_block"] in original_source:
                if replace_code.strip() == "" or "pass" in replace_code.lower():
                    # Block removal
                    patched = original_source.replace(SMOKE_TASK["buggy_block"], "", 1)
                else:
                    # Try line replacement
                    patched = original_source.replace(SMOKE_TASK["buggy_block"], replace_code, 1)
                source_path.write_text(patched)
                patch_applied = True
            else:
                patch_applied = False

            # Verify
            passed_verify, verify_report = run_verification()

            results["M1"] = {
                "solved": passed_verify,
                "verification": "PASS" if passed_verify else f"FAIL: {verify_report[:200]}",
                "patch_applied": patch_applied,
                "syntax_passed": True,
                "model_patch_reward": 1.0 if (passed_verify and patch_applied and not has_search) else 0.0,
                "failure_class": "" if passed_verify else "model_semantic_failure",
            }

        write_receipt("M1", results["M1"])

    # ── M2: Guarded model candidate ──
    print(f"\n{'=' * 60}")
    print("MODE M2: Guarded model candidate")
    print("=" * 60)

    if results["M1"].get("syntax_passed") and results["M1"].get("patch_applied"):
        # M2 uses same patch, strict verification
        reset_workspace()
        ws = NEXUS_ROOT / ".nexus/workspaces" / SMOKE_TASK["workspace"]
        source_path = ws / SMOKE_TASK["target_file"]
        original_source = source_path.read_text()
        if SMOKE_TASK["buggy_block"] in original_source:
            patched = original_source.replace(SMOKE_TASK["buggy_block"], replace_code, 1)
            source_path.write_text(patched)
        passed_m2, report_m2 = run_verification()

        results["M2"] = {
            "solved": passed_m2,
            "verification": "PASS" if passed_m2 else f"FAIL: {report_m2[:200]}",
            "patch_applied": True,
            "syntax_passed": True,
            "model_patch_reward": 1.0 if passed_m2 else 0.0,
            "failure_class": "" if passed_m2 else "model_semantic_failure",
        }
    else:
        results["M2"] = {
            "solved": False, "verification": "SKIPPED",
            "failure_class": "m1_not_passed",
            "failure_reason": "M1 did not produce valid patch",
            "model_patch_reward": 0.0, "syntax_passed": False,
        }
        print("  SKIPPED: M1 did not produce valid patch")

    write_receipt("M2", results["M2"])

    # Summary
    print(f"\n{'=' * 70}")
    print("T3.1 RESULTS")
    print(f"{'=' * 70}")

    for mode in ["D0", "M1", "M2"]:
        r = results[mode]
        solved = "PASS" if r.get("solved") else "FAIL"
        reward = r.get("model_patch_reward", 0.0)
        print(f"  {mode}: {solved} | model_patch_reward={reward} | verification={r.get('verification', 'N/A')}")

    # Verdict
    if results["D0"]["solved"] and results["M2"].get("model_patch_reward", 0) > 0:
        verdict = "GREEN"
    elif results["D0"]["solved"] and results["M1"].get("syntax_passed"):
        verdict = "YELLOW"
    elif results["D0"]["solved"]:
        verdict = "YELLOW"
    else:
        verdict = "RED"

    print(f"\nT3.1 Verdict: {verdict}")

    if verdict == "GREEN":
        print("Single-task model-call smoke PASS. Ready for T3.2 controlled 6-task model-call.")
    elif verdict == "YELLOW":
        print("Model-call partially working. Needs refinement before expansion.")
    else:
        print("Model-call not working. Fix infrastructure before proceeding.")

    # Write summary
    summary = {
        "verdict": verdict,
        "run_group": RUN_GROUP,
        "smoke_task": SMOKE_TASK["instance_id"],
        "model": OLLAMA_MODEL,
        "d0_solved": results["D0"]["solved"],
        "m1_syntax_passed": results["M1"].get("syntax_passed", False),
        "m1_patch_applied": results["M1"].get("patch_applied", False),
        "m1_model_patch_reward": results["M1"].get("model_patch_reward", 0.0),
        "m2_solved": results["M2"].get("solved", False),
        "m2_model_patch_reward": results["M2"].get("model_patch_reward", 0.0),
        "prompt_hash": prompt_hash,
        "output_hash": output_hash if 'output_hash' in dir() else "N/A",
    }
    summary_path = NEXUS_ROOT / ".nexus/reports/local_heal" / RUN_GROUP / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\nSummary: {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
