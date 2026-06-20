#!/bin/bash
# Sympy workspace bootstrap script
# T2.7 Baseline: sympy-python39 dependency profile

set -e

PYTHON_VERSION="${PYTHON_VERSION:-python3.9}"
REPO_DIR="${REPO_DIR:-.nexus/workspaces/sympy}"

echo "=== Sympy Workspace Bootstrap ==="
echo "NOTE: sympy 1.0.1.dev uses collections.Mapping (Python 3.9 required)"

# 1. Check Python version
echo "Checking Python version..."
$PYTHON_VERSION --version

# 2. Create venv if not exists
if [ ! -d ".venv_sympy" ]; then
    echo "Creating venv..."
    $PYTHON_VERSION -m venv .venv_sympy
fi

source .venv_sympy/bin/activate

# 3. Install dependencies
echo "Installing dependencies..."
pip install --quiet mpmath

# 4. Set PYTHONPATH
export PYTHONPATH="${REPO_DIR}:${PYTHONPATH:-}"

# 5. Validate imports
echo "Validating imports..."
python -c "import sympy; print(f'sympy: {sympy.__version__}')"
python -c "import mpmath; print(f'mpmath: {mpmath.__version__}')"

# 6. Validate workspace
if [ -d "$REPO_DIR" ]; then
    echo "Repo root exists: $REPO_DIR"
else
    echo "WARNING: Repo root not found at $REPO_DIR"
fi

echo "=== Sympy Bootstrap Complete ==="
