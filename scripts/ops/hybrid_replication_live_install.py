#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import subprocess
from pathlib import Path
from typing import Any

LIVE_BUNDLE_FILES = (
    "nexus/__init__.py",
    "nexus/research/__init__.py",
    "nexus/research/hybrid_replication_pipeline.py",
    "scripts/ops/hybrid_replication_daemon.py",
    "scripts/ops/hybrid_replication_live_stack.py",
    "scripts/ops/hybrid_replication_ground_truth.py",
)

LABEL = "com.nexus.hybrid-replication"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_show(repo: Path, revision: str, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"bundle_source_missing:{path}")
    return completed.stdout


def build_live_bundle(
    *,
    source_repo: Path,
    source_revision: str,
    install_root: Path,
) -> dict[str, Any]:
    bundle_root = install_root / "bundles" / source_revision
    manifest_path = bundle_root / "MANIFEST.json"
    files: dict[str, str] = {}
    for relative in LIVE_BUNDLE_FILES:
        data = _git_show(source_repo, source_revision, relative)
        destination = bundle_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != data:
                raise RuntimeError(f"bundle_file_conflict:{relative}")
        else:
            destination.write_bytes(data)
        files[relative] = _sha256(data)
    payload = {
        "schema": "nexus.hybrid_replication.live_bundle.v1",
        "source_revision": source_revision,
        "files": files,
    }
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    if manifest_path.exists():
        if manifest_path.read_bytes() != encoded:
            raise RuntimeError("bundle_manifest_conflict")
    else:
        manifest_path.write_bytes(encoded)
    return {
        **payload,
        "bundle_root": str(bundle_root),
        "manifest_sha256": _sha256(encoded),
    }


def render_launchd_plist(
    *,
    python: str,
    bundle_root: Path,
    experiment_root: Path,
    d0_root: Path,
    repo_map: Path,
    t_auto: str,
    frozen_policy_sha256: str,
) -> bytes:
    live_root = experiment_root / "live"
    state_root = live_root / "state"
    effect_root = live_root / "effects"
    log_root = live_root / "logs"
    stack_command = " ".join(
        [
            python,
            str(bundle_root / "scripts/ops/hybrid_replication_live_stack.py"),
            "--repo-map",
            str(repo_map),
            "--d0-root",
            str(d0_root),
            "--effect-root",
            str(effect_root),
        ]
    )
    ground_truth_command = " ".join(
        [
            python,
            str(bundle_root / "scripts/ops/hybrid_replication_ground_truth.py"),
        ]
    )
    args = [
        python,
        str(bundle_root / "scripts/ops/hybrid_replication_daemon.py"),
        "--root",
        str(state_root),
        "--since",
        t_auto,
        "--frozen-policy-sha256",
        frozen_policy_sha256,
        "--stack-command",
        stack_command,
        "--ground-truth-command",
        ground_truth_command,
    ]
    payload = {
        "Label": LABEL,
        "ProgramArguments": args,
        "WorkingDirectory": str(bundle_root),
        "EnvironmentVariables": {
            "PYTHONPATH": str(bundle_root),
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(Path.home()),
        },
        "RunAtLoad": True,
        "StartInterval": 60,
        "StandardOutPath": str(log_root / "stdout.log"),
        "StandardErrorPath": str(log_root / "stderr.log"),
        "ProcessType": "Background",
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)


def _verify_python(python: str) -> None:
    completed = subprocess.run(
        [
            python,
            "-c",
            "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 2)",
        ],
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("python_3_11_or_newer_required")


def _launch_agent(plist_path: Path) -> None:
    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["launchctl", "bootout", domain, str(plist_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    completed = subprocess.run(
        ["launchctl", "bootstrap", domain, str(plist_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"launchd_bootstrap_failed:{completed.stderr.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-repo", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--experiment-root", required=True)
    parser.add_argument("--d0-root", required=True)
    parser.add_argument("--repo-map", required=True)
    parser.add_argument("--t-auto")
    parser.add_argument("--frozen-policy-sha256")
    parser.add_argument("--python", default="/opt/homebrew/bin/python3")
    parser.add_argument("--load", action="store_true")
    args = parser.parse_args()

    source_repo = Path(args.source_repo)
    experiment_root = Path(args.experiment_root)
    live_root = experiment_root / "live"
    live_root.mkdir(parents=True, exist_ok=True)
    _verify_python(args.python)
    bundle = build_live_bundle(
        source_repo=source_repo,
        source_revision=args.source_revision,
        install_root=live_root,
    )
    receipt: dict[str, Any] = {
        "schema": "nexus.hybrid_replication.live_install_receipt.v1",
        "source_revision": args.source_revision,
        "bundle": bundle,
        "scheduler_loaded": False,
        "t_auto": args.t_auto,
    }

    if args.load:
        if not args.t_auto or not args.frozen_policy_sha256:
            raise SystemExit("--load requires --t-auto and --frozen-policy-sha256")
        if len(args.frozen_policy_sha256) != 64:
            raise SystemExit("invalid frozen policy sha256")
        repo_map = Path(args.repo_map)
        if not repo_map.is_file():
            raise SystemExit("repo map missing")
        log_root = live_root / "logs"
        log_root.mkdir(parents=True, exist_ok=True)
        plist_path = live_root / f"{LABEL}.plist"
        plist_bytes = render_launchd_plist(
            python=args.python,
            bundle_root=Path(bundle["bundle_root"]),
            experiment_root=experiment_root,
            d0_root=Path(args.d0_root),
            repo_map=repo_map,
            t_auto=args.t_auto,
            frozen_policy_sha256=args.frozen_policy_sha256,
        )
        plist_path.write_bytes(plist_bytes)
        _launch_agent(plist_path)
        receipt["scheduler_loaded"] = True
        receipt["plist_path"] = str(plist_path)
        receipt["plist_sha256"] = _sha256(plist_bytes)

    receipt_bytes = (
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    receipt_path = live_root / "LIVE_INSTALL_RECEIPT.json"
    receipt_path.write_bytes(receipt_bytes)
    print(json.dumps({**receipt, "receipt_sha256": _sha256(receipt_bytes)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
