from scripts.engine.critique_engine import critique, RationalizationError

def test_critique():
    # Test 1: Good Plan
    assert critique.prescan("Deploying version 25.5 with full TDD tests.") == "✅ Intent Clear"
    
    # Test 2: Lazy Plan (Blocked)
    try:
        critique.prescan("Updating the router, will skip tests for now to save time.")
        assert False, "Should have blocked 'skip tests'"
    except RationalizationError as e:
        print(f"🛑 Successfully Blocked: {e}")

if __name__ == "__main__":
    test_critique()
