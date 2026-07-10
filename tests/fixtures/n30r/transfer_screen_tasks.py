"""N30R-R3 transfer screen tasks — 8 tasks for local armor transfer screen."""
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class TransferTask:
    task_id: str
    family: str
    original: str
    golden: str
    verifier: Tuple[str, ...]
    expected_failure: str


TASKS = [
    # === localization (2) ===
    TransferTask(
        task_id="ts_loc_01",
        family="localization",
        original="def safe_divide(a, b):\n    return a / 0\n",
        golden="def safe_divide(a, b):\n    return a / b if b != 0 else 0\n",
        verifier=("python3", "-c", "from f import safe_divide; assert safe_divide(10,2)==5.0; assert safe_divide(10,0)==0"),
        expected_failure="ZeroDivisionError",
    ),
    TransferTask(
        task_id="ts_loc_02",
        family="localization",
        original="def first_even(nums):\n    for n in nums:\n        if n % 2 == 1:\n            return n\n    return None\n",
        golden="def first_even(nums):\n    for n in nums:\n        if n % 2 == 0:\n            return n\n    return None\n",
        verifier=("python3", "-c", "from f import first_even; assert first_even([1,3,4,5])==4; assert first_even([1,3,5])==None"),
        expected_failure="AssertionError",
    ),
    # === syntax/apply (2) ===
    TransferTask(
        task_id="ts_syn_01",
        family="syntax",
        original="def divide(a, b)\n    return a / b\n",
        golden="def divide(a, b):\n    return a / b\n",
        verifier=("python3", "-c", "from f import divide; assert divide(10,2)==5.0"),
        expected_failure="SyntaxError",
    ),
    TransferTask(
        task_id="ts_syn_02",
        family="syntax",
        original="class Calculator:\n    def add(self, a, b)\n        return a + b\n",
        golden="class Calculator:\n    def add(self, a, b):\n        return a + b\n",
        verifier=("python3", "-c", "from f import Calculator; assert Calculator().add(2,3)==5"),
        expected_failure="SyntaxError",
    ),
    # === semantic (2) ===
    TransferTask(
        task_id="ts_sem_01",
        family="semantic",
        original="def count_words(s):\n    return len(s.split('x'))\n",
        golden="def count_words(s):\n    return len(s.split())\n",
        verifier=("python3", "-c", "from f import count_words; assert count_words('hello world')==2; assert count_words('one')==1"),
        expected_failure="AssertionError",
    ),
    TransferTask(
        task_id="ts_sem_02",
        family="semantic",
        original="def reverse_list(lst):\n    return lst\n",
        golden="def reverse_list(lst):\n    return lst[::-1]\n",
        verifier=("python3", "-c", "from f import reverse_list; assert reverse_list([1,2,3])==[3,2,1]; assert reverse_list([])==[]"),
        expected_failure="AssertionError",
    ),
    # === mixed (2) ===
    TransferTask(
        task_id="ts_mix_01",
        family="mixed",
        original="def sum_until_negative(nums):\n    total = 0\n    for n in nums:\n        total += n\n    return total\n",
        golden="def sum_until_negative(nums):\n    total = 0\n    for n in nums:\n        if n < 0: break\n        total += n\n    return total\n",
        verifier=("python3", "-c", "from f import sum_until_negative; assert sum_until_negative([1,2,3,-1,4])==6; assert sum_until_negative([-1,2])==0"),
        expected_failure="AssertionError",
    ),
    TransferTask(
        task_id="ts_mix_02",
        family="mixed",
        original="def all_positive(nums):\n    return True\n",
        golden="def all_positive(nums):\n    return all(n > 0 for n in nums)\n",
        verifier=("python3", "-c", "from f import all_positive; assert all_positive([1,2,3]) is True; assert all_positive([1,-1,3]) is False"),
        expected_failure="AssertionError",
    ),
]
