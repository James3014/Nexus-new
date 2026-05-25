from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import sqlite3
import time
import logging

logger = logging.getLogger(__name__)

class CreditLedger:
    def __init__(self, db_path: Path, timeout: float = 10.0) -> None:
        self.db_path = db_path
        self.timeout = timeout
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_conn() as conn:
            # Create accounts table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS accounts (
                    tenant_id TEXT PRIMARY KEY,
                    balance REAL NOT NULL DEFAULT 100.0,
                    created_at REAL NOT NULL
                )
            ''')
            # Create transactions log
            conn.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    buyer_id TEXT NOT NULL,
                    seller_id TEXT,
                    crystal_id TEXT,
                    amount REAL NOT NULL,
                    fee REAL NOT NULL,
                    timestamp REAL NOT NULL
                )
            ''')
            conn.commit()

    def check_balance(self, tenant_id: str) -> float:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT balance FROM accounts WHERE tenant_id = ?", (tenant_id,))
            row = cursor.fetchone()
            if row:
                return float(row[0])
            # Initialize new account with 100 credits
            conn.execute("INSERT INTO accounts (tenant_id, balance, created_at) VALUES (?, 100.0, ?)", (tenant_id, time.time()))
            conn.commit()
            return 100.0

    def transact(self, buyer_id: str, seller_id: str, crystal_id: str, price: float) -> bool:
        buyer_bal = self.check_balance(buyer_id)
        self.check_balance(seller_id) # init if not exists BEFORE opening transaction
        
        if buyer_bal < price:
            logger.warning("Market [FAILED] Tenant [%s] Insufficient funds (%s < %s)", buyer_id, buyer_bal, price)
            return False

        seller_share = price * 0.9
        fee = price - seller_share

        with self._get_conn() as conn:
            try:
                # Deduct buyer
                conn.execute("UPDATE accounts SET balance = balance - ? WHERE tenant_id = ?", (price, buyer_id))
                # Add seller
                conn.execute("UPDATE accounts SET balance = balance + ? WHERE tenant_id = ?", (seller_share, seller_id))
                
                # Log transaction
                conn.execute('''
                    INSERT INTO transactions (buyer_id, seller_id, crystal_id, amount, fee, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (buyer_id, seller_id, crystal_id, price, fee, time.time()))
                
                conn.commit()
                logger.info("Market [SUCCESS] Transferred %s tokens from %s to %s for %s", seller_share, buyer_id, seller_id, crystal_id)
                return True
            except Exception as e:
                conn.rollback()
                logger.error("Market Transaction Error: %s", e)
                return False

    def log(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM transactions ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor]
