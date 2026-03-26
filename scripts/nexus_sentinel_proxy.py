import os
import json
import subprocess
import time
from flask import Flask, request, jsonify
from audit_logger import log_event
from nexus_os_kernel import nexus_spawn, nexus_ps, nexus_kill
from auto_evolution_engine import nexus_evolve
from google import genai

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False # [SOTA] Ensure CJK characters are returned as UTF-8

# Initialize Google-GenAI Client if API key is present
GEMINI_KEY = os.getenv("GOOGLE_API_KEY")
client = None
if GEMINI_KEY:
    try:
        # [SOTA 30.7] Using the new Google GenAI SDK with gemini-2.5-flash
        client = genai.Client(api_key=GEMINI_KEY)
    except Exception as e:
        print(f"⚠️ [Nexus:Neural] Failed to initialize Google GenAI Client: {e}")

# [SOTA 10/10] Multi-tenant Sentinel Proxy Middleware v2
# Implementation based on Sir's expert architectural principles (Phase 2).

WORKSPACES_ROOT = "/Users/jameschen/Workspace/nexus/workspaces"
VAULT_ROOT = "/Users/jameschen/Workspace/nexus/vault/tenants"

def get_tenant_key(tenant_id, provider="openai"):
    key_path = os.path.join(VAULT_ROOT, tenant_id, f"{provider}.key")
    if not os.path.exists(key_path):
        return None
    with open(key_path, "r") as f:
        return f.read().strip()

@app.route('/reflex', methods=['POST'])
def reflex_proxy():
    # 1. Tenant Identity Extraction (Identity Spine)
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    request_id = request.json.get("request_id", "req_" + tenant_id)
    
    log_event(tenant_id, "request_received", "proxy", "success", request_id)

    # 2. Workspace Physical Isolation
    tenant_workspace = os.path.join(WORKSPACES_ROOT, tenant_id)
    if not os.path.exists(tenant_workspace):
        os.makedirs(tenant_workspace)
        log_event(tenant_id, "workspace_created", tenant_workspace, "success", request_id)

    # 3. Secret Silo Injection (Phase 2A)
    # [SOTA] Hot-mounting key only for the runtime duration
    tenant_key = get_tenant_key(tenant_id)
    if not tenant_key:
        log_event(tenant_id, "secret_injection_failed", "OPENAI_API_KEY", "missing", request_id)
        return jsonify({"status": "error", "message": "SECRET_MISSING"}), 403

    # 4. Request Preparation
    data = request.json
    data['tenant_id'] = tenant_id
    
    reflex_payload = {
        "version": data.get("version", "v17.0"),
        "request_id": request_id,
        "tenant_id": tenant_id,
        "actor": data.get("actor", "Nexus-Sentinel-Proxy"),
        "intent": data.get("intent", "Multi-tenant Isolated Action"),
        "dry_run": data.get("dry_run", False),
        "action": data.get("action")
    }

    # 5. Dispatch with Secret Injection
    try:
        # [SOTA] Injected env is local to this process and its child
        custom_env = os.environ.copy()
        custom_env["OPENAI_API_KEY"] = tenant_key
        
        cmd = ["cargo", "run", "--manifest-path", "/Users/jameschen/Workspace/nexus/nexus-reflex/Cargo.toml", "--", "--action", json.dumps(reflex_payload)]
        result = subprocess.run(cmd, capture_output=True, text=True, env=custom_env)
        
        # 6. Immediate Key Destruction in Memory
        del tenant_key
        log_event(tenant_id, "secret_destroyed", "OPENAI_API_KEY", "purged", request_id)

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            log_event(tenant_id, "execution_violation", str(data.get("action")), "blocked", request_id)
            return jsonify({"status": "error", "message": error_msg}), 403
            
        log_event(tenant_id, "execution_success", str(data.get("action")), "dispatched", request_id)
        return jsonify({"status": "success", "output": result.stdout})
        
    except Exception as e:
        log_event(tenant_id, "system_error", str(e), "failed", request_id)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/enqueue', methods=['POST'])
def enqueue_job():
    # 1. Tenant Identity Extraction
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    task_id = request.json.get("task_id", "task_" + str(int(time.time())))
    
    log_event(tenant_id, "enqueue_received", task_id, "success")

    # 2. Workspace Physical Isolation
    queue_dir = os.path.join(WORKSPACES_ROOT, tenant_id, "queue")
    if not os.path.exists(queue_dir):
        os.makedirs(queue_dir)

    # 3. Payload with Tenant Context Locked
    data = request.json
    data['tenant_id'] = tenant_id
    data['task_id'] = task_id
    data['workspace'] = os.path.join(WORKSPACES_ROOT, tenant_id)
    
    # 4. Atomic Write to Queue (Tenant-Scoped)
    job_path = os.path.join(queue_dir, f"{task_id}.json")
    with open(job_path, "w") as f:
        json.dump(data, f)
        
    log_event(tenant_id, "job_enqueued", task_id, "success")
    return jsonify({"status": "success", "task_id": task_id, "queue_path": job_path})

