from bounds import is_in_range

assert is_in_range(5, 5, 10) is True, "is_in_range(5, 5, 10) should be True"
assert is_in_range(11, 5, 10) is False, "is_in_range(11, 5, 10) should be False"
