import csv
from pathlib import Path
p = Path('ci_benchmark.csv')
if not p.exists():
    print("❌ ci_benchmark.csv not found")
    exit(1)
rows=list(csv.DictReader(open(p,encoding='utf-8')))
if not rows:
    print("❌ empty benchmark")
    exit(1)
sr=sum(r.get('status','').upper()=='PASS' for r in rows)/len(rows)*100
avg=sum(float(r.get('health') or 0) for r in rows)/len(rows)
raw=sum(int(float(r.get('token_raw_model') or 0)) for r in rows)
empty=sum(1 for r in rows if not (r.get('token_capture_status') or '').strip())
print(f"success_rate={sr:.1f} avg_health={avg:.1f} raw={raw} empty={empty}")
if sr>=95 and avg>=90 and raw>0 and empty==0:
    print("✅ VERIFICATION PASSED")
    exit(0)
else:
    print("❌ VERIFICATION FAILED")
    exit(1)
