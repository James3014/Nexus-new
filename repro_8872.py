import numpy as np
from astropy import units as u

try:
    val = np.float16(1)
    q = val * u.km
    print(f"Input dtype: {val.dtype}")
    print(f"Output Quantity dtype: {q.dtype}")
    if q.dtype == np.float16:
        print("PASS: dtype preserved")
    else:
        print("FAIL: dtype not preserved (upgraded to float64)")
except Exception as e:
    print(f"ERROR: {e}")
