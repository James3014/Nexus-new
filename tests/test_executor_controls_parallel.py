import time
import unittest
import datetime
from unittest.mock import MagicMock, patch

from nexus.core.belief_contracts import CapabilityExecutionPlan, SkillSlot
from nexus.core.capability_registry import CapabilityRegistry, CapabilityInfo
from nexus.core.executor_controls import ExecutorControls


class TestExecutorControlsParallel(unittest.TestCase):
    def setUp(self):
        self.project_root = "/mock/project/root"
        # Mock Registry containing capabilities for the same phase
        self.mock_registry = MagicMock(spec=CapabilityRegistry)
        
        # Define mock capabilities that both belong to phase "X"
        self.cap1_info = CapabilityInfo(
            name="cap_parallel_1",
            phases=["X"],
            cost_weight=0.2,
            maturity="ACTIVE",
            default_skill="skill_1",
            allowed_heep_modes=["Mode A"]
        )
        self.cap2_info = CapabilityInfo(
            name="cap_parallel_2",
            phases=["X"],
            cost_weight=0.2,
            maturity="ACTIVE",
            default_skill="skill_2",
            allowed_heep_modes=["Mode A"]
        )
        
        def get_capability_mock(name):
            if name == "cap_parallel_1":
                return self.cap1_info
            if name == "cap_parallel_2":
                return self.cap2_info
            return None

        self.mock_registry.get_capability.side_name = "mock_get_capability"
        self.mock_registry.get_capability.side_effect = get_capability_mock

    def test_registry_injection_prevents_reinstantiation(self):
        """Verify that injecting a registry prevents reconstructing CapabilityRegistry."""
        controller = ExecutorControls(self.project_root, registry=self.mock_registry)
        
        plan = CapabilityExecutionPlan(
            plan_id="test_plan_registry",
            task_id="task_1",
            phases=["X"],
            required_capabilities=["cap_parallel_1"],
            skill_slots={
                "cap_parallel_1": [SkillSlot(role="LOGIC", skill_id="skill_1")]
            }
        )
        
        # Using patch to see if CapabilityRegistry class constructor is called
        with patch("nexus.core.capability_registry.CapabilityRegistry") as mock_registry_class:
            controller.execute_plan(plan)
            # Constructor of CapabilityRegistry should not be called
            mock_registry_class.assert_not_called()

    def test_same_phase_capabilities_executed_in_parallel(self):
        """Verify that same-phase capabilities run in parallel, reducing wall-time."""
        controller = ExecutorControls(self.project_root, registry=self.mock_registry)
        
        plan = CapabilityExecutionPlan(
            plan_id="test_plan_parallel",
            task_id="task_2",
            phases=["X"],
            required_capabilities=["cap_parallel_1", "cap_parallel_2"],
            skill_slots={
                "cap_parallel_1": [SkillSlot(role="LOGIC", skill_id="skill_1")],
                "cap_parallel_2": [SkillSlot(role="LOGIC", skill_id="skill_2")]
            }
        )

        # Mock the execution block to sleep for 0.15s per capability execution
        original_sleep = time.sleep
        sleep_duration = 0.15

        def mock_sleep(seconds):
            if seconds == sleep_duration:
                original_sleep(seconds)
            else:
                original_sleep(seconds)

        # We patch time.sleep inside the execution block
        with patch("time.sleep", side_effect=mock_sleep):
            start_time = time.time()
            
            original_now = datetime.datetime.now
            def mock_now(*args, **kwargs):
                time.sleep(sleep_duration)
                return original_now(*args, **kwargs)
            
            with patch("nexus.core.executor_controls.datetime") as mock_datetime:
                mock_datetime.now.side_effect = mock_now
                mock_datetime.timezone = datetime.timezone
                
                controller.execute_plan(plan)
                
            elapsed_time = time.time() - start_time
            
            # Since both cap_parallel_1 and cap_parallel_2 are in phase "X",
            # if run sequentially they would sleep at least 2 * 4 * sleep_duration = 1.2s.
            # If parallelized, they should complete in ~0.6s.
            # We assert that the elapsed time is less than 0.9s and greater than 0.4s.
            self.assertLess(elapsed_time, 0.9)
            self.assertGreater(elapsed_time, 0.4)


if __name__ == "__main__":
    unittest.main()
