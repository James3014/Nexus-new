import pandas as pd
import numpy as np

# Test Index.isin with level
idx = pd.MultiIndex.from_tuples([(1, 'a'), (1, 'b'), (2, 'a')], names=['L1', 'L2'])

try:
    result = idx.isin([1], level='L1')
    print("isin level='L1' result:", result)
    expected = np.array([True, True, False])
    np.testing.assert_array_equal(result, expected)

    result2 = idx.isin(['a'], level=1)
    print("isin level=1 result:", result2)
    expected2 = np.array([True, False, True])
    np.testing.assert_array_equal(result2, expected2)

    print("SUCCESS: pandas-7890 verified")
except Exception as e:
    print("FAILED: pandas-7890 verification failed:", e)
    import traceback
    traceback.print_exc()
