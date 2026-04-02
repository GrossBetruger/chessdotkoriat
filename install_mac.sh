#!/usr/bin/env bash
set -e

echo "==> Installing Homebrew (if needed)..."
command -v brew >/dev/null || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

echo "==> Installing Stockfish..."
brew list stockfish &>/dev/null || brew install stockfish

echo "==> Installing uv..."
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh

echo "==> Installing Python 3.12 and project dependencies..."
uv python install 3.12
uv sync

echo ""
echo "Done! Run the app with:"
echo "  uv run python app.py"
