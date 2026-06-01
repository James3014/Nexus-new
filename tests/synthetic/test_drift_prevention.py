def target_func():
    # Model will try to match this but with typos
    raise ValueError("Precision mismatch here")

def other_func():
    # This is the old drift target
    raise TypeError("Different error type")

if __name__ == "__main__":
    target_func()
