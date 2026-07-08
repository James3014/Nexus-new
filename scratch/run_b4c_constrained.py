"""B4-C: 12B Constrained Selection/Completion on C_13453."""
import os, sys, json, hashlib, subprocess, tempfile, urllib.request
from pathlib import Path

os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"
WORKSPACE = Path("/Users/jameschen/Workspace/nexus")
sys.path.insert(0, str(WORKSPACE))

OLLAMA = "http://localhost:11434"
MODEL = "gemma4-coder-12b-q4km:latest"

TASK = {
    "repo_dir": str(WORKSPACE / ".nexus/workspaces/astropy"),
    "base_commit": "19cc804717", "target_file": "astropy/io/ascii/html.py",
    "python_executable": str(WORKSPACE / ".venv_astropy/bin/python3"),
    "problem": "Table.write with format='ascii.html' ignores the formats parameter.",
    "repro": ("from astropy.table import Table\nimport sys\n"
              "def test_repro():\n    t = Table([[1.12345]], names=['a'])\n"
              "    import io; out = io.StringIO()\n"
              "    t.write(out, format='ascii.html', formats={'a': '%.2f'})\n"
              "    html = out.getvalue()\n"
              "    if '<td>1.12</td>' not in html: raise AssertionError('formats ignored')\n"
              "    print('SUCCESS')\n"
              "if __name__ == '__main__':\n"
              "    try: test_repro(); sys.exit(0)\n"
              "    except Exception as e: print(f'FAILURE: {e}'); sys.exit(1)\n"),
    "anchor_text": '''    def write(self, table):
        """
        Return data in ``table`` converted to HTML as a list of strings.
        """
        # Check that table has only 1-d or 2-d columns. Above that fails.
        self._check_multidim_table(table)

        cols = list(table.columns.values())

        self.data.header.cols = cols

        if isinstance(self.data.fill_values, tuple):
            self.data.fill_values = [self.data.fill_values]

        self.data._set_fill_values(cols)

        lines = []

        # Set HTML escaping to False for any column in the raw_html_cols input
        raw_html_cols = self.html.get('raw_html_cols', [])
        if isinstance(raw_html_cols, str):
            raw_html_cols = [raw_html_cols]  # Allow for a single string to be passed

        cols_escaped = [col.info.name not in raw_html_cols for col in cols]''',
}


def ollama_gen(model, system, prompt, timeout=300):
    try:
        req = urllib.request.Request(f"{OLLAMA}/api/generate",
            data=json.dumps({"model": model, "system": system, "prompt": prompt,
                "stream": False, "options": {"temperature": 0.1, "num_ctx": 4096, "num_predict": 1024}}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()).get("response", "")
    except Exception as e:
        print(f"  error: {e}"); return ""

def ollama_unload(model):
    try:
        urllib.request.urlopen(urllib.request.Request(f"{OLLAMA}/api/generate",
            data=json.dumps({"name": model}).encode(),
            headers={"Content-Type": "application/json"}, method="DELETE"), timeout=10)
    except: pass

def run_git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)

def run_repro(script, py, repo):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
        f.write(script); p = f.name
    try:
        r = subprocess.run([py, p], cwd=repo, capture_output=True, text=True, timeout=60)
        return r.returncode == 0, (r.stdout + "\n" + r.stderr).strip()
    except Exception as e:
        return False, str(e)
    finally:
        Path(p).unlink(missing_ok=True)


