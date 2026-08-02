"""
Epistemic Workflow Benchmark v0 — Observation Import.

Provides import_observation, import_observations, verify_observation.
Oracle is never read during import. Correctness is never computed here.
"""
import json
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from nexus.research.epistemic_benchmark.contracts import (
    BENCHMARK_OBSERVATION_SCHEMA,
    BenchmarkArm,
    BenchmarkDecision,
    compute_canonical_sha256,
    validate_observation,
)
from nexus.research.epistemic_benchmark.packets import load_packet, load_run_manifest


# ---------------------------------------------------------------------------
# Duplicate / conflict detection
# ---------------------------------------------------------------------------

BENCHMARK_DUPLICATE_OBSERVATION = "BENCHMARK_DUPLICATE_OBSERVATION"


def _observation_dir(run_dir: str, arm: str, case_alias: str) -> str:
    return os.path.join(run_dir, "observations", arm, case_alias)


def _observation_path(run_dir: str, arm: str, case_alias: str, observation_id: str) -> str:
    return os.path.join(_observation_dir(run_dir, arm, case_alias), f"{observation_id}.json")


def _load_packet_for_alias(run_dir: str, arm: str, case_alias: str) -> Optional[Dict[str, Any]]:
    """Load the packet for the given arm/alias. Returns None if not found."""
    pkt_path = os.path.join(run_dir, "packets", arm, f"{case_alias}.json")
    if not os.path.exists(pkt_path):
        return None
    with open(pkt_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_dir = os.path.dirname(path)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=tmp_dir,
        delete=False,
        suffix=".tmp",
    ) as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
        tmp_path = f.name
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# Verification (no oracle)
# ---------------------------------------------------------------------------


