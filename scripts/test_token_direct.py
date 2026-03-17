
import os
import sys
from nexus.services.llm import LLMClient

client = LLMClient()
prompt = "Hi, this is a test. Please respond with 'OK'."
diff = "No diff"

print(f"Calling LLM with bin: {client.llm_bin}")
data, raw = client.ask(prompt, diff)

print(f"Data: {data}")
print(f"Raw tail: {raw[-200:] if raw else 'None'}")
