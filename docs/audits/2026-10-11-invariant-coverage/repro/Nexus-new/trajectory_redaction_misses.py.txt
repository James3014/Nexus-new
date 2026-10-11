"""Repro: trajectory_continuity._redact_value is the only redaction applied to
run_cli_worker stdout/stderr persisted by bind_trajectory_step_result. Common
secret formats survive it."""
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/user/Nexus-new")
from nexus.research.clm_system_one.trajectory_continuity import _redact_value
samples = {
  "control_ghp": "token ghp_" + "A"*36,
  "anthropic_key": "sk-ant-api03-" + "A"*40,
  "openai_proj_key": "sk-proj-" + "B"*40,
  "github_fine_grained_pat": "github_pat_11ABCDEFG0" + "C"*60,
  "json_token_field_in_stdout": '{"access_token": "ya29.' + "D"*30 + '"}',
  "google_api_key": "AIza" + "E"*35,
  "aws_access_key": "AKIA" + "F"*16,
}
out = _redact_value({"stdout": "\n".join(samples.values())})["stdout"].split("\n")
for (k, v), r in zip(samples.items(), out):
    print(f"{k:28} {'REDACTED' if '[REDACTED]' in r else 'LEAKED'}: {r[:60]}")
