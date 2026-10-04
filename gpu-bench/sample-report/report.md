# GPU architecture benchmark
Run: MOCK integration test only — no GPU measurements · Harness 1.0.0

## Measured comparison
| Configuration | Architecture | Success | Mean check score | Task median / p95 (s) | First text / answer median (s) |
|---|---|---:|---:|---:|---:|
| MOCK SERVER — NOT GPU MEASUREMENTS | mock_validation | 2/2 | 1.00 | 0.00 / 0.00 | 0.00 / 0.00 |

## Concurrency and throughput
| Configuration | Clients | Completed / attempted | Requests/min | Reported output tokens/s | p95 first text (s) |
|---|---:|---:|---:|---:|---:|
| MOCK SERVER — NOT GPU MEASUREMENTS | 1 | 2/2 | 43648.24 | 30553.77 | 0.00 |
| MOCK SERVER — NOT GPU MEASUREMENTS | 2 | 2/2 | 73445.57 | 51411.90 | 0.00 |

## Interpretation and limits
- Success means all independent checks for a task passed; a correct partial answer is not a task success.
- Review uses a synthetic version of the TTL defects, not your original files. Coding uses six independent unittest checks per task. Generated regression tests are scored against the original, a fixed implementation and four isolated mutations. No model self-reported counts are trusted.
- First text includes reasoning; first answer excludes reasoning. These are client-observed times from request start, including queue/network delay, and SSE chunks can contain multiple tokens.
- Throughput tokens come only from server-reported usage and include reasoning when the server counts it. Missing counts remain missing; characters are never called tokens.
- Task time includes all model calls and grading. Collaborating agents use producer → reviewer → producer; parallel-independent load uses round-robin routing across endpoints.
- Model/quantization changes confound architecture comparisons. Use the same file/settings on one GPU and RPC to isolate transport; compare IQ3 single versus Q5 RPC separately as a capacity-enabled quality comparison.
- Requests include unique trial markers, but shared prefix caches may remain warm. This is an application benchmark, not a guaranteed cold-prefill benchmark. Warmup is excluded.
- GPU/network samples cover each scenario, including warmup and load tests. Tailscale counters include all traffic on that interface, not RPC-only traffic; do not add both hosts and call it unique transferred bytes.
- No energy estimate is produced from sparse samples. GPU power is not wall-system power. No claim about a network bottleneck follows from bandwidth alone.
- Small samples have wide uncertainty; repeated tasks are correlated and confidence intervals are descriptive, not proof of general coding reliability.
- This controlled harness is not OpenCode: it tests model review/coding and artifact exchange, not unrestricted editor tools, web search, or whole-repository coding.
- Server availability or setup failures remain in the evidence. Unmeasured configurations have no invented numbers.

## Per-configuration evidence

### MOCK SERVER — NOT GPU MEASUREMENTS
Success 95% Wilson interval: 34.2%–100.0%; infrastructure errors: 0.
Telemetry: `{}`
Setup completed.
