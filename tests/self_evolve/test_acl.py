import pytest
from nexus.core.access_control_list import AccessControlList

def test_acl_default_roles():
    acl = AccessControlList()
    assert acl.check_permission("root", "any_tool") is True
    assert acl.check_permission("agent", "read_file") is True
    assert acl.check_permission("agent", "run_command") is False

def test_acl_role_expansion():
    acl = AccessControlList()
    role = "custom_agent"
    tool = "secret_tool"
    
    # Pre-check
    assert acl.check_permission(role, tool) is False
    
    # Add rule
    acl.add_rule(role, tool)
    assert acl.check_permission(role, tool) is True

def test_acl_tool_gate_logic():
    acl = AccessControlList()
    # 測試多重工具授權
    acl.add_rule("executor", "multi_replace")
    assert acl.check_permission("executor", "multi_replace") is True
    assert acl.check_permission("executor", "run_command") is True
