from __future__ import annotations

import json
import pytest
import tempfile
from pathlib import Path
from nexus.services.local_heal.p8_smoke_prompt_capsule import (
    P8SmokePromptCapsule,
    compute_p8_smoke_prompt_capsule,
    write_p8_smoke_prompt_capsule_artifact,
    p8_smoke_prompt_capsule_to_dict,
)


# ============================================================
# B3-1: default capsule valid
# ============================================================


def test_default_capsule_valid():
    capsule = compute_p8_smoke_prompt_capsule()
    assert capsule.prompt_capsule_valid is True
    assert capsule.synthetic_prompt_only is True
    assert capsule.repo_context_included is False
    assert capsule.private_data_included is False
    assert capsule.patch_request_included is False
    assert capsule.tool_request_included is False


# ============================================================
# B3-2: redacted prompt hash present
# ============================================================


def test_redacted_prompt_hash_present():
    capsule = compute_p8_smoke_prompt_capsule()
    assert capsule.redacted_prompt_hash != ""


# ============================================================
# B3-3: raw prompt hash present
# ============================================================


def test_raw_prompt_hash_present():
    capsule = compute_p8_smoke_prompt_capsule()
    assert capsule.raw_prompt_hash != ""


# ============================================================
# B3-4: artifact JSON exists
# ============================================================


def test_artifact_json_exists():
    capsule = compute_p8_smoke_prompt_capsule()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    write_p8_smoke_prompt_capsule_artifact(capsule, path)
    assert Path(path).exists()
    Path(path).unlink()


# ============================================================
# B3-5: artifact reloads
# ============================================================


def test_artifact_reloads():
    capsule = compute_p8_smoke_prompt_capsule()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    write_p8_smoke_prompt_capsule_artifact(capsule, path)
    with open(path) as f:
        loaded = json.load(f)
    assert loaded["capsule_version"] == "1.0"
    assert loaded["synthetic_prompt_only"] is True
    Path(path).unlink()


# ============================================================
# B3-6: JSON serialization works
# ============================================================


def test_json_serializable():
    capsule = compute_p8_smoke_prompt_capsule()
    d = p8_smoke_prompt_capsule_to_dict(capsule)
    assert isinstance(json.dumps(d), str)
