"""
Epistemic Workflow Benchmark v0 — Observation Import and Inventory.

Provides import_observation, import_observations, verify_observation,
and load_observation_inventory.
Oracle is never read during import. Correctness is never computed here.
No overwrite parameter or mechanism exists (ERB-R2B1).
"""
import fcntl
import json
import os
import re
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from nexus.research.epistemic_benchmark.contracts import (
    BENCHMARK_OBSERVATION_SCHEMA,
    BenchmarkArm,
    BenchmarkDecision,
    compute_canonical_sha256,
    validate_observation,
)
from nexus.research.epistemic_benchmark.packets import (
    load_packet,
    load_public_run_manifest,
    validate_public_run_integrity,
)

# ---------------------------------------------------------------------------
# Duplicate / conflict detection constants
# ---------------------------------------------------------------------------

BENCHMARK_DUPLICATE_OBSERVATION = "BENCHMARK_DUPLICATE_OBSERVATION"
BENCHMARK_DUPLICATE_EVALUATOR_OBSERVATION = "BENCHMARK_DUPLICATE_EVALUATOR_OBSERVATION"
BENCHMARK_OBSERVATION_INVENTORY_INVALID = "BENCHMARK_OBSERVATION_INVENTORY_INVALID"

OBS_PATH_COMPONENT_INVALID = "OBS_PATH_COMPONENT_INVALID"
OBS_DESTINATION_OUTSIDE_RUN = "OBS_DESTINATION_OUTSIDE_RUN"
OBS_IMPORT_LOCK_TIMEOUT = "OBS_IMPORT_LOCK_TIMEOUT"
OBS_IMPORT_INTERNAL_ERROR = "OBS_IMPORT_INTERNAL_ERROR"
OBS_SYMLINK_COMPONENT = "OBS_SYMLINK_COMPONENT"
OBS_INVENTORY_MANIFEST_INVALID = "OBS_INVENTORY_MANIFEST_INVALID"
OBSERVATION_LOCK_FILENAME = ".observation-import.lock"
IMPORT_LOCK_TIMEOUT_SECONDS = 10.0

_OBSERVATION_ID_RE = re.compile(r"^OBS-[A-Za-z0-9][A-Za-z0-9._-]{0,126}$")
_CASE_ALIAS_RE = re.compile(r"^CASE-[0-9A-F]{16}$")


def _observation_dir(run_dir: str, arm: str, case_alias: str) -> str:
    return os.path.join(run_dir, "observations", arm, case_alias)


def _observation_path(run_dir: str, arm: str, case_alias: str, observation_id: str) -> str:
    return os.path.join(_observation_dir(run_dir, arm, case_alias), f"{observation_id}.json")


def _validate_symlink_components(run_dir: str, arm: str, case_alias: str) -> List[str]:
    """Reject any existing symlink component in the destination chain.

    Uses os.path.islink (lstat-based) on run_dir, run_dir/observations,
    run_dir/observations/<arm>, and run_dir/observations/<arm>/<case_alias>.
    Missing components are allowed (they will be created as real directories);
    a component that exists as a symlink is rejected with OBS_SYMLINK_COMPONENT.
    """
    errors: List[str] = []
    components = [
        run_dir,
        os.path.join(run_dir, "observations"),
        os.path.join(run_dir, "observations", arm),
        os.path.join(run_dir, "observations", arm, case_alias),
    ]
    for component in components:
        if os.path.islink(component):
            errors.append(f"{OBS_SYMLINK_COMPONENT}: {component!r}")
    return errors


