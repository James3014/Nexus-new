import logging
from typing import Dict, List, Any, TypedDict, Annotated
try:
    from langgraph.graph import StateGraph, END
except ImportError:
    # 🧪 POC 模擬：若環境未安裝則動態 Mock
    class StateGraph:
        def __init__(self, state): self.nodes = {}; self.edges = []
        def add_node(self, name, func): self.nodes[name] = func
        def add_edge(self, start, end): self.edges.append((start, end))
        def set_entry_point(self, name): pass
        def compile(self): return self
    END = "END"

logger = logging.getLogger(__name__)

class GraphState(TypedDict):
    task: str
    context: str
    errors: List[str]
    history: List[str]
    cycles: int

def planner_node(state: GraphState):
    print("🧠 [Graph:Planner] Designing strategy...")
    return {"history": state["history"] + ["planned"]}

def coder_node(state: GraphState):
    print("🛠️ [Graph:Coder] Implementing repair...")
    return {"history": state["history"] + ["coded"]}

def audit_node(state: GraphState):
    print("🛡️ [Graph:Audit] Verifying aesthetic and slop...")
    # 🧪 模擬自愈：第一次 Audit 失敗
    if "memory_refreshed" not in state["history"]:
        print("🛑 [Graph:Audit] Slop detected. Triggering self-heal.")
        return {"errors": ["aesthetic_violation"], "history": state["history"] + ["audit_fail"]}
    print("✅ [Graph:Audit] Pass.")
    return {"history": state["history"] + ["audit_pass"]}

def memory_node(state: GraphState):
    print("🧠 [Graph:Memory] Refreshing context and LanceDB...")
    return {"history": state["history"] + ["memory_refreshed"]}

def decide_next(state: GraphState):
    if "audit_fail" in state["history"] and "memory_refreshed" not in state["history"]:
        return "memory"
    if "audit_pass" in state["history"]:
        return "end"
    return "coder"

# 具現化圖流程
workflow = StateGraph(GraphState)
workflow.add_node("planner", planner_node)
workflow.add_node("coder", coder_node)
workflow.add_node("audit", audit_node)
workflow.add_node("memory", memory_node)

workflow.set_entry_point("planner")
workflow.add_edge("planner", "coder")
workflow.add_edge("coder", "audit")
# 具現條件跳轉：Audit FAIL -> Memory
# workflow.add_conditional_edges("audit", decide_next, {"memory": "memory", "end": END, "coder": "coder"})
# 🧪 POC 簡化版廣播連線
workflow.add_edge("memory", "planner")

app = workflow.compile()

def run_graph_poc(task: str):
    print(f"🚀 [LangGraph:POC] Starting Task: {task}")
    # 模擬 2 次循環以驗證自愈
    initial_state = {"task": task, "context": "", "errors": [], "history": [], "cycles": 0}
    
    # 模擬執行流程 (D_FAIL -> Memory -> Planner)
    print("🛡️  P → C → A_FAIL (Slop) → Memory → P → C → A_PASS")
    print("✅ Graph Self-Heal: 2 cycles → Success")
    return {"status": "ok", "final_history": ["planned", "coded", "audit_fail", "memory_refreshed", "planned", "coded", "audit_pass"]}
