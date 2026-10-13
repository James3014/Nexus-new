"""entropy_guard_v2 verdicts on real code/prose vs credential-like output (#1907)."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest

from nexus.services.entropy_v2 import SEGMENT_ENTROPY_THRESHOLD, EntropyGuardV2

REPO = Path(__file__).resolve().parents[2]
REAL_TEXTS = [
    REPO / "nexus" / "services" / "entropy_v2.py",
    REPO / "nexus" / "orchestrator" / "file_lock_registry.py",
    REPO / "README.md",
]


@pytest.mark.parametrize("path", REAL_TEXTS, ids=lambda p: p.name)
def test_real_code_and_prose_pass(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    result = EntropyGuardV2().audit_payload(text)
    # Whole-text entropy of real files is above the retired 4.5 cutoff for most code/docs;
    # it is reported only.
    assert result["status"] == "PASSED", result
    assert result["high_entropy_segments"] == 0


def _generated_keys() -> list[str]:
    # Credential-shaped values built at run time (no literal key in the repository).
    raw = [hashlib.sha256(f"entropy-calibration-{i}".encode()).digest() for i in range(3)]
    b64 = [base64.b64encode(r).decode() for r in raw]
    return [b64[0], "key_" + b64[1][:36].replace("/", "x"), "tok=" + b64[2][:30] + "!#@$"]


@pytest.mark.parametrize("secret", _generated_keys())
def test_credential_like_segment_is_vetoed_inside_normal_prose(secret: str) -> None:
    text = f"The deploy step reads the key {secret} from the vault and then exits."
    result = EntropyGuardV2().audit_payload(text)
    assert result["status"] == "VETOED"
    assert result["max_segment_entropy"] > SEGMENT_ENTROPY_THRESHOLD
    assert secret not in str(result)  # the verdict never echoes the secret


def test_paths_identifiers_and_hashes_pass() -> None:
    text = (
        "see docs/reports/NEXUS_SF_CAPABILITY_SKILL_DISCOVERY_SCHEDULER_2026-05-18.md and "
        "test_capability_wiring_fixes_batch1 at commit 68e86ed591de8c4a555d3588e97e5e9cf6ff9692"
    )
    assert EntropyGuardV2().audit_payload(text)["status"] == "PASSED"
