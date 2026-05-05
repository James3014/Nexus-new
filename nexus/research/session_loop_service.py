from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_session_id(value: str) -> str:
    slug = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in (value or "").strip())
    return slug[:80] or f"research-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


@dataclass(frozen=True)
class ResearchSessionLoopService:
    repo_root: Path

    @property
    def sessions_dir(self) -> Path:
        return Path(self.repo_root) / ".nexus" / "research_sessions"

    def _manifest_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{_safe_session_id(session_id)}.json"

    def _ledger_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{_safe_session_id(session_id)}.jsonl"

    def _last_packet_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{_safe_session_id(session_id)}.last-packet.json"

    def onboarding(
        self,
        *,
        session_id: str,
        goal: str,
        benchmark: str = "",
        metric: str = "",
        scope: list[str] | None = None,
    ) -> dict[str, Any]:
        sid = _safe_session_id(session_id)
        manifest = {
            "schema": "nexus_research_session_v1",
            "session_id": sid,
            "goal": goal,
            "benchmark": benchmark,
            "metric": metric,
            "scope": list(scope or []),
            "stage": "onboarded",
            "created_at": _now(),
            "updated_at": _now(),
            "ledger_path": str(self._ledger_path(sid)),
            "last_packet_path": str(self._last_packet_path(sid)),
        }
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._manifest_path(sid).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        if not self._ledger_path(sid).exists():
            self._ledger_path(sid).write_text("", encoding="utf-8")
        return manifest

    def load_manifest(self, session_id: str) -> dict[str, Any]:
        path = self._manifest_path(session_id)
        if not path.exists():
            return self.onboarding(session_id=session_id, goal="", scope=[])
        return json.loads(path.read_text(encoding="utf-8"))

    def recommend_next(self, *, session_id: str, route: dict[str, Any] | None = None) -> dict[str, Any]:
        manifest = self.load_manifest(session_id)
        route = route if isinstance(route, dict) else {}
        research_context = route.get("research_context", {}) if isinstance(route.get("research_context"), dict) else {}
        next_action = {
            "stage": "packet",
            "reason": str(route.get("recommended_reason") or research_context.get("next_action_hint") or "ready_for_packet"),
            "safety": "scope_bound_and_log_required",
            "recommended_flow": str(route.get("recommended_flow") or "baseline"),
            "recommended_capabilities": list(research_context.get("recommended_capabilities", []) or []),
            "missing_essentials": [
                name
                for name, value in {
                    "goal": manifest.get("goal"),
                    "scope": manifest.get("scope"),
                }.items()
                if not value
            ],
        }
        return {
            "schema": "nexus_research_recommendation_v1",
            "session_id": manifest["session_id"],
            "nextStep": {"stage": next_action["stage"], "nextAction": next_action},
            "route": route,
        }

    def packet(
        self,
        *,
        session_id: str,
        report: dict[str, Any] | None = None,
        route: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        manifest = self.load_manifest(session_id)
        report = report if isinstance(report, dict) else {}
        route = route if isinstance(route, dict) else {}
        packet = {
            "schema": "nexus_research_packet_v1",
            "session_id": manifest["session_id"],
            "created_at": _now(),
            "packet_id": f"{manifest['session_id']}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "command_identity": report.get("command_name", "research:run"),
            "status": report.get("status", "unknown"),
            "semantic_status": report.get("semantic_status", "UNKNOWN"),
            "metrics": {
                "winner": report.get("winner"),
                "total_cost": ((report.get("cost_curve") or {}).get("total_cost") if isinstance(report.get("cost_curve"), dict) else None),
            },
            "artifacts": {
                "report_file": report.get("report_file", ""),
                "route_decision_report": route.get("route_decision_report", ""),
            },
            "research_context": route.get("research_context", {}),
            "freshness": {
                "manifest_updated_at": manifest.get("updated_at", ""),
                "route_schema": ((route.get("route_decision") or {}).get("schema_version") if isinstance(route.get("route_decision"), dict) else ""),
            },
        }
        self._last_packet_path(manifest["session_id"]).write_text(json.dumps(packet, indent=2), encoding="utf-8")
        return packet

    def log_from_last(
        self,
        *,
        session_id: str,
        status: str,
        description: str,
        asi: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        manifest = self.load_manifest(session_id)
        packet_path = self._last_packet_path(manifest["session_id"])
        if not packet_path.exists():
            return {
                "schema": "nexus_research_log_result_v1",
                "session_id": manifest["session_id"],
                "logged": False,
                "reason": "last_packet_missing",
            }
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        entry = {
            "schema": "nexus_research_ledger_entry_v1",
            "logged_at": _now(),
            "session_id": manifest["session_id"],
            "packet_id": packet.get("packet_id", ""),
            "status": status,
            "description": description,
            "asi": asi or {
                "hypothesis": description,
                "evidence": str(packet.get("semantic_status", "")),
                "rollback_reason": "" if status == "keep" else "not_kept",
                "next_action_hint": "recommend-next",
            },
            "packet": packet,
        }
        with self._ledger_path(manifest["session_id"]).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        manifest["stage"] = "logged"
        manifest["updated_at"] = _now()
        self._manifest_path(manifest["session_id"]).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return {"schema": "nexus_research_log_result_v1", "session_id": manifest["session_id"], "logged": True, "entry": entry}

    def finalize_preview(self, *, session_id: str) -> dict[str, Any]:
        manifest = self.load_manifest(session_id)
        ledger_path = self._ledger_path(manifest["session_id"])
        entries = [
            json.loads(line)
            for line in ledger_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ] if ledger_path.exists() else []
        keeps = [entry for entry in entries if entry.get("status") == "keep"]
        last_packet_exists = self._last_packet_path(manifest["session_id"]).exists()
        last_packet_logged = bool(entries and entries[-1].get("packet_id"))
        return {
            "schema": "nexus_research_finalize_preview_v1",
            "session_id": manifest["session_id"],
            "ready": bool(keeps and (not last_packet_exists or last_packet_logged)),
            "keep_count": len(keeps),
            "entry_count": len(entries),
            "warnings": [] if keeps else ["no_kept_packets"],
            "manifest": manifest,
        }

    def human_report(self, *, session_id: str) -> str:
        preview = self.finalize_preview(session_id=session_id)
        manifest = preview["manifest"]
        return "\n".join(
            [
                f"# Research Session {manifest['session_id']}",
                "",
                f"- Goal: {manifest.get('goal', '')}",
                f"- Stage: {manifest.get('stage', '')}",
                f"- Entries: {preview['entry_count']}",
                f"- Keeps: {preview['keep_count']}",
                f"- Ready: {preview['ready']}",
                f"- Warnings: {', '.join(preview['warnings']) if preview['warnings'] else 'none'}",
            ]
        )
