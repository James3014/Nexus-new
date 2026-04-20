from typing import Any, Dict, List, Optional, Tuple
import http.server
import socketserver
import threading
import json
import time
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.sse")

class SSEEmitter:
    """🛡️ Swarm Emitter: 基於 SSE 的 Agent 信令中心"""
    def __init__(self):
        self.clients = []
        self.lock = threading.Lock()

    def add_client(self, client):
        with self.lock:
            self.clients.append(client)
            logger.info(f"📡 [SSE] Client connected. Total: {len(self.clients)}")

    def broadcast(self, data: Dict):
        payload = f"data: {json.dumps(data)}\n\n"
        with self.lock:
            for client in self.clients:
                try:
                    client.wfile.write(payload.encode('utf-8'))
                    client.wfile.flush()
                except Exception:
                    self.clients.remove(client)

emitter = SSEEmitter()

class SSEHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/nexus-sync/'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            emitter.add_client(self)
            # 保持連接
            while True:
                time.sleep(1)
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/broadcast':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data)
            logger.info(f"📢 [SSE] Broadcasting: {data.get('type')}")
            emitter.broadcast(data)
            self.send_response(200)
            self.end_headers()

def run_server(port=None):
    if port is None:
        port = int(os.environ.get("NEXUS_SSE_PORT", "8080"))
    with socketserver.ThreadingTCPServer(("", port), SSEHandler) as httpd:
        logger.info(f"📡 [SSE:Server] Claude-Together Signaling Active on port {port}")
        httpd.serve_forever()

if __name__ == "__main__":
    run_server()
