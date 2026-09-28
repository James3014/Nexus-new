#!/usr/bin/env python3
from __future__ import annotations
import argparse, concurrent.futures, hashlib, json, math, os, pathlib, re, statistics, subprocess, time
from dataclasses import dataclass, asdict
from typing import Any

ROOT=pathlib.Path(__file__).resolve().parents[3]
SOURCE=ROOT/'docs/reports/NEXUS_HEEP_MAT_B_LIVE_REPORT_2026-05-20.json'
SCHEMA='nexus.experiment.apple_fm_evidence_filter_ab.v1'
NETWORK_DENY='(version 1)(allow default)(deny network*)'
VERDICTS=('HOLD_MISSING_MAT_B_EVIDENCE','REJECT_MULTI_SKILL','KEEP_SINGLE_PRIMARY','APPROVE_HEEP_MODE_CANDIDATE')
POLICY='''Apply this ordered MAT-B decision policy:
1. If baseline.infra_invalid_reason is non-empty -> HOLD_MISSING_MAT_B_EVIDENCE.
2. Else if challenger.infra_invalid_reason is non-empty -> HOLD_MISSING_MAT_B_EVIDENCE.
3. Else if challenger.success_rate < baseline.success_rate or challenger.success_rate < 1.0 -> REJECT_MULTI_SKILL.
4. Else if challenger.pollution_pct > baseline.pollution_pct -> REJECT_MULTI_SKILL.
5. Else if challenger.evidence_seal_count < baseline.evidence_seal_count or challenger.receipt_chain_pass is false -> REJECT_MULTI_SKILL.
6. Else if token truth or wall-time truth is missing -> HOLD_MISSING_MAT_B_EVIDENCE.
7. Else if challenger total_tokens > baseline total_tokens OR challenger phase_wall_total_sec > baseline phase_wall_total_sec -> KEEP_SINGLE_PRIMARY.
8. Else if either reopen_rate is missing -> HOLD_MISSING_MAT_B_EVIDENCE.
9. Else if challenger.reopen_rate > baseline.reopen_rate -> REJECT_MULTI_SKILL.
10. Else -> APPROVE_HEEP_MODE_CANDIDATE.'''

ALL_FIELDS=(
'baseline.success_rate','baseline.pollution_pct','baseline.evidence_seal_count','baseline.total_tokens',
'baseline.phase_wall_total_sec','baseline.reopen_rate','baseline.trust_mismatch','baseline.skill_mount_contract_status',
'baseline.receipt_chain_pass','baseline.infra_invalid_reason',
'challenger.success_rate','challenger.pollution_pct','challenger.evidence_seal_count','challenger.total_tokens',
'challenger.phase_wall_total_sec','challenger.reopen_rate','challenger.trust_mismatch','challenger.skill_mount_contract_status',
'challenger.receipt_chain_pass','challenger.infra_invalid_reason',
)
STATIC_FIELDS=frozenset((
'baseline.success_rate','baseline.pollution_pct','baseline.evidence_seal_count','baseline.total_tokens',
'baseline.phase_wall_total_sec','baseline.reopen_rate','baseline.infra_invalid_reason',
'challenger.success_rate','challenger.pollution_pct','challenger.evidence_seal_count','challenger.total_tokens',
'challenger.phase_wall_total_sec','challenger.reopen_rate','challenger.receipt_chain_pass','challenger.infra_invalid_reason',
))

@dataclass(frozen=True)
class Case:
    case_id:str; capability:str; task_id:str; source_sha256:str; expected_verdict:str
    spans:tuple[tuple[str,str,str],...]; critical_ids:tuple[str,...]; split:str

def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def canon(v:Any)->str:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def getv(row:dict[str,Any], field:str)->Any:
    a,b=field.split('.',1); return row[a].get(b)

