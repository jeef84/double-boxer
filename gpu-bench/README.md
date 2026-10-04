# Two-node GPU architecture benchmark

A single-command, Python-standard-library benchmark for Jeff's two RTX 3060 12 GB boxes. It produces a print-friendly HTML report, Markdown report, CSV trial table, JSON summaries, raw model responses, unittest outputs, server identities and optional GPU/network samples. No cloud model calls or paid APIs.

## What it compares

| Scenario | Resources | Accuracy workflow | Throughput workflow |
|---|---|---|---|
| single-iq3 | labcomp GPU, 27B IQ3_XXS | One model per task | One endpoint, 1/2/4 clients |
| rpc-iq3 | Both GPUs, same IQ3 file | One distributed model | One endpoint, 1/2/4 clients |
| rpc-q5 | Both GPUs, 27B Q5_K_M | One distributed model | One endpoint, 1/2/4 clients |
| independent | One IQ3 model per GPU | Tasks alternate endpoints by repeat | Round-robin request pool across both |
| collaborating | One IQ3 model per GPU | Producer → independent reviewer → producer revision | Same request pool; not collaborative-task throughput |

Single-IQ3 versus RPC-IQ3 isolates architecture approximately. RPC-Q5 versus IQ3 tests the quality enabled by capacity, and changes quantization method as well as precision. Independent versus collaborating tests review/revision overhead and benefit. A two-GPU local-motherboard setup can be added as another scenario using the same endpoint structure and your own setup script.

This is a controlled API benchmark, not an OpenCode automation wrapper. It measures structured review, executable coding, generated tests and artifact exchange. It does not measure general shell-tool selection, web search, editor ergonomics or large repository work. Those require a separate harness and task corpus.

## First-time setup on the Mac

1. Unzip this folder somewhere outside the existing test project, for example `~/gpu-bench`.
2. Python 3.10+ is required. No pip packages are needed.
3. Both boxes must already have the matching RPC-enabled llama.cpp builds we set up. The supplied scripts use `~/inference/llama.cpp/build/bin`.
4. SSH must work without interactive prompts:
   ```bash
   ssh -o BatchMode=yes j@100.120.160.53 true
   ssh -o BatchMode=yes j@100.75.127.122 true
   ```
   Configure normal SSH keys and verify host fingerprints once if needed. Tailscale SSH is not required. If you use SSH aliases, change `nodes[].ssh` in config.json and set BENCH_LAB_SSH / BENCH_CUDA_SSH in your environment for the server controller.
5. Stop the manually launched llama-server and RPC server once with Ctrl-C. The controller deliberately does not kill arbitrary preexisting processes. It will subsequently start/stop only its managed server processes. vLLM must also be stopped to free VRAM.
6. Generated Python is executed on the machine running the harness. `-I` and timeouts are NOT a security sandbox. Use a disposable macOS account/VM or a container without personal files/secrets, with network restricted where practical. `run.sh` explicitly enables generated-code execution. For a no-code option, set `settings.tasks` to `["ttl_review"]` and run `python3 bench.py` without the execution flag. The built-in fixtures are small, but untrusted generated Python retains your OS user's permissions.

## One command

From the unzipped folder:

```bash
bash run.sh
```

The full default run cycles all five configurations, performs three repeats of four tasks per configuration (60 task trials), and tests concurrency 1, 2 and 4. It may take hours on these cards. Warmup and model loading/download time are excluded from task timing. Server setup may download the cached IQ3 and Q5 models if absent. Keep the Mac awake; you can run `caffeinate -i bash run.sh` instead.

Your current Q5 server can be tested without switching servers or setting up SSH:

```bash
bash run.sh --config config-current.json
```

That produces a measured Q5 baseline only, not a multi-architecture comparison. It expects the server already running at 100.120.160.53:8000.

Limit a full controlled run to selected scenarios:

```bash
bash run.sh --scenario single-iq3 --scenario rpc-iq3
```

Resume after an interruption (completed trials are not repeated):

```bash
bash run.sh --resume runs/20261004-180000
```

Use the same config file and scenario flags when resuming. Setup is repeated, and incomplete load tests are repeated; completed trial evidence is preserved. Ctrl-C may leave managed servers alive; the next setup stops them. For explicit cleanup:

```bash
bash scripts/scenario.sh stop
```

Rebuild reports without any model calls:

```bash
python3 bench.py --report-only runs/20261004-180000
```

## Automated accuracy scoring

Four fixed, versioned tasks:

- **TTL review:** classify the five known behaviors and identify exactly the three seeded defects. Outcomes and category precision are scored deterministically. Explanations are retained but not semantically graded.
- **Generate TTL regression tests:** exactly five tests are run against the original (expected 2 pass / 2 fail / 1 error), corrected code (all pass), and isolated frozen-clock, eviction, exact-boundary and missing-reset mutations (must fail with assertions, not unrelated import errors). This rejects many superficially passing or defective tests.
- **Merge intervals implementation:** six trusted unittest cases check overlap, touching endpoints, nested/negative ranges, input immutability, empty input and invalid reversed intervals.
- **TTL implementation:** six trusted cases check expiration-before-eviction, update at capacity and exact deadlines, LRU access, zero TTL, never-expiring entries and invalid capacity.

