from __future__ import annotations

import json
import re
from pathlib import Path

from nexus.delivery.models import CompletionResult


def render_markdown_report(result: CompletionResult) -> str:
    lines = [
        "# Delivery Report",
        "",
        f"- Task: `{result.task_name}`",
        f"- Level: `{result.task_level.value}`",
        f"- Status: `{result.status.value}`",
        f"- Gate Passed: `{str(result.gate_passed).lower()}`",
        f"- Summary: {result.summary}",
        "",
        "## Verification Commands",
        "",
    ]
    for record in result.verification_records:
        lines.append(
            f"- `{'PASS' if record.passed else 'FAIL'}` `{record.command}` "
            f"(exit={record.exit_code})"
        )
    lines.extend(["", "## Artifacts", ""])
    if result.existing_artifacts:
        for artifact in result.existing_artifacts:
            lines.append(f"- present: `{artifact}`")
    if result.missing_artifacts:
        for artifact in result.missing_artifacts:
            lines.append(f"- missing: `{artifact}`")
    if not result.existing_artifacts and not result.missing_artifacts:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return slug or "delivery-report"


def write_report_bundle(result: CompletionResult, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{result.generated_at.strftime('%Y%m%d-%H%M%S')}-{_slugify(result.task_name)}"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown_report(result), encoding="utf-8")
    return json_path, md_path
