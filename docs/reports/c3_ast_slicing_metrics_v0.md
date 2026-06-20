# C3 — AST Slicing Metrics Report

**Status**: C3_AST_SLICING_COMPLETED
**Track**: Capability-First Post-V6 Execution Track

---

## 1. Slicing Metrics Summary

本階段利用 `SurgicalSlicer` 對 3 個重現任務的 target files 進行了 AST 切片，並將龐大的原始檔案縮減為僅包含 target symbol 及其關鍵依賴的精簡 context。這大幅減少了 LLM 處理的 token 數量並提升了 context 精確度。

| 任務 ID | 實例 ID | 目標 Symbol | 原始檔行數 | 切片檔行數 | Token 估計 | 縮減比例 | 依賴 symbols |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| `C_13453` | `astropy__astropy-13453` | `HTML` | 477 | 404 | 3932 | 15.3% | HTML, HTMLHeader, HTMLSplitter, SoupString, HTMLData (+4 more) |
| `C_11618` | `sympy__sympy-11618` | `Point` | 1352 | 1382 | 9022 | -2.2% | Point, evalf, x, __div__, origin (+5 more) |
| `C_12481` | `sympy__sympy-12481` | `Permutation` | 2835 | 3214 | 22259 | -13.4% | Permutation, size, max, cyclic_form, list (+19 more) |

---

## 2. Detailed Slicing Results

### C_13453 (astropy__astropy-13453)
*   **原始檔案**: [.nexus/workspaces/astropy/astropy/io/ascii/html.py](file:///Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy/astropy/io/ascii/html.py) (477 行)
*   **切片檔案**: [sliced_context.py](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/c3_ast_slicing_metrics_v0/C_13453/sliced_context.py) (404 行)
*   **Token 估計**: 3932
*   **分析的依賴**: 9 個
```python
# Sliced Context Reference (First 15 lines):

import warnings
from . import core
from astropy.table import Column
from astropy.utils.xml import writer
from copy import deepcopy


# --- Value-Flow Sorted Slice ---

# Score: 5.0 | Symbol: HTML

class HTML(core.BaseReader):
    """HTML format table.

    In order to customize input and output, a dict of parameters may
# ... [truncated]
```

### C_11618 (sympy__sympy-11618)
*   **原始檔案**: [.nexus/workspaces/sympy/sympy/geometry/point.py](file:///Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy/sympy/geometry/point.py) (1352 行)
*   **切片檔案**: [sliced_context.py](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/c3_ast_slicing_metrics_v0/C_11618/sliced_context.py) (1382 行)
*   **Token 估計**: 9022
*   **分析的依賴**: 10 個
```python
# Sliced Context Reference (First 15 lines):

from __future__ import division, print_function
import warnings
from sympy.core import S, sympify, Expr
from sympy.core.numbers import Number
from sympy.core.compatibility import iterable, is_sequence, as_int
from sympy.core.containers import Tuple
from sympy.simplify import nsimplify, simplify
from sympy.geometry.exceptions import GeometryError
from sympy.functions.elementary.miscellaneous import sqrt
from sympy.functions.elementary.complexes import im
from sympy.matrices import Matrix
from sympy.core.relational import Eq
from sympy.core.numbers import Float
from sympy.core.evaluate import global_evaluate
from sympy.core.add import Add
# ... [truncated]
```

### C_12481 (sympy__sympy-12481)
*   **原始檔案**: [.nexus/workspaces/sympy/sympy/combinatorics/permutations.py](file:///Users/jameschen/Workspace/nexus/.nexus/workspaces/sympy/sympy/combinatorics/permutations.py) (2835 行)
*   **切片檔案**: [sliced_context.py](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/c3_ast_slicing_metrics_v0/C_12481/sliced_context.py) (3214 行)
*   **Token 估計**: 22259
*   **分析的依賴**: 24 個
```python
# Sliced Context Reference (First 15 lines):

from __future__ import print_function, division
import random
from collections import defaultdict
from sympy.core import Basic
from sympy.core.compatibility import is_sequence, reduce, range, as_int
from sympy.utilities.iterables import flatten, has_variety, minlex, has_dups, runs
from sympy.polys.polytools import lcm
from sympy.matrices import zeros
from mpmath.libmp.libintmath import ifac


# --- Value-Flow Sorted Slice ---

# Score: 16.0 | Symbol: Permutation

# ... [truncated]
```
