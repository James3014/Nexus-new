# Nexus Docker Deployment & Smoke Test

## 🐳 Image Overview
The Nexus Docker image is a **CLI Smoke Image** designed for automated verification and lightweight orchestration. It is **not** a long-running server by default.

## 🚀 Building the Image
```bash
docker build -t nexus:v28.3.0 .
```

## 🧪 Smoke Testing
Verify the engine's health and environment alignment:
```bash
docker run --rm nexus:v28.3.0
```
This runs `python scripts/engine/nexus_cli.py status` and should exit with code 0.

## 🧠 Ollama / LLM Integration
Nexus does **not** include LLM weights in the image to keep it lightweight.
- **Recommended**: Run Ollama in a separate container and point Nexus to it via environment variables.
- **Network**: Use `--network=host` or a custom Docker network.

```bash
docker run --rm \
  -e LLM_PROVIDER=ollama \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  nexus:v28.3.0 status
```

## 🔒 Security
- Runs as non-root user `nexus` (UID 1000).
- Multi-stage build minimizes attack surface.
