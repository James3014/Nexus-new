from typing import Any, Dict, List, Optional, Tuple
"""TLS-encrypted Registry Synchronization Server and Client.

Handles secure push/pull requests between Nexus Swarm nodes.
"""

import json
import ssl
import socket
import logging
import threading

from nexus.security.tls_provider import TLSProvider
from nexus.learning.skill_registry import SkillRegistry

logger = logging.getLogger(__name__)

class SecureRegistrySync:
    def __init__(self, tls: TLSProvider, registry: SkillRegistry, node_registry=None):
        self.tls = tls
        self.registry = registry
        self.node_registry = node_registry
        self._server_sock = None
        self._thread = None

    def serve(self, host: str = "0.0.0.0", port: int = 8443) -> None:
        """Start mTLS server daemon to listen for swarm skill requests."""
        if not self.registry:
            return
            
        context = self.tls.get_server_context()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(5)
        
        self._server_sock = context.wrap_socket(sock, server_side=True)
        logger.info("SecureRegistrySync serving on %s:%d mTLS", host, port)
        
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self):
        while True:
            try:
                conn, addr = self._server_sock.accept()
                threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
            except Exception as e:
                logger.error("mTLS accept error: %s", e)
                break

    def _handle_client(self, conn: ssl.SSLSocket, addr):
        try:
            cert = conn.getpeercert()
            if not cert:
                logger.warning("Rejecting connection from %s: No client cert", addr)
                return
                
            # Basic Identity Verification (Optional: Implement CN checks)
            client_id = "unknown"
            for sub in cert.get('subject', ()):
                for k, v in sub:
                    if k == 'commonName':
                        client_id = v
                        
            logger.debug("mTLS Conn established from %s (Node: %s)", addr, client_id)
            
            # Simple line-based JSON protocol
            f = conn.makefile("rwb")
            line = f.readline().decode("utf-8")
            if not line:
                return
                
            req = json.loads(line)
            action = req.get("action")
            
            if action == "push":
                from nexus.learning.skill_schema import SkillFrontmatter, SkillSuccessMetric
                for skill_dict in req.get("payload", []):
                    try:
                        # Extract success metric if present
                        sm_dict = skill_dict.pop("success_metric", {})
                        if isinstance(sm_dict, dict):
                            skill_dict["success_metric"] = SkillSuccessMetric(**{k: v for k, v in sm_dict.items() if k in SkillSuccessMetric.__annotations__})
                        
                        fm = SkillFrontmatter(**{k: v for k, v in skill_dict.items() if k in SkillFrontmatter.__annotations__})
                        self.registry.upsert(fm, origin_node_id=client_id)
                    except Exception as e:
                        logger.warning("mTLS Push hydration failed for node %s: %s", client_id, e)
                resp = {"status": "ok"}
                
            elif action == "heartbeat":
                resp = {
                    "status": "alive",
                    "load": 0.5, # Placeholder real load
                    "skill_count": 0 # Placeholder for skill registry size
                }
                
            elif action == "pull":
                query_tokens = set(req.get("query_tokens", []))
                res = self.registry.search(
                    query_tokens=query_tokens,
                    task_type=req.get("task_type"),
                    exclude_origin=client_id,
                    max_results=req.get("max_results", 5)
                )
                resp = {"status": "ok", "payload": res}
                
            elif action == "event":
                from nexus.core.event_bus import NexusEventBus
                event_type = req.get("event_type", "unknown")
                payload = req.get("payload", {})
                
                # Tag as remote to avoid rebroadcast loop
                payload["_source_node"] = client_id
                payload["_is_remote"] = True
                
                NexusEventBus.publish(event_type, payload)
                resp = {"status": "ok"}
                
            else:
                resp = {"status": "error", "message": f"Unknown action: {action}"}
                
            f.write((json.dumps(resp) + "\n").encode("utf-8"))
            f.flush()
            
        except ssl.SSLError as e:
            logger.warning("TLS Handsake Failed with %s: %s", addr, e)
        except Exception as e:
            logger.error("Error handling client %s: %s", addr, e)
        finally:
            conn.close()

    def pull_from_peer(self, peer_host: str, peer_port: int, query_tokens: set, task_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Client: Pull skills via mTLS."""
        context = self.tls.get_client_context()
        try:
            with socket.create_connection((peer_host, peer_port), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=peer_host) as ssock:
                    f = ssock.makefile("rwb")
                    
                    req = {
                        "action": "pull",
                        "query_tokens": list(query_tokens),
                        "task_type": task_type,
                        "max_results": 5
                    }
                    f.write((json.dumps(req) + "\n").encode("utf-8"))
                    f.flush()
                    
                    resp_line = f.readline().decode("utf-8")
                    if not resp_line:
                        return []
                        
                    resp = json.loads(resp_line)
                    if resp.get("status") == "ok":
                        return resp.get("payload", [])
                    return []
        except Exception as e:
            logger.warning("mTLS pull from %s:%d failed: %s", peer_host, peer_port, e)
            return []

    def broadcast_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Broadcast event to all known peers."""
        if not self.node_registry:
            return
            
        # Prevent broadcast loop
        if payload.get("_is_remote"):
            return
            
        peers = self.node_registry.discover()
        context = self.tls.get_client_context()
        
        req = {
            "action": "event",
            "event_type": event_type,
            "payload": payload
        }
        req_line = (json.dumps(req) + "\n").encode("utf-8")
        
        for peer in peers:
            # Skip self
            if peer.node_id == self.tls.node_id:
                continue
                
            try:
                with socket.create_connection((peer.host, peer.port), timeout=5) as sock:
                    with context.wrap_socket(sock, server_hostname=peer.host) as ssock:
                        ssock.sendall(req_line)
            except Exception as e:
                logger.debug("mTLS broadcast to %s failed: %s", peer.node_id, e)
