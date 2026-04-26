#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LABEL = "com.nexus.learn-refresh"
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"


def _build_program_args(
    *,
    uv_bin: str,
    topic: str,
    benchmark_manifest: str,
    due_within_days: int,
    pass_threshold: float,
    question_count: int,
) -> list[str]:
    args = [
        uv_bin,
        "run",
        "python",
        "scripts/ops/learn_refresh_daemon.py",
        "--once",
        "--due-within-days",
        str(due_within_days),
        "--pass-threshold",
        str(pass_threshold),
        "--question-count",
        str(question_count),
    ]
    if topic:
        args.extend(["--topic", topic])
    if benchmark_manifest:
        args.extend(["--benchmark-manifest", benchmark_manifest])
    return args


def build_plist_payload(
    *,
    label: str,
    interval_sec: int,
    uv_bin: str,
    topic: str,
    benchmark_manifest: str,
    due_within_days: int,
    pass_threshold: float,
    question_count: int,
) -> dict[str, Any]:
    return {
        "Label": label,
        "WorkingDirectory": str(REPO_ROOT),
        "ProgramArguments": _build_program_args(
            uv_bin=uv_bin,
            topic=topic,
            benchmark_manifest=benchmark_manifest,
            due_within_days=due_within_days,
            pass_threshold=pass_threshold,
            question_count=question_count,
        ),
        "StartInterval": max(300, int(interval_sec)),
        "StandardOutPath": str(REPO_ROOT / ".nexus" / "learn_refresh_launchd.out.log"),
        "StandardErrorPath": str(REPO_ROOT / ".nexus" / "learn_refresh_launchd.err.log"),
        "RunAtLoad": True,
    }


def _to_plist_xml(payload: dict[str, Any]) -> str:
    def esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
        '<plist version="1.0">',
        "<dict>",
    ]
    for key, value in payload.items():
        lines.append(f"  <key>{esc(str(key))}</key>")
        if isinstance(value, bool):
            lines.append("  <true/>" if value else "  <false/>")
        elif isinstance(value, int):
            lines.append(f"  <integer>{value}</integer>")
        elif isinstance(value, list):
            lines.append("  <array>")
            for item in value:
                lines.append(f"    <string>{esc(str(item))}</string>")
            lines.append("  </array>")
        else:
            lines.append(f"  <string>{esc(str(value))}</string>")
    lines.extend(["</dict>", "</plist>"])
    return "\n".join(lines) + "\n"


def install(args: argparse.Namespace) -> int:
    uv_bin = shutil.which("uv") or str(REPO_ROOT / ".venv" / "bin" / "uv")
    if not Path(uv_bin).exists():
        print(json.dumps({"status": "FAIL", "reason": "uv_not_found"}, ensure_ascii=False))
        return 1

    payload = build_plist_payload(
        label=args.label,
        interval_sec=args.interval_sec,
        uv_bin=uv_bin,
        topic=args.topic,
        benchmark_manifest=args.benchmark_manifest,
        due_within_days=args.due_within_days,
        pass_threshold=args.pass_threshold,
        question_count=args.question_count,
    )
    plist_path = (LAUNCH_AGENTS / f"{args.label}.plist").resolve()

    if args.dry_run:
        print(
            json.dumps(
                {"status": "DRY_RUN", "plist_path": str(plist_path), "payload": payload},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / ".nexus").mkdir(parents=True, exist_ok=True)
    plist_path.write_text(_to_plist_xml(payload), encoding="utf-8")

    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    res = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, text=True)
    if res.returncode != 0:
        print(json.dumps({"status": "FAIL", "plist_path": str(plist_path), "stderr": res.stderr.strip()}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "SUCCESS", "plist_path": str(plist_path), "label": args.label}, ensure_ascii=False))
    return 0


def uninstall(args: argparse.Namespace) -> int:
    plist_path = (LAUNCH_AGENTS / f"{args.label}.plist").resolve()
    if args.dry_run:
        print(json.dumps({"status": "DRY_RUN", "action": "uninstall", "plist_path": str(plist_path)}, ensure_ascii=False))
        return 0
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    if plist_path.exists():
        plist_path.unlink()
    print(json.dumps({"status": "SUCCESS", "action": "uninstall", "plist_path": str(plist_path)}, ensure_ascii=False))
    return 0


def status(args: argparse.Namespace) -> int:
    plist_path = (LAUNCH_AGENTS / f"{args.label}.plist").resolve()
    loaded = False
    proc = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    if proc.returncode == 0 and args.label in proc.stdout:
        loaded = True
    print(
        json.dumps(
            {
                "status": "SUCCESS",
                "label": args.label,
                "plist_path": str(plist_path),
                "plist_exists": plist_path.exists(),
                "launchd_loaded": loaded,
            },
            ensure_ascii=False,
        )
    )
    return 0


def print_plist(args: argparse.Namespace) -> int:
    uv_bin = shutil.which("uv") or "uv"
    payload = build_plist_payload(
        label=args.label,
        interval_sec=args.interval_sec,
        uv_bin=uv_bin,
        topic=args.topic,
        benchmark_manifest=args.benchmark_manifest,
        due_within_days=args.due_within_days,
        pass_threshold=args.pass_threshold,
        question_count=args.question_count,
    )
    print(_to_plist_xml(payload))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Install/uninstall launchd schedule for Learn refresh daemon")
    parser.add_argument("action", choices=["install", "uninstall", "status", "print-plist"])
    parser.add_argument("--label", default=DEFAULT_LABEL)
    parser.add_argument("--interval-sec", type=int, default=3600)
    parser.add_argument("--topic", default="")
    parser.add_argument("--benchmark-manifest", default="")
    parser.add_argument("--due-within-days", type=int, default=0)
    parser.add_argument("--pass-threshold", type=float, default=0.6)
    parser.add_argument("--question-count", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.action == "install":
        return install(args)
    if args.action == "uninstall":
        return uninstall(args)
    if args.action == "status":
        return status(args)
    return print_plist(args)


if __name__ == "__main__":
    raise SystemExit(main())