def _validate_import_path(run_dir: str, arm: str, case_alias: str, observation_id: str) -> List[str]:
    """Validate path components before any directory or temp file is created.
    Returns a list of stable error codes; empty means the path is safe."""
    errors: List[str] = []

    if (
        not isinstance(observation_id, str)
        or not _OBSERVATION_ID_RE.match(observation_id)
        or len(observation_id) > 127
        or ".." in observation_id
    ):
        errors.append(f"{OBS_PATH_COMPONENT_INVALID}: observation_id={observation_id!r}")

    if arm not in {e.value for e in BenchmarkArm}:
        errors.append(f"{OBS_PATH_COMPONENT_INVALID}: arm={arm!r}")

    if not isinstance(case_alias, str) or not _CASE_ALIAS_RE.match(case_alias):
        errors.append(f"{OBS_PATH_COMPONENT_INVALID}: case_alias={case_alias!r}")

    if errors:
        return errors

    # Symlink component rejection: refuse any existing symlink in the chain
    # before any lock, directory, or temp file is created.
    errors.extend(_validate_symlink_components(run_dir, arm, case_alias))

    # Root containment: the resolved observations root must itself remain a
    # descendant of the resolved run root (so a symlinked observations root
    # cannot redirect writes outside the run), and the resolved destination
    # must remain a descendant of the resolved observation root.
    resolved_run_root = os.path.realpath(os.path.abspath(run_dir))
    resolved_observation_root = os.path.realpath(
        os.path.abspath(os.path.join(run_dir, "observations"))
    )
    if not (
        resolved_observation_root == resolved_run_root
        or resolved_observation_root.startswith(resolved_run_root + os.sep)
    ):
        errors.append(
            f"{OBS_DESTINATION_OUTSIDE_RUN}: observations root resolves outside run root"
        )

    # Independent containment check: resolved destination must remain a
    # descendant of the resolved observation root.
    destination = _observation_path(run_dir, arm, case_alias, observation_id)
    resolved_destination = os.path.realpath(os.path.abspath(destination))
    if not (
        resolved_destination == resolved_observation_root
        or resolved_destination.startswith(resolved_observation_root + os.sep)
    ):
        errors.append(f"{OBS_DESTINATION_OUTSIDE_RUN}: destination={destination!r}")

    return errors


# ---------------------------------------------------------------------------
# Cross-thread / cross-process import lock
# ---------------------------------------------------------------------------

_import_critical_section = threading.Lock()


def _lock_path(run_dir: str) -> str:
    return os.path.join(run_dir, "observations", OBSERVATION_LOCK_FILENAME)


def _acquire_import_lock(run_dir: str, timeout_seconds: float) -> Optional[int]:
    """Acquire process-local (threading.Lock) and cross-process (flock) lock.
    Returns an open lock fd on success, None on timeout.
    The caller MUST call _release_import_lock(fd) on success."""
    if not _import_critical_section.acquire(timeout=timeout_seconds):
        return None
    lock_dir = os.path.join(run_dir, "observations")
    try:
        os.makedirs(lock_dir, exist_ok=True)
        fd = os.open(_lock_path(run_dir), os.O_RDWR | os.O_CREAT, 0o644)
    except Exception:
        _import_critical_section.release()
        raise
    try:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except OSError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    _import_critical_section.release()
                    return None
                time.sleep(0.005)
    except Exception:
        os.close(fd)
        _import_critical_section.release()
        raise


def _release_import_lock(fd: Optional[int]) -> None:
    """Release both the flock and the process-local lock. Safe to call once."""
    try:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
    finally:
        _import_critical_section.release()


