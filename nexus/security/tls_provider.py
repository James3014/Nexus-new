from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
"""Zero-dependency mTLS using Python's built-in ssl and subprocess.

Handles automatic generation of a local Certificate Authority (CA)
and node-specific certificates for Swarm encrypted communication.
"""

import os
import ssl
import logging
import subprocess

logger = logging.getLogger(__name__)

class TLSProvider:
    def __init__(self, certs_dir: Path, node_id: str = "local"):
        self.certs_dir = certs_dir
        self.node_id = node_id
        
        self.certs_dir.mkdir(parents=True, exist_ok=True)
        
        self.ca_cert = self.certs_dir / "nexus_ca.crt"
        self.ca_key = self.certs_dir / "nexus_ca.key"
        self.node_cert = self.certs_dir / f"{self.node_id}.crt"
        self.node_key = self.certs_dir / f"{self.node_id}.key"
        
        self._ensure_certs()

    def _ensure_certs(self):
        """Ensure CA and Node certs exist. If not, generate them via OpenSSL."""
        if not self.ca_cert.exists() or not self.ca_key.exists():
            logger.info("Generating new Nexus CA in %s", self.certs_dir)
            self._run_openssl([
                "req", "-x509", "-newkey", "rsa:4096", "-days", "3650",
                "-nodes", "-keyout", str(self.ca_key), "-out", str(self.ca_cert),
                "-subj", "/C=US/O=Nexus Singularity/CN=Nexus Root CA"
            ])

        if not self.node_cert.exists() or not self.node_key.exists():
            logger.info("Generating cert for node %s", self.node_id)
            csr_path = self.certs_dir / f"{self.node_id}.csr"
            
            # Create CSR
            self._run_openssl([
                "req", "-new", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(self.node_key), "-out", str(csr_path),
                "-subj", f"/C=US/O=Nexus Swarm/CN={self.node_id}"
            ])
            
            # Sign with CA (simplified, no serial tracking for local dev)
            self._run_openssl([
                "x509", "-req", "-in", str(csr_path),
                "-CA", str(self.ca_cert), "-CAkey", str(self.ca_key),
                "-CAcreateserial", "-out", str(self.node_cert), "-days", "365", "-sha256"
            ])
            
            if csr_path.exists():
                csr_path.unlink()

    def _run_openssl(self, args: list) -> None:
        """Run OpenSSL command."""
        try:
            subprocess.run(["openssl"] + args, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            logger.error("OpenSSL error: %s", e.stderr.decode("utf-8"))
            raise RuntimeError(f"OpenSSL failed: {e.stderr.decode('utf-8')}")

    def get_server_context(self) -> ssl.SSLContext:
        """Create TLS context for Server: Require and verify client cert."""
        if not self.ca_cert.exists() or not self.node_cert.exists():
            raise RuntimeError("Certificates not ready")
            
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile=self.node_cert, keyfile=self.node_key)
        
        # Require Client Certificate
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cafile=self.ca_cert)
        
        return context

    def get_client_context(self) -> ssl.SSLContext:
        """Create TLS context for Client: Present own cert and verify server."""
        if not self.ca_cert.exists() or not self.node_cert.exists():
            raise RuntimeError("Certificates not ready")
            
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.load_verify_locations(cafile=self.ca_cert)
        
        # Present Client Certificate
        context.load_cert_chain(certfile=self.node_cert, keyfile=self.node_key)
        
        # Also check hostname
        context.check_hostname = False # Set True in production with proper SANs
        
        return context
