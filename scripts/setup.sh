#!/usr/bin/env bash
# aenigmata — development environment setup
# Usage: ./scripts/setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "==> Setting up aenigmata development environment"
echo "    Root: $ROOT_DIR"
echo

# ---------------------------------------------------------------------------
# Python environment
# ---------------------------------------------------------------------------
if command -v conda &>/dev/null; then
    echo "==> conda detected — creating/updating 'aenigmata' environment"
    conda env create -f "$ROOT_DIR/environment.yml" --name aenigmata 2>/dev/null \
        || conda env update -f "$ROOT_DIR/environment.yml" --name aenigmata
    echo
    echo "==> Installing Python package in editable mode"
    conda run -n aenigmata pip install -e "$ROOT_DIR[dev]"
    PYTHON_ACTIVATE="conda activate aenigmata"
else
    echo "==> conda not found — falling back to plain venv"
    python3 -m venv "$ROOT_DIR/.venv"
    # shellcheck disable=SC1091
    source "$ROOT_DIR/.venv/bin/activate"
    pip install --upgrade pip --quiet
    pip install -e "$ROOT_DIR[dev]"
    PYTHON_ACTIVATE="source .venv/bin/activate"
fi
echo

# ---------------------------------------------------------------------------
# Lexical database
# ---------------------------------------------------------------------------
echo "==> Initializing lexical database"
if command -v conda &>/dev/null; then
    conda run -n aenigmata python -m src.lexicon.db --init
else
    python -m src.lexicon.db --init
fi
echo

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
echo "==> Installing frontend dependencies"
if command -v npm &>/dev/null; then
    (cd "$ROOT_DIR/src/frontend" && npm install)
else
    echo "    WARNING: npm not found — install Node.js 20+ to build the frontend"
fi
echo

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "==> Setup complete"
echo
echo "    Activate Python env:  $PYTHON_ACTIVATE"
echo "    API server:           uvicorn src.api.main:app --reload --port 8000"
echo "    Frontend dev server:  cd src/frontend && npm run dev"
echo "    Run tests:            pytest tests/"
echo "    Lint:                 ruff check src/ tests/"
