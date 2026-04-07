from nexus.services.metabolism_engine import metabolism

def test_metabolism():
    # Test 1: Safe Zone
    assert metabolism.should_distill(10000) == False
    
    # Test 2: Threshold Breach (85% of 128k)
    assert metabolism.should_distill(110000) == True
    
    # Test 3: Distillation Snap
    essence = {"manifest": "V25_GOVERNANCE", "step": 36}
    tx_id = metabolism.distill(essence)
    assert "ar_tx_distilled" in tx_id
    print(f"✅ Metabolism Verification Passed. TX: {tx_id}")

if __name__ == "__main__":
    test_metabolism()
