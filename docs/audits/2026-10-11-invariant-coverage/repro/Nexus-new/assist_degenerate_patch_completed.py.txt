"""Repro: unified_mcp_gateway assist jobs use output_schema {"type":"object","required":["patch"]}
(_assist_submit, line ~2753). _assist_refresh marks status COMPLETED iff
returncode==0 and _decode_assist_payload(...)!=None and schema_valid. A degenerate
provider answer with an empty/null patch therefore becomes COMPLETED (next_action
'none', attention_required False) instead of failing closed with retry_required."""
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/user/Nexus-new")
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway as G
schema = {"type": "object", "required": ["patch"]}
for out in ['{"patch": ""}', '{"patch": null}', '{"patch": "I cannot help with that."}', 'garbage, no json']:
    parsed = G._decode_assist_payload(out, "codex", require_patch=True)
    ok, err = G._validate_output_schema(parsed, schema)
    status = "COMPLETED" if parsed is not None and ok else "FAILED"
    action = G._assist_action({"status": status})
    print(f"{out!r:40} -> status={status} next_action={action['next_action']} attention={action['attention_required']}")
