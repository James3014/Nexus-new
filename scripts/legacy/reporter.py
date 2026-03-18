"""
⚠️ LEGACY / ARCHIVED SCRIPT
This script is part of the legacy Muse-Nexus implementation and is no longer actively maintained.
Please use the corresponding module in `scripts/core/` or `nexus/` instead.
---
⚠️ 舊版 / 封存腳本
此腳本為舊版 Muse-Nexus 實作，已不再主動維護。
請改用 `scripts/core/` 或 `nexus/` 中的對應模組。
"""
from pathlib import Path


class Reporter:
    """負責結果的呈現與持久化報告。"""

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
