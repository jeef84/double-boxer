#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Override in the environment if SSH uses different account/host aliases.
LAB="${BENCH_LAB_SSH:-j@100.120.160.53}"
CUDA="${BENCH_CUDA_SSH:-j@100.75.127.122}"
remote() { ssh -o BatchMode=yes -o ConnectTimeout=10 "$1" bash -s -- "$2" "$3" < scripts/node.sh; }
remote "$LAB" stop 100.120.160.53
remote "$CUDA" stop 100.75.127.122
case "$1" in
 stop) ;;
 single) remote "$LAB" single 100.120.160.53 ;;
 rpc-iq3|rpc-q5)
  remote "$CUDA" rpc-worker 100.75.127.122
  remote "$LAB" "$1" 100.120.160.53 ;;
 independent)
  remote "$LAB" single 100.120.160.53
  remote "$CUDA" single 100.75.127.122 ;;
 *) echo "Unknown scenario $1" >&2; exit 1 ;;
esac
