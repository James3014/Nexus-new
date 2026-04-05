#!/usr/bin/env python3
import asyncio
import grpc
import time
import os
import psutil
import socket
import logging
import argparse

import swarm_pb2
import swarm_pb2_grpc

# 🛡️ Logging Configuration
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger("NEXUS-NODE")

class NexusNodeAgent:
    def __init__(self, manager_addr="localhost:9000", region="local"):
        self.manager_addr = manager_addr
        self.region = region
        self.node_id = f"nexus-node-{socket.gethostname()}-{os.getpid()}"
        self.active_tasks = 0

    def make_traceparent(self):
        # 🛡️ W3C TraceContext Stub
        return f"00-{os.urandom(16).hex()}-{os.urandom(8).hex()}-01"

    async def register(self, stub):
        """Node Registration with NSP v0.1 Contract"""
        req = swarm_pb2.RegisterNodeRequest(
            node_id=self.node_id,
            version="v22.0",
            capabilities=["python", "repair", "audit", "eternal"],
            region=self.region,
            cpu_cores=psutil.cpu_count(),
            memory_mb=psutil.virtual_memory().total // (1024**2),
            advertise_addr=socket.gethostbyname(socket.gethostname()),
            traceparent=self.make_traceparent()
        )
        try:
            resp = await stub.RegisterNode(req)
            if resp.accepted:
                logger.info(f"✅ Registered with Manager: {resp.manager_id} (Interval: {resp.heartbeat_interval_sec}s)")
                return True
        except Exception as e:
            logger.error(f"❌ Registration failed: {e}")
        return False

    async def heartbeat_loop(self, stub):
        """Continuous Heartbeat (STALE protection)"""
        while True:
            req = swarm_pb2.HeartbeatRequest(
                node_id=self.node_id,
                cpu_percent=psutil.cpu_percent(),
                memory_percent=psutil.virtual_memory().percent,
                active_tasks=self.active_tasks,
                timestamp_unix=int(time.time()),
                traceparent=self.make_traceparent()
            )
            try:
                await stub.Heartbeat(req)
                logger.debug(f"💓 Heartbeat sent for {self.node_id}")
            except Exception as e:
                logger.warning(f"⚠️ Heartbeat failed: {e}")
            await asyncio.sleep(30)

async def main():
    parser = argparse.ArgumentParser(description="Nexus Swarm Node Agent")
    parser.add_argument("--manager", default="localhost:9000", help="Manager address")
    parser.add_argument("--region", default="local", help="Node region")
    args = parser.parse_args()

    # 🛡️ [v22/v24] mTLS Configuration
    try:
        with open("certs/ca.crt", "rb") as f:
            ca_cert = f.read()
        with open("certs/node.crt", "rb") as f:
            client_cert = f.read()
        with open("certs/node.key", "rb") as f:
            client_key = f.read()
        
        creds = grpc.ssl_channel_credentials(
            root_certificates=ca_cert,
            private_key=client_key,
            certificate_chain=client_cert
        )
        logger.info("🛡️ mTLS Credentials loaded.")
    except Exception as e:
        logger.error(f"❌ Failed to load certs: {e}")
        return

    agent = NexusNodeAgent(manager_addr=args.manager, region=args.region)
    async with grpc.aio.secure_channel(agent.manager_addr, creds) as channel:
        stub = swarm_pb2_grpc.SwarmManagerStub(channel)
        
        if await agent.register(stub):
            await agent.heartbeat_loop(stub)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Node shutting down...")
