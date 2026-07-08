"""
M3-M6: Sequential Multi-Model Cascade on C_13453
=================================================
Sequential: 3B → unload → 7B → unload → 12B → unload → verifier
RAM-safe: only one model at a time on 16GB.
"""
import os
import sys
import json
import hashlib
import subprocess
import tempfile
import urllib.request
from pathlib import Path

os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"

WORKSPACE_ROOT = Path("/Users/jameschen/Workspace/nexus")
sys.path.insert(0, str(WORKSPACE_ROOT))

from nexus.services.local_heal.backend_resource_policy import BackendResourcePolicy
from nexus.services.local_heal.structured_verifier_feedback import StructuredVerifierFeedback

# ── Config ───────────────────────────────────────────────────────────────────
OLLAMA_ENDPOINT = "http://localhost:11434"
OUTPUT_DIR = WORKSPACE_ROOT / "artifacts/runtime/m6_multimodel_delta_v0/C_13453"

TASK = {
    "task_id": "C_13453",
    "repo_dir": str(WORKSPACE_ROOT / ".nexus/workspaces/astropy"),
    "base_commit": "19cc804717",
    "target_file": "astropy/io/ascii/html.py",
    "python_executable": str(WORKSPACE_ROOT / ".venv_astropy/bin/python3"),
    "problem_statement": "Table.write with format='ascii.html' ignores the 'formats' parameter.",
    "repro_script": (
        "from astropy.table import Table\n"
        "import sys\n"
        "def test_repro():\n"
        "    t = Table([[1.12345]], names=['a'])\n"
        "    import io\n"
        "    out = io.StringIO()\n"
        "    t.write(out, format='ascii.html', formats={'a': '%.2f'})\n"
        "    html = out.getvalue()\n"
        "    if '<td>1.12</td>' not in html:\n"
        "        raise AssertionError('formats ignored')\n"
        "    print('SUCCESS')\n"
        "if __name__ == '__main__':\n"
        "    try:\n"
        "        test_repro()\n"
        "        sys.exit(0)\n"
        "    except Exception as e:\n"
        "        print(f'FAILURE: {e}')\n"
        "        sys.exit(1)\n"
    ),
    # H2-B corrected anchor
    "anchor_text": (
        "    def write(self, table):\n"
        "        \"\"\"\n"
        "        Return data in ``table`` converted to HTML as a list of strings.\n"
        "        \"\"\""
    ),
    "anchor_span": (342, 348),
    "issue_intent": "output_formatting",
    "issue_keywords": ["format", "html", "table", "write", "formats"],
}

# ── Model configs ────────────────────────────────────────────────────────────
MODELS = {
    "3b": {"name": "qwen2.5:3b", "timeout": 120, "role": "advisory"},
    "7b": {"name": "qwen2.5-coder:7b", "timeout": 180, "role": "generator"},
    "12b": {"name": "gemma4-coder-12b-q4km:latest", "timeout": 300, "role": "fallback"},
}