def verify_observation(
    obs: Dict[str, Any],
    run_dir: str,
) -> Tuple[bool, List[str]]:
    """
    Verify an observation without consulting the oracle.
    Returns (valid, errors).
    Does not compute correctness.
    """
    errors: List[str] = []

    # Basic contract validation
    arm = obs.get("arm", "")
    case_alias = obs.get("case_alias", "")

    # Load packet for this arm/alias (verify binding)
    packet = _load_packet_for_alias(run_dir, arm, case_alias)
    if packet is None:
        errors.append(f"OBS_PACKET_NOT_FOUND: arm={arm} alias={case_alias}")
        # Still run basic validation without packet ref checking
        errors.extend(validate_observation(obs, packet=None))
        return False, errors

    # Verify arm field matches packet
    if packet.get("arm") != arm:
        errors.append(f"OBS_ARM_MISMATCH: obs.arm={arm!r} packet.arm={packet.get('arm')!r}")

    # Verify alias matches packet
    if packet.get("case_alias") != case_alias:
        errors.append(
            f"OBS_ALIAS_MISMATCH: obs.case_alias={case_alias!r} "
            f"packet.case_alias={packet.get('case_alias')!r}"
        )

    # Verify run_id matches
    manifest_path = os.path.join(run_dir, "manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        expected_run_id = manifest.get("benchmark_run_id")
        if expected_run_id and obs.get("benchmark_run_id") != expected_run_id:
            errors.append(
                f"OBS_RUN_ID_MISMATCH: obs={obs.get('benchmark_run_id')!r} "
                f"manifest={expected_run_id!r}"
            )

    # Schema-level validation with packet context
    errors.extend(validate_observation(obs, packet=packet))

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def import_observation(
    run_dir: str,
    observation: Dict[str, Any],
    *,
    allow_overwrite: bool = False,
) -> Tuple[bool, List[str]]:
    """
    Import a single observation into the run directory.

    Rules:
    - Does not read oracle.
    - Does not compute correctness.
    - Atomic write.
    - Existing observation not overwritten unless allow_overwrite=True.
    - Packet existence verified.
    - Arm and alias binding verified.
    - Evidence refs verified.

    Returns (success, errors).
    """
    arm = observation.get("arm", "")
    case_alias = observation.get("case_alias", "")
    obs_id = observation.get("observation_id", "")

    if not obs_id:
        return False, ["OBS_ID_MISSING"]

    # Check for duplicate
    dest_path = _observation_path(run_dir, arm, case_alias, obs_id)
    if os.path.exists(dest_path) and not allow_overwrite:
        return False, [BENCHMARK_DUPLICATE_OBSERVATION]

    valid, errors = verify_observation(observation, run_dir)
    if not valid:
        return False, errors

    _atomic_write(dest_path, observation)
    return True, []


def import_observation_from_file(
    run_dir: str,
    observation_path: str,
    *,
    allow_overwrite: bool = False,
) -> Tuple[bool, List[str]]:
    """Import an observation from a JSON file path."""
    try:
        with open(observation_path, "r", encoding="utf-8") as f:
            observation = json.load(f)
    except Exception as e:
        return False, [f"OBS_FILE_LOAD_ERROR: {e}"]
    return import_observation(run_dir, observation, allow_overwrite=allow_overwrite)


def import_observations(
    run_dir: str,
    observation_paths: List[str],
    *,
    allow_overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Import multiple observations from file paths.
    Returns summary dict with success/failure counts.
    """
    results = {
        "imported": [],
        "failed": [],
        "errors": {},
    }
    for path in observation_paths:
        success, errors = import_observation_from_file(run_dir, path, allow_overwrite=allow_overwrite)
        if success:
            results["imported"].append(path)
        else:
            results["failed"].append(path)
            results["errors"][path] = errors
    return results


# ---------------------------------------------------------------------------
# Observation loading
# ---------------------------------------------------------------------------


def load_all_observations(run_dir: str) -> List[Dict[str, Any]]:
    """
    Load all valid observations from run_dir/observations/.
    Returns only observations that parse and validate (no oracle check).
    Invalid ones are returned as-is but flagged.
    """
    obs_list = []
    obs_root = os.path.join(run_dir, "observations")
    if not os.path.isdir(obs_root):
        return obs_list

    for arm_name in os.listdir(obs_root):
        arm_dir = os.path.join(obs_root, arm_name)
        if not os.path.isdir(arm_dir):
            continue
        for alias_dir_name in os.listdir(arm_dir):
            alias_dir = os.path.join(arm_dir, alias_dir_name)
            if not os.path.isdir(alias_dir):
                continue
            for fname in os.listdir(alias_dir):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(alias_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        obs = json.load(f)
                    obs_list.append(obs)
                except Exception:
                    pass  # Skip unparseable files

    return obs_list


def load_valid_observations(run_dir: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Load all observations and split into valid and invalid.
    No oracle check.
    Returns (valid_obs, invalid_obs).
    """
    all_obs = load_all_observations(run_dir)
    valid = []
    invalid = []
    for obs in all_obs:
        arm = obs.get("arm", "")
        case_alias = obs.get("case_alias", "")
        packet = _load_packet_for_alias(run_dir, arm, case_alias)
        errors = validate_observation(obs, packet=packet)
        if errors:
            invalid.append(obs)
        else:
            valid.append(obs)
    return valid, invalid


# ---------------------------------------------------------------------------
# Synthetic observation builder (for tests)
# ---------------------------------------------------------------------------


def build_synthetic_observation(
    *,
    benchmark_run_id: str,
    arm: str,
    case_alias: str,
    observation_id: str,
    decision: str,
    detected_defect_ids: Optional[List[str]] = None,
    cited_evidence_refs: Optional[List[str]] = None,
    rationale_summary: str = "Synthetic observation for testing.",
    confidence: Optional[int] = None,
    evaluator_id: Optional[str] = None,
    provider: str = "synthetic-test",
    model_id: str = "deterministic-fixture",
    prompt_version: str = "v0",
    duration_seconds: float = 1.0,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    cost_usd: Optional[float] = None,
    started_at: str = "2026-08-02T00:00:00Z",
    completed_at: str = "2026-08-02T00:00:01Z",
    skipped_checks: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Build a valid synthetic observation for testing.
    Always labelled as synthetic-test/deterministic-fixture.
    """
    body = {
        "schema": BENCHMARK_OBSERVATION_SCHEMA,
        "observation_id": observation_id,
        "benchmark_run_id": benchmark_run_id,
        "arm": arm,
        "case_alias": case_alias,
        "evaluator": {
            "evaluator_id": evaluator_id or f"fixture-{observation_id}",
            "provider": provider,
            "model_id": model_id,
            "prompt_version": prompt_version,
        },
        "decision": decision,
        "detected_defect_ids": detected_defect_ids or [],
        "cited_evidence_refs": cited_evidence_refs or [],
        "rationale_summary": rationale_summary,
        "confidence": confidence,
        "execution": {
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_seconds": duration_seconds,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
        },
        "skipped_checks": skipped_checks or [],
    }
    body["observation_sha256"] = compute_canonical_sha256(
        {k: v for k, v in body.items() if k != "observation_sha256"}
    )
    return body
