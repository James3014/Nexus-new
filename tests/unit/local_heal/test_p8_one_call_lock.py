from __future__ import annotations

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch
from nexus.services.local_heal.p8_one_call_lock import (
    P8OneCallLock,
    acquire_p8_one_call_lock,
    p8_one_call_lock_to_dict,
)


# ============================================================
# E2-1: no previous lock acquires lock
# ============================================================


def test_no_previous_lock_acquires():
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.json"
        with patch("nexus.services.local_heal.p8_one_call_lock.LOCK_PATH", lock_path):
            result = acquire_p8_one_call_lock()
            assert result.lock_acquired is True
            assert result.network_execution_allowed is True
            assert result.previous_lock_present is False


# ============================================================
# E2-2: previous lock blocks
# ============================================================


def test_previous_lock_blocks():
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.json"
        lock_path.write_text('{"lock_version": "1.0", "smoke_id": "existing"}')
        with patch("nexus.services.local_heal.p8_one_call_lock.LOCK_PATH", lock_path):
            result = acquire_p8_one_call_lock()
            assert result.lock_acquired is False
            assert result.network_execution_allowed is False
            assert "previous_lock_exists" in result.blocked_reasons


# ============================================================
# E2-3: previous_network_call_count>0 blocks
# ============================================================


def test_previous_call_count_blocks():
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.json"
        with patch("nexus.services.local_heal.p8_one_call_lock.LOCK_PATH", lock_path):
            result = acquire_p8_one_call_lock(previous_network_call_count=1)
            assert result.lock_acquired is False
            assert result.network_execution_allowed is False
            assert "previous_network_call_exists" in result.blocked_reasons


# ============================================================
# E2-4: max_network_calls must be 1
# ============================================================


def test_max_calls_must_be_1():
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.json"
        with patch("nexus.services.local_heal.p8_one_call_lock.LOCK_PATH", lock_path):
            result = acquire_p8_one_call_lock()
            assert result.max_network_calls == 1


# ============================================================
# E2-5: duplicate execution blocked
# ============================================================


def test_duplicate_execution_blocked():
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.json"
        lock_path.write_text('{"lock_version": "1.0", "smoke_id": "existing"}')
        with patch("nexus.services.local_heal.p8_one_call_lock.LOCK_PATH", lock_path):
            result = acquire_p8_one_call_lock()
            assert result.duplicate_execution_blocked is True


# ============================================================
# E2-6: lock artifact reloads
# ============================================================


def test_lock_artifact_reloads():
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.json"
        with patch("nexus.services.local_heal.p8_one_call_lock.LOCK_PATH", lock_path):
            result = acquire_p8_one_call_lock()
            assert lock_path.exists()
            with open(lock_path) as f:
                loaded = json.load(f)
            assert loaded["smoke_id"] == result.smoke_id


# ============================================================
# E2-7: JSON serialization works
# ============================================================


def test_json_serializable():
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.json"
        with patch("nexus.services.local_heal.p8_one_call_lock.LOCK_PATH", lock_path):
            result = acquire_p8_one_call_lock()
            d = p8_one_call_lock_to_dict(result)
            assert isinstance(json.dumps(d), str)
