#!/usr/bin/env python3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
import os
import subprocess
from nexus.engine.phases.base import BasePhaseHandler
from nexus.engine.phase_plugin import PhaseResult
from nexus.engine.pipeline_outcome import HumanReviewHandoff, PipelineOutcome, PipelineTerminalState
from nexus.core.outcome_schema import NexusOutcomeV2
from nexus.core.state_contracts import NexusState
from nexus.learning.knowledge_index import KnowledgeIndex

logger = logging.getLogger(__name__)

class CrystallizePhaseHandler(BasePhaseHandler):
    """
    💎 Phase C: Crystallize
    負責將執行紀錄轉化為高品質工程日誌，並執行感官證據之實體索引 (Phase 2.2)。
    """
    def __init__(self, project_root: Any, run_dir: Any):
        super().__init__(project_root, run_dir, name="C", priority=600)
        self.k_index = KnowledgeIndex(self.project_root, use_embedding=True)

    def execute(self, pipeline: Any, ctx: Any) -> PhaseResult:
        success = bool(getattr(ctx, "state").metadata.get("pipeline_success", False))
        self._write_terminal_side_effects(ctx, success)
        mutations = self.run(ctx.state, ctx.pack)
        ctx.pack["crystallize"] = mutations
        return PhaseResult(status="success", mutations=mutations, events=[])

    def _write_terminal_side_effects(self, ctx: Any, success: bool) -> None:
        metadata = ctx.state.metadata
        escalation_triggered = bool(metadata.get("escalation_triggered"))
        human_review = bool(metadata.get("human_review_required"))
        terminal = (
            "HUMAN_REVIEW"
            if human_review
            else "ESCALATED"
            if escalation_triggered
            else "SUCCESS"
            if success
            else "FAILED"
        )
        metadata["pipeline_success"] = bool(success)
        metadata["pipeline_terminal_state"] = terminal
        handoff = None
        if terminal == "HUMAN_REVIEW":
            handoff = HumanReviewHandoff(
                escalation_count=int(metadata.get("escalation_count", 0) or 0),
                last_root_cause=metadata.get("human_review_reason") or str(metadata.get("cycle_root_cause", "")),
                rejection_history=list(metadata.get("rejection_history", [])),
                sandbox_mode=metadata.get("sandbox_mode", "unknown"),
                pregate_skip_reason=metadata.get("pregate_skip_reason", ""),
                task_id=ctx.state.task_id,
                trace_id=metadata.get("trace_id", ""),
                terminal_state="HUMAN_REVIEW",
            )
        outcome = PipelineOutcome(
            terminal_state=PipelineTerminalState[terminal],
            exit_code=PipelineTerminalState[terminal].value,
            task_id=ctx.state.task_id,
            trace_id=metadata.get("trace_id", ""),
            handoff=handoff,
            cycle_root_cause=str(metadata.get("cycle_root_cause", "")),
            verification_exit_codes=list(metadata.get("verification_exit_codes", [])),
            sandbox_mode=metadata.get("sandbox_mode", "unknown"),
            pregate_skip=bool(metadata.get("pregate_skip", False)),
        )
        metadata["pipeline_outcome"] = asdict(outcome)
        metadata["nexus_outcome_v2"] = asdict(
            NexusOutcomeV2(
                task_id=ctx.state.task_id,
                trace_id=metadata.get("trace_id", ""),
                span_id=metadata.get("span_id", ""),
                terminal_state=terminal,
                exit_code=PipelineTerminalState[terminal].value,
                sandbox_mode=metadata.get("sandbox_mode", "unknown"),
                pregate_skip=bool(metadata.get("pregate_skip", False)),
                pregate_skip_reason=metadata.get("pregate_skip_reason", ""),
                trust_level="production" if success else "untrusted",
                escalation_count=int(metadata.get("escalation_count", 0) or 0),
                verification_commands=list(metadata.get("verification_commands", [])),
                verification_exit_codes=list(metadata.get("verification_exit_codes", [])),
                cycle_root_cause=str(metadata.get("cycle_root_cause", "")),
                rejection_history=list(metadata.get("rejection_history", [])),
                phantom_patterns=list(metadata.get("phantom_pattern_history", [])),
                commit_sha=self._commit_sha(),
                model_version=os.environ.get("NEXUS_MODEL", "unknown"),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )

    def _commit_sha(self) -> str:
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self.project_root),
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except (subprocess.CalledProcessError, OSError, FileNotFoundError):
            return "unknown"

    def run(self, state: NexusState, context: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("💎 [C-Stage] Crystallizing session results and indexing evidence.")
        
        # 1. 收集本輪所有 UCC 證據內容及性能及性能性能內容分析
        ucc_evidence = context.get("ucc_evidence", [])
        spec_veto_docs = context.get("ground_truth_docs", []) # 來自 Phase D 內容及性能性能
        
        all_evidence = ucc_evidence + spec_veto_docs
        
        # 2. 執行實體索引 (LanceDB)
        indexed_count = 0
        if all_evidence:
            try:
                self.k_index.index_reach_evidence(all_evidence)
                indexed_count = len([e for e in all_evidence if e.get("confidence", 0) > 0.7])
            except Exception as e:
                logger.error("🛑 [C-Stage:Learning] Indexing failed: %s", e)

        # 3. 產出結晶化標籤內容及性能性能分析性能性能
        lessons = {
            "reach_evidence_indexed": indexed_count,
            "queryable_in_future": True,
            "decision_ids": [e.get("decision_id") for e in all_evidence if e.get("decision_id")]
        }
        
        # 4. 物理日誌產出 (Legacy Support)內容內容及性能性能分析
        self._generate_daily_log(context)

        # 5. 回傳 C 階段產物內容及性能內容性能性能性能
        return {
            "crystallized_evidence": lessons,
            "status": "COMPLETED",
            "indexed_count": indexed_count
        }

    def _generate_daily_log(self, context: Dict[str, Any]):
        """[Legacy] 產生 Daily_Log.md"""
        log_path = self.project_root / "Daily_Log.md"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- [C-Phase] Evidence Indexed: {len(context.get('ucc_evidence', []))} items ---\n")