def oracle(row:dict[str,Any])->tuple[str,list[str]]:
    b=row['baseline']; c=row['challenger']
    crit=['baseline.infra_invalid_reason']
    if b.get('infra_invalid_reason'): return 'HOLD_MISSING_MAT_B_EVIDENCE',crit
    crit+=['challenger.infra_invalid_reason']
    if c.get('infra_invalid_reason'): return 'HOLD_MISSING_MAT_B_EVIDENCE',crit
    crit+=['baseline.success_rate','challenger.success_rate']
    if c.get('success_rate',0)<b.get('success_rate',0) or c.get('success_rate',0)<1.0:return 'REJECT_MULTI_SKILL',crit
    crit+=['baseline.pollution_pct','challenger.pollution_pct']
    if c.get('pollution_pct',0)>b.get('pollution_pct',0):return 'REJECT_MULTI_SKILL',crit
    crit+=['baseline.evidence_seal_count','challenger.evidence_seal_count','challenger.receipt_chain_pass']
    if c.get('evidence_seal_count',0)<b.get('evidence_seal_count',0) or not c.get('receipt_chain_pass'):return 'REJECT_MULTI_SKILL',crit
    crit+=['baseline.total_tokens','challenger.total_tokens','baseline.phase_wall_total_sec','challenger.phase_wall_total_sec']
    if b.get('total_tokens') is None or c.get('total_tokens') is None or b.get('phase_wall_total_sec') is None or c.get('phase_wall_total_sec') is None:return 'HOLD_MISSING_MAT_B_EVIDENCE',crit
    if c['total_tokens']-b['total_tokens']>0 or c['phase_wall_total_sec']-b['phase_wall_total_sec']>0:return 'KEEP_SINGLE_PRIMARY',crit
    crit+=['baseline.reopen_rate','challenger.reopen_rate']
    if b.get('reopen_rate') is None or c.get('reopen_rate') is None:return 'HOLD_MISSING_MAT_B_EVIDENCE',crit
    if c['reopen_rate']>b['reopen_rate']:return 'REJECT_MULTI_SKILL',crit
    return 'APPROVE_HEEP_MODE_CANDIDATE',crit

def build_cases()->list[Case]:
    raw=json.loads(SOURCE.read_text())
    rows=raw['comparisons']
    source_sha=sha(SOURCE.read_bytes())
    cases=[]
    for i,row in enumerate(rows):
        expected,crit_fields=oracle(row)
        # Current report may refine HOLD into a blocker subtype; compare collapsed source semantics.
        current=row['verdict']
        if current.startswith('BLOCKED_BY_'): current='HOLD_MISSING_MAT_B_EVIDENCE'
        if current!=expected:
            raise RuntimeError(f'oracle drift row {i}: report={row["verdict"]} oracle={expected}')
        spans=[]
        id_by_field={}
        for j,field in enumerate(ALL_FIELDS,1):
            sid=f'S{j:02d}'; id_by_field[field]=sid
            value=getv(row,field)
            spans.append((sid,field,canon(value)))
        crit=tuple(id_by_field[f] for f in crit_fields)
        # Stratified-ish stable calibration: first deterministic hash-ranked 10, holdout 24.
        cases.append(Case(f'MATB-{i+1:02d}',str(row['capability']),str(row['task_id']),source_sha,expected,tuple(spans),crit,''))
    ranked=sorted(cases,key=lambda c:sha(c.case_id.encode()))
    cal={c.case_id for c in ranked[:10]}
    return [Case(c.case_id,c.capability,c.task_id,c.source_sha256,c.expected_verdict,c.spans,c.critical_ids,'calibration' if c.case_id in cal else 'holdout') for c in cases]

def fm_decide_span(case:Case, candidate:tuple[str,str,str])->dict[str,Any]:
    packet='\n'.join(f'{sid} {field}={value}' for sid,field,value in case.spans)
    sid,field,value=candidate
    prompt=f'''You are an evidence-preservation filter, not the decision maker.
{POLICY}
Full evidence packet:
{packet}
Candidate span:
{sid} {field}={value}
Question: If this candidate span were removed, could the correct verdict become ambiguous or change under the ordered policy? Return exactly KEEP if yes. Return exactly DROP only if no.'''
    argv=['/usr/bin/sandbox-exec','-p',NETWORK_DENY,'/usr/bin/fm','respond','--no-stream','--greedy',prompt]
    t=time.perf_counter()
    try:
        cp=subprocess.run(argv,capture_output=True,text=True,timeout=30)
        out=cp.stdout.strip()
        valid=cp.returncode==0 and out in ('KEEP','DROP')
        # Evidence-preserving fail closed: invalid/timeout => KEEP.
        keep=(out=='KEEP') if valid else True
        return {'span_id':sid,'keep':keep,'raw':out,'valid':valid,'returncode':cp.returncode,'latency_ms':int((time.perf_counter()-t)*1000),'error':None if valid else ('INVALID_OUTPUT' if cp.returncode==0 else f'EXIT_{cp.returncode}')}
    except subprocess.TimeoutExpired:
        return {'span_id':sid,'keep':True,'raw':'','valid':False,'returncode':None,'latency_ms':30000,'error':'TIMEOUT'}

