# 🛡️ Nexus Swarm Node (Python v22)
FROM python:3.12-slim

WORKDIR /app
# Build context is nexus_swarm/: docker build -f nexus_swarm/node/Dockerfile nexus_swarm
COPY node/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# swarm_pb2*.py are vendored inside node/
COPY node/ .

# 🛡️ Certs will be mounted via K8s Secret or copied here for local test
# COPY certs/ca.crt certs/node.crt certs/node.key ./certs/

RUN useradd -m -s /bin/bash nexus && chown -R nexus:nexus /app
USER nexus

EXPOSE 0
HEALTHCHECK --interval=30s --timeout=3s CMD python3 -c "import grpc; print('grpc ok')" || exit 1

CMD ["python", "main.py"]
