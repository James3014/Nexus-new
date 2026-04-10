from rich.console import Console
from nexus.pilot_cli.session import PilotSession


def render_main_screen(session: PilotSession) -> str:
    """🛡️ Nexus vSINGULARITY Desk (v24.0 Hardened)"""
    workspace = session.workspace or "(not set)"
    provider = session.provider or "(not set)"
    model = session.model or "(not set)"
    tenant_id = session.tenant_id or "(not set)"
    
    # 🧪 [Round 20 Evolution] Status Line
    status_line = "[SYSTEM: ONLINE]" if session.mode != "error" else "[SYSTEM: FAULT_RECOVERY]"
    
    return (
        f"Nexus Singularity {status_line}\n"
        f"Tenant: {tenant_id} | Provider: {provider} | Model: {model}\n"
        f"Workspace: {workspace} | Mode: {session.mode}\n\n"
        "💡 Tip: Use /adjust to override policy thresholds live.\n"
        "Commands: /mount  /govern  /adjust  /status  /exit\n\n"
        "NEXUS指挥官 >"
    )

def process_human_guidance(user_input: str, task_id: str):
    """🚀 [v24.0] 將使用者意志物理化為硬性約束"""
    import json
    from datetime import datetime
    guidance_path = Path(".nexus/knowledge/human_guidance.jsonl")
    guidance_path.parent.mkdir(parents=True, exist_ok=True)
    
    payload = {
        "timestamp": datetime.now().isoformat(),
        "task_id": task_id,
        "type": "USER_OVERRIDE",
        "content": user_input,
        "priority": "HIGH"
    }
    
    with open(guidance_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(f"🧠 [Desk] Guidance codified and injected into context.")
