import sys
import json

def handle_request(request):
    method = request.get("method")
    req_id = request.get("id")
    params = request.get("params", {})
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "serverInfo": {"name": "mock", "version": "1.0.0"}
            }
        }
        
    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if tool_name == "error_tool":
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": "Triggered error"}}
        if tool_name == "malformed_tool":
            print("not json")
            sys.stdout.flush()
            return None
        if tool_name == "timeout_tool":
            import time
            time.sleep(2)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": "too late"}]}}
            
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps({"status": "executed", "tool": f"mempalace_{tool_name}", "args": arguments})}]
            }
        }
        
    if method == "exit":
        sys.exit(0)
        
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            if response:
                print(json.dumps(response))
                sys.stdout.flush()
        except Exception:
            pass

if __name__ == "__main__":
    main()
