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
    assert hasattr(svc, "_report_svc")
    assert hasattr(svc, "_phase_bridge_svc")
    assert hasattr(svc, "_benchmark_svc")
    assert hasattr(svc, "_source_registry_svc")
    assert hasattr(svc, "_phase_slo_summary_svc")
    assert hasattr(svc, "_phase_kpi_svc")
    
    # Check if public methods exist (Stability Check)
    methods = [
        "ingest",
        "load_claims",
        "converge",
        "ask",
        "build_phase_slo_report",
        "build_phase_kpi_report",
        "build_report",
        "curate_benchmark_bank",
        "register_source",
        "refresh_sources",
        "build_refresh_plan",
        "read_phase_slo_summary",
    ]
    for m in methods:
        assert hasattr(svc, m)
        assert callable(getattr(svc, m))

def test_delegation_to_subservices(tmp_path, monkeypatch):
    svc = LearnModeService(tmp_path)
    called = {"ingest": False}
    
    def fake_ingest(source, source_file=None, topic=""):
        called["ingest"] = True
        return {
            "status": "SUCCESS",
            "claims_count": 1,
            "verified_claims_count": 1,
            "sources_count": 1,
            "documents_ingested": 1,
        }
        
    monkeypatch.setattr(svc._ingest_svc, "ingest", fake_ingest)
    
    res = svc.ingest("test-source")
    assert called["ingest"] is True
    assert res["status"] == "SUCCESS"


def test_ingest_fail_closed_on_contract_violation(tmp_path, monkeypatch):
    svc = LearnModeService(tmp_path)

    def fake_ingest(source, source_file=None, topic=""):
        return {"status": "SUCCESS"}  # missing required fields

    monkeypatch.setattr(svc._ingest_svc, "ingest", fake_ingest)

    with pytest.raises(RuntimeError, match="learn_ingest_contract_violation"):
        svc.ingest("repo:nexus", source_file=None, topic="nexus")


def test_report_delegation_to_subservice(tmp_path, monkeypatch):
    svc = LearnModeService(tmp_path)
    called = {"report": False}

    def fake_report(topic="", question_count=5, pass_threshold=0.6):
        called["report"] = True
        return {"status": "SUCCESS", "topic": topic, "converged": True}

    monkeypatch.setattr(svc._report_svc, "build_report", fake_report)
    out = svc.build_report(topic="nexus")
    assert called["report"] is True
    assert out["status"] == "SUCCESS"


def test_phase_bridge_delegation_to_subservice(tmp_path, monkeypatch):
    svc = LearnModeService(tmp_path)
    called = {"bridge": False}

    def fake_bridge(topic, metrics, phase_status=None):
        called["bridge"] = True
        return {
            "status": "SUCCESS",
            "topic": topic,
            "entries_written": 6,
            "phase_routes": {},
            "phase_slo_summary": {"status": "SUCCESS"},
        }

    monkeypatch.setattr(svc._phase_bridge_svc, "sync_phase_learning_closure", fake_bridge)
    out = svc.sync_phase_learning_closure(topic="nexus", metrics={"coverage": 0.9})
    assert called["bridge"] is True
    assert out["entries_written"] == 6


def test_benchmark_curation_delegation_to_subservice(tmp_path, monkeypatch):
    svc = LearnModeService(tmp_path)
    called = {"benchmark": False}

    def fake_curate(topic="", max_questions=40, min_occurrences=1):
        called["benchmark"] = True
        return {"status": "SUCCESS", "selected_count": 3}

    monkeypatch.setattr(svc._benchmark_svc, "curate_benchmark_bank", fake_curate)
    out = svc.curate_benchmark_bank(topic="nexus", max_questions=10, min_occurrences=2)
    assert called["benchmark"] is True
    assert out["selected_count"] == 3


def test_source_registry_delegation_to_subservice(tmp_path, monkeypatch):
    svc = LearnModeService(tmp_path)
    called = {"register": False}

    def fake_register_source(*, topic, source, refresh_after_days=14, priority="medium", source_file=None):
        called["register"] = True
        return {
            "status": "SUCCESS",
            "topic": topic,
            "source": source,
            "refresh_after_days": refresh_after_days,
            "priority": priority,
            "source_file": source_file,
        }

    monkeypatch.setattr(svc._source_registry_svc, "register_source", fake_register_source)
    out = svc.register_source(topic="nexus", source="repo:demo", refresh_after_days=3, priority="high")
    assert called["register"] is True
    assert out["status"] == "SUCCESS"
    assert out["source"] == "repo:demo"


def test_phase_slo_summary_delegation_to_subservice(tmp_path, monkeypatch):
    svc = LearnModeService(tmp_path)
    called = {"read": False}

    def fake_read_phase_slo_summary():
        called["read"] = True
        return {"status": "SUCCESS", "phase_slo_pass": True}

    monkeypatch.setattr(svc._phase_slo_summary_svc, "read_phase_slo_summary", fake_read_phase_slo_summary)
    out = svc.read_phase_slo_summary()
    assert called["read"] is True
    assert out["phase_slo_pass"] is True


def test_phase_kpi_report_delegation_to_subservice(tmp_path, monkeypatch):
    svc = LearnModeService(tmp_path)
    called = {"kpi": False}

    def fake_build_phase_kpi_report(window=300):
        called["kpi"] = True
        return {"status": "SUCCESS", "window": window, "total_records": 0}

    monkeypatch.setattr(svc._phase_kpi_svc, "build_phase_kpi_report", fake_build_phase_kpi_report)
    out = svc.build_phase_kpi_report(window=64)
    assert called["kpi"] is True
    assert out["status"] == "SUCCESS"
    assert out["window"] == 64