def main():
    print("=" * 60)
    print("🏁 B4-C: 12B Constrained Selection/Completion")
    print("=" * 60)

    run_git(["checkout", "--", "."], TASK["repo_dir"])
    run_git(["clean", "-fd"], TASK["repo_dir"])
    run_git(["checkout", TASK["base_commit"]], TASK["repo_dir"])
    source_text = (Path(TASK["repo_dir"]) / TASK["target_file"]).read_text(encoding="utf-8")

    # B4-C prompt: constrained action selection
    system = (
        "You are fixing a Python bug using CONSTRAINED edit actions.\n\n"
        "AVAILABLE ACTIONS:\n"
        "1. REPLACE_EXPR — replace one expression inside allowed span\n"
        "2. INSERT_GUARD — insert small conditional before value conversion\n"
        "3. INSERT_FORMAT_APPLICATION — insert one formatting line\n"
        "4. REORDER_EXISTING_CALL — move existing call within method\n"
        "5. CALL_EXISTING_HELPER — call existing helper discovered by CodeIntel\n"
        "6. ABSTAIN\n\n"
        "DEEP EVIDENCE:\n"
        "- _set_col_formats() (core.py L934-L938) sets col.info.format from self.formats\n"
        "- html.py iter_str_vals() (L440) ignores col.info.format\n"
        "- formats kwarg stored in writer.data.formats (ui.py L1726)\n"
        "- FIX: Apply col.info.format to column values BEFORE iter_str_vals\n\n"
        "RULES:\n"
        "1. Output ONLY a JSON object\n"
        "2. NEVER output code blocks or prose\n"
        "3. replacement_snippet must be a minimal code fragment (1-3 lines)\n"
        "4. Do NOT rewrite the entire write method\n"
        "5. If uncertain, output: {\"abstain\": true}\n\n"
        "Output JSON:\n"
        "{\n"
        "  \"selected_action_type\": \"ACTION_TYPE\",\n"
        "  \"target_span\": \"html.py L440\",\n"
        "  \"replacement_snippet\": \"minimal code fragment\",\n"
        "  \"expected_effect\": \"what this does\",\n"
        "  \"confidence\": 0.0-1.0\n"
        "}"
    )

    user = (
        f"Bug: {TASK['problem']}\n\n"
        f"Code to replace (anchor):\n{TASK['anchor_text']}\n\n"
        f"Select one constrained action and provide the minimal replacement snippet.\n"
        f"Output JSON only:"
    )

    results = []
    for i in range(2):
        print(f"\n  Loading 12B (attempt {i+1}/2)...")
        resp = ollama_gen(MODEL, system, user)
        print(f"  12B response: {len(resp)} chars")
        print(f"  Preview: {resp[:300]}")

        # Parse JSON
        try:
            action = json.loads(resp)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{[^{}]*\}', resp, re.DOTALL)
            if json_match:
                try:
                    action = json.loads(json_match.group())
                except:
                    action = {"abstain": True, "error": "json_parse_failed"}
            else:
                action = {"abstain": True, "error": "no_json_found"}

        results.append({"attempt": i+1, "raw": resp[:500], "parsed": action})

        if action.get("abstain"):
            print(f"  Action: ABSTAIN")
            continue

        # Validate action type
        valid_types = {"REPLACE_EXPR", "INSERT_GUARD", "INSERT_FORMAT_APPLICATION",
                       "REORDER_EXISTING_CALL", "CALL_EXISTING_HELPER"}
        if action.get("selected_action_type") not in valid_types:
            print(f"  Action: INVALID type: {action.get('selected_action_type')}")
            results[-1]["valid"] = False
            continue

        # Build replacement from action
        snippet = action.get("replacement_snippet", "")
        if not snippet or len(snippet) < 5:
            print(f"  Action: REPLACEMENT_TOO_SHORT")
            results[-1]["valid"] = False
            continue

        # Try to apply
        print(f"  Action: {action.get('selected_action_type')} — applying...")
        print(f"  Snippet: {snippet[:100]}")

        # Build full replacement by inserting snippet at target span
        # For simplicity, try inserting snippet before the iter_str_vals line
        anchor = TASK["anchor_text"]
        patched = source_text.replace(anchor, anchor.replace(
            "col_iter_str_vals = self.fill_values(col, col.info.iter_str_vals())",
            f"{snippet}\n                                col_iter_str_vals = self.fill_values(col, col.info.iter_str_vals())"
        ), 1)

        if patched == source_text:
            print(f"  Apply failed (no change)")
            results[-1]["apply_ok"] = False
            continue

        (Path(TASK["repo_dir"]) / TASK["target_file"]).write_text(patched, encoding="utf-8")
        ok, out = run_repro(TASK["repro"], TASK["python_executable"], TASK["repo_dir"])
        run_git(["checkout", "--", TASK["target_file"]], TASK["repo_dir"])

        results[-1]["apply_ok"] = True
        results[-1]["verifier_ok"] = ok
        results[-1]["verifier_output"] = out[:200]
        print(f"  Verifier: {'PASS ✅' if ok else 'FAIL ❌'} — {out[:150]}")

        if ok:
            print("\n  ✅ VERIFIER PASS!")
            break

    ollama_unload(MODEL)

    # Final status
    passed = any(r.get("verifier_ok") for r in results)
    all_abstain = all(r.get("parsed", {}).get("abstain", False) for r in results)

    if passed:
        status = "B4C_VERIFIER_PASS_INTERNAL_ONLY"
    elif all_abstain:
        status = "B4C_MODEL_ABSTAINED"
    else:
        status = "B4C_PATCH_APPLIED_VERIFIER_FAILED"

    print(f"\n{'='*60}")
    print(f"  Status: {status}")
    print(f"  Attempts: {len(results)}")
    print(f"  Verifier pass: {passed}")
    print(f"{'='*60}")

    (Path("artifacts/runtime/b4c_constrained_selection_v0/results.json")).write_text(
        json.dumps({"status": status, "results": results}, indent=2))


if __name__ == "__main__":
    main()
