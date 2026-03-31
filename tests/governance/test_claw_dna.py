import pytest
from nexus.core.parity_audit import ParityAuditor, ParityViolation
from nexus.core.command_dag import CommandDAG, CommandLockedError
from nexus.core.cost_hook import CostHook
from nexus.core.ink_parser import InkParser
from nexus.core.state_contracts import NexusState

# ⚖️ P5.7: Parity Audit Tests
def test_parity_audit_missing_func():
    auditor = ParityAuditor(".")
    before = "def old_func(): pass\ndef keep_me(): pass"
    after = "def keep_me(): pass" # old_func missing
    
    res = auditor.audit_patch(before, after, "test.py")
    assert res["surface_match"] is False
    assert "func:old_func()" in res["missing_funcs"]

def test_parity_audit_safe_refactor():
    auditor = ParityAuditor(".")
    before = "def func_a(): pass"
    after = "def func_a():\n    print('hello')" # logic changed, surface matches
    
    res = auditor.audit_patch(before, after, "test.py")
    assert res["surface_match"] is True

# 🕹️ P5.8: Command DAG Tests
def test_command_dag_planning_restricted():
    dag = CommandDAG("X") # PLANNING stage
    assert dag.validate("read_file") is True
    with pytest.raises(CommandLockedError):
        dag.validate("edit_file") # edit forbidden in X stage

def test_command_dag_repair_allowed():
    dag = CommandDAG("R") # REPAIRING stage
    assert dag.validate("edit_file") is True
    assert dag.validate("safe_patch") is True

# 💰 P5.9: Cost Hook Tests
def test_cost_hook_budget_blocked():
    hook = CostHook()
    # Predicted 1500 + 300 = 1800
    # Remaining 1000
    status = hook.budget_check(1800, 1000)
    assert status == "BLOCKED"

def test_cost_hook_warn():
    hook = CostHook()
    # Predicted 800
    # Remaining 1000 (800 > 700)
    status = hook.budget_check(800, 1000)
    assert status == "WARN_OPTIMIZE"

# 🎨 P5.10: Ink Parser Tests
def test_ink_parser_basic():
    parser = InkParser()
    content = "ink-read<nexus/core/utils.py>\nink-edit<nexus/core/utils.py><old><new>"
    commands = parser.parse(content)
    
    assert len(commands) == 2
    assert commands[0].type == "read"
    assert commands[0].target == "nexus/core/utils.py"
    assert commands[1].type == "edit"
    assert commands[1].params["p1"] == "new"

def test_ink_to_formal():
    parser = InkParser()
    ink_cmd = parser.parse("ink-read<main.py>")[0]
    formal = parser.to_formal(ink_cmd)
    assert formal["tool"] == "read_file"
    assert formal["args"]["path"] == "main.py"
