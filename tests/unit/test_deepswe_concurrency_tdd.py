import pytest
from nexus.services.local_heal.parser import LockGranularityChecker, AtomicBlockSynthesizer

def test_lock_granularity_checker_race_window():
    checker = LockGranularityChecker()
    
    # 程式碼中有 sleep 且沒有 wrapped inside lock 的潛在 race window
    vulnerable_code = "def transfer(amount):\n    time.sleep(0.001)\n    balance -= amount\n"
    assert checker.has_unprotected_race(vulnerable_code) is True
    
    # 完美被鎖保護的安全程式碼
    safe_code = "def transfer(amount):\n    with self.lock:\n        time.sleep(0.001)\n        balance -= amount\n"
    assert checker.has_unprotected_race(safe_code) is False

def test_atomic_block_synthesizer_wrapping():
    synthesizer = AtomicBlockSynthesizer()
    
    # 遺漏鎖保護的程式碼
    bare_code = "time.sleep(0.001)\nself.active += 1"
    
    # 應能自動使用 context manager 整形包裝 unparse
    wrapped_code = synthesizer.wrap_with_lock(bare_code, "self.lock", "    ")
    
    assert "with self.lock:" in wrapped_code
    assert "    time.sleep(0.001)" in wrapped_code
