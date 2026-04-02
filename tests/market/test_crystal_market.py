from pathlib import Path
import pytest
from nexus.market.credit_ledger import CreditLedger
from nexus.market.crystal_market import CrystalMarket, CrystalListing

def test_credit_ledger_transaction(tmp_path: Path):
    db_path = tmp_path / "ledger.db"
    ledger = CreditLedger(db_path)
    
    assert ledger.check_balance("tenant-A") == 100.0
    assert ledger.check_balance("tenant-B") == 100.0
    
    success = ledger.transact("tenant-A", "tenant-B", "skill-1", price=50.0)
    assert success is True
    
    assert ledger.check_balance("tenant-A") == 50.0
    assert ledger.check_balance("tenant-B") == 145.0
    
    fail = ledger.transact("tenant-A", "tenant-B", "skill-2", price=60.0)
    assert fail is False
    assert ledger.check_balance("tenant-A") == 50.0

def test_dynamic_pricing(tmp_path: Path):
    ledger = CreditLedger(tmp_path / "ledger.db")
    market = CrystalMarket(ledger)
    
    listing = CrystalListing(
        skill_id="magic-sort",
        seller_node_id="tenant-B",
        base_price=10.0,
        quality_score=1.2,
        demand_multiplier=1.0
    )
    market.list_crystal(listing)
    
    price1 = market.calculate_dynamic_price("magic-sort")
    assert abs(price1 - 13.2) < 0.01
    
    success = market.purchase("tenant-A", "magic-sort")
    assert success is True
    
    price2 = market.calculate_dynamic_price("magic-sort")
    assert abs(price2 - 14.4) < 0.01
