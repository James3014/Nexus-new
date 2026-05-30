import ast

class LockGranularityChecker:
    """負責分析臨界區高併發安全度的組件 (SRP)"""
    def has_unprotected_race(self, code: str) -> bool:
        """判定代碼中是否存在 unprotected sleep 或潛在的 Race Window"""
        has_sleep = "time.sleep" in code
        has_lock = "with self.lock" in code or "with self._lock" in code or "with lock" in code
        if has_sleep and not has_lock:
            return True
        return False


class AtomicBlockSynthesizer:
    """負責將併發代碼塊自動包裝合成為 Thread-safe 原子結構的引擎 (Linus 原則)"""
    def wrap_with_lock(self, code_block: str, lock_name: str, indent: str) -> str:
        """將多行併發語句安全包裝在 with lock: 上下文管理器中，重新 unparse 輸出"""
        wrapped_lines = [f"with {lock_name}:"]
        for line in code_block.splitlines():
            wrapped_lines.append(indent + line)
        
        try:
            node = ast.parse("\n".join(wrapped_lines))
            return ast.unparse(node)
        except Exception:
            return "\n".join(wrapped_lines)
