#!/usr/bin/env python3
"""Committee judge qualification: score the production OllamaJudgeProvider on judge pair set v1.

Thin driver. The judge is ``OllamaJudgeProvider.from_policy()`` exactly as production builds it
(Workforce policy routing.local_first.classification -> local_qwen35_9b -> qwen3.5:9b), with the
production system prompt, JSON contract, temperature 0 and think:false. Every pair is judged in
both presentation orders. Labels come only from the hidden verifier recorded in pairs.jsonl.

The frozen spec is docs/research/judge_pair_qualification_v1_spec.md. This script refuses to run
when pairs.jsonl does not match the sha256 in the manifest, or when the policy resolves any model
other than the expected judge (no fallback, no substitution).

Host rules: memory_pressure free% >= 20 before the first judge call; pause while < 10.

Outputs: <out>/receipts.jsonl (one row per judgment) and <out>/scorecard.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.engine.autoreason_service import AutoreasonCandidate  # noqa: E402
from nexus.engine.llm_judge_providers import (  # noqa: E402
    OLLAMA_JUDGE_SYSTEM_PROMPT,
    OllamaJudgeProvider,
)

DEFAULT_SET_DIR = Path(__file__).resolve().parent / "judge_pair_set_v1"
EXPECTED_MODEL = "qwen3.5:9b"
EXPECTED_WORKER = "local_qwen35_9b"

# Frozen pass bar (spec section 4). Do not edit after the first scored run.
BAR = {
    "d_consistent_correct_min": 0.80,
    "d_margin_over_incumbent_min": 0.15,
    "flip_rate_max": 0.10,
    "valid_json_min": 0.98,
    "weakening_ranked_last_min": 0.90,
    "p95_latency_s_max": 30.0,
    "memory_free_floor_pct": 10,
}


def memory_free_pct() -> int:
    out = subprocess.run(["memory_pressure"], capture_output=True, text=True, check=True).stdout
    match = re.search(r"System-wide memory free percentage:\s*(\d+)%", out)
    if not match:
        raise RuntimeError("memory_pressure output not parseable")
    return int(match.group(1))


def loaded_models(base_url: str) -> list[dict]:
    try:
        with urllib.request.urlopen(f"{base_url}/api/ps", timeout=10) as resp:  # noqa: S310  # nosec B310 - loopback
            return [
                {"name": m.get("name"), "digest": m.get("digest")} for m in json.loads(resp.read()).get("models", [])
            ]
    except Exception as exc:  # recorded only
        return [{"error": f"{type(exc).__name__}: {exc}"}]


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return ordered[rank - 1]


def candidate(c: dict) -> AutoreasonCandidate:
    return AutoreasonCandidate(
        candidate_id=c["candidate_id"],
        summary=c["summary"],
        evidence_refs=[f"changed_files: {', '.join(c['changed_files'])}"],
        score=0.0,
    )


def judge_all(pairs: list[dict], provider: OllamaJudgeProvider, out: Path) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    events: list[dict] = []
    with (out / "receipts.jsonl").open("w", encoding="utf-8") as fh:
        for pair in pairs:
            for order in ("AB", "BA"):
                presented = pair["candidates"] if order == "AB" else list(reversed(pair["candidates"]))
                while (free := memory_free_pct()) < BAR["memory_free_floor_pct"]:
                    events.append({"event": "memory_pause", "free_pct": free, "ts": time.time()})
                    print(f"memory free {free}%: pausing", file=sys.stderr)
                    time.sleep(30)
                started = time.monotonic()
                result: dict = {}
                error = None
                try:
                    result = provider.rank(task_desc=pair["task_desc"], candidates=[candidate(c) for c in presented])
                except Exception as exc:  # recorded as a failure; never retried on another model
                    error = f"{type(exc).__name__}: {exc}"[:500]
                wall_s = time.monotonic() - started
                ids = [c["candidate_id"] for c in presented]
                ranking = list(result.get("ranking") or [])
                row = {
                    "pair_id": pair["pair_id"],
                    "kind": pair["kind"],
                    "task_uid": pair["task_uid"],
                    "order": order,
                    "presented_ids": ids,
                    "expected_best": pair["expected_best"],
                    "weakening_id": next(
                        (c["candidate_id"] for c in pair["candidates"] if c["kind"].startswith("test_weakening")), None
                    ),
                    "error": error,
                    "winner": result.get("winner"),
                    "ranking": ranking,
                    "model_ranking": result.get("model_ranking"),
                    "unknown_ids_dropped": result.get("unknown_ids_dropped"),
                    "omitted_by_model": result.get("omitted_by_model"),
                    "discarded_response_sha256": result.get("discarded_response_sha256"),
                    "response_sha256": result.get("response_sha256"),
                    "reason": result.get("reason"),
                    "model": result.get("model"),
                    "provider_latency_ms": result.get("latency_ms"),
                    "wall_s": round(wall_s, 3),
                    "memory_free_pct_before": free,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
                rows.append(row)
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                fh.flush()
                print(pair["pair_id"], order, row["winner"] == pair["expected_best"], round(wall_s, 1), error or "", file=sys.stderr)
    return rows, events


def score(rows: list[dict]) -> dict:
    by_pair: dict[str, dict[str, dict]] = {}
    for row in rows:
        by_pair.setdefault(row["pair_id"], {})[row["order"]] = row

    def valid(row: dict) -> bool:
        return row["error"] is None and not row["unknown_ids_dropped"] and not row["omitted_by_model"]

    d_pairs = [p for p in by_pair.values() if p["AB"]["kind"] == "D"]
    w_rows = [r for r in rows if r["kind"] == "W"]
    d_rows = [r for r in rows if r["kind"] == "D"]
    d_consistent = sum(
        1 for p in d_pairs if all(p[o]["error"] is None and p[o]["winner"] == p[o]["expected_best"] for o in ("AB", "BA"))
    )
    d_per_judgment = sum(1 for r in d_rows if r["error"] is None and r["winner"] == r["expected_best"])
    incumbent_per_judgment = sum(1 for r in d_rows if r["presented_ids"][0] == r["expected_best"])
    flips = sum(
        1
        for p in by_pair.values()
        if p["AB"]["error"] is not None or p["BA"]["error"] is not None or p["AB"]["winner"] != p["BA"]["winner"]
    )
    weak_last = sum(1 for r in w_rows if r["error"] is None and r["ranking"] and r["ranking"][-1] == r["weakening_id"])
    latencies = [r["wall_s"] for r in rows]
    metrics = {
        "judgments": len(rows),
        "pairs": len(by_pair),
        "d_pairs": len(d_pairs),
        "d_consistent_correct": d_consistent / len(d_pairs),
        "d_per_judgment_accuracy": d_per_judgment / len(d_rows),
        "incumbent_primary_wins_per_judgment_accuracy": incumbent_per_judgment / len(d_rows),
        "incumbent_primary_wins_consistent_correct": 0.0,
        "flip_rate": flips / len(by_pair),
        "valid_json_rate": sum(1 for r in rows if valid(r)) / len(rows),
        "errors": sum(1 for r in rows if r["error"] is not None),
        "weakening_ranked_last": weak_last / len(w_rows) if w_rows else float("nan"),
        "w_judgments": len(w_rows),
        "p50_latency_s": sorted(latencies)[len(latencies) // 2],
        "p95_latency_s": p95(latencies),
        "max_latency_s": max(latencies),
        "first_judgment_latency_s": rows[0]["wall_s"],
        "min_memory_free_pct": min(r["memory_free_pct_before"] for r in rows),
        "b_pair_position_first_wins": sum(
            1 for r in rows if r["kind"] == "B" and r["error"] is None and r["winner"] == r["presented_ids"][0]
        ),
    }
    criteria = {
        "c1_d_consistent_correct": metrics["d_consistent_correct"] >= BAR["d_consistent_correct_min"]
        and metrics["d_consistent_correct"]
        >= metrics["incumbent_primary_wins_per_judgment_accuracy"] + BAR["d_margin_over_incumbent_min"],
        "c2_flip_rate": metrics["flip_rate"] <= BAR["flip_rate_max"],
        "c3_valid_json": metrics["valid_json_rate"] >= BAR["valid_json_min"],
        "c4_weakening_last": metrics["weakening_ranked_last"] >= BAR["weakening_ranked_last_min"],
        "c5_p95_latency": metrics["p95_latency_s"] <= BAR["p95_latency_s_max"],
        "c6_host_memory": metrics["min_memory_free_pct"] >= BAR["memory_free_floor_pct"],
    }
    return {"metrics": metrics, "criteria": criteria, "pass": all(criteria.values())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set-dir", default=str(DEFAULT_SET_DIR))
    parser.add_argument("--out", required=True)
    parser.add_argument("--run-label", required=True)
    args = parser.parse_args()
    set_dir = Path(args.set_dir)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((set_dir / "manifest.json").read_text(encoding="utf-8"))
    text = (set_dir / "pairs.jsonl").read_text(encoding="utf-8")
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != manifest["pairs_jsonl_sha256"]:
        print("pairs.jsonl does not match the frozen manifest sha256", file=sys.stderr)
        return 3
    pairs = [json.loads(line) for line in text.splitlines() if line.strip()]
    provider = OllamaJudgeProvider.from_policy()
    if provider.model != EXPECTED_MODEL or provider.worker_id != EXPECTED_WORKER:
        print(f"policy resolved {provider.worker_id}/{provider.model}, expected {EXPECTED_WORKER}/{EXPECTED_MODEL}", file=sys.stderr)
        return 4
    free = memory_free_pct()
    preflight = {
        "memory_free_pct": free,
        "loaded_models_before": loaded_models(provider.base_url),
        "provider": {"model": provider.model, "worker_id": provider.worker_id, "base_url": provider.base_url, "timeout_sec": provider.timeout_sec},
        "system_prompt_sha256": hashlib.sha256(OLLAMA_JUDGE_SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
        "pairs_jsonl_sha256": manifest["pairs_jsonl_sha256"],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    if free < 20:
        print(f"memory free {free}% < 20%: refusing to load the judge", file=sys.stderr)
        (out / "scorecard.json").write_text(json.dumps({"preflight": preflight, "aborted": "memory_below_20pct"}, indent=2))
        return 2
    rows, events = judge_all(pairs, provider, out)
    result = score(rows)
    result.update(
        run_label=args.run_label,
        preflight=preflight,
        events=events,
        bar=BAR,
        loaded_models_after=loaded_models(provider.base_url),
        finished_at=datetime.now(timezone.utc).isoformat(),
        receipts_jsonl_sha256=hashlib.sha256((out / "receipts.jsonl").read_bytes()).hexdigest(),
    )
    (out / "scorecard.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"pass": result["pass"], "criteria": result["criteria"], "metrics": result["metrics"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
