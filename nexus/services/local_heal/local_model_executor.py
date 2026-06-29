from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from typing import Any, Mapping

from nexus.services.local_heal.local_model_provider import (
    LocalModelProvider,
    LocalModelProviderRequest,
    InertLocalModelProvider,
    OllamaLocalModelProvider,
    InjectedLocalModelProvider,
)
from nexus.services.local_heal.capability_adapter import build_local_model_provider_from_env


@dataclass(frozen=True)
class LocalModelExecutorRequest:
    task_id: str
    problem_statement: str
    repo_root: str
    target_file: str
    selected_capabilities: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    receipt_context: dict[str, Any] = field(default_factory=dict)
    route_context: dict[str, Any] = field(default_factory=dict)
    model_name: str = ""
    dry_run: bool = True
    mutation_allowed: bool = False
    verifier_allowed: bool = False
    execution_topology: str = "single_local_model"


@dataclass(frozen=True)
class LocalModelExecutorResponse:
    invoked: bool
    local_model_called: bool
    candidate_patch: str
    candidate_hash: str
    reasoning_summary: str
    raw_model_metadata: dict[str, Any]
    provider: str
    model_name: str
    error: str
    timeout: bool
    evidence_refs: tuple[str, ...]


def _resolve_execution_topology(request: LocalModelExecutorRequest) -> str:
    """Resolve execution topology with planner-owned signal_snapshot as first priority.
    
    Resolution order:
    1. request.route_context["signal_snapshot"]["execution_topology"] (planner-owned)
    2. request.route_context["execution_topology"] (top-level fallback)
    3. request.execution_topology (request field)
    4. "single_local_model" (hardcoded default)
    """
    route_ctx = request.route_context if isinstance(request.route_context, dict) else {}
    
    signal_snapshot = route_ctx.get("signal_snapshot")
    if not isinstance(signal_snapshot, dict):
        signal_snapshot = {}
    
    topology = signal_snapshot.get("execution_topology")
    if topology:
        return str(topology)
    
    topology = route_ctx.get("execution_topology")
    if topology:
        return str(topology)
    
    topology = request.execution_topology
    if topology:
        return str(topology)
    
    return "single_local_model"


