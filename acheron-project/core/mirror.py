from core.memory import MemoryMirror  # 跨語言引用

class PyMirror:
    def __init__(self):
        self._rust_mirror = MemoryMirror()  # 這裡 RefObject 字段對應 Rust 型別出錯
        self.phantom = self._rust_mirror.phantom  # 幽靈引用暴露
    
    def process(self, data: list) -> str:
        # 模擬呼叫序列觸發錯誤
        # 假想這裡透過 PyO3 暴露了 borrow_mut，實際上會踩到 lifetime mismatch
        self._rust_mirror.phantom.borrow_mut().push_str("leaked")  # PyO3 lifetime mismatch
        return f"Processed {len(data)} items"
