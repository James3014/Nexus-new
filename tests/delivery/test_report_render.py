from pathlib import Path
import sys

from nexus.delivery.gate import evaluate_completion
from nexus.delivery.models import CompletionRequest
from nexus.delivery.models import TaskLevel
from nexus.delivery.report import render_markdown_report


def test_render_markdown_report_includes_status_and_commands(tmp_path: Path) -> None:
    request = CompletionRequest(
        task_name="report-case",
        task_level=TaskLevel.SMALL_FIX,
        verification_commands=[f"{sys.executable} -c \"print('ok')\""],
        cwd=tmp_path,
    )

    result = evaluate_completion(request)
    report = render_markdown_report(result)

    assert "# Delivery Report" in report
    assert "report-case" in report
    assert "verified" in report.lower()
    assert sys.executable in report
