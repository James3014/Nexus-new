ORIGINAL = 'def binary_search(arr, target):\n    lo, hi = 0, len(arr)\n    while lo < hi:\n        mid = (lo + hi) // 2\n        if arr[mid] < target: lo = mid + 1\n        else: hi = mid\n    return -1\n'
GOLDEN = 'def binary_search(arr, target):\n    lo, hi = 0, len(arr)\n    while lo < hi:\n        mid = (lo + hi) // 2\n        if arr[mid] < target: lo = mid + 1\n        elif arr[mid] > target: hi = mid\n        else: return mid\n    return -1\n'
VERIFIER = ('python3', '-c', 'from f import binary_search; assert binary_search([1,2,3,4,5],3)==2; assert binary_search([1,2,3,4,5],6)==-1')
EXPECTED_FAILURE = 'AssertionError'
