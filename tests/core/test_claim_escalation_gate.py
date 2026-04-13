import pytest
from nexus.core.critique_engine import CritiqueEngine, RationalizationError
from nexus.core.verification_card import VerificationCard

def test_overclaim_blocker():
    engine = CritiqueEngine()
    # 模擬一個沒有足夠證據的高風險宣告
    claim = "I have solved the CPython weakref race 100%!"
    bad_evidence = {"confidence_level": "MEDIUM", "known_gaps": []}
    
    with pytest.raises(RationalizationError) as excinfo:
        engine.detect_overclaim(claim, bad_evidence)
    assert "Overclaim detected" in str(excinfo.value)

def test_verification_card_rejection():
    # 模擬一個宣稱 VERIFIED 但缺乏 Sanitizer 覆蓋的卡片
    card = VerificationCard(
        claim_state="VERIFIED",
        evidence_count=5,
        missing_evidence=["TSAN Log"],
        sanitizer_coverage=False, # ❌ 關鍵缺失
        repro_status=True,
        confidence="HIGH"
    )
    assert card.validate() is False
    assert "❌ REJECTED" in card.render_markdown()

def test_anti_rationalization_preflight():
    engine = CritiqueEngine()
    # HIGH 信心度必須包含 known_gaps
    with pytest.raises(RationalizationError):
        engine.anti_rationalization_preflight("Claim", {"confidence_level": "HIGH", "known_gaps": []})
