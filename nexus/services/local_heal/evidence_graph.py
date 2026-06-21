"""Y1: Evidence Graph v0 — Structured cross-symbol evidence builder.

Runtime AST-based graph extraction replacing hardcoded task_id branches.
Computes real source hashes and extracts bounded graph nodes/edges from source.
"""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class EvidenceNode:
    node_id: str
    type: str
    name: str
    file_path: str
    line_span: Optional[List[int]] = None
    source_hash: str = ""
    provenance: str = "ast_analysis"
    confidence_score: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "type": self.type,
            "name": self.name,
            "file_path": self.file_path,
            "line_span": self.line_span,
            "source_hash": self.source_hash,
            "provenance": self.provenance,
            "confidence_score": self.confidence_score,
        }


@dataclass
class EvidenceEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation: str
    provenance: str = "ast_call_graph"
    confidence_score: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "relation": self.relation,
            "provenance": self.provenance,
            "confidence_score": self.confidence_score,
        }


@dataclass
class EvidenceGraph:
    graph_id: str
    task_id: str
    root_anchor: Dict[str, Any]
    nodes: List[EvidenceNode] = field(default_factory=list)
    edges: List[EvidenceEdge] = field(default_factory=list)
    candidate_symbols: List[str] = field(default_factory=list)
    candidate_files: List[str] = field(default_factory=list)
    causal_paths: List[Dict[str, Any]] = field(default_factory=list)
    edit_candidate_paths: List[Dict[str, Any]] = field(default_factory=list)
    risk_paths: List[Dict[str, Any]] = field(default_factory=list)
    missing_context_risks: List[str] = field(default_factory=list)
    evidence_confidence: float = 1.0
    graph_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "task_id": self.task_id,
            "root_anchor": self.root_anchor,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "candidate_symbols": self.candidate_symbols,
            "candidate_files": self.candidate_files,
            "causal_paths": self.causal_paths,
            "edit_candidate_paths": self.edit_candidate_paths,
            "risk_paths": self.risk_paths,
            "missing_context_risks": self.missing_context_risks,
            "evidence_confidence": self.evidence_confidence,
            "graph_summary": self.graph_summary,
        }


