from nexus.services.local_heal.output_understanding import build_output_understanding_result


def test_build_output_understanding_result_for_converted_unified_diff() -> None:
    result = build_output_understanding_result(
        candidate_id="cand-1",
        expected_model="qwen2.5-coder:7b-instruct",
        invoked_model="qwen2.5-coder:7b-instruct",
        target_file="toy/math_util.py",
        target_symbol="normalize_score",
        patch_text="SEARCH/REPLACE",
        patch_hash="abc123",
        model_decision={
            "output_class": "UNIFIED_DIFF",
            "parser_error_kind": "",
            "conversion_status": "unified_diff_to_ssrp_converted",
        },
    )

    assert result.source_format == "unified_diff_converted"
    assert result.normalization_steps == ("unified_diff_to_ssrp_converted",)
    assert result.anchor_status == "target_declared"
    assert result.rejection_reason == ""
    assert result.candidate is not None
    assert result.candidate.source_format == "unified_diff_converted"
    assert result.candidate.safety_flags == ()


def test_build_output_understanding_result_for_empty_mismatched_candidate() -> None:
    result = build_output_understanding_result(
        candidate_id="cand-2",
        expected_model="deepseek-coder:6.7b-instruct",
        invoked_model="qwen2.5-coder:7b-instruct",
        target_file="toy/math_util.py",
        target_symbol="normalize_score",
        patch_text="",
        patch_hash="",
        model_decision={
            "output_class": "EMPTY",
            "parser_error_kind": "MODEL_EMPTY_RESPONSE",
            "conversion_status": "none",
        },
    )

    assert result.source_format == "empty"
    assert result.normalization_steps == ()
    assert result.anchor_status == "target_declared"
    assert result.rejection_reason == "MODEL_EMPTY_RESPONSE"
    assert result.candidate is None
