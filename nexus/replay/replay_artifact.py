from dataclasses import dataclass, field
from typing import Sequence, Optional

@dataclass(frozen=True)
class ReplayArtifact:
    """
    🔄 Replay Artifact Contract
    職責: 純粹記錄物理重播事實，不負責任判定。
    """
    task_id: str
    status: str # SUCCESS, FAILURE, ERROR
    repro_command: str
    cwd: str
    timeout_sec: int
    pass_fail_evidence: Sequence[str]
    failure_reason: Optional[str] = None

    def validate(self):
        """物理級檢查契約完整性"""
        if not all([self.repro_command, self.cwd, self.timeout_sec]):
            raise ValueError("Incomplete ReplayArtifact: Missing repro_command, cwd, or timeout.")