These are synthetic fixtures inspired by the earlier review, not edits to your real review-target files. Every trial starts from a fresh request; generated artifacts go into its own directory. The reviewer never sees trusted grading tests/results before revising. Generated-code execution uses subprocesses with timeouts. The harness trusts the server and generated code to be non-adversarial; subprocess isolation does not prevent deliberate grader tampering.

A task succeeds only if all its checks pass. Partial check scores are separate. No model's claim that tests passed is used as evidence. Infrastructure errors are recorded separately and remain unsuccessful attempts.

## Metrics and how to read them

- **Task success rate:** completed correct tasks / attempted task trials. Different task types are equally weighted. Also inspect per-task rows in trials.csv: pooled scores can hide weaknesses.
- **Mean check score:** partial correctness, distinct from full task success.
- **Task median and p95:** end-to-end seconds, including all inference rounds and grading.
- **TTFT / first text:** client request start to first streamed content OR reasoning text; a chunk can contain multiple tokens, so this is an observable proxy for token arrival.
- **First answer:** request start to first final content text, excluding separate reasoning. If a server places thinking in content instead, that metric cannot distinguish it.
- **Requests/min:** successful completion count / wall time of the load batch. This is response completion throughput, not correctness-weighted throughput.
- **Output tokens/s:** summed server-reported completion tokens / batch wall time. Missing usage stays missing. Thinking may count as completion tokens. It is not the same as per-request decoding speed.
- **Telemetry:** one-second GPU memory/utilization/power/temperature samples and Tailscale interface cumulative byte counters. SSH telemetry is optional and failures are logged. These counters include other traffic; an RPC-only packet trace is not performed. Low bytes/s does not rule out latency bottlenecks.

TTFT includes queuing, input processing and network time. It does not isolate pure GPU prefill. Full raw server timings, when emitted, are preserved in responses. No tokenizer estimates, dollar costs, energy or wall power are fabricated.

Sample sizes are small and repeated prompts correlated. A reported Wilson interval is descriptive; it does not demonstrate general coding reliability. Three repeats is a screening run; increase repeats and add domain tasks before relying on a model for your work.

## Fairness and reproducibility

- Same context 32768, output cap 4096, thinking budget 1024, temperature 0, cache q8_0, batch512/ubatch128 and one server slot in supplied scripts.
- With one slot, concurrency tests deliberately include queuing. This measures the currently deployed configuration, not maximum tuned throughput. For a later tuning experiment increase --parallel and memory allocation explicitly, label a new scenario and record settings.
- Warmup is excluded. Shared-prefix KV caches may remain warm; unique trial markers do not guarantee cold cache. Cold-prefill requires server-specific reset/restart controls.
- Seeded randomized task order within each configuration. Configuration order is fixed, so thermal/time drift is still a potential confound.
- Suite SHA256, configuration, client Python/platform, server /models, llama.cpp commit and GPU metadata are saved. The config filename labels a requested model; /models and startup logs are evidence of the loaded model, not a cryptographic attestation of weights.
- Setup scripts operate sequentially; the two configurations which compete for the same GPUs are never benchmarked together.
- Your 16 GB host RAM can be under pressure while loading Q5; startup and RSS/swap diagnosis should be inspected if it stalls. GPU memory capacity and host-memory capacity are different constraints.

## Report outputs

`runs/<timestamp>/report.html` is fully offline and print-friendly: open it in a browser and print to PDF for a presentation. `report.md`, `trials.csv` and `summary.json` are companions. Each scenario includes server identity/environment, telemetry and raw per-trial content/reasoning, grades and test outputs. Setup failures are displayed instead of invented measurements. Logs may contain model output and SSH host identities; no API key values are intentionally saved.

The folder `sample-report` contains a **MOCK integration-test report**, useful to preview the layout. Its numbers are not measurements of either GPU and must not be presented as hardware results.

## Configuration changes

Edit config.json once to choose repeats, tasks, concurrency, endpoint/model aliases or scenarios. API keys use `api_key_env` variable names; never paste key values into config. Endpoint `request_overrides` can supply backend-specific options, but cannot disable streaming. Endpoint URLs must end in `/v1`.

To add an already-running same-motherboard or other hardware setup, duplicate a scenario, change its id/label/architecture/endpoints and delete setup_argv/teardown_argv. Keep the same model/quantization and context for architecture-only comparisons.

The automated server scripts bind to your known Tailscale IPs and use unauthenticated experimental RPC. Keep it within your trusted tailnet; do not port-forward RPC to the Internet.

## Validate the toolkit locally

```bash
python3 -m unittest test_harness -v
```

Validation uses a local mocked SSE API plus actual Python unittest execution. It does not contact the CUDA boxes. Remote startup scripts are syntax-checked locally; their real execution needs your hosts.

## Primary references

- llama.cpp server API/settings: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- llama.cpp RPC usage/status: https://github.com/ggml-org/llama.cpp/blob/master/tools/rpc/README.md
- IQ3 weights: https://huggingface.co/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF
- Q5 weights: https://huggingface.co/bartowski/Qwen3.8-27B-GGUF

Toolkit created 2026-10-04. Protocol behavior should be checked if backends change.
