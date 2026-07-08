"""
P13-A: Verifier Feedback Correction for C_12481
================================================
Uses verifier feedback to attempt one bounded correction.
"""
import os
import sys
import json
import hashlib
import urllib.request
import subprocess
import tempfile
from pathlib import Path

os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"

WORKSPACE_ROOT = Path("/Users/jameschen/Workspace/nexus")
sys.path.insert(0, str(WORKSPACE_ROOT))

from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol

OLLAMA_ENDPOINT = "http://localhost:11434"
MODEL_NAME = "gemma4-coder-12b-q4km:latest"
NUM_CTX = 4096
NUM_PREDICT = 768
TIMEOUT_S = 300
OUTPUT_DIR = WORKSPACE_ROOT / "artifacts/runtime/p13a_verifier_feedback_correction_v0/C_12481"

# Task config
TASK = {
    "task_id": "C_12481",
    "instance_id": "sympy__sympy-12481",
    "repo_dir": WORKSPACE_ROOT / ".nexus/workspaces/sympy",
    "base_commit": "c807dfe756",
    "target_file": "sympy/combinatorics/permutations.py",
    "python_executable": "/Users/jameschen/Workspace/nexus/.venv_sympy/bin/python3",
    "anchor_text": (
        "        if has_dups(temp):\n"
        "            if is_cycle:\n"
        "                raise ValueError('there were repeated elements; to resolve '\n"
        "                'cycles use Cycle%s.' % ''.join([str(tuple(c)) for c in args]))\n"
        "            else:\n"
        "                raise ValueError('there were repeated elements.')"
    ),
    "repro_script": (
        "import sys\n"
        "sys.path.insert(0, '/Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy')\n"
        "from sympy.combinatorics import Permutation\n"
        "def test_repro():\n"
        "    try:\n"
        "        p = Permutation([[0, 1], [0, 2]])\n"
        "        print(f'Calculated permutation: {p}')\n"
        "        if p == Permutation(0, 1, 2):\n"
        "            print('SUCCESS: Permutation allowed non-disjoint lists and calculated correctly.')\n"
        "            sys.exit(0)\n"
        "        else:\n"
        "            print('FAILURE: Permutation calculated incorrectly.')\n"
        "            sys.exit(1)\n"
        "    except ValueError as e:\n"
        "        if 'there were repeated elements' in str(e):\n"
        "            print(f'BUG PRESENT: ValueError raised for repeated elements: {e}')\n"
        "            sys.exit(1)\n"
        "        else:\n"
        "            print(f'FAILURE: Unexpected ValueError: {e}')\n"
            "            sys.exit(1)\n"
        "    except Exception as e:\n"
        "        print(f'FAILURE: Unexpected exception: {e}')\n"
        "        sys.exit(1)\n"
        "if __name__ == '__main__':\n"
        "    test_repro()\n"
    ),
    "previous_replacement": "if has_dups(temp):\n    raise ValueError('there were repeated elements.')",
    "verifier_failure": "IndentationError: unexpected indent at line 900 in permutations.py. The replacement removed the 'if is_cycle:' branch, causing indentation mismatch.",
}


def ollama_generate(system_prompt: str, user_prompt: str) -> str:
    payload = json.dumps({
        "model": MODEL_NAME,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT,
        }
    }).encode()
    print(f"    → Invoking {MODEL_NAME}...", flush=True)
    try:
        req = urllib.request.Request(
            f"{OLLAMA_ENDPOINT}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read())
            return data.get("response", "")
    except Exception as e:
        print(f"    ❌ Ollama error: {e}", flush=True)
        return ""


def run_git(args, cwd):
    return subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True)


def run_repro(repro_script: str, python_exe: str, repo_dir: Path) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
        f.write(repro_script)
        script_path = f.name
    try:
        res = subprocess.run(
            [python_exe, script_path],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=60
        )
        return res.returncode == 0, (res.stdout + "\n" + res.stderr).strip()
    except Exception as e:
        return False, f"REPRO_ERROR: {e}"
    finally:
        Path(script_path).unlink(missing_ok=True)


