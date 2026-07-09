from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_CAPSULE_PATH = Path("artifacts/effect_reports/p8_smoke_prompt_capsule_v0.json")


@dataclass(frozen=True)
class P8SmokePromptCapsule:
    """P8-B3: Synthetic smoke prompt capsule."""
    capsule_version: str
    prompt_kind: str
    raw_prompt_hash: str
    redacted_prompt: str
    redacted_prompt_hash: str
    synthetic_prompt_only: bool
    repo_context_included: bool
    private_data_included: bool
    secrets_detected: bool
    secrets_redacted: bool
    patch_request_included: bool
    tool_request_included: bool
    prompt_capsule_valid: bool
    blocked_reasons: list[str] = field(default_factory=list)


SYNTHETIC_PROMPT = '{"action": "echo", "message": "Nexus P8 smoke test complete", "timestamp": "REDACTED"}'


def compute_p8_smoke_prompt_capsule() -> P8SmokePromptCapsule:
    """Compute smoke prompt capsule."""
    blocked_reasons: list[str] = []
    raw_hash = hashlib.sha256(SYNTHETIC_PROMPT.encode("utf-8")).hexdigest()
    redacted_hash = hashlib.sha256(SYNTHETIC_PROMPT.encode("utf-8")).hexdigest()

    return P8SmokePromptCapsule(
        capsule_version="1.0",
        prompt_kind="synthetic_one_line_json",
        raw_prompt_hash=raw_hash,
        redacted_prompt=SYNTHETIC_PROMPT,
        redacted_prompt_hash=redacted_hash,
        synthetic_prompt_only=True,
        repo_context_included=False,
        private_data_included=False,
        secrets_detected=False,
        secrets_redacted=True,
        patch_request_included=False,
        tool_request_included=False,
        prompt_capsule_valid=True,
        blocked_reasons=blocked_reasons,
    )


def write_p8_smoke_prompt_capsule_artifact(
    capsule: P8SmokePromptCapsule,
    path: str | Path | None = None,
) -> Path:
    """Write capsule artifact."""
    p = Path(path) if path else DEFAULT_CAPSULE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump({
            "capsule_version": capsule.capsule_version,
            "prompt_kind": capsule.prompt_kind,
            "raw_prompt_hash": capsule.raw_prompt_hash,
            "redacted_prompt": capsule.redacted_prompt,
            "redacted_prompt_hash": capsule.redacted_prompt_hash,
            "synthetic_prompt_only": capsule.synthetic_prompt_only,
            "prompt_capsule_valid": capsule.prompt_capsule_valid,
        }, f, indent=2)
    return p


def p8_smoke_prompt_capsule_to_dict(capsule: P8SmokePromptCapsule) -> dict[str, Any]:
    return {
        "p8_capsule_version": capsule.capsule_version,
        "p8_prompt_kind": capsule.prompt_kind,
        "p8_raw_prompt_hash": capsule.raw_prompt_hash,
        "p8_redacted_prompt": capsule.redacted_prompt,
        "p8_redacted_prompt_hash": capsule.redacted_prompt_hash,
        "p8_synthetic_prompt_only": capsule.synthetic_prompt_only,
        "p8_repo_context_included": capsule.repo_context_included,
        "p8_private_data_included": capsule.private_data_included,
        "p8_secrets_detected": capsule.secrets_detected,
        "p8_secrets_redacted": capsule.secrets_redacted,
        "p8_patch_request_included": capsule.patch_request_included,
        "p8_tool_request_included": capsule.tool_request_included,
        "p8_prompt_capsule_valid": capsule.prompt_capsule_valid,
        "p8_blocked_reasons": capsule.blocked_reasons,
    }
