from typing import Any, Dict, List, Optional, Tuple, Protocol
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
MAX_SYNC_MESSAGE_BYTES = 1_048_576


def decode_sync_request(line: bytes, *, max_bytes: int = MAX_SYNC_MESSAGE_BYTES) -> Tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
    """Decode one newline-delimited JSON object with bounded memory and type checks."""
    if len(line) > max_bytes:
        return None, {"status": "error", "message": "message_too_large"}
    try:
        req = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, {"status": "error", "message": "invalid_json"}
    if not isinstance(req, dict):
        return None, {"status": "error", "message": "invalid_request"}
    return req, None


class IncomingMessageHandler(Protocol):
    def handle(self, req: Dict[str, Any], client_id: str) -> Dict[str, Any]: ...


class RegistryMessageHandler:
    def __init__(self, registry: SkillRegistry | None, allowed_actions: Dict[str, set[str]] | None = None):
        self.registry = registry
        self.allowed_actions = allowed_actions or {}

    def handle(self, req: Dict[str, Any], client_id: str) -> Dict[str, Any]:
        action = req.get("action")
        if not self._action_allowed(str(action), client_id):
            return {"status": "error", "message": "unauthorized_action", "action": action}
        if action == "push":
            return self._handle_push(req, client_id)
        if action == "heartbeat":
            return {"status": "alive", "load": 0.5, "skill_count": 0}
        if action == "pull":
            return self._handle_pull(req, client_id)
        if action == "event":
            return self._handle_event(req, client_id)
        return {"status": "error", "message": f"Unknown action: {action}"}

    def _action_allowed(self, action: str, client_id: str) -> bool:
        if not self.allowed_actions:
            return True
        allowed = self.allowed_actions.get(client_id, self.allowed_actions.get("*", set()))
        return action in allowed

    def _handle_push(self, req: Dict[str, Any], client_id: str) -> Dict[str, Any]:
        if not self.registry:
            return {"status": "error", "message": "registry_unavailable"}
        from nexus.learning.skill_schema import SkillFrontmatter, SkillSuccessMetric

        for skill_dict in req.get("payload", []):
            try:
                skill_dict = dict(skill_dict)
                sm_dict = skill_dict.pop("success_metric", {})
                if isinstance(sm_dict, dict):
                    skill_dict["success_metric"] = SkillSuccessMetric(
                        **{k: v for k, v in sm_dict.items() if k in SkillSuccessMetric.__annotations__}
                    )
                fm = SkillFrontmatter(
                    **{k: v for k, v in skill_dict.items() if k in SkillFrontmatter.__annotations__}
                )
                self.registry.upsert(fm, origin_node_id=client_id)
            except Exception as e:
                logger.warning("mTLS Push hydration failed for node %s: %s", client_id, e)
        return {"status": "ok"}

    def _handle_pull(self, req: Dict[str, Any], client_id: str) -> Dict[str, Any]:
        if not self.registry:
            return {"status": "error", "message": "registry_unavailable"}
        res = self.registry.search(
            query_tokens=set(req.get("query_tokens", [])),
            task_type=req.get("task_type"),
            exclude_origin=client_id,
            max_results=req.get("max_results", 5),
        )
        return {"status": "ok", "payload": res}

    def _handle_event(self, req: Dict[str, Any], client_id: str) -> Dict[str, Any]:
        from nexus.events.transport import NexusEventBus

        payload = req.get("payload", {})
        payload = payload if isinstance(payload, dict) else {}
        payload["_source_node"] = client_id
        payload["_is_remote"] = True
        NexusEventBus.publish(req.get("event_type", "unknown"), payload)
        return {"status": "ok"}


class SecureRegistrySync:
    def __init__(
        self,
        tls: TLSProvider,
        registry: SkillRegistry,
        node_registry=None,
        handler: IncomingMessageHandler | None = None,
        allowed_actions: Dict[str, set[str]] | None = None,
    ):
        self.tls = tls
        self.registry = registry
        self.node_registry = node_registry
        self.handler = handler or RegistryMessageHandler(registry, allowed_actions=allowed_actions)
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
                
            client_id = "unknown"
            for sub in cert.get('subject', ()):
                for k, v in sub:
                    if k == 'commonName':
                        client_id = v
                        
            logger.debug("mTLS Conn established from %s (Node: %s)", addr, client_id)
            f = conn.makefile("rwb")
            line = f.readline()
            if not line:
                return
            req, error = decode_sync_request(line)
            resp = error or self.handler.handle(req or {}, client_id)
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
