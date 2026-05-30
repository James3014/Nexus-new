import pytest
from nexus.services.local_heal.micromerger import EnvContextPerceiver, ASTMicroMerger

def test_env_context_perceiver_indentation():
    perceiver = EnvContextPerceiver()
    
    # 測試 4 格空格縮排
    code_4spaces = "def hello():\n    return 42\n"
    assert perceiver.detect_indent(code_4spaces) == "    "
    
    # 測試 2 格空格縮排
    code_2spaces = "def hello():\n  return 42\n"
    assert perceiver.detect_indent(code_2spaces) == "  "
    
    # 測試 Tab 縮排
    code_tab = "def hello():\n\treturn 42\n"
    assert perceiver.detect_indent(code_tab) == "\t"

def test_ast_micro_merger_indents():
    merger = ASTMicroMerger()
    
    # 模擬 LLM 產生的殘缺縮排補丁
    broken_code = "def hello():\nreturn 42"
    
    # AST 微微調融合應能自動將其融合並整形為正確縮排 (預設為 4 格)
    fixed_code = merger.fix_indentation(broken_code, "    ")
    
    # 驗證 unparse 整形結果
    assert "    return 42" in fixed_code
