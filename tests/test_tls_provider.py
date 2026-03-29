"""Tests for the TLSProvider and mTLS certificate management."""

import os
import ssl
import time
import socket
import threading
import tempfile
from pathlib import Path

from nexus.security.tls_provider import TLSProvider

def test_generate_and_verify_certs():
    with tempfile.TemporaryDirectory() as tmpdir:
        certs_dir = Path(tmpdir) / "certs"
        
        # This will trigger CA and node cert generation
        tls = TLSProvider(certs_dir, node_id="test_node_x")
        
        assert tls.ca_cert.exists()
        assert tls.ca_key.exists()
        assert tls.node_cert.exists()
        assert tls.node_key.exists()
        
        # Verify sizes are non-zero
        assert tls.ca_cert.stat().st_size > 0
        assert tls.node_cert.stat().st_size > 0

def _run_test_server(context: ssl.SSLContext, host: str, port: int, stop_event: threading.Event):
    """Runs a simple TLS echo server that stops when the event is set."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Try different ports if address already in use, or just hardcode for isolated test
    server_socket.bind((host, port))
    server_socket.listen(1)
    # Set a short timeout so accept() doesn't block forever when stopping
    server_socket.settimeout(0.5)
    
    try:
        with context.wrap_socket(server_socket, server_side=True) as tls_sock:
            while not stop_event.is_set():
                try:
                    conn, addr = tls_sock.accept()
                except socket.timeout:
                    continue
                except ssl.SSLError:
                    # Usually means client failed verification
                    continue
                
                with conn:
                    # Simple echo
                    data = conn.recv(1024)
                    if data:
                        conn.sendall(data)
    except Exception:
        pass
    finally:
        server_socket.close()

def test_mutual_auth():
    with tempfile.TemporaryDirectory() as tmpdir:
        certs_dir = Path(tmpdir) / "certs"
        
        server_tls = TLSProvider(certs_dir, node_id="server_node")
        server_ctx = server_tls.get_server_context()
        
        client_tls = TLSProvider(certs_dir, node_id="client_node")
        client_ctx = client_tls.get_client_context()
        
        stop_event = threading.Event()
        host = "127.0.0.1"
        port = 18443
        
        server_thread = threading.Thread(
            target=_run_test_server, args=(server_ctx, host, port, stop_event)
        )
        server_thread.start()
        
        # Give server a moment to start
        time.sleep(0.5)
        
        try:
            # Client connects to server
            with socket.create_connection((host, port), timeout=3) as sock:
                with client_ctx.wrap_socket(sock, server_hostname="server_node") as ssl_sock:
                    msg = b"hello TLS"
                    ssl_sock.sendall(msg)
                    data = ssl_sock.recv(1024)
                    assert data == msg
        finally:
            stop_event.set()
            server_thread.join(timeout=2)

def test_reject_untrusted_client():
    with tempfile.TemporaryDirectory() as tmpdir_server, tempfile.TemporaryDirectory() as tmpdir_attacker:
        server_certs = Path(tmpdir_server) / "certs"
        attacker_certs = Path(tmpdir_attacker) / "certs"
        
        # Server set up its own CA
        server_tls = TLSProvider(server_certs, node_id="server_node")
        server_ctx = server_tls.get_server_context()
        
        # Attacker sets up a DIFFERENT CA
        attacker_tls = TLSProvider(attacker_certs, node_id="evil_node")
        attacker_ctx = attacker_tls.get_client_context()
        
        stop_event = threading.Event()
        host = "127.0.0.1"
        port = 18444
        
        server_thread = threading.Thread(
            target=_run_test_server, args=(server_ctx, host, port, stop_event)
        )
        server_thread.start()
        
        time.sleep(0.5)
        
        try:
            import pytest
            with pytest.raises(ssl.SSLError):
                with socket.create_connection((host, port), timeout=3) as sock:
                    with attacker_ctx.wrap_socket(sock, server_hostname="server_node") as ssl_sock:
                        # Should fail during handshake
                        ssl_sock.sendall(b"hack")
        finally:
            stop_event.set()
            server_thread.join(timeout=2)
