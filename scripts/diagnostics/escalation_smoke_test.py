import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import sys
import os

# Ensure project root is in path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from nexus.services.reviewer import CodexLoopV2
from nexus.executors.protocol import ExecutorOutput, ExecutorStatusEnum, TaskInstruction, ExecutorMeta

class TestEscalationPipeline(unittest.TestCase):
    def setUp(self):
        self.mock_executor = MagicMock()
        self.mock_git = MagicMock()
        self.mock_git.project_root = "/tmp"
        self.mock_git.get_changes.return_value = (["test.py"], "diff content")
        
    @patch("scripts.codex_loop_brain.build_action_brief")
    @patch("scripts.codex_loop_brain.derive_task_metadata")
    def test_escalation_feedback_loop(self, mock_derive, mock_build_brief):
        # Setup mocks
        mock_derive.return_value = MagicMock()
        mock_brief = MagicMock()
        mock_brief.instructions = "FIX THE LINTER"
        mock_brief.title = "Review Feedback"
        mock_build_brief.return_value = mock_brief
        
        # Mock Executor to FAIL first, then SUCCESS
        fail_output = ExecutorOutput(
            executor_name="test-gemini",
            phase="P",
            status=ExecutorStatusEnum.EXECUTION_FAIL,
            patch_generated=False,
            evidence_present=True,
            raw_exit_code=1,
            summary="Linter failed"
        )
        success_output = ExecutorOutput(
            executor_name="test-gemini",
            phase="R",
            status=ExecutorStatusEnum.SUCCESS,
            patch_generated=False,
            evidence_present=True,
            raw_exit_code=0,
            summary="Fixed"
        )
        self.mock_executor.execute.side_effect = [fail_output, success_output]
        
        # Initialize Core with 3 max strikes (developer mode default)
        engine = CodexLoopV2(
            mode="developer",
            executor=self.mock_executor,
            git=self.mock_git,
            apply_patch=False
        )
        engine.max_strikes = 3
        
        # Trigger review
        with patch.object(Path, "read_text", return_value="test code"), \
             patch.object(Path, "is_file", return_value=True), \
             patch.object(engine.linter, "scan", return_value="[]"), \
             patch.object(engine, "_verify_work", return_value=True):
            engine._do_review(manual_files=["test.py"])
            
        # Assertions
        # 1. build_action_brief was called after FAIL
        self.assertTrue(mock_build_brief.called)
        
        # 2. Executor was called twice (initial + retry)
        self.assertEqual(self.mock_executor.execute.call_count, 2)
        
        # 3. Instruction of the second call contains FEEDBACK
        second_call_input = self.mock_executor.execute.call_args_list[1][0][0]
        self.assertIn("FIX THE LINTER", second_call_input.instruction.objective)

    def test_benchmark_no_retry(self):
        # Mock Executor to FAIL
        fail_output = ExecutorOutput(
            executor_name="test-gemini",
            phase="P",
            status=ExecutorStatusEnum.EXECUTION_FAIL,
            patch_generated=False,
            evidence_present=True,
            raw_exit_code=1,
            summary="Linter failed"
        )
        self.mock_executor.execute.return_value = fail_output
        
        # Initialize Core in benchmark mode (executor != None)
        engine = CodexLoopV2(
            mode="developer",
            executor=self.mock_executor,
            git=self.mock_git,
            apply_patch=False
        )
        # Verify strike lock to 1
        self.assertEqual(engine.max_strikes, 1)
        
        # Trigger review
        with patch.object(Path, "read_text", return_value="test code"), \
             patch.object(Path, "is_file", return_value=True), \
             patch.object(engine.linter, "scan", return_value="[]"), \
             patch.object(engine, "_verify_work", return_value=True):
            engine._do_review(manual_files=["test.py"])
            
        # Assertions
        # Executor was called ONLY once
        self.assertEqual(self.mock_executor.execute.call_count, 1)

if __name__ == "__main__":
    unittest.main()
