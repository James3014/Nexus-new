from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_cloud_candidate_stub import (
    compute_cloud_candidate_stub,
    p3_cloud_stub_to_dict,
)


def test_cloud_stub_standalone():
    stub = compute_cloud_candidate_stub(
        diagnosis_metadata={
            "p3_diagnosis_cloud_ready": True,
            "p3_diagnosis_reason": "diagnosis_complete",
            "p3_diagnosis_compact_prompt_hash": "abc123",
            "p3_diagnosis_compact_prompt_token_estimate": 50,
        },
        cloud_provider="openai",
        cloud_model="gpt-4",
    )
    assert stub.cloud_call_planned is True
    assert stub.cloud_call_invoked is False
    meta = p3_cloud_stub_to_dict(stub)
    assert meta["p3_cloud_stub_call_planned"] is True


def test_cloud_stub_json_serializable():
    stub = compute_cloud_candidate_stub(
        diagnosis_metadata={"p3_diagnosis_cloud_ready": True, "p3_diagnosis_compact_prompt_hash": "h"},
    )
    meta = p3_cloud_stub_to_dict(stub)
    serialized = json.dumps(meta)
    assert isinstance(serialized, str)
