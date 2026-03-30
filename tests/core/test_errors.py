import pytest
from nexus.core.errors import NexusError, PhaseError, ValidationError, InfrastructureError, safe_phase

def test_nexus_error_details():
    """驗證 NexusError 是否能正確攜帶細節資訊。"""
    msg = "Test error"
    details = {"code": 500}
    e = NexusError(msg, details=details)
    assert str(e) == msg
    assert e.details == details

def test_safe_phase_decorator_success():
    """驗證 safe_phase 裝飾器在成功時的行為。"""
    @safe_phase("test_phase")
    def my_func():
        return 42
    assert my_func() == 42

def test_safe_phase_decorator_known_error():
    """驗證 safe_phase 裝飾器對已知錯誤 (NexusError) 的透傳。"""
    @safe_phase("test_phase")
    def my_func():
        raise ValidationError("Invalid data")
    
    with pytest.raises(ValidationError, match="Invalid data"):
        my_func()

def test_safe_phase_decorator_unknown_error():
    """驗證 safe_phase 裝飾器對未知錯誤的捕獲與轉換。"""
    @safe_phase("test_phase")
    def my_func():
        raise RuntimeError("Crash")
    
    with pytest.raises(PhaseError, match="Unexpected crash in test_phase"):
        my_func()
