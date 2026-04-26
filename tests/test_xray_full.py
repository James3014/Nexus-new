import pytest
import os
from nexus.core.xray_observer import XRayObserver

def test_xray_multi_repo_scan(tmp_path):
    """驗證 v23 觀察者能否同時掃描核心與 Benchmarks"""
    benchmark_fixture = tmp_path / "benchmarks"
    benchmark_fixture.mkdir()
    (benchmark_fixture / "click_smoke.py").write_text(
        "import click\n\n"
        "def smoke_command():\n"
        "    click.echo('ok')\n",
        encoding="utf-8",
    )
    targets = ["nexus/core", str(benchmark_fixture)]
    observer = XRayObserver(targets)
    report = observer.scan(recursive=True)
    
    assert len(report.symbols) > 500, "Should find core and benchmark symbols"
    assert any("click" in c["source"] or "click" in c["target"] for c in report.crossings), \
        "Should identify click benchmark dependencies"

def test_xray_docker_parsing(tmp_path):
    """驗證 Dockerfile 靜態分析"""
    dockerfile = tmp_path / "Dockerfile.test"
    dockerfile.write_text("FROM python:3.12-slim\nRUN pip install mock-dependency\n", encoding="utf-8")

    observer = XRayObserver([str(dockerfile)])
    report = observer.scan(recursive=False)

    targets = [c["target"] for c in report.crossings]
    assert "docker://python:3.12-slim" in targets
    assert any("Network-active installation" in r for r in report.risks)

def test_xray_skills_kb_visibility():
    """驗證全域技能庫的可見性"""
    kb_path = os.path.expanduser("~/.agents/skills/core")
    if os.path.exists(kb_path):
        observer = XRayObserver([kb_path])
        report = observer.scan(recursive=True)
        assert len(report.symbols) > 0, "Should find symbols in global skills core"

if __name__ == "__main__":
    pytest.main([__file__])
