from __future__ import annotations

import json
import os
import shutil
import tempfile
from unittest import mock

from scripts.local_heal.run_controlled_local_solve_fixture import main


def test_fixture_single_line_replacement() -> None:
    with tempfile.TemporaryDirectory() as src_root:
        test_file = "f.py"
        src_path = os.path.join(src_root, test_file)
        with open(src_path, "w", encoding="utf-8") as f:
            f.write("print('hello')\n")
            
        diff = """--- a/f.py
+++ b/f.py
@@ -1 +1 @@
-print('hello')
+print('world')
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            model_out_path = os.path.join(temp_dir, "model.diff")
            with open(model_out_path, "w", encoding="utf-8") as f:
                f.write(f"```diff\n{diff}```")
                
            output_json = os.path.join(temp_dir, "output.json")
            
            verifier_cmd = ["python3", "-c", "import pathlib; assert pathlib.Path('f.py').read_text() == 'print(\\'world\\')\\n'"]
            
            argv = [
                "run_controlled_local_solve_fixture.py",
                "--task-id", "t_fix1",
                "--source-root", src_root,
                "--target-file", test_file,
                "--target-symbol", "print",
                "--locked-search", "print('hello')",
                "--verifier-command-json", json.dumps(verifier_cmd),
                "--model-output-file", model_out_path,
                "--provider-mode", "injected",
                "--output-json", output_json,
            ]
            
            with mock.patch("sys.argv", argv):
                exit_code = main()
                
            assert exit_code == 0
            with open(output_json, "r", encoding="utf-8") as f:
                res = json.load(f)
                
            assert res["route_mode"] == "local_only_executed"
            assert res["gate_passed"] is True
            assert res["public_claim_allowed"] is False
            assert res["production_ready"] is False
            
            with open(src_path, "r", encoding="utf-8") as f:
                assert f.read() == "print('hello')\n"


def test_fixture_function_return_replacement() -> None:
    with tempfile.TemporaryDirectory() as src_root:
        test_file = "f.py"
        src_path = os.path.join(src_root, test_file)
        with open(src_path, "w", encoding="utf-8") as f:
            f.write("def add(a, b):\n    return a - b\n")
            
        diff = """--- a/f.py
+++ b/f.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            model_out_path = os.path.join(temp_dir, "model.diff")
            with open(model_out_path, "w", encoding="utf-8") as f:
                f.write(f"```diff\n{diff}```")
                
            output_json = os.path.join(temp_dir, "output.json")
            
            verifier_cmd = ["python3", "-c", "import sys; sys.path.append('.'); import f; assert f.add(2, 3) == 5"]
            
            argv = [
                "run_controlled_local_solve_fixture.py",
                "--task-id", "t_fix2",
                "--source-root", src_root,
                "--target-file", test_file,
                "--target-symbol", "add",
                "--locked-search", "def add(a, b):\n    return a - b",
                "--verifier-command-json", json.dumps(verifier_cmd),
                "--model-output-file", model_out_path,
                "--provider-mode", "injected",
                "--output-json", output_json,
            ]
            
            with mock.patch("sys.argv", argv):
                exit_code = main()
                
            assert exit_code == 0
            with open(output_json, "r", encoding="utf-8") as f:
                res = json.load(f)
                
            assert res["route_mode"] == "local_only_executed"
            assert res["gate_passed"] is True
            assert res["public_claim_allowed"] is False
            
            with open(src_path, "r", encoding="utf-8") as f:
                assert f.read() == "def add(a, b):\n    return a - b\n"


