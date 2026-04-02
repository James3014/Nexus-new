import pytest
from nexus.core.shadow_auditor import ShadowAuditor, RBACViolation

def test_coder_rbac_authorized():
    """核驗 Coder 角色獲權呼叫 file_write"""
    assert ShadowAuditor.check_rbac("Coder", "file_write") is True

def test_coder_rbac_unauthorized():
    """核驗 Coder 角色無權呼叫 git_push (應拋出 RBACViolation)"""
    with pytest.raises(RBACViolation) as excinfo:
        ShadowAuditor.check_rbac("Coder", "git_push")
    assert "角色 Coder 權限不足，禁止呼叫: git_push" in str(excinfo.value)

def test_manager_rbac_authorized():
    """核驗 Manager 角色獲權呼叫 git_push"""
    assert ShadowAuditor.check_rbac("Manager", "git_push") is True

def test_reviewer_rbac_unauthorized_write():
    """核驗 Reviewer 唯讀角色攔截寫入工具"""
    with pytest.raises(RBACViolation):
        ShadowAuditor.check_rbac("Reviewer", "file_write")

def test_default_role_fallback():
    """核驗未知角色回退至 Coder 權限"""
    # Coder 權限允許 file_write
    assert ShadowAuditor.check_rbac("Unknown", "file_write") is True
    # Coder 權限不允許 git_push
    with pytest.raises(RBACViolation):
        ShadowAuditor.check_rbac("Unknown", "git_push")
