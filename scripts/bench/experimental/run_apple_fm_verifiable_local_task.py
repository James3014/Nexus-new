#!/usr/bin/env python3
"""Compare deterministic receipt triage with Apple FM on real Agy outcomes."""

from __future__ import annotations
import argparse, concurrent.futures, hashlib, json, pathlib, re, statistics, subprocess, time
from dataclasses import dataclass, asdict
from typing import Any

ROOT=pathlib.Path(__file__).resolve().parents[3]
SOURCE=pathlib.Path('/Users/james/.local/share/nexus-agy-direct/worktrees/apple-fm-value-ab-v1/artifacts/experiments/apple_fm_value_ab_v2/result.json')
SCHEMA='nexus.experiment.apple_fm_verifiable_local_task.v1'
NETWORK_DENY='(version 1)(allow default)(deny network*)'
LABELS=('SUCCESS','TIMEOUT','UNKNOWN')

@dataclass(frozen=True)
class Case:
    case_id:str
    ground_truth:str
    event_text:str
    source_result_sha256:str
    source_case_id:str

def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def canon(v:Any)->str:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)

def redact(text:str)->str:
    text=re.sub(r'("account_alias_hash"\s*:\s*)"[^"]+"',r'\1"<redacted>"',text)
    text=re.sub(r'("lease_id_hash"\s*:\s*)"[^"]+"',r'\1"<redacted>"',text)
    # Remove the already-structured class label so the model sees the operational evidence, not the answer field.
    text=re.sub(r'\s*"failure_kind"\s*:\s*"[^"]+"\s*,?','',text)
    return text.strip()

def build_cases()->list[Case]:
    d=json.loads(SOURCE.read_text())
    source_sha=sha(SOURCE.read_bytes())
    candidates=[]
    for arm,rows in d['rows'].items():
        for row in rows:
            o=row.get('online')
            if not isinstance(o,dict):continue
            status=o.get('status')
            stderr=str(o.get('stderr_tail') or '')
            if status=='PASS':
                gt='SUCCESS'
            elif status=='INFRA_ERROR' and 'TIMEOUT' in stderr.upper():
                gt='TIMEOUT'
            else:
                continue
            candidates.append((f'{arm}:{row["case_id"]}',gt,redact(stderr)))
    # De-duplicate exact arm-bound physical observations only.
    seen=set(); unique=[]
    for cid,gt,text in candidates:
        key=(cid,gt)
        if key in seen:continue
        seen.add(key); unique.append((cid,gt,text))
    timeouts=[x for x in unique if x[1]=='TIMEOUT']
    successes=[x for x in unique if x[1]=='SUCCESS']
    if len(timeouts)<25 or len(successes)<25:
        raise RuntimeError(f'insufficient real corpus timeout={len(timeouts)} success={len(successes)}')
    # Stable hash-ranked balanced cohort: 25+25 independent source cases.
    pick=lambda xs,n: sorted(xs,key=lambda x:sha((x[0]+'|'+x[1]).encode()))[:n]
    rows=pick(timeouts,25)+pick(successes,25)
    rows=sorted(rows,key=lambda x:sha((x[0]+'|'+x[1]).encode()))
    return [Case(f'TRIAGE-{i+1:03d}',gt,text,source_sha,cid) for i,(cid,gt,text) in enumerate(rows)]

def deterministic_classify(text:str)->str:
    low=text.lower()
    # Same-input deterministic baseline. The source experiment invoked Agy with
    # --timeout 120, and Nexus tests bind a 2m print-timeout to TIMEOUT.
    if '"status": "completed"' in low or '"status":"completed"' in low:
        return 'SUCCESS'
    if 'timeout' in low:
        return 'TIMEOUT'
    match=re.search(r'"wall_ms"\s*:\s*(\d+)', text)
    failed=('"status": "failed"' in low or '"status":"failed"' in low)
    if failed and match and int(match.group(1)) >= 120000:
        return 'TIMEOUT'
    return 'UNKNOWN'

