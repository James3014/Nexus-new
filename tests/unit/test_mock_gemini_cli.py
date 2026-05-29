import os
import pytest
from unittest import mock

# We will import these from scripts.mock_gemini_cli once refactored
from scripts.mock_gemini_cli import get_model_and_options

def test_easy_difficulty_routing():
    # Easy tasks should map to qwen2.5-coder:7b with optimized params
    model, options = get_model_and_options(difficulty="easy")
    assert model == "qwen2.5-coder:7b"
    assert options["num_gpu"] == 99
    assert options["num_thread"] == 8
    assert options["num_ctx"] == 8192
    assert options["temperature"] == 0.1

def test_medium_difficulty_routing():
    # Medium tasks should map to qwen2.5-coder:14b with optimized params
    model, options = get_model_and_options(difficulty="medium")
    assert model == "qwen2.5-coder:14b"
    assert options["num_gpu"] == 99
    assert options["num_thread"] == 8
    assert options["num_ctx"] == 12288

def test_hard_difficulty_routing():
    # Hard tasks should map to qwen2.5-coder:14b with optimized params
    model, options = get_model_and_options(difficulty="hard")
    assert model == "qwen2.5-coder:14b"
    assert options["num_gpu"] == 99
    assert options["num_thread"] == 8
    assert options["num_ctx"] == 12288

def test_model_override_via_env():
    # Environment variable should override difficulty-based model selection
    with mock.patch.dict(os.environ, {"NEXUS_OLLAMA_REFLEX_MODEL": "custom-model:latest"}):
        model, options = get_model_and_options(difficulty="easy")
        assert model == "custom-model:latest"
        assert options["num_ctx"] == 8192  # Keep difficulty context window

def test_default_fallback():
    # Fallback to default model and options when difficulty is empty or unknown
    model, options = get_model_and_options(difficulty=None)
    assert model == "qwen2.5-coder:14b"
    assert options["num_gpu"] == 99
    assert options["num_ctx"] == 12288
