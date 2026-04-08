import pytest
from pydantic import ValidationError
from nexus.models.enums import TaskType
from nexus.models.planner_models import ImplementationPackSchema

def test_enum_logic_enforcement():
    # 使用 Enum 調用，IDE 會自動補全且保證拼寫正確
    pack = ImplementationPackSchema(task_id="T1", goal="UI Task", task_type=TaskType.UI)
    assert pack.task_type == "ui"

def test_invalid_string_rejection():
    # 嘗試傳入非法的字串 (例如拼錯)
    with pytest.raises(ValidationError):
        # Pydantic 會自動根據 Enum 進行校驗
        ImplementationPackSchema(task_id="T1", goal="Bad Task", task_type="frontend")

def test_case_insensitivity_handled():
    # 即使傳入字串，只要是在 Enum 值範圍內，Pydantic 也能處理
    pack = ImplementationPackSchema(task_id="T1", goal="UI Task", task_type="ui")
    assert pack.task_type == TaskType.UI
