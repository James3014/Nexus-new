import pytest
import time
from scripts.core.shell_adapter import ShellAdapter, TokenBucket

def test_token_bucket_initial_burst():
    # 設置大桶 5 個 Token
    bucket = TokenBucket(rate=1, burst=5)
    
    # 前 5 次請求應成功
    for _ in range(5):
        assert bucket.consume(1) is True
    
    # 第 6 次請求應失敗 (除非時間流逝夠快)
    assert bucket.consume(1) is False

def test_token_bucket_refill():
    # 速率為每秒 2 個 Token
    bucket = TokenBucket(rate=2, burst=2)
    assert bucket.consume(2) is True
    assert bucket.consume(1) is False
    
    # 等待 0.5 秒，預期恢復 1 個 Token
    time.sleep(0.55)
    assert bucket.consume(1) is True

def test_shell_adapter_platform_mapping():
    # 模擬 Mac 平台
    adapter = ShellAdapter(platform="darwin")
    
    # 測試列表指令映射
    assert adapter.map_command("ls -G") == "ls -G" # Mac 改色
    
    # 模擬 Windows 平台
    win_adapter = ShellAdapter(platform="win32")
    assert win_adapter.map_command("ls") == "dir"
    assert win_adapter.map_command("rm -rf foo") == "rmdir /s /q foo"

def test_weighted_rate_limit():
    adapter = ShellAdapter(rate=10, burst=10)
    
    # 輕量指令 (Weight: 1)
    assert adapter.can_run("ls", weight=1) is True
    
    # 重量級指令 (Weight: 8)
    assert adapter.can_run("nexus:swarm", weight=8) is True
    
    # 超過剩餘容量
    assert adapter.can_run("nexus:swarm", weight=8) is False
