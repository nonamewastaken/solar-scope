#!/usr/bin/env bash
# Sets up the project on macOS or Linux.
# Run it from the project folder with:  bash setup.sh
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. See docs/environment-setup.md, then run this again."
  exit 1
fi

echo "Creating the virtual environment in .venv"
python3 -m venv .venv

echo "Installing dependencies"
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt

echo
echo "Done. Activate the environment with:"
echo "    source .venv/bin/activate"
echo
echo "Then check everything works with:"
echo "    python src/app.py"
echo "    pytest"
