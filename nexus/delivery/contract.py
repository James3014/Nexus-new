from __future__ import annotations

from pydantic import BaseModel

from nexus.delivery.models import TaskLevel


class DeliveryContract(BaseModel):
    task_level: TaskLevel
    min_verification_commands: int
    required_artifacts: int = 0


_CONTRACTS: dict[TaskLevel, DeliveryContract] = {
    TaskLevel.DOC: DeliveryContract(
        task_level=TaskLevel.DOC,
        min_verification_commands=1,
        required_artifacts=0,
    ),
    TaskLevel.SMALL_FIX: DeliveryContract(
        task_level=TaskLevel.SMALL_FIX,
        min_verification_commands=1,
        required_artifacts=0,
    ),
    TaskLevel.FEATURE: DeliveryContract(
        task_level=TaskLevel.FEATURE,
        min_verification_commands=2,
        required_artifacts=0,
    ),
    TaskLevel.DELIVERY: DeliveryContract(
        task_level=TaskLevel.DELIVERY,
        min_verification_commands=2,
        required_artifacts=1,
    ),
}


def contract_for_level(task_level: TaskLevel) -> DeliveryContract:
    return _CONTRACTS[task_level]
