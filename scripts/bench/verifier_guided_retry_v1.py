#!/usr/bin/env python3
"""
Verifier-guided retry minimal loop v1
處理 3 個 VERIFIER_REJECTION_BEHAVIORAL cases
"""

import json
import ast
import subprocess
import sys
import os
import tempfile
import requests
from pathlib import Path
from datetime import datetime

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
WORKSPACE = NEXUS_ROOT / ".nexus/workspaces/astropy"
VENV_PYTHON = str(NEXUS_ROOT / ".venv_astropy/bin/python")
OLLAMA_URL = "http://localhost:11434/api/generate"
OUTPUT_DIR = NEXUS_ROOT / "artifacts/runtime/advisor_evidence_v4"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RESULTS_PATH = OUTPUT_DIR / "verifier_guided_retry_results_v1.jsonl"

# ── 3 failed cases ──────────────────────────────────────────────────────────
CASES = [
    {
        "task_id": "astropy__astropy-13236",
        "model": "qwen2.5-coder:7b",
        "verifier_command": f"{VENV_PYTHON} -m pytest astropy/table/tests/test_column.py::TestColumn::test_quantity_comparison -x -q --tb=short",
        "target_file": "astropy/table/column.py",
        "target_symbol": "_make_compare / _compare",
        "abbreviated_traceback": (
            "[ERROR_TYPE]: UnitConversionError\n"
            "[MESSAGE]: Can only apply 'greater' function to dimensionless quantities when other argument is not a quantity\n"
            "[MINIMIZED_STACK]:\n"
            "  - file: astropy/table/column.py:329, in _compare\n"
            "  - file: astropy/units/quantity_helper/converters.py:192, in converters_and_unit\n"
            "[VERDICT]: FAILED (behavioral_rejection)"
        ),
        "input_failure_reason": "UnitConversionError in _compare when comparing Column with unit quantity",
    },
    {
        "task_id": "astropy__astropy-13236",
        "model": "qwen2.5-coder:14b-instruct-q3_K_M",
        "verifier_command": f"{VENV_PYTHON} -m pytest astropy/table/tests/test_column.py::TestColumn::test_quantity_comparison -x -q --tb=short",
        "target_file": "astropy/table/column.py",
        "target_symbol": "_make_compare / _compare",
        "abbreviated_traceback": (
            "[ERROR_TYPE]: UnitConversionError\n"
            "[MESSAGE]: Can only apply 'greater' function to dimensionless quantities when other argument is not a quantity\n"
            "[MINIMIZED_STACK]:\n"
            "  - file: astropy/table/column.py:329, in _compare\n"
            "  - file: astropy/units/quantity_helper/converters.py:192, in converters_and_unit\n"
            "[VERDICT]: FAILED (behavioral_rejection)"
        ),
        "input_failure_reason": "UnitConversionError in _compare when comparing Column with unit quantity",
    },
    {
        "task_id": "astropy__astropy-14182",
        "model": "qwen2.5-coder:14b-instruct-q3_K_M",
        "verifier_command": f"{VENV_PYTHON} -m pytest astropy/coordinates/tests/test_geodetic_representations.py::test_cartesian_wgs84geodetic_roundtrip -x -q --tb=short",
        "target_file": "astropy/coordinates/representation.py",
        "target_symbol": "CartesianRepresentation.get_xyz",
        "abbreviated_traceback": (
            "[ERROR_TYPE]: TypeError\n"
            "[MESSAGE]: concatenate() got an unexpected keyword argument 'dtype'\n"
            "[MINIMIZED_STACK]:\n"
            "  - file: astropy/coordinates/representation.py:1351, in get_xyz\n"
            "  - file: astropy/units/quantity.py:1680, in __array_function__\n"
            "  - file: numpy/core/shape_base.py:456, in stack\n"
            "[VERDICT]: FAILED (behavioral_rejection)"
        ),
        "input_failure_reason": "np.stack() in get_xyz passes dtype kwarg not supported by numpy 1.26 Quantity.__array_function__",
    },
]

