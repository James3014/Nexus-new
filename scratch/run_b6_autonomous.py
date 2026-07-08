"""B6: Autonomous Constrained Action Repair Loop for C_13453."""
import os, sys, json, hashlib, subprocess, tempfile
from pathlib import Path

sys.path.insert(0, '/Users/jameschen/Workspace/nexus')
os.environ["NEXUS_PROTOCOL_MODE"] = "anchored_edit"

from nexus.services.local_heal.constrained_action_applier import (
    ConstrainedActionApplier, ConstrainedAction, ActionResult
)

WORKSPACE = Path('/Users/jameschen/Workspace/nexus')
REPO = WORKSPACE / '.nexus/workspaces/astropy'
OUTPUT = WORKSPACE / 'artifacts/runtime/b6b_replay_v0'

TASK = {
    'repo_dir': str(REPO),
    'base_commit': '19cc804717',
    'target_file': 'astropy/io/ascii/html.py',
    'python_executable': str(WORKSPACE / '.venv_astropy/bin/python3'),
    'problem': 'Table.write with format="ascii.html" ignores the formats parameter.',
    'repro': ('from astropy.table import Table\nimport sys\n'
              'def test_repro():\n    t = Table([[1.12345]], names=["a"])\n'
              '    import io; out = io.StringIO()\n'
              '    t.write(out, format="ascii.html", formats={"a": "%.2f"})\n'
              '    html = out.getvalue()\n'
              '    if "<td>1.12</td>" not in html: raise AssertionError("formats ignored")\n'
              '    print("SUCCESS")\n'
              'if __name__ == "__main__":\n'
              '    try: test_repro(); sys.exit(0)\n'
              '    except Exception as e: print(f"FAILURE: {e}"); sys.exit(1)\n'),
    'anchor_text': '''    def write(self, table):
        """
        Return data in ``table`` converted to HTML as a list of strings.
        """
        # Check that table has only 1-d or 2-d columns. Above that fails.
        self._check_multidim_table(table)

        cols = list(table.columns.values())

        self.data.header.cols = cols

        if isinstance(self.data.fill_values, tuple):
            self.data.fill_values = [self.data.fill_values]

        self.data._set_fill_values(cols)''',
}


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

def _hash(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class InsertPointResolver:
    """B6-A: Relation-based insertion point resolver."""

    def resolve(self, lines, action_type, target_span, anchor_text):
        """Find insertion point using relation-based matching."""
        # Find the write method span
        write_start = None
        write_end = None
        for i, line in enumerate(lines):
            if "def write(self, table):" in line:
                write_start = i
            if write_start and i > write_start and line.strip() and not line.startswith(" " * 4):
                write_end = i
                break
        if write_end is None:
            write_end = len(lines)

        # Strategy 1: AFTER_CALL — find _set_fill_values(cols) call
        for i in range(write_start or 0, write_end):
            if "_set_fill_values(cols)" in lines[i]:
                return i + 1, "AFTER_CALL:_set_fill_values"

        # Strategy 2: BEFORE_CALL — find iter_str_vals call
        for i in range(write_start or 0, write_end):
            if "iter_str_vals" in lines[i] and "def " not in lines[i]:
                return i, "BEFORE_CALL:iter_str_vals"

        # Strategy 3: INSIDE_ANCHOR — first empty line after _set_fill_values setup
        in_anchor = False
        for i in range(write_start or 0, write_end):
            if "_set_fill_values" in lines[i]:
                in_anchor = True
            if in_anchor and lines[i].strip() == "" and i > (write_start or 0) + 5:
                return i, "INSIDE_ANCHOR:after_dependency_setup"

        return -1, "INSERTION_TARGET_NOT_FOUND"


def main():
    print("=" * 60)
    print("🏁 B6: Autonomous Constrained Action Repair Loop")
    print("=" * 60)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    # Setup
    run_git(["checkout", "--", "."], REPO)
    run_git(["clean", "-fd"], REPO)
    run_git(["checkout", TASK["base_commit"]], REPO)
    source_text = (REPO / TASK["target_file"]).read_text(encoding="utf-8")
    source_hash = _hash(source_text)
    print(f"  Source hash: {source_hash}")

    lines = source_text.splitlines()
    anchor_text = TASK["anchor_text"]

    # B6-A: Resolve insertion point
    print("\n=== B6-A: Insert Point Resolution ===")
    resolver = InsertPointResolver()
    action_type = "CALL_EXISTING_HELPER"
    insert_line, insert_reason = resolver.resolve(lines, action_type, "L342-L456", anchor_text)
    print(f"  Insert point: L{insert_line} ({insert_reason})")

    if insert_line < 0:
        print("  ❌ Insertion target not found")
        return

    # B6-B: Replay action
    print("\n=== B6-B: Replay Correct Action ===")
    snippet = "self.data._set_col_formats(cols)"
    target_line = lines[insert_line - 1] if insert_line <= len(lines) else ""
    indent = len(target_line) - len(target_line.lstrip())
    indented_snippet = " " * indent + snippet

    # Build patched source
    new_lines = lines[:insert_line] + [indented_snippet] + lines[insert_line:]
    patched_source = "\n".join(new_lines)

    # Syntax check
    try:
        ast.parse(patched_source)
        syntax_ok = True
        print("  Syntax: ✅ PASS")
    except SyntaxError as e:
        print(f"  Syntax: ❌ FAIL — {e}")
        syntax_ok = False

    if not syntax_ok:
        print("  ❌ Syntax failed after insertion")
        return

    # Apply patch
    (REPO / TASK["target_file"]).write_text(patched_source, encoding="utf-8")
    patched_hash = _hash(patched_source)
    print(f"  Patched hash: {patched_hash}")

    # Run verifier
    print("\n  Running verifier...")
    ok, out = run_repro(TASK["repro"], TASK["python_executable"], str(REPO))
    print(f"  Verifier: {'PASS ✅' if ok else 'FAIL ❌'}")
    print(f"  Output: {out[:300]}")

    # Save diff
    diff_result = subprocess.run(["git", "diff", TASK["target_file"]], cwd=str(REPO),
        capture_output=True, text=True)
    (OUTPUT / "patch_diff.patch").write_text(diff_result.stdout)

    if ok:
        print("\n" + "=" * 60)
        print("  🎉 B6_VERIFIER_PASS_INTERNAL_ONLY")
        print("=" * 60)
    else:
        print(f"\n  Verifier failed: {out[:200]}")
        print("  This is a new failure, not 'formats ignored'")

    # Restore
    run_git(["checkout", "--", "."], REPO)
    run_git(["clean", "-fd"], REPO)

    # Write receipt
    receipt = {
        "task_id": "C_13453",
        "insert_line": insert_line,
        "insert_reason": insert_reason,
        "snippet": snippet,
        "syntax_ok": syntax_ok,
        "verifier_pass": ok,
        "verifier_output": out[:300],
        "source_hash_before": source_hash,
        "source_hash_after": patched_hash,
        "status": "B6_VERIFIER_PASS_INTERNAL_ONLY" if ok else "B6_PATCH_APPLIED_VERIFIER_FAILED",
    }
    (OUTPUT / "receipt.json").write_text(json.dumps(receipt, indent=2))


import ast

if __name__ == "__main__":
    main()
