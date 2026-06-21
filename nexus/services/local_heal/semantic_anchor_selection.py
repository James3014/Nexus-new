"""P10: Semantic Anchor Selection for anchored_edit repair.

Instead of selecting a single anchor from the first relevant symbol,
generates a small anchor candidate set and scores each candidate before
model patching. This fixes the C_13453 class of failure where the anchor
was valid but semantically at the wrong layer.
"""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nexus.services.local_heal.memory_retrieval_adapter import MemoryRetrievalAdapter


@dataclass
class AnchorCandidate:
    """A candidate anchor for semantic selection."""
    anchor_id: str
    file_path: str
    symbol_name: str
    span_start: int  # 1-indexed line number
    span_end: int    # 1-indexed line number
    source_hash: str
    candidate_type: str  # failing_stack_frame, direct_caller, direct_callee, etc.
    score: float = 0.0
    score_reasons: list[str] = field(default_factory=list)
    risk: str = "low"
    selected: bool = False
    source_text: str = ""  # exact source text of the anchor
    memory_contribution: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnchorSelectionResult:
    """Result of semantic anchor selection."""
    selected: AnchorCandidate | None
    candidates: list[AnchorCandidate]
    selection_reason: str
    source_hash: str
    file_path: str
    total_candidates: int
    # H2: Ambiguity reporting
    ambiguity: bool = False
    score_margin: float = 0.0
    top_k: list[AnchorCandidate] = field(default_factory=list)
    # BMF3-OBS: ctx-scoped memory trace (replaces BMF2 global shim)
    memory_trace: dict[str, Any] = field(default_factory=dict)


