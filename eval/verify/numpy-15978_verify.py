import numpy as np
import numpy.ma as ma

# Problem: Comparing object-type MaskedArray with None crashes
data = np.array([None, None], dtype=object)
m = ma.masked_array(data, mask=[False, True])

try:
    result = (m == None)
    print("Comparison successful")
    print("Result:", result)
    assert result[0] is True or result[0] == True
    # result[1] should be masked or False/True depending on implementation
    # But it shouldn't crash.
    print("SUCCESS: numpy-15978 verified")
except TypeError as e:
    print("FAILED: numpy-15978 still crashes:", e)
except Exception as e:
    print("ERROR:", e)