def fm_filter(cases:list[Case],workers:int=2)->dict[str,Any]:
    jobs=[(c,s) for c in cases for s in c.spans]
    results={c.case_id:[] for c in cases}
    start=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs={ex.submit(fm_decide_span,c,s):(c.case_id,s[0]) for c,s in jobs}
        for fut in concurrent.futures.as_completed(futs):
            cid,_=futs[fut]; results[cid].append(fut.result())
    wall=int((time.perf_counter()-start)*1000)
    return {'results':results,'wall_ms':wall,'tasks':len(jobs),'workers':workers}

def selected_ids(case:Case,arm:str,fm:dict[str,Any])->list[str]:
    if arm=='A0': return [s[0] for s in case.spans]
    if arm=='A1': return [sid for sid,field,_ in case.spans if field in STATIC_FIELDS]
    keep={r['span_id'] for r in fm['results'][case.case_id] if r['keep']}
    return [sid for sid,_,_ in case.spans if sid in keep]

def parse_verdict(text:str)->str:
    up=text.upper()
    for v in VERDICTS:
        if v in up:return v
    return text.strip()

def online_one(case:Case,arm:str,ids:list[str],cwd:pathlib.Path)->dict[str,Any]:
    lookup={sid:(field,value) for sid,field,value in case.spans}
    evidence='\n'.join(f'{sid} {lookup[sid][0]}={lookup[sid][1]}' for sid in ids)
    prompt=f'''BENCHMARK MODE. Do not call tools, read files, or inspect the workspace. Answer solely from the policy and raw evidence below.
{POLICY}
Case capability: {case.capability}
Raw evidence spans:
{evidence}
Return exactly one verdict from: {", ".join(VERDICTS)}.'''
    argv=[os.path.expanduser('~/.local/bin/nexus-agy-dispatch'),'--cwd',str(cwd),'--mode','plan','--model','gemini-3.8-flash','--effort','low','--timeout','120','--max-calls','3','--pool-wait-timeout','180','--prompt',prompt]
    t=time.perf_counter(); cp=subprocess.run(argv,capture_output=True,text=True,timeout=240); elapsed=int((time.perf_counter()-t)*1000)
    lines=[x.strip() for x in cp.stdout.splitlines() if x.strip() and not x.startswith('NEXUS_AGY_DISPATCH ')]
    ans='\n'.join(lines); parsed=parse_verdict(ans)
    return {'status':'PASS' if cp.returncode==0 else 'INFRA_ERROR','returncode':cp.returncode,'answer':ans,'parsed':parsed,'correct':cp.returncode==0 and parsed==case.expected_verdict,'latency_ms':elapsed,'prompt_chars':len(prompt),'stderr_tail':cp.stderr[-400:]}

