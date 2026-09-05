# cpuaas-bench

A reproducible benchmark suite comparing three sandboxing runtimes, Docker, Firecracker and Wasmtime, under the three CPUaaS execution models: ephemeral invocation (Model 1), long-lived sessions (Model 2), and tightly coupled shared-memory exchange (Model 3). One harness, one driver contract, one ping-pong protocol; every number in the accompanying report regenerates from this repository.

MSc Software Engineering project, University of Westminster, 7SENG013W (2026). Author: Christopher Phillips.

## What is measured

| Model | Question | Metric | Runtimes |
|---|---|---|---|
| 1 | Cost of a sandbox created per request | cold start (ms), first-invocation exec (ms), peak memory | Docker, Firecracker, Wasmtime |
| 2 | Cost of keeping a sandbox warm across requests | warm exec (ms), session peak memory, crossover vs Model 1 | Docker, Firecracker, Wasmtime |
| 3 | Cost of coupling two sandboxes through memory vs the network | round-trip latency (ns to ms), CDFs | Docker (POSIX SHM, TCP, TCP + netem), Wasmtime (in-process shared memory), host baselines and a Python-threads control |

Firecracker has no Model 3 rung: cross-VM shared memory is precluded by its isolation design (see the report). Its Model 1 and 2 columns run the workload as PID 1 of a minimal microVM.

## Layout

```
bench.py            single entry point (m1 / m2 / m3 / figures)
demo.py             guided menu that builds and shows the same commands (viva aid)
runner.py           the measurement loop: one stopwatch, uniform CSV rows
drivers/            RuntimeDriver contract (base.py) + docker, wasmtime, firecracker drivers
workloads/          model1.py, model2.py (stdio protocol); model3_shm.py, model3_tcp.py, model3_wasm.py (ping-pong pairs)
workloads_rust/     the same model1/model2 workloads in Rust (wasm32-wasip1 for Wasmtime; x86_64 musl for Docker _rs and Firecracker)
fc/                 Firecracker assets: build_rootfs.sh, gate.json, per-workload VM configs; binaries are fetched, not committed
analysis/           one script per figure
results/<runtime>/  CSVs + .meta.json sidecars (docker/, wasmtime/, firecracker/, host/)
results/figures/    every PNG
Makefile            build and setup targets
```

The `host/` results are un-sandboxed baselines: plain host processes over POSIX SHM and TCP loopback, and the Python-threads control that shares a buffer with the Wasm guests.

## Prerequisites

Measured on: WSL2, Ubuntu 24.04, Linux 6.6.87-microsoft-WSL2, Python 3.12.3, Docker Engine 29.7.1 (native, inside WSL), wasmtime CLI 47.0.3 and wasmtime-py 47.0.1, cargo 1.97.1, Firecracker v1.16.1 with the v1.15 CI guest kernel 6.1.155. The repository must live on the Linux filesystem (`~`), not under `/mnt/c`.

- Docker Engine, with the current user in the `docker` group.
- Python 3.12 with a venv for analysis only: `python3 -m venv .venv && . .venv/bin/activate && pip install matplotlib wasmtime==47.0.1`. The measurement path is standard-library only by design; only `analysis/` and `model3_wasm.py` need the venv.
- Rust toolchain via rustup with two targets: `rustup target add wasm32-wasip1 x86_64-unknown-linux-musl`, plus `musl-tools` (`sudo apt install musl-tools`).
- Wasmtime CLI 47.0.3: `curl https://wasmtime.dev/install.sh -sSf | bash`.
- For Firecracker: `/dev/kvm` present and writable (WSL2 needs `nestedVirtualization=true` in `.wslconfig`; add the user to the `kvm` group), `e2fsprogs`, and `sudo` for the one loop mount in the rootfs build.
- `iproute2` for `tc netem` (inside the container image; installed by the Dockerfile).

## Build

