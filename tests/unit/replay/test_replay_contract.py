import unittest
from nexus.replay.replay_artifact import ReplayArtifact

class TestReplayContract(unittest.TestCase):
    def test_missing_fields_raises_value_error(self):
        # 故意缺失 cwd 與 timeout
        with self.assertRaises(ValueError):
            art = ReplayArtifact(
                task_id="t1", status="SUCCESS", 
                repro_command="pytest", cwd="", timeout_sec=0, 
                pass_fail_evidence=[]
            )
            art.validate()

    def test_valid_artifact_passes_validation(self):
        art = ReplayArtifact(
            task_id="t1", status="SUCCESS", 
            repro_command="pytest", cwd="/tmp", timeout_sec=60, 
            pass_fail_evidence=["test passed"]
        )
        art.validate() # 應不拋出異常

if __name__ == "__main__":
    unittest.main()
