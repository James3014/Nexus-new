from pathlib import Path
import pytest
import os
import ssl
from nexus.security.tls_provider import TLSProvider

def test_tls_provider_init(tmp_path):
    """驗證 TLSProvider 初始化時是否正確生成 CA 與 Node 憑證。"""
    certs_dir = tmp_path / "certs"
    provider = TLSProvider(certs_dir, node_id="test_node")
    
    assert (certs_dir / "nexus_ca.crt").exists()
    assert (certs_dir / "nexus_ca.key").exists()
    assert (certs_dir / "test_node.crt").exists()
    assert (certs_dir / "test_node.key").exists()

def test_tls_provider_contexts(tmp_path):
    """驗證產出的 Server 與 Client SSLContext 是否配置正確。"""
    certs_dir = tmp_path / "certs"
    provider = TLSProvider(certs_dir, node_id="test_node")
    
    # Server Context
    server_ctx = provider.get_server_context()
    assert isinstance(server_ctx, ssl.SSLContext)
    assert server_ctx.verify_mode == ssl.CERT_REQUIRED
    
    # Client Context
    client_ctx = provider.get_client_context()
    assert isinstance(client_ctx, ssl.SSLContext)
    assert client_ctx.check_hostname is False

def test_tls_provider_missing_certs_error(tmp_path):
    """驗證當憑證丟失時，獲取 Context 應拋出錯誤。"""
    certs_dir = tmp_path / "certs"
    provider = TLSProvider(certs_dir, node_id="test_node")
    
    # 刪除憑證
    (certs_dir / "test_node.crt").unlink()
    
    with pytest.raises(RuntimeError, match="Certificates not ready"):
        provider.get_server_context()
