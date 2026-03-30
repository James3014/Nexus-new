import pytest
from nexus.services.predictor import Predictor

def test_predictor_low_risk():
    """驗證低風險任務的評分。"""
    p = Predictor()
    res = p.predict("Update README", {"files_count": 5})
    assert res["risk_level"] == "LOW"
    assert res["risk_score"] == 0.2

def test_predictor_critical_risk():
    """驗證關鍵風險關鍵字觸發。"""
    p = Predictor()
    # "delete" (+0.5) + "file" (+0.8) -> 1.0 (capped)
    res = p.predict("delete data file", {"files_count": 10})
    assert res["risk_level"] == "CRITICAL"
    assert res["risk_score"] >= 0.8
    assert any("keyword" in r.lower() for r in res["reasons"])

def test_predictor_complexity_risk():
    """驗證高複雜度（檔案數量多）引起的風險。"""
    p = Predictor()
    res = p.predict("Simple task", {"files_count": 100})
    # 0.2 (base) + 0.2 (complexity) = 0.4
    assert res["risk_score"] == 0.4
    assert any("Complexity" in r for r in res["reasons"])

def test_predictor_js_conflict():
    """驗證 JavaScript 與 HTML 觸發的衝突風險。"""
    p = Predictor()
    res = p.predict("fix script.js and index.html", {})
    # 0.2 (base) + 0.3 (JS conflict) = 0.5 -> MAJOR
    assert res["risk_level"] == "MAJOR"
    assert any("JS conflict" in r for r in res["reasons"])
