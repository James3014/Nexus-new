#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _load_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("runs"), list):
        return [row for row in payload["runs"] if isinstance(row, dict)]
    raise ValueError(f"Unsupported JSON payload at {path}")


def load_runs(path: str | Path) -> list[dict[str, Any]]:
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(src)
    ext = src.suffix.lower()
    if ext == ".csv":
        return _load_csv(src)
    if ext == ".jsonl":
        return _load_jsonl(src)
    if ext == ".json":
        return _load_json(src)
    raise ValueError(f"Unsupported file extension: {src}")


def _is_solved(row: dict[str, Any]) -> bool:
    semantic_raw = row.get("semantic_status")
    semantic = str(semantic_raw).strip().upper() if semantic_raw is not None else ""
    if semantic and semantic not in {"NONE", "NULL"}:
        return semantic == "VERIFIED"
    status = str(row.get("status", "")).strip().upper()
    if status:
        return status in {"PASS", "SUCCESS"}
    return False


def _is_trust_mismatch(row: dict[str, Any]) -> bool:
    if "report_trust_mismatch" in row:
        return bool(row.get("report_trust_mismatch"))
    # fallback signal for old rows
    return str(row.get("runtime_classification", "")).strip().lower() == "report_causality_defect"


def summarize_runs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {
            "total_runs": 0,
            "solve_rate": 0.0,
            "avg_duration_sec": 0.0,
            "avg_total_tokens": 0.0,
            "avg_model_calls": 0.0,
            "avg_attempt_count": 0.0,
            "trust_mismatch_rate": 0.0,
        }

    solved = sum(1 for row in rows if _is_solved(row))
    semantic_verified = sum(
        1
        for row in rows
        if str(row.get("semantic_status", "")).strip().upper() == "VERIFIED"
    )
    total_duration = sum(
        _as_float(
            row.get(
                "task_duration_sec",
                row.get("duration_sec", row.get("elapsed_sec", row.get("avg_duration_sec", 0.0))),
            ),
            0.0,
        )
        for row in rows
    )
    total_wall_duration = sum(
        _as_float(row.get("wall_duration_sec", row.get("duration_sec", row.get("elapsed_sec", 0.0))), 0.0)
        for row in rows
    )
    total_tokens = sum(_as_float(row.get("total_tokens"), 0.0) for row in rows)
    total_model_calls = sum(_as_int(row.get("model_calls"), 0) for row in rows)
    total_attempts = sum(_as_int(row.get("attempt_count"), 0) for row in rows)
    trust_mismatch = sum(1 for row in rows if _is_trust_mismatch(row))

    return {
        "total_runs": total,
        "solve_rate": round(solved / total, 4),
        "semantic_verified_rate": round(semantic_verified / total, 4),
        "avg_duration_sec": round(total_duration / total, 4),
        "avg_wall_duration_sec": round(total_wall_duration / total, 4),
        "avg_total_tokens": round(total_tokens / total, 2),
        "avg_model_calls": round(total_model_calls / total, 2),
        "avg_attempt_count": round(total_attempts / total, 2),
        "trust_mismatch_rate": round(trust_mismatch / total, 4),
    }


def compare_datasets(label_a: str, rows_a: list[dict[str, Any]], label_b: str, rows_b: list[dict[str, Any]]) -> dict[str, Any]:
    summary_a = summarize_runs(rows_a)
    summary_b = summarize_runs(rows_b)
    delta = {
        "solve_rate_delta": round(summary_b["solve_rate"] - summary_a["solve_rate"], 4),
        "semantic_verified_rate_delta": round(
            summary_b["semantic_verified_rate"] - summary_a["semantic_verified_rate"], 4
        ),
        "avg_duration_sec_delta": round(summary_b["avg_duration_sec"] - summary_a["avg_duration_sec"], 4),
        "avg_wall_duration_sec_delta": round(
            summary_b["avg_wall_duration_sec"] - summary_a["avg_wall_duration_sec"], 4
        ),
        "avg_total_tokens_delta": round(summary_b["avg_total_tokens"] - summary_a["avg_total_tokens"], 2),
        "avg_model_calls_delta": round(summary_b["avg_model_calls"] - summary_a["avg_model_calls"], 2),
        "avg_attempt_count_delta": round(summary_b["avg_attempt_count"] - summary_a["avg_attempt_count"], 2),
        "trust_mismatch_rate_delta": round(summary_b["trust_mismatch_rate"] - summary_a["trust_mismatch_rate"], 4),
    }
    return {
        "a": {"label": label_a, "summary": summary_a},
        "b": {"label": label_b, "summary": summary_b},
        "delta": delta,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Nexus A/B benchmark results.")
    parser.add_argument("file_a", nargs="?", help="Dataset A (.csv/.jsonl/.json)")
    parser.add_argument("file_b", nargs="?", help="Dataset B (.csv/.jsonl/.json)")
    parser.add_argument("--a", dest="file_a_opt", help="Dataset A (.csv/.jsonl/.json)")
    parser.add_argument("--b", dest="file_b_opt", help="Dataset B (.csv/.jsonl/.json)")
    parser.add_argument("--label-a", default="A")
    parser.add_argument("--label-b", default="B")
    parser.add_argument("--output-json", action="store_true")
    parser.add_argument("--output-file", type=str, default="")
    args = parser.parse_args()

    file_a = args.file_a_opt or args.file_a
    file_b = args.file_b_opt or args.file_b
    if not file_a or not file_b:
        parser.error("Both dataset paths are required.")

    rows_a = load_runs(file_a)
    rows_b = load_runs(file_b)
    report = compare_datasets(args.label_a, rows_a, args.label_b, rows_b)

    if args.output_file:
        out_path = Path(args.output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.output_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"--- A/B Comparison: {file_a} vs {file_b} ---")
        print(f"Solve Rate: {report['a']['summary']['solve_rate']:.2%} -> {report['b']['summary']['solve_rate']:.2%} ({report['delta']['solve_rate_delta']:+.2%})")
        print(
            f"Semantic Verified Rate: {report['a']['summary']['semantic_verified_rate']:.2%} -> "
            f"{report['b']['summary']['semantic_verified_rate']:.2%} "
            f"({report['delta']['semantic_verified_rate_delta']:+.2%})"
        )
        print(
            f"Avg Duration: {report['a']['summary']['avg_duration_sec']:.2f}s -> "
            f"{report['b']['summary']['avg_duration_sec']:.2f}s "
            f"({report['delta']['avg_duration_sec_delta']:+.2f}s)"
        )
        print(
            f"Avg Wall Duration: {report['a']['summary']['avg_wall_duration_sec']:.2f}s -> "
            f"{report['b']['summary']['avg_wall_duration_sec']:.2f}s "
            f"({report['delta']['avg_wall_duration_sec_delta']:+.2f}s)"
        )
        print(
            f"Avg Tokens: {report['a']['summary']['avg_total_tokens']:.1f} -> "
            f"{report['b']['summary']['avg_total_tokens']:.1f} "
            f"({report['delta']['avg_total_tokens_delta']:+.1f})"
        )
        print(
            f"Trust Mismatch Rate: {report['a']['summary']['trust_mismatch_rate']:.2%} -> "
            f"{report['b']['summary']['trust_mismatch_rate']:.2%} "
            f"({report['delta']['trust_mismatch_rate_delta']:+.2%})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
