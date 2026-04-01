import pytest
import os
from nexus.core.xray_observer import XRayObserver

def test_xray_multi_repo_scan():
    """驗證 v23 觀察者能否同時掃描核心與 Benchmarks"""
    targets = ["nexus/core", "benchmarks"]
    observer = XRayObserver(targets)
    report = observer.scan(recursive=True)
    
    assert len(report.symbols) > 500, "Should find core and benchmark symbols"
    assert any("click" in c["source"] or "click" in c["target"] for c in report.crossings), \
        "Should identify click benchmark dependencies"

def test_xray_docker_parsing():
    """驗證 Dockerfile 靜態分析"""
    # 建立臨時 Dockerfile
    docker_content = "FROM python:3.12-slim\nRUN pip install mock-dependency\n"
    with open("Dockerfile.test", "w") as f:
        f.write(docker_content)
        
    try:
        observer = XRayObserver(["Dockerfile.test"])
        report = observer.scan(recursive=False)
        
        # 斷言：識別出 Base Image
        targets = [c["target"] for c in report.crossings]
        assert "docker://python:3.12-slim" in targets
        
        # 斷言：識別出風險
        assert any("Network-active installation" in r for r in report.risks)
    finally:
        if os.path.exists("Dockerfile.test"):
            os.remove("Dockerfile.test")

def test_xray_skills_kb_visibility():
    """驗證全域技能庫的可見性"""
    kb_path = os.path.expanduser("~/.agents/skills/core")
    if os.path.exists(kb_path):
        observer = XRayObserver([kb_path])
        report = observer.scan(recursive=True)
        assert len(report.symbols) > 0, "Should find symbols in global skills core"

if __name__ == "__main__":
    pytest.main([__file__])