def run_online(cases:list[Case],arm:str,fm:dict[str,Any],cwd:pathlib.Path,workers:int=4)->dict[str,Any]:
    out={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs={}
        for c in cases:
            ids=selected_ids(c,arm,fm); futs[ex.submit(online_one,c,arm,ids,cwd)]=(c,ids)
        for fut in concurrent.futures.as_completed(futs):
            c,ids=futs[fut]; r=fut.result(); r['selected_ids']=ids; out[c.case_id]=r
    return out

def pct(values:list[int],p:float)->float:
    s=sorted(values); return float(s[max(0,math.ceil(p*len(s))-1)]) if s else float('nan')

def summarize(cases:list[Case],arm:str,online:dict[str,Any],fm:dict[str,Any])->dict[str,Any]:
    rows=[]
    for c in cases:
        ids=online[c.case_id]['selected_ids']; crit=set(c.critical_ids)
        rows.append({'case_id':c.case_id,'expected':c.expected_verdict,'critical_recall':len(crit&set(ids))/len(crit),'all_critical_kept':crit.issubset(ids),'selected_count':len(ids),'total_count':len(c.spans),'online':online[c.case_id]})
    completed=[r for r in rows if r['online']['status']=='PASS']
    chars=[r['online']['prompt_chars'] for r in rows]
    lats=[r['online']['latency_ms'] for r in rows]
    return {'arm':arm,'cases':len(rows),'critical_recall_mean':statistics.fmean(r['critical_recall'] for r in rows),'critical_recall_100_count':sum(r['all_critical_kept'] for r in rows),'mean_selected_spans':statistics.fmean(r['selected_count'] for r in rows),'mean_prompt_chars':statistics.fmean(chars),'p50_latency_ms':pct(lats,.5),'p95_latency_ms':pct(lats,.95),'infra_errors':sum(r['online']['status']!='PASS' for r in rows),'completed_accuracy':sum(r['online']['correct'] for r in completed)/len(completed) if completed else None,'system_accuracy':sum(r['online']['correct'] for r in rows)/len(rows),'rows':rows}

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--cohort',type=pathlib.Path,required=True); ap.add_argument('--output-json',type=pathlib.Path,required=True); ap.add_argument('--online-cwd',type=pathlib.Path,required=True); ap.add_argument('--build-only',action='store_true'); args=ap.parse_args()
    cases=build_cases(); text='\n'.join(canon(asdict(c)) for c in cases)+'\n'; args.cohort.parent.mkdir(parents=True,exist_ok=True); args.cohort.write_text(text)
    csha=sha(text.encode())
    if args.build_only:
        print(json.dumps({'status':'COHORT_BUILT','cases':len(cases),'calibration':sum(c.split=='calibration' for c in cases),'holdout':sum(c.split=='holdout' for c in cases),'cohort_sha256':csha},indent=2)); return 0
    # Physical network-deny preflight.
    direct=subprocess.run(['/usr/bin/curl','--max-time','3','-sS','https://example.com'],capture_output=True,text=True,timeout=5)
    denied=subprocess.run(['/usr/bin/sandbox-exec','-p',NETWORK_DENY,'/usr/bin/curl','--max-time','3','-sS','https://example.com'],capture_output=True,text=True,timeout=5)
    if not (direct.returncode==0 and denied.returncode!=0): raise SystemExit('network denial preflight failed')
    fm=fm_filter(cases,2)
    # Fixed prompt already chosen before cohort execution; calibration is reported only, not used to retune.
    arms={a:run_online(cases,a,fm,args.online_cwd,4) for a in ('A0','A1','A2')}
    summaries={a:summarize(cases,a,arms[a],fm) for a in arms}
    hold=[c for c in cases if c.split=='holdout']
    hold_summaries={a:summarize(hold,a,{c.case_id:arms[a][c.case_id] for c in hold},fm) for a in arms}
    base_chars=hold_summaries['A0']['mean_prompt_chars']
    for a in ('A1','A2'): hold_summaries[a]['prompt_char_reduction_vs_A0']=1-hold_summaries[a]['mean_prompt_chars']/base_chars
    fm_valid=[r for rs in fm['results'].values() for r in rs]
    gates={
      'A2_holdout_critical_recall_100pct':hold_summaries['A2']['critical_recall_100_count']==len(hold),
      'A2_holdout_completed_accuracy_noninferior_1pp':(hold_summaries['A2']['completed_accuracy'] or 0)>=(hold_summaries['A0']['completed_accuracy'] or 0)-.01,
      'A2_prompt_chars_reduced_ge_30pct':hold_summaries['A2'].get('prompt_char_reduction_vs_A0',0)>=.30,
      'A2_no_more_infra_errors_than_A0':hold_summaries['A2']['infra_errors']<=hold_summaries['A0']['infra_errors'],
    }
    verdict='EVIDENCE_FILTER_PILOT' if all(gates.values()) else 'REJECT_EVIDENCE_FILTER'
    payload={'schema':SCHEMA,'status':'COMPLETE','claim_ceiling':'EXPERIMENT_ONLY_NO_ROUTING_AUTHORITY','source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'source_tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip(),'source_report':str(SOURCE.relative_to(ROOT)),'source_report_sha256':sha(SOURCE.read_bytes()),'cohort_sha256':csha,'cohort_count':len(cases),'fm':{'binary':'/usr/bin/fm','binary_sha256':sha(pathlib.Path('/usr/bin/fm').read_bytes()),'workers':2,'network_denial_verified':True,'classification_tasks':fm['tasks'],'wall_ms':fm['wall_ms'],'valid_rate':sum(r['valid'] for r in fm_valid)/len(fm_valid),'invalid_count':sum(not r['valid'] for r in fm_valid),'invalid_fail_closed_action':'KEEP'},'online':{'transport':'~/.local/bin/nexus-agy-dispatch','model':'gemini-3.8-flash','effort':'low','workers':4,'token_usage':'UNKNOWN_NOT_EXPOSED'},'summaries_all':summaries,'summaries_holdout':hold_summaries,'gates':gates,'verdict':verdict,'arm_results':arms,'fm_filter_results':fm['results']}
    args.output_json.parent.mkdir(parents=True,exist_ok=True); args.output_json.write_text(json.dumps(payload,indent=2,ensure_ascii=False))
    print(json.dumps({'status':'COMPLETE','holdout':hold_summaries,'gates':gates,'verdict':verdict},indent=2,ensure_ascii=False))
    return 0
if __name__=='__main__': raise SystemExit(main())
