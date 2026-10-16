import sys
import os
import numpy as np
import astropy
from astropy.modeling import models as m
from astropy.modeling.separable import separability_matrix

def test_separability_nested():
    print(f"--- ASTROPY LOCATION ---")
    print(f"Loaded from: {astropy.__file__}")
    print(f"Version: {getattr(astropy, '__version__', 'unknown')}")
    print(f"------------------------")

    cm = m.Linear1D(10) & m.Linear1D(5)
    model = m.Pix2Sky_TAN() & cm
    matrix = separability_matrix(model)
    
    expected = np.array([
        [ True,  True, False, False],
        [ True,  True, False, False],
        [False, False,  True, False],
        [False, False, False,  True]
    ])
    
    print("Computed separability matrix:")
    print(matrix)
    
    if np.array_equal(matrix, expected):
        print("SUCCESS: Separability matrix is correct.")
        sys.exit(0)
    else:
        print("FAILURE: Separability matrix is incorrect for nested CompoundModels!")
        sys.exit(1)

if __name__ == "__main__":
    try:
        test_separability_nested()
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
