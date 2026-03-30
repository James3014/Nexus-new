import sys
import os
from pathlib import Path

# Add current dir to path
sys.path.append(str(Path.cwd()))

from nexus.services.gateway import BattlesuitGateway as LLMClient

def probe():
    bin_path = "/Users/jameschen/.npm-global/bin/codex"
    client = LLMClient(bin_path=bin_path, project_root=".")
    print(f"Using LLM Binary: {client.llm_bin}")
    
    prompt = "Hello, please provide a simple JSON with status: PASS and include the line 'Total Session Tokens: 100' in your response for testing purposes."
    payload = " { \"test\": true } "
    
    data, raw_output = client.ask(prompt, payload, phase="P")
    
    print("--- RAW OUTPUT START ---")
    print(raw_output)
    print("--- RAW OUTPUT END ---")
    
    print(f"Captured Token Status: {data.get('token_capture_status')}")
    print(f"Captured Tokens Used: {data.get('tokens_used')}")

if __name__ == "__main__":
    probe()
