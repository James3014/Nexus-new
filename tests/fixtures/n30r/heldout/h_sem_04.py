ORIGINAL = 'def flatten(lst):\n    return lst\n'
GOLDEN = 'def flatten(lst):\n    result = []\n    for item in lst:\n        if isinstance(item, list):\n            result.extend(flatten(item))\n        else:\n            result.append(item)\n    return result\n'
VERIFIER = ('python3', '-c', 'from f import flatten; assert flatten([1,[2,[3]],4])==[1,2,3,4]')
EXPECTED_FAILURE = 'AssertionError'
