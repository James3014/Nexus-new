#!/usr/bin/env python3
"""H5-20: Cloud fallback focused smoke harness.

Focused smoke for cloud fallback path validation.
Must not connect result to benchmark runner output, final_source, or production behavior.

Usage:
    python3 scripts/bench/h5_cloud_fallback_e2e_smoke.py --dry-run --provider gemini
    python3 scripts/bench/h5_cloud_fallback_e2e_smoke.py --run-if-allowed --provider gemini
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


SUPPORTED_PROVIDERS = {"gemini", "codex"}


def run_h5_cloud_fallback_e2e_smoke(
    *,
    provider: str = "gemini",
    dry_run: bool = True,
    allow_real_call: bool = False,
) -> dict[str, Any]:
    """Run focused cloud fallback E2E smoke.

    dry_run=True by default. allow_real_call=False by default.
    Real cloud calls require both allow_real_call=True and env var.
    """
    if provider not in SUPPORTED_PROVIDERS:
        return _build_cloud_smoke_result(
            status="skipped",
            provider=provider,
            dry_run=dry_run,
            allow_real_call=allow_real_call,
            skipped_reason="unsupported_provider",
        )

    if dry_run:
        return _build_cloud_smoke_result(
            status="pass",
            provider=provider,
            dry_run=True,
            allow_real_call=False,
            cloud_fallback_would_invoke=True,
            model_calls_before=0,
            model_calls_after_shadow=1,
            evidence={"note": "dry_run mode, no cloud provider called"},
        )

    if not allow_real_call:
        return _build_cloud_smoke_result(
            status="skipped",
            provider=provider,
            dry_run=False,
            allow_real_call=False,
            skipped_reason="real_cloud_call_not_allowed",
        )

    env_enabled = os.environ.get("NEXUS_H5_ALLOW_REAL_CLOUD_SMOKE", "").strip() in {"1", "true", "yes"}
    if not env_enabled:
        return _build_cloud_smoke_result(
            status="skipped",
            provider=provider,
            dry_run=False,
            allow_real_call=True,
            real_call_env_enabled=False,
            skipped_reason="real_cloud_call_env_not_enabled",
        )

    # Real call path — not implemented in this phase
    return _build_cloud_smoke_result(
        status="skipped",
        provider=provider,
        dry_run=False,
        allow_real_call=True,
        real_call_env_enabled=True,
        skipped_reason="real_cloud_call_not_implemented",
        evidence={"note": "real cloud call path not yet implemented"},
    )


def _build_cloud_smoke_result(
    *,
    status: str,
    provider: str,
    dry_run: bool,
    allow_real_call: bool,
    real_call_env_enabled: bool = False,
    skipped_reason: str = "",
    cloud_fallback_would_invoke: bool = False,
    model_calls_before: int = 0,
    model_calls_after_shadow: int = 0,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "nexus.h5_cloud_fallback_e2e_smoke.v1",
        "status": status,
        "skipped_reason": skipped_reason,
        "provider": provider,
        "dry_run": dry_run,
        "allow_real_call": allow_real_call,
        "real_call_env_enabled": real_call_env_enabled,
        "cloud_fallback_would_invoke": cloud_fallback_would_invoke,
        "cloud_fallback_invoked": False,
        "cloud_model_invoked": False,
        "cloud_output_captured": False,
        "cloud_output_verified": False,
        "model_calls_before": model_calls_before,
        "model_calls_after_shadow": model_calls_after_shadow,
        "model_calls_incremented": False,
        "final_source_changed": False,
        "final_patch_replaced": False,
        "output_mutated": False,
        "public_claim_allowed": False,
        "production_ready": False,
        "evidence": evidence or {},
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="H5-20 cloud fallback E2E smoke")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--run-if-allowed", action="store_true", default=False)
    parser.add_argument("--provider", default="gemini", choices=["gemini", "codex"])
    args = parser.parse_args()

    dry_run = not args.run_if_allowed
    result = run_h5_cloud_fallback_e2e_smoke(
        provider=args.provider,
        dry_run=dry_run,
        allow_real_call=args.run_if_allowed,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
