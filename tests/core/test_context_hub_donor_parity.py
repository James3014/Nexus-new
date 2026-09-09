from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from nexus.core.context_hub import ContextDependencies, ContextHub


class State:
    task_id = "task-1"
    metadata = {"task_description": "parser repair", "chat_history": ["one", "two"]}
    steps_history = [SimpleNamespace(summary="researched", phase="X", status="completed")]
    tdd_status = "green"
    superpowers_plan = {}

    def get_conversation_metadata(self):
        return {"conversation_id": "conv-1", "user_goal": "repair parser", "current_question": "how?", "needs_research": False}


class Knowledge:
    def recommend_skills(self, summary, hotspots): return ["skill:parser"]
    def inject_wisdom_prior(self, summary, hotspots): return "prior"

class Diagnosis:
    summary = "parser failure"
    pseudo_flows = ["inspect", "repair"]
    hotspots = ["parser.py"]

class Research:
    key_findings = ["fixture finding"]


def test_runtime_context_hub_matches_donor_core_packs(tmp_path: Path, monkeypatch):
    state = State()
    memory = {"reminders": ["phase"], "total_sources": 1}
    wiki = {"context": "wiki:parser failure", "selected_sources": []}
    knowledge = Knowledge()
    class Memory:
        def cached_search(self, _key): return memory
    class Wiki:
        def retrieve(self, _query, max_results=3): return wiki
    monkeypatch.setattr("nexus.core.state_io.StateIO.load_global_state", lambda _self: state)
    monkeypatch.setattr("nexus.core.context_text_store.ContextTextStore.load_program_rules", lambda _self, _name="program.md": "rules:program.md")
    monkeypatch.setattr("nexus.core.context_hub.ToonRenderer.render", staticmethod(lambda _state, aggression=0.0: "toon-summary"))
    hub = ContextHub(
        str(tmp_path),
        deps=ContextDependencies(memory_service=Memory(), knowledge_injector=knowledge, wiki_knowledge_agent=Wiki()),
        strict_deps=True,
    )
    hub.runtime_hub.deps = hub.runtime_hub.deps.__class__(
        **{**hub.runtime_hub.deps.__dict__, "clock": lambda: "fixed"}
    )
    donor_script = r'''
import importlib.util, json
from pathlib import Path
from types import SimpleNamespace
p=Path("/private/tmp/astra-production-integrated-20260909/nexus/core/context_hub.py")
s=importlib.util.spec_from_file_location("donor",p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
class S:
 task_id="task-1"; metadata={"task_description":"parser repair","chat_history":["one","two"]}; steps_history=[SimpleNamespace(summary="researched",phase="X",status="completed")]; tdd_status="green"; superpowers_plan={}
 def get_conversation_metadata(self): return {"conversation_id":"conv-1","user_goal":"repair parser","current_question":"how?","needs_research":False}
    class K:
     def recommend_skills(self,s,h): return ["skill:parser"]
     def inject_wisdom_prior(self,s,h): return "prior"
    class Diagnosis:
     summary="parser failure"; pseudo_flows=["inspect","repair"]; hotspots=["parser.py"]
    class Research:
     key_findings=["fixture finding"]
state=S(); memory={"reminders":["phase"],"total_sources":1}; wiki={"context":"wiki:parser failure","selected_sources":[]}; k=K()
d=m.ContextHub.__new__(m.ContextHub); d.state_io=SimpleNamespace(load_global_state=lambda:state); d._text_store=SimpleNamespace(load_program_rules=lambda n="program.md":"rules:program.md"); d.memory_service=SimpleNamespace(cached_search=lambda _key:memory, aggregate_memory=lambda:memory); d.nexus_fs=None; d.knowledge_injector=k; d.wiki_knowledge_agent=None; d.belief_engine=None; d.run_dir=None
d._retrieve_wiki_context=lambda q,max_results=3:wiki; d._inject_memory_reminders=lambda phase:memory; d.load_program_rules=lambda md_path="program.md":"rules:program.md"; m.ToonRenderer=SimpleNamespace(render=lambda st,aggression=0.0:"toon-summary"); m.prune_dialogue=lambda h:"pruned-history"
out={"feature":d.assemble_feature_pack({"steps":["inspect"]}),"diag":d.assemble_diag_pack([{"file":"parser.py","message":"bad"}],"parser failure"),"research":d.assemble_research_pack("parser",[{"fact":1}]),"conversation":d.assemble_conversation_pack(),"repair":d.assemble_repair_pack(Diagnosis(),[{"reflection":1},{"reflection":2},{"reflection":3}],Research())}
print(json.dumps(out,sort_keys=True,default=str))
'''
    env = {"PYTHONPATH": "/private/tmp/astra-production-integrated-20260909"}
    proc = subprocess.run([sys.executable, "-c", donor_script], check=True, capture_output=True, text=True, env=env)
    donor = json.loads(proc.stdout)
    def normalized(value):
        value = dict(value)
        value.pop("timestamp", None)
        return value

    assert normalized(hub.assemble_feature_pack({"steps": ["inspect"]})) == normalized(donor["feature"])
    assert hub.assemble_diag_pack([{"file": "parser.py", "message": "bad"}], "parser failure") == donor["diag"]
    assert hub.assemble_research_pack("parser", [{"fact": 1}]) == donor["research"]
    assert normalized(hub.assemble_conversation_pack()) == normalized(donor["conversation"])
    assert hub.assemble_repair_pack(Diagnosis(), [{"reflection": 1}, {"reflection": 2}, {"reflection": 3}], Research()) == donor["repair"]