```
make build              # docker image bench-py (python workloads + the two musl binaries)
make network            # docker network benchnet, used by the TCP experiments
make build-wasm         # workloads_rust -> wasm32-wasip1 modules
make build-rust         # workloads_rust -> static musl binaries (Docker _rs and Firecracker guests)
make fc-fetch           # pinned Firecracker v1.16.1 + guest kernel vmlinux-6.1.155 into fc/
make build-fc-rootfs    # 32 MiB ext4 with the two binaries and /dev/console (needs sudo)
make fc-gate            # boot the Firecracker guest interactively: READY, type 1000, expect 332833500, Ctrl-D to exit
```

Or `python demo.py` and choose option 0.

## Run

Everything goes through `bench.py`; `demo.py` is a menu that assembles and shows the same command lines.

```
python bench.py m1 --runtime docker                                  # results/docker/docker_m1.csv
python bench.py m1 --runtime docker --workload model1_rs             # native-binary control
python bench.py m1 --runtime wasmtime
python bench.py m1 --runtime firecracker --workload model1_rs        # Firecracker guests are native binaries only
python bench.py m2 --runtime <docker|wasmtime|firecracker> [--workload model2_rs]
python bench.py m3 shm [--netem 50ms]     # PRINTS the two-terminal docker command pair; paste it, first-listed first
python bench.py m3 tcp [--netem 10ms]
python workloads/model3_wasm.py [--chunk 1000]            # Wasm in-process shared memory
python workloads/model3_wasm.py control [--switch-us 100] # Python-threads control on the same buffer
python bench.py figures                                   # regenerate every PNG in results/figures/
```

Multi-container Model 3 work is printed rather than orchestrated, deliberately: the exact command pair is the reproducibility artefact.

### Overwrite policy (three tiers)

- Model 3 raw runs are guarded: an existing output file is refused, never overwritten. Repeat a condition with `--tag NAME` (new filename) or move the old file first.
- Untagged Model 1/2 runs overwrite the canonical file; regeneration is the normal workflow. Use `--tag` to keep a comparison run.
- Figures are always overwritten; they are derived from CSVs and cheap.

### Provenance

Every CSV has a `.meta.json` sidecar recording the exact `argv`, UTC time, and run parameters (reps, sessions, warmup, iters, condition). Filenames derive from parameters: `<runtime>_<model>[_<workload>][_<mechanism>][_<condition>][_<tag>].csv`. The folder is always the filename's first token. Firecracker VM definitions used for each run are in `fc/<workload>.json`.

## Known-answer checks

Every workload, in every language and runtime, answers `1000` with `332833500` (sum of squares below 1000). Model 2 accumulates: `1000` then `2000` gives `2997500500`. Each driver has a smoke test: `python -m drivers.docker_driver`, `python -m drivers.wasmtime_driver`, `python -m drivers.firecracker_driver`.

## Figures

| File | What |
|---|---|
| m1_cold_compare.png | Model 1 cold-start CDFs, all runtimes, log axis |
| docker_m1_cdf.png | Docker cold-start CDF |
| docker_exec_compare.png | Model 1 first-invocation exec vs Model 2 warm exec |
| docker_crossover.png | cumulative cost of N requests, Model 1 vs Model 2 |
| docker_m3_ladder.png | the Model 3 latency ladder: Wasm SHM, Docker SHM (with and without netem), TCP, TCP + netem, Python-threads control |
| m3_executor_sweep.png | Python-threads RTT vs GIL switch interval, Wasm reference line |
| m3_chunk_fit.png | FFI toll calibration: chunk mean RTT vs 1/chunk |

## Reproducing the report's numbers

`make build network build-wasm build-rust fc-fetch build-fc-rootfs`, then the `bench.py` commands above for each runtime and model, then `python bench.py figures`. Sidecars in `results/` are the ground truth for every figure quoted in the report.

## Notes

- `sync.sh` mirrors the repository to a Windows folder for backup; never run benchmarks from the mirror.
- AI assistance used in this project is declared in the accompanying report.
