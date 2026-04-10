import time
import sys
import os

class TokenBucket:
    """
    🧬 Token Bucket (v22 Swarm)
    功能：實作加權限流，防止工具過度調用。
    """
    def __init__(self, rate: float, burst: int):
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_updated = time.time()

    def consume(self, amount: int = 1) -> bool:
        """嘗試取權杖"""
        now = time.time()
        elapsed = now - self.last_updated
        
        # 恢復權杖
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_updated = now
        
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False

class ShellAdapter:
    """
    💻 Cross-Platform Shell Adapter
    功能：OS 抽象層與執行速率管控。
    """
    def __init__(self, platform: str = sys.platform, rate: float = 2.0, burst: int = 10):
        self.platform = platform
        self.bucket = TokenBucket(rate=rate, burst=burst)
        self.mapping = {
            "win32": {
                "ls": "dir",
                "ls -G": "dir /w",
                "rm -rf": "rmdir /s /q",
                "grep": "findstr",
                "cat": "type"
            },
            "darwin": {
                "ls -G": "ls -G",
                "ls": "ls -G", # Mac 預設彩色
            }
        }

    def map_command(self, cmd: str) -> str:
        """根據平台轉譯指令 (OS Abstraction)"""
        if self.platform not in self.mapping:
            return cmd # Linux/Other (Unmodified)
        
        # 簡單的前綴替換
        for orig, target in self.mapping[self.platform].items():
            if cmd.startswith(orig):
                return cmd.replace(orig, target, 1)
        return cmd

    def can_run(self, cmd: str, weight: int = 1) -> bool:
        """檢查是否允許執行 (Rate Limit)"""
        return self.bucket.consume(weight)

# 🧬 Global instance (if enabled)
# 可透過 OrchestratorConfig 控制啟啟動
