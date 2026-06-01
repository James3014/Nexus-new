import numpy as np
from astropy.modeling import models as m
from astropy.modeling.separable import separability_matrix

def print_test(name, model):
    print(f"\n--- Test: {name} ---")
    res = separability_matrix(model)
    print("Resulting Matrix:")
    print(res)
    return res

# 1. 簡單組合 (預期正確)
cm = m.Linear1D(10) & m.Linear1D(5)
print_test("Simple Composition (cm)", cm)

# 2. 扁平組合 (預期正確)
flat_cm = m.Pix2Sky_TAN() & m.Linear1D(10) & m.Linear1D(5)
print_test("Flat Composition (Pix2Sky & L1 & L1)", flat_cm)

# 3. 嵌套組合 (真正有 Bug 的案例)
nested_cm = m.Pix2Sky_TAN() & cm
res3 = print_test("Nested Composition (Pix2Sky & cm)", nested_cm)

# 邏輯判定
buggy_rows = np.array([
    [False, False, True, True],
    [False, False, True, True]
])

is_buggy = np.all(res3[2:] == buggy_rows)
is_fixed = np.all(res3[2:] == np.array([
    [False, False, True, False],
    [False, False, False, True]
]))

print("\n--- Diagnostic Conclusion ---")
if is_buggy:
    print("STATUS: BUG REPRODUCED (Red Light Established)")
    print("Evidence: Last two rows match buggy pattern [[F, F, T, T], [F, F, T, T]]")
elif is_fixed:
    print("STATUS: ALREADY FIXED AT CHECKOUT (Green Light)")
    print("Evidence: Last two rows match expected diagonal pattern.")
else:
    print("STATUS: UNEXPECTED RESULT")
    print("Evidence: Matrix does not match buggy OR fixed patterns.")