def ollama_generate(model_name: str, system_prompt: str, user_prompt: str, timeout: int = 180) -> str:
    payload = json.dumps({
        "model": model_name,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_ctx": 4096, "num_predict": 768}
    }).encode()
    try:
        req = urllib.request.Request(
            f"{OLLAMA_ENDPOINT}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data.get("response", "")
    except Exception as e:
        print(f"    ❌ Ollama error: {e}")
        return ""


def ollama_unload(model_name: str):
    """Unload model from memory."""
    try:
        payload = json.dumps({"name": model_name}).encode()
        req = urllib.request.Request(
            f"{OLLAMA_ENDPOINT}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass  # Best effort unload


def run_git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def run_repro(repro_script: str, python_exe: str, repo_dir: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
        f.write(repro_script)
        script_path = f.name
    try:
        res = subprocess.run(
            [python_exe, script_path],
            cwd=repo_dir,
            capture_output=True, text=True, timeout=60
        )
        return res.returncode == 0, (res.stdout + "\n" + res.stderr).strip()
    except Exception as e:
        return False, f"REPRO_ERROR: {e}"
    finally:
        Path(script_path).unlink(missing_ok=True)


def main():
    print("=" * 60)
    print("🏁 M3-M6: Sequential Multi-Model Cascade on C_13453")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── M2: Resource Guard Check ─────────────────────────────────────────────
    print("\n=== M2: Resource Guard Check ===")
    policy = BackendResourcePolicy()
    for model_key, model_cfg in MODELS.items():
        allowed, reason = policy.validate_execution(model_cfg["name"])
        print(f"  {model_key} ({model_cfg['name']}): {'ALLOWED' if allowed else 'BLOCKED'} — {reason}")

    # ── Checkout and verify ──────────────────────────────────────────────────
    print("\n=== Setup: Checkout and Verify ===")
    run_git(["checkout", "--", "."], TASK["repo_dir"])
    run_git(["clean", "-fd"], TASK["repo_dir"])
    run_git(["checkout", TASK["base_commit"]], TASK["repo_dir"])

    source_text = Path(TASK["repo_dir"]) / TASK["target_file"]
    source_text = source_text.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(source_text.encode()).hexdigest()[:16]
    print(f"  Source hash: {source_hash}")

    # Verify anchor exists
    anchor = TASK["anchor_text"]
    anchor_count = source_text.count(anchor)
    print(f"  Anchor found {anchor_count}x")
    if anchor_count != 1:
        print("  ❌ Anchor not found or ambiguous!")
        return

    # Verify bug exists
    print("  Running baseline repro...")
    baseline_ok, baseline_log = run_repro(TASK["repro_script"], TASK["python_executable"], TASK["repo_dir"])
    print(f"  Baseline: {'PASS' if baseline_ok else 'FAIL (bug confirmed)'}")

    # ── M3: 3B Advisory Preflight ────────────────────────────────────────────
    print("\n=== M3: 3B Advisory Preflight ===")
    advisory = {}
    if policy.is_allowed(MODELS["3b"]["name"]):
        system_3b = (
            "You are a bug analysis assistant. Analyze the bug and output JSON.\n"
            "Do NOT write code. Do NOT write patches.\n"
            "Output ONLY valid JSON with these fields:\n"
            "- issue_intent: string\n"
            "- anchor_category: string\n"
            "- confidence: float 0-1\n"
            "- should_try_7b: bool\n"
            "- should_abstain: bool\n"
            "- rationale_short: string"
        )
        user_3b = (
            f"Bug: {TASK['problem_statement']}\n"
            f"Issue intent: {TASK['issue_intent']}\n"
            f"Anchor: write method at L342-L456 in HTML class\n"
            f"Repro: formats parameter ignored in HTML output\n\n"
            "Analyze and output JSON only:"
        )
        print("  Loading 3B...")
        response_3b = ollama_generate(MODELS["3b"]["name"], system_3b, user_3b, timeout=120)
        print(f"  3B response: {len(response_3b)} chars")

        # Parse advisory
        try:
            advisory = json.loads(response_3b)
            print(f"  Advisory: intent={advisory.get('issue_intent')}, confidence={advisory.get('confidence')}")
        except json.JSONDecodeError:
            print(f"  ⚠️ 3B output not valid JSON, using defaults")
            advisory = {"issue_intent": "output_formatting", "confidence": 0.5, "should_try_7b": True}

        # Unload 3B
        print("  Unloading 3B...")
        ollama_unload(MODELS["3b"]["name"])
    else:
        print("  3B not allowed, skipping")

    (OUTPUT_DIR / "3b_advisory.json").write_text(json.dumps(advisory, indent=2))

    # ── M4: 7B Narrow Candidate Generation ───────────────────────────────────
    print("\n=== M4: 7B Narrow Candidate Generation ===")
    sevenb_results = []
    sevenb_selected = None

    if policy.is_allowed(MODELS["7b"]["name"]):
        system_7b = (
            "You are fixing a Python bug with a MINIMAL, PRECISE change.\n\n"
            "RULES:\n"
            "1. Output ONLY raw Python code (max 12 lines)\n"
            "2. NEVER wrap in ```python ... ``` fences\n"
            "3. NEVER add explanation\n"
            "4. Preserve exact indentation\n"
            "5. Change ONLY what fixes the bug\n"
            "6. If uncertain, output: ABSTAIN\n"
        )

        for i in range(3):
            user_7b = (
                f"Bug: {TASK['problem_statement']}\n\n"
                f"Symbol: HTML.write\n"
                f"Issue: formats parameter ignored in HTML output\n"
                f"Fix: apply column format before iter_str_vals\n\n"
                f"Code to replace:\n{anchor}\n\n"
                f"Output ONLY replacement code (raw Python, no markdown):"
            )
            print(f"  Loading 7B (candidate {i+1}/3)...")
            response_7b = ollama_generate(MODELS["7b"]["name"], system_7b, user_7b, timeout=180)
            print(f"  7B response: {len(response_7b)} chars")

            if not response_7b:
                sevenb_results.append({"candidate": i+1, "status": "empty"})
                continue

            # Check ABSTAIN
            if response_7b.strip().upper() == "ABSTAIN":
                sevenb_results.append({"candidate": i+1, "status": "abstain"})
                print(f"  Candidate {i+1}: ABSTAIN")
                continue

            # Check markdown fence
            if response_7b.strip().startswith("```"):
                sevenb_results.append({"candidate": i+1, "status": "parser_rejected", "reason": "markdown_fence"})
                print(f"  Candidate {i+1}: REJECTED (markdown fence)")
                continue

            # Check prose
            first_line = response_7b.strip().splitlines()[0] if response_7b.strip() else ""
            prose_starters = ["here", "this", "the", "note", "see", "fix"]
            if any(first_line.lower().startswith(p) for p in prose_starters):
                sevenb_results.append({"candidate": i+1, "status": "parser_rejected", "reason": "prose"})
                print(f"  Candidate {i+1}: REJECTED (prose)")
                continue

            # Apply patch
            patched = source_text.replace(anchor, response_7b, 1)
            if patched == source_text:
                sevenb_results.append({"candidate": i+1, "status": "apply_failed", "reason": "anchor_not_replaced"})
                print(f"  Candidate {i+1}: APPLY FAILED (anchor not replaced)")
                continue

            (Path(TASK["repo_dir"]) / TASK["target_file"]).write_text(patched, encoding="utf-8")

            # Run verifier
            ok, output = run_repro(TASK["repro_script"], TASK["python_executable"], TASK["repo_dir"])
            run_git(["checkout", "--", TASK["target_file"]], TASK["repo_dir"])

            sevenb_results.append({
                "candidate": i+1,
                "status": "verifier_pass" if ok else "verifier_fail",
                "replacement": response_7b[:200],
                "verifier_output": output[:200],
            })
            print(f"  Candidate {i+1}: {'VERIFIER PASS ✅' if ok else 'VERIFIER FAIL ❌'}")

            if ok:
                sevenb_selected = response_7b
                break

        # Unload 7B
        print("  Unloading 7B...")
        ollama_unload(MODELS["7b"]["name"])
    else:
        print("  7B not allowed, skipping")

    (OUTPUT_DIR / "7b_candidates.json").write_text(json.dumps(sevenb_results, indent=2))

    # ── M5: 12B Semantic Fallback ────────────────────────────────────────────
    print("\n=== M5: 12B Semantic Fallback ===")
    twelveb_results = []
    twelveb_selected = None

    # Only invoke 12B if 7B failed cleanly
    sevenb_passed = any(r.get("status") == "verifier_pass" for r in sevenb_results)
    sevenb_abstained = any(r.get("status") == "abstain" for r in sevenb_results)
    sevenb_all_rejected = all(r.get("status") in ("parser_rejected", "empty", "apply_failed") for r in sevenb_results)

    invoke_12b = (not sevenb_passed) and (sevenb_abstained or sevenb_all_rejected or
                   any(r.get("status") == "verifier_fail" for r in sevenb_results))

    if invoke_12b and policy.is_allowed(MODELS["12b"]["name"]):
        print("  7B failed/abstained — invoking 12B fallback...")

        # Build verifier feedback if available
        verifier_fail = next((r for r in sevenb_results if r.get("status") == "verifier_fail"), None)
        feedback_section = ""
        if verifier_fail:
            fb = StructuredVerifierFeedback()
            packet = fb.parse(
                verifier_fail.get("verifier_output", ""),
                previous_replacement=verifier_fail.get("replacement", ""),
                anchor_text=anchor,
            )
            feedback_section = (
                f"\n\nPrevious attempt failed:\n"
                f"- Failure type: {packet.failure_type}\n"
                f"- Error: {packet.assertion_summary}\n"
                f"- Fix the specific error."
            )

        system_12b = (
            "You are fixing a Python bug with a MINIMAL, PRECISE change.\n\n"
            "RULES:\n"
            "1. Output ONLY raw Python code (max 12 lines)\n"
            "2. NEVER wrap in ```python ... ``` fences\n"
            "3. NEVER add explanation\n"
            "4. Preserve exact indentation\n"
            "5. Change ONLY what fixes the bug\n"
            "6. If uncertain, output: ABSTAIN\n"
        )

        for i in range(2):
            user_12b = (
                f"Bug: {TASK['problem_statement']}\n\n"
                f"Symbol: HTML.write\n"
                f"Issue: formats parameter ignored in HTML output\n"
                f"Fix: apply column format before iter_str_vals\n\n"
                f"Code to replace:\n{anchor}\n"
                f"{feedback_section}\n\n"
                f"Output ONLY replacement code (raw Python, no markdown):"
            )
            print(f"  Loading 12B (candidate {i+1}/2)...")
            response_12b = ollama_generate(MODELS["12b"]["name"], system_12b, user_12b, timeout=300)
            print(f"  12B response: {len(response_12b)} chars")

            if not response_12b:
                twelveb_results.append({"candidate": i+1, "status": "empty"})
                continue

            if response_12b.strip().upper() == "ABSTAIN":
                twelveb_results.append({"candidate": i+1, "status": "abstain"})
                print(f"  Candidate {i+1}: ABSTAIN")
                continue

            # Apply and verify
            patched = source_text.replace(anchor, response_12b, 1)
            if patched == source_text:
                twelveb_results.append({"candidate": i+1, "status": "apply_failed"})
                continue

            (Path(TASK["repo_dir"]) / TASK["target_file"]).write_text(patched, encoding="utf-8")
            ok, output = run_repro(TASK["repro_script"], TASK["python_executable"], TASK["repo_dir"])
            run_git(["checkout", "--", TASK["target_file"]], TASK["repo_dir"])

            twelveb_results.append({
                "candidate": i+1,
                "status": "verifier_pass" if ok else "verifier_fail",
                "replacement": response_12b[:200],
                "verifier_output": output[:200],
            })
            print(f"  Candidate {i+1}: {'VERIFIER PASS ✅' if ok else 'VERIFIER FAIL ❌'}")

            if ok:
                twelveb_selected = response_12b
                break

        # Unload 12B
        print("  Unloading 12B...")
        ollama_unload(MODELS["12b"]["name"])
    else:
        print(f"  12B not needed (7B passed={sevenb_passed}, abstained={sevenb_abstained})")

    (OUTPUT_DIR / "12b_fallback.json").write_text(json.dumps(twelveb_results, indent=2))

    # ── M6: Delta Analysis ───────────────────────────────────────────────────
    print("\n=== M6: Delta Analysis ===")

    # Determine final status
    if sevenb_passed or twelveb_selected:
        status = "M6_C13453_VERIFIER_PASS_INTERNAL_ONLY"
    elif sevenb_abstained and not twelveb_results:
        status = "M6_C13453_MODEL_ABSTAINED"
    elif all(r.get("status") in ("parser_rejected", "empty") for r in sevenb_results + twelveb_results):
        status = "M6_C13453_ALL_CANDIDATES_REJECTED"
    else:
        status = "M6_C13453_SEMANTIC_FAIL"

    # Build final selection
    final_selection = {
        "task_id": TASK["task_id"],
        "anchor_symbol": "write",
        "anchor_span": f"L{TASK['anchor_span'][0]}-L{TASK['anchor_span'][1]}",
        "issue_intent": TASK["issue_intent"],
        "source_hash": source_hash,
        "3b_advisory": advisory,
        "7b_results": sevenb_results,
        "7b_passed": sevenb_passed,
        "7b_abstained": sevenb_abstained,
        "12b_invoked": invoke_12b,
        "12b_results": twelveb_results,
        "12b_passed": twelveb_selected is not None,
        "final_status": status,
    }

    (OUTPUT_DIR / "final_selection.json").write_text(json.dumps(final_selection, indent=2))

    # Restore workspace
    run_git(["checkout", "--", "."], TASK["repo_dir"])
    run_git(["clean", "-fd"], TASK["repo_dir"])

    print("\n" + "=" * 60)
    print(f"  Final Status: {status}")
    print(f"  7B passed: {sevenb_passed}")
    print(f"  12B invoked: {invoke_12b}")
    print(f"  12B passed: {twelveb_selected is not None}")
    print("=" * 60)


if __name__ == "__main__":
    main()
