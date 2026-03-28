from nexus.delivery.contract import contract_for_level
from nexus.delivery.models import TaskLevel


def test_doc_contract_requires_one_verification_command() -> None:
    contract = contract_for_level(TaskLevel.DOC)

    assert contract.min_verification_commands == 1
    assert contract.required_artifacts == 0


def test_feature_contract_requires_two_verification_commands() -> None:
    contract = contract_for_level(TaskLevel.FEATURE)

    assert contract.min_verification_commands == 2
    assert contract.required_artifacts == 0


def test_delivery_contract_requires_artifact_and_two_commands() -> None:
    contract = contract_for_level(TaskLevel.DELIVERY)

    assert contract.min_verification_commands == 2
    assert contract.required_artifacts == 1
