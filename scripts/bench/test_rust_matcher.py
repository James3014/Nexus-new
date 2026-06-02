import nexus_core
import time
import os

def test_rust_matcher():
    root = os.getcwd()
    patterns = ["*.py", "*.md"]
    
    print(f"🚀 Testing Rust FastMatcher at {root}...")
    start = time.time()
    results = nexus_core.fast_scan(root, patterns)
    end = time.time()
    
    print(f"✅ Found {len(results)} files in {end - start:.4f}s")
    
    # Print first 5 results
    for m in results[:5]:
        print(f"  - {m.path} ({m.size} bytes)")

if __name__ == "__main__":
    try:
        test_rust_matcher()
    except Exception as e:
        print(f"❌ Error: {e}")
