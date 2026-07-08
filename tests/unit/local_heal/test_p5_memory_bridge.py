"""EA-R2: P5 Memory Bridge Tests."""
from __future__ import annotations

import pytest
from nexus.services.local_heal.p5_memory_bridge import (
    P5MemoryBridgePayload,
    build_p5_memory_bridge_payload,
)


def test_bridge_payload_controlled_not_eligible():
    """EA-R2: Controlled P5 fixture → eligible_for_findings_memory=False."""
    payload = build_p5_memory_bridge_payload(
        task_id="t1",
        selection_strategy="diversity_v1",
        selection_changed=True,
        selected_model="good-model",
        counterfactual_model="bad-model",
        claim_level="controlled",
    )
    assert payload.eligible_for_findings_memory is False
    assert payload.claim_level == "controlled"


def test_bridge_payload_shadow_not_eligible():
    """EA-R2: Real shadow (no verifier) → eligible_for_findings_memory=False."""
    payload = build_p5_memory_bridge_payload(
        task_id="t2",
        selection_strategy="diversity_v1",
        selection_changed=True,
        selected_model="deepseek",
        counterfactual_model="qwen",
        claim_level="shadow",
    )
    assert payload.eligible_for_findings_memory is False
    assert payload.claim_level == "shadow"


def test_bridge_payload_verified_eligible():
    """EA-R2: Verified apply/verifier/claim → eligible_for_findings_memory=True."""
    payload = build_p5_memory_bridge_payload(
        task_id="t3",
        selection_strategy="diversity_v1",
        selection_changed=True,
        selected_model="deepseek",
        counterfactual_model="qwen",
        claim_level="verified",
    )
    assert payload.eligible_for_findings_memory is True
    assert payload.claim_level == "verified"


def test_bridge_does_not_import_diversity_selector():
    """EA-R2: Bridge does not import diversity_selector."""
    import nexus.services.local_heal.p5_memory_bridge as mod
    import inspect
    source = inspect.getsource(mod)
    assert "diversity_selector" not in source


def test_bridge_does_not_import_committee_routed_tool():
    """EA-R2: Bridge does not import committee_routed_tool."""
    import nexus.services.local_heal.p5_memory_bridge as mod
    import inspect
    source = inspect.getsource(mod)
    assert "committee_routed_tool" not in source


def test_bridge_does_not_write_to_disk():
    """EA-R2: Bridge does not write to disk."""
    import nexus.services.local_heal.p5_memory_bridge as mod
    import inspect
    source = inspect.getsource(mod)
    assert "open(" not in source
    assert "write(" not in source
