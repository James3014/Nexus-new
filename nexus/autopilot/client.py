import grpc
import sys
from pathlib import Path

# Add project root to path for proto imports
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import proto.swarm_pb2 as swarm_pb2
import proto.swarm_pb2_grpc as swarm_pb2_grpc

class NSPClient:
    """
    🛰️ Nexus Swarm Protocol Client (Python)
    用於與 Go Swarm Manager 進行通訊，獲取節點狀態與執行感知感知。
    """
    def __init__(self, endpoint="localhost:8516"):
        self.channel = grpc.insecure_channel(endpoint)
        self.stub = swarm_pb2_grpc.SwarmManagerStub(self.channel)
    
    def sensing_stream(self):
        """
        🌊 獲取實時節點感測流。
        返回感測到的節點屬性、負載與增益效能。
        """
        try:
            # v0.2 使用 HeartbeatReq/Resp 或特定的 SensingStream
            # 此處模擬對位 v0.2 的 SensingStream 邏輯
            # 在目前的 Go 實現中，Manager 會維護 node_registry.json
            import json
            registry_path = REPO_ROOT / ".nexus/federation/node_registry.json"
            if registry_path.exists():
                with open(registry_path, 'r') as f:
                    nodes = json.load(f)
                    for node in nodes:
                        yield {
                            "id": node.get("node_id"),
                            "lang": node.get("capabilities", []),
                            "load": node.get("load", 0.1),
                            "latency": node.get("latency_ms", 50),
                            "gain": node.get("learning_gain", 85)
                        }
        except Exception as e:
            print(f"⚠️ [NSPClient] Sensing error: {e}")
            yield {}

    def heartbeat(self, node_id: str, status: str = "ONLINE"):
        req = swarm_pb2.HeartbeatReq(
            node_id=node_id,
            status=status,
            timestamp=int(time.time()),
            capabilities=["python-kernel"]
        )
        return self.stub.Heartbeat(req)