# ── Source anchors ──────────────────────────────────────────────────────────
SOURCE_ANCHORS = {
    "astropy__astropy-13236": {
        "file": "astropy/table/column.py",
        "span_start": 289,
        "span_end": 334,
        "code": open(WORKSPACE / "astropy/table/column.py").readlines()[288:334],
    },
    "astropy__astropy-14182": {
        "file": "astropy/coordinates/representation.py",
        "span_start": 1327,
        "span_end": 1353,
        "code": open(WORKSPACE / "astropy/coordinates/representation.py").readlines()[1326:1353],
    },
}

# ── Test context ─────────────────────────────────────────────────────────────
TEST_CONTEXTS = {
    "astropy__astropy-13236": """# Failing test (test_column.py:157-165):
    def test_quantity_comparison(self, Column):
        # regression test for gh-6532
        c = Column([1, 2100, 3], unit='Hz')
        q = 2 * u.kHz
        check = c < q
        assert np.all(check == [True, False, True])
        check = q >= c
        assert np.all(check == [True, False, True])
""",
    "astropy__astropy-14182": """# Failing test (test_geodetic_representations.py:18-42):
    def test_cartesian_wgs84geodetic_roundtrip():
        s1 = CartesianRepresentation(x=[1, 3000.] * u.km, y=[7000., 4.] * u.km, z=[5., 6000.] * u.km)
        s2 = WGS84GeodeticRepresentation.from_representation(s1)
        s3 = CartesianRepresentation.from_representation(s2)
        # ... roundtrip asserts
    # The error occurs in get_xyz() when it calls np.stack([self._x, self._y, self._z], axis=xyz_axis)
    # np.stack passes 'dtype' kwarg internally which Quantity.__array_function__ rejects
""",
}


def read_source_anchor(task_id, anchor):
    lines = anchor["code"]
    numbered = "".join(f"{anchor['span_start'] + i}: {l}" for i, l in enumerate(lines))
    return numbered


def build_retry_prompt(case, anchor):
    task_id = case["task_id"]
    source_code = read_source_anchor(task_id, anchor)
    test_ctx = TEST_CONTEXTS[task_id]

    num_ctx = 4096 if "7b" in case["model"] else 6144

    prompt = f"""You are a Python bug-fix specialist. Fix ONLY the behavioral failure described below.

TASK ID: {task_id}
TARGET FILE: {case["target_file"]}
TARGET SYMBOL: {case["target_symbol"]}

## ABBREVIATED TRACEBACK (do not use full traceback)
{case["abbreviated_traceback"]}

## FAILING TEST CONTEXT
{test_ctx}

## CURRENT SOURCE (lines {anchor["span_start"]}-{anchor["span_end"]})
```python
{source_code}
```

## INSTRUCTION
Output ONLY a unified diff patch that fixes the behavioral failure.
- Fix ONLY the function shown above.
- Do NOT rewrite unrelated code.
- Do NOT add imports unless strictly required.
- The diff MUST apply cleanly to the file shown above.
- Output format: standard unified diff with --- a/... and +++ b/... headers.
- Do NOT output explanations, only the diff block.

```diff
"""
    return prompt, num_ctx


def call_ollama(model, prompt, num_ctx):
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": num_ctx,
            "num_predict": 1024,
            "temperature": 0.0,
        }
    }
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=180)
        r.raise_for_status()
        return r.json().get("response", "")
    except Exception as e:
        return f"ERROR: {e}"


def extract_diff(raw_response):
    """Extract unified diff from model response."""
    lines = raw_response.split("\n")
    in_diff = False
    diff_lines = []
    for line in lines:
        if line.startswith("---") or line.startswith("diff --git"):
            in_diff = True
        if in_diff:
            # stop at closing code fence
            if line.strip() == "```" and diff_lines:
                break
            diff_lines.append(line)
    return "\n".join(diff_lines).strip()


