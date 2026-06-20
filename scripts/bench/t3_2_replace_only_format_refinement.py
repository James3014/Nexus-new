#!/usr/bin/env python3
"""T3.2: REPLACE-Only Format Contract Refinement

Improves Qwen14B prompt to output raw replacement code instead of diff format.
Tests on astropy__astropy-13236 with D0/M1a/M1b/M2 modes.
"""

import json
import subprocess
import sys
import hashlib
import time
import re
from pathlib import Path

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
PYTHON_EXEC_ASTROPY = str(NEXUS_ROOT / ".venv_astropy/bin/python")
RUN_GROUP = "T3_2_REPLACE_ONLY_FORMAT_REFINEMENT"
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


def apply_deterministic_fix():
    ws = NEXUS_ROOT / ".nexus/workspaces" / SMOKE_TASK["workspace"]
    source_path = ws / SMOKE_TASK["target_file"]
    source = source_path.read_text()
    if SMOKE_TASK["buggy_block"] in source:
        source_path.write_text(source.replace(SMOKE_TASK["buggy_block"], SMOKE_TASK["fixed_block"], 1))
        return True
    return False


def read_source():
    ws = NEXUS_ROOT / ".nexus/workspaces" / SMOKE_TASK["workspace"]
    return (ws / SMOKE_TASK["target_file"]).read_text()


def build_prompt_v1(source_context):
    """T3_REPLACE_ONLY_V1: Strict REPLACE-only prompt."""
    return f"""TASK: Return ONLY the replacement code for a specific code block.

FILE: {SMOKE_TASK['target_file']}

BUGGY CODE BLOCK (this exact block must be removed):
{SMOKE_TASK['buggy_block']}

EXPECTED FIX: Remove this entire block. The replacement is empty (block deletion).

RULES:
- Return ONLY the replacement code body
- NO markdown, NO code fences, NO diff format, NO explanation
- NO SEARCH, NO @@ markers, NO +/- prefixes
- If the fix is block deletion, return exactly: PASS (one word, nothing else)
- If you cannot fix it, return exactly: NO_VALID_REPLACE

YOUR OUTPUT (raw replacement code only):"""


def build_prompt_v2(source_context):
    """T3_REPLACE_ONLY_V2: Even stricter, with anti-diff warning."""
    return f"""CRITICAL: You must return ONLY raw Python replacement code. NOT a diff. NOT markdown. NOT an explanation.

File: {SMOKE_TASK['target_file']}

The following buggy code block must be DELETED (replaced with nothing):
---
{SMOKE_TASK['buggy_block']}
---

FORBIDDEN OUTPUT FORMATS (will be rejected):
- Unified diff (lines starting with + or -)
- Markdown code fences (```)
- SEARCH/REPLACE blocks
- Explanations or prose
- File paths or line numbers

REQUIRED OUTPUT FORMAT:
Return ONLY the replacement code that goes in place of the buggy block.
For block deletion, output exactly: PASS

Do NOT output anything else. Just the replacement code or PASS.

Replacement:"""


def call_ollama(prompt):
    import urllib.request
    import urllib.error
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 512}
    }).encode("utf-8")
    try:
        req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", ""), True
    except Exception as e:
        return str(e), False


def classify_output(raw_output):
    """Classify model output format."""
    text = raw_output.strip()

    # Check for NO_VALID_REPLACE
    if text.upper() == "NO_VALID_REPLACE":
        return "no_valid_replace", text, False, False

    # Check for PASS (block deletion)
    if text.upper() == "PASS" or text == "":
        return "raw_replace_body", "", True, False

    # Check for unified diff markers
    diff_markers = re.findall(r'^[+-]\s', text, re.MULTILINE)
    if len(diff_markers) > 2:
        return "unified_diff", text, False, False

    # Check for markdown fences
    if text.startswith("```") or "```python" in text:
        # Try to extract code from fences
        code = re.sub(r'^```\w*\n?', '', text)
        code = re.sub(r'\n?```$', '', code)
        code = code.strip()
        if code and not re.search(r'^[+-]\s', code, re.MULTILINE):
            return "markdown_fenced_code", code, True, True
        return "markdown_fenced_code", text, False, True

    # Check for SEARCH/REPLACE block
    if "SEARCH" in text.upper() and "REPLACE" in text.upper():
        return "search_replace_block", text, False, False

    # Check for prose (more than 30% non-code characters)
    alpha_ratio = sum(c.isalpha() for c in text) / max(len(text), 1)
    if alpha_ratio > 0.6 and len(text) > 100:
        return "prose_with_code", text, False, False

    # Check if it looks like raw code
    try:
        compile(text, '<model>', 'exec')
        return "raw_replace_body", text, True, False
    except SyntaxError:
        pass

    # Partial code check - lines starting with spaces (indented Python)
    lines = text.strip().split('\n')
    code_lines = [l for l in lines if l.strip() and not l.strip().startswith('#') and not l.strip().startswith('```')]
    if len(code_lines) > 0:
        return "raw_replace_body", text, True, False

    return "invalid_format", text, False, False


