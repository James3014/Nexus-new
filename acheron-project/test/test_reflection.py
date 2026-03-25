from core.mirror import PyMirror

def test_no_leak():
    mirror = PyMirror()
    # 初始狀態應該是 ghost
    assert str(mirror.phantom) == "ghost"
    mirror.process([1, 2, 3])
    # 修復後應該不含 leaked
    assert "leaked" not in str(mirror.phantom)
