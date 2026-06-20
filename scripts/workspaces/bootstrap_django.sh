#!/bin/bash
# Django workspace bootstrap script
# T2.7 Baseline: django-legacy dependency profile

set -e

PYTHON_VERSION="${PYTHON_VERSION:-python3}"
REPO_DIR="${REPO_DIR:-.nexus/workspaces/django}"

echo "=== Django Workspace Bootstrap ==="

# 1. Check Python version
echo "Checking Python version..."
$PYTHON_VERSION --version

# 2. Create venv if not exists
if [ ! -d ".venv_django" ]; then
    echo "Creating venv..."
    $PYTHON_VERSION -m venv .venv_django
fi

source .venv_django/bin/activate

# 3. Install dependencies
echo "Installing dependencies..."
pip install --quiet django

# 4. Validate imports
echo "Validating imports..."
python -c "import django; print(f'django: {django.__version__}')"

# 5. Validate workspace
if [ -d "$REPO_DIR" ]; then
    echo "Repo root exists: $REPO_DIR"
else
    echo "WARNING: Repo root not found at $REPO_DIR"
fi

echo "=== Django Bootstrap Complete ==="
