from pathlib import Path

from scripts.ops import nexus_completion_gate


def test_completion_gate_cli_writes_verified_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    verify_file = tmp_path / "verify.txt"
    verify_file.write_text("/bin/echo ok-1\n/bin/echo ok-2\n", encoding="utf-8")
    monkeypatch.chdir("/Users/jameschen/Workspace/nexus")
    monkeypatch.setattr(
        "sys.argv",
        [
            "nexus_completion_gate.py",
            "--task-name",
            "cli-verified",
            "--task-level",
            "feature",
            "--verify-file",
            str(verify_file),
            "--cwd",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    exit_code = nexus_completion_gate.main()

    assert exit_code == 0
    assert list((tmp_path / "out").glob("*.json"))
    assert list((tmp_path / "out").glob("*.md"))


def test_completion_gate_cli_requires_artifact_for_delivery_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    verify_file = tmp_path / "verify.txt"
    verify_file.write_text("/bin/echo ok-1\n/bin/echo ok-2\n", encoding="utf-8")
    artifact = tmp_path / "proof.txt"
    artifact.write_text("proof", encoding="utf-8")
    artifact_file = tmp_path / "artifacts.txt"
    artifact_file.write_text(f"{artifact}\n", encoding="utf-8")
    monkeypatch.chdir("/Users/jameschen/Workspace/nexus")
    monkeypatch.setattr(
        "sys.argv",
        [
            "nexus_completion_gate.py",
            "--task-name",
            "cli-delivery",
            "--task-level",
            "delivery",
            "--verify-file",
            str(verify_file),
            "--artifact-file",
            str(artifact_file),
            "--cwd",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    exit_code = nexus_completion_gate.main()

    assert exit_code == 0
