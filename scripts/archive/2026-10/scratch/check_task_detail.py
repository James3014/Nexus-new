import json
import re

log_path = "ollama_calls.log"
print(f"Reading {log_path}...")

# Let's read the file and find all occurrences of "qwen2.5-coder:14b-instruct-q3_K_M" and print the generated outputs.
with open(log_path, "r", encoding="utf-8", errors="replace") as f:
    content = f.read()

# Ollama calls are logged in some structured format. Let's search for "REPLACE" or SEARCH/REPLACE blocks.
# We can find all search/replace blocks or response strings.
matches = re.findall(r"<<<<<<< SEARCH.*?>>>>>>> REPLACE", content, re.DOTALL)
print(f"Found {len(matches)} SEARCH/REPLACE blocks in the log.")
for i, match in enumerate(matches[-5:]):
    print(f"\n--- MATCH {i+1} ---")
    print(match)
