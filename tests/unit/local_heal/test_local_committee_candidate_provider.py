from __future__ import annotations

from unittest import mock
import pytest
from nexus.services.local_heal.local_committee_candidate_provider import LocalCommitteeCandidateProvider
from nexus.services.local_heal.local_model_provider import (
    InjectedLocalModelProvider,
    LocalModelProviderRequest,
)
from nexus.services.local_heal.backend_resource_policy import DEFAULT_POLICIES, ModelPolicy, ModelTier, ResourcePolicy


def test_generate_committee_candidates_success() -> None:
    prompts_captured = {}

    def mock_gen(req: LocalModelProviderRequest) -> str:
        prompts_captured[req.model_name] = req.prompt
        if req.model_name == "qwen2.5:3b":
            return "judge analysis text"
        elif req.model_name == "qwen2.5-coder:7b":
            return "<<<<<<< REPLACE\nprint('qwen')\n>>>>>>> REPLACE"
        elif req.model_name == "deepseek-coder:6.7b-instruct":
            return "<<<<<<< REPLACE\nprint('deepseek')\n>>>>>>> REPLACE"
        return ""

    provider = InjectedLocalModelProvider(mock_gen)
    envelopes = LocalCommitteeCandidateProvider.generate_committee_candidates(
        task_id="task-123",
        problem_statement="fix hello",
        target_file="app.py",
        target_symbol="run",
        locked_search="print('hello')",
        evidence_refs=("ref-1",),
        provider=provider,
        protocol_mode="anchored_edit",
    )

    assert len(envelopes) == 3
    
    # 3B Judge envelope assert
    judge_env = next(e for e in envelopes if e.model == "qwen2.5:3b")
    assert judge_env.role == "judge"
    assert judge_env.candidate_patch == ""
    assert judge_env.abstained is False
    assert "brief ranking or classification" in prompts_captured["qwen2.5:3b"]

    # Qwen 7B primary proposer assert
    qwen_env = next(e for e in envelopes if e.model == "qwen2.5-coder:7b")
    assert qwen_env.role == "primary_proposer"
    assert qwen_env.candidate_patch == "<<<<<<< REPLACE\nprint('qwen')\n>>>>>>> REPLACE"
    assert qwen_env.abstained is False

    # DeepSeek secondary proposer assert
    ds_env = next(e for e in envelopes if e.model == "deepseek-coder:6.7b-instruct")
    assert ds_env.role == "secondary_proposer"
    assert ds_env.candidate_patch == "<<<<<<< REPLACE\nprint('deepseek')\n>>>>>>> REPLACE"
    assert ds_env.abstained is False


def test_generate_committee_candidates_resource_blocked() -> None:
    # Temporarily modify default policy for deepseek to FORBIDDEN
    original_policy = DEFAULT_POLICIES["deepseek-coder:6.7b-instruct"]
    try:
        DEFAULT_POLICIES["deepseek-coder:6.7b-instruct"] = ModelPolicy(
            model_name="deepseek-coder:6.7b-instruct",
            model_tier=ModelTier.LOCAL_7B,
            resource_policy=ResourcePolicy.FORBIDDEN,
        )

        def mock_gen(req: LocalModelProviderRequest) -> str:
            return "output"

        provider = InjectedLocalModelProvider(mock_gen)
        envelopes = LocalCommitteeCandidateProvider.generate_committee_candidates(
            task_id="task-123",
            problem_statement="fix hello",
            target_file="app.py",
            target_symbol="run",
            locked_search="print('hello')",
            evidence_refs=("ref-1",),
            provider=provider,
            protocol_mode="anchored_edit",
        )

        assert len(envelopes) == 3
        ds_env = next(e for e in envelopes if e.model == "deepseek-coder:6.7b-instruct")
        assert ds_env.abstained is True
        assert "resource_policy_forbidden" in ds_env.risk_flags
        assert ds_env.candidate_patch == ""

    finally:
        DEFAULT_POLICIES["deepseek-coder:6.7b-instruct"] = original_policy
