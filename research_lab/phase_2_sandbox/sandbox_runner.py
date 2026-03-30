import os
import shutil
import subprocess
import tempfile
from pathlib import Path

class NexusSandbox:
    def __init__(self, source_dir: Path):
        self.source_dir = Path(source_dir)
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="nexus_research_"))
        
    def setup(self):
        """Fork the codebase into a sandbox."""
        print(f"🔬 [Sandbox] Forking {self.source_dir} -> {self.tmp_dir}")
        # Use shutil.copytree but ignore .git or heavy dirs for speed in research
        shutil.copytree(self.source_dir, self.tmp_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns('.git', '.venv', '__pycache__'))
        
    def apply_patch(self, relative_path: str, new_content: str):
        """Blue Team: Apply a candidate fix."""
        target = self.tmp_dir / relative_path
        print(f"🛠️ [Blue Team] Applying patch to {relative_path}")
        target.write_text(new_content)
        
    def verify(self, command: str) -> bool:
        """Red Team: Run validation in the isolated sandbox."""
        print(f"⚔️ [Red Team] Executing verification: {command}")
        result = subprocess.run(command, shell=True, cwd=self.tmp_dir, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ [Validation] SUCCESS in Sandbox.")
            return True
        else:
            print("❌ [Validation] FAILED in Sandbox.")
            print(f"Error Context: {result.stderr[:200]}")
            return False

    def cleanup(self):
        shutil.rmtree(self.tmp_dir)

# --- Simulation Logic ---
if __name__ == "__main__":
    # 1. Prepare a Mock Project with a bug
    mock_root = Path("/Users/jameschen/Workspace/nexus/research_lab/phase_2_sandbox/mock_proj")
    src_file = mock_root / "src" / "logic.py"
    src_file.parent.mkdir(parents=True, exist_ok=True)
    src_file.write_text("def calculate(a, b):\n    return a / b  # Bug: ZeroDivisionError not handled")
    
    test_file = mock_root / "test_logic.py"
    test_file.write_text("from src.logic import calculate\ntry:\n    assert calculate(10, 0) == 0\n    print('TEST_PASS')\nexcept Exception as e:\n    print(f'TEST_FAIL: {e}')\n    exit(1)")

    # 2. Run the Sandbox Loop
    sandbox = NexusSandbox(mock_root)
    try:
        sandbox.setup()
        
        # Verify initial state (should fail)
        print("\n--- Initial State ---")
        sandbox.verify("python3 test_logic.py")
        
        # Apply Fix (Blue Team)
        fix = "def calculate(a, b):\n    if b == 0: return 0\n    return a / b"
        sandbox.apply_patch("src/logic.py", fix)
        
        # Verify Final State (should pass)
        print("\n--- After Repair ---")
        if sandbox.verify("python3 test_logic.py"):
            print("💎 [Verdict] Patch is SAFE for main deployment.")
        
    finally:
        # sandbox.cleanup() # Keep for Sir to inspect if needed
        print(f"\n📁 [Inspection] Sandbox remains at: {sandbox.tmp_dir}")