def fm_one(case:Case)->dict[str,Any]:
    prompt=(
        'Classify this real Agy execution event into exactly one label: SUCCESS, TIMEOUT, UNKNOWN. '
        'SUCCESS means the wrapper/provider operation completed. TIMEOUT means the operation failed due to timeout. '
        'Do not infer account identity. Return only the label. Event:\n'+case.event_text
    )
    argv=['/usr/bin/sandbox-exec','-p',NETWORK_DENY,'/usr/bin/fm','respond','--no-stream','--greedy',prompt]
    t=time.perf_counter()
    try:
        cp=subprocess.run(argv,capture_output=True,text=True,timeout=30)
        elapsed=int((time.perf_counter()-t)*1000)
        out=cp.stdout.strip().upper()
        valid=cp.returncode==0 and out in LABELS
        return {'label':out if valid else 'UNKNOWN','raw':cp.stdout.strip(),'valid':valid,'latency_ms':elapsed,'returncode':cp.returncode,'error':None if valid else 'INVALID_OUTPUT'}
    except subprocess.TimeoutExpired:
        return {'label':'UNKNOWN','raw':'','valid':False,'latency_ms':30000,'returncode':None,'error':'TIMEOUT'}

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--cohort',type=pathlib.Path,required=True); ap.add_argument('--output-json',type=pathlib.Path,required=True); ap.add_argument('--build-only',action='store_true'); args=ap.parse_args()
    cases=build_cases()
    text='\n'.join(canon(asdict(c)) for c in cases)+'\n'; args.cohort.parent.mkdir(parents=True,exist_ok=True); args.cohort.write_text(text)
    cohort_sha=sha(text.encode())
    if args.build_only:
        from collections import Counter
        print(json.dumps({'status':'COHORT_BUILT','cases':len(cases),'class_counts':Counter(c.ground_truth for c in cases),'cohort_sha256':cohort_sha},default=dict,indent=2)); return 0

    direct=subprocess.run(['/usr/bin/curl','--max-time','3','-sS','https://example.com'],capture_output=True,text=True,timeout=5)
    denied=subprocess.run(['/usr/bin/sandbox-exec','-p',NETWORK_DENY,'/usr/bin/curl','--max-time','3','-sS','https://example.com'],capture_output=True,text=True,timeout=5)
    if not(direct.returncode==0 and denied.returncode!=0):raise SystemExit('network denial preflight failed')

    det_rows=[]
    for c in cases:
        # Repeat classification for stable CPU timing while preserving the exact same semantic function.
        loops=10000; t=time.perf_counter_ns(); label=''
        for _ in range(loops):label=deterministic_classify(c.event_text)
        ns=time.perf_counter_ns()-t
        det_rows.append({'case_id':c.case_id,'label':label,'correct':label==c.ground_truth,'latency_us_per_call':ns/loops/1000})

    fm_rows={}
    start=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futs={ex.submit(fm_one,c):c for c in cases}
        for fut in concurrent.futures.as_completed(futs):
            c=futs[fut]; r=fut.result(); r['case_id']=c.case_id; r['correct']=r['label']==c.ground_truth; fm_rows[c.case_id]=r
    fm_wall_ms=int((time.perf_counter()-start)*1000)

    det_acc=sum(r['correct'] for r in det_rows)/len(det_rows)
    fm_acc=sum(fm_rows[c.case_id]['correct'] for c in cases)/len(cases)
    det_us=statistics.fmean(r['latency_us_per_call'] for r in det_rows)
    fm_lats=[fm_rows[c.case_id]['latency_ms'] for c in cases]
    fm_valid=sum(fm_rows[c.case_id]['valid'] for c in cases)/len(cases)
    sorted_lat=sorted(fm_lats)
    p50=sorted_lat[(len(sorted_lat)-1)//2]; p95=sorted_lat[max(0,__import__('math').ceil(.95*len(sorted_lat))-1)]

    # If deterministic is exact, the task is not a useful LLM target even if FM also succeeds.
    verdict='DETERMINISTIC_DOMINATES' if det_acc==1.0 and det_us*1000 < statistics.fmean(fm_lats) else 'FM_ADDS_MEASURABLE_VALUE'
    gates={
      'deterministic_accuracy_100pct':det_acc==1.0,
      'fm_accuracy_ge_95pct':fm_acc>=.95,
      'fm_false_classifications_zero':sum(not fm_rows[c.case_id]['correct'] for c in cases)==0,
      'deterministic_faster_than_fm':det_us/1000 < statistics.fmean(fm_lats),
    }
    payload={'schema':SCHEMA,'status':'COMPLETE','claim_ceiling':'EXPERIMENT_ONLY_NO_ROUTING_AUTHORITY','source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'source_tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip(),'source_result_path':str(SOURCE),'source_result_sha256':sha(SOURCE.read_bytes()),'cohort_sha256':cohort_sha,'cohort_count':len(cases),'classes':{k:sum(c.ground_truth==k for c in cases) for k in LABELS},'network_denial_verified':True,'deterministic':{'source_contract':'nexus/services/external_worker_runtime.py failure-text classification + structured completion receipt','accuracy':det_acc,'mean_latency_us':det_us,'rows':det_rows},'apple_fm':{'binary':'/usr/bin/fm','binary_sha256':sha(pathlib.Path('/usr/bin/fm').read_bytes()),'workers':2,'accuracy':fm_acc,'valid_rate':fm_valid,'wall_ms':fm_wall_ms,'mean_latency_ms':statistics.fmean(fm_lats),'p50_latency_ms':p50,'p95_latency_ms':p95,'rows':[fm_rows[c.case_id] for c in cases]},'gates':gates,'verdict':verdict}
    args.output_json.parent.mkdir(parents=True,exist_ok=True); args.output_json.write_text(json.dumps(payload,indent=2,ensure_ascii=False))
    print(json.dumps({k:payload[k] for k in ('status','classes','deterministic','apple_fm','gates','verdict') if k not in ('deterministic','apple_fm')} | {'deterministic':{k:v for k,v in payload['deterministic'].items() if k!='rows'},'apple_fm':{k:v for k,v in payload['apple_fm'].items() if k!='rows'}},indent=2,ensure_ascii=False))
    return 0
if __name__=='__main__': raise SystemExit(main())
