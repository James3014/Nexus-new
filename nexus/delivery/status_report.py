"""Honest `nexus nexus status` report: only real, observable facts; no fabricated metrics."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nexus.delivery.receipt import load_delivery_receipt

SCHEMA = "nexus.status_report.v1"
NOT_MEASURED = "NOT_MEASURED"
UNVERIFIED = "UNVERIFIED"

# Things the old status command printed as PASS that nothing in the repo measures at status time.
UNMEASURED_DIMENSIONS = (
    "tenant_isolation",
    "hallucination_rate",
    "concurrency_p95",
    "rbac_security",
    "crm_integration",
    "fleet_size",
    "mcp_readiness",
)


def _git_head(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    head = out.stdout.strip()
    return head if out.returncode == 0 and head else None


def _mtime_utc(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _head_match(recorded: str | None, head: str | None) -> str:
    if not recorded or not head:
        return UNVERIFIED
    return "MATCHES_HEAD" if recorded == head or head.startswith(recorded) else "STALE"


def _governance_seal(root: Path) -> dict[str, Any]:
    seal_path = root / ".nexus" / "config" / "governance_seal.json"
    if not seal_path.is_file():
        return {"state": NOT_MEASURED, "reason": "no governance seal file"}
    try:
        files = json.loads(seal_path.read_text(encoding="utf-8")).get("files", {})
    except (OSError, ValueError, AttributeError):
        return {"state": UNVERIFIED, "reason": "governance seal unreadable"}
    drift: list[str] = []
    for rel, expected in sorted(files.items()):
        target = root / rel
        actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else "MISSING"
        if actual != expected:
            drift.append(rel)
    return {"state": "DRIFT" if drift else "MATCH", "checked_files": len(files), "drifted": drift}


def _delivery_receipt(root: Path, head: str | None) -> dict[str, Any]:
    path = root / ".nexus" / "reports" / "delivery_gate.json"
    payload = load_delivery_receipt(path)
    if not payload:
        return {"state": NOT_MEASURED, "reason": "no delivery receipt on disk"}
    recorded = payload.get("head_sha") or payload.get("head")
    return {
        "state": _head_match(recorded, head),
        "head_sha": payload.get("head_sha"),
        "generated_at_utc": payload.get("generated_at_utc"),
        "receipt_reports_gate_passed": bool(payload.get("delivery_gate_passed")),
        "path": ".nexus/reports/delivery_gate.json",
    }


def _acceptance_report(root: Path, head: str | None) -> dict[str, Any]:
    path = root / ".nexus" / "reports" / "acceptance_check.json"
    if not path.is_file():
        return {"state": NOT_MEASURED, "reason": "no acceptance-check report on disk"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": UNVERIFIED, "reason": "acceptance report unreadable"}
    if not isinstance(data, dict):
        data = {}
    recorded = data.get("head_sha") or data.get("commit_sha") or data.get("head")
    return {
        "state": _head_match(recorded, head),
        "recorded_status": data.get("status"),
        "file_mtime_utc": _mtime_utc(path),
        "path": ".nexus/reports/acceptance_check.json",
    }


def _drone_crystals(root: Path) -> dict[str, Any]:
    directory = root / ".nexus" / "reports" / "drones"
    crystals = sorted(directory.glob("*_crystal.json")) if directory.is_dir() else []
    return {"count": len(crystals), "state": "OBSERVED" if crystals else NOT_MEASURED}


def build_status_report(root: Path) -> dict[str, Any]:
    root = Path(root)
    head = _git_head(root)
    seal = _governance_seal(root)
    receipt = _delivery_receipt(root, head)
    if receipt["state"] == "MATCHES_HEAD" and seal["state"] != "DRIFT":
        overall = (
            "EVIDENCE_PRESENT" if receipt["receipt_reports_gate_passed"] else "EVIDENCE_FAILING"
        )
    else:
        overall = UNVERIFIED
    return {
        "schema": SCHEMA,
        "overall": overall,
        "health_claimed": False,
        "head_sha": head,
        "governance_seal": seal,
        "delivery_receipt": receipt,
        "acceptance_check": _acceptance_report(root, head),
        "drone_crystals": _drone_crystals(root),
        "not_measured": {name: NOT_MEASURED for name in UNMEASURED_DIMENSIONS},
    }


def render_status_report(report: dict[str, Any]) -> str:
    seal = report["governance_seal"]
    receipt = report["delivery_receipt"]
    acceptance = report["acceptance_check"]
    crystals = report["drone_crystals"]
    receipt_detail = (
        f" (generated {receipt['generated_at_utc']}, head {receipt['head_sha']})"
        if "head_sha" in receipt
        else ""
    )
    acceptance_detail = (
        f" (recorded status {acceptance['recorded_status']}, {acceptance['file_mtime_utc']})"
        if "file_mtime_utc" in acceptance
        else ""
    )
    lines = [
        f"Nexus status (observed facts only; health is not claimed): {report['overall']}",
        f"  repo HEAD:           {report['head_sha'] or NOT_MEASURED}",
        f"  governance seal:     {seal['state']}",
        f"  delivery receipt:    {receipt['state']}{receipt_detail}",
        f"  acceptance report:   {acceptance['state']}{acceptance_detail}",
        f"  drone crystals:      {crystals['count']} ({crystals['state']})",
        "  not measured: " + ", ".join(report["not_measured"]),
    ]
    return "\n".join(lines)
