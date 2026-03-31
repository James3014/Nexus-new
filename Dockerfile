FROM python:3.12-slim
RUN apt-get update && apt-get install -y curl ca-certificates git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
RUN pip install uv && uv pip install sentence-transformers lancedb requests arweave-python-client cryptography

# Ollama $0 Reasoning Layer (v18.4)
RUN curl -fsSL https://ollama.ai/install.sh | sh && \
    (ollama serve &) && sleep 30 && \
    ollama pull llama3.1:8b-q4_0 && pkill ollama

ENV LLM_PROVIDER=ollama MODEL=llama3.1:8b-q4_0 NEXUS_HOME=/data/.nexus
VOLUME ["/data"]
EXPOSE 8516 9192
CMD ollama serve & uv run scripts/engine/nexus_cli.py health --full
