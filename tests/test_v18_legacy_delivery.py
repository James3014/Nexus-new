from pathlib import Path
from importlib.util import module_from_spec
from importlib.util import spec_from_file_location
from unittest.mock import MagicMock


ROOT = Path(__file__).resolve().parents[1]


def _load_module(module_name: str, relative_path: str):
    file_path = ROOT / relative_path
    spec = spec_from_file_location(module_name, file_path)
    module = module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_v18_mega_routes_bug_through_command_service():
    module = _load_module("v18_mega", "scripts/v1.8_mega.py")
    service = MagicMock()
    service.execute_bug.return_value = True
    task = {"id": "BUG-301", "desc": "Fix recursion depth error in Jinja lexer"}

    success = module.execute_bug_task(service, task)

    assert success is True
    service.execute_bug.assert_called_once_with(
        "Fix recursion depth error in Jinja lexer",
        delivery_mode="standard",
        bug_id="BUG-301",
    )


def test_v18_feature_bench_routes_feature_through_command_service():
    module = _load_module("v18_feature_bench", "scripts/v1.8_feature_bench.py")
    service = MagicMock()
    service.execute_feature.return_value = True
    task = {"id": "FEAT-401", "desc": "新增 profile endpoint"}

    success = module.execute_feature_task(service, task)

    assert success is True
    service.execute_feature.assert_called_once_with(
        "新增 profile endpoint",
        delivery_mode="standard",
    )
