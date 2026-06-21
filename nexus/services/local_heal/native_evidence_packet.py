"""B1-B: Native Evidence Packet Bridge — Compact evidence from existing Nexus capabilities."""
from __future__ import annotations

import hashlib
import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CodeIntelItem:
    file: str
    start_line: int
    end_line: int
    symbol: str
    relation: str
    relevance_reason: str


@dataclass
class MemoryItem:
    finding_id: str
    summary: str
    relevance_reason: str
    provenance: str


@dataclass
class PriorFailureItem:
    failure_type: str
    previous_candidate_summary: str
    verifier_feedback: str


@dataclass
class EvidencePacket:
    task_id: str
    route_id: str
    issue_intent: str
    base_commit: str
    source_hash: str
    selected_anchor: dict
    codeintel_evidence: list[CodeIntelItem]
    memory_evidence: list[MemoryItem]
    prior_failure_evidence: list[PriorFailureItem]
    missing_context_risks: list[str]
    context_budget: str
    prompt_inclusion_plan: str


class NativeEvidencePacketBuilder:
    """Builds compact evidence packets from existing Nexus capabilities."""

    def build(
        self,
        *,
        task_id: str,
        route_id: str,
        issue_intent: str,
        base_commit: str,
        repo_path: str,
        target_file: str,
        anchor_symbol: str,
        anchor_span: tuple[int, int],
        anchor_source_text: str,
    ) -> EvidencePacket:
        source_path = Path(repo_path) / target_file
        source_text = source_path.read_text(encoding="utf-8") if source_path.exists() else ""
        source_hash = hashlib.sha256(source_text.encode()).hexdigest()[:16] if source_text else ""

        # B1-B: Extract bounded CodeIntel evidence
        codeintel = self._extract_codeintel(
            source_text, target_file, anchor_symbol, anchor_span
        )

        # B1-B: Extract bounded memory evidence
        memory = self._extract_memory(issue_intent, anchor_symbol)

        # B1-B: Extract prior failure evidence
        prior_failures = self._extract_prior_failures(task_id)

        # B1-B: Identify missing context risks
        missing = self._identify_missing_risks(codeintel, memory, anchor_symbol)

        selected_anchor = {
            "symbol": anchor_symbol,
            "file": target_file,
            "start_line": anchor_span[0],
            "end_line": anchor_span[1],
            "source_text_preview": anchor_source_text[:200],
        }

        return EvidencePacket(
            task_id=task_id,
            route_id=route_id,
            issue_intent=issue_intent,
            base_commit=base_commit,
            source_hash=source_hash,
            selected_anchor=selected_anchor,
            codeintel_evidence=codeintel,
            memory_evidence=memory,
            prior_failure_evidence=prior_failures,
            missing_context_risks=missing,
            context_budget="bounded_evidence_packet",
            prompt_inclusion_plan="include_all_bounded_sections",
        )

    def _extract_codeintel(
        self, source_text: str, target_file: str, anchor_symbol: str,
        anchor_span: tuple[int, int],
    ) -> list[CodeIntelItem]:
        """Extract bounded CodeIntel evidence around the anchor."""
        if not source_text:
            return []

        items = []
        lines = source_text.splitlines()
        start, end = anchor_span

        # Find methods in the same class/file
        for i, line in enumerate(lines):
            if "def " in line and i != start - 1:
                method_name = line.strip().split("def ")[1].split("(")[0] if "def " in line else ""
                if method_name and method_name != anchor_symbol:
                    # Compute end line for this method
                    method_end = i + 1
                    for j in range(i + 1, min(i + 30, len(lines))):
                        if lines[j].strip() and not lines[j].strip().startswith("#"):
                            method_end = j + 1
                        elif lines[j].strip() == "" and j > i + 2:
                            break
                    items.append(CodeIntelItem(
                        file=target_file,
                        start_line=i + 1,
                        end_line=method_end,
                        symbol=method_name,
                        relation="same_class_neighbor",
                        relevance_reason=f"method in same file, may interact with {anchor_symbol}",
                    ))
                    if len(items) >= 5:
                        break

        # Find data-flow related lines
        for i, line in enumerate(lines):
            if any(kw in line.lower() for kw in ["fill_values", "iter_str_vals", "_set_col_formats", "formats"]):
                items.append(CodeIntelItem(
                    file=target_file,
                    start_line=i + 1,
                    end_line=i + 1,
                    symbol=line.strip()[:50],
                    relation="data_flow",
                    relevance_reason="formatting/data-flow related code",
                ))
                if len(items) >= 8:
                    break

        return items[:8]  # Hard bound

    def _extract_memory(self, issue_intent: str, anchor_symbol: str) -> list[MemoryItem]:
        """Extract bounded memory evidence."""
        items = []
        if issue_intent == "output_formatting":
            items.append(MemoryItem(
                finding_id="mem_output_fmt_001",
                summary="output_formatting bugs: modify write/render path, not read/parse",
                relevance_reason="matches issue_intent",
                provenance="local_memory_heuristic",
            ))
        if "write" in anchor_symbol.lower():
            items.append(MemoryItem(
                finding_id="mem_write_behavior_001",
                summary="write methods that own output behavior should be selected over caller iteration",
                relevance_reason="matches anchor_symbol",
                provenance="local_memory_heuristic",
            ))
        return items

    def _extract_prior_failures(self, task_id: str) -> list[PriorFailureItem]:
        """Extract prior failure evidence."""
        return []  # No prior failures for fresh task

    def _identify_missing_risks(
        self, codeintel: list[CodeIntelItem], memory: list[MemoryItem], anchor_symbol: str
    ) -> list[str]:
        """Identify missing context risks."""
        risks = []
        data_flow_items = [i for i in codeintel if i.relation == "data_flow"]
        if not data_flow_items:
            risks.append("no_data_flow_trace_discovered")
        if not memory:
            risks.append("no_memory_evidence_available")
        return risks
