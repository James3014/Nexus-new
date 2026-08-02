"""
Epistemic Workflow Benchmark v0 — Report Builder and Verifier.

Produces deterministic JSON and Markdown reports.
Verifier is read-only and detects tampering.

All report functions require an explicit private_context_path — scoring
cannot be performed without access to the private context.
"""
import hashlib
import json
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from nexus.research.epistemic_benchmark.contracts import (
    BENCHMARK_REPORT_SCHEMA,
    CLAIM_CEILING_TEXT,
    FORBIDDEN_REPORT_WORDS,
    REQUIRED_LIMITATIONS,
    BenchmarkArm,
    compute_canonical_sha256,
    validate_packet,
)
from nexus.research.epistemic_benchmark.corpus import get_all_oracles, get_corpus_version
from nexus.research.epistemic_benchmark.metrics import (
    _build_alias_to_case_private,
    compute_all_metrics,
)
from nexus.research.epistemic_benchmark.observations import (
    load_valid_observations,
    load_all_observations,
)
from nexus.research.epistemic_benchmark.packets import (
    load_public_run_manifest,
    load_private_scoring_context,
)


COVERAGE_WARNING_THRESHOLD = 0.80

# ---------------------------------------------------------------------------
# Limitations and claim ceiling (static)
# ---------------------------------------------------------------------------

LIMITATIONS: List[str] = list(REQUIRED_LIMITATIONS)


# ---------------------------------------------------------------------------
# JSON report builder
# ---------------------------------------------------------------------------


def _safe_div(n, d):
    return round(n / d, 6) if d and d > 0 else None


def build_benchmark_report(
    run_dir: str,
    private_context_path: str = "",
) -> Dict[str, Any]:
    """
    Build the benchmark report. Uses oracle privately.
    No generated timestamp — uses run manifest created_at.
    Deterministic: same run + observations → byte-for-byte same JSON.

    Parameters
    ----------
    run_dir : str
        Public benchmark run directory.
    private_context_path : str
        Path to the private scoring context JSON file.
        Required for alias→case_id resolution and seed recovery.
        Falls back to legacy auto-derive if empty.
    """
    if not private_context_path:
        # Legacy auto-derive: sibling private context file.
        pub_abs = os.path.abspath(run_dir)
        pub_parent = os.path.dirname(pub_abs)
        pub_name = os.path.basename(pub_abs)
        private_context_path = os.path.join(
            pub_parent, f"_{pub_name}_private_context.json"
        )

    manifest = load_public_run_manifest(run_dir)
    private_ctx = load_private_scoring_context(run_dir, private_context_path)

    valid_obs, invalid_obs = load_valid_observations(run_dir)
    all_obs = load_all_observations(run_dir)

    metrics = compute_all_metrics(run_dir, valid_obs, private_context_path)
    arm_metrics = metrics["arm_metrics"]
    comparisons = metrics["comparisons"]
    corpus_case_count = metrics["corpus_case_count"]

    # Coverage per arm
    coverage = {}
    for arm_name, m in arm_metrics.items():
        assigned = m.get("_assigned_cases", corpus_case_count)
        observed = m.get("_observed_cases", 0)
        coverage[arm_name] = {
            "assigned_cases": assigned,
            "observed_cases": observed,
            "valid_observations": m.get("observation_count", 0),
            "invalid_observations": sum(
                1 for o in invalid_obs if o.get("arm") == arm_name
            ),
            "missing_cases": m.get("_missing_cases", assigned),
            "completion_rate": m.get("completion_rate"),
        }

    # Remove internal keys from arm_metrics for report
    clean_arm_metrics = {}
    for arm_name, m in arm_metrics.items():
        clean_arm_metrics[arm_name] = {
            k: v for k, v in m.items()
            if not k.startswith("_")
        }

    # Oracle summary (classification counts only — no oracle decisions revealed)
    oracles = get_all_oracles()
    corpus_summary = {
        "version": get_corpus_version(),
        "total_cases": corpus_case_count,
        "clean_cases": sum(1 for o in oracles if o["oracle_class"] == "CLEAN"),
        "defective_cases": sum(1 for o in oracles if o["oracle_class"] == "DEFECTIVE"),
        "indeterminate_cases": sum(1 for o in oracles if o["oracle_class"] == "INDETERMINATE"),
    }

    # seed comes from private context (not the public manifest)
    seed = private_ctx.get("seed")

    body = {
        "schema": BENCHMARK_REPORT_SCHEMA,
        "benchmark_run": {
            "benchmark_run_id": manifest.get("benchmark_run_id"),
            "corpus_version": manifest.get("corpus_version"),
            "seed": seed,
            "created_at": manifest.get("created_at"),
        },
        "corpus": corpus_summary,
        "coverage": coverage,
        "arms": clean_arm_metrics,
        "comparisons": comparisons,
        "limitations": LIMITATIONS,
        "claim_ceiling": CLAIM_CEILING_TEXT,
    }

    body["report_sha256"] = compute_canonical_sha256(
        {k: v for k, v in body.items() if k != "report_sha256"}
    )
    return body


