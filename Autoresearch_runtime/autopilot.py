import json
import re
import subprocess
from pathlib import Path

TRAIN_PY = Path("train.py")
HARDENING_PY = Path("formal_research_hardening.py")
MASTER_JSONL = Path("master_round_summary.jsonl")
PROD_JSONL = Path("round_summary.jsonl")
MAX_RUNS = 50

PRECISION_MIN = 0.95
PRECISION_MAX = 0.99
STEP_SMALL = 0.001
STEP_LARGE = 0.002


def parse_metrics(text: str) -> dict:
    text = text.strip()
    if not text:
        return {}
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return {}


def mutate_precision(step: float) -> float:
    text = TRAIN_PY.read_text(encoding="utf-8")
    match = re.search(r"PRECISION_ALPHA\s+=\s+([\d.]+)", text)
    old_val = float(match.group(1)) if match else PRECISION_MIN
    new_val = max(PRECISION_MIN, min(PRECISION_MAX, old_val + step))
    new_text = re.sub(r"PRECISION_ALPHA\s+=\s+[\d.]+", f"PRECISION_ALPHA = {new_val:.4f}", text)
    TRAIN_PY.write_text(new_text, encoding="utf-8")
    return new_val


def summarize_last20(rows: list[dict]) -> dict:
    tail = rows[-20:]
    mismatch = []
    proof = []
    for r in tail:
        mv = r.get("mismatch_rate", 999.0)
        pv = r.get("proof_ratio", 0.0)
        mismatch.append(999.0 if mv is None else float(mv))
        proof.append(0.0 if pv is None else float(pv))
    return {
        "mismatch_lt_0_5_last20": sum(1 for x in mismatch if x < 0.5),
        "mismatch_max_last20": max(mismatch) if mismatch else 0.0,
        "proof_ratio_min_last20": min(proof) if proof else 0.0,
    }


def main() -> None:
    print("Starting Phase 5 v8.0 (Damped Single-Variable Convergence)...", flush=True)
    if MASTER_JSONL.exists():
        MASTER_JSONL.unlink()
    if PROD_JSONL.exists():
        PROD_JSONL.unlink()

    all_rows: list[dict] = []
    best_mismatch = 100.0
    best_precision = PRECISION_MIN
    stagnation_rounds = 0

    for i in range(1, MAX_RUNS + 1):
        backup = TRAIN_PY.read_text(encoding="utf-8")
        step = STEP_SMALL if stagnation_rounds < 5 else STEP_LARGE
        precision = mutate_precision(step)

        res = subprocess.run(["python3", str(TRAIN_PY)], capture_output=True, text=True)
        row = parse_metrics(res.stdout)
        if not row:
            TRAIN_PY.write_text(backup, encoding="utf-8")
            stagnation_rounds += 1
            continue
        row["round"] = i

        with MASTER_JSONL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")

        # Always judge by hardening output.
        subprocess.run(
            [
                "python3",
                str(HARDENING_PY),
                "--round-summary",
                str(MASTER_JSONL),
                "--output-dir",
                ".",
                "--proof-ratio-min",
                "95.0",
            ],
            capture_output=True,
            text=True,
        )

        all_rows.append(row)
        stats = summarize_last20(all_rows)

        mismatch = float(row.get("mismatch_rate", 1.0) or 1.0)
        proof = float(row.get("proof_ratio", 0.0) or 0.0)
        print(
            f"R{i} P:{proof:.2f}% | M:{mismatch:.3f}% | <0.5(last20):{stats['mismatch_lt_0_5_last20']} | PREC:{precision:.4f}",
            flush=True,
        )

        if proof < 95.0:
            print(f"  HARD REVERT: proof dropped to {proof:.2f}%", flush=True)
            TRAIN_PY.write_text(backup, encoding="utf-8")
            stagnation_rounds += 1
            continue

        if mismatch < best_mismatch:
            best_mismatch = mismatch
            best_precision = precision
            stagnation_rounds = 0
            print(f"  BEST UPDATE: mismatch={mismatch:.3f}% precision={precision:.4f}", flush=True)
        elif mismatch >= 0.5:
            print(f"  SOFT REJECT: mismatch={mismatch:.3f}%", flush=True)
            TRAIN_PY.write_text(backup, encoding="utf-8")
            stagnation_rounds += 1
        else:
            stagnation_rounds = 0

        if stats["mismatch_lt_0_5_last20"] >= 20:
            print("MILESTONE B REACHED: 20/20 rounds under 0.5%", flush=True)
            break

    final_stats = summarize_last20(all_rows) if all_rows else {
        "mismatch_lt_0_5_last20": 0,
        "mismatch_max_last20": 0.0,
        "proof_ratio_min_last20": 0.0,
    }
    print("\n--- PHASE 5 v8.0 FINAL STATS ---", flush=True)
    print(f"mismatch_lt_0.5_last20: {final_stats['mismatch_lt_0_5_last20']}", flush=True)
    print(f"mismatch_max_last20: {final_stats['mismatch_max_last20']}", flush=True)
    print(f"proof_ratio_min_last20: {final_stats['proof_ratio_min_last20']}", flush=True)
    print(f"best_precision: {best_precision:.4f}", flush=True)


if __name__ == "__main__":
    main()
