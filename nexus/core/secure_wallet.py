import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class SecureWallet:
    """
    🛡️ Nexus v24.0 Secure Wallet Loader
    Handles Arweave JWK keys from encrypted environment variables.
    """
    def __init__(self, env_var: str = "NEXUS_ARWEAVE_JWK"):
        self.env_var = env_var

    def load_jwk(self) -> Optional[Dict[str, Any]]:
        """🛡️ Load and validate JWK from environment."""
        raw_jwk = os.getenv(self.env_var)
        if not raw_jwk:
            logger.warning(f"⚠️ [Wallet] Missing {self.env_var}. Arweave sync will use LOCAL_MIRROR.")
            return None
        
        try:
            jwk = json.loads(raw_jwk)
            # Basic JWK validation
            required_keys = ["kty", "n", "e", "d", "p", "q"]
            if all(k in jwk for k in required_keys):
                logger.info("✅ [Wallet] Arweave JWK loaded and validated.")
                return jwk
            else:
                logger.error("🛑 [Wallet] Invalid JWK format.")
                return None
        except Exception as e:
            logger.error(f"🛑 [Wallet] Failed to decode JWK: {e}")
            return None

def get_wallet():
    """Authoritative singleton/accessor for the secure wallet."""
    return SecureWallet().load_jwk()
