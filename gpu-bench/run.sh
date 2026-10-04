#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# Explicit opt-in: generated Python executes locally. Read README and use a disposable environment.
exec python3 bench.py --allow-code-execution "$@"
