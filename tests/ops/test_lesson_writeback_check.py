import pytest
import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from scripts.ops.lesson_writeback_check import check_lesson_evidence

def test_lesson_check_pass_acceptance(tmp_path):
    reports_dir = tmp_path / ".nexus" / "reports"
    reports_dir.mkdir(parents=True)
    acceptance_file = reports_dir / "acceptance_check.json"
    acceptance_file.write_text(json.dumps({"status": "PASS", "gate_passed": True}))
    
    assert check_lesson_evidence(tmp_path) is True

def test_lesson_check_fail_no_evidence(tmp_path):
    reports_dir = tmp_path / ".nexus" / "reports"
    reports_dir.mkdir(parents=True)
    acceptance_file = reports_dir / "acceptance_check.json"
    acceptance_file.write_text(json.dumps({"status": "FAIL", "gate_passed": False}))
    
    assert check_lesson_evidence(tmp_path) is False

def test_lesson_check_fail_with_json_evidence(tmp_path):
    reports_dir = tmp_path / ".nexus" / "reports"
    reports_dir.mkdir(parents=True)
    acceptance_file = reports_dir / "acceptance_check.json"
    acceptance_file.write_text(json.dumps({"status": "FAIL", "gate_passed": False}))
    
    lesson_file = reports_dir / "lesson_writeback.json"
    lesson_file.write_text("{}")
    
    assert check_lesson_evidence(tmp_path) is True

def test_lesson_check_fail_with_matrix_evidence(tmp_path):
    reports_dir = tmp_path / ".nexus" / "reports"
    reports_dir.mkdir(parents=True)
    acceptance_file = reports_dir / "acceptance_check.json"
    acceptance_file.write_text(json.dumps({"status": "FAIL", "gate_passed": False}))
    
    matrix_dir = tmp_path / "nexus_wiki_vault" / "06_Ops"
    matrix_dir.mkdir(parents=True)
    matrix_file = matrix_dir / "Ops - Learning Closure Matrix.md"
    today_str = datetime.now().strftime("%Y-%m-%d")
    matrix_file.write_text(f"Some content before {today_str} some content after")
    
    assert check_lesson_evidence(tmp_path) is True

def test_lesson_check_fail_with_outdated_json_evidence(tmp_path, monkeypatch):
    reports_dir = tmp_path / ".nexus" / "reports"
    reports_dir.mkdir(parents=True)
    acceptance_file = reports_dir / "acceptance_check.json"
    acceptance_file.write_text(json.dumps({"status": "FAIL", "gate_passed": False}))
    
    lesson_file = reports_dir / "lesson_writeback.json"
    lesson_file.write_text("{}")
    
    # Set mtime to 2 days ago
    mtime = (datetime.now() - timedelta(days=2)).timestamp()
    os.utime(lesson_file, (mtime, mtime))
    
    assert check_lesson_evidence(tmp_path) is False
