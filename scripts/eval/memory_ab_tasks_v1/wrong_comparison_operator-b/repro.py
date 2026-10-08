from grading import has_passing

assert has_passing([60], 60) is True, "has_passing([60], 60) should be True"
assert has_passing([59], 60) is False, "has_passing([59], 60) should be False"