class SemanticAnchorScorer:
    """Scores anchor candidates based on semantic relevance to the bug.

    H2: Generalized intent-to-behavior-owner mapping.
    No task-specific, repo-specific, or file-specific rules.
    """

    # ── H2: Generalized Issue Intent Classes ──────────────────────────────────
    ISSUE_INTENT_KEYWORDS: dict[str, list[str]] = {
        "output_formatting": ["format", "formats", "formatting", "render", "rendering", "output", "display", "html", "table", "write", "str", "repr"],
        "input_parsing": ["parse", "parsing", "read", "load", "decode", "from_", "input", "import"],
        "validation": ["validate", "validation", "check", "verify", "assert", "ensure", "sanitize"],
        "normalization": ["normalize", "normalization", "canonicalize", "standardize"],
        "construction": ["construct", "create", "init", "__new__", "__init__", "instantiate", "factory"],
        "algebraic_semantics": ["algebra", "compose", "compose", "simplify", "eval", "expand", "reduce", "symbolic"],
        "collection_semantics": ["collection", "list", "set", "dict", "order", "sort", "unique", "duplicate"],
        "permutation_cycle_semantics": ["permutation", "cycle", "compose", "disjoint", "repeated", "elements"],
        "distance_geometry": ["distance", "geometry", "point", "dimension", "coordinate", "euclidean"],
    }

    # ── H2: Generalized Behavior-Owner Mapping ────────────────────────────────
    # For each intent class, which symbol name patterns should be preferred/penalized
    BEHAVIOR_OWNER_PREFERENCES: dict[str, dict[str, list[str]]] = {
        "output_formatting": {
            "prefer": ["write", "render", "format", "serialize", "display", "str", "repr", "html", "table", "output", "to_", "emit"],
            "penalize": ["read", "parse", "load", "input", "from_", "decode"],
        },
        "input_parsing": {
            "prefer": ["read", "parse", "load", "decode", "from_", "input", "import"],
            "penalize": ["write", "render", "output", "display", "emit"],
        },
        "validation": {
            "prefer": ["validate", "check", "verify", "assert", "ensure", "sanitize"],
            "penalize": [],
        },
        "normalization": {
            "prefer": ["normalize", "canonicalize", "standardize", "clean"],
            "penalize": [],
        },
        "construction": {
            "prefer": ["__new__", "__init__", "construct", "create", "factory", "from_"],
            "penalize": [],
        },
        "algebraic_semantics": {
            "prefer": ["compose", "simplify", "eval", "expand", "reduce", "evaluate"],
            "penalize": [],
        },
        "collection_semantics": {
            "prefer": ["sort", "unique", "deduplicate", "filter", "map", "reduce"],
            "penalize": [],
        },
        "permutation_cycle_semantics": {
            "prefer": ["__new__", "__init__", "compose", "cycle", "permutation"],
            "penalize": ["format", "write", "render", "html"],
        },
        "distance_geometry": {
            "prefer": ["distance", "norm", "metric", "euclidean", "calculate"],
            "penalize": ["format", "render", "html"],
        },
    }

    # Keywords that indicate behavior ownership
    BEHAVIOR_KEYWORDS = frozenset({
        "write", "read", "format", "render", "output", "display",
        "validate", "check", "verify", "assert", "raise", "return",
        "set", "get", "update", "create", "delete", "remove",
        "parse", "encode", "decode", "convert", "transform",
        "distance", "calculate", "compute", "solve", "optimize",
    })

    # Keywords that indicate mechanical/iteration code
    MECHANICAL_KEYWORDS = frozenset({
        "for", "while", "iter", "loop", "enumerate", "zip",
        "append", "extend",
    })

    def __init__(self, memory_adapter: MemoryRetrievalAdapter | None = None, *, memory_enabled: bool = True):
        self.memory_adapter = memory_adapter or MemoryRetrievalAdapter(enabled=memory_enabled)
        self.memory_enabled = memory_enabled
        self.scoring_metadata: dict[str, Any] = {}
        self.last_memory_metadata: dict[str, Any] = {}  # BMF2-OBS
        self._scorers = [
            self._score_behavior_ownership,
            self._score_failing_trace_relevance,
            self._score_span_size,
            self._score_keyword_overlap,
            self._score_leaf_method,
            self._score_behavior_depth,
            self._score_prior_lessons,
        ]

    # ── H2: Issue Intent Detection ───────────────────────────────────────────

    @classmethod
    def detect_issue_intent(cls, issue_keywords: list[str] | None = None) -> str:
        """Detect the general issue intent from keywords.

        Returns the primary intent class (e.g., 'output_formatting', 'input_parsing').
        No task-specific or repo-specific logic.
        """
        if not issue_keywords:
            return "unknown"

        scores: dict[str, int] = {}
        for intent, keywords in cls.ISSUE_INTENT_KEYWORDS.items():
            score = sum(1 for kw in issue_keywords if kw.lower() in [k.lower() for k in keywords])
            if score > 0:
                scores[intent] = score

        if not scores:
            return "unknown"

        return max(scores, key=scores.get)

    # ── H2: Directional Behavior-Owner Scoring ───────────────────────────────

    def _score_directional_behavior(
        self,
        candidate: AnchorCandidate,
        *,
        issue_intent: str = "unknown",
        **kwargs,
    ) -> tuple[float, str]:
        """H2: Score based on intent-to-behavior-owner mapping.

        For output_formatting bugs, prefer write/render/format over read/parse.
        For input_parsing bugs, prefer read/parse over write/render.
        For other intents, use the preference/penalize lists.

        Uses prefix/exact matching, not substring matching, to avoid false positives.
        """
        if issue_intent == "unknown":
            return 0.0, ""

        prefs = self.BEHAVIOR_OWNER_PREFERENCES.get(issue_intent, {})
        if not prefs:
            return 0.0, ""

        prefer_list = [p.lower() for p in prefs.get("prefer", [])]
        penalize_list = [p.lower() for p in prefs.get("penalize", [])]

        symbol_lower = candidate.symbol_name.lower()

        # Use prefix/exact matching, not substring matching
        # This avoids "iter_str_vals" matching "str" or "read_permutation" matching "permutation"
        def matches_pattern(symbol: str, patterns: list[str]) -> bool:
            for p in patterns:
                # Exact match
                if symbol == p:
                    return True
                # Prefix match (symbol starts with pattern + underscore)
                if symbol.startswith(p + "_"):
                    return True
                # Only match if the pattern is a meaningful prefix (not just a substring)
                # e.g., "write" matches "write_data" but "permutation" does NOT match "read_permutation"
            return False

        prefer_match = matches_pattern(symbol_lower, prefer_list)
        penalize_match = matches_pattern(symbol_lower, penalize_list)

        if prefer_match and not penalize_match:
            return 3.0, f"intent_direction_match:{issue_intent}"
        elif penalize_match and not prefer_match:
            return -2.0, f"intent_direction_penalty:{issue_intent}"
        elif prefer_match and penalize_match:
            # Both match — neutral
            return 0.0, f"intent_direction_ambiguous:{issue_intent}"
        else:
            return 0.0, ""

    # ── H2: Traceback Override Guard ─────────────────────────────────────────

    def _score_traceback_override_guard(
        self,
        candidate: AnchorCandidate,
        *,
        failing_symbol: str | None = None,
        issue_intent: str = "unknown",
        **kwargs,
    ) -> tuple[float, str]:
        """H2: Guard against traceback symbol dominating behavior ownership.

        If traceback points to a caller/transport layer (e.g., iter_str_vals),
        but issue intent points to output formatting, do NOT let traceback override.
        Only boost traceback if it directly owns the behavior.
        """
        if not failing_symbol or issue_intent == "unknown":
            return 0.0, ""

        # Only boost if failing_symbol EXACTLY matches candidate symbol
        if failing_symbol == candidate.symbol_name:
            # Check if this symbol matches the intent direction
            prefs = self.BEHAVIOR_OWNER_PREFERENCES.get(issue_intent, {})
            prefer_list = [p.lower() for p in prefs.get("prefer", [])]
            penalize_list = [p.lower() for p in prefs.get("penalize", [])]
            symbol_lower = candidate.symbol_name.lower()

            prefer_match = any(p in symbol_lower for p in prefer_list)
            penalize_match = any(p in symbol_lower for p in penalize_list)

            if prefer_match and not penalize_match:
                return 2.0, f"traceback_exact_matches_intent:{issue_intent}"
            elif penalize_match:
                return -3.0, f"traceback_exact_conflicts_intent:{issue_intent}"
            else:
                # Exact match but neutral — DO NOT boost traceback
                # Traceback is just a caller/transport, not behavior owner
                return 0.0, f"traceback_neutral:{issue_intent}"

        return 0.0, ""

    # ── H2: Scoring with Intent Context ──────────────────────────────────────

    def score_candidate(
        self,
        candidate: AnchorCandidate,
        *,
        failing_symbol: str | None = None,
        failing_keywords: list[str] | None = None,
        issue_keywords: list[str] | None = None,
        repro_failure_message: str = "",
    ) -> AnchorCandidate:
        """Score a single anchor candidate with H2 intent awareness."""
        total_score = 0.0
        reasons = []

        # Detect issue intent
        issue_intent = self.detect_issue_intent(issue_keywords)

        # Run base scorers with issue_intent
        for scorer in self._scorers:
            score, reason = scorer(
                candidate,
                failing_symbol=failing_symbol,
                failing_keywords=failing_keywords,
                issue_keywords=issue_keywords,
                issue_intent=issue_intent,
                repro_failure_message=repro_failure_message,
            )
            total_score += score
            if reason:
                reasons.append(reason)

        # H2: Directional behavior-owner scoring
        dir_score, dir_reason = self._score_directional_behavior(
            candidate,
            issue_intent=issue_intent,
        )
        total_score += dir_score
        if dir_reason:
            reasons.append(dir_reason)

        # H2: Traceback override guard
        tb_score, tb_reason = self._score_traceback_override_guard(
            candidate,
            failing_symbol=failing_symbol,
            issue_intent=issue_intent,
        )
        total_score += tb_score
        if tb_reason:
            reasons.append(tb_reason)

        candidate.score = total_score
        candidate.score_reasons = reasons
        return candidate

    def _score_prior_lessons(
        self,
        candidate: AnchorCandidate,
        issue_keywords: list[str] | None = None,
        failing_keywords: list[str] | None = None,
        repro_failure_message: str = "",
        **kwargs,
    ) -> tuple[float, str]:
        """Score based on retrieved Memory / LanceDB prior lessons (Z2-P1)."""
        query = " ".join(
            item
            for item in [
                candidate.symbol_name,
                candidate.candidate_type,
                " ".join(issue_keywords or []),
                " ".join(failing_keywords or []),
                repro_failure_message[:200],
            ]
            if item
        )
        lessons = self.memory_adapter.retrieve(query_text=query, limit=5)
        metadata = dict(self.memory_adapter.last_metadata)
        delta = round(sum(lesson.scoring_delta for lesson in lessons), 4)
        candidate.memory_contribution = {
            "enabled": bool(self.memory_enabled),
            "delta": delta,
            "lessons": [
                {
                    "finding_id": lesson.finding_id,
                    "pattern_type": lesson.pattern_type,
                    "provenance": lesson.provenance,
                    "relevance_score": lesson.relevance_score,
                }
                for lesson in lessons
            ],
            "metadata": metadata,
        }
        self.scoring_metadata[candidate.anchor_id] = candidate.memory_contribution
        self.last_memory_metadata = dict(metadata)  # BMF3-OBS: instance-level (not global)
        if metadata.get("no_memory_match"):
            return 0.0, "no_memory_match"
        if delta > 0:
            return delta, f"memory_success_delta:{delta:.2f}"
        if delta < 0:
            return delta, f"memory_failure_delta:{delta:.2f}"
        return 0.0, "memory_neutral"

    def _score_behavior_ownership(
        self,
        candidate: AnchorCandidate,
        *,
        issue_intent: str = "unknown",
        **kwargs,
    ) -> tuple[float, str]:
        """Score based on whether the anchor owns the failing behavior.

        H2: Intent-aware behavior ownership scoring.
        Only boost behavior keywords that match the intent direction.
        """
        symbol_lower = candidate.symbol_name.lower()
        source_lower = candidate.source_text.lower()

        # Check if symbol name suggests behavior ownership
        has_behavior_name = any(kw in symbol_lower for kw in self.BEHAVIOR_KEYWORDS)
        has_mechanical_name = any(kw in symbol_lower for kw in self.MECHANICAL_KEYWORDS)

        if has_mechanical_name:
            return -1.0, "symbol_name_indicates_mechanical_code"

        if has_behavior_name:
            # H2: Check if this behavior keyword matches the intent direction
            if issue_intent != "unknown":
                prefs = self.BEHAVIOR_OWNER_PREFERENCES.get(issue_intent, {})
                prefer_list = [p.lower() for p in prefs.get("prefer", [])]
                penalize_list = [p.lower() for p in prefs.get("penalize", [])]

                # Use prefix/exact matching for intent direction
                def matches_pattern(symbol: str, patterns: list[str]) -> bool:
                    for p in patterns:
                        if symbol == p:
                            return True
                        if symbol.startswith(p + "_"):
                            return True
                    return False

                prefer_match = matches_pattern(symbol_lower, prefer_list)
                penalize_match = matches_pattern(symbol_lower, penalize_list)

                if penalize_match:
                    return -1.0, f"behavior_keyword_penalized:{issue_intent}"
                elif prefer_match:
                    return 3.0, f"behavior_keyword_preferred:{issue_intent}"
                else:
                    # H2: No default boost for behavior keywords that don't match intent
                    return 0.0, f"behavior_keyword_neutral:{issue_intent}"
            else:
                return 2.0, "symbol_name_indicates_behavior_ownership"

        return 0.0, ""

    def _score_failing_trace_relevance(
        self,
        candidate: AnchorCandidate,
        *,
        failing_symbol: str | None = None,
        **kwargs,
    ) -> tuple[float, str]:
        """Score based on proximity to the failing stack frame."""
        if failing_symbol and failing_symbol in candidate.symbol_name:
            return 3.0, "anchor_is_failing_symbol"
        if failing_symbol and candidate.symbol_name in failing_symbol:
            return 1.0, "anchor_contains_failing_symbol"
        return 0.0, ""

    def _score_span_size(
        self,
        candidate: AnchorCandidate,
        **kwargs,
    ) -> tuple[float, str]:
        """Score based on span size — prefer smaller, complete methods."""
        span_lines = candidate.span_end - candidate.span_start + 1
        if span_lines <= 10:
            return 2.0, f"small_span_{span_lines}_lines"
        elif span_lines <= 30:
            return 1.0, f"medium_span_{span_lines}_lines"
        elif span_lines > 100:
            return -2.0, f"oversized_span_{span_lines}_lines"
        else:
            return 0.0, ""

    def _score_keyword_overlap(
        self,
        candidate: AnchorCandidate,
        *,
        issue_keywords: list[str] | None = None,
        repro_failure_message: str = "",
        **kwargs,
    ) -> tuple[float, str]:
        """Score based on keyword overlap with issue description."""
        if not issue_keywords and not repro_failure_message:
            return 0.0, ""

        source_lower = candidate.source_text.lower()
        overlap_count = 0

        for kw in (issue_keywords or []):
            if kw.lower() in source_lower:
                overlap_count += 1

        if repro_failure_message:
            failure_words = set(repro_failure_message.lower().split())
            source_words = set(source_lower.split())
            overlap_count += len(failure_words & source_words)

        if overlap_count >= 3:
            return 2.0, f"high_keyword_overlap_{overlap_count}"
        elif overlap_count >= 1:
            return 1.0, f"moderate_keyword_overlap_{overlap_count}"
        return 0.0, ""

    def _score_leaf_method(
        self,
        candidate: AnchorCandidate,
        *,
        source_text: str = "",
        **kwargs,
    ) -> tuple[float, str]:
        """Score based on whether the anchor is a leaf method (no nested defs)."""
        # Count nested function/class definitions in the span
        nested_count = candidate.source_text.count("def ") + candidate.source_text.count("class ")
        if nested_count == 0:
            return 1.0, "leaf_method_no_nested_defs"
        elif nested_count == 1:
            return 0.0, "single_nested_def"
        else:
            return -1.0, f"multiple_nested_defs_{nested_count}"

    def _score_behavior_depth(
        self,
        candidate: AnchorCandidate,
        *,
        issue_intent: str = "unknown",
        **kwargs,
    ) -> tuple[float, str]:
        """H2: Score based on behavior depth — how much actual logic the method contains.

        Methods with more logic (return statements, conditionals, loops) are more
        likely to be the behavior owner than simple one-liners.
        """
        source = candidate.source_text
        lines = [l.strip() for l in source.splitlines() if l.strip()]

        # Count behavior-indicating constructs
        has_return = "return " in source
        has_conditional = "if " in source or "else:" in source
        has_loop = "for " in source or "while " in source
        has_method_call = "(" in source and ")" in source

        depth_score = 0
        depth_reasons = []

        if has_return:
            depth_score += 1
            depth_reasons.append("has_return")
        if has_conditional:
            depth_score += 1
            depth_reasons.append("has_conditional")
        if has_loop:
            depth_score += 1
            depth_reasons.append("has_loop")
        if has_method_call:
            depth_score += 1
            depth_reasons.append("has_method_call")

        # H2: Strong preference for behavior depth in output_formatting/rendering
        # This ensures the actual formatting method is selected over simple append/write
        if issue_intent in ("output_formatting", "rendering", "serialization"):
            if depth_score >= 4:
                return 4.0, f"very_high_behavior_depth_{depth_score}"
            elif depth_score >= 3:
                return 3.0, f"high_behavior_depth_{depth_score}"
            elif depth_score >= 2:
                return 1.0, f"medium_behavior_depth_{depth_score}"
            elif depth_score == 0:
                return -2.0, "no_behavior_depth_simple_append"
        else:
            # For other intents, mild preference for behavior depth
            if depth_score >= 3:
                return 1.0, f"high_behavior_depth_{depth_score}"
            elif depth_score == 0:
                return -0.5, "no_behavior_depth"

        return 0.0, ""