def _load_packet_for_alias(run_dir: str, arm: str, case_alias: str) -> Optional[Dict[str, Any]]:
    """Load the packet for the given arm/alias. Returns None if not found."""
    pkt_path = os.path.join(run_dir, "packets", arm, f"{case_alias}.json")
    if not os.path.exists(pkt_path):
        return None
    try:
        with open(pkt_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _fsync_dir(directory: str) -> None:
    """Fsync a directory to make a just-created entry durable."""
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_no_overwrite_write(path: str, data: Dict[str, Any]) -> None:
    """
    Atomic no-overwrite publishing.
    Creates destination directory if needed, writes data to temporary file,
    flushes and syncs to disk, then atomically links/moves using O_CREAT | O_EXCL
    or os.link to guarantee existing files are NEVER overwritten (no TOCTOU race).
    On success the destination parent directory is fsynced. A failed cleanup of
    the temporary file raises a stable error rather than being silently ignored.
    """
    dest_dir = os.path.dirname(path)
    os.makedirs(dest_dir, exist_ok=True)

    # Temporary file in same directory for atomic link/move
    fd_tmp, tmp_path = tempfile.mkstemp(dir=dest_dir, suffix=".tmp")
    try:
        with os.fdopen(fd_tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        # macOS / POSIX atomic link / exclusive creation
        try:
            os.link(tmp_path, path)
        except FileExistsError:
            raise
        except (AttributeError, OSError):
            # Fallback for systems where os.link is restricted or cross-device
            fd_dst = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(fd_dst, "w", encoding="utf-8") as f_dst:
                with open(tmp_path, "r", encoding="utf-8") as f_src:
                    f_dst.write(f_src.read())
                f_dst.flush()
                os.fsync(f_dst.fileno())

        _fsync_dir(dest_dir)
    except FileExistsError:
        raise FileExistsError(f"DESTINATION_EXISTS: {path}")
    finally:
        if os.path.exists(tmp_path):
            last_err = None
            for _attempt in range(2):
                try:
                    os.remove(tmp_path)
                    last_err = None
                    break
                except OSError as e:
                    last_err = e
                    time.sleep(0.01)
            if last_err is not None:
                raise OSError(f"OBS_TMP_CLEANUP_FAILED: {tmp_path}: {last_err}")


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

    # Verify public run integrity first
    try:
        ok_run, run_errs = validate_public_run_integrity(run_dir)
        if not ok_run:
            errors.extend([f"PUBLIC_RUN_INTEGRITY_FAIL: {e}" for e in run_errs])
            return False, errors
    except Exception as e:
        errors.append(f"PUBLIC_RUN_INTEGRITY_EXCEPTION: {e}")
        return False, errors

    arm = obs.get("arm", "")
    case_alias = obs.get("case_alias", "")

    # Load public manifest packet commitment
    try:
        manifest = load_public_run_manifest(run_dir)
        expected_run_id = manifest.get("benchmark_run_id")
        if expected_run_id and obs.get("benchmark_run_id") != expected_run_id:
            errors.append(
                f"OBS_RUN_ID_MISMATCH: obs={obs.get('benchmark_run_id')!r} "
                f"manifest={expected_run_id!r}"
            )
        # Find packet entry in manifest
        manifest_packets = manifest.get("packets", [])
        m_pkt = None
        for p_entry in manifest_packets:
            if p_entry.get("arm") == arm and p_entry.get("case_alias") == case_alias:
                m_pkt = p_entry
                break
        if m_pkt is None:
            errors.append(f"MANIFEST_PACKET_NOT_FOUND: arm={arm} alias={case_alias}")
    except Exception as e:
        errors.append(f"MANIFEST_LOAD_ERROR: {e}")
        m_pkt = None

    # Load packet file
    packet = _load_packet_for_alias(run_dir, arm, case_alias)
    if packet is None:
        errors.append(f"OBS_PACKET_NOT_FOUND: arm={arm} alias={case_alias}")
        errors.extend(validate_observation(obs, packet=None))
        return False, errors

    # Verify arm and alias match packet
    if packet.get("arm") != arm:
        errors.append(f"OBS_ARM_MISMATCH: obs.arm={arm!r} packet.arm={packet.get('arm')!r}")

    if packet.get("case_alias") != case_alias:
        errors.append(
            f"OBS_ALIAS_MISMATCH: obs.case_alias={case_alias!r} "
            f"packet.case_alias={packet.get('case_alias')!r}"
        )

    # Exact Packet SHA-256 Binding Check:
    # obs.packet_sha256 == manifest.packet_sha256 == packet.packet_sha256 == recomputed packet SHA
    obs_pkt_sha = obs.get("packet_sha256")
    pkt_self_sha = packet.get("packet_sha256")
    body_pkt = {k: v for k, v in packet.items() if k != "packet_sha256"}
    recomputed_pkt_sha = compute_canonical_sha256(body_pkt)

    if pkt_self_sha != recomputed_pkt_sha:
        errors.append(f"PACKET_SELF_HASH_CORRUPTED: {pkt_self_sha!r} != {recomputed_pkt_sha!r}")

    if m_pkt and m_pkt.get("packet_sha256") != pkt_self_sha:
        errors.append(f"MANIFEST_PACKET_HASH_MISMATCH: manifest={m_pkt.get('packet_sha256')!r} packet={pkt_self_sha!r}")

    if obs_pkt_sha != pkt_self_sha:
        errors.append(f"OBS_PACKET_SHA256_MISMATCH: obs={obs_pkt_sha!r} packet={pkt_self_sha!r}")

    # Schema-level validation with packet context
    errors.extend(validate_observation(obs, packet=packet))

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Complete Observation Inventory
# ---------------------------------------------------------------------------


def load_observation_inventory(run_dir: str) -> Dict[str, Any]:
    """
    Build a complete inventory of all files under run_dir/observations/.
    Returns dict with keys: valid, invalid, unexpected_files, global_failures.
    No exceptions swallowed. All files are accounted for deterministically.
    """
    valid: List[Dict[str, Any]] = []
    invalid: List[Dict[str, Any]] = []
    unexpected_files: List[Dict[str, Any]] = []
    global_failures: List[str] = []

    obs_root = os.path.join(run_dir, "observations")
    if not os.path.exists(obs_root):
        return {
            "valid": [],
            "invalid": [],
            "unexpected_files": [],
            "global_failures": [],
        }

    # Tracking global duplicate detection across the entire run
    seen_obs_ids: Dict[str, str] = {}  # obs_id -> relative_path
    seen_evaluators: Dict[Tuple[str, str, str, str, str, str, str], str] = {}  # tuple -> relative_path

    # Check public run manifest run_id for evaluator tuple binding.
    # A manifest that cannot be loaded is surfaced, never silently ignored.
    manifest_run_id = None
    try:
        m = load_public_run_manifest(run_dir)
        manifest_run_id = m.get("benchmark_run_id")
    except Exception as e:
        global_failures.append(f"{OBS_INVENTORY_MANIFEST_INVALID}: {e}")

    valid_arms = {e.value for e in BenchmarkArm}

    # Unexpected directories (empty, unknown arm/alias, deep, symlink) are
    # recorded, never dropped.
    unexpected_dirs: Dict[str, Tuple[str, str, str]] = {}

    def _unexpected_dir(rel_dir, dir_arm, dir_alias, reason):
        unexpected_dirs[rel_dir] = (dir_arm, dir_alias, reason)

    # Walk directory structure deterministically
    for root, dirs, files in os.walk(obs_root):
        # Sort for deterministic processing order
        dirs.sort()
        files.sort()

        rel_dir = os.path.relpath(root, obs_root)
        dir_parts = [] if rel_dir == "." else rel_dir.split(os.sep)
        depth = len(dir_parts)

        inferred_arm = dir_parts[0] if len(dir_parts) >= 1 else ""
        inferred_alias = dir_parts[1] if len(dir_parts) >= 2 else ""

        # Unexpected directory detection (including empty nested directories).
        if depth == 1:
            if inferred_arm not in valid_arms:
                _unexpected_dir(rel_dir, inferred_arm, "", "UNKNOWN_ARM_DIRECTORY")
        elif depth >= 2 and dir_parts[0] in valid_arms:
            if not _CASE_ALIAS_RE.match(inferred_alias or ""):
                _unexpected_dir(rel_dir, inferred_arm, inferred_alias, "UNKNOWN_ALIAS_DIRECTORY")
            elif depth > 2:
                _unexpected_dir(rel_dir, inferred_arm, inferred_alias, "DEPTH_EXCEEDS_ARM_ALIAS")

        # Symlink directories are unexpected and must not be descended into.
        for d in list(dirs):
            if os.path.islink(os.path.join(root, d)):
                _unexpected_dir(os.path.relpath(os.path.join(root, d), run_dir),
                                inferred_arm, inferred_alias, "SYMLINK_DIRECTORY_NOT_ALLOWED")
                dirs.remove(d)

        for fname in files:
            full_path = os.path.join(root, fname)
            rel_file_path = os.path.relpath(full_path, run_dir)

            # The import lock file lives inside observations/ and is not an
            # observation; it must never appear in the inventory.
            if fname == OBSERVATION_LOCK_FILENAME:
                continue

            file_arm = inferred_arm if depth >= 1 else ""
            file_alias = inferred_alias if depth >= 2 else ""

            # Check symlink or path escape
            if os.path.islink(full_path):
                unexpected_files.append({
                    "relative_path": rel_file_path,
                    "arm": file_arm,
                    "case_alias": file_alias,
                    "reason": "SYMLINK_NOT_ALLOWED",
                })
                continue

            # Non-JSON or unexpected path depth
            if not fname.endswith(".json") or depth != 2:
                unexpected_files.append({
                    "relative_path": rel_file_path,
                    "arm": file_arm,
                    "case_alias": file_alias,
                    "reason": "UNEXPECTED_FILE_OR_DIRECTORY_STRUCTURE",
                })
                continue

            # Unknown arm directory
            if inferred_arm not in valid_arms:
                invalid.append({
                    "relative_path": rel_file_path,
                    "arm": inferred_arm,
                    "case_alias": inferred_alias,
                    "inferred_arm": inferred_arm,
                    "inferred_alias": inferred_alias,
                    "failure_codes": [f"UNKNOWN_ARM_DIRECTORY: {inferred_arm!r}"],
                })
                continue

            # Try loading JSON
            obs = None
            file_err = None
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    obs = json.load(f)
            except Exception as e:
                file_err = f"MALFORMED_JSON: {e}"

            if file_err is not None or not isinstance(obs, dict):
                invalid.append({
                    "relative_path": rel_file_path,
                    "arm": inferred_arm,
                    "case_alias": inferred_alias,
                    "inferred_arm": inferred_arm,
                    "inferred_alias": inferred_alias,
                    "failure_codes": [file_err or "ROOT_NOT_DICT"],
                })
                continue

            # Verify content arm and alias match path
            failures: List[str] = []
            obs_arm = obs.get("arm", "")
            obs_alias = obs.get("case_alias", "")
            obs_id = obs.get("observation_id", "")

            if obs_arm != inferred_arm:
                failures.append(f"PATH_CONTENT_ARM_MISMATCH: path={inferred_arm!r} content={obs_arm!r}")

            if obs_alias != inferred_alias:
                failures.append(f"PATH_CONTENT_ALIAS_MISMATCH: path={inferred_alias!r} content={obs_alias!r}")

            expected_fname = f"{obs_id}.json" if obs_id else ""
            if fname != expected_fname:
                failures.append(f"FILENAME_ID_MISMATCH: filename={fname!r} obs_id={obs_id!r}")

            # Verify observation logic and packet binding
            ok_obs, obs_errs = verify_observation(obs, run_dir)
            if not ok_obs:
                failures.extend(obs_errs)

            # Global Duplicate Observation ID check
            if obs_id:
                if obs_id in seen_obs_ids:
                    failures.append(f"{BENCHMARK_DUPLICATE_OBSERVATION}: duplicate of {seen_obs_ids[obs_id]!r}")
                else:
                    seen_obs_ids[obs_id] = rel_file_path

            # Duplicate Evaluator tuple check
            ev = obs.get("evaluator", {})
            if isinstance(ev, dict):
                run_id = obs.get("benchmark_run_id") or manifest_run_id or ""
                ev_tuple = (
                    str(run_id),
                    str(obs_arm),
                    str(obs_alias),
                    str(ev.get("provider", "")),
                    str(ev.get("model_id", "")),
                    str(ev.get("evaluator_id", "")),
                    str(ev.get("prompt_version", "")),
                )
                if any(ev_tuple[3:]):  # if evaluator keys populated
                    if ev_tuple in seen_evaluators:
                        failures.append(f"{BENCHMARK_DUPLICATE_EVALUATOR_OBSERVATION}: duplicate of {seen_evaluators[ev_tuple]!r}")
                    else:
                        seen_evaluators[ev_tuple] = rel_file_path

            if failures:
                # When content parsed, attribute by content; otherwise fall
                # back to the path-derived arm/alias so report counts work.
                invalid.append({
                    "relative_path": rel_file_path,
                    "arm": obs_arm or inferred_arm,
                    "case_alias": obs_alias or inferred_alias,
                    "inferred_arm": inferred_arm,
                    "inferred_alias": inferred_alias,
                    "failure_codes": failures,
                })
            else:
                valid.append({
                    "relative_path": rel_file_path,
                    "arm": obs_arm,
                    "case_alias": obs_alias,
                    "observation_id": obs_id,
                    "packet_sha256": obs.get("packet_sha256", ""),
                    "observation": obs,
                })

    # Materialize unexpected directory records (including empty / deep ones).
    for rel_dir, (dir_arm, dir_alias, reason) in sorted(unexpected_dirs.items()):
        unexpected_files.append({
            "relative_path": os.path.join("observations", rel_dir),
            "arm": dir_arm,
            "case_alias": dir_alias,
            "reason": reason,
        })

    # Sort all sections by relative_path ascending for determinism
    valid.sort(key=lambda x: x["relative_path"])
    invalid.sort(key=lambda x: x["relative_path"])
    unexpected_files.sort(key=lambda x: x["relative_path"])
    global_failures.sort()

    return {
        "valid": valid,
        "invalid": invalid,
        "unexpected_files": unexpected_files,
        "global_failures": global_failures,
    }


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def import_observation(
    run_dir: str,
    observation: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """
    Import a single observation into the run directory.

    Rules:
    - Does not read oracle.
    - Does not compute correctness.
    - Atomic no-overwrite write.
    - No allow_overwrite parameter exists.
    - Path components validated before any directory or temp file is created.
    - The whole critical section (inventory scan, duplicate check, verify,
      write) runs under a cross-thread and cross-process lock per run.
    - Full inventory pre-check: fail closed if inventory invalid or duplicate.

    Returns (success, errors).
    """
    if not isinstance(observation, dict):
        return False, ["OBS_NOT_DICT"]

    arm = observation.get("arm", "")
    case_alias = observation.get("case_alias", "")
    obs_id = observation.get("observation_id", "")

    if not obs_id:
        return False, ["OBS_ID_MISSING"]

    # Path safety: fast-fail before any lock, directory, or temp file creation.
    path_errs = _validate_import_path(run_dir, arm, case_alias, obs_id)
    if path_errs:
        return False, path_errs

    fd = _acquire_import_lock(run_dir, IMPORT_LOCK_TIMEOUT_SECONDS)
    if fd is None:
        return False, [OBS_IMPORT_LOCK_TIMEOUT]

    # Every path after lock acquisition is wrapped in a single try/finally so
    # the lock is always released exactly once, including on unexpected
    # exceptions (no scattered manual _release() branches, no leaks).
    try:
        # Under-lock recheck: symlink components and root containment can change
        # between the pre-check above and the moment the lock is held.
        path_errs = _validate_import_path(run_dir, arm, case_alias, obs_id)
        if path_errs:
            return False, path_errs

        # Fail closed on an invalid public run before any inventory scan or write.
        ok_run, run_errs = validate_public_run_integrity(run_dir)
        if not ok_run:
            return False, [f"PUBLIC_RUN_INTEGRITY_FAIL: {e}" for e in run_errs]

        # Pre-inventory check: fail closed if existing inventory contains invalid files
        # or if obs_id / evaluator tuple is already present
        inventory = load_observation_inventory(run_dir)
        if inventory.get("invalid") or inventory.get("unexpected_files") or inventory.get("global_failures"):
            # Check if invalid contains corrupt state that blocks safe import
            inv_errs = [item["failure_codes"] for item in inventory.get("invalid", [])]
            # Return inventory invalid status
            return False, [BENCHMARK_OBSERVATION_INVENTORY_INVALID, f"Existing inventory contains invalid entries: {inv_errs}"]

        # Check for duplicate observation_id globally across valid items
        for item in inventory.get("valid", []):
            if item.get("observation_id") == obs_id:
                return False, [BENCHMARK_DUPLICATE_OBSERVATION]

        # Check for duplicate evaluator tuple
        ev = observation.get("evaluator", {})
        if isinstance(ev, dict):
            new_ev_tuple = (
                str(observation.get("benchmark_run_id", "")),
                str(arm),
                str(case_alias),
                str(ev.get("provider", "")),
                str(ev.get("model_id", "")),
                str(ev.get("evaluator_id", "")),
                str(ev.get("prompt_version", "")),
            )
            for item in inventory.get("valid", []):
                v_obs = item.get("observation", {})
                v_ev = v_obs.get("evaluator", {})
                if isinstance(v_ev, dict):
                    existing_tuple = (
                        str(v_obs.get("benchmark_run_id", "")),
                        str(v_obs.get("arm", "")),
                        str(v_obs.get("case_alias", "")),
                        str(v_ev.get("provider", "")),
                        str(v_ev.get("model_id", "")),
                        str(v_ev.get("evaluator_id", "")),
                        str(v_ev.get("prompt_version", "")),
                    )
                    if new_ev_tuple == existing_tuple:
                        return False, [BENCHMARK_DUPLICATE_EVALUATOR_OBSERVATION]

        # Verify observation
        valid, errors = verify_observation(observation, run_dir)
        if not valid:
            return False, errors

        dest_path = _observation_path(run_dir, arm, case_alias, obs_id)

        try:
            _atomic_no_overwrite_write(dest_path, observation)
        except FileExistsError:
            return False, [BENCHMARK_DUPLICATE_OBSERVATION]
        except Exception as e:
            return False, [f"OBS_WRITE_ERROR: {e}"]

        return True, []
    except Exception as e:
        return False, [f"{OBS_IMPORT_INTERNAL_ERROR}: {type(e).__name__}"]
    finally:
        _release_import_lock(fd)


def import_observation_from_file(
    run_dir: str,
    observation_path: str,
) -> Tuple[bool, List[str]]:
    """Import an observation from a JSON file path."""
    try:
        with open(observation_path, "r", encoding="utf-8") as f:
            observation = json.load(f)
    except Exception as e:
        return False, [f"OBS_FILE_LOAD_ERROR: {e}"]
    return import_observation(run_dir, observation)


def import_observations(
    run_dir: str,
    observation_paths: List[str],
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
        success, errors = import_observation_from_file(run_dir, path)
        if success:
            results["imported"].append(path)
        else:
            results["failed"].append(path)
            results["errors"][path] = errors
    return results


# ---------------------------------------------------------------------------
# Observation loading (driven by load_observation_inventory)
# ---------------------------------------------------------------------------


def load_all_observations(run_dir: str) -> List[Dict[str, Any]]:
    """
    Load all valid observations from run_dir/observations/.
    Driven by load_observation_inventory.
    Returns list of observation dicts.
    """
    inventory = load_observation_inventory(run_dir)
    return [item["observation"] for item in inventory.get("valid", [])]


def load_valid_observations(run_dir: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Load all observations and split into valid and invalid.
    No oracle check. Driven by load_observation_inventory.
    Returns (valid_obs, invalid_metadata).
    """
    inventory = load_observation_inventory(run_dir)
    valid_obs = [item["observation"] for item in inventory.get("valid", [])]
    invalid_metadata = inventory.get("invalid", []) + inventory.get("unexpected_files", [])
    return valid_obs, invalid_metadata


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
    packet_sha256: Optional[str] = None,
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
        "packet_sha256": packet_sha256 or "0" * 64,
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
