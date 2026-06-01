from pathlib import Path

from nexus.research.learn.phase_slo_summary_service import PhaseSLOSummaryService
from nexus.research.learn_mode import LearnModeService


def test_phase_slo_summary_service_returns_unavailable_when_missing(tmp_path: Path):
    svc = LearnModeService(tmp_path)
    reader = PhaseSLOSummaryService(svc)
    out = reader.read_phase_slo_summary()
    assert out["status"] == "UNAVAILABLE"
    assert out["reason"] == "phase_slo_summary_missing"


def test_phase_slo_summary_service_returns_unavailable_when_parse_error(tmp_path: Path):
    svc = LearnModeService(tmp_path)
    svc.phase_slo_summary_path.parent.mkdir(parents=True, exist_ok=True)
    svc.phase_slo_summary_path.write_text("{invalid-json", encoding="utf-8")
    reader = PhaseSLOSummaryService(svc)
    out = reader.read_phase_slo_summary()
    assert out["status"] == "UNAVAILABLE"
    assert out["reason"] == "phase_slo_summary_parse_error"


def test_phase_slo_summary_service_returns_unavailable_when_invalid_type(tmp_path: Path):
    svc = LearnModeService(tmp_path)
    svc.phase_slo_summary_path.parent.mkdir(parents=True, exist_ok=True)
    svc.phase_slo_summary_path.write_text('["not-a-dict"]', encoding="utf-8")
    reader = PhaseSLOSummaryService(svc)
    out = reader.read_phase_slo_summary()
    assert out["status"] == "UNAVAILABLE"
    assert out["reason"] == "phase_slo_summary_invalid_type"


def test_phase_slo_summary_service_returns_payload_when_valid(tmp_path: Path):
    svc = LearnModeService(tmp_path)
    payload = {"status": "SUCCESS", "phase_slo_pass": True, "global": {"required_done_ratio": 1.0}}
    svc.phase_slo_summary_path.parent.mkdir(parents=True, exist_ok=True)
    svc.phase_slo_summary_path.write_text('{"status":"SUCCESS","phase_slo_pass":true,"global":{"required_done_ratio":1.0}}', encoding="utf-8")
    reader = PhaseSLOSummaryService(svc)
    out = reader.read_phase_slo_summary()
    assert out["status"] == payload["status"]
    assert out["phase_slo_pass"] is True
