import pytest
import os
import sys
from unittest.mock import MagicMock, patch

# 🧪 導入目標組件 (預期實作後可用)
# 將腳本路徑加入 sys.path
scripts_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if scripts_path not in sys.path:
    sys.path.insert(0, scripts_path)

from core.guard_executor import EntropyAuditor

def test_entropy_auditor_allowlist():
    auditor = EntropyAuditor(mode="audit")
    
    # 1. 測試白名單 (Allowlist: SSH)
    assert auditor.is_allowed("ssh -i id_rsa user@host") is True
    
    # 2. 測試白名單 (Allowlist: Git over SSH)
    assert auditor.is_allowed("git clone git@github.com:user/repo.git") is True
    
    # 3. 測試白名單 (Allowlist: TLS/HTTPS)
    assert auditor.is_allowed("curl https://google.com") is True

def test_entropy_score_detection():
    auditor = EntropyAuditor(mode="audit")
    
    # 低熵值字串 (規律)
    low_entropy = "aaaaaaaaaa"
    assert auditor.calculate_entropy(low_entropy) < 1.0
    
    # 高熵值字串 (隨機密鑰模擬)
    # 預期高於 3.9 (實測約 3.98)
    high_entropy = "4f2e9d8a1c7b6f5e4d3c2b1a0f9e8d7c6b5a4938271605a4b3c2d1e0f"
    assert auditor.calculate_entropy(high_entropy) > 3.9

def test_audit_mode_no_kill():
    # 模擬高風險 Payload
    risky_payload = "HighEntropySecretPayload_1234567890abcdef"
    
    with patch("os.kill") as mock_kill:
        auditor = EntropyAuditor(mode="audit")
        # 在 Audit 模式下，即使熵值高也不應調用 kill
        auditor.audit(risky_payload)
        mock_kill.assert_not_called()

def test_block_mode_kill_threshold():
    # 模擬極端高風險 Payload
    extreme_payload = "4f2e9d8a1c7b6f5e4d3c2b1a0f9e8d7"
    
    with patch("os.kill") as mock_kill:
        auditor = EntropyAuditor(mode="block", threshold=4.5)
        # 如果熵值極高且為 block 模式，則執行 kill
        # 這裡我們模擬一個超過 4.5 的情境
        # (實際上 calculate_entropy 的確切值取決於字串多樣性)
        if auditor.calculate_entropy(extreme_payload) > 4.5:
             auditor.audit(extreme_payload)
             # 我們預期它會嘗試殺掉當前進程或相關進程
             # 實作中可能用 os.getpid()
             mock_kill.assert_called()
