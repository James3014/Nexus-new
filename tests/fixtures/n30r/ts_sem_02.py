ORIGINAL = 'def reverse_list(lst):\n    return lst\n'
GOLDEN = 'def reverse_list(lst):\n    return lst[::-1]\n'
VERIFIER = ('python3', '-c', 'from f import reverse_list; assert reverse_list([1,2,3])==[3,2,1]; assert reverse_list([])==[]')
EXPECTED_FAILURE = 'AssertionError'
