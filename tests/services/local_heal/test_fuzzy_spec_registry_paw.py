from __future__ import annotations

from nexus.services.local_heal.fuzzy_spec_registry import (
    FuzzyFunctionSpec,
    get_fuzzy_function_spec,
    list_fuzzy_function_specs,
)


class TestFuzzySpecPAWFields:

    def test_fuzzy_function_spec_new_fields_default_empty(self):
        spec = FuzzyFunctionSpec(
            function_name="test",
            version="1.0",
            natural_language_spec="test",
            input_schema={},
            output_schema={},
            deterministic_backend="test",
        )
        assert spec.paw_compiled_lora_path == ""
        assert spec.paw_interpreter_model == "Qwen3-0.6B"
        assert spec.paw_compile_trigger == {}

    def test_popularity_trap_paw_available_true(self):
        spec = get_fuzzy_function_spec("popularity_trap_risk_v1")
        assert spec is not None
        assert spec.paw_backend_available is True

    def test_candidate_quality_paw_available_true(self):
        spec = get_fuzzy_function_spec("candidate_quality_v1")
        assert spec is not None
        assert spec.paw_backend_available is True

    def test_duplicate_similarity_paw_available_true(self):
        spec = get_fuzzy_function_spec("duplicate_similarity_v1")
        assert spec is not None
        assert spec.paw_backend_available is True

    def test_memory_usefulness_paw_available_false(self):
        spec = get_fuzzy_function_spec("memory_usefulness_v1")
        assert spec is not None
        assert spec.paw_backend_available is False

    def test_quota_degradation_paw_available_false(self):
        spec = get_fuzzy_function_spec("quota_degradation_risk_v1")
        assert spec is not None
        assert spec.paw_backend_available is False

    def test_paw_compile_trigger_default_empty_dict(self):
        spec = get_fuzzy_function_spec("candidate_quality_v1")
        assert spec is not None
        assert spec.paw_compile_trigger == {}
