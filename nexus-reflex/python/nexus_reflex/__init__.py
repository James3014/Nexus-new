import subprocess
import json
import os
import sys

# Get the path to the bundled rust binary
def _get_bin_path():
    base_path = os.path.dirname(__file__)
    bin_path = os.path.join(base_path, "scripts", "nexus-reflex-core")
    if not os.path.exists(bin_path):
        raise FileNotFoundError(f"Nexus-Reflex core binary not found at {bin_path}")
    return bin_path

def scan(path="."):
    """Perform a high-speed symbolic scan of the given directory."""
    bin_path = _get_bin_path()
    try:
        result = subprocess.run([bin_path, path], capture_output=True, text=True, check=True)
        # Filter out Nexus logs and find the JSON start
        lines = result.stdout.splitlines()
        json_lines = [l for l in lines if l.startswith("{") or l.startswith("  ") or l.strip().startswith("}")]
        return json.loads("".join(json_lines))
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"// Nexus-Reflex Python Bridge Error: {e}", file=sys.stderr)
        return None

def apply_action(action_request):
    """Apply a governed physical action using the ReflexRequest protocol."""
    bin_path = _get_bin_path()
    
    # Smart wrapping
    if isinstance(action_request, dict):
        # If 'action' key isn't present but 'type' is, it's a flat action dict
        if "action" not in action_request and "type" in action_request:
            # Extract metadata and nested action
            meta = {
                "version": action_request.get("version", "1.0"),
                "request_id": action_request.get("request_id", "REQ-PY"),
                "actor": action_request.get("actor", "Python-SDK"),
                "intent": action_request.get("intent", "SDK Action"),
                "dry_run": action_request.get("dry_run", False)
            }
            # The rest of the dict is the action
            action_data = {k: v for k, v in action_request.items() if k not in ["version", "request_id", "actor", "intent", "dry_run"]}
            meta["action"] = action_data
            payload = json.dumps(meta)
        else:
            # Already structured or missing 'type'
            payload = json.dumps(action_request)
    else:
        payload = action_request

    try:
        result = subprocess.run([bin_path, "--action", payload], capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"// Nexus-Reflex Python Bridge Error: {e.stderr}", file=sys.stderr)
        return None