def apply_patch_and_test(case, diff_text, patch_suffix):
    """Write patch, apply, check syntax, run verifier. Returns result dict."""
    task_id = case["task_id"]
    target_rel = case["target_file"]
    target_abs = WORKSPACE / target_rel

    # Save patch
    patch_dir = OUTPUT_DIR / "patches"
    patch_dir.mkdir(exist_ok=True)
    safe_task = task_id.replace("/", "_").replace(":", "_")
    safe_model = case["model"].replace(":", "_").replace("/", "_")
    patch_path = patch_dir / f"{safe_task}__{safe_model}__{patch_suffix}.diff"
    patch_path.write_text(diff_text)

    # Backup original
    original_src = target_abs.read_text()

    # Try applying patch via patch command
    patch_apply_pass = False
    apply_error = ""
    try:
        result = subprocess.run(
            ["patch", "-p0", "--dry-run", "-i", str(patch_path)],
            cwd=WORKSPACE,
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            # Apply for real
            subprocess.run(
                ["patch", "-p0", "-i", str(patch_path)],
                cwd=WORKSPACE,
                capture_output=True, text=True, timeout=15
            )
            patch_apply_pass = True
        else:
            apply_error = result.stderr + result.stdout
            # Try p1
            result2 = subprocess.run(
                ["patch", "-p1", "--dry-run", "-i", str(patch_path)],
                cwd=WORKSPACE,
                capture_output=True, text=True, timeout=15
            )
            if result2.returncode == 0:
                subprocess.run(
                    ["patch", "-p1", "-i", str(patch_path)],
                    cwd=WORKSPACE,
                    capture_output=True, text=True, timeout=15
                )
                patch_apply_pass = True
            else:
                apply_error = result2.stderr + result2.stdout
    except Exception as e:
        apply_error = str(e)

    if not patch_apply_pass:
        return {
            "patch_apply_pass": False,
            "syntax_pass": False,
            "verifier_exit_code": -1,
            "verifier_pass": False,
            "failure_class_after_retry": "PATCH_APPLY_FAIL",
            "failure_reason_after_retry": apply_error[:300],
            "abbreviated_traceback_after_retry": f"[PATCH_APPLY_FAIL]: {apply_error[:200]}",
            "patch_path_after": str(patch_path),
        }

    # Syntax check
    new_src = target_abs.read_text()
    syntax_pass = False
    syntax_error = ""
    try:
        ast.parse(new_src)
        syntax_pass = True
    except SyntaxError as e:
        syntax_error = str(e)
        # Restore
        target_abs.write_text(original_src)
        return {
            "patch_apply_pass": True,
            "syntax_pass": False,
            "verifier_exit_code": -1,
            "verifier_pass": False,
            "failure_class_after_retry": "SYNTAX_INVALID",
            "failure_reason_after_retry": syntax_error,
            "abbreviated_traceback_after_retry": f"[SYNTAX_INVALID]: {syntax_error}",
            "patch_path_after": str(patch_path),
        }

    # Run verifier
    ver_result = subprocess.run(
        case["verifier_command"].split(),
        cwd=WORKSPACE,
        capture_output=True, text=True, timeout=120
    )
    exit_code = ver_result.returncode
    stdout = ver_result.stdout + ver_result.stderr

    # Restore original regardless of result (keep workspace clean)
    target_abs.write_text(original_src)

    verifier_pass = (exit_code == 0)
    if verifier_pass:
        failure_class = "VERIFIED_SOLVE"
        failure_reason = None
        abbrv_trace = "[VERDICT]: PASSED"
    else:
        failure_class = "VERIFIER_REJECTION_BEHAVIORAL"
        # Extract key lines
        lines = stdout.strip().split("\n")
        key_lines = [l for l in lines if any(k in l for k in ["FAILED", "Error", "assert", "E "])][-5:]
        abbrv_trace = "\n".join(key_lines) if key_lines else stdout[-300:]
        failure_reason = abbrv_trace[:300]

    return {
        "patch_apply_pass": True,
        "syntax_pass": True,
        "verifier_exit_code": exit_code,
        "verifier_pass": verifier_pass,
        "failure_class_after_retry": failure_class,
        "failure_reason_after_retry": failure_reason,
        "abbreviated_traceback_after_retry": abbrv_trace[:500],
        "patch_path_after": str(patch_path),
    }


def main():
    results = []
    consecutive_hard_fails = 0

    for i, case in enumerate(CASES):
        task_id = case["task_id"]
        model = case["model"]
        print(f"\n{'='*60}")
        print(f"[{i+1}/3] {task_id} / {model}")
        print(f"{'='*60}")

        anchor = SOURCE_ANCHORS[task_id]
        prompt, num_ctx = build_retry_prompt(case, anchor)

        print(f"  → Calling {model} (num_ctx={num_ctx})...")
        raw = call_ollama(model, prompt, num_ctx)

        if raw.startswith("ERROR:"):
            print(f"  ✗ Ollama error: {raw}")
            result = {
                "task_id": task_id,
                "model": model,
                "retry_round": 1,
                "input_failure_class": "VERIFIER_REJECTION_BEHAVIORAL",
                "input_failure_reason": case["input_failure_reason"],
                "used_abbreviated_traceback": True,
                "patch_path_before": "N/A",
                "patch_path_after": "N/A",
                "patch_apply_pass": False,
                "syntax_pass": False,
                "verifier_command": case["verifier_command"],
                "verifier_exit_code": -1,
                "verifier_pass": False,
                "failure_class_after_retry": "PATCH_APPLY_FAIL",
                "failure_reason_after_retry": raw,
                "abbreviated_traceback_after_retry": raw[:300],
                "full_trace_path_after_retry": None,
            }
            results.append(result)
            consecutive_hard_fails += 1
            if consecutive_hard_fails >= 2:
                print("  ✗ Stop condition: 2 consecutive hard fails")
                break
            continue

        diff_text = extract_diff(raw)
        print(f"  → Extracted diff ({len(diff_text)} chars)")

        if not diff_text or len(diff_text) < 20:
            print("  ✗ No valid diff extracted")
            result = {
                "task_id": task_id,
                "model": model,
                "retry_round": 1,
                "input_failure_class": "VERIFIER_REJECTION_BEHAVIORAL",
                "input_failure_reason": case["input_failure_reason"],
                "used_abbreviated_traceback": True,
                "patch_path_before": "N/A",
                "patch_path_after": "N/A",
                "patch_apply_pass": False,
                "syntax_pass": False,
                "verifier_command": case["verifier_command"],
                "verifier_exit_code": -1,
                "verifier_pass": False,
                "failure_class_after_retry": "PATCH_APPLY_FAIL",
                "failure_reason_after_retry": "No valid diff extracted from model output",
                "abbreviated_traceback_after_retry": raw[:300],
                "full_trace_path_after_retry": None,
            }
            results.append(result)
            consecutive_hard_fails += 1
            if consecutive_hard_fails >= 2:
                print("  ✗ Stop condition: 2 consecutive hard fails")
                break
            continue

        print(f"  → Applying patch and running verifier...")
        test_result = apply_patch_and_test(case, diff_text, f"retry_v1")
        print(f"  → Result: {test_result['failure_class_after_retry']}")

        full_result = {
            "task_id": task_id,
            "model": model,
            "retry_round": 1,
            "input_failure_class": "VERIFIER_REJECTION_BEHAVIORAL",
            "input_failure_reason": case["input_failure_reason"],
            "used_abbreviated_traceback": True,
            "patch_path_before": "N/A (no prior successful patch)",
            "patch_path_after": test_result["patch_path_after"],
            "patch_apply_pass": test_result["patch_apply_pass"],
            "syntax_pass": test_result["syntax_pass"],
            "verifier_command": case["verifier_command"],
            "verifier_exit_code": test_result["verifier_exit_code"],
            "verifier_pass": test_result["verifier_pass"],
            "failure_class_after_retry": test_result["failure_class_after_retry"],
            "failure_reason_after_retry": test_result["failure_reason_after_retry"],
            "abbreviated_traceback_after_retry": test_result["abbreviated_traceback_after_retry"],
            "full_trace_path_after_retry": None,
        }
        results.append(full_result)

        fc = test_result["failure_class_after_retry"]
        if fc in ("SYNTAX_INVALID", "PATCH_APPLY_FAIL"):
            consecutive_hard_fails += 1
        else:
            consecutive_hard_fails = 0

        if consecutive_hard_fails >= 2:
            print("  ✗ Stop condition: 2 consecutive hard fails")
            break

    # Write JSONL
    with open(RESULTS_PATH, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    print(f"\n{'='*60}")
    print(f"Results written to: {RESULTS_PATH}")
    attempted = len(results)
    solved = sum(1 for r in results if r["verifier_pass"])
    hard_fails = sum(1 for r in results if r["failure_class_after_retry"] in ("SYNTAX_INVALID", "PATCH_APPLY_FAIL"))
    print(f"Attempted: {attempted}/3")
    print(f"VERIFIED_SOLVE: {solved}")
    print(f"Hard fails (SYNTAX/PATCH_APPLY): {hard_fails}")

    return results


if __name__ == "__main__":
    results = main()
