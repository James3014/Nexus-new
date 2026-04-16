import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

def rollup(input_dir, output_file):
    p = Path(input_dir)
    files = sorted(p.glob("*.json"))
    bench_files = [f for f in files if "precision" in f.name and "summary" not in f.name]
    if not bench_files: return
    recent = bench_files[-7:]
    aggs = []
    for f in recent:
        try:
            d = json.loads(f.read_text())
            aggs.append(d)
        except: continue
    if not aggs: return
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rolling_window": 7,
        "sample_count": len(aggs),
        "metrics": {
            "avg_precision": round(sum(a.get("precision", 0) for a in aggs) / len(aggs), 4),
            "avg_unknown_correct_rate": round(sum(a.get("unknown_correct_rate", 0) for a in aggs) / len(aggs), 4),
            "avg_citation_noise_rate": round(sum(a.get("citation_noise_rate", 0) for a in aggs) / len(aggs), 4)
        },
        "history": [{"file": f.name, "precision": a.get("precision")} for f, a in zip(recent, aggs)]
    }
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    Path(output_file).write_text(json.dumps(summary, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rollup(args.input_dir, args.output)
