from __future__ import annotations

from click.testing import CliRunner


def test_acceptance_check_runs_claim_verifier(monkeypatch):
    from scripts.engine.nexus_cli import nexus

    calls = []

    class _Res:
        def __init__(self, returncode=0):
            self.returncode = returncode
            self.stdout = b"ok"
            self.stderr = b""

    def _fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return _Res(0)

    # Skip hallucination dependency in this focused unit test.
    monkeypatch.setattr("scripts.engine.nexus_cli.check_hallucination", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("scripts.engine.nexus_cli.subprocess.run", _fake_run)

    result = CliRunner().invoke(nexus, ["nexus", "acceptance-check"])
    assert result.exit_code == 0
    joined = [" ".join(map(str, c)) for c in calls]
    assert any("scripts/ops/nexus_acceptance_check.py" in c for c in joined)
    assert any("scripts/ops/verify_report_claims.py" in c for c in joined)
