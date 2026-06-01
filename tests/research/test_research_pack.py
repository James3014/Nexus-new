from nexus.research.research_pack import build_research_pack, ResearchContext


def test_build_research_pack_contract_shape():
    pack = build_research_pack(ResearchContext(
        task="fix race condition",
        mode="experimental",
        source="AUTORESEARCH_PHASE7_LOOP",
        reason="multi_candidate_or_low_confidence",
        role="failure_historian",
        hypotheses=[{"id": "H1", "description": "A", "confidence": 0.8}],
        experiments=[{"round": 1, "hypothesis": "H1", "metric": 1.0, "kept": True}],
        winner={"hypothesis_id": "H1", "final_metric": 1.0},
        eliminated=[],
        rounds=3,
        time_sec=120.5,
        status="SUCCESS",
        findings=["ok"],
        verified_claims=[{"claim": "historical fix matched", "evidence_refs": ["memory:1"]}],
        rejected_claims=[{"claim": "single-line retry is enough", "reason": "prior regressions"}],
        retrieval_refs=["memory:1", "doc:race-playbook"],
        risk_flags=["plateau_risk"],
        recommended_capabilities=["research", "autoreason"],
        blocked_assumptions=["root cause confirmed"],
        next_action_hint="test an architectural alternative",
        confidence=0.72,
        raw={"tokens_used": 33},
    ))
    assert pack["schema_version"] == "research_pack.v1"
    assert pack["context_v2"]["schema_version"] == "research_context.v2"
    assert pack["budget_used"]["rounds"] == 3
    assert pack["winner"]["hypothesis_id"] == "H1"
    assert isinstance(pack["experiments"], list)
    assert isinstance(pack["hypotheses"], list)
    assert pack["role"] == "failure_historian"
    assert pack["context_v2"]["role"] == "failure_historian"
    assert pack["verified_claims"][0]["claim"] == "historical fix matched"
    assert pack["recommended_capabilities"] == ["research", "autoreason"]
    assert pack["next_action_hint"] == "test an architectural alternative"
    assert pack["confidence"] == 0.72
    assert "created_at" in pack

def test_build_research_pack_edge_cases():
    pack = build_research_pack(ResearchContext(
        task="",
        mode="",
        source="",
        reason="",
    ))
    assert pack["schema_version"] == "research_pack.v1"
    assert pack["context_v2"]["schema_version"] == "research_context.v2"
    assert pack["budget_used"]["rounds"] == 0
    assert pack["budget_used"]["time_sec"] == 0.0
    assert pack["token_fallback_est"] == 0
    assert pack["token_capture_status"] == "n/a"
    assert pack["role"] == "general"
    assert pack["context_v2"]["role"] == "general"
    assert pack["verified_claims"] == []
    assert pack["recommended_capabilities"] == []
    assert pack["confidence"] == 0.0
    assert "created_at" in pack
