
import sys
import json
import uuid
import requests

MCP_URL = "http://127.0.0.1:12307/mcp"
TOKEN = "8d0bdae063e8912d5d089c5c694de31653063ba9ca73561cce1ef0ce60ccda7d"

def parse_sse(text):
    for line in text.split('\n'):
        if line.startswith("data: "):
            return json.loads(line[6:])
    return None

def run():
    if len(sys.argv) < 2:
        print("Usage: python browser_lite_util.py <tool_name> [json_arguments]")
        sys.exit(1)
    
    tool_name = sys.argv[1]
    tool_args = {}
    if len(sys.argv) > 2:
        tool_args = json.loads(sys.argv[2])

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    })

    # 1. Initialize
    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "nexus-util", "version": "1.0.0"}
        }
    }
    
    r1 = session.post(MCP_URL, json=init_payload, timeout=10)
    session_id = r1.headers.get("mcp-session-id")
    if not session_id:
        print("Error: No mcp-session-id returned.")
        return
    
    session.headers["mcp-session-id"] = session_id

    # 2. Notification: initialized
    notify_payload = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    }
    session.post(MCP_URL, json=notify_payload, timeout=10)

    # 3. Call Tool
    call_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": tool_args
        }
    }
    
    r2 = session.post(MCP_URL, json=call_payload, timeout=60)
    if r2.status_code == 200:
        data = parse_sse(r2.text)
        if data:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(f"No data in SSE response: {r2.text}")
    else:
        print(f"Tool Call Failed: {r2.status_code} {r2.text}")

if __name__ == "__main__":
    run()
