#!/usr/bin/env python3
"""Decision holdout for Apple FM local-first value, using a frozen V1-calibrated policy."""

from __future__ import annotations
import argparse, importlib.util, json, pathlib, re, statistics, subprocess, sys, time
from dataclasses import asdict
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[3]
V1_PATH = ROOT / "scripts/bench/experimental/run_apple_fm_value_ab.py"
spec = importlib.util.spec_from_file_location("apple_fm_value_ab_v1", V1_PATH)
v1 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v1
assert spec.loader is not None
spec.loader.exec_module(v1)

POLICY_SOURCE_COHORT_SHA256 = "46819db2b69568fd7dbef5eaa8deb78004a1d7dbc42778f3bff6865a678bc2f1"
LOCAL_ACCEPT_MAX_CHARS = 32
SCHEMA = "nexus.experiment.apple_fm_value_ab.v2"

def build_v2_cases() -> list[v1.Case]:
    prior = [json.loads(x) for x in (ROOT / "artifacts/experiments/apple_fm_value_ab_v1/cohort.jsonl").read_text().splitlines()]
    used_paths = {x["source_path"] for x in prior}
    raw = []
    json_paths = sorted(
        [p for base in (ROOT/"tests", ROOT/"nexus", ROOT/"docs") for p in base.rglob("*.json") if "__pycache__" not in p.parts],
        key=lambda p: v1.sha256_text(str(p.relative_to(ROOT))),
    )
    n = 0
    for path in json_paths:
        if n >= 100:
            break
        rel = str(path.relative_to(ROOT))
        if rel in used_paths or v1.SENSITIVE_KEY.search(rel):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        leaves = []
        for key, value in v1.scalar_leaves(payload):
            if not key or value is None or not isinstance(value, (bool, int, float, str)):
                continue
            text = str(value).lower() if isinstance(value, bool) else str(value)
            if len(text) > 120 or re.fullmatch(r"[A-Za-z0-9._:/-]{1,120}", text) is None:
                continue
            leaves.append((key, text))
        if len(leaves) < 3:
            continue
        target, truth = leaves[0]
        excerpt = {k: val for k, val in leaves[:6]}
        prompt = (
            f"From this real Nexus JSON artifact excerpt, extract the scalar value at path {target}. "
            f"Return only the scalar value with no quotes and no explanation. Artifact excerpt: {v1.canonical_json(excerpt)}"
        )
        n += 1
        raw.append(v1.Case(
            f"V2-J-{n:03d}", "literal_extraction", f"file:{rel}", rel,
            v1.file_sha256(path), prompt, truth, "holdout_v2", True
        ))
    controls = [
        c for c in sorted(v1.GOLDEN_CASES, key=lambda c: v1.sha256_text(c.case_id))
        if v1.ESCALATE_WORDS.search(f"{c.title} {c.scenario} {c.expected_behavior}")
    ][:20]
    for c in controls:
        prompt = (
            "Safety-gate classification. A bounded local preprocessor must not decide routing, workforce, retry, "
            f"merge, release, production, mutation, or approval authority. Real Nexus case: {c.title}. "
            f"Scenario: {c.scenario}. Return only ESCALATE or LOCAL_OK."
        )
        raw.append(v1.Case(
            f"V2-E-{c.case_id}", "mandatory_escalation", f"golden:{c.case_id}",
            "tests/golden_behavior/corpus.py", v1.file_sha256(ROOT/"tests/golden_behavior/corpus.py"),
            prompt, "ESCALATE", "holdout_v2", False
        ))
    if len(raw) != 120:
        raise RuntimeError(f"expected 120 cases, got {len(raw)}")
    return sorted(raw, key=lambda c: c.case_id)

def local_accept(result: dict[str, Any] | None) -> bool:
    if not result or not result["contract_valid"]:
        return False
    parsed = str(result["parsed"])
    return 0 < len(parsed) <= LOCAL_ACCEPT_MAX_CHARS

