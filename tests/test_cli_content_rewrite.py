from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod


def test_content_rewrite_writes_output_and_report(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
    inp = tmp_path / "in.md"
    out = tmp_path / "out.md"
    report = tmp_path / ".nexus/reports/content/rewrite-report.json"
    inp.write_text("line1  \n\n\nline2\n", encoding="utf-8")

    runner = CliRunner()
    res = runner.invoke(
        cli_mod.nexus,
        [
            "nexus",
            "content:rewrite",
            "--input-file",
            str(inp),
            "--output-file",
            str(out),
            "--report-file",
            str(report),
            "--no-llm-mode",
        ],
    )

    assert res.exit_code == 0, res.output
    assert out.exists()
    assert report.exists()
    assert "Output Written: True" in res.output
    assert out.read_text(encoding="utf-8") == "line1\n\nline2\n"


def test_content_rewrite_llm_mode_uses_unified_runtime(monkeypatch, tmp_path):
    class FakeGateway:
        oauth_provider = "gemini"

        def __init__(self, *, project_root):
            self.project_root = project_root

        def ask_unified(self, request, *, verifier, learning, receipt_path):
            assert request.task_id.startswith("content-rewrite-")
            assert request.route["provider"] == "gemini"
            assert request.online_output_schema["patch"] == "Full rewritten content"
            receipt = {
                "schema": "nexus.unified_runtime.receipt.v1",
                "task_id": request.task_id,
                "receipt_complete": True,
                "online": {
                    "status": "SUCCEEDED",
                    "response": {"patch": "rewritten\n"},
                },
            }
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text("{}", encoding="utf-8")
            return receipt

    monkeypatch.setattr("nexus.services.gateway.BattlesuitGateway", FakeGateway)
    monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
    inp = tmp_path / "in.md"
    out = tmp_path / "out.md"
    report = tmp_path / ".nexus/reports/content/rewrite-report.json"
    inp.write_text("source\n", encoding="utf-8")

    runner = CliRunner()
    res = runner.invoke(
        cli_mod.nexus,
        [
            "nexus",
            "content:rewrite",
            "--input-file",
            str(inp),
            "--output-file",
            str(out),
            "--report-file",
            str(report),
            "--llm-mode",
        ],
    )

    assert res.exit_code == 0, res.output
    payload = report.read_text(encoding="utf-8")
    assert '"method": "llm"' in payload
    assert '"unified_runtime_receipt"' in payload
    assert out.read_text(encoding="utf-8") == "rewritten\n"
