import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional


class Reporter:
    """負責結果的呈現、持久化報告、語音通知與 Tracing。"""

    def __init__(self, project_root: str, tracelog_path: Optional[Path] = None, silent: bool = False, run_dir: Optional[str] = None):
        self.project_root = Path(project_root)
        self.run_dir = Path(run_dir) if run_dir else None
        # Phase C: Default tracelog to run_dir if available
        if self.run_dir and tracelog_path is None:
            self.tracelog_path = self.run_dir / "tracelog.jsonl"
        else:
            self.tracelog_path = tracelog_path or self.project_root / "tracelog.jsonl"
        self.silent = silent

    def voice_notify(self, message: str, urgency: str = "normal"):
        """🔊 v7 Spec: 關鍵點語音通知 (支持優先級)"""
        if self.silent and urgency != "critical":
            return
        try:
            subprocess.run(
                [
                    sys.executable,
                    "/Users/jameschen/.openclaw/skills/audio-notify/scripts/notify.py",
                    message,
                ],
                check=False,
            )
        except Exception:
            pass

    def write_metrics(self, metrics: dict):
        """💾 Phase C: 寫入運行時指標至 run_dir。"""
        if self.run_dir:
            metrics_file = self.run_dir / ".nexus_metrics"
            with open(metrics_file, "w", encoding="utf-8") as f:
                json.dump(metrics, f, ensure_ascii=False, indent=2)

    def log_trace(self, command: str, task: str, status: str, tokens: int = 0, score: float = 0.0):
        """📊 v7 Spec: 自動寫入 tracelog.jsonl"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "command": command,
            "task": task,
            "status": status,
            "tokens_used": tokens,
            "flashjudge_score": score,
        }
        with open(self.tracelog_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    @staticmethod
    def _build_next_step_lines(data):
        next_action = data.get("next_action")
        next_actor = data.get("next_actor")
        reason_codes = data.get("escalation_reasons", [])
        action_brief = data.get("action_brief") or {}
        brief_context = action_brief.get("context") or {}

        if not any([next_action, next_actor, reason_codes, action_brief]):
            return []

        lines = ["## Next Step\n"]

        if next_action:
            lines.append(f"- **Action**: `{next_action}`")
        if next_actor:
            lines.append(f"- **Actor**: `{next_actor}`")
        if reason_codes:
            formatted_reasons = ", ".join(f"`{reason}`" for reason in reason_codes)
            lines.append(f"- **Reasons**: {formatted_reasons}")

        brief_title = action_brief.get("title")
        brief_instructions = action_brief.get("instructions")
        if brief_title:
            lines.append("")
            lines.append(f"### {brief_title}")
        if brief_instructions:
            lines.append(f"- **Instructions**: {brief_instructions}")

        for key, value in brief_context.items():
            if value:
                lines.append(f"- **{key}**: {value}")

        lines.append("")
        return lines

    @staticmethod
    def render_ansi_table(violations):
        """繪製終端視覺表格 (含嚴重等級)。"""
        if not violations:
            return ""

        header = f"\n{'-' * 110}\n| {'SEVERITY':<10} | {'TYPE':<12} | {'FILE:LINE':<25} | {'REASON & SUGGESTION':<55} |\n{'-' * 110}"
        rows = []
        for v in violations:
            severity = v.get("severity", "MAJOR")
            loc = f"{v.get('file')}:{v.get('line', 1)}"
            # 簡單的自動換行處理
            rows.append(
                f"| {severity:<10} | {v.get('type', 'INFO'):<12} | {loc:<25} | {v.get('reason')[:53]:<55} |"
            )
            rows.append(
                f"| {'':<10} | {'':<12} | {'':<25} | Suggestion: {v.get('suggestion')[:41]:<55} |"
            )
            rows.append("-" * 110)

        return header + "\n" + "\n".join(rows)

    @staticmethod
    def write_markdown_report(report_path, data, total_tokens=0):
        """寫入精準的 Markdown 結晶報告 (含嚴重等級)。"""
        violations = data.get("violations", [])
        lines = [
            "# Codex-Loop Audit Report\n",
            f"**Status**: {data.get('status', 'N/A')}",
            f"**Total Tokens**: {total_tokens:,}" if total_tokens else "",
            f"**Summary**: {data.get('summary', 'No summary provided.')}\n",
            *Reporter._build_next_step_lines(data),
            "## Violations\n",
        ]

        for v in violations:
            severity = v.get("severity", "MAJOR")
            lines.append(
                f"### [{severity}][{v.get('type', 'INFO')}] {v.get('file')}:{v.get('line', 1)}"
            )
            lines.append(f"- **Reason**: {v.get('reason')}")
            lines.append(f"- **Suggestion**: {v.get('suggestion')}\n")
            if v.get("patch"):
                lines.append("```diff\n" + v.get("patch") + "\n```\n")

        Path(report_path).write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def write_action_sidecar(action_path, data):
        payload = {
            "status": data.get("status", "N/A"),
            "summary": data.get("summary", ""),
            "next_action": data.get("next_action"),
            "next_actor": data.get("next_actor"),
            "escalation_reasons": data.get("escalation_reasons", []),
            "action_brief": data.get("action_brief") or {},
        }
        Path(action_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
