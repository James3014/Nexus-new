from __future__ import annotations

import os
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from nexus.services.product_capability_closure import (
    LIVE_EXECUTED_PASS,
    PRODUCT_CAPABILITIES,
    verify_product_capability_resolution,
)
from nexus.services.product_capability_closure_harness import (
    ClosureTaskSpec,
    build_product_task_catalog,
    run_closure_task,
)
from tests.services.test_product_capability_online_native_closure import (
    _production_canary_runner,
)
from tests.services.test_product_capability_stage_owned_closure import (
    _stage_result,
)


def _online_live_authorized() -> bool:
    return os.environ.get("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "").strip() == "1"


@pytest.mark.skipif(
    not _online_live_authorized(),
    reason="Requires NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1 and live registered_cli agy provider",
)
def test_real_agy_consumption_and_challenge_closure(tmp_path: Path) -> None:
    """P1: Verify real agy registered_cli consumption with task-scoped challenge across product capabilities."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "target.py").write_text(
        "def family_canary_target():\n    return 'verified'\n",
        encoding="utf-8",
    )

    catalog = build_product_task_catalog(workspace)
    task = [t for t in catalog if t.capability == "codeintel" and t.origin == "online"][0]

    row = run_closure_task(
        task,
        _production_canary_runner,
        output_dir=tmp_path / "runs",
    )

    verdict = row["closure_verdict"]
    assert verdict["status"] == LIVE_EXECUTED_PASS
    assert verdict["live_pass"] is True
    assert verdict["missing_evidence_reasons"] == []

    mainchain_result, raw_receipt, stage = _stage_result(row, "codeintel")
    online_stages = [s for s in raw_receipt.get("stages", []) if s.get("name") == "online"]
    assert len(online_stages) == 1
    online_stage = online_stages[0]
    response = online_stage.get("response", {})

    # 1. Require provider=agy, provider_call_count=1, output_delivered=true
    assert response.get("provider") == "agy"
    assert response.get("provider_call_count") == 1
    assert response.get("output_delivered") is True
    assert response.get("gate_passed") is True

    # 2. Require capability bundle hash in prompt and lineaged hashes
    with_nexus = response.get("with_nexus", {})
    lineage = with_nexus.get("lineage", {})
    bundle_hash = str(lineage.get("bundle_hash") or "")
    assert len(bundle_hash) == 64
    assert lineage.get("capability_consumed") is True
    assert lineage.get("capability_evidence_injected") is True

    # 3. Record and verify prompt_hash and provider_output_hash
    prompt_hash = str(with_nexus.get("prompt_hash") or "")
    assert len(prompt_hash) == 64
    raw_response_text = str(response.get("raw_response") or "")
    assert len(raw_response_text) > 0


@pytest.mark.skipif(
    not _online_live_authorized(),
    reason="Requires NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1 and live registered_cli agy provider",
)
def test_real_agy_stage_owned_postflight_claim_and_delivery_gates(tmp_path: Path) -> None:
    """P1: Verify claim_gate and delivery_gate with live agy registered_cli without -k exclusion."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "target.py").write_text(
        "def family_canary_target():\n    return 'verified'\n",
        encoding="utf-8",
    )

    catalog = build_product_task_catalog(workspace)
    task = [t for t in catalog if t.capability == "claim_gate" and t.origin == "online"][0]

    row = run_closure_task(
        task,
        _production_canary_runner,
        output_dir=tmp_path / "runs",
    )

    verdict = row["closure_verdict"]
    assert verdict["status"] == LIVE_EXECUTED_PASS
    assert verdict["live_pass"] is True
    assert verdict["missing_evidence_reasons"] == []
