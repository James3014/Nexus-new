from nexus.demo.feature_discount_engine import calculate_discount

def test_base_discount_threshold():
    assert calculate_discount(120, is_vip=False, coupon=None) == 108.0

def test_coupon_stack():
    assert calculate_discount(120, is_vip=False, coupon="SAVE5") == 102.0

def test_vip_bonus_discount():
    # VIP should receive extra 5% on top of threshold discount.
    assert calculate_discount(120, is_vip=True, coupon=None) == 102.0
