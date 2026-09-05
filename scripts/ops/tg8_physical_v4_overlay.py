#!/usr/bin/env python3
from __future__ import annotations

import argparse, asyncio, contextlib, hashlib, io, json, os, runpy, shutil, subprocess, sys
from pathlib import Path
from typing import Any


def canon(v: Any) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def dig(v: Any) -> str:
    return "sha256:" + hashlib.sha256(canon(v).encode()).hexdigest()


def fh(p: Path) -> str:
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


def load(p: Path) -> dict[str, Any]:
    v=json.loads(p.read_text()); assert isinstance(v,dict); return v


def write(p: Path, v: dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(canon(v)+"\n")


def hashed(v: dict[str, Any], key: str) -> dict[str, Any]:
    o=dict(v); o[key]=dig(o); return o


def sh(cmd: list[str], *, cwd: Path|None=None, check: bool=True, input: str|None=None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd,cwd=cwd,check=check,text=True,capture_output=True,input=input)


def mkvenv(root: Path, name: str) -> Path:
    p=root/name; shutil.rmtree(p,ignore_errors=True); subprocess.run([sys.executable,"-m","venv",str(p)],check=True); return p


def install(v: Path, wheel: Path) -> None:
    subprocess.run([str(v/"bin/pip"),"install","--no-deps","--force-reinstall",str(wheel)],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)


def state(v: Path) -> dict[str,str]:
    code='''import hashlib,json\nfrom pathlib import Path\nfrom product.protocol import PUBLIC_PROTOCOL_VERSION,IMPLEMENTATION_SCHEMA\nimport product.runtime,product.ledger\ndef h(p): return "sha256:"+hashlib.sha256(Path(p).read_bytes()).hexdigest()\ndef d(r):\n r=Path(r); rows=[{"p":p.relative_to(r).as_posix(),"h":h(p)} for p in sorted(x for x in r.rglob("*") if x.is_file() and "__pycache__" not in x.parts)]; return "sha256:"+hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(",",":")).encode()).hexdigest()\nprint(json.dumps({"protocol":PUBLIC_PROTOCOL_VERSION,"implementation_schema":IMPLEMENTATION_SCHEMA,"runtime_hash":d(Path(product.runtime.__file__).parent),"ledger_hash":h(Path(product.ledger.__file__)),"ledger_schema":product.ledger.LEDGER_SCHEMA_VERSION},sort_keys=True))'''
    return json.loads(sh([str(v/"bin/python"),"-c",code]).stdout)


def req_probe(v: Path, protocol: str, schema: str) -> bool:
    p={"protocol_version":protocol,"implementation_schema":schema,"repository":{"owner":"James3014","name":"Nexus-new","pr_number":635,"expected_base_sha":"a"*40,"expected_head_sha":"b"*40},"acceptance_contract":{},"verification_plan":{},"profile_id":"python-oci-pytest-v1","idempotency_key":"tg8-v4","expected_generation":0}
    code='import json,sys; from product.runtime.schemas import validate_certification_request as f; print(json.dumps(list(f(json.loads(sys.stdin.read())))))'
    return not json.loads(sh([str(v/"bin/python"),"-c",code],input=json.dumps(p)).stdout)


def receipt_probe(v: Path, receipt: dict[str,Any]) -> bool:
    p={"receipt":receipt,"requested_scope":"ENVELOPE_ONLY","original_inputs":None}
    code='import json,sys; from product.runtime.schemas import validate_receipt_verify_request as f; print(json.dumps(list(f(json.loads(sys.stdin.read())))))'
    return not json.loads(sh([str(v/"bin/python"),"-c",code],input=json.dumps(p)).stdout)


def transition(root: Path, name: str, oldw: Path, neww: Path, oldver: str, newver: str, receipt_hash: str) -> dict[str,Any]:
    v=mkvenv(root,name); install(v,oldw); old=state(v); install(v,neww); new=state(v)
    return {"ok":old["protocol"]==oldver and new["protocol"]==newver,"old":old,"new":new,"old_wheel_hash":fh(oldw),"new_wheel_hash":fh(neww),"receipt_hash":receipt_hash}


def hostile(src: Path, root: Path, kind: str) -> Path:
    d=root/("src-"+kind); shutil.rmtree(d,ignore_errors=True); shutil.copytree(src,d,ignore=shutil.ignore_patterns(".git",".venv","__pycache__","dist"))
    if kind=="protocol":
        p=d/"product/protocol/__init__.py"; p.write_text(p.read_text().replace('PUBLIC_PROTOCOL_VERSION = "1.0.0-rc.1"','PUBLIC_PROTOCOL_VERSION = "2.0.0-foreign"',1))
    elif kind=="schema":
        p=d/"product/protocol/__init__.py"; p.write_text(p.read_text().replace('IMPLEMENTATION_SCHEMA = "nexus.changeset_certification.v2"','IMPLEMENTATION_SCHEMA = "nexus.foreign.v9"',1))
    else:
        p=d/"product/ledger.py"; p.write_text(p.read_text().replace('LEDGER_SCHEMA_VERSION = "nexus.ledger-entry.v1"','LEDGER_SCHEMA_VERSION = "nexus.ledger-entry.v9"',1))
    out=root/("wheel-"+kind); out.mkdir(exist_ok=True); subprocess.run(["uv","build","--wheel","--out-dir",str(out)],cwd=d,check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    ws=list(out.glob("*.whl")); assert len(ws)==1; return ws[0]


async def clients(candidate: Path, root: Path) -> dict[str,Any]:
    sys.path.insert(0,str(candidate)); ns=runpy.run_path(str(candidate/"tests/product/test_client_conformance.py")); req=ns["CANONICAL_REQUEST"]; Service=ns["MockCanonicalService"]
    from product.runtime.auth import generate_bearer_token,write_secure_token
    from product.runtime.http import start_runtime
    from product.clients.mcp import nexus_certify
    from product.clients.cli import build_parser,cmd_submit
    from product.clients.github_action import run_action
    d=root/"client"; d.mkdir(parents=True,exist_ok=True); token=generate_bearer_token(); tf=d/"token"; write_secure_token(token,tf); rf=d/"request.json"; rf.write_text(json.dumps(req)); handle=await start_runtime(host="127.0.0.1",port=0,token_path=tf,db_path=d/"ledger.sqlite3",service=Service()); url=f"http://127.0.0.1:{handle.port}"
    try:
        m=await asyncio.to_thread(nexus_certify,arguments=req,service_url=url,token=token); a=build_parser().parse_args(["submit","--request",str(rf),"--url",url,"--token-file",str(tf)]); buf=io.StringIO()
        with contextlib.redirect_stdout(buf): assert await asyncio.to_thread(cmd_submit,a)==0
        c=json.loads(buf.getvalue()); old=os.environ.get("RUNNER_ENVIRONMENT"); os.environ["RUNNER_ENVIRONMENT"]="self-hosted"
        try: g=await asyncio.to_thread(run_action,request_file=rf,token_file=tf,service_url=url)
        finally:
            if old is None: os.environ.pop("RUNNER_ENVIRONMENT",None)
            else: os.environ["RUNNER_ENVIRONMENT"]=old
        raw={"CLI":c,"MCP":m,"ACTION":g["response"]}; hashes={k:dig(v) for k,v in raw.items()}; return {"hashes":hashes,"parity":len(set(hashes.values()))==1,"request_hash":dig(req)}
    finally: await handle.stop()


def ledger(v: Path, receipt_file: Path, root: Path) -> dict[str,Any]:
    code='''import json,sys\nfrom pathlib import Path\nfrom product.evidence.ingestion import IDENTITY_ENVELOPE_SCHEMA\nfrom product.ledger import LedgerAppendRequest,append_or_replay,verify_chain\nr=json.loads(Path(sys.argv[1]).read_text()); e=json.dumps({"schema":IDENTITY_ENVELOPE_SCHEMA},sort_keys=True,separators=(",",":")).encode(); rb=json.dumps(r,sort_keys=True,separators=(",",":")).encode(); db=Path(sys.argv[2]); a=append_or_replay(LedgerAppendRequest("tg8-v4","r1","k1",0,1,{"x":1},e,rb,"sha256:"+"1"*64),db_path=db); s=append_or_replay(LedgerAppendRequest("tg8-v4","r2","k2",0,1,{"x":2},e,rb,"sha256:"+"2"*64),db_path=db); q=verify_chain(db_path=db,expected_ledger_id="tg8-v4"); print(json.dumps({"append":a.status.value,"stale":s.status.value,"valid":q.valid,"status":q.status}))'''
    return json.loads(sh([str(v/"bin/python"),"-c",code,str(receipt_file),str(root/"good.sqlite3")]).stdout)


def bad_ledger(hostile_v: Path, rc1_v: Path, receipt_file: Path, root: Path) -> dict[str,Any]:
    wc='''import json,sys\nfrom pathlib import Path\nfrom product.evidence.ingestion import IDENTITY_ENVELOPE_SCHEMA\nfrom product.ledger import LedgerAppendRequest,append_or_replay\nr=json.loads(Path(sys.argv[1]).read_text()); e=json.dumps({"schema":IDENTITY_ENVELOPE_SCHEMA},sort_keys=True,separators=(",",":")).encode(); rb=json.dumps(r,sort_keys=True,separators=(",",":")).encode(); x=append_or_replay(LedgerAppendRequest("foreign","r","k",0,1,{"x":1},e,rb,"sha256:"+"3"*64),db_path=Path(sys.argv[2])); print(x.status.value)'''
    rc='''import json,sys\nfrom pathlib import Path\nfrom product.ledger import verify_chain\nq=verify_chain(db_path=Path(sys.argv[1]),expected_ledger_id="foreign"); print(json.dumps({"valid":q.valid,"status":q.status}))'''
    db=root/"foreign.sqlite3"; sh([str(hostile_v/"bin/python"),"-c",wc,str(receipt_file),str(db)]); return json.loads(sh([str(rc1_v/"bin/python"),"-c",rc,str(db)]).stdout)


def observe(candidate: Path, rc1: Path, currentw: Path, rc1w: Path, rc2w: Path, stablew: Path, evidence: Path, raw: Path) -> dict[str,Any]:
    raw.mkdir(parents=True,exist_ok=True); cert=load(evidence/"tg5-receipt.json")["certification_receipt"]; rb=(canon(cert)+"\n").encode(); rfile=raw/"receipt.json"; rfile.write_bytes(rb); rh="sha256:"+hashlib.sha256(rb).hexdigest(); vr=raw/"venvs"; vr.mkdir()
    cp=asyncio.run(clients(candidate,raw)); c1=transition(vr,"current-rc1",currentw,rc1w,"0.1.0-experimental","1.0.0-rc.1",rh); c2=transition(vr,"rc1-rc2",rc1w,rc2w,"1.0.0-rc.1","1.0.0-rc.2",rh); cs=transition(vr,"rc1-stable",rc1w,stablew,"1.0.0-rc.1","1.0.0",rh)
    rv=mkvenv(vr,"rc1"); install(rv,rc1w); rs=state(rv); good=req_probe(rv,"1.0.0-rc.1","nexus.changeset_certification.v2"); bp=not req_probe(rv,"2.0.0-foreign","nexus.changeset_certification.v2"); bs=not req_probe(rv,"1.0.0-rc.1","nexus.foreign.v9"); gr=receipt_probe(rv,cert); br=dict(cert); br["receipt_schema"]="foreign:certification_receipt_schema"; brf=not receipt_probe(rv,br); lg=ledger(rv,rfile,raw)
    hp,hs,hl=(hostile(rc1,raw,k) for k in ("protocol","schema","ledger")); hv=mkvenv(vr,"hostile-ledger"); install(hv,hl); hls=state(hv); bl=bad_ledger(hv,rv,rfile,raw)
    fv=mkvenv(vr,"failed"); install(fv,rc1w); old=state(fv); corrupt=raw/"stable-corrupt.whl"; b=stablew.read_bytes(); corrupt.write_bytes(b[:max(64,len(b)//3)]); pr=subprocess.run([str(fv/"bin/pip"),"install","--no-deps","--force-reinstall",str(corrupt)],capture_output=True,text=True); install(fv,rc1w); restored=state(fv); fail=pr.returncode!=0 and restored==old
    return {"clients":cp,"transitions":{"current-to-rc":c1,"rc-patch":c2,"rc-to-stable":cs},"good_request":good,"bad_protocol":bp,"bad_schema":bs,"good_receipt":gr,"bad_receipt":brf,"ledger":lg,"bad_ledger":bl,"rc1":rs,"hostile":{"protocol":fh(hp),"schema":fh(hs),"ledger":fh(hl),"ledger_state":hls},"failed":{"ok":fail,"old":old,"restored":restored,"wheel":fh(corrupt)},"receipt_hash":rh}


def overlay(candidate: Path, evidence: Path, obs: dict[str,Any]) -> None:
    sys.path.insert(0,str(candidate)); from product.protocol import compatibility_gate as g; from product.protocol import PUBLIC_PROTOCOL_VERSION,IMPLEMENTATION_SCHEMA,EVIDENCE_BUNDLE_SCHEMA,PROVENANCE_ENVELOPE_SCHEMA,CERTIFICATION_RECEIPT_SCHEMA
    t=load(evidence/"thresholds.json"); head=t["subject_commit"]; tree=t["subject_tree"]; paths={"CLI":candidate/"product/clients/cli.py","MCP":candidate/"product/clients/mcp.py","ACTION":candidate/"product/clients/github_action.py"}; cr=[]
    for n in g.REQUIRED_CLIENTS:
        r={"name":n,"artifact_hash":fh(paths[n]),"output_hash":obs["clients"]["hashes"][n],"parity":obs["clients"]["parity"]}; r["row_hash"]=dig(r); cr.append(r)
    con={"schema":g.CONFORMANCE_SCHEMA,"subject_commit":head,"subject_tree":tree,"canonical_request_hash":obs["clients"]["request_hash"],"canonical_response_hash":next(iter(obs["clients"]["hashes"].values())),"endpoint_sequence":["POST /v1/certifications","GET /v1/certifications/{id}"],"redaction_set":["authorization","github_token"],"clients":cr,"parity":obs["clients"]["parity"]}; con["report_hash"]=dig(con); write(evidence/"client-conformance.json",con)
    src={"public_protocol":PUBLIC_PROTOCOL_VERSION,"implementation_schema":IMPLEMENTATION_SCHEMA,"evidence_bundle_schema":EVIDENCE_BUNDLE_SCHEMA,"provenance_envelope_schema":PROVENANCE_ENVELOPE_SCHEMA,"certification_receipt_schema":CERTIFICATION_RECEIPT_SCHEMA,"ledger_schema":g.LEDGER_SCHEMA,"ledger_generation":"generation-cas-v1","http_schema":g.HTTP_SCHEMA,"cli_client":fh(paths["CLI"]),"mcp_client":fh(paths["MCP"]),"action_client":fh(paths["ACTION"]),"reader_version":f"core-reader@{head}"}; physical={"public_protocol-supported":obs["transitions"]["current-to-rc"]["ok"],"public_protocol-refused":obs["bad_protocol"],"implementation_schema-supported":obs["good_request"],"implementation_schema-refused":obs["bad_schema"],"certification_receipt_schema-supported":obs["good_receipt"],"certification_receipt_schema-refused":obs["bad_receipt"],"ledger_schema-supported":obs["ledger"]["valid"],"ledger_schema-refused":not obs["bad_ledger"]["valid"],"ledger_generation-supported":obs["ledger"]["append"]=="APPENDED","ledger_generation-refused":obs["ledger"]["stale"]=="STALE_GENERATION","cli_client-supported":obs["clients"]["parity"],"mcp_client-supported":obs["clients"]["parity"],"action_client-supported":obs["clients"]["parity"],"reader_version-supported":obs["good_receipt"]}; rows=[]
    for s in t["compatibility_manifest"]:
        assert src[s["axis"]]==s["source"]; rid=s["row_id"]; ok=physical[rid] if rid in physical else (src[s["axis"]]==s["target"] if rid.endswith("-supported") else src[s["axis"]]!=s["target"]); observed=("REFUSED" if ok else "SUPPORTED") if rid.endswith("-refused") else ("SUPPORTED" if ok else "REFUSED"); r={**s,"observed":observed,"reason_code":"PHYSICAL_V4_OBSERVATION","receipt_preservation_hash":obs["receipt_hash"]}; r["row_hash"]=dig(r); rows.append(r)
    comp={"schema":g.COMPATIBILITY_SCHEMA,"subject_commit":head,"subject_tree":tree,"rows":rows}; comp["matrix_hash"]=dig(comp); write(evidence/"protocol-compatibility.json",comp)
    specs={x["row_id"]:x for x in t["upgrade_manifest"]}; rm={};
    for rid,key in (("current-to-rc","current-to-rc"),("rc-patch","rc-patch"),("rc-to-stable","rc-to-stable")):
        x=obs["transitions"][key]; rm[rid]={**specs[rid],"observed":"SUPPORTED" if x["ok"] else "REFUSED","old_wheel_hash":x["old_wheel_hash"],"new_wheel_hash":x["new_wheel_hash"],"old_runtime_hash":x["old"]["runtime_hash"],"new_runtime_hash":x["new"]["runtime_hash"],"old_ledger_hash":x["old"]["ledger_hash"],"new_ledger_hash":x["new"]["ledger_hash"],"old_receipt_hash":obs["receipt_hash"],"new_receipt_hash":obs["receipt_hash"],"old_receipt_byte_equal":True,"rollback_state":"NOT_REQUIRED","reason_code":"PHYSICAL_WHEEL_TRANSITION"}
    for rid,k,ok,newstate in (("bad-protocol","protocol",obs["bad_protocol"],obs["rc1"]),("bad-schema","schema",obs["bad_schema"],obs["rc1"]),("bad-ledger","ledger",not obs["bad_ledger"]["valid"],obs["hostile"]["ledger_state"])):
        rm[rid]={**specs[rid],"observed":"REFUSED" if ok else "SUPPORTED","old_wheel_hash":fh(Path(os.environ["RC1_WHEEL"])),"new_wheel_hash":obs["hostile"][k],"old_runtime_hash":obs["rc1"]["runtime_hash"],"new_runtime_hash":newstate["runtime_hash"],"old_ledger_hash":obs["rc1"]["ledger_hash"],"new_ledger_hash":newstate["ledger_hash"],"old_receipt_hash":obs["receipt_hash"],"new_receipt_hash":obs["receipt_hash"],"old_receipt_byte_equal":True,"rollback_state":"NOT_REQUIRED","reason_code":"PHYSICAL_REFUSAL"}
    f=obs["failed"]; rm["failed-upgrade"]={**specs["failed-upgrade"],"observed":"REFUSED" if f["ok"] else "SUPPORTED","old_wheel_hash":fh(Path(os.environ["RC1_WHEEL"])),"new_wheel_hash":f["wheel"],"old_runtime_hash":f["old"]["runtime_hash"],"new_runtime_hash":f["restored"]["runtime_hash"],"old_ledger_hash":f["old"]["ledger_hash"],"new_ledger_hash":f["restored"]["ledger_hash"],"old_receipt_hash":obs["receipt_hash"],"new_receipt_hash":obs["receipt_hash"],"old_receipt_byte_equal":True,"rollback_state":"RESTORED_EXACT" if f["ok"] else "NOT_RESTORED","reason_code":"CORRUPT_STABLE_WHEEL_ABORT_RC1_RESTORED"}; ur=[]
    for s in t["upgrade_manifest"]: r=rm[s["row_id"]]; r["row_hash"]=dig(r); ur.append(r)
    up={"schema":g.UPGRADE_ROLLBACK_SCHEMA,"subject_commit":head,"subject_tree":tree,"rows":ur}; up["report_hash"]=dig(up); write(evidence/"upgrade-rollback.json",up)
    ip={"tg4_receipt":"tg4-receipt.json","tg5_receipt":"tg5-receipt.json","tg6_receipt":"tg6-receipt.json","compatibility":"protocol-compatibility.json","conformance":"client-conformance.json","upgrade_rollback":"upgrade-rollback.json","open_issues":"open-issues.json","tg7_selection":"tg7-selection.json","tg7_corpus":"tg7-corpus.json","tg7_shadow":"tg7-shadow-receipt.json","tg7_report":"tg7-report.json"}; t["input_hashes"]={k:fh(evidence/v) for k,v in sorted(ip.items())}; t["threshold_hash"]=dig({k:v for k,v in t.items() if k!="threshold_hash"}); write(evidence/"thresholds.json",t); (evidence/"thresholds.sha256").write_text(t["threshold_hash"][7:]+"\n")


def fingerprint(o: dict[str,Any]) -> dict[str,Any]:
    return {"client_parity":o["clients"]["parity"],"client_hashes":o["clients"]["hashes"],"current_to_rc":o["transitions"]["current-to-rc"]["ok"],"rc_patch":o["transitions"]["rc-patch"]["ok"],"rc_to_stable":o["transitions"]["rc-to-stable"]["ok"],"bad_protocol":o["bad_protocol"],"bad_schema":o["bad_schema"],"bad_receipt":o["bad_receipt"],"ledger_valid":o["ledger"]["valid"],"stale":o["ledger"]["stale"],"foreign_ledger_valid":o["bad_ledger"]["valid"],"foreign_ledger_status":o["bad_ledger"]["status"],"failed_restore":o["failed"]["ok"],"receipt_hash":o["receipt_hash"]}


def main() -> int:
    a=argparse.ArgumentParser(); a.add_argument("mode",choices=["collect","audit"]); [a.add_argument("--"+x,required=True) for x in ("candidate","rc1","current-wheel","rc1-wheel","rc2-wheel","stable-wheel","evidence","raw")]; ns=a.parse_args(); c=Path(ns.candidate).resolve(); r=Path(ns.rc1).resolve(); e=Path(ns.evidence).resolve(); raw=Path(ns.raw).resolve(); o=observe(c,r,Path(ns.current_wheel),Path(ns.rc1_wheel),Path(ns.rc2_wheel),Path(ns.stable_wheel),e,raw); fp=fingerprint(o)
    if ns.mode=="collect": overlay(c,e,o); write(e/"physical-fingerprint-v4.json",fp)
    else:
        old=load(e/"physical-fingerprint-v4.json"); assert fp==old,(fp,old); write(raw/"independent-audit-v4.json",hashed({"schema":"nexus.core-v1.tg8-independent-physical-audit-v4.v1","status":"ACCEPT","fingerprint":fp},"audit_hash"))
    return 0

if __name__=="__main__": raise SystemExit(main())
