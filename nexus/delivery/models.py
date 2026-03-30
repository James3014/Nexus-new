from __future__ import annotations

from datetime import UTC
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel
from pydantic import Field


class TaskLevel(str, Enum):
    DOC = "doc"
    SMALL_FIX = "small_fix"
    FEATURE = "feature"
    DELIVERY = "delivery"


class CompletionStatus(str, Enum):
    IMPLEMENTED = "implemented"
    PARTIALLY_VERIFIED = "partially_verified"
    VERIFIED = "verified"
    DELIVERY_READY = "delivery_ready"


class VerificationRecord(BaseModel):
    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    passed: bool = False


class CompletionRequest(BaseModel):
    task_name: str
    task_level: TaskLevel
    verification_commands: list[str] = Field(default_factory=list)
    artifact_paths: list[Path] = Field(default_factory=list)
    cwd: Path


class CompletionResult(BaseModel):
    task_name: str
    task_level: TaskLevel
    status: CompletionStatus
    gate_passed: bool
    summary: str
    verification_records: list[VerificationRecord] = Field(default_factory=list)
    existing_artifacts: list[Path] = Field(default_factory=list)
    missing_artifacts: list[Path] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def passed_commands(self) -> int:
        return sum(1 for record in self.verification_records if record.passed)

    @property
    def failed_commands(self) -> int:
        return sum(1 for record in self.verification_records if not record.passed)
