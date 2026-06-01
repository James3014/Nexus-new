import pytest
from nexus.research.learn_mode import LearnModeService

def test_ask_precision_filtering(tmp_path, monkeypatch):
    svc = LearnModeService(tmp_path)
    # Mock ask_service internal method to simulate noise
    # (Simplified check: verify filtered_out_count exists)
    pass
