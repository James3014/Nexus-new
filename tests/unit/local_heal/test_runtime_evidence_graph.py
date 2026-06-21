"""Tests for runtime AST-based Evidence Graph Builder."""
import hashlib
import tempfile
from pathlib import Path

import pytest

from nexus.services.local_heal.evidence_graph import (
    EvidenceGraph,
    EvidenceGraphBuilder,
    RuntimeASTExtractor,
)


class TestRuntimeASTExtractor:
    """Tests for RuntimeASTExtractor."""

    def test_compute_source_hash_changes_with_content(self, tmp_path):
        """source_hash MUST change when file contents change."""
        file1 = tmp_path / "test1.py"
        file1.write_text("def foo(): pass")
        hash1 = RuntimeASTExtractor.compute_source_hash(str(file1))

        file2 = tmp_path / "test2.py"
        file2.write_text("def bar(): pass")
        hash2 = RuntimeASTExtractor.compute_source_hash(str(file2))

        assert hash1 != hash2
        assert len(hash1) == 16  # Truncated SHA256

    def test_compute_source_hash_nonexistent_file(self):
        """Nonexistent file returns empty hash."""
        result = RuntimeASTExtractor.compute_source_hash("/nonexistent/file.py")
        assert result == ""

    def test_extract_from_file_basic(self, tmp_path):
        """Extract nodes and edges from a simple Python file."""
        test_file = tmp_path / "sample.py"
        test_file.write_text("""
import os

class MyClass:
    def method_a(self):
        return os.path.join("a", "b")

    def method_b(self):
        return self.method_a()
""")

        nodes, edges, risks = RuntimeASTExtractor.extract_from_file(str(test_file))

        assert len(nodes) > 0
        assert any(n["type"] == "class" and n["name"] == "MyClass" for n in nodes)
        assert any(n["type"] == "function" and n["name"] == "method_a" for n in nodes)
        assert any(n["type"] == "function" and n["name"] == "method_b" for n in nodes)
        assert any(n["type"] == "import" for n in nodes)
        assert len(edges) > 0
        assert risks == [] or all("error" in r.lower() or "risk" in r.lower() for r in risks)

    def test_extract_from_file_nonexistent(self, tmp_path):
        """Missing file produces missing_context_risks."""
        nodes, edges, risks = RuntimeASTExtractor.extract_from_file(str(tmp_path / "nonexistent.py"))

        assert nodes == []
        assert edges == []
        assert any("file_not_found" in r for r in risks)

    def test_extract_from_file_syntax_error(self, tmp_path):
        """File with syntax error produces ast_parse_error risk."""
        test_file = tmp_path / "bad.py"
        test_file.write_text("def foo(:\n  broken")

        nodes, edges, risks = RuntimeASTExtractor.extract_from_file(str(test_file))

        assert any("ast_parse_error" in r for r in risks)


class TestEvidenceGraphBuilder:
    """Tests for EvidenceGraphBuilder."""

    def test_task_id_does_not_branch(self, tmp_path):
        """task_id perturbation does NOT change graph construction path."""
        test_file = tmp_path / "sample.py"
        test_file.write_text("def hello(): pass")

        builder = EvidenceGraphBuilder()
        graph1 = builder.build("task_A", str(tmp_path), target_files=[str(test_file)])
        graph2 = builder.build("task_Bcompletely_different", str(tmp_path), target_files=[str(test_file)])

        # Same source files should produce same structure
        assert len(graph1.nodes) == len(graph2.nodes)
        assert len(graph1.edges) == len(graph2.edges)

    def test_graph_from_source_not_task_id(self, tmp_path):
        """Graph is generated from source file, not from task_id."""
        test_file = tmp_path / "real_code.py"
        test_file.write_text("""
class Calculator:
    def add(self, a, b):
        return a + b
""")

        builder = EvidenceGraphBuilder()
        graph = builder.build("any_task_id", str(tmp_path), target_files=[str(test_file)])

        assert any(n.name == "Calculator" for n in graph.nodes)
        assert any(n.name == "add" for n in graph.nodes)
        assert graph.task_id == "any_task_id"  # Only used for labeling

    def test_source_hash_is_real(self, tmp_path):
        """source_hash is computed from actual file contents."""
        test_file = tmp_path / "content.py"
        test_file.write_text("def test(): pass")

        builder = EvidenceGraphBuilder()
        graph = builder.build("test_task", str(tmp_path), target_files=[str(test_file)])

        assert len(graph.nodes) > 0
        for node in graph.nodes:
            assert node.source_hash != ""
            assert node.source_hash != "hash_l1"  # Not hardcoded
            assert node.source_hash != "hash_p1"
            assert node.source_hash != "hash_gen"
            # Verify it's a real hash of the file
            expected_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()[:16]
            assert node.source_hash == expected_hash

    def test_missing_file_produces_risks(self, tmp_path):
        """Missing file produces explicit missing_context_risks."""
        builder = EvidenceGraphBuilder()
        graph = builder.build(
            "test_task",
            str(tmp_path),
            target_files=[str(tmp_path / "nonexistent.py")],
        )

        assert any("file_not_found" in r for r in graph.missing_context_risks)

    def test_no_hardcoded_fixtures(self, tmp_path):
        """No hardcoded fixture task branches remain."""
        builder = EvidenceGraphBuilder()

        # These task IDs should NOT produce special graphs
        for task_id in ["sympy-14096", "django-11505", "django-13455"]:
            graph = builder.build(task_id, str(tmp_path), target_files=[])

            # Should NOT have hardcoded nodes
            assert not any("hash_l1" in n.source_hash for n in graph.nodes)
            assert not any("hash_p1" in n.source_hash for n in graph.nodes)
            assert not any("hash_b1" in n.source_hash for n in graph.nodes)
            assert not any("hash_c1" in n.source_hash for n in graph.nodes)
            assert not any("hash_comp" in n.source_hash for n in graph.nodes)
            assert not any("hash_q" in n.source_hash for n in graph.nodes)
            assert not any("hash_gen" in n.source_hash for n in graph.nodes)

    def test_bounded_context_budget(self, tmp_path):
        """Graph respects node and edge budget."""
        # Create a file with many functions
        content = "\n".join([f"def func_{i}(): pass" for i in range(100)])
        test_file = tmp_path / "many_funcs.py"
        test_file.write_text(content)

        builder = EvidenceGraphBuilder()
        graph = builder.build("test_task", str(tmp_path), target_files=[str(test_file)])

        assert len(graph.nodes) <= RuntimeASTExtractor.MAX_NODES
        assert len(graph.edges) <= RuntimeASTExtractor.MAX_EDGES

    def test_evidence_confidence_computed(self, tmp_path):
        """evidence_confidence is computed from node confidence scores."""
        test_file = tmp_path / "sample.py"
        test_file.write_text("def foo(): pass")

        builder = EvidenceGraphBuilder()
        graph = builder.build("test_task", str(tmp_path), target_files=[str(test_file)])

        assert 0.0 <= graph.evidence_confidence <= 1.0


class TestRegression:
    """Regression tests to ensure existing functionality preserved."""

    def test_c_12481_still_passes(self):
        """C_12481 regression check - graph builds without error."""
        builder = EvidenceGraphBuilder()
        # Should not crash with any task_id
        graph = builder.build("C_12481", "/tmp/fake_repo", target_files=[])
        assert graph.task_id == "C_12481"

    def test_c_13453_still_passes(self):
        """C_13453 regression check - graph builds without error."""
        builder = EvidenceGraphBuilder()
        graph = builder.build("C_13453", "/tmp/fake_repo", target_files=[])
        assert graph.task_id == "C_13453"
