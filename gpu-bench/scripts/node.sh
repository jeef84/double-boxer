#!/usr/bin/env bash
# Uploaded over stdin by scenario.sh. Controls only processes started by this harness.
set -euo pipefail
mode="$1"
address="$2"
state="$HOME/inference/gpu-bench-managed"
mkdir -p "$state"
stop_owned() {
  for name in server rpc; do
    if [[ -f "$state/$name.pid" ]]; then
      pid=$(cat "$state/$name.pid")
      if kill -0 "$pid" 2>/dev/null; then
        cmd=$(ps -p "$pid" -o args=)
        case "$cmd" in
          *llama-server*|*ggml-rpc-server*) kill "$pid"; for attempt in {1..30}; do kill -0 "$pid" 2>/dev/null || break; sleep 1; done ;;
          *) echo "Refusing to stop reused PID $pid: $cmd" >&2; exit 1 ;;
        esac
      fi
      rm -f "$state/$name.pid"
    fi
  done
}
stop_owned
[[ "$mode" == stop ]] && exit 0
cd "$HOME/inference/llama.cpp"
port=8000
[[ "$mode" == rpc-worker ]] && port=50052
python3 - "$address" "$port" <<'PYPORT'
import socket,sys
try:
 s=socket.create_connection((sys.argv[1],int(sys.argv[2])),timeout=2)
except OSError:
 sys.exit(0)
else:
 s.close();sys.exit("Port already in use; stop the manually started server first")
PYPORT
if [[ "$mode" == rpc-worker ]]; then
  nohup ./build/bin/ggml-rpc-server --host "$address" --port 50052 --device CUDA0 -c \
    > "$state/rpc.log" 2>&1 < /dev/null &
  echo $! > "$state/rpc.pid"
  sleep 2
  kill -0 "$(cat "$state/rpc.pid")"
  exit 0
fi
repo=ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF
file=Qwen3.8-27B-GSQ-RCO-IQ3_XXS.gguf
args=()
if [[ "$mode" == rpc-q5 ]]; then
  repo=bartowski/Qwen3.8-27B-GGUF
  file=Qwen3.8-27B-Q5_K_M.gguf
fi
if [[ "$mode" == rpc-* ]]; then
  args=(--rpc 100.75.127.122:50052 --device CUDA0,RPC0 --split-mode layer --tensor-split 1,1)
fi
nohup ./build/bin/llama-server --hf-repo "$repo" --hf-file "$file" \
 --no-mmproj --alias local-coder --host "$address" --port 8000 \
 --ctx-size 32768 --parallel 1 --gpu-layers all --flash-attn on \
 --cache-type-k q8_0 --cache-type-v q8_0 --batch-size 512 --ubatch-size 128 \
 --jinja --no-reasoning-preserve --reasoning-budget 1024 "${args[@]}" \
 > "$state/server.log" 2>&1 < /dev/null &
echo $! > "$state/server.pid"
# /health returns 503 during loading. Downloads/load are excluded from benchmark timing.
for attempt in {1..1800}; do
  if ! kill -0 "$(cat "$state/server.pid")" 2>/dev/null; then tail -n 60 "$state/server.log"; exit 1; fi
  if curl -fsS --max-time 2 "http://$address:8000/health" > /dev/null 2>&1; then exit 0; fi
  sleep 1
done
echo 'Startup timeout; inspect ~/inference/gpu-bench-managed/server.log' >&2
exit 1
