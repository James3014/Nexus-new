import importlib.util
import threading
import unittest

from nexus.verifiers.domain.common_core.state_guards import execute_with_double_checked_lock


class TestCore(unittest.TestCase):
    def test_locks(self):
        # lock_helpers was retired in Phase-2 batch C (#2584, ARCHIVED_2026-10-21_phase2_batch_C.md).
        self.assertIsNone(
            importlib.util.find_spec("nexus.verifiers.domain.common_core.lock_helpers")
        )
        
    def test_dcl(self):
        l = threading.Lock()
        state = []
        res = execute_with_double_checked_lock(l, lambda: not state, lambda: state.append(1))
        self.assertEqual(len(state), 1)
