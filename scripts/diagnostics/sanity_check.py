import sys
import os
import unittest
import json
from unittest.mock import MagicMock
from pathlib import Path

# Ensure we can import nexus and scripts
sys.path.append(os.getcwd())

from nexus.services.reviewer import CodexLoopV2
from nexus.executors.gemini import GeminiExecutor
from nexus.executors.protocol import ExecutorStatusEnum, ExecutorOutput, ProviderErrorType

class NexusSanityCheck(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(os.getcwd()).resolve()
        self.mock_git = MagicMock()
        self.mock_git.project_root = self.repo_root
        self.mock_linter = MagicMock()
        self.mock_linter.scan.return_value = "[]"
        self.mock_commander = MagicMock()
        self.mock_commander.get_crystal_lessons.return_value = ["💎 Sanity Check Rule"]
        # Use a non-core file for safety check
        self.target_file = str(self.repo_root / "dummy_target.py")

    def test_1_executor_status(self):
        """1. Output executor status (Name, Model, Sandbox)."""
        print("\n--- [STEP 1: EXECUTOR STATUS] ---")
        executor = GeminiExecutor()
        print(f"✅ Executor Name: {getattr(executor, 'executor_name', 'gemini_adapter_v1')}")
        print(f"✅ Model: {executor.model_name}")
        print(f"✅ Sandbox Path: {executor.sandbox_dir}")
        self.assertTrue(executor.sandbox_dir.exists())

    def test_2_context_integrity(self):
        """2. Validate context statistics (Privileged Counter)."""
        print("\n--- [STEP 2: CONTEXT INTEGRITY] ---")
        mock_executor = MagicMock(spec=GeminiExecutor)
        mock_executor.execute.return_value = ExecutorOutput(
            executor_name="mock", phase="R", status=ExecutorStatusEnum.SUCCESS, 
            patch_generated=False, evidence_present=True, raw_exit_code=0, 
            files_touched=[]
        )
        
        engine = CodexLoopV2(
            executor=mock_executor, 
            initial_files=[self.target_file], 
            git=self.mock_git,
            linter=self.mock_linter,
            commander=self.mock_commander
        )
        engine._apply_persona_profile("developer")
        self.mock_git.get_changes.return_value = ([], "")
        
        # This should call executor because target_file is not in core
        engine.run_review()
        
        self.assertTrue(mock_executor.execute.called, "Executor was not called!")
        call_args = mock_executor.execute.call_args[0][0]
        privileged_count = len([f for f in call_args.context_pack.files if Path(f).resolve() == Path(self.target_file).resolve()])
        
        print(f"✅ Privileged Context Count: {privileged_count}")
        self.assertGreaterEqual(privileged_count, 1)

    def test_3_legacy_path_lock(self):
        """3. Explicitly prove legacy path is locked."""
        print("\n--- [STEP 3: LEGACY PATH LOCK] ---")
        mock_executor = MagicMock(spec=GeminiExecutor)
        engine = CodexLoopV2(executor=mock_executor, git=self.mock_git)
        
        engine.llm = MagicMock()
        engine.linter = self.mock_linter
        engine.commander = self.mock_commander
        engine._apply_persona_profile("developer")
        self.mock_git.get_changes.return_value = ([], "")
        
        # Simulate executor missing but lock engaged
        engine.executor = None 
        with self.assertRaises(RuntimeError) as cm:
            # Pass manual_files that are NOT in core to reach the lock check
            engine.run_review(manual_files=[self.target_file])
            
        print(f"✅ Lock Error Caught: {cm.exception}")
        self.assertIn("Pattern Lock", str(cm.exception))

if __name__ == "__main__":
    print("\n🚀 [NEXUS SANITY CHECK STARTING]")
    suite = unittest.TestLoader().loadTestsFromTestCase(NexusSanityCheck)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    
    if result.wasSuccessful():
        print("\n💎 SANITY_CHECK_PASSED")
        sys.exit(0)
    else:
        print("\n🚨 SANITY_CHECK_FAILED")
        sys.exit(1)