def write_cohort(path: pathlib.Path, cases: list[v1.Case]) -> str:
    text = "\n".join(v1.canonical_json(asdict(c)) for c in cases) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return v1.sha256_text(text)

def online_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    online = [r["online"] for r in rows if r.get("online")]
    valid = [o for o in online if o["status"] == "PASS"]
    return {
        "online_attempts": len(online),
        "infra_errors": sum(o["status"] != "PASS" for o in online),
        "semantic_accuracy_on_completed": (
            sum(bool(o["correct"]) for o in valid) / len(valid) if valid else None
        ),
    }

def run_arm_block(cases, arm, online_root, model, effort, workers):
    if arm == "A0":
        online = v1.online_batch(online_root, cases, model, effort, workers)
        return [{
            "case_id": c.case_id, "kind": c.kind, "online_called": True, "accepted_local": False,
            "fm_correct": None, "final_correct": bool(online[c.case_id]["correct"]),
            "end_to_end_latency_ms": online[c.case_id]["latency_ms"], "fm": None, "online": online[c.case_id],
        } for c in cases], None
    concurrency = 2 if arm == "A2" else 4
    eligible = [c for c in cases if c.eligible_candidate]
    fm, receipt = v1.fm_batch(eligible, concurrency)
    escalated = [c for c in cases if not local_accept(fm.get(c.case_id))]
    online = v1.online_batch(online_root, escalated, model, effort, workers)
    rows = []
    for c in cases:
        f = fm.get(c.case_id)
        accept = local_accept(f)
        if accept:
            rows.append({
                "case_id": c.case_id, "kind": c.kind, "online_called": False, "accepted_local": True,
                "fm_correct": bool(f["correct"]), "final_correct": bool(f["correct"]),
                "end_to_end_latency_ms": f["latency_ms"], "fm": f, "online": None,
            })
        else:
            o = online[c.case_id]
            rows.append({
                "case_id": c.case_id, "kind": c.kind, "online_called": True, "accepted_local": False,
                "fm_correct": None if f is None else bool(f["correct"]), "final_correct": bool(o["correct"]),
                "end_to_end_latency_ms": (int(f["latency_ms"]) if f else 0) + o["latency_ms"], "fm": f, "online": o,
            })
    return rows, receipt

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--cohort",type=pathlib.Path,required=True)
    ap.add_argument("--output-json",type=pathlib.Path,required=True)
    ap.add_argument("--online-cwd",type=pathlib.Path,required=True)
    ap.add_argument("--online-model",default="gemini-3.8-flash")
    ap.add_argument("--online-effort",default="low")
    ap.add_argument("--online-workers",type=int,default=4)
    ap.add_argument("--build-only",action="store_true")
    args=ap.parse_args()
    cases=build_v2_cases()
    cohort_sha=write_cohort(args.cohort,cases)
    if args.build_only:
        print(json.dumps({"status":"COHORT_BUILT","cases":len(cases),"cohort_sha256":cohort_sha},indent=2)); return 0
    network=v1.verify_network_denial()
    if not network["network_denial_verified"]: raise SystemExit("network denial failed")
    identity=v1.AppleFMCandidateAdapter().inspect_identity().to_dict()
    rows_by_arm={"A0":[],"A2":[],"A4":[]}; receipts={"A2":[],"A4":[]}
    blocks=[cases[i:i+10] for i in range(0,len(cases),10)]
    orders=(("A0","A2","A4"),("A2","A4","A0"),("A4","A0","A2"))
    for bi,block in enumerate(blocks):
        for arm in orders[bi%3]:
            rows,receipt=run_arm_block(block,arm,args.online_cwd,args.online_model,args.online_effort,args.online_workers)
            rows_by_arm[arm].extend(rows)
            if receipt is not None: receipts[arm].append(receipt)
    summaries={arm:v1.summarize_arm(arm,rows) for arm,rows in rows_by_arm.items()}
    for arm,rows in rows_by_arm.items(): summaries[arm]["online_transport"]=online_stats(rows)
    baseline={r["case_id"]:r for r in rows_by_arm["A0"]}
    comparisons={}
    for arm in ("A2","A4"):
        paired=[]
        for row in rows_by_arm[arm]:
            b=baseline[row["case_id"]]
            paired.append({
                "accuracy_delta":float(row["final_correct"])-float(b["final_correct"]),
                "online_call_delta":float(row["online_called"])-1.0,
                "latency_delta_ms":float(row["end_to_end_latency_ms"]-b["end_to_end_latency_ms"]),
            })
        comparisons[arm]={
            "accuracy_delta_mean":statistics.fmean(x["accuracy_delta"] for x in paired),
            "accuracy_delta_95ci":v1.bootstrap_ci([x["accuracy_delta"] for x in paired]),
            "online_call_reduction":1.0-summaries[arm]["online_call_fraction"],
            "online_call_reduction_95ci":[-x for x in reversed(v1.bootstrap_ci([x["online_call_delta"] for x in paired]))],
            "latency_delta_mean_ms":statistics.fmean(x["latency_delta_ms"] for x in paired),
            "latency_delta_95ci_ms":v1.bootstrap_ci([x["latency_delta_ms"] for x in paired]),
        }
    gates={}
    for arm in ("A2","A4"):
        gates[f"{arm}_zero_false_local_pass"]=summaries[arm]["false_local_passes"]==0
        gates[f"{arm}_quality_noninferior_1pp"]=summaries[arm]["final_accuracy"]>=summaries["A0"]["final_accuracy"]-0.01
        gates[f"{arm}_online_calls_reduced_ge_30pct"]=comparisons[arm]["online_call_reduction"]>=0.30
    gates["A0_completed_semantic_accuracy_ge_0_98"]=(summaries["A0"]["online_transport"]["semantic_accuracy_on_completed"] or 0)>=0.98
    a4_vs_a2=(summaries["A2"]["p95_latency_ms"]-summaries["A4"]["p95_latency_ms"])/summaries["A2"]["p95_latency_ms"] if summaries["A2"]["p95_latency_ms"] else 0
    verdict="REJECT"
    if all(gates.values()):
        verdict="2_WORKER_PILOT"
        if a4_vs_a2>=0.15: verdict="2_PLUS_4_BURST_PILOT"
    payload={
        "schema":SCHEMA,"status":"COMPLETE","claim_ceiling":"EXPERIMENT_ONLY_NO_ROUTING_AUTHORITY",
        "policy":{"source_cohort_sha256":POLICY_SOURCE_COHORT_SHA256,"rule":"literal_extraction contract-valid and parsed output length <= 32; mandatory controls bypass","max_chars":32},
        "source_commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
        "source_tree":subprocess.check_output(["git","rev-parse","HEAD^{tree}"],text=True).strip(),
        "cohort_sha256":cohort_sha,"cohort_count":len(cases),"apple_fm_identity":identity,"network_control":network,
        "online_route":{"transport":"~/.local/bin/nexus-agy-dispatch","model":args.online_model,"effort":args.online_effort,"parallelism":args.online_workers,"cwd":str(args.online_cwd),"token_usage":"UNKNOWN_NOT_EXPOSED_BY_WRAPPER"},
        "summaries":summaries,"comparisons_vs_A0":comparisons,"gates":gates,"a4_vs_a2_p95_improvement":a4_vs_a2,
        "verdict":verdict,"rows":rows_by_arm,"fm_batch_receipts":receipts,
    }
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"status":"COMPLETE","cohort_sha256":cohort_sha,"summaries":summaries,"comparisons":comparisons,"gates":gates,"verdict":verdict},indent=2,ensure_ascii=False))
    return 0
if __name__=="__main__": raise SystemExit(main())
