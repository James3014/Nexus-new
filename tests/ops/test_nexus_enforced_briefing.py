import os
import subprocess
from pathlib import Path


def _render_briefing(tmp_path: Path) -> str:
    out_file = tmp_path / "enforced_agent_briefing.md"
    result = subprocess.run(
        ["bash", "scripts/ops/_nexus_enforced_briefing.sh", str(out_file)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert str(out_file) in result.stdout
    return out_file.read_text(encoding="utf-8")


def test_enforced_briefing_requires_bootstrap_before_active(tmp_path):
    briefing = _render_briefing(tmp_path)

    assert briefing.splitlines()[0] == "[NEXUS BOOTSTRAP-CANDIDATE]"
    assert "[NEXUS ACTIVE]" in briefing
    assert "NEXUS v26" not in briefing
    assert "NEXUS v24" not in briefing
    assert "NEXUS v22" not in briefing


def test_compact_briefing_is_task_aware_and_smaller_than_legacy(tmp_path):
    compact_path = tmp_path / "compact.md"
    legacy_path = tmp_path / "legacy.md"
    compact = subprocess.run(
        ["bash", "scripts/ops/_nexus_enforced_briefing.sh", str(compact_path)],
        capture_output=True,
        text=True,
        check=True,
        env=os.environ.copy(),
    )
    legacy = subprocess.run(
        ["bash", "scripts/ops/_nexus_enforced_briefing.sh", str(legacy_path)],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "NEXUS_BRIEFING_MODE": "legacy"},
    )

    assert compact.stdout.strip().endswith("compact.md")
    assert legacy.stdout.strip().endswith("legacy.md")
    compact_text = compact_path.read_text(encoding="utf-8")
    legacy_text = legacy_path.read_text(encoding="utf-8")
    assert len(compact_text) < len(legacy_text)
    assert "task_id: orphan-workspace-reconciliation" in compact_text
    assert "workforce_query: python3 scripts/engine/nexus_cli.py workforce status" in compact_text
    assert "authority: non_normative" in legacy_text


def test_enforced_briefing_blocks_report_trust_overclaims(tmp_path):
    briefing = _render_briefing(tmp_path)

    assert "FAIL_CLOSED != SUCCESS" in briefing
    assert "INFRA_INVALID" in briefing
    assert "ROOT_ARTIFACT_LEAK" in briefing
    assert "Do not kill/stash/restore/clean ambiguous targets" in briefing
    assert "deterministic local rescue profile" in briefing
    assert "selected-only" in briefing


def test_committed_protocol_matches_runtime_briefing_guardrails():
    protocol = Path("docs/AGENT_MANDATORY_PROTOCOL.md").read_text(encoding="utf-8")

    assert "v2.9" in protocol
    assert "[NEXUS v26 BOOTSTRAP-CANDIDATE]" in protocol
    assert "FAIL_CLOSED != SUCCESS" in protocol
    assert "INFRA_INVALID" in protocol
    assert "ROOT_ARTIFACT_LEAK" in protocol


def test_gemini_round_runner_uses_enforced_briefing_not_legacy_active_preamble():
    runner = Path("scripts/ops/run_gemini_nexus_round.sh").read_text(encoding="utf-8")

    assert "[NEXUS v22 ACTIVE]" not in runner
    assert "_nexus_enforced_briefing.sh" in runner
    assert 'cat "$BRIEFING_PATH"' in runner
    assert "NEXUS_BOOTSTRAP_INCOMPLETE" in runner


def test_gemini_enforced_launcher_does_not_leak_runner_env_to_gemini_cli():
    launcher = Path("scripts/ops/start_gemini_nexus_enforced.sh").read_text(encoding="utf-8")

    assert 'export NEXUS_RUNNER="Gemini"' in launcher
    assert "nexus_startup_contract_check.py" in launcher
    assert "unset NEXUS_RUNNER" in launcher
    assert launcher.index("unset NEXUS_RUNNER") > launcher.index("nexus_startup_contract_check.py")
    assert launcher.index("unset NEXUS_RUNNER") < launcher.index("run_gemini_nexus_round.sh")


def test_gemini_round_runner_uses_shared_invoker_for_preflight():
    runner = Path("scripts/ops/run_gemini_nexus_round.sh").read_text(encoding="utf-8")

    assert "gemini_nexus_invoke.py" in runner
    assert "--preflight-only" in runner
    assert 'UV_BIN="${NEXUS_UV_BIN:-/Users/jameschen/.local/bin/uv}"' in runner
    assert '"$UV_BIN" run scripts/ops/gemini_nexus_invoke.py' in runner
    assert "capture_output=True" not in runner


def test_nexus_preflight_prefers_local_venv_python_for_cli_smoke():
    preflight = Path("scripts/ops/_nexus_preflight.sh").read_text(encoding="utf-8")

    assert 'export PATH="$PATH:/opt/homebrew/bin' in preflight
    assert 'export PATH="/opt/homebrew/bin' not in preflight
    assert '[[ -x ".venv/bin/python" ]]' in preflight
    assert 'NEXUS_CLI_SMOKE=(".venv/bin/python" "scripts/engine/nexus_cli.py" "--help")' in preflight
    assert 'NEXUS_CLI_SMOKE=("uv" "run" "scripts/engine/nexus_cli.py" "--help")' in preflight
