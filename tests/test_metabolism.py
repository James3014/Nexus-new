from nexus.services.metabolism_engine import metabolism

def test_metabolism():
    # Test 1: Safe Zone
    assert metabolism.should_distill(10000) == False
    
    # Test 2: Threshold Breach (85% of 128k)
    assert metabolism.should_distill(110000) == True
    
    # Test 3: Distillation Snap
    essence = {"manifest": "V25_GOVERNANCE", "step": 36}
    seed_ref = metabolism.distill(essence)
    assert "ar_tx_distilled" not in seed_ref  # no fake transaction id
    assert seed_ref.endswith("session_seed.json")
    print(f"✅ Metabolism Verification Passed. Seed: {seed_ref}")

if __name__ == "__main__":
    test_metabolism()
