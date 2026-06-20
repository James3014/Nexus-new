#!/bin/bash
# Astropy workspace bootstrap script
# T2.7 Baseline: astropy-legacy dependency profile

set -e

PYTHON_VERSION="${PYTHON_VERSION:-python3}"
REPO_DIR="${REPO_DIR:-.nexus/workspaces/astropy}"

echo "=== Astropy Workspace Bootstrap ==="

# 1. Check Python version
echo "Checking Python version..."
$PYTHON_VERSION --version

# 2. Create venv if not exists
if [ ! -d ".venv_astropy" ]; then
    echo "Creating venv..."
    $PYTHON_VERSION -m venv .venv_astropy
fi

source .venv_astropy/bin/activate

# 3. Install dependencies
echo "Installing dependencies..."
pip install --quiet beautifulsoup4==4.15.0 lxml==6.1.1 soupsieve==2.8.4

# 4. Validate imports
echo "Validating imports..."
python -c "import astropy; print(f'astropy: {astropy.__version__}')"
python -c "import bs4; print(f'bs4: {bs4.__version__}')"
python -c "import lxml; print(f'lxml: {lxml.__version__}')"

# 5. Validate workspace
if [ -d "$REPO_DIR" ]; then
    echo "Repo root exists: $REPO_DIR"
else
    echo "WARNING: Repo root not found at $REPO_DIR"
fi

echo "=== Astropy Bootstrap Complete ==="