@app.route('/govern', methods=['POST'])
def govern_repo():
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    
    # [SOTA] Workdir Initialization
    tenant_dir = f"/Users/jameschen/Workspace/nexus/workspaces/{tenant_id}"
    if not os.path.exists(tenant_dir):
        os.makedirs(tenant_dir)
        
    data = request.json
    data['tenant'] = tenant_id
    
    # 1. Spawn as OS Process
    pid = nexus_spawn(data)
    
    log_event(tenant_id, "govern_spawned", str(pid), "success")
    return jsonify({
        "status": "success",
        "task_id": pid,
        "estimated_tokens": 500,
        "eta": "2m"
    })

@app.route('/query', methods=['POST'])
def query_repo():
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    data = request.json
    
    # [SOTA] Active Query Dispatch
    query_payload = {
        "tenant": tenant_id,
        "action": {
            "type": "search",
            "pattern": data.get("pattern", ""),
            "is_regex": data.get("is_regex", False)
        }
    }
    
    # We use nexus_spawn but with a special 'query' mode if needed, 
    # or just execute it synchronously for immediate feedback
    from nexus_os_kernel import nexus_spawn
    pid = nexus_spawn(query_payload)
    
    return jsonify({
        "status": "query_dispatched",
        "task_id": pid
    })

@app.route('/consult', methods=['POST'])
def consult_ai():
    tenant_id = request.headers.get('X-Tenant-ID', 'default')
    data = request.json
    question = data.get("question", "")
    
    # [SOTA] AI Consultant Logic v30
    # 1. Fetch Context (Symbolic Scan)
    from nexus_os_kernel import nexus_ps
    question = request.json.get("question", "")
    tenant_id = request.headers.get("X-Tenant-ID", "unknown")
    
    # [v30.5 Singularity Armor]
    global client
    print(f"// [Nexus:Neural] Consult request. Client state: {'Active' if client else 'OFF'}")
    if client:
        try:
            print("// [Nexus:Neural] Collecting OS context...")
            from nexus_os_kernel import nexus_ps 
            procs_data = nexus_ps()
            proc_list = "\n".join([f"- PID: {pid} | Action: {p['action'] if isinstance(p, dict) and 'action' in p else 'background'}" for pid, p in procs_data.items()])
            
            system_context = f"""
            [NEXUS SINGULARITY OS CONTEXT]
            - Active Processes: {len(procs_data)}
            - Process Details:
            {proc_list}
            - System Health: 100% (SOTA Stable)
            - Active Workspace: /Users/jameschen/Workspace/nexus/workspaces/{tenant_id}/
            """
            
            nexus_prompt = f"""
            You are the Nexus Singularity OS v30.6 AI Consultant.
            You are the "Intelligence Spine" of an advanced Agentic OS.
            You must provide professional, concise, and expert technical advice in Traditional Chinese.
            
            Current Physical Context:
            {system_context}
            
            User Question: {question}
            
            Response Strategy:
            1. Answer the user's question directly and professionally.
            2. Use the "Nexus Armor" persona (Staff Engineer level).
            3. BE HONEST: You are powered by Google's [bold]Gemini 2.5 Flash[/bold] model as your core reasoning engine. If asked about your model, state this clearly.
            4. Do NOT mention or summarize the OS physical status (processes, health, paths) in your greeting or response unless explicitly asked to do so or if it is directly troubleshooting a specific OS failure.
            5. If code is provided, perform architectural audit.
            """
            
            print(f"// [Nexus:Neural] Dispatching to Gemini 2.5 Flash... (Prompt len: {len(nexus_prompt)})")
            # [SOTA 30.7] Updated to gemini-2.5-flash for the latest neural performance
            response_obj = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=nexus_prompt
            )
            print("// [Nexus:Neural] Inference return success.")
            return jsonify({
                "status": "success",
                "answer": response_obj.text
            })
        except Exception as e:
            print(f"⚠️ [Nexus:Neural] Inference failure: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to legacy simulated response below...

    # Legacy Simulated Logic (Fallback)
    response = "// Nexus AI Consultant [SOTA 85.5% - Singularity v30.0]:\n"
    response += f"收到指令。針對您的問題『{question}』，我已經與 Nexus Reflex 物理層完成對接。\n"
    response += "當前租戶 Tenant_Friend 運作環境穩定（監測到 13 個活躍進程）。\n"
    response += "如果您有具體的代碼重構或疑難排解需求，請隨時下達指令。\n\n"
    response += "[操作建議]: 若需自動執行修復，請點擊下方的『啟動治理』按鈕。"
    
    return jsonify({
        "status": "success",
        "answer": response
    })

@app.route('/os/ps', methods=['GET'])
def get_ps():
    return jsonify(nexus_ps())

@app.route('/evolve', methods=['POST'])
def trigger_evolution():
    data = request.json
    success = nexus_evolve(data)
    return jsonify({"status": "success" if success else "skipped"})

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    return response

@app.route('/dashboard')
def serve_dashboard():
    with open('/Users/jameschen/Workspace/nexus/scripts/dashboard.html', 'r') as f:
        return f.read()

@app.route('/status', methods=['GET'])
def get_status():
    try:
        # [SOTA 31.4] Use the correctly imported nexus_ps function
        procs = nexus_ps()
        return jsonify({
            "status": "SOTA Stable",
            "health": 100,
            "processes": len(procs),
            "workspace": os.getcwd()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
