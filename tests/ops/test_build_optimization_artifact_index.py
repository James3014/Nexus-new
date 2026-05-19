from __future__ import annotations

from scripts.ops.build_optimization_artifact_index import build_optimization_artifact_index


def test_build_optimization_artifact_index_writes_claim_boundary(tmp_path):
    output = tmp_path / "index.md"

    summary = build_optimization_artifact_index(
        artifact_paths=("nexus/contracts/retrieval_receipt.py", "scripts/ops/check_optimization_artifact_hygiene.py"),
        output_path=output,
    )
    text = output.read_text(encoding="utf-8")

    assert summary["status"] == "PASS"
    assert summary["artifact_count"] == 2
    assert "`nexus/contracts/retrieval_receipt.py`" in text
    assert "Not a runtime apply approval." in text
    assert "Not a public benchmark claim." in text


def test_build_optimization_artifact_index_dry_run_does_not_write(tmp_path):
    output = tmp_path / "index.md"

    summary = build_optimization_artifact_index(
        artifact_paths=("nexus/contracts/retrieval_receipt.py",),
        output_path=output,
        dry_run=True,
    )

    assert summary["status"] == "PASS"
    assert summary["dry_run"] is True
    assert output.exists() is False


def test_build_optimization_artifact_index_returns_without_artifacts(tmp_path):
    output = tmp_path / "index.md"

    summary = build_optimization_artifact_index(artifact_paths=(), output_path=output)

    assert summary["status"] == "RETURN"
    assert summary["artifact_count"] == 0
