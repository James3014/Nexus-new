from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_enforced_briefing_exposes_local_assist_and_closeout_contract(tmp_path: Path) -> None:
    output = tmp_path / "briefing.md"
    result = subprocess.run(
        ["bash", "scripts/ops/_nexus_enforced_briefing.sh", str(output)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    content = output.read_text(encoding="utf-8")
    for term in (
        "nexus local-assist advisor",
        "nexus local-assist candidate",
        "nexus local-assist verified-subtask",
        "nexus local-assist closeout",
        "local_assist_output_consumed",
        "receipt path or task identity",
    ):
        assert term in content


def test_gemini_enforced_round_script_is_shell_valid() -> None:
    result = subprocess.run(
        ["bash", "-n", "scripts/ops/run_gemini_nexus_round.sh"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
