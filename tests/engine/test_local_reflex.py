from nexus.engine.local_reflex import ReflexAssessment, _merge_ollama_shadow, _parse_reflex_jsonish, assess_local_reflex


def test_local_reflex_marks_low_risk_public_repair_bare_sufficient(monkeypatch):
    monkeypatch.delenv("NEXUS_LOCAL_REFLEX_PROVIDER", raising=False)
    assessment = assess_local_reflex(
        task_desc="Fix a focused public fixture assertion.",
        task_type="public_test_repair",
        difficulty="hard",
        category="test_repair",
        repo_kind="neutral_fixture",
    )

    assert assessment.provider == "heuristic"
    assert assessment.available is True
    assert assessment.risk_level == "low"
    assert assessment.bare_sufficiency == "high"
    assert assessment.needs_hyper is False
    assert assessment.to_route_features()["local_reflex_bare_sufficiency"] == "high"


def test_local_reflex_does_not_match_rm_inside_normalization_words(monkeypatch):
    monkeypatch.delenv("NEXUS_LOCAL_REFLEX_PROVIDER", raising=False)
    assessment = assess_local_reflex(
        task_desc=(
            "Fix a boundary parser where the verification command checks "
            "unicode-free normalization, empty input, and repeated separators."
        ),
        task_type="public_bugfix",
        difficulty="hard",
        category="bugfix",
        repo_kind="neutral_fixture",
        fixture_kind="nexus_value_hidden_parser",
    )

    assert assessment.risk_level == "low"
    assert assessment.bare_sufficiency == "high"
    assert "rm" not in assessment.reasons


def test_local_reflex_blocks_bare_first_for_core_refactor(monkeypatch):
    monkeypatch.delenv("NEXUS_LOCAL_REFLEX_PROVIDER", raising=False)
    assessment = assess_local_reflex(
        task_desc="Refactor core orchestrator routing and remove old policy paths.",
        task_type="public_test_repair",
        difficulty="hard",
        category="test_repair",
        repo_kind="neutral_fixture",
    )

    assert assessment.risk_level == "high"
    assert assessment.bare_sufficiency == "low"
    assert assessment.needs_hyper is True
    assert assessment.needs_ultra_review is True


def test_local_reflex_ollama_unavailable_fails_closed_to_heuristic(monkeypatch):
    monkeypatch.setenv("NEXUS_LOCAL_REFLEX_PROVIDER", "ollama")
    monkeypatch.setenv("NEXUS_OLLAMA_URL", "http://localhost:1")

    assessment = assess_local_reflex(
        task_desc="Fix a focused public fixture assertion.",
        task_type="public_test_repair",
        difficulty="hard",
        category="test_repair",
        repo_kind="neutral_fixture",
        timeout_sec=0.01,
    )

    assert assessment.provider == "heuristic_fallback"
    assert assessment.available is False
    assert "ollama_unavailable" in assessment.reasons
    assert assessment.bare_sufficiency == "high"


def test_parse_reflex_jsonish_extracts_embedded_json():
    parsed = _parse_reflex_jsonish('thinking... {"risk_level":"high","bare_sufficiency":"low"} done')

    assert parsed == {"risk_level": "high", "bare_sufficiency": "low"}


def test_ollama_shadow_cannot_downgrade_heuristic_high_risk():
    local = ReflexAssessment(
        schema_version="nexus_local_reflex.v1",
        provider="ollama",
        available=True,
        risk_level="low",
        bare_sufficiency="high",
        needs_research=False,
        needs_hyper=False,
        needs_ultra_review=False,
        confidence=0.7,
        latency_ms=10,
        reasons=("ollama_response",),
    )

    merged = _merge_ollama_shadow(
        local=local,
        task_desc="Refactor core orchestrator routing and remove old policy paths.",
        task_type="public_test_repair",
        difficulty="hard",
        category="test_repair",
        repo_kind="neutral_fixture",
        fixture_kind="",
        start=0,
    )

    assert merged.provider == "ollama"
    assert merged.available is True
    assert merged.risk_level == "high"
    assert merged.bare_sufficiency == "low"
    assert "ollama_risk:low" in merged.reasons


def test_ollama_shadow_false_positive_does_not_upgrade_public_fixture():
    local = ReflexAssessment(
        schema_version="nexus_local_reflex.v1",
        provider="ollama",
        available=True,
        risk_level="high",
        bare_sufficiency="low",
        needs_research=False,
        needs_hyper=True,
        needs_ultra_review=True,
        confidence=0.7,
        latency_ms=10,
        reasons=("ollama_response",),
    )

    merged = _merge_ollama_shadow(
        local=local,
        task_desc="Fix typo in tests/fixtures/mock_data.json.",
        task_type="public_test_repair",
        difficulty="hard",
        category="test_repair",
        repo_kind="neutral_fixture",
        fixture_kind="",
        start=0,
    )

    assert merged.risk_level == "low"
    assert merged.bare_sufficiency == "high"
    assert "ollama_high_risk_ignored_without_strong_veto_term" in merged.reasons


def test_heuristic_marks_destructive_write_paths_high_risk():
    assessment = assess_local_reflex(
        task_desc="Command rm -rf .git and write_file benchmarks/result.json.",
        task_type="execute",
    )

    assert assessment.risk_level == "high"
    assert assessment.bare_sufficiency == "low"
    assert assessment.needs_ultra_review is True
