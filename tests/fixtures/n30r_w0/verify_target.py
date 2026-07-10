import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from target import add_one

def verify():
    assert add_one(4) == 5, f"add_one(4) = {add_one(4)}, expected 5"
    return True

if __name__ == "__main__":
    verify()
    print("PASS")
