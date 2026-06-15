import pytest
from pathlib import Path
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
from nexus.services.local_heal.patcher import Patcher
from nexus.services.local_heal.patch_applier import PatchApplier

def test_patch_applier_success(tmp_path):
    # 建立測試檔案
    file_path = tmp_path / "calc.py"
    file_path.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    
    parser = SolidSearchReplaceProtocol()
    patcher = Patcher()
    applier = PatchApplier(parser, patcher)
    
    # 解析 patch
    patch_text = (
        "FILE: calc.py\n"
        "<<<<<<< SEARCH\n"
        "def add(a, b):\n"
        "    return a - b\n"
        "=======\n"
        "def add(a, b):\n"
        "    return a + b\n"
        ">>>>>>> REPLACE\n"
    )
    
    intents = parser.parse(patch_text)
    assert not isinstance(intents, Exception)
    
    res = applier.apply_and_validate(
        intents=intents,
        repo_dir=tmp_path,
        localized_files=[("calc.py", "def add(a, b):\n    return a - b\n")]
    )
    
    assert res.success is True
    assert "calc.py" in res.applied_diffs[0]
    assert "+    return a + b" in res.applied_diffs[0]
    assert file_path.read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"

def test_patch_applier_match_gate_failure(tmp_path):
    # 建立測試檔案，但是內容不符合 SEARCH
    file_path = tmp_path / "calc.py"
    file_path.write_text("def add(a, b):\n    return a * b\n", encoding="utf-8")
    
    parser = SolidSearchReplaceProtocol()
    patcher = Patcher()
    applier = PatchApplier(parser, patcher)
    
    patch_text = (
        "FILE: calc.py\n"
        "<<<<<<< SEARCH\n"
        "def add(a, b):\n"
        "    return a - b - c - d - e - f - g\n"
        "=======\n"
        "def add(a, b):\n"
        "    return a + b\n"
        ">>>>>>> REPLACE\n"
    )
    
    intents = parser.parse(patch_text)
    res = applier.apply_and_validate(
        intents=intents,
        repo_dir=tmp_path,
        localized_files=[("calc.py", "def add(a, b):\n    return a * b\n")]
    )
    
    assert res.success is False
    assert res.failure_reason == "SEARCH_MISMATCH"

def test_patch_applier_syntax_gate_failure(tmp_path):
    file_path = tmp_path / "calc.py"
    file_path.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    
    parser = SolidSearchReplaceProtocol()
    patcher = Patcher()
    applier = PatchApplier(parser, patcher)
    
    # 寫出有語法錯誤的 code
    patch_text = (
        "FILE: calc.py\n"
        "<<<<<<< SEARCH\n"
        "def add(a, b):\n"
        "    return a - b\n"
        "=======\n"
        "def add(a, b):\n"
        "    return a +  # Syntax Error\n"
        ">>>>>>> REPLACE\n"
    )
    
    intents = parser.parse(patch_text)
    res = applier.apply_and_validate(
        intents=intents,
        repo_dir=tmp_path,
        localized_files=[("calc.py", "def add(a, b):\n    return a - b\n")]
    )
    
    assert res.success is False
    assert res.syntax_gate_passed is False
    assert res.failure_reason == "SYNTAX_ERROR"
