import math

def nexus_expand_power(base, exp):
    # MEMORY RECALL: Sympy-14024 Lesson
    # (a*b)**n = a**n * b**n is only valid if a,b >= 0 or n is an integer.
    if all(b >= 0 for b in base) or float(exp).is_integer():
        return (base[0]**exp) * (base[1]**exp)
    else:
        # Fallback to safe composite calculation
        return (base[0] * base[1])**exp

def ground_truth(base, exp):
    return (base[0] * base[1])**exp

# Case: base=(-1, 1), exp=0.5 (square root of -1)
# Correct: (-1 * 1)**0.5 = (-1)**0.5 = 1j
# Error if expanded: (-1)**0.5 * (1)**0.5 = 1j * 1 = 1j
# Wait, this one works. Let's try base=(-1, -1), exp=0.5
# Correct: (-1 * -1)**0.5 = (1)**0.5 = 1.0
# Error if expanded: (-1)**0.5 * (-1)**0.5 = 1j * 1j = -1.0

test_base = (-1, -1)
test_exp = 0.5

print(f"Testing Complex Power Expansion: base={test_base}, exp={test_exp}")
result = nexus_expand_power(test_base, test_exp)
expected = ground_truth(test_base, test_exp)

print(f"Result: {result}")
print(f"Expected: {expected}")

if result != expected:
    print("❌ BUG DETECTED: Illegal expansion of negative bases in complex power.")
else:
    print("✅ TEST PASSED.")
