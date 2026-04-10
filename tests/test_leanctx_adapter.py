import os
import unittest
import json
from unittest.mock import MagicMock, patch
from nexus.core.context_adapter import ContextAdapter
from scripts.ops.feynman_bridge import DualTrackAudit

class TestLeanCtxIntegration(unittest.TestCase):
    def test_dual_track_audit_compatibility(self):
        """Test DualTrackAudit handles both positional and keyword arguments."""
        auditor = DualTrackAudit()
        
        # Positional arguments (Legacy)
        res1 = auditor.run_advisory_audit("diff content", "task spec")
        self.assertEqual(res1["status"], "PASS")
        
        # Keyword arguments (New)
        res2 = auditor.run_advisory_audit(candidate="diff content", task="task spec")
        self.assertEqual(res2["status"], "PASS")
        
        # Mixed/Hybrid
        res3 = auditor.run_advisory_audit("diff content", task="task spec")
        self.assertEqual(res3["status"], "PASS")

    def test_context_adapter_legacy_switch(self):
        """Test ContextAdapter uses legacy provider when NEXUS_CONTEXT_PROVIDER=legacy."""
        mock_hub = MagicMock()
        mock_hub.assemble_context.return_value = "legacy context"
        
        with patch.dict(os.environ, {"NEXUS_CONTEXT_PROVIDER": "legacy"}):
            adapter = ContextAdapter(mock_hub)
            res = adapter.assemble_context("task-1", [1, 2])
            self.assertEqual(res, "legacy context")
            mock_hub.assemble_context.assert_called_once()

    @patch("subprocess.run")
    def test_context_adapter_leanctx_switch(self, mock_run):
        """Test ContextAdapter uses lean-ctx when NEXUS_CONTEXT_PROVIDER=leanctx."""
        mock_hub = MagicMock()
        mock_run.return_value = MagicMock(returncode=0, stdout="lean context output")
        
        with patch.dict(os.environ, {"NEXUS_CONTEXT_PROVIDER": "leanctx"}):
            adapter = ContextAdapter(mock_hub)
            res = adapter.assemble_context("task-1", [1, 2])
            self.assertEqual(res, "lean context output")
            mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_context_adapter_fallback(self, mock_run):
        """Test ContextAdapter falls back to legacy when lean-ctx fails."""
        mock_hub = MagicMock()
        mock_hub.assemble_context.return_value = "fallback legacy context"
        mock_run.side_effect = FileNotFoundError("lean-ctx not found")
        
        with patch.dict(os.environ, {"NEXUS_CONTEXT_PROVIDER": "leanctx"}):
            adapter = ContextAdapter(mock_hub)
            res = adapter.assemble_context("task-1", [1, 2])
            self.assertEqual(res, "fallback legacy context")
            mock_hub.assemble_context.assert_called_once()

    @patch("subprocess.run")
    def test_assemble_repair_pack_non_authoritative(self, mock_run):
        """Test lean-ctx is not authoritative for memory/router data in repair pack."""
        mock_hub = MagicMock()
        mock_hub.assemble_repair_pack.return_value = {
            "root_cause": "legacy",
            "memory_reminders": ["legacy-mem"],
            "recommended_skills": ["legacy-skill"]
        }
        mock_run.return_value = MagicMock(
            returncode=0, 
            stdout=json.dumps({"root_cause": "leanctx", "extra_info": "from-lean"})
        )
        
        with patch.dict(os.environ, {"NEXUS_CONTEXT_PROVIDER": "leanctx"}):
            adapter = ContextAdapter(mock_hub)
            diagnosis = MagicMock(summary="sum", hotspots=["f1"])
            res = adapter.assemble_repair_pack(diagnosis, [])
            
            # Should have leanctx data for basic fields
            self.assertEqual(res["root_cause"], "leanctx")
            self.assertEqual(res["extra_info"], "from-lean")
            # Should RETAIN legacy authoritative data
            self.assertEqual(res["memory_reminders"], ["legacy-mem"])
            self.assertEqual(res["recommended_skills"], ["legacy-skill"])

if __name__ == "__main__":
    unittest.main()
