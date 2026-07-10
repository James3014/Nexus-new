"""N30R heldout task fixtures — 24 tasks in 4 families.

Each task provides ORIGINAL (broken) and GOLDEN (fixed) source,
plus VERIFIER command and EXPECTED_FAILURE.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class HeldoutTask:
    task_id: str
    family: str
    original: str
    golden: str
    verifier: Tuple[str, ...]
    expected_failure: str


TASKS = [
    # === FAMILY: localization (6) ===
    HeldoutTask(
        task_id="h_loc_01",
        family="localization",
        original="def abs_val(x):\n    return -x\n",
        golden="def abs_val(x):\n    return x if x >= 0 else -x\n",
        verifier=("python3", "-c", "from f import abs_val; assert abs_val(5)==5; assert abs_val(-3)==3"),
        expected_failure="AssertionError",
    ),
    HeldoutTask(
        task_id="h_loc_02",
        family="localization",
        original="def max_of_two(a, b):\n    return a\n",
        golden="def max_of_two(a, b):\n    return a if a >= b else b\n",
        verifier=("python3", "-c", "from f import max_of_two; assert max_of_two(3,5)==5; assert max_of_two(7,2)==7"),
        expected_failure="AssertionError",
    ),
    HeldoutTask(
        task_id="h_loc_03",
        family="localization",
        original="def clamp(val, lo, hi):\n    return val\n",
        golden="def clamp(val, lo, hi):\n    return max(lo, min(hi, val))\n",
        verifier=("python3", "-c", "from f import clamp; assert clamp(5,1,10)==5; assert clamp(-1,0,10)==0; assert clamp(15,0,10)==10"),
        expected_failure="AssertionError",
    ),
    HeldoutTask(
        task_id="h_loc_04",
        family="localization",
        original="def sign(x):\n    return 1\n",
        golden="def sign(x):\n    if x > 0: return 1\n    if x < 0: return -1\n    return 0\n",
        verifier=("python3", "-c", "from f import sign; assert sign(5)==1; assert sign(-3)==-1; assert sign(0)==0"),
        expected_failure="AssertionError",
    ),
    HeldoutTask(
        task_id="h_loc_05",
        family="localization",
        original="def swap(a, b):\n    return a, a\n",
        golden="def swap(a, b):\n    return b, a\n",
        verifier=("python3", "-c", "from f import swap; assert swap(1,2)==(2,1)"),
        expected_failure="AssertionError",
    ),
    HeldoutTask(
        task_id="h_loc_06",
        family="localization",
        original="def negate(x):\n    return x\n",
        golden="def negate(x):\n    return -x\n",
        verifier=("python3", "-c", "from f import negate; assert negate(5)==-5; assert negate(-3)==3"),
        expected_failure="AssertionError",
    ),

    # === FAMILY: syntax/parse (6) ===
    HeldoutTask(
        task_id="h_syn_01",
        family="syntax",
        original="def add(a, b)\n    return a + b\n",
        golden="def add(a, b):\n    return a + b\n",
        verifier=("python3", "-c", "from f import add; assert add(2,3)==5"),
        expected_failure="SyntaxError",
    ),
    HeldoutTask(
        task_id="h_syn_02",
        family="syntax",
        original="class Foo:\n    def bar(self)\n        return 42\n",
        golden="class Foo:\n    def bar(self):\n        return 42\n",
        verifier=("python3", "-c", "from f import Foo; assert Foo().bar()==42"),
        expected_failure="SyntaxError",
    ),
    HeldoutTask(
        task_id="h_syn_03",
        family="syntax",
        original="if True\n    x = 1\n",
        golden="if True:\n    x = 1\n",
        verifier=("python3", "-c", "exec(open('f.py').read()); assert x == 1"),
        expected_failure="SyntaxError",
    ),
    HeldoutTask(
        task_id="h_syn_04",
        family="syntax",
        original="for i in range(5)\n    pass\n",
        golden="for i in range(5):\n    pass\n",
        verifier=("python3", "-c", "exec(open('f.py').read())"),
        expected_failure="SyntaxError",
    ),
    HeldoutTask(
        task_id="h_syn_05",
        family="syntax",
        original="def fn():\n    x = 1\n    x = 2\n    return x\n",
        golden="def fn():\n    return 1\n",
        verifier=("python3", "-c", "from f import fn; assert fn()==1"),
        expected_failure="AssertionError",
    ),
    HeldoutTask(
        task_id="h_syn_06",
        family="syntax",
        original="x = [1, 2, 3]\ny = x[5]\n",
        golden="x = [1, 2, 3]\ny = x[2]\n",
        verifier=("python3", "-c", "exec(open('f.py').read()); assert y == 3"),
        expected_failure="IndexError",
    ),

    # === FAMILY: semantic (6) ===
    HeldoutTask(
        task_id="h_sem_01",
        family="semantic",
        original="def factorial(n):\n    if n == 0: return 0\n    return n * factorial(n-1)\n",
        golden="def factorial(n):\n    if n == 0: return 1\n    return n * factorial(n-1)\n",
        verifier=("python3", "-c", "from f import factorial; assert factorial(5)==120; assert factorial(0)==1"),
        expected_failure="AssertionError",
    ),
    HeldoutTask(
        task_id="h_sem_02",
        family="semantic",
        original="def fibonacci(n):\n    if n <= 1: return 1\n    return fibonacci(n-1) + fibonacci(n-2)\n",
        golden="def fibonacci(n):\n    if n <= 1: return n\n    return fibonacci(n-1) + fibonacci(n-2)\n",
        verifier=("python3", "-c", "from f import fibonacci; assert fibonacci(0)==0; assert fibonacci(1)==1; assert fibonacci(6)==8"),
        expected_failure="AssertionError",
    ),
    HeldoutTask(
        task_id="h_sem_03",
        family="semantic",
        original="def is_palindrome(s):\n    return s == s\n",
        golden="def is_palindrome(s):\n    return s == s[::-1]\n",
        verifier=("python3", "-c", "from f import is_palindrome; assert is_palindrome('racecar') is True; assert is_palindrome('hello') is False"),
        expected_failure="AssertionError",
    ),
    HeldoutTask(
        task_id="h_sem_04",
        family="semantic",
        original="def flatten(lst):\n    return lst\n",
        golden="def flatten(lst):\n    result = []\n    for item in lst:\n        if isinstance(item, list):\n            result.extend(flatten(item))\n        else:\n            result.append(item)\n    return result\n",
        verifier=("python3", "-c", "from f import flatten; assert flatten([1,[2,[3]],4])==[1,2,3,4]"),
        expected_failure="AssertionError",
    ),
    HeldoutTask(
        task_id="h_sem_05",
        family="semantic",
        original="def binary_search(arr, target):\n    lo, hi = 0, len(arr)\n    while lo < hi:\n        mid = (lo + hi) // 2\n        if arr[mid] < target: lo = mid + 1\n        else: hi = mid\n    return -1\n",
        golden="def binary_search(arr, target):\n    lo, hi = 0, len(arr)\n    while lo < hi:\n        mid = (lo + hi) // 2\n        if arr[mid] < target: lo = mid + 1\n        elif arr[mid] > target: hi = mid\n        else: return mid\n    return -1\n",
        verifier=("python3", "-c", "from f import binary_search; assert binary_search([1,2,3,4,5],3)==2; assert binary_search([1,2,3,4,5],6)==-1"),
        expected_failure="AssertionError",
    ),
    HeldoutTask(
        task_id="h_sem_06",
        family="semantic",
        original="def gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return b\n",
        golden="def gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return a\n",
        verifier=("python3", "-c", "from f import gcd; assert gcd(12,8)==4; assert gcd(7,13)==1"),
        expected_failure="AssertionError",
    ),

    # === FAMILY: mixed (6) ===
    HeldoutTask(
        task_id="h_mix_01",
        family="mixed",
        original="def count_chars(s):\n    d = {}\n    for c in s:\n        d[c] = d.get(c, 0)\n    return d\n",
        golden="def count_chars(s):\n    d = {}\n    for c in s:\n        d[c] = d.get(c, 0) + 1\n    return d\n",
        verifier=("python3", "-c", "from f import count_chars; r=count_chars('aab'); assert r['a']==2 and r['b']==1"),
        expected_failure="AssertionError",
    ),
    HeldoutTask(
        task_id="h_mix_02",
        family="mixed",
        original="def unique(lst):\n    return list(lst)\n",
        golden="def unique(lst):\n    return list(dict.fromkeys(lst))\n",
        verifier=("python3", "-c", "from f import unique; assert unique([1,2,2,3])==[1,2,3]"),
        expected_failure="AssertionError",
    ),
    HeldoutTask(
        task_id="h_mix_03",
        family="mixed",
        original="def chunk(lst, n):\n    result = []\n    for i in range(0, len(lst), n):\n        result.append(lst[i:i+n])\n    result.append(lst[-1])\n    return result\n",
        golden="def chunk(lst, n):\n    return [lst[i:i+n] for i in range(0, len(lst), n)]\n",
        verifier=("python3", "-c", "from f import chunk; assert chunk([1,2,3,4,5],2)==[[1,2],[3,4],[5]]"),
        expected_failure="AssertionError",
    ),
    HeldoutTask(
        task_id="h_mix_04",
        family="mixed",
        original="def compact(s):\n    return ' '.join(s.split('x'))\n",
        golden="def compact(s):\n    return ' '.join(s.split())\n",
        verifier=("python3", "-c", "from f import compact; assert compact('  a  b  ')=='a b'"),
        expected_failure="AssertionError",
    ),
    HeldoutTask(
        task_id="h_mix_05",
        family="mixed",
        original="def interleave(a, b):\n    result = []\n    i = 0\n    while i < len(a):\n        result.append(a[i])\n        i += 1\n    i = 0\n    while i < len(b):\n        result.append(b[i])\n        i += 1\n    return result\n",
        golden="def interleave(a, b):\n    result = []\n    i = 0\n    while i < len(a) or i < len(b):\n        if i < len(a): result.append(a[i])\n        if i < len(b): result.append(b[i])\n        i += 1\n    return result\n",
        verifier=("python3", "-c", "from f import interleave; assert interleave([1,3],[2,4])==[1,2,3,4]"),
        expected_failure="AssertionError",
    ),
    HeldoutTask(
        task_id="h_mix_06",
        family="mixed",
        original="def zip_with(f, a, b):\n    return [f(x) for x in a]\n",
        golden="def zip_with(f, a, b):\n    return [f(x, y) for x, y in zip(a, b)]\n",
        verifier=("python3", "-c", "from f import zip_with; r=zip_with(lambda x,y:x-y,[1,2,3],[4,5]); assert r==[-3,-3]"),
        expected_failure="AssertionError",
    ),
]
