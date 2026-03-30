import sys
import os
from pathlib import Path
# Ensure we can import from the project
sys.path.append(os.getcwd())

from nexus.services.gateway import BattlesuitGateway as LLMClient

def report_metrics():
    client = LLMClient(project_root=os.getcwd())
    anti_tokens = client.get_anti_token_estimate()
    print(f"--- RESOURCE REPORT ---")
    print(f"Commander (Anti) Token Estimate: {anti_tokens} tokens")
    print(f"Note: This is an estimated cumulative usage based on local session logs.")

if __name__ == "__main__":
    report_metrics()
