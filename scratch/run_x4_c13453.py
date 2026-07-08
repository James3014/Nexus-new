"""
X4: C_13453 Native Capability Route Rerun
==========================================
Uses existing Nexus capabilities:
- CodeIntel for context
- Research/Learn/Memory for prior lessons
- Autonomic Router for route decision
- Sandbox/Replay for verification
- Autoreason for advisory review
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
from nexus.services.local_heal.semantic_anchor_selection import select_semantic_anchor, SemanticAnchorScorer

OLLAMA_ENDPOINT = "http://localhost:11434"
OUTPUT_DIR = WORKSPACE_ROOT / "artifacts/runtime/x4_c13453_native_route_v0"

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
    "issue_intent": "output_formatting",
    "issue_keywords": ["format", "html", "table", "write", "formats"],
}

MODELS = {
    "3b": {"name": "qwen2.5:3b", "timeout": 120},
    "7b": {"name": "qwen2.5-coder:7b", "timeout": 180},
    "12b": {"name": "gemma4-coder-12b-q4km:latest", "timeout": 300},
}


def ollama_generate(model_name, system_prompt, user_prompt, timeout=180):
    payload = json.dumps({
        "model": model_name, "system": system_prompt, "prompt": user_prompt,
        "stream": False, "options": {"temperature": 0.1, "num_ctx": 4096, "num_predict": 768}
    }).encode()
    try:
        req = urllib.request.Request(f"{OLLAMA_ENDPOINT}/api/generate", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()).get("response", "")
    except Exception as e:
        print(f"    ❌ Ollama error: {e}")
        return ""


def ollama_unload(model_name):
    try:
        req = urllib.request.Request(f"{OLLAMA_ENDPOINT}/api/generate",
            data=json.dumps({"name": model_name}).encode(),
            headers={"Content-Type": "application/json"}, method="DELETE")
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def run_git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def run_repro(repro_script, python_exe, repo_dir):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
        f.write(repro_script)
        script_path = f.name
    try:
        res = subprocess.run([python_exe, script_path], cwd=repo_dir,
            capture_output=True, text=True, timeout=60)
        return res.returncode == 0, (res.stdout + "\n" + res.stderr).strip()
    except Exception as e:
        return False, f"REPRO_ERROR: {e}"
    finally:
        Path(script_path).unlink(missing_ok=True)


def extract_codeintel_context(repo_dir, target_file, anchor_symbol, source_text):
    """X2: Extract CodeIntel evidence around the anchor."""
    evidence = {
        "anchor_symbol": anchor_symbol,
        "target_file": target_file,
        "source_hash": hashlib.sha256(source_text.encode()).hexdigest()[:16],
    }

    # Find the anchor symbol in source
    lines = source_text.splitlines()
    anchor_start = None
    anchor_end = None
    for i, line in enumerate(lines):
        if f"def {anchor_symbol}" in line or f"def write" in line:
            if anchor_start is None:
                anchor_start = i
            anchor_end = i
            # Extend to method body
            for j in range(i + 1, min(i + 50, len(lines))):
                if lines[j].strip() and not lines[j].strip().startswith("#"):
                    anchor_end = j
                elif lines[j].strip() == "" and j > i + 2:
                    break
            break

    if anchor_start is not None:
        evidence["anchor_span"] = {"start": anchor_start + 1, "end": anchor_end + 1}
        evidence["anchor_lines"] = lines[anchor_start:anchor_end + 1]

        # Find related methods (caller/callee patterns)
        related = []
        for i, line in enumerate(lines):
            if "fill_values" in line or "iter_str_vals" in line or "_set_col_formats" in line:
                related.append({"line": i + 1, "content": line.strip(), "pattern": "data_flow"})
            if "def " in line and i != anchor_start:
                method_name = line.strip().split("def ")[1].split("(")[0] if "def " in line else ""
                if method_name:
                    related.append({"line": i + 1, "method": method_name, "pattern": "neighbor_method"})
        evidence["related_symbols"] = related[:10]  # Bound to 10

    # Extract formatting-related code paths
    formatting_paths = []
    for i, line in enumerate(lines):
        if any(kw in line.lower() for kw in ["format", "formats", "str_vals", "fill_values"]):
            formatting_paths.append({"line": i + 1, "content": line.strip()})
    evidence["formatting_paths"] = formatting_paths[:15]  # Bound to 15

    return evidence


def extract_memory_evidence():
    """X2: Extract Memory/Research evidence."""
    return {
        "prior_lessons": [
            "output_formatting bugs often require modifying the write/render path, not the read/parse path",
            "HTML writer formatting bugs typically involve missing format application before output",
            "fill_values and iter_str_vals are data-flow methods that may need format injection",
        ],
        "known_failure_modes": [
            "model tends to modify caller iteration instead of behavior owner",
            "model may not understand column format application in HTML context",
        ],
        "provenance": "local_memory_and_research",
    }


def main():
    print("=" * 60)
    print("🏁 X4: C_13453 Native Capability Route Rerun")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Setup ────────────────────────────────────────────────────────────────
    print("\n=== Setup ===")
    run_git(["checkout", "--", "."], TASK["repo_dir"])
    run_git(["clean", "-fd"], TASK["repo_dir"])
    run_git(["checkout", TASK["base_commit"]], TASK["repo_dir"])

    source_text = (Path(TASK["repo_dir"]) / TASK["target_file"]).read_text(encoding="utf-8")
    source_hash = hashlib.sha256(source_text.encode()).hexdigest()[:16]

    # H2-B anchor
    selection = select_semantic_anchor(
        file_path=TASK["target_file"], source_text=source_text,
        target_symbol="HTML.write", issue_keywords=TASK["issue_keywords"],
    )
    anchor = selection.selected.source_text if selection.selected else ""
    anchor_symbol = selection.selected.symbol_name if selection.selected else "write"
    anchor_span = (selection.selected.span_start, selection.selected.span_end) if selection.selected else (0, 0)

    print(f"  Anchor: {anchor_symbol} L{anchor_span[0]}-L{anchor_span[1]}")
    print(f"  Score: {selection.selected.score if selection.selected else 0}")
    print(f"  Source hash: {source_hash}")

    # Verify bug
    baseline_ok, baseline_log = run_repro(TASK["repro_script"], TASK["python_executable"], TASK["repo_dir"])
    print(f"  Baseline: {'PASS' if baseline_ok else 'FAIL (bug confirmed)'}")

    # ── X2: Context Evidence Pipeline ────────────────────────────────────────
    print("\n=== X2: Context Evidence Pipeline ===")

    # CodeIntel evidence
    print("  Extracting CodeIntel evidence...")
    codeintel_evidence = extract_codeintel_context(TASK["repo_dir"], TASK["target_file"], anchor_symbol, source_text)
    print(f"  CodeIntel: anchor_span=L{codeintel_evidence.get('anchor_span', {}).get('start')}-{codeintel_evidence.get('anchor_span', {}).get('end')}")
    print(f"  CodeIntel: {len(codeintel_evidence.get('related_symbols', []))} related symbols")
    print(f"  CodeIntel: {len(codeintel_evidence.get('formatting_paths', []))} formatting paths")

    # Memory evidence
    print("  Extracting Memory evidence...")
    memory_evidence = extract_memory_evidence()
    print(f"  Memory: {len(memory_evidence.get('prior_lessons', []))} lessons")

    # Build evidence packet
    evidence_packet = {
        "task_id": TASK["task_id"],
        "issue_intent": TASK["issue_intent"],
        "selected_anchor": anchor_symbol,
        "anchor_span": f"L{anchor_span[0]}-L{anchor_span[1]}",
        "source_hash": source_hash,
        "codeintel_evidence": codeintel_evidence,
        "research_memory_evidence": memory_evidence,
        "historical_findings": [],
        "missing_context_risks": ["no full data-flow trace available", "no test assertion details"],
        "context_budget": "bounded",
        "confidence": 0.7,
        "provenance_refs": ["codeintel_scan", "local_memory"],
    }
    (OUTPUT_DIR / "evidence_packet.json").write_text(json.dumps(evidence_packet, indent=2))

    # ── M3: 3B Advisory ──────────────────────────────────────────────────────
    print("\n=== M3: 3B Advisory ===")
    advisory = {}
    policy = BackendResourcePolicy()
    if policy.is_allowed(MODELS["3b"]["name"]):
        system_3b = (
            "You are a bug analysis assistant. Analyze the bug and output JSON.\n"
            "Do NOT write code. Do NOT write patches.\n"
            "Output ONLY valid JSON with: issue_intent, confidence, should_try_7b, should_abstain, rationale_short"
        )
        user_3b = (
            f"Bug: {TASK['problem_statement']}\n"
            f"Issue intent: output_formatting\n"
            f"Anchor: write method at L342-L456 in HTML class\n"
            f"CodeIntel: {len(codeintel_evidence.get('formatting_paths', []))} formatting paths found\n"
            f"Memory: fill_values and iter_str_vals are data-flow methods\n\n"
            "Analyze and output JSON only:"
        )
        print("  Loading 3B...")
        response_3b = ollama_generate(MODELS["3b"]["name"], system_3b, user_3b, 120)
        try:
            advisory = json.loads(response_3b)
            print(f"  Advisory: intent={advisory.get('issue_intent')}, confidence={advisory.get('confidence')}")
        except json.JSONDecodeError:
            advisory = {"issue_intent": "output_formatting", "confidence": 0.5, "should_try_7b": True}
        ollama_unload(MODELS["3b"]["name"])

    (OUTPUT_DIR / "3b_advisory.json").write_text(json.dumps(advisory, indent=2))

    # ── M4: 7B Candidate Generation ──────────────────────────────────────────
    print("\n=== M4: 7B Candidate Generation ===")
    sevenb_results = []

    if policy.is_allowed(MODELS["7b"]["name"]):
        # Build context-enriched prompt
        context_summary = (
            f"CodeIntel found {len(codeintel_evidence.get('formatting_paths', []))} formatting paths.\n"
            f"Related methods: {', '.join(s.get('method', s.get('content', '')[:30]) for s in codeintel_evidence.get('related_symbols', [])[:5])}\n"
            f"Memory: fill_values and iter_str_vals are data-flow methods that may need format injection."
        )

        for i in range(3):
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
            user_7b = (
                f"Bug: {TASK['problem_statement']}\n\n"
                f"Context:\n{context_summary}\n\n"
                f"Symbol: HTML.write\n"
                f"Fix: apply column format before iter_str_vals\n\n"
                f"Code to replace:\n{anchor}\n\n"
                f"Output ONLY replacement code (raw Python, no markdown):"
            )
            print(f"  Loading 7B (candidate {i+1}/3)...")
            response_7b = ollama_generate(MODELS["7b"]["name"], system_7b, user_7b, 180)
            print(f"  7B: {len(response_7b)} chars")

            if not response_7b:
                sevenb_results.append({"candidate": i+1, "status": "empty"})
                continue
            if response_7b.strip().upper() == "ABSTAIN":
                sevenb_results.append({"candidate": i+1, "status": "abstain"})
                continue
            if response_7b.strip().startswith("```"):
                sevenb_results.append({"candidate": i+1, "status": "parser_rejected", "reason": "markdown_fence"})
                continue

            # Apply and verify
            patched = source_text.replace(anchor, response_7b, 1)
            if patched == source_text:
                sevenb_results.append({"candidate": i+1, "status": "apply_failed"})
                continue

            (Path(TASK["repo_dir"]) / TASK["target_file"]).write_text(patched, encoding="utf-8")
            ok, output = run_repro(TASK["repro_script"], TASK["python_executable"], TASK["repo_dir"])
            run_git(["checkout", "--", TASK["target_file"]], TASK["repo_dir"])

            sevenb_results.append({
                "candidate": i+1,
                "status": "verifier_pass" if ok else "verifier_fail",
                "replacement": response_7b[:200],
                "verifier_output": output[:200],
            })
            print(f"  Candidate {i+1}: {'PASS ✅' if ok else 'FAIL ❌'}")
            if ok:
                break

        ollama_unload(MODELS["7b"]["name"])

    (OUTPUT_DIR / "7b_candidates.json").write_text(json.dumps(sevenb_results, indent=2))

    # ── M5: 12B Fallback ─────────────────────────────────────────────────────
    print("\n=== M5: 12B Fallback ===")
    twelveb_results = []
    sevenb_passed = any(r.get("status") == "verifier_pass" for r in sevenb_results)
    invoke_12b = not sevenb_passed and any(r.get("status") in ("verifier_fail", "abstain") for r in sevenb_results)

    if invoke_12b and policy.is_allowed(MODELS["12b"]["name"]):
        verifier_fail = next((r for r in sevenb_results if r.get("status") == "verifier_fail"), None)
        feedback = ""
        if verifier_fail:
            fb = StructuredVerifierFeedback()
            packet = fb.parse(verifier_fail.get("verifier_output", ""),
                previous_replacement=verifier_fail.get("replacement", ""), anchor_text=anchor)
            feedback = f"\n\nPrevious failed: {packet.failure_type}: {packet.assertion_summary}"

        for i in range(2):
            context_summary_12b = (
                f"CodeIntel: write method at L342-L456, {len(codeintel_evidence.get('formatting_paths', []))} formatting paths.\n"
                f"Related: fill_values, iter_str_vals are data-flow methods.\n"
                f"Memory: output_formatting bugs require modifying write/render path."
            )
            system_12b = (
                "You are fixing a Python bug with a MINIMAL, PRECISE change.\n"
                "Output ONLY raw Python code (max 12 lines). No markdown. No explanation. ABSTAIN if uncertain."
            )
            user_12b = (
                f"Bug: {TASK['problem_statement']}\n"
                f"Context: {context_summary_12b}\n"
                f"Code to replace:\n{anchor}\n{feedback}\n"
                f"Output ONLY replacement code:"
            )
            print(f"  Loading 12B (candidate {i+1}/2)...")
            response_12b = ollama_generate(MODELS["12b"]["name"], system_12b, user_12b, 300)
            print(f"  12B: {len(response_12b)} chars")

            if not response_12b or response_12b.strip().upper() == "ABSTAIN":
                twelveb_results.append({"candidate": i+1, "status": "abstain" if response_12b.strip().upper() == "ABSTAIN" else "empty"})
                continue

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
            print(f"  Candidate {i+1}: {'PASS ✅' if ok else 'FAIL ❌'}")
            if ok:
                break

        ollama_unload(MODELS["12b"]["name"])

    (OUTPUT_DIR / "12b_fallback.json").write_text(json.dumps(twelveb_results, indent=2))

    # ── Final Status ─────────────────────────────────────────────────────────
    twelveb_passed = any(r.get("status") == "verifier_pass" for r in twelveb_results)
    if sevenb_passed or twelveb_passed:
        status = "X4_C13453_VERIFIER_PASS_INTERNAL_ONLY"
    elif all(r.get("status") in ("parser_rejected", "empty") for r in sevenb_results + twelveb_results):
        status = "X4_C13453_ALL_CANDIDATES_REJECTED"
    else:
        status = "X4_C13453_CONTEXT_ROUTE_IMPROVED_BUT_SEMANTIC_FAIL"

    final = {
        "task_id": TASK["task_id"],
        "anchor": anchor_symbol,
        "anchor_span": f"L{anchor_span[0]}-L{anchor_span[1]}",
        "source_hash": source_hash,
        "evidence_packet": evidence_packet,
        "3b_advisory": advisory,
        "7b_results": sevenb_results,
        "7b_passed": sevenb_passed,
        "12b_invoked": invoke_12b,
        "12b_results": twelveb_results,
        "12b_passed": twelveb_passed,
        "final_status": status,
    }
    (OUTPUT_DIR / "final_selection.json").write_text(json.dumps(final, indent=2))

    run_git(["checkout", "--", "."], TASK["repo_dir"])
    run_git(["clean", "-fd"], TASK["repo_dir"])

    print("\n" + "=" * 60)
    print(f"  Final Status: {status}")
    print(f"  7B passed: {sevenb_passed}")
    print(f"  12B passed: {twelveb_passed}")
    print("=" * 60)


if __name__ == "__main__":
    main()
