from src.logic import calculate
try:
    assert calculate(10, 0) == 0
    print('TEST_PASS')
except Exception as e:
    print(f'TEST_FAIL: {e}')
    exit(1)