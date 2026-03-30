import pytest
from nexus.core.exit_codes import NexusExitCode, describe, requires_handoff, is_ci_blocking

def test_exit_code_enum():
    """驗證 Exit Code Enum 的數值正確性。"""
    assert NexusExitCode.SUCCESS == 0
    assert NexusExitCode.FAILED == 1
    assert NexusExitCode.ESCALATED == 2
    assert NexusExitCode.HUMAN_REVIEW == 3

def test_describe_mapping():
    """驗證 Exit Code 的文字描述對齊。"""
    assert "passed" in describe(NexusExitCode.SUCCESS).lower()
    assert "Human" in describe(NexusExitCode.HUMAN_REVIEW)
    assert "Unknown" in describe(999)

def test_requires_handoff_policy():
    """驗證哪些狀態代碼必須觸發交接 (Handoff)。"""
    assert requires_handoff(NexusExitCode.HUMAN_REVIEW) is True
    assert requires_handoff(NexusExitCode.SUCCESS) is False
    assert requires_handoff(NexusExitCode.FAILED) is False

def test_is_ci_blocking_policy():
    """驗證哪些狀態代碼應導致 CI 阻斷。"""
    assert is_ci_blocking(NexusExitCode.FAILED) is True
    assert is_ci_blocking(NexusExitCode.ESCALATED) is True
    assert is_ci_blocking(NexusExitCode.HUMAN_REVIEW) is True
    assert is_ci_blocking(NexusExitCode.SUCCESS) is False