def main():
    print("=" * 60)
    print("🏁 P13-A: Verifier Feedback Correction for C_12481")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Checkout to base commit
    run_git(["checkout", "--", "."], TASK["repo_dir"])
    run_git(["clean", "-fd"], TASK["repo_dir"])
    run_git(["checkout", TASK["base_commit"]], TASK["repo_dir"])

    # 2. Read source
    source_text = (TASK["repo_dir"] / TASK["target_file"]).read_text(encoding="utf-8")
    source_hash = hashlib.sha256(source_text.encode()).hexdigest()[:16]

    # 3. Verify anchor exists
    anchor = TASK["anchor_text"]
    anchor_count = source_text.count(anchor)
    print(f"   → Anchor found {anchor_count}x in source.")
    if anchor_count != 1:
        print("   ❌ Anchor not found or ambiguous!")
        return

    # 4. Build correction prompt
    system = (
        "You are fixing a Python bug. Your previous attempt was close but had an issue.\n"
        "CRITICAL RULES:\n"
        "1. Output ONLY raw Python code — no explanation, no markdown\n"
        "2. NEVER wrap output in ```python ... ``` code fences\n"
        "3. Preserve the EXACT structure of the original code\n"
        "4. Do NOT remove existing branches (if/else) — modify them\n"
        "5. The replacement must fit exactly where the anchor is\n"
    )

    user = (
        f"Bug: Permutation should allow non-disjoint cycles.\n\n"
        f"Original code to replace:\n{anchor}\n\n"
        f"Your previous replacement:\n{TASK['previous_replacement']}\n\n"
        f"Verifier failure:\n{TASK['verifier_failure']}\n\n"
        f"The issue: You removed the 'if is_cycle:' branch, causing indentation error.\n"
        f"Fix: Keep the if/else structure. When is_cycle is True, convert to Cycle composition "
        f"instead of raising ValueError. When is_cycle is False, keep the ValueError.\n\n"
        f"Output ONLY the replacement code (same indentation as original):"
    )

    print("   → Generating correction...")
    response = ollama_generate(system, user)
    print(f"   → Received {len(response)} chars.")

    if not response:
        print("   ❌ Empty response!")
        return

    # 5. Parse with strict parser
    parser = SolidSearchReplaceProtocol()
    intents_or_err = parser.parse(response, anchor_text=anchor)
    if hasattr(intents_or_err, "kind"):
        print(f"   ❌ Parser rejected: {intents_or_err.kind.name} — {intents_or_err.message}")
        # Save the raw response for analysis
        (OUTPUT_DIR / "raw_response.txt").write_text(response)
        return

    intent = intents_or_err[0]
    print(f"   → Replacement ({len(intent.replace)} chars):")
    print(f"     {intent.replace[:200]}...")

    # 6. Apply patch
    full_path = TASK["repo_dir"] / TASK["target_file"]
    patched = source_text.replace(anchor, intent.replace, 1)
    if patched == source_text:
        print("   ❌ Anchor not replaced!")
        return

    full_path.write_text(patched, encoding="utf-8")
    print("   → Patch applied.")

    # 7. Run verifier
    print("   → Running verifier...")
    repro_ok, repro_log = run_repro(TASK["repro_script"], TASK["python_executable"], TASK["repo_dir"])
    print(f"   → Verifier: {'PASS ✅' if repro_ok else 'FAIL ❌'}")
    print(f"   → Output: {repro_log[:500]}")

    # 8. Save results
    (OUTPUT_DIR / "raw_response.txt").write_text(response)
    (OUTPUT_DIR / "repro.log").write_text(repro_log)

    diff_res = subprocess.run(
        ["git", "diff", TASK["target_file"]],
        cwd=str(TASK["repo_dir"]),
        capture_output=True, text=True
    )
    (OUTPUT_DIR / "patch.diff").write_text(diff_res.stdout)

    receipt = {
        "task_id": TASK["task_id"],
        "model": MODEL_NAME,
        "source_hash": source_hash,
        "anchor_hash": hashlib.sha256(anchor.encode()).hexdigest()[:16],
        "replacement": intent.replace,
        "verifier_passed": repro_ok,
        "verifier_output": repro_log[:500],
        "status": "P13A_CORRECTION_VERIFIER_PASS" if repro_ok else "P13A_CORRECTION_IMPROVED_BUT_FAILS",
    }
    (OUTPUT_DIR / "receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False))

    # Restore workspace
    run_git(["checkout", "--", "."], TASK["repo_dir"])
    run_git(["clean", "-fd"], TASK["repo_dir"])

    print("\n" + "=" * 60)
    print(f"{'✅ P13A_CORRECTION_VERIFIER_PASS' if repro_ok else '❌ P13A_CORRECTION_IMPROVED_BUT_FAILS'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