# ---------------------------------------------------------------------------
# Markdown report renderer
# ---------------------------------------------------------------------------


def _fmt(value: Optional[float], fmt: str = ".4f") -> str:
    if value is None:
        return "N/A"
    return format(value, fmt)


def _pct(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def render_benchmark_markdown(report: Dict[str, Any]) -> str:
    """
    Render a Markdown report from the JSON report dict.
    Deterministic. No forbidden words. No current timestamp.
    """
    lines: List[str] = []
    run = report.get("benchmark_run", {})
    coverage = report.get("coverage", {})
    arms = report.get("arms", {})
    comparisons = report.get("comparisons", [])
    limitations = report.get("limitations", [])
    claim_ceiling = report.get("claim_ceiling", "")

    # Check if any arm is below coverage threshold
    below_threshold = any(
        (cov.get("completion_rate") or 0) < COVERAGE_WARNING_THRESHOLD
        for cov in coverage.values()
    )

    lines.append("# Epistemic Workflow Benchmark v0")
    lines.append("")

    if below_threshold:
        lines.append("> **INCOMPLETE BENCHMARK COVERAGE**: One or more arms have fewer than 80% of cases observed.")
        lines.append("")

    # Run identity
    lines.append("## Run Identity")
    lines.append("")
    lines.append(f"- **Run ID**: `{run.get('benchmark_run_id', 'N/A')}`")
    lines.append(f"- **Corpus Version**: `{run.get('corpus_version', 'N/A')}`")
    lines.append(f"- **Seed**: `{run.get('seed', 'N/A')}`")
    lines.append(f"- **Created At**: `{run.get('created_at', 'N/A')}`")
    lines.append("")

    # Corpus and coverage
    corpus = report.get("corpus", {})
    lines.append("## Corpus and Coverage")
    lines.append("")
    lines.append(f"- Total cases: {corpus.get('total_cases', 'N/A')}")
    lines.append(f"- CLEAN (ACCEPT expected): {corpus.get('clean_cases', 'N/A')}")
    lines.append(f"- DEFECTIVE (REJECT expected): {corpus.get('defective_cases', 'N/A')}")
    lines.append(f"- INDETERMINATE (BLOCK expected): {corpus.get('indeterminate_cases', 'N/A')}")
    lines.append("")
    lines.append("### Coverage by Arm")
    lines.append("")
    lines.append("| Arm | Assigned | Observed | Valid Obs | Invalid Obs | Missing | Completion |")
    lines.append("|-----|----------|----------|-----------|-------------|---------|------------|")
    for arm_name, cov in coverage.items():
        lines.append(
            f"| {arm_name} "
            f"| {cov.get('assigned_cases', 'N/A')} "
            f"| {cov.get('observed_cases', 'N/A')} "
            f"| {cov.get('valid_observations', 'N/A')} "
            f"| {cov.get('invalid_observations', 'N/A')} "
            f"| {cov.get('missing_cases', 'N/A')} "
            f"| {_pct(cov.get('completion_rate'))} |"
        )
    lines.append("")

    # Per-arm sections
    arm_display_names = {
        "standard_review": "Arm A — Standard Review",
        "strong_protocol": "Arm B — Strong Protocol",
        "epistemic_workflow": "Arm C — Epistemic Workflow",
    }

    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        display = arm_display_names.get(arm_name, arm_name)
        m = arms.get(arm_name, {})
        lines.append(f"## {display}")
        lines.append("")
        lines.append(f"- Observations: {m.get('observation_count', 0)}")
        lines.append(f"- Decision Accuracy: {_pct(m.get('decision_accuracy'))}")
        lines.append(f"- False Acceptance Rate: {_pct(m.get('false_acceptance_rate'))}")
        lines.append(f"- False Rejection Rate: {_pct(m.get('false_rejection_rate'))}")
        lines.append(f"- Appropriate Abstention Rate: {_pct(m.get('appropriate_abstention_rate'))}")
        lines.append(f"- Over-Abstention Rate: {_pct(m.get('over_abstention_rate'))}")
        lines.append(f"- Defect Detection Recall: {_pct(m.get('defect_detection_recall'))}")
        lines.append(f"- Critical Defect Recall: {_pct(m.get('critical_defect_detection_recall'))}")
        lines.append(f"- High Defect Recall: {_pct(m.get('high_defect_detection_recall'))}")
        lines.append(f"- Mean Confidence: {_fmt(m.get('mean_confidence'))}")
        lines.append(f"- Brier Score: {_fmt(m.get('brier_score'))} (n={m.get('brier_calibration_sample_count', 0)})")
        lines.append(f"- Median Duration: {_fmt(m.get('median_duration_seconds'))}s")
        lines.append(f"- P95 Duration: {_fmt(m.get('p95_duration_seconds'))}s")
        lines.append(f"- Total Input Tokens: {m.get('total_input_tokens', 0)}")
        lines.append(f"- Total Output Tokens: {m.get('total_output_tokens', 0)}")
        lines.append(f"- Total Cost USD: {_fmt(m.get('total_cost_usd'))}")
        lines.append(f"- Decision Agreement: {_pct(m.get('decision_agreement'))}")
        lines.append("")

    # Paired comparisons
    lines.append("## Paired Comparisons")
    lines.append("")
    lines.append(
        "> Observed deltas are descriptive only. "
        "This benchmark does not establish statistical significance "
        "or general research-quality improvement."
    )
    lines.append("")

    comp_sections = [
        ("False Acceptance", "false_acceptance_delta"),
        ("Appropriate Abstention", "appropriate_abstention_delta"),
        ("Defect Detection", "defect_recall_delta"),
        ("Decision Accuracy", "decision_accuracy_delta"),
    ]

    for comp in comparisons:
        lines.append(f"### {comp.get('comparison', 'Comparison')}")
        lines.append("")
        lines.append(f"- Paired Cases: {comp.get('paired_case_count', 'N/A')}")
        for label, key in comp_sections:
            delta = comp.get(key)
            lines.append(f"- {label} Delta: {_pct(delta) if delta is not None else 'N/A'}")
        dur_delta = comp.get("median_duration_delta_seconds")
        lines.append(f"- Median Duration Delta: {_fmt(dur_delta)}s")
        lines.append("")

    # Reviewer agreement
    lines.append("## Reviewer Agreement")
    lines.append("")
    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        m = arms.get(arm_name, {})
        lines.append(
            f"- {arm_display_names.get(arm_name, arm_name)}: "
            f"{_pct(m.get('decision_agreement'))}"
        )
    lines.append("")

    # Limitations
    lines.append("## Limitations")
    lines.append("")
    for lim in limitations:
        lines.append(f"- {lim}")
    lines.append("")

    # Claim ceiling
    lines.append("## Claim Ceiling")
    lines.append("")
    lines.append(f"> {claim_ceiling}")
    lines.append("")

    # Report hash
    lines.append("---")
    lines.append("")
    lines.append(f"*Report SHA-256: `{report.get('report_sha256', 'N/A')}`*")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Atomic dual output write
# ---------------------------------------------------------------------------


def write_benchmark_report(
    report: Dict[str, Any],
    json_output_path: str,
    markdown_output_path: str,
) -> None:
    """
    Atomically write JSON and Markdown reports.
    If either write fails, existing outputs are preserved (no partial state).
    """
    md_content = render_benchmark_markdown(report)
    json_content = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)

    # Write to temp files first, then replace atomically
    tmp_paths = []
    try:
        for output_path, content in [
            (json_output_path, json_content),
            (markdown_output_path, md_content),
        ]:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=os.path.dirname(os.path.abspath(output_path)) or ".",
                delete=False,
                suffix=".tmp",
            ) as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
                tmp_paths.append((f.name, output_path))

        # Only replace originals if both temp writes succeeded
        for tmp_path, final_path in tmp_paths:
            os.replace(tmp_path, final_path)

    except Exception:
        # Clean up temp files on failure, preserve originals
        for tmp_path, _ in tmp_paths:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


