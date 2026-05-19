from __future__ import annotations

import json

from scripts.ops.build_route_context_seam_freeze import build_route_context_seam_freeze_from_artifacts


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_route_context_seam_freeze_from_clean_artifacts(tmp_path):
    route = tmp_path / "route.json"
    context = tmp_path / "context.json"
    read_model = tmp_path / "read_model.json"
    output = tmp_path / "freeze.json"
    _write(route, {"runtime_dispatch_changed": False})
    _write(context, {"preserved_L0_L1": True})
    _write(read_model, {"status": "PASS"})

    summary = build_route_context_seam_freeze_from_artifacts(
        route_manifest_path=route,
        context_contract_path=context,
        claim_read_model_path=read_model,
        output_path=output,
        allowed_next_work=("context_refactor",),
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert summary["status"] == "PASS"
    assert payload["blockers"] == []
    assert payload["claim_read_model_ref"] == str(read_model)
    assert payload["allowed_next_work"] == ["context_refactor"]


def test_build_route_context_seam_freeze_returns_on_runtime_dispatch_change(tmp_path):
    route = tmp_path / "route.json"
    context = tmp_path / "context.json"
    read_model = tmp_path / "read_model.json"
    output = tmp_path / "freeze.json"
    _write(route, {"runtime_dispatch_changed": True})
    _write(context, {"preserved_L0_L1": True})
    _write(read_model, {"status": "PASS"})

    summary = build_route_context_seam_freeze_from_artifacts(
        route_manifest_path=route,
        context_contract_path=context,
        claim_read_model_path=read_model,
        output_path=output,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert summary["status"] == "RETURN"
    assert "runtime_dispatch_changed" in payload["blockers"]


def test_build_route_context_seam_freeze_dry_run_does_not_write(tmp_path):
    route = tmp_path / "route.json"
    context = tmp_path / "context.json"
    read_model = tmp_path / "read_model.json"
    output = tmp_path / "freeze.json"
    _write(route, {"runtime_dispatch_changed": False})
    _write(context, {"preserved_L0_L1": True})
    _write(read_model, {"status": "PASS"})

    summary = build_route_context_seam_freeze_from_artifacts(
        route_manifest_path=route,
        context_contract_path=context,
        claim_read_model_path=read_model,
        output_path=output,
        dry_run=True,
    )

    assert summary["status"] == "PASS"
    assert output.exists() is False
