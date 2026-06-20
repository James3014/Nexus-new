"""Strategy probe evaluator with strategy-type-specific evidence probes."""

from .strategy_envelope import StrategyEnvelope


class StrategyProbeEvaluator:
    """Two-layer probe: readiness gates + strategy-type-specific evidence."""

    READINESS_WEIGHTS = {
        "target_file_found": 2,
        "source_snapshot_available": 2,
        "canonical_search_lockable": 3,
        "verifier_available": 2,
        "public_claim_boundary_present": 1,
    }

    def evaluate_readiness(self, envelope: StrategyEnvelope,
                           target_file_exists: bool = True,
                           source_snapshot_present: bool = True,
                           canonical_search_locked: bool = True,
                           verifier_available: bool = True,
                           ) -> dict:
        """Layer A: Hard readiness gates."""
        checks = {
            "target_file_found": target_file_exists,
            "source_snapshot_available": source_snapshot_present,
            "canonical_search_lockable": canonical_search_locked,
            "verifier_available": verifier_available,
            "public_claim_boundary_present": True,
        }

        score = 0
        max_score = sum(self.READINESS_WEIGHTS.values())
        fail_reasons = []
        for name, passed in checks.items():
            if passed:
                score += self.READINESS_WEIGHTS.get(name, 1)
            else:
                fail_reasons.append(name)

        return {
            "readiness_pass": score >= 5,
            "readiness_score": score,
            "readiness_max_score": max_score,
            "readiness_fail_reasons": fail_reasons,
        }

    def evaluate_traceback_first(self, envelope: StrategyEnvelope,
                                  has_traceback: bool = False,
                                  traceback_matches_target: bool = False,
                                  traceback_line_near_canonical: bool = False,
                                  traceback_in_project_frame: bool = False,
                                  ) -> dict:
        """Layer B: traceback_first evidence probes."""
        checks = {
            "traceback_file_matches_target": traceback_matches_target,
            "traceback_line_near_canonical_span": traceback_line_near_canonical,
            "failure_stack_contains_project_frame": traceback_in_project_frame,
            "traceback_available": has_traceback,
        }
        score = sum(3 if v else 0 for v in checks.values())
        max_score = len(checks) * 3
        confidence = score / max_score if max_score > 0 else 0.0

        return {
            "strategy_type": "traceback_first",
            "strategy_evidence_score": score,
            "strategy_evidence_max_score": max_score,
            "strategy_evidence_confidence": confidence,
            "checks": checks,
        }

    def evaluate_symbol_graph_first(self, envelope: StrategyEnvelope,
                                     has_target_symbol: bool = False,
                                     symbol_unique: bool = False,
                                     symbol_in_canonical_span: bool = False,
                                     imports_detected: bool = False,
                                     ) -> dict:
        """Layer B: symbol_graph_first evidence probes."""
        checks = {
            "target_symbol_present": has_target_symbol,
            "target_symbol_unique": symbol_unique,
            "symbol_definition_contains_canonical_span": symbol_in_canonical_span,
            "related_imports_detected": imports_detected,
        }
        score = sum(3 if v else 0 for v in checks.values())
        max_score = len(checks) * 3
        confidence = score / max_score if max_score > 0 else 0.0

        return {
            "strategy_type": "symbol_graph_first",
            "strategy_evidence_score": score,
            "strategy_evidence_max_score": max_score,
            "strategy_evidence_confidence": confidence,
            "checks": checks,
        }

    def evaluate_issue_semantics_first(self, envelope: StrategyEnvelope,
                                        has_issue_summary: bool = False,
                                        has_behavior_delta: bool = False,
                                        keywords_match_target: bool = False,
                                        semantic_category: bool = False,
                                        ) -> dict:
        """Layer B: issue_semantics_first evidence probes."""
        checks = {
            "issue_summary_present": has_issue_summary,
            "expected_behavior_delta_present": has_behavior_delta,
            "issue_keywords_match_target_file": keywords_match_target,
            "semantic_category_detected": semantic_category,
        }
        score = sum(3 if v else 0 for v in checks.values())
        max_score = len(checks) * 3
        confidence = score / max_score if max_score > 0 else 0.0

        return {
            "strategy_type": "issue_semantics_first",
            "strategy_evidence_score": score,
            "strategy_evidence_max_score": max_score,
            "strategy_evidence_confidence": confidence,
            "checks": checks,
        }

    def probe(self, envelope: StrategyEnvelope, **kwargs) -> dict:
        """Legacy interface: combine readiness + evidence."""
        readiness = self.evaluate_readiness(envelope, **kwargs)
        strategy_type = envelope.strategy_source.replace("deterministic_", "")

        if strategy_type == "traceback_first":
            evidence = self.evaluate_traceback_first(envelope)
        elif strategy_type == "symbol_graph_first":
            evidence = self.evaluate_symbol_graph_first(envelope)
        else:
            evidence = self.evaluate_issue_semantics_first(envelope)

        final_score = evidence["strategy_evidence_score"] if readiness["readiness_pass"] else -1

        return {
            "probe_score": final_score,
            "probe_pass": readiness["readiness_pass"],
            "readiness": readiness,
            "evidence": evidence,
        }
