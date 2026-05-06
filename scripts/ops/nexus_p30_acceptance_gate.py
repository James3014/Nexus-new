#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.ops.brain_hub_audit import scan_brain_hub
from scripts.ops.hallucination_guard_drift import audit_drift
from scripts.ops.pipeline_composition_inventory import build_inventory


def _load_route_smoke(repo_root: Path) -> dict[str, Any]:
    path = repo_root / ".nexus" / "reports" / "capability_route_smoke_summary.json"
    if not path.exists():
        return {"passed": False, "blocked_reason": "route_smoke_summary_missing", "path": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_flash_bundle(repo_root: Path) -> dict[str, Any]:
    candidates = sorted((repo_root / ".nexus" / "reports").glob("**/evidence_bundle.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        if "bench_route_" in str(path):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        delivery_gate = payload.get("public_delivery_gate") if isinstance(payload, dict) else {}
        if not isinstance(delivery_gate, dict) or not delivery_gate:
            delivery_gate = payload.get("public_claim_gate", {}) if isinstance(payload, dict) else {}
        cost_gate = payload.get("public_cost_claim_gate", {}) if isinstance(payload, dict) else {}
        return {
            "path": str(path),
            "public_claim_gate": payload.get("public_claim_gate", {}) if isinstance(payload, dict) else {},
            "public_delivery_gate": delivery_gate,
            "public_cost_claim_gate": cost_gate,
            "passed": delivery_gate.get("verdict") == "PASS",
            "cost_claim_passed": cost_gate.get("verdict") == "PASS",
        }
    return {"passed": False, "blocked_reason": "flash_evidence_bundle_missing"}


def build_gate(repo_root: Path, *, require_flash: bool = False) -> dict[str, Any]:
    drift = audit_drift()
    hub = scan_brain_hub(repo_root, [], manifest_path=repo_root / "docs" / "ops" / "brain_hub_manifest.json")
    inventory = build_inventory(repo_root)
    route_smoke = _load_route_smoke(repo_root)
    flash = _latest_flash_bundle(repo_root)
    legacy_claim_gate = flash.get("public_claim_gate", {}) if isinstance(flash.get("public_claim_gate"), dict) else {}
    checks = {
        "hallucination_guard_drift": drift.passed,
        "brain_hub_audit": hub.passed,
        "pipeline_composition_inventory": bool(inventory.get("passed")),
        "route_smoke": bool(route_smoke.get("passed")),
        "flash_public_delivery_gate": bool(flash.get("passed")),
        "flash_public_cost_claim_gate": bool(flash.get("cost_claim_passed")),
        "flash_public_claim_gate": legacy_claim_gate.get("verdict") == "PASS",
    }
    optional_when_requiring_flash = {"flash_public_claim_gate", "flash_public_cost_claim_gate"}
    required = {
        key: value
        for key, value in checks.items()
        if (require_flash and key not in optional_when_requiring_flash) or (not require_flash and not key.startswith("flash_public_"))
    }
    return {
        "schema_version": "nexus_p30_acceptance_gate.v1",
        "passed": all(required.values()),
        "require_flash": require_flash,
        "checks": checks,
        "pipeline_composition": inventory,
        "route_smoke": route_smoke,
        "flash": flash,
        "failures": [name for name, passed in required.items() if not passed],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate P30 Nexus acceptance gates.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--require-flash", action="store_true")
    args = parser.parse_args(argv)
    payload = build_gate(Path(args.repo_root).resolve(), require_flash=args.require_flash)
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
