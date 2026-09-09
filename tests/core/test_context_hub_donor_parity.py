from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
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


def test_runtime_context_hub_matches_donor_core_packs(tmp_path: Path):
    state = State()
    memory = {"reminders": ["phase"], "total_sources": 1}
    wiki = {"context": "wiki:parser failure", "selected_sources": []}
    knowledge = Knowledge()
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)
    deps = replace(
        hub.runtime_hub.deps,
        state_reader=lambda: state,
        memory_reader=lambda _phase: memory,
        wiki_reader=lambda _query, max_results=3: wiki,
        knowledge_reader=knowledge,
        renderer=lambda _state, aggression=0.0: "toon-summary",
        dialogue_pruner=lambda _history: "pruned-history",
        clock=lambda: "fixed",
    )
    hub.runtime_hub.deps = deps
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
state=S(); memory={"reminders":["phase"],"total_sources":1}; wiki={"context":"wiki:parser failure","selected_sources":[]}; k=K()
d=m.ContextHub.__new__(m.ContextHub); d.state_io=SimpleNamespace(load_global_state=lambda:state); d._text_store=SimpleNamespace(load_program_rules=lambda n="program.md":"rules:program.md"); d.memory_service=None; d.nexus_fs=None; d.knowledge_injector=k; d.wiki_knowledge_agent=None; d.belief_engine=None; d.run_dir=None
d._retrieve_wiki_context=lambda q,max_results=3:wiki; d._inject_memory_reminders=lambda phase:memory; d.load_program_rules=lambda md_path="program.md":"rules:program.md"; m.ToonRenderer=SimpleNamespace(render=lambda st,aggression=0.0:"toon-summary"); m.prune_dialogue=lambda h:"pruned-history"
out={"feature":d.assemble_feature_pack({"steps":["inspect"]}),"diag":d.assemble_diag_pack([{"file":"parser.py","message":"bad"}],"parser failure"),"research":d.assemble_research_pack("parser",[{"fact":1}])}
print(json.dumps(out,sort_keys=True,default=str))
'''
    env = {"PYTHONPATH": "/private/tmp/astra-production-integrated-20260909"}
    proc = subprocess.run([sys.executable, "-c", donor_script], check=True, capture_output=True, text=True, env=env)
    donor = json.loads(proc.stdout)
    assert hub.runtime_hub.assemble_feature_pack({"steps": ["inspect"]}) == donor["feature"]
    assert hub.runtime_hub.assemble_diag_pack([{"file": "parser.py", "message": "bad"}], "parser failure") == donor["diag"]
    assert hub.runtime_hub.assemble_research_pack("parser", [{"fact": 1}]) == donor["research"]
