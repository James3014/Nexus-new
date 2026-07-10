from __future__ import annotations

import os

from nexus.services.local_heal.fuzzy_spec_registry import (
    FuzzyFunctionSpec,
    get_fuzzy_function_spec,
    list_fuzzy_function_specs,
)
from nexus.services.local_heal.fuzzy_functions import PawCompiler, list_functions, evaluate


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

    # === L3-F: real PAW Compiler ===

    def test_real_paw_compiler_disabled_deterministic(self):
        if "NEXUS_PAW_COMPILE" in os.environ:
            del os.environ["NEXUS_PAW_COMPILE"]
        compiler = PawCompiler()
        assert compiler.is_enabled() is False
        assert compiler.compile() is False
        result = compiler.evaluate("candidate_quality_v1", syntax_like_score=0.8, safety_penalty=0.0)
        assert result.backend == "deterministic"
        assert result.deterministic is True

    def test_real_paw_compiler_lora_compile_disabled(self):
        os.environ["NEXUS_PAW_COMPILE"] = "0"
        compiler = PawCompiler()
        assert compiler.is_enabled() is False
        del os.environ["NEXUS_PAW_COMPILE"]

    def test_real_paw_compiler_5_functions(self):
        if "NEXUS_PAW_COMPILE" in os.environ:
            del os.environ["NEXUS_PAW_COMPILE"]
        compiler = PawCompiler()
        for spec in list_functions():
            result = compiler.evaluate(
                spec.name,
                **{k: 0.5 for k in spec.input_schema}
            )
            assert result.name == spec.name
            assert result.backend == "deterministic"

    def test_real_paw_compiler_fallback_on_missing_model(self):
        os.environ["NEXUS_PAW_COMPILE"] = "1"
        compiler = PawCompiler()
        assert compiler.is_enabled() is True
        # compile will fail since transformers not loaded -> fallback
        result = compiler.evaluate("candidate_quality_v1", syntax_like_score=0.8, safety_penalty=0.0)
        assert result.backend == "deterministic"
        assert result.deterministic is True
        del os.environ["NEXUS_PAW_COMPILE"]
