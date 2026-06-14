"""Tests for SWE-Explore Lite multi-granularity retrieval."""
import pytest
from pathlib import Path
from nexus.search.swe_explore_lite import SWEExploreLite, RetrievalBudget, LineWindowEvidence


@pytest.fixture
def sample_repo(tmp_path):
    """Create a sample repo for testing."""
    # Create a Python file with functions
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    
    (src_dir / "utils.py").write_text("""
import os
import sys

def calculate_hash(data):
    \"\"\"Calculate hash of data.\"\"\"
    import hashlib
    return hashlib.md5(data.encode()).hexdigest()

def parse_config(path):
    \"\"\"Parse config file.\"\"\"
    with open(path) as f:
        return json.load(f)

class DataProcessor:
    def __init__(self, config):
        self.config = config
    
    def process(self, data):
        return self.config.transform(data)
""")
    
    (src_dir / "models.py").write_text("""
from dataclasses import dataclass

@dataclass
class User:
    id: int
    name: str
    email: str

@dataclass
class Product:
    id: int
    title: str
    price: float
""")
    
    return tmp_path


def test_retrieve_files(sample_repo):
    """File-level retrieval works."""
    explore = SWEExploreLite()
    result = explore.retrieve("calculate hash", sample_repo, target_files=["src/utils.py"])
    
    assert len(result["files"]) == 1
    assert result["files"][0]["path"] == "src/utils.py"
    assert result["metrics"]["files_scanned"] == 1


def test_retrieve_symbols(sample_repo):
    """Symbol-level retrieval works."""
    explore = SWEExploreLite()
    result = explore.retrieve("calculate hash", sample_repo, target_files=["src/utils.py"])
    
    assert len(result["symbols"]) > 0
    symbol_names = [s["name"] for s in result["symbols"]]
    assert "calculate_hash" in symbol_names


def test_retrieve_line_windows(sample_repo):
    """Line-window retrieval works."""
    explore = SWEExploreLite()
    result = explore.retrieve("calculate hash", sample_repo, target_files=["src/utils.py"])
    
    assert len(result["line_windows"]) > 0
    assert result["line_windows"][0].file_path == "src/utils.py"
    assert result["line_windows"][0].hit_reason == "query_token_match"


def test_evidence_summary(sample_repo):
    """Evidence summary is generated."""
    explore = SWEExploreLite()
    result = explore.retrieve("calculate hash", sample_repo, target_files=["src/utils.py"])
    
    assert "src/utils.py" in result["evidence_summary"]
    assert "confidence=" in result["evidence_summary"]


def test_budget_enforcement(sample_repo):
    """Budget limits are enforced."""
    budget = RetrievalBudget(max_files=1, max_symbols_per_file=2, max_line_windows=2)
    explore = SWEExploreLite(budget=budget)
    result = explore.retrieve("hash config", sample_repo)
    
    assert len(result["files"]) <= 1
    assert len(result["symbols"]) <= 2
    assert len(result["line_windows"]) <= 2


def test_symbol_with_target_symbols(sample_repo):
    """Target symbols boost score."""
    explore = SWEExploreLite()
    result = explore.retrieve(
        "process data",
        sample_repo,
        target_files=["src/utils.py"],
        symbols=["DataProcessor"],
    )
    
    # DataProcessor should be found
    symbol_names = [s["name"] for s in result["symbols"]]
    assert "DataProcessor" in symbol_names


def test_empty_query():
    """Empty query returns empty results."""
    explore = SWEExploreLite()
    result = explore.retrieve("", Path("/nonexistent"))
    
    assert result["files"] == []
    assert result["symbols"] == []
    assert result["line_windows"] == []
    assert "No evidence" in result["evidence_summary"]


def test_line_window_evidence_dataclass():
    """LineWindowEvidence dataclass works."""
    lw = LineWindowEvidence(
        file_path="src/utils.py",
        start_line=10,
        end_line=20,
        content="def foo(): pass",
        hit_reason="symbol_match",
        confidence=0.8,
    )
    assert lw.file_path == "src/utils.py"
    assert lw.confidence == 0.8
