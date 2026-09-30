"""One-shot external bootstrap for the fixed Nexus Gateway manager artifact.

This is not a normal deployment path. It exists only to converge one exact
pre-effect stable manager when the normal host-effect authority is itself stale.
No Gateway process, launchd, recovery, merge, or release effect is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

REPOSITORY = "James3014/Nexus-new"
OWNER_LOGIN = "James3014"
OWNER_COMMENT_ID = 5915401527
OWNER_COMMENT_SHA256 = "63386ca9ac928e2208c4667be57cae3789b724809f38c4487e6086ac6eb5e29c"
ACCEPTED_COMMIT = "17fce58675c91fb91344da5ed5ede34a53a652a9"
ACCEPTED_TREE = "e34fd98ca7f56a42a43dee24e91d4f0aa4e1bcdd"
MANAGER_PATH = "scripts/ops/mcp_gateway_durable.py"
PREDECESSOR_SHA256 = "6e4fa4af4ba50eeb956c7b2ed2579c06dbc392576bf5893f4e93505f6120a6ef"
TARGET_SHA256 = "7f93a472870303d44f7c57b02362ac3f7599216576ce620334a847c4ce4a1e0c"
OPERATION_ID = "issue1237-g2-stable-manager-bootstrap-20260930-v1"
STATE_ROOT = Path.home() / "Library" / "Application Support" / "Nexus" / "gateway-direct"
REPOSITORY_MIRROR = STATE_ROOT / "repository.git"
DESTINATION = STATE_ROOT / "manager.py"


class BootstrapError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run(command: list[str], *, runner: Callable[..., Any] = subprocess.run) -> bytes:
    result = runner(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise BootstrapError(f"COMMAND_FAILED:{detail}")
    return bytes(result.stdout)


def _verify_owner_activation(*, runner: Callable[..., Any] = subprocess.run) -> None:
    raw = _run(
        ["gh", "api", f"repos/{REPOSITORY}/issues/comments/{OWNER_COMMENT_ID}"],
        runner=runner,
    )
    try:
        payload = json.loads(raw.decode("utf-8"))
        author = payload["user"]["login"]
        body = payload["body"]
    except (UnicodeError, ValueError, KeyError, TypeError) as exc:
        raise BootstrapError("OWNER_ACTIVATION_MALFORMED") from exc
    if author != OWNER_LOGIN:
        raise BootstrapError("OWNER_ACTIVATION_AUTHOR_MISMATCH")
    if _sha256(body.encode("utf-8")) != OWNER_COMMENT_SHA256:
        raise BootstrapError("OWNER_ACTIVATION_BODY_MISMATCH")


def _target_bytes(*, runner: Callable[..., Any] = subprocess.run) -> bytes:
    if not REPOSITORY_MIRROR.is_dir():
        raise BootstrapError("REPOSITORY_MIRROR_MISSING")
    tree = _run(
        ["git", "--git-dir", str(REPOSITORY_MIRROR), "rev-parse", f"{ACCEPTED_COMMIT}^{{tree}}"],
        runner=runner,
    ).decode().strip()
    if tree != ACCEPTED_TREE:
        raise BootstrapError("ACCEPTED_TREE_MISMATCH")
    data = _run(
        ["git", "--git-dir", str(REPOSITORY_MIRROR), "show", f"{ACCEPTED_COMMIT}:{MANAGER_PATH}"],
        runner=runner,
    )
    if _sha256(data) != TARGET_SHA256:
        raise BootstrapError("TARGET_MANAGER_HASH_MISMATCH")
    return data


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
def apply_bootstrap(*, dry_run: bool = False, runner: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    _verify_owner_activation(runner=runner)
    target = _target_bytes(runner=runner)
    if not DESTINATION.is_file() or DESTINATION.is_symlink():
        raise BootstrapError("STABLE_MANAGER_DESTINATION_INVALID")
    current = DESTINATION.read_bytes()
    current_hash = _sha256(current)
    if current_hash == TARGET_SHA256:
        return {
            "schema": "nexus.gateway.manager_bootstrap_receipt.v1",
            "operation_id": OPERATION_ID,
            "status": "ALREADY_CONVERGED",
            "effect_started": False,
            "predecessor_sha256": PREDECESSOR_SHA256,
            "target_sha256": TARGET_SHA256,
        }
    if current_hash != PREDECESSOR_SHA256:
        raise BootstrapError("STABLE_MANAGER_PREDECESSOR_MISMATCH")
    if dry_run:
        return {
            "schema": "nexus.gateway.manager_bootstrap_receipt.v1",
            "operation_id": OPERATION_ID,
            "status": "READY",
            "effect_started": False,
            "predecessor_sha256": PREDECESSOR_SHA256,
            "target_sha256": TARGET_SHA256,
        }
    parent = DESTINATION.parent
    fd, tmp_name = tempfile.mkstemp(prefix=".manager-bootstrap.", dir=parent)
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(target)
            handle.flush()
            os.fsync(handle.fileno())
        if _sha256(DESTINATION.read_bytes()) != PREDECESSOR_SHA256:
            raise BootstrapError("STABLE_MANAGER_PREDECESSOR_CHANGED")
        os.replace(tmp, DESTINATION)
        _fsync_dir(parent)
    finally:
        if tmp.exists():
            tmp.unlink()
    readback = DESTINATION.read_bytes()
    if _sha256(readback) != TARGET_SHA256:
        raise BootstrapError("STABLE_MANAGER_READBACK_MISMATCH")
    if (DESTINATION.stat().st_mode & 0o777) != 0o600:
        raise BootstrapError("STABLE_MANAGER_MODE_MISMATCH")
    return {
        "schema": "nexus.gateway.manager_bootstrap_receipt.v1",
        "operation_id": OPERATION_ID,
        "status": "CONVERGED",
        "effect_started": True,
        "predecessor_sha256": PREDECESSOR_SHA256,
        "target_sha256": TARGET_SHA256,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = apply_bootstrap(dry_run=args.dry_run)
    except BootstrapError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
