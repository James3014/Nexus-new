from nexus.research.research_pack import build_research_pack


def test_build_research_pack_contract_shape():
    pack = build_research_pack(
        task="fix race condition",
        mode="experimental",
        source="AUTORESEARCH_PHASE7_LOOP",
        reason="multi_candidate_or_low_confidence",
        hypotheses=[{"id": "H1", "description": "A", "confidence": 0.8}],
        experiments=[{"round": 1, "hypothesis": "H1", "metric": 1.0, "kept": True}],
        winner={"hypothesis_id": "H1", "final_metric": 1.0},
        eliminated=[],
        rounds=3,
        time_sec=120.5,
        status="SUCCESS",
        findings=["ok"],
        raw={"tokens_used": 33},
    )
    assert pack["schema_version"] == "research_pack.v1"
    assert pack["budget_used"]["rounds"] == 3
    assert pack["winner"]["hypothesis_id"] == "H1"
    assert isinstance(pack["experiments"], list)
    assert isinstance(pack["hypotheses"], list)
    assert "created_at" in pack

def test_build_research_pack_edge_cases():
    pack = build_research_pack(
        task="",
        mode="",
        source="",
        reason="",
    )
    assert pack["schema_version"] == "research_pack.v1"
    assert pack["budget_used"]["rounds"] == 0
    assert pack["budget_used"]["time_sec"] == 0.0
    assert pack["token_fallback_est"] == 0
    assert pack["token_capture_status"] == "n/a"
    assert "created_at" in pack
