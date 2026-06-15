from __future__ import annotations
import json
from pathlib import Path
from nexus.engine.surgical_slicer import SurgicalSlicer
from nexus.engine.surgical_intel_service import SurgicalIntelligence
from nexus.core.vector_rag import VectorRAG

def test_surgical_slicer_line_tracking(tmp_path) -> None:
    src_file = tmp_path / "math_utils.py"
    src_file.write_text("""# Math file
def calculate_sum(a, b):
    # Sum function
    return a + b

class Calculator:
    def multiply(self, x, y):
        return x * y
""")

    slicer = SurgicalSlicer(src_file)
    
    # 1. Test function slicing lines
    res_func = slicer.slice_function("calculate_sum")
    assert res_func.start_line == 2
    assert res_func.end_line == 4
    
    # 2. Test class slicing lines
    res_class = slicer.slice_function("Calculator")
    assert res_class.start_line == 6
    assert res_class.end_line == 8

def test_surgical_intel_evidence_logging(tmp_path) -> None:
    src_file = tmp_path / "utils.py"
    src_file.write_text("""
def calculate_sum(a, b):
    return a + b
""")
    
    log_file = tmp_path / "surgical_evidence.jsonl"
    intel = SurgicalIntelligence(root=tmp_path, evidence_log_path=log_file)
    # mock finder definition
    intel.retriever.find_definition = lambda sym: [src_file]
    
    ctx = intel.provide_context("calculate_sum", budget=100)
    assert "def calculate_sum" in ctx
    assert log_file.exists()
    
    lines = log_file.read_text().strip().split("\n")
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["symbol"] == "calculate_sum"
    assert row["file_path"] == "utils.py"
    assert row["start_line"] == 2
    assert row["end_line"] == 3
    assert row["budget_tokens"] == 100

def test_vector_rag_query_multigranularity() -> None:
    rag = VectorRAG()
    mock_rows = [
        {"task": "file pattern A", "granularity": "file", "resolution": "res A"},
        {"task": "class pattern B", "granularity": "class", "resolution": "res B"},
        {"task": "func pattern C", "granularity": "function", "resolution": "res C"},
        {"task": "line pattern D", "granularity": "line", "resolution": "res D"},
        {"task": "file pattern E", "granularity": "unknown", "resolution": "res E"}
    ]
    rag._load_fallback_rows = lambda: mock_rows
    rag.enabled = False  # force fallback to avoid ollama dependency
    
    grouped = rag.query_multigranularity("pattern", k=2)
    assert len(grouped["file"]) == 2  # "file pattern A" and "file pattern E" (unknown -> file)
    assert len(grouped["class"]) == 1
    assert len(grouped["function"]) == 1
    assert len(grouped["line"]) == 1
    
    # Verify format_for_prompt
    prompt = rag.format_for_prompt(grouped)
    assert "MULTIGRANULAR REUSED PATTERNS" in prompt
    assert "[FILE LEVEL]" in prompt
    assert "[CLASS LEVEL]" in prompt
    assert "[FUNCTION LEVEL]" in prompt
    assert "[LINE LEVEL]" in prompt
    assert "file pattern A" in prompt
