from __future__ import annotations
from pathlib import Path

import io
import runpy
from contextlib import redirect_stdout


def _write_csv(tmp_path: Path, content: str) -> Path:
    csv_path = tmp_path / "ci_benchmark.csv"
    csv_path.write_text(content, encoding="utf-8")
    return csv_path


def test_final_verify_accepts_health_column(tmp_path, monkeypatch):
    _write_csv(
        tmp_path,
        "task_id,status,health,token_raw_model,token_capture_status\n"
        "OFF-001,PASS,95,123,ok\n",
    )
    monkeypatch.chdir(tmp_path)

    stdout = io.StringIO()
    try:
        with redirect_stdout(stdout):
            runpy.run_path(
                str(__import__("pathlib").Path(__file__).resolve().parents[2] / "final_verify.py"),
                run_name="__main__",
            )
    except SystemExit as exc:
        assert exc.code == 0

    assert "VERIFICATION PASSED" in stdout.getvalue()


def test_export_eval_report_accepts_tokens_and_health_columns(tmp_path, monkeypatch):
    _write_csv(
        tmp_path,
        "task_id,status,tokens,health\n"
        "OFF-001,PASS,111,91\n"
        "OFF-002,FAIL,222,49\n",
    )
    monkeypatch.chdir(tmp_path)

    runpy.run_path(
        str(__import__("pathlib").Path(__file__).resolve().parents[2] / "scripts/ops/export_eval_report.py"),
        run_name="__main__",
    )

    report = (tmp_path / "evaluation_report.md").read_text(encoding="utf-8")
    assert "Avg Tokens" in report
    assert "Avg Health" in report
