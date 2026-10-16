import csv
from pathlib import Path
p=Path("ci_benchmark.csv")
rows=list(csv.DictReader(p.open())) if p.exists() else []
print(f"rows={len(rows)}")
if rows:
    succ=sum(1 for r in rows if r.get("status")=="PASS")
    avg=sum(float(r.get("health") or r.get("health_score") or 0) for r in rows)/len(rows)
    empty=sum(1 for r in rows if not (r.get("token_capture_status") or "").strip())
    raw=sum(int(float(r.get("token_raw_model") or 0)) for r in rows)
    print(f"success_rate={succ/len(rows)*100:.1f}%")
    print(f"avg_health={avg:.1f}")
    print(f"empty_token_status={empty}")
    print(f"total_raw_tokens={raw}")