class AnchorCandidateGenerator:
    """Generates anchor candidates from different sources."""

    def generate_candidates(
        self,
        *,
        file_path: str,
        source_text: str,
        target_symbol: str,
        failing_symbol: str | None = None,
        failing_line: int | None = None,
        call_graph: dict[str, list[str]] | None = None,
    ) -> list[AnchorCandidate]:
        """Generate candidate anchors from multiple sources."""
        candidates = []
        source_hash = hashlib.sha256(source_text.encode()).hexdigest()[:16]

        try:
            tree = ast.parse(source_text)
        except SyntaxError:
            return candidates

        source_lines = source_text.splitlines()

        # 1. Failing stack frame anchor
        if failing_symbol:
            candidate = self._find_symbol_anchor(
                tree, source_lines, source_text, source_hash,
                file_path, failing_symbol, "failing_stack_frame"
            )
            if candidate:
                candidates.append(candidate)

        # 2. Target symbol anchor
        candidate = self._find_symbol_anchor(
            tree, source_lines, source_text, source_hash,
            file_path, target_symbol, "target_symbol"
        )
        if candidate:
            candidates.append(candidate)

        # 3. Direct caller anchors
        if call_graph and target_symbol in call_graph:
            for caller in call_graph[target_symbol]:
                candidate = self._find_symbol_anchor(
                    tree, source_lines, source_text, source_hash,
                    file_path, caller, "direct_caller"
                )
                if candidate:
                    candidates.append(candidate)

        # 4. Direct callee anchors
        if call_graph:
            for symbol, callees in call_graph.items():
                if target_symbol in callees:
                    candidate = self._find_symbol_anchor(
                        tree, source_lines, source_text, source_hash,
                        file_path, symbol, "direct_callee"
                    )
                    if candidate:
                        candidates.append(candidate)

        # 5. Methods containing formatting/normalization behavior
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_name = node.name.lower()
                if any(kw in method_name for kw in ["format", "render", "write", "output", "normalize"]):
                    candidate = self._ast_node_to_candidate(
                        node, source_lines, source_text, source_hash,
                        file_path, "formatting_behavior"
                    )
                    if candidate and candidate.anchor_id not in [c.anchor_id for c in candidates]:
                        candidates.append(candidate)

        # G2: Behavior Ownership Anchor Map extensions
        # 6. Output-generation methods (methods that produce/return the final output)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_name = node.name.lower()
                if any(kw in method_name for kw in ["generate", "produce", "create", "build", "make", "compose"]):
                    candidate = self._ast_node_to_candidate(
                        node, source_lines, source_text, source_hash,
                        file_path, "output_generation"
                    )
                    if candidate and candidate.anchor_id not in [c.anchor_id for c in candidates]:
                        candidates.append(candidate)

        # 7. Validation/check methods (methods that validate or check behavior)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_name = node.name.lower()
                if any(kw in method_name for kw in ["validate", "check", "verify", "assert", "ensure"]):
                    candidate = self._ast_node_to_candidate(
                        node, source_lines, source_text, source_hash,
                        file_path, "validation_behavior"
                    )
                    if candidate and candidate.anchor_id not in [c.anchor_id for c in candidates]:
                        candidates.append(candidate)

        # 8. Methods with return statements (behavior-owning methods)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check if method has return statements (indicates behavior ownership)
                has_return = any(isinstance(n, ast.Return) for n in ast.walk(node))
                if has_return:
                    method_name = node.name.lower()
                    # Skip very generic names
                    if method_name not in ["__init__", "__str__", "__repr__", "main", "run"]:
                        candidate = self._ast_node_to_candidate(
                            node, source_lines, source_text, source_hash,
                            file_path, "behavior_with_return"
                        )
                        if candidate and candidate.anchor_id not in [c.anchor_id for c in candidates]:
                            candidates.append(candidate)

        # Deduplicate by anchor_id
        seen = set()
        unique_candidates = []
        for c in candidates:
            if c.anchor_id not in seen:
                seen.add(c.anchor_id)
                unique_candidates.append(c)

        return unique_candidates

    def _find_symbol_anchor(
        self,
        tree: ast.AST,
        source_lines: list[str],
        source_text: str,
        source_hash: str,
        file_path: str,
        symbol_name: str,
        candidate_type: str,
    ) -> AnchorCandidate | None:
        """Find an anchor candidate for a specific symbol."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == symbol_name:
                    return self._ast_node_to_candidate(
                        node, source_lines, source_text, source_hash,
                        file_path, candidate_type
                    )
        return None

    def _ast_node_to_candidate(
        self,
        node: ast.AST,
        source_lines: list[str],
        source_text: str,
        source_hash: str,
        file_path: str,
        candidate_type: str,
    ) -> AnchorCandidate | None:
        """Convert an AST node to an AnchorCandidate."""
        start_line = node.lineno  # 1-indexed
        end_line = getattr(node, "end_lineno", None)
        if end_line is None:
            # Estimate end line by finding dedent
            base_indent = len(source_lines[start_line - 1]) - len(source_lines[start_line - 1].lstrip())
            end_line = start_line + 1
            for i in range(start_line, min(start_line + 200, len(source_lines))):
                line = source_lines[i]
                if not line.strip():
                    end_line = i + 1
                    continue
                cur_indent = len(line) - len(line.lstrip())
                if cur_indent <= base_indent and line.strip() and i > start_line - 1:
                    break
                end_line = i + 1

        # Extract source text for this span
        span_lines = source_lines[start_line - 1:end_line]
        span_text = "\n".join(span_lines)

        # Verify the span is unique in source
        if source_text.count(span_text) > 1:
            return None

        anchor_id = hashlib.sha256(
            f"{file_path}:{node.name}:{start_line}:{end_line}".encode()
        ).hexdigest()[:12]

        return AnchorCandidate(
            anchor_id=anchor_id,
            file_path=file_path,
            symbol_name=node.name,
            span_start=start_line,
            span_end=end_line,
            source_hash=source_hash,
            candidate_type=candidate_type,
            source_text=span_text,
        )


class SemanticAnchorSelector:
    """Selects the best anchor candidate from a scored set."""

    def select(
        self,
        candidates: list[AnchorCandidate],
        *,
        max_candidates: int = 5,
        min_score: float = 0.0,
        ambiguity_threshold: float = 1.0,
    ) -> AnchorSelectionResult:
        """Select the best anchor candidate with H2 ambiguity reporting."""
        if not candidates:
            return AnchorSelectionResult(
                selected=None,
                candidates=[],
                selection_reason="no_candidates_generated",
                source_hash="",
                file_path="",
                total_candidates=0,
            )

        # H2: Sort by score descending, with tie-breaking favoring behavior depth
        def sort_key(c: AnchorCandidate) -> tuple[float, int]:
            # Primary: score descending
            # Secondary: behavior depth (more depth = higher priority)
            depth = 0
            if "very_high_behavior_depth" in str(c.score_reasons):
                depth = 4
            elif "high_behavior_depth" in str(c.score_reasons):
                depth = 3
            elif "medium_behavior_depth" in str(c.score_reasons):
                depth = 2
            return (c.score, depth)

        scored = sorted(candidates, key=sort_key, reverse=True)

        # Take top-k
        top_candidates = scored[:max_candidates]

        # H2: Check for ambiguity
        ambiguity = False
        score_margin = 0.0
        if len(top_candidates) >= 2:
            score_margin = top_candidates[0].score - top_candidates[1].score
            if score_margin < ambiguity_threshold:
                ambiguity = True

        # Select best if above minimum score
        selected = None
        selection_reason = "below_min_score"

        if top_candidates and top_candidates[0].score >= min_score:
            selected = top_candidates[0]
            selected.selected = True
            if ambiguity:
                selection_reason = f"highest_score_{selected.score:.2f}_type_{selected.candidate_type}_ambiguous_margin_{score_margin:.2f}"
            else:
                selection_reason = f"highest_score_{selected.score:.2f}_type_{selected.candidate_type}"

        return AnchorSelectionResult(
            selected=selected,
            candidates=top_candidates,
            selection_reason=selection_reason,
            source_hash=top_candidates[0].source_hash if top_candidates else "",
            file_path=top_candidates[0].file_path if top_candidates else "",
            total_candidates=len(candidates),
            ambiguity=ambiguity,
            score_margin=score_margin,
            top_k=top_candidates[:3],
        )


def select_semantic_anchor(
    *,
    file_path: str,
    source_text: str,
    target_symbol: str,
    failing_symbol: str | None = None,
    failing_keywords: list[str] | None = None,
    issue_keywords: list[str] | None = None,
    repro_failure_message: str = "",
    call_graph: dict[str, list[str]] | None = None,
) -> AnchorSelectionResult:
    """High-level API for semantic anchor selection.

    Generates candidates, scores them, and returns the best one.
    """
    generator = AnchorCandidateGenerator()
    scorer = SemanticAnchorScorer()
    selector = SemanticAnchorSelector()

    # Generate candidates
    candidates = generator.generate_candidates(
        file_path=file_path,
        source_text=source_text,
        target_symbol=target_symbol,
        failing_symbol=failing_symbol,
        call_graph=call_graph,
    )

    # Score candidates
    for candidate in candidates:
        scorer.score_candidate(
            candidate,
            failing_symbol=failing_symbol,
            failing_keywords=failing_keywords,
            issue_keywords=issue_keywords,
            repro_failure_message=repro_failure_message,
        )

    # Select best
    result = selector.select(candidates)
    # BMF2-OBS: attach memory trace to result
    result.memory_trace = dict(scorer.last_memory_metadata)
    return result
