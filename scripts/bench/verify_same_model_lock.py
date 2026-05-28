#!/usr/bin/env python3
"""
verify_same_model_lock.py — PR1: Same-Model Baseline Preflight Verifier.

Standalone script to validate that env_model and direct_model are identical
before running a same-model paired A/B benchmark.

Usage:
  uv run scripts/bench/verify_same_model_lock.py \
    --env-model gemini-2.5-flash \
    --direct-model gemini-2.5-flash

  # Or from environment variables:
  NEXUS_GEMINI_MODEL_NAME=gemini-2.5-flash \
  NEXUS_DIRECT_GEMINI_MODEL=gemini-2.5-flash \
  uv run scripts/bench/verify_same_model_lock.py

Exit codes:
  0  — PASS: models match and without_mode is provider path
  2  — FAIL: model lock mismatch or bare arm is local-only
"""
import argparse
import json
import os
import sys


def verify_same_model_lock(
    env_model: str,
    direct_model: str,
    without_mode: str = "gemini",
) -> dict:
    """
    Verify same-model baseline conditions.

    Returns a result dict with:
      status: PASS | FAIL
      failures: list of failure codes
      model_lock: {env_model, direct_model, same_model, without_mode}
    """
    failures: list[str] = []

    # 1. without_mode must be a real provider path (not local bare)
    if without_mode not in {"gemini", "codex"}:
        failures.append("same_model_required_but_bare_arm_is_local")

    # 2. env_model must be set
    if not env_model:
        failures.append("same_model_required_but_env_model_missing")

    # 3. direct_model must be set
    if not direct_model:
        failures.append("same_model_required_but_direct_model_env_missing")

    # 4. models must match (only when both are present)
    if env_model and direct_model and env_model.strip() != direct_model.strip():
        failures.append(
            f"same_model_required_but_model_names_differ:"
            f"env={env_model!r},direct={direct_model!r}"
        )

    same_model = bool(
        env_model
        and direct_model
        and env_model.strip() == direct_model.strip()
        and without_mode in {"gemini", "codex"}
    )

    return {
        "schema": "nexus_same_model_lock_verify_v1",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "model_lock": {
            "env_model": env_model,
            "direct_model": direct_model,
            "same_model": same_model,
            "without_mode": without_mode,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify same-model baseline lock before A/B benchmark."
    )
    parser.add_argument(
        "--env-model",
        default=os.environ.get("NEXUS_GEMINI_MODEL_NAME", ""),
        help="The Nexus treatment arm model name (default: NEXUS_GEMINI_MODEL_NAME env var).",
    )
    parser.add_argument(
        "--direct-model",
        default=os.environ.get("NEXUS_DIRECT_GEMINI_MODEL", ""),
        help="The bare/direct baseline model name (default: NEXUS_DIRECT_GEMINI_MODEL env var).",
    )
    parser.add_argument(
        "--without-mode",
        choices=["bare", "service", "gemini", "codex"],
        default="gemini",
        help="The baseline arm mode. Must be 'gemini' or 'codex' for same-model paired comparison.",
    )
    args = parser.parse_args()

    result = verify_same_model_lock(
        env_model=args.env_model.strip(),
        direct_model=args.direct_model.strip(),
        without_mode=args.without_mode,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))

    if result["status"] != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
