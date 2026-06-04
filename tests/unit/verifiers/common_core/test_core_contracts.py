import unittest
import threading
from nexus.verifiers.domain.common_core.lock_helpers import acquire_locks_lexicographically, release_locks
from nexus.verifiers.domain.common_core.state_guards import execute_with_double_checked_lock

class TestCore(unittest.TestCase):
    def test_locks(self):
        l1, l2 = threading.Lock(), threading.Lock()
        locks = acquire_locks_lexicographically([l2, l1])
        self.assertEqual(len(locks), 2)
        release_locks(locks)
        
    def test_dcl(self):
        l = threading.Lock()
        state = []
        res = execute_with_double_checked_lock(l, lambda: not state, lambda: state.append(1))
        self.assertEqual(len(state), 1)