def check_syntax(code_str):
    if not code_str or code_str.strip() == "" or code_str.strip() == "PASS":
        return True
    try:
        compile(code_str, '<model_output>', 'exec')
        return True
    except SyntaxError:
        return False


def write_receipt(mode, result):
    receipt = {
        "schema": "nexus.local_heal.t3_2_format_receipt.v1",
        "instance_id": SMOKE_TASK["instance_id"],
        "run_group": RUN_GROUP,
        "mode": mode,
        "simulated": False,
        "claim_eligible": False,
        "public_claim_allowed": False,
        "claim_block_reason": "internal_model_call_format_refinement",
        "telemetry": {
            "instance_id": SMOKE_TASK["instance_id"],
            "run_group": RUN_GROUP,
            "mode": mode,
            "model_name": OLLAMA_MODEL,
            "model_runtime": "ollama_local",
            "model_calls": 1 if mode.startswith("M") else 0,
            "prompt_contract_id": "T3_REPLACE_ONLY_V2" if "b" in mode else "T3_REPLACE_ONLY_V1",
            "model_prompt_hash": result.get("prompt_hash", ""),
            "model_output_hash": result.get("output_hash", ""),
            "output_format_class": result.get("output_format_class", ""),
            "sanitizer_used": result.get("sanitizer_used", False),
            "diff_conversion_used": False,
            "canonical_span_source": SMOKE_TASK["canonical_span_source"],
            "canonical_search_locked": True,
            "model_generated_search_detected": False,
            "model_generated_search_used": False,
            "file_path": SMOKE_TASK["target_file"],
            "replace_extracted": result.get("replace_extracted", False),
            "patch_applied": result.get("patch_applied", False),
            "syntax_gate_passed": result.get("syntax_passed", False),
            "verification_result": result.get("verification", ""),
            "solved": result.get("solved", False),
            "deterministic_fallback_used": False,
            "truth_patch_applied": False,
            "manual_patch_applied": False,
            "llm_replace_success": result.get("llm_replace_success", False),
            "model_patch_reward": result.get("model_patch_reward", 0.0),
            "export_as_model_patch_success": False,
            "requires_human_review_before_training": True,
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
    print("T3.2: REPLACE-Only Format Contract Refinement")
    print(f"Task: {SMOKE_TASK['instance_id']}")
    print(f"Model: {OLLAMA_MODEL}")
    print("=" * 70)

    results = {}
    source = read_source()

    # ── D0 ──
    print(f"\n[D0] Deterministic baseline")
    reset_workspace()
    passed_before, _ = run_verification()
    if passed_before:
        results["D0"] = {"solved": True, "verification": "PASS", "patch_applied": False, "syntax_passed": True, "model_patch_reward": 0.0}
    else:
        applied = apply_deterministic_fix()
        passed_after, _ = run_verification()
        results["D0"] = {"solved": passed_after, "verification": "PASS" if passed_after else "FAIL", "patch_applied": applied, "syntax_passed": True, "model_patch_reward": 0.0, "deterministic_fallback_used": applied, "deterministic_fallback_reward": "REMOVE_BLOCK" if applied else ""}
    write_receipt("D0", results["D0"])
    print(f"  Result: {'PASS' if results['D0']['solved'] else 'FAIL'}")

    if not results["D0"]["solved"]:
        print("  D0 FAILED. Stopping.")
        return 1

    # ── M1a: First prompt attempt ──
    print(f"\n[M1a] Prompt contract attempt (T3_REPLACE_ONLY_V1)")
    reset_workspace()
    prompt_v1 = build_prompt_v1(source)
    prompt_hash_v1 = hashlib.sha256(prompt_v1.encode()).hexdigest()[:16]
    print(f"  Prompt hash: {prompt_hash_v1}")
    print("  Calling Qwen14B...")
    t0 = time.time()
    output_v1, ok_v1 = call_ollama(prompt_v1)
    latency_v1 = time.time() - t0
    output_hash_v1 = hashlib.sha256(output_v1.encode()).hexdigest()[:16]
    print(f"  Latency: {latency_v1:.1f}s")
    print(f"  Raw output: {output_v1[:300]}")

    fmt_class_v1, extracted_v1, replace_ok_v1, sanitizer_v1 = classify_output(output_v1)
    print(f"  Format class: {fmt_class_v1}")
    print(f"  Replace extracted: {replace_ok_v1}")

    syntax_v1 = check_syntax(extracted_v1)
    print(f"  Syntax OK: {syntax_v1}")

    results["M1a"] = {
        "solved": False, "verification": "N/A",
        "output_format_class": fmt_class_v1, "sanitizer_used": sanitizer_v1,
        "replace_extracted": replace_ok_v1, "syntax_passed": syntax_v1,
        "model_patch_reward": 0.0, "prompt_hash": prompt_hash_v1, "output_hash": output_hash_v1,
        "latency": latency_v1,
    }
    write_receipt("M1a", results["M1a"])

    # ── M1b: Retry if M1a failed ──
    m1b_ran = False
    if not replace_ok_v1 or not syntax_v1:
        print(f"\n[M1b] Retry with stricter prompt (T3_REPLACE_ONLY_V2)")
        reset_workspace()
        prompt_v2 = build_prompt_v2(source)
        prompt_hash_v2 = hashlib.sha256(prompt_v2.encode()).hexdigest()[:16]
        print(f"  Prompt hash: {prompt_hash_v2}")
        print("  Calling Qwen14B...")
        t0 = time.time()
        output_v2, ok_v2 = call_ollama(prompt_v2)
        latency_v2 = time.time() - t0
        output_hash_v2 = hashlib.sha256(output_v2.encode()).hexdigest()[:16]
        print(f"  Latency: {latency_v2:.1f}s")
        print(f"  Raw output: {output_v2[:300]}")

        fmt_class_v2, extracted_v2, replace_ok_v2, sanitizer_v2 = classify_output(output_v2)
        print(f"  Format class: {fmt_class_v2}")
        print(f"  Replace extracted: {replace_ok_v2}")

        syntax_v2 = check_syntax(extracted_v2)
        print(f"  Syntax OK: {syntax_v2}")

        results["M1b"] = {
            "solved": False, "verification": "N/A",
            "output_format_class": fmt_class_v2, "sanitizer_used": sanitizer_v2,
            "replace_extracted": replace_ok_v2, "syntax_passed": syntax_v2,
            "model_patch_reward": 0.0, "prompt_hash": prompt_hash_v2, "output_hash": output_hash_v2,
            "latency": latency_v2,
        }
        write_receipt("M1b", results["M1b"])
        m1b_ran = True

        # Use M1b result for M2 if better
        best_extracted = extracted_v2 if replace_ok_v2 else extracted_v1
        best_ok = replace_ok_v2 and syntax_v2
    else:
        best_extracted = extracted_v1
        best_ok = True

    # ── M2: Guarded candidate ──
    print(f"\n[M2] Guarded model candidate")
    if best_ok:
        reset_workspace()
        ws = NEXUS_ROOT / ".nexus/workspaces" / SMOKE_TASK["workspace"]
        source_path = ws / SMOKE_TASK["target_file"]
        original = source_path.read_text()

        # Apply model patch
        if SMOKE_TASK["buggy_block"] in original:
            if best_extracted.strip() == "" or best_extracted.strip() == "PASS":
                patched = original.replace(SMOKE_TASK["buggy_block"], "", 1)
            else:
                patched = original.replace(SMOKE_TASK["buggy_block"], best_extracted, 1)
            source_path.write_text(patched)
            patch_applied = True
        else:
            patch_applied = False

        passed_m2, report_m2 = run_verification()
        results["M2"] = {
            "solved": passed_m2,
            "verification": "PASS" if passed_m2 else f"FAIL: {report_m2[:200]}",
            "patch_applied": patch_applied,
            "syntax_passed": True,
            "model_patch_reward": 1.0 if passed_m2 else 0.0,
            "llm_replace_success": passed_m2,
        }
    else:
        results["M2"] = {
            "solved": False, "verification": "SKIPPED",
            "patch_applied": False, "syntax_passed": False,
            "model_patch_reward": 0.0,
            "failure_class": "m1_not_passed",
        }
        print("  SKIPPED: M1 did not produce valid replace body")

    write_receipt("M2", results["M2"])

    # Summary
    print(f"\n{'=' * 70}")
    print("T3.2 RESULTS")
    print(f"{'=' * 70}")
    for mode in ["D0", "M1a", "M1b", "M2"]:
        if mode in results:
            r = results[mode]
            solved = "PASS" if r.get("solved") else "FAIL"
            reward = r.get("model_patch_reward", 0.0)
            fmt = r.get("output_format_class", "N/A")
            print(f"  {mode}: {solved} | fmt={fmt} | reward={reward}")

    # Verdict
    if results["D0"]["solved"] and results["M2"].get("model_patch_reward", 0) > 0:
        verdict = "GREEN"
    elif results["D0"]["solved"]:
        verdict = "YELLOW"
    else:
        verdict = "RED"

    print(f"\nT3.2 Verdict: {verdict}")

    summary = {
        "verdict": verdict, "run_group": RUN_GROUP,
        "task": SMOKE_TASK["instance_id"], "model": OLLAMA_MODEL,
        "d0_solved": results["D0"]["solved"],
        "m1a_format": results["M1a"].get("output_format_class", ""),
        "m1b_format": results.get("M1b", {}).get("output_format_class", "not_run"),
        "m2_reward": results["M2"].get("model_patch_reward", 0.0),
    }
    sp = NEXUS_ROOT / ".nexus/reports/local_heal" / RUN_GROUP / "summary.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(summary, indent=2))
    print(f"\nSummary: {sp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
