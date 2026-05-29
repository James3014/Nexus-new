from __future__ import annotations

import os
from unittest import mock
import pytest
from scripts.bench.preflight_7r_restart import run_preflight


def test_preflight_dual_denominator_fail_closed():
    """
    測試雙分母不匹配時 (例如 100 selected 但 99 execution-safe)，
    preflight 必須 fail-closed 阻斷 (回傳 exit code 4)。
    """
    # 模擬環境變數皆有正確綁定，避開 Abort Seams 攔截
    env_mock = {
        "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
        "NEXUS_OUTBOUND_PROMPT_STRICT": "1",
        "NEXUSBENCHFAILFASTONROWFAILURE": "1",
        "NEXUS_DIRECT_TIMEOUT_ABORT_THRESHOLD": "30",
        "NEXUS_DIRECT_INFRA_ABORT_THRESHOLD": "5"
    }
    
    with mock.patch.dict(os.environ, env_mock):
        # 測試：當 selected=100, execution-safe=99 時，必須阻斷
        exit_code = run_preflight(
            manifest_path=None,
            index_filter=None,
            expected_selected=100,
            expected_execution_safe=100,
            mock_selected_count=100,
            mock_execution_safe_count=99
        )
        assert exit_code == 4  # 4 代表雙分母不匹配 fail-closed
        
        # 測試：當 selected=100, execution-safe=100 時，且 row-key 重複性沒問題，應 PASS (回傳 0)
        exit_code_pass = run_preflight(
            manifest_path=None,
            index_filter="0-99",
            expected_selected=100,
            expected_execution_safe=100,
            mock_selected_count=100,
            mock_execution_safe_count=100
        )
        assert exit_code_pass == 0


def test_preflight_duplicate_without_index_filter_fail_closed():
    """
    測試當偵測到重複 Task ID 但不給 manifest_index_filter 時，
    preflight 必須 fail-closed 阻斷 (回傳 exit code 5)。
    """
    env_mock = {
        "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
        "NEXUS_OUTBOUND_PROMPT_STRICT": "1",
        "NEXUSBENCHFAILFASTONROWFAILURE": "1",
        "NEXUS_DIRECT_TIMEOUT_ABORT_THRESHOLD": "30",
        "NEXUS_DIRECT_INFRA_ABORT_THRESHOLD": "5"
    }
    
    with mock.patch.dict(os.environ, env_mock):
        exit_code = run_preflight(
            manifest_path=None,
            index_filter="FORCE_DUPLICATE_ERROR",
            expected_selected=100,
            expected_execution_safe=100,
            mock_selected_count=100,
            mock_execution_safe_count=100
        )
        assert exit_code == 5  # 5 代表偵測到重複且未提供 index filter
