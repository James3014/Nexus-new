import json
from pathlib import Path

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod


def test_code_impact_cli_outputs_json_and_report(monkeypatch, tmp_path: Path):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("import pkg.core\n", encoding="utf-8")
    report = tmp_path / "impact.json"

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    runner = CliRunner()
    res = runner.invoke(
        cli_mod.nexus,
        [
            "nexus",
            "code",
            "impact",
            "--files",
            "pkg/core.py",
            "--report-file",
            str(report),
            "--output-json",
        ],
    )

    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["schema_version"] == "codeintel-v1"
    assert payload["impacted_files"] == ["pkg/consumer.py", "pkg/core.py"]
    assert json.loads(report.read_text(encoding="utf-8")) == payload