class RuntimeASTExtractor:
    """Extracts bounded graph nodes and edges from Python source using AST."""

    MAX_NODES = 50
    MAX_EDGES = 100

    @staticmethod
    def compute_source_hash(file_path: str) -> str:
        """Compute real SHA256 hash from file contents."""
        try:
            path = Path(file_path)
            if path.exists():
                content = path.read_bytes()
                return hashlib.sha256(content).hexdigest()[:16]
        except (OSError, IOError):
            pass
        return ""

    @staticmethod
    def extract_from_file(file_path: str) -> tuple[list[dict], list[dict], list[str]]:
        """Extract nodes and edges from a Python file using AST.

        Returns:
            (nodes, edges, missing_context_risks)
        """
        nodes = []
        edges = []
        risks = []

        try:
            path = Path(file_path)
            if not path.exists():
                risks.append(f"file_not_found:{file_path}")
                return nodes, edges, risks

            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=file_path)
            source_hash = RuntimeASTExtractor.compute_source_hash(file_path)

            node_counter = 0

            for node in ast.walk(tree):
                if node_counter >= RuntimeASTExtractor.MAX_NODES:
                    risks.append("node_budget_exceeded")
                    break

                if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    node_id = f"n{node_counter}"
                    nodes.append({
                        "node_id": node_id,
                        "type": "function",
                        "name": node.name,
                        "file_path": file_path,
                        "line_span": [node.lineno, node.end_lineno or node.lineno],
                        "source_hash": source_hash,
                        "provenance": "local_ast_analysis",
                        "confidence_score": 1.0,
                    })
                    node_counter += 1

                    # Extract callsites within this function
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call) and node_counter < RuntimeASTExtractor.MAX_NODES:
                            call_name = RuntimeASTExtractor._get_call_name(child)
                            if call_name:
                                call_id = f"n{node_counter}"
                                nodes.append({
                                    "node_id": call_id,
                                    "type": "callsite",
                                    "name": call_name,
                                    "file_path": file_path,
                                    "line_span": [child.lineno, child.lineno],
                                    "source_hash": source_hash,
                                    "provenance": "local_ast_analysis",
                                    "confidence_score": 0.8,
                                })
                                edges.append({
                                    "edge_id": f"e{len(edges)}",
                                    "source_node_id": node_id,
                                    "target_node_id": call_id,
                                    "relation": "calls",
                                    "provenance": "local_ast_call_graph",
                                    "confidence_score": 0.8,
                                })
                                node_counter += 1

                elif isinstance(node, ast.ClassDef):
                    node_id = f"n{node_counter}"
                    nodes.append({
                        "node_id": node_id,
                        "type": "class",
                        "name": node.name,
                        "file_path": file_path,
                        "line_span": [node.lineno, node.end_lineno or node.lineno],
                        "source_hash": source_hash,
                        "provenance": "local_ast_analysis",
                        "confidence_score": 1.0,
                    })
                    node_counter += 1

                elif isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
                    if node_counter < RuntimeASTExtractor.MAX_NODES:
                        module_name = RuntimeASTExtractor._get_import_name(node)
                        if module_name:
                            node_id = f"n{node_counter}"
                            nodes.append({
                                "node_id": node_id,
                                "type": "import",
                                "name": module_name,
                                "file_path": file_path,
                                "line_span": [node.lineno, node.lineno],
                                "source_hash": source_hash,
                                "provenance": "local_ast_analysis",
                                "confidence_score": 1.0,
                            })
                            node_counter += 1

        except (SyntaxError, ValueError, TypeError) as exc:
            risks.append(f"ast_parse_error:{type(exc).__name__}")

        return nodes, edges, risks

    @staticmethod
    def _get_call_name(node: ast.Call) -> str | None:
        """Extract call name from AST Call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return None

    @staticmethod
    def _get_import_name(node: ast.AST) -> str | None:
        """Extract import name from AST Import/ImportFrom node."""
        if isinstance(node, ast.Import):
            return ", ".join(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = ", ".join(alias.name for alias in node.names)
            return f"{module}.{names}" if module else names
        return None


class EvidenceGraphBuilder:
    """Builds bounded Evidence Graphs for cross-symbol reasoning.

    Uses runtime AST extraction instead of hardcoded task_id branches.
    """

    def build(
        self,
        task_id: str,
        repo: str,
        target_files: Optional[List[str]] = None,
        failing_symbol: Optional[str] = None,
    ) -> EvidenceGraph:
        """Build evidence graph from actual source files.

        Args:
            task_id: Task identifier (for labeling only, NOT for branching).
            repo: Repository root path.
            target_files: Files to analyze. If None, returns minimal graph.
            failing_symbol: Optional symbol name from test failure.

        Returns:
            EvidenceGraph with real AST-extracted nodes and edges.
        """
        extractor = RuntimeASTExtractor()
        all_nodes = []
        all_edges = []
        all_risks = []
        candidate_symbols = []
        candidate_files = []

        root_anchor = {
            "symbol": failing_symbol or "unknown",
            "file": target_files[0] if target_files else f"{repo}/unknown",
            "start_line": 1,
            "end_line": 1,
        }

        if target_files:
            for file_path in target_files[:5]:  # Bounded context budget
                nodes, edges, risks = extractor.extract_from_file(file_path)
                all_nodes.extend(nodes)
                all_edges.extend(edges)
                all_risks.extend(risks)
                candidate_files.append(file_path)

                # Extract function/method names as candidate symbols
                for node in nodes:
                    if node["type"] in ("function", "class"):
                        candidate_symbols.append(node["name"])

        # Trim to budget
        all_nodes = all_nodes[:RuntimeASTExtractor.MAX_NODES]
        all_edges = all_edges[:RuntimeASTExtractor.MAX_EDGES]

        # Compute aggregate confidence
        if all_nodes:
            confidence = sum(n.get("confidence_score", 1.0) for n in all_nodes) / len(all_nodes)
        else:
            confidence = 0.5
            all_risks.append("no_nodes_extracted")

        graph = EvidenceGraph(
            graph_id=f"g_{task_id}",
            task_id=task_id,
            root_anchor=root_anchor,
            candidate_symbols=candidate_symbols[:10],
            candidate_files=candidate_files,
            evidence_confidence=confidence,
            graph_summary=f"Runtime AST graph: {len(all_nodes)} nodes, {len(all_edges)} edges from {len(candidate_files)} files.",
        )

        # Convert dicts to EvidenceNode/EvidenceEdge objects
        for n in all_nodes:
            graph.nodes.append(EvidenceNode(
                node_id=n["node_id"],
                type=n["type"],
                name=n["name"],
                file_path=n["file_path"],
                line_span=n.get("line_span"),
                source_hash=n.get("source_hash", ""),
                provenance=n.get("provenance", "local_ast_analysis"),
                confidence_score=n.get("confidence_score", 1.0),
            ))

        for e in all_edges:
            graph.edges.append(EvidenceEdge(
                edge_id=e["edge_id"],
                source_node_id=e["source_node_id"],
                target_node_id=e["target_node_id"],
                relation=e["relation"],
                provenance=e.get("provenance", "local_ast_call_graph"),
                confidence_score=e.get("confidence_score", 1.0),
            ))

        graph.missing_context_risks = all_risks

        # Build causal paths from edges
        if all_edges:
            path_nodes = [e["source_node_id"] for e in all_edges[:3]]
            graph.causal_paths = [{
                "path_id": f"path_{task_id}_runtime",
                "nodes": path_nodes,
                "reasoning": f"Runtime-extracted path from {len(all_edges)} call edges.",
            }]

        return graph