class LocalModelExecutor:
    @staticmethod
    def run(request: LocalModelExecutorRequest, *, provider: LocalModelProvider | None = None) -> LocalModelExecutorResponse:
        empty_hash = hashlib.sha256(b"").hexdigest()
        
        execution_topology = _resolve_execution_topology(request)
        
        # 1. Handle Dry Run
        if request.dry_run:
            return LocalModelExecutorResponse(
                invoked=False,
                local_model_called=False,
                candidate_patch="",
                candidate_hash=empty_hash,
                reasoning_summary="dry_run_active",
                raw_model_metadata={"dry_run": True, "execution_topology": execution_topology},
                provider="none",
                model_name="",
                error="dry_run",
                timeout=False,
                evidence_refs=request.evidence_refs,
            )

        # 2. Build Provider
        if provider is None:
            provider = build_local_model_provider_from_env(
                os.environ,
                request.route_context,
                "candidate_generate_fn"
            )

        # 3. Check Provider Availability
        if isinstance(provider, InertLocalModelProvider):
            return LocalModelExecutorResponse(
                invoked=True,
                local_model_called=False,
                candidate_patch="",
                candidate_hash=empty_hash,
                reasoning_summary="provider_unavailable",
                raw_model_metadata={},
                provider="inert",
                model_name="",
                error="provider_unavailable",
                timeout=False,
                evidence_refs=request.evidence_refs,
            )

        # 4. Handle Active Memory Retrieval if enabled
        selected_caps = request.selected_capabilities
        lessons = []
        if "memory" in selected_caps:
            try:
                from nexus.services.local_heal.memory_retrieval_adapter import MemoryRetrievalAdapter
                adapter = MemoryRetrievalAdapter(enabled=True)
                lessons = adapter.retrieve_reranked(
                    query_text=request.problem_statement,
                    anchor_symbol=request.route_context.get("target_symbol") or "",
                    anchor_file=request.target_file,
                    limit=3,
                    max_chars=800,
                    task_id=request.task_id
                )
            except Exception:
                pass

        memory_context = ""
        if lessons:
            memory_context = "\n\n=== RELEVANT HISTORICAL LESSONS ===\n"
            for idx, lesson in enumerate(lessons, 1):
                content = ""
                if hasattr(lesson, "summary"):
                    content = lesson.summary
                elif hasattr(lesson, "content"):
                    content = lesson.content
                else:
                    content = str(lesson)
                memory_context += f"Lesson {idx}: {content}\n"
            memory_context += "====================================\n"

        # 5. Handle Execution Topology Branching
        if execution_topology == "local_committee_only":
            protocol_mode = os.environ.get("NEXUS_PROTOCOL_MODE", "anchored_edit")
            target_symbol = request.route_context.get("target_symbol") or ""
            locked_search = request.route_context.get("locked_search") or ""
            
            from nexus.services.local_heal.local_committee_candidate_provider import LocalCommitteeCandidateProvider
            from nexus.services.local_heal.candidate_decision_adapter import CandidateDecisionAdapter
            
            # Generate committee candidates with memory context appended to problem statement
            candidates = LocalCommitteeCandidateProvider.generate_committee_candidates(
                task_id=request.task_id,
                problem_statement=request.problem_statement + memory_context,
                target_file=request.target_file,
                target_symbol=target_symbol,
                locked_search=locked_search,
                evidence_refs=request.evidence_refs,
                provider=provider,
                protocol_mode=protocol_mode,
            )
            
            decision = CandidateDecisionAdapter.select_candidate(candidates)
            
            # Local model is called if at least one candidate wasn't blocked/abstained
            local_model_called = any(not c.abstained for c in candidates)
            
            selected_patch = decision.selected_candidate_patch
            if selected_patch.strip():
                selected_patch = _convert_to_unified_diff(request, locked_search, selected_patch)
                selected_hash = hashlib.sha256(selected_patch.encode("utf-8")).hexdigest()
            else:
                selected_hash = empty_hash
                
            provider_name = "ollama" if isinstance(provider, OllamaLocalModelProvider) else "injected"
            
            # Resolve selected model name or fallback to "committee"
            selected_model = ""
            for c in candidates:
                if c.candidate_id == decision.selected_candidate_id:
                    selected_model = c.model
                    break
            if not selected_model:
                selected_model = "committee"
                
            return LocalModelExecutorResponse(
                invoked=True,
                local_model_called=local_model_called,
                candidate_patch=selected_patch,
                candidate_hash=selected_hash,
                reasoning_summary=f"selected_by_{decision.selected_by}",
                raw_model_metadata={
                    "execution_topology": "local_committee_only",
                    "committee_candidate_count": len(candidates),
                    "selected_candidate_id": decision.selected_candidate_id,
                    "selected_by": decision.selected_by,
                    "final_authority": decision.final_authority,
                },
                provider=provider_name,
                model_name=selected_model,
                error="",
                timeout=False,
                evidence_refs=decision.decision_evidence_refs or request.evidence_refs,
            )

        # 6. Generate Candidate Patch for single_local_model
        protocol_mode = os.environ.get("NEXUS_PROTOCOL_MODE", "standard")
        
        if protocol_mode == "anchored_edit":
            locked_search = request.route_context.get("locked_search") or ""
            target_symbol = request.route_context.get("target_symbol") or ""
            explicit_prompt = (
                f"You are generating a replacement code block to solve a coding task.\n"
                f"Problem: {request.problem_statement}{memory_context}\n"
                f"Target File: {request.target_file}\n"
                f"Target Symbol: {target_symbol}\n"
                f"Locked Search Span that will be replaced:\n"
                f"```\n{locked_search}\n```\n\n"
                f"Provide the replacement code inside a REPLACE block exactly like this:\n"
                f"<<<<<<< REPLACE\n"
                f"[replacement code goes here]\n"
                f">>>>>>> REPLACE\n\n"
                f"Do not include any other text, explanation, markdown formatting, or markdown code fences outside the REPLACE block.\n"
            )
        else:
            # Construct explicit prompt to output standard unified diff
            # Include locked_search context so the model generates an applicable patch
            locked_search = request.route_context.get("locked_search") or ""
            target_symbol = request.route_context.get("target_symbol") or ""

            # Read surrounding context from the actual file
            source_context = ""
            try:
                from pathlib import Path as _Path
                _fp = _Path(request.repo_root) / request.target_file if request.repo_root else _Path(request.target_file)
                if _fp.exists():
                    _lines = _fp.read_text(encoding="utf-8").splitlines()
                    # Find locked_search start line
                    _search_first = locked_search.strip().splitlines()[0].strip() if locked_search.strip() else ""
                    _anchor_line = 1
                    for _i, _l in enumerate(_lines, 1):
                        if _search_first and _search_first in _l:
                            _anchor_line = _i
                            break
                    # Show ±15 lines around anchor
                    _start = max(0, _anchor_line - 16)
                    _end = min(len(_lines), _anchor_line + 20)
                    numbered = "\n".join(f"{_start+_j+1}: {_lines[_start+_j]}" for _j in range(_end - _start))
                    source_context = f"\nRelevant source lines (with line numbers):\n```python\n{numbered}\n```\n"
            except Exception:
                pass

            context_block = ""
            if locked_search.strip():
                context_block = (
                    f"\nThe code to be changed (locked search span):\n"
                    f"```python\n{locked_search}\n```\n"
                )

            explicit_prompt = (
                f"You are generating a unified diff to fix a bug in {request.target_file}.\n"
                f"Problem: {request.problem_statement}{memory_context}\n"
                f"Target File: {request.target_file}\n"
                f"Target Symbol: {target_symbol}\n"
                f"{context_block}"
                f"{source_context}\n"
                f"IMPORTANT RULES:\n"
                f"1. The diff header MUST use exactly: --- a/{request.target_file}  and  +++ b/{request.target_file}\n"
                f"2. The @@ hunk header MUST use the EXACT line numbers from the source above.\n"
                f"3. Context lines (no +/-) MUST EXACTLY match the source file character-for-character including indentation.\n"
                f"4. Return ONLY the diff wrapped in a ```diff fenced block. No prose, no explanation.\n"
            )

        
        prov_req = LocalModelProviderRequest(
            task_id=request.task_id,
            prompt=explicit_prompt,
            evidence_refs=request.evidence_refs,
            model_name=request.model_name or os.environ.get("NEXUS_LOCAL_MODEL_NAME", "qwen2.5-coder:7b"),
        )
        
        prov_resp = provider.generate(prov_req)
        
        candidate_patch = prov_resp.output_text
        if candidate_patch.strip():
            candidate_patch = _convert_to_unified_diff(request, locked_search, candidate_patch)
            candidate_hash = hashlib.sha256(candidate_patch.encode("utf-8")).hexdigest()
        else:
            candidate_hash = empty_hash
            
        provider_name = "ollama" if isinstance(provider, OllamaLocalModelProvider) else "injected"
        
        return LocalModelExecutorResponse(
            invoked=prov_resp.provider_invoked,
            local_model_called=prov_resp.model_called,
            candidate_patch=candidate_patch,
            candidate_hash=candidate_hash,
            reasoning_summary="success" if not prov_resp.error else "failed",
            raw_model_metadata={
                "output_truncated": prov_resp.output_truncated,
                "error": prov_resp.error,
                "protocol_mode": protocol_mode,
                "execution_topology": execution_topology,
            },
            provider=provider_name,
            model_name=prov_resp.model_name or prov_req.model_name,
            error=prov_resp.error,
            timeout=prov_resp.timed_out,
            evidence_refs=request.evidence_refs,
        )