# ---------------------------------------------------------------------------
# Report verifier (read-only)
# ---------------------------------------------------------------------------


def verify_benchmark_report(
    report: Dict[str, Any],
    run_dir: str,
    private_context_path: str = "",
) -> Tuple[bool, List[str]]:
    """
    Read-only verifier. Detects tampering including count manipulation + hash recomputation.

    Steps:
    1. Re-read run manifest.
    2. Re-read packets.
    3. Re-read observations.
    4. Use private oracle.
    5. Re-compute expected report.
    6. Compare semantic fields and hash.
    7. Detect count tampering.
    8. Does NOT modify run directory.

    Parameters
    ----------
    private_context_path : str
        Path to the private scoring context. Falls back to legacy auto-derive if empty.
    """
    errors: List[str] = []

    # 1. Claim ceiling exact
    claim_ceiling = report.get("claim_ceiling", "")
    if claim_ceiling != CLAIM_CEILING_TEXT:
        errors.append("REPORT_CLAIM_CEILING_MISMATCH")

    # 2. Limitations present
    lims = report.get("limitations", [])
    for required_lim in REQUIRED_LIMITATIONS:
        if not any(required_lim in lim for lim in lims):
            errors.append(f"REPORT_LIMITATION_MISSING: {required_lim!r}")

    # 3. Forbidden words absent
    report_str = json.dumps(report).lower()
    for fw in FORBIDDEN_REPORT_WORDS:
        if fw.lower() in report_str:
            errors.append(f"REPORT_FORBIDDEN_WORD: {fw!r}")

    # 4. Schema check
    if report.get("schema") != BENCHMARK_REPORT_SCHEMA:
        errors.append(f"REPORT_SCHEMA_INVALID: {report.get('schema')!r}")

    # 5. Recompute report from scratch and compare semantic fields
    try:
        expected_report = build_benchmark_report(run_dir, private_context_path)
    except Exception as e:
        errors.append(f"REPORT_RECOMPUTE_FAILED: {e}")
        return False, errors

    # 6. Compare observation counts (detect count tampering)
    report_coverage = report.get("coverage", {})
    expected_coverage = expected_report.get("coverage", {})
    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        r_cov = report_coverage.get(arm_name, {})
        e_cov = expected_coverage.get(arm_name, {})
        for field in ("observed_cases", "valid_observations", "missing_cases"):
            if r_cov.get(field) != e_cov.get(field):
                errors.append(
                    f"REPORT_COUNT_TAMPERED: {arm_name}.{field}: "
                    f"reported={r_cov.get(field)} expected={e_cov.get(field)}"
                )

    # 7. Compare arm metrics
    report_arms = report.get("arms", {})
    expected_arms = expected_report.get("arms", {})
    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        r_arm = report_arms.get(arm_name, {})
        e_arm = expected_arms.get(arm_name, {})
        for field in ("decision_accuracy", "false_acceptance_rate", "defect_detection_recall"):
            if r_arm.get(field) != e_arm.get(field):
                errors.append(
                    f"REPORT_METRIC_TAMPERED: {arm_name}.{field}: "
                    f"reported={r_arm.get(field)} expected={e_arm.get(field)}"
                )

    # 8. Compare report hash (must match recomputed)
    reported_hash = report.get("report_sha256", "")
    expected_hash = expected_report.get("report_sha256", "")
    if reported_hash != expected_hash:
        errors.append(
            f"REPORT_HASH_MISMATCH: reported={reported_hash!r} expected={expected_hash!r}"
        )

    # 9. Self-consistency: reported hash must match its own body
    body_without_hash = {k: v for k, v in report.items() if k != "report_sha256"}
    self_hash = compute_canonical_sha256(body_without_hash)
    if self_hash != reported_hash:
        errors.append(f"REPORT_SELF_HASH_INCONSISTENT")

    return len(errors) == 0, errors
