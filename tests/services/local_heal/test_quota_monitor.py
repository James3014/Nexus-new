from __future__ import annotations

import os

import pytest

from nexus.services.local_heal.quota_monitor import QuotaMonitor


class TestQuotaMonitorInit:
    def test_quota_monitor_init_default_interval_30(self):
        monitor = QuotaMonitor()
        assert monitor.poll_interval_seconds == 30

    def test_quota_monitor_custom_interval(self):
        monitor = QuotaMonitor(poll_interval_seconds=60)
        assert monitor.poll_interval_seconds == 60


class TestQuotaMonitorObserve:
    def test_quota_monitor_observe_returns_quota_state(self):
        monitor = QuotaMonitor()
        state = monitor.observe()
        from nexus.services.local_heal.quota_state import QuotaState
        assert isinstance(state, QuotaState)

    def test_quota_monitor_get_state_history_capped_at_100(self):
        monitor = QuotaMonitor()
        for _ in range(105):
            monitor.observe()
        assert len(monitor.get_state_history()) == 100

    def test_quota_monitor_detect_change_returns_new_state(self):
        monitor = QuotaMonitor()
        state = monitor.detect_change()
        assert state is not None
        from nexus.services.local_heal.quota_state import QuotaState
        assert isinstance(state, QuotaState)

    def test_quota_monitor_detect_change_returns_none_when_same(self):
        monitor = QuotaMonitor()
        state1 = monitor.detect_change()
        state2 = monitor.detect_change()
        assert state1 is not None
        assert state2 is None

    def test_quota_monitor_no_background_thread(self):
        import threading
        original = threading.Thread
        try:
            threading.Thread = None
            monitor = QuotaMonitor()
            assert monitor.poll_interval_seconds == 30
        finally:
            threading.Thread = original
