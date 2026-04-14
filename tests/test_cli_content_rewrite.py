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

