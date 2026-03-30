import numpy as np
import numpy.ma as ma

try:
    d = ma.array([1, None], mask=[False, True])
    print("Masked array created:", d)
    res = d > 0
    print("Comparison result:", res)
except Exception as e:
    print("Caught expected exception:", e)

try:
    d2 = ma.array([1, np.nan], mask=[False, True])
    print("Masked array with nan created:", d2)
    res2 = d2 > 0
    print("Comparison result with nan:", res2)
except Exception as e:
    print("Caught exception with nan:", e)