def test_fixture_outside_locked_span_blocked() -> None:
    with tempfile.TemporaryDirectory() as src_root:
        test_file = "f.py"
        src_path = os.path.join(src_root, test_file)
        with open(src_path, "w", encoding="utf-8") as f:
            f.write("line 1\nline 2\nline 3\nline 4\n")
            
        diff = """--- a/f.py
+++ b/f.py
@@ -2,1 +2,1 @@
-line 2
+line 2 modified
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            model_out_path = os.path.join(temp_dir, "model.diff")
            with open(model_out_path, "w", encoding="utf-8") as f:
                f.write(f"```diff\n{diff}```")
                
            output_json = os.path.join(temp_dir, "output.json")
            verifier_cmd = ["python3", "-c", "print(1)"]
            
            argv = [
                "run_controlled_local_solve_fixture.py",
                "--task-id", "t_fix3",
                "--source-root", src_root,
                "--target-file", test_file,
                "--target-symbol", "line",
                "--locked-search", "line 4",
                "--verifier-command-json", json.dumps(verifier_cmd),
                "--model-output-file", model_out_path,
                "--provider-mode", "injected",
                "--output-json", output_json,
            ]
            
            with mock.patch("sys.argv", argv):
                exit_code = main()
                
            assert exit_code == 0
            with open(output_json, "r", encoding="utf-8") as f:
                res = json.load(f)
                
            assert res["route_mode"] == "local_only_blocked"
            assert res["gate_passed"] is False
            assert "SEARCH_MISMATCH" in res["fallback_block_reason"]
            assert "patch_outside_locked_span" in res["fallback_block_reason"]


def test_fixture_verifier_fail_blocked() -> None:
    with tempfile.TemporaryDirectory() as src_root:
        test_file = "f.py"
        src_path = os.path.join(src_root, test_file)
        with open(src_path, "w", encoding="utf-8") as f:
            f.write("print('hello')\n")
            
        diff = """--- a/f.py
+++ b/f.py
@@ -1 +1 @@
-print('hello')
+print('world')
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            model_out_path = os.path.join(temp_dir, "model.diff")
            with open(model_out_path, "w", encoding="utf-8") as f:
                f.write(f"```diff\n{diff}```")
                
            output_json = os.path.join(temp_dir, "output.json")
            
            verifier_cmd = ["python3", "-c", "import sys; sys.exit(1)"]
            
            argv = [
                "run_controlled_local_solve_fixture.py",
                "--task-id", "t_fix4",
                "--source-root", src_root,
                "--target-file", test_file,
                "--target-symbol", "print",
                "--locked-search", "print('hello')",
                "--verifier-command-json", json.dumps(verifier_cmd),
                "--model-output-file", model_out_path,
                "--provider-mode", "injected",
                "--output-json", output_json,
            ]
            
            with mock.patch("sys.argv", argv):
                exit_code = main()
                
            assert exit_code == 0
            with open(output_json, "r", encoding="utf-8") as f:
                res = json.load(f)
                
            assert res["route_mode"] == "local_only_blocked"
            assert res["gate_passed"] is False
            assert "VERIFIER_FAIL" in res["fallback_block_reason"]


def test_fixture_missing_evidence_blocked() -> None:
    with tempfile.TemporaryDirectory() as src_root:
        test_file = "f.py"
        src_path = os.path.join(src_root, test_file)
        with open(src_path, "w", encoding="utf-8") as f:
            f.write("print('hello')\n")
            
        diff = """--- a/f.py
+++ b/f.py
@@ -1 +1 @@
-print('hello')
+print('world')
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            model_out_path = os.path.join(temp_dir, "model.diff")
            with open(model_out_path, "w", encoding="utf-8") as f:
                f.write(f"```diff\n{diff}```")
                
            output_json = os.path.join(temp_dir, "output.json")
            verifier_cmd = ["python3", "-c", "print(1)"]
            
            argv = [
                "run_controlled_local_solve_fixture.py",
                "--task-id", "t_fix_no_ev",
                "--source-root", src_root,
                "--target-file", test_file,
                "--target-symbol", "print",
                "--locked-search", "print('hello')",
                "--verifier-command-json", json.dumps(verifier_cmd),
                "--model-output-file", model_out_path,
                "--provider-mode", "injected",
                "--output-json", output_json,
                "--no-evidence",
            ]
            
            with mock.patch("sys.argv", argv):
                exit_code = main()
                
            assert exit_code == 0
            with open(output_json, "r", encoding="utf-8") as f:
                res = json.load(f)
                
            assert res["route_mode"] == "local_only_blocked"
            assert res["gate_passed"] is False
            assert "missing_required_control" in res["fallback_block_reason"]
            assert res["public_claim_allowed"] is False
            assert res["production_ready"] is False
