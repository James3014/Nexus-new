import os
from nexus.services.llm import LLMClient
client = LLMClient()
print(f"Use OAuth: {client.use_oauth}")
# Attempt a small ask
res, raw = client.ask("Say HI", "", phase="P")
print(f"Status: {res.get('status')}")
print(f"Tokens Used: {res.get('tokens_used')}")
print(f"Raw Tokens: {res.get('token_raw_model')}")
