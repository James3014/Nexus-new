import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from nexus.market.credit_ledger import CreditLedger

logger = logging.getLogger(__name__)

@dataclass
class CrystalListing:
    skill_id: str
    seller_node_id: str
    base_price: float = 10.0
    quality_score: float = 1.0
    demand_multiplier: float = 1.0

class CrystalMarket:
    def __init__(self, ledger: CreditLedger) -> None:
        self.ledger = ledger
        self.listings: Dict[str, CrystalListing] = {}

    def list_crystal(self, crystal: CrystalListing) -> None:
        self.listings[crystal.skill_id] = crystal
        logger.info("Crystal Listed: %s by %s for %s", crystal.skill_id, crystal.seller_node_id, crystal.base_price)

    def calculate_dynamic_price(self, skill_id: str) -> float:
        listing = self.listings.get(skill_id)
        if not listing:
            return 0.0
        # price = base * (1 + (demand/10)) * quality
        return listing.base_price * (1.0 + (listing.demand_multiplier / 10.0)) * listing.quality_score

    def purchase(self, buyer_id: str, skill_id: str) -> bool:
        listing = self.listings.get(skill_id)
        if not listing:
            logger.warning("Crystal [%s] not found.", skill_id)
            return False
            
        current_price = self.calculate_dynamic_price(skill_id)
        
        success = self.ledger.transact(
            buyer_id=buyer_id,
            seller_id=listing.seller_node_id,
            crystal_id=skill_id,
            price=current_price
        )
        
        if success:
            listing.demand_multiplier += 1.0 # Increase demand for next buyer
            
        return success
