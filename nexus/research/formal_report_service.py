from __future__ import annotations

from typing import Any


class FormalReportService:
    """Build an auditable Markdown report from runtime evidence receipts."""

    def build(
        self,
        *,
        title: str,
        hypothesis: str,
        asi_constraints: list[dict[str, Any]],
        judge_votes: list[dict[str, Any]],
        verification: list[dict[str, Any]],
        route_receipts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        evidence_ready = self._evidence_ready(
            judge_votes=judge_votes,
            verification=verification,
            route_receipts=route_receipts,
        )
        claim_status = "PASS" if evidence_ready else "BLOCKED"
        status = "READY" if evidence_ready else "CLAIM_BLOCKED"
        markdown = "\n".join(
            [
                f"# {title}",
                "",
                "## Hypothesis",
                hypothesis,
                "",
                "## Evidence Gate",
                f"Claim Status: {claim_status}",
                "",
                "## Judge Panel",
                self._bullet_json(judge_votes),
                "",
                "## ASI Constraints",
                self._bullet_json(asi_constraints),
                "",
                "## Verification Matrix",
                self._bullet_json(verification),
                "",
                "## Route Receipts",
                self._bullet_json(route_receipts),
            ]
        )
        return {
            "schema": "nexus_formal_report_v1",
            "status": status,
            "claim_status": claim_status,
            "markdown": markdown,
        }

    def _evidence_ready(
        self,
        *,
        judge_votes: list[dict[str, Any]],
        verification: list[dict[str, Any]],
        route_receipts: list[dict[str, Any]],
    ) -> bool:
        has_judge = bool(judge_votes)
        has_pass = any(str(item.get("status") or "").upper() == "PASS" for item in verification if isinstance(item, dict))
        has_route = any(
            bool(item.get("evidence_present") and item.get("gate_passed"))
            for item in route_receipts
            if isinstance(item, dict)
        )
        return bool(has_judge and has_pass and has_route)

    def _bullet_json(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "- none"
        out: list[str] = []
        for row in rows:
            parts = [f"{key}={value}" for key, value in sorted(row.items())]
            out.append(f"- {'; '.join(parts)}")
        return "\n".join(out)