def _convert_to_unified_diff(request: LocalModelExecutorRequest, locked_search: str, candidate_patch: str) -> str:
    if not candidate_patch.strip():
        return ""
        
    # 如果已經是 standard unified diff 格式，且沒有 REPLACE 標記，則直接返回
    if "--- a/" in candidate_patch and "+++ b/" in candidate_patch and "<<<<<<< REPLACE" not in candidate_patch:
        return candidate_patch

    # 1. 提取 replacement 內容
    clean_patch = candidate_patch.strip()
    if "<<<<<<< REPLACE" in clean_patch:
        try:
            parts = clean_patch.split("<<<<<<< REPLACE")
            if len(parts) > 1:
                inner = parts[1].split(">>>>>>> REPLACE")[0]
                clean_patch = inner.strip("\r\n")
        except Exception:
            pass

    # 2. 尋找 _anchor_line
    _anchor_line = 1
    if locked_search.strip():
        try:
            from pathlib import Path as _Path
            _fp = _Path(request.repo_root) / request.target_file if request.repo_root else _Path(request.target_file)
            if _fp.exists():
                _lines = _fp.read_text(encoding="utf-8").splitlines()
                _search_first = locked_search.strip().splitlines()[0].strip()
                for _i, _l in enumerate(_lines, 1):
                    if _search_first in _l:
                        _anchor_line = _i
                        break
        except Exception:
            pass

    # 3. 使用 difflib 生成 unified diff
    import difflib
    import re
    
    locked_lines = locked_search.splitlines(keepends=True)
    clean_lines = clean_patch.splitlines(keepends=True)
    
    # 確保結尾有換行符
    locked_lines = [l if l.endswith("\n") else l + "\n" for l in locked_lines]
    clean_lines = [l if l.endswith("\n") else l + "\n" for l in clean_lines]
    
    diff_gen = difflib.unified_diff(
        locked_lines,
        clean_lines,
        fromfile=f"a/{request.target_file}",
        tofile=f"b/{request.target_file}",
        lineterm="\n"
    )
    
    adjusted_lines = []
    for line in diff_gen:
        if line.startswith("@@"):
            match = re.match(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@(.*)", line)
            if match:
                old_start = int(match.group(1))
                old_len = int(match.group(2))
                new_start = int(match.group(3))
                new_len = int(match.group(4))
                extra = match.group(5)
                
                # 依據 _anchor_line 偏移
                adj_old = _anchor_line + old_start - 1
                adj_new = _anchor_line + new_start - 1
                
                line = f"@@ -{adj_old},{old_len} +{adj_new},{new_len} @@{extra}\n"
        adjusted_lines.append(line)
        
    return "".join(adjusted_lines)
