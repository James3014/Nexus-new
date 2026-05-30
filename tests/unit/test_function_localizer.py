import pytest
from nexus.services.local_heal.function_localizer import FunctionLocalizer

def test_function_localizer_extracts_correct_function():
    code = (
        "class A:\n"
        "    def foo(self):\n"
        "        return 1\n"
        "def bar():\n"
        "    return 2\n"
    )
    localizer = FunctionLocalizer()
    funcs = localizer.extract_functions(code)
    # 預期能找到 A.foo 與 bar
    func_names = [f["name"] for f in funcs]
    assert "foo" in func_names or "A.foo" in func_names
    assert "bar" in func_names

def test_function_localizer_scores_functions_by_issue():
    code = (
        "def calculate_total(price, tax):\n"
        "    return price + tax\n"
        "\n"
        "def print_hello():\n"
        "    print('hello')\n"
    )
    localizer = FunctionLocalizer()
    funcs = localizer.extract_functions(code)
    scored = localizer.score_functions(funcs, "Need to fix total calculation tax computation")
    # 第一個函數相關度應該顯著高於第二個
    assert scored[0]["name"] == "calculate_total"

def test_function_localizer_builds_focused_context():
    code = (
        "import math\n"
        "\n"
        "def calculate_total(price, tax):\n"
        "    return price + tax\n"
        "\n"
        "def print_hello():\n"
        "    print('hello')\n"
    )
    localizer = FunctionLocalizer()
    ctx = localizer.build_focused_context("calculate_total", code, "Need to fix total calculation")
    assert "calculate_total" in ctx
    assert "math" in ctx  # 應保留 globals/imports
    assert "def print_hello" not in ctx  # 無關代碼被裁剪
