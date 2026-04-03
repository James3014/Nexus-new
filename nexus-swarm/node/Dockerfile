# 🛡️ Nexus Swarm Node (Python v22)
FROM python:3.12-slim

WORKDIR /app
COPY nexus-swarm/node/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY nexus-swarm/node/ .
COPY nexus-swarm/api/proto/swarm_pb2.py .
COPY nexus-swarm/api/proto/swarm_pb2_grpc.py .

# 🛡️ Certs will be mounted via K8s Secret or copied here for local test
# COPY nexus-swarm/certs/ca.crt nexus-swarm/certs/node.crt nexus-swarm/certs/node.key ./certs/

EXPOSE 0
HEALTHCHECK --interval=30s --timeout=3s CMD python3 -c "import grpc; print('grpc ok')" || exit 1

CMD ["python", "main.py"]
