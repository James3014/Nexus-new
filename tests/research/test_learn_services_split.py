import pytest
from pathlib import Path
from nexus.research.learn_mode import LearnModeService

def test_learn_mode_service_facade_integrity(tmp_path: Path):
    svc = LearnModeService(tmp_path)
    
    # Check if sub-services are initialized
    assert hasattr(svc, "_ingest_svc")
    assert hasattr(svc, "_claim_svc")
    assert hasattr(svc, "_converge_svc")
    assert hasattr(svc, "_ask_svc")
    assert hasattr(svc, "_slo_svc")
    
    # Check if public methods exist (Stability Check)
    methods = ["ingest", "load_claims", "converge", "ask", "build_phase_slo_report"]
    for m in methods:
        assert hasattr(svc, m)
        assert callable(getattr(svc, m))

def test_delegation_to_subservices(tmp_path, monkeypatch):
    svc = LearnModeService(tmp_path)
    called = {"ingest": False}
    
    def fake_ingest(source, source_file=None, topic=""):
        called["ingest"] = True
        return {"status": "ok"}
        
    monkeypatch.setattr(svc._ingest_svc, "ingest", fake_ingest)
    
    res = svc.ingest("test-source")
    assert called["ingest"] is True
    assert res["status"] == "ok"
