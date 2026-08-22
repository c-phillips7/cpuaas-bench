#!/usr/bin/env python3
# =============================================================================
# bench.py - single entry point for reproducing all benchmark results.
# v1 rule: single-process work is RUN directly; multi-container (M3) work is
# PRINTED as an exact two-terminal command pair, never orchestrated.
#
# USAGE
#   python3 bench.py m1 [--reps 30] [--tag NAME]
#     Docker Model 1 cold starts -> results/docker_m1[_NAME].csv + .meta.json
#
#   python3 bench.py m2 [--sessions 5] [--execs 30] [--tag NAME]
#     Docker Model 2 sessions -> results/docker_m2[_NAME].csv + .meta.json
#
#   python3 bench.py figures
#     Regenerate every PNG from the CSVs currently in results/.
#     Overwrites freely: figures are derived artefacts, cheap by design.
#
#   python3 bench.py m3 {shm|tcp} [--netem 10ms] [--tag NAME]
#     Prints the command pair for an M3 experiment, output name derived
#     from the parameters (e.g. docker_m3_tcp_netem10ms[_NAME].csv),
#     with start order labelled. Paste into two terminals.
#
# OVERWRITE POLICY (three tiers, deliberate):
#   - M3 raw runs: the ping-pong scripts' own guard REFUSES existing files.
#     To repeat a condition and keep the old data, add --tag (new filename);
#     to replace it, move/delete the old file first. Ten-minute runs cannot
#     be destroyed by a forgotten flag.
#   - m1/m2 untagged: OVERWRITE the canonical file - regeneration is the
#     normal workflow for these. Use --tag to keep a comparison run.
#   - figures: always overwritten; regenerable from CSVs at any time.
# =============================================================================
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

RESULTS = Path("results")

RUNTIMES = ["docker", "wasmtime"]

def get_driver(name):
    from drivers.docker_driver import DockerDriver
    from drivers.wasmtime_driver import WasmtimeDriver
    return {"docker": DockerDriver, "wasmtime": WasmtimeDriver}[name]()

def sidecar(out, extra):
    meta = {"argv": sys.argv, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    meta.update(extra)
    with open(f"{out}.meta.json", "w") as f:
        json.dump(meta, f, indent=1)


def cmd_m1(args):
    from runner import bench_model1, write_csv
    suffix = f"_{args.tag}" if args.tag else ""
    out = RESULTS / f"{args.runtime}_m1{suffix}.csv"
    write_csv(bench_model1(get_driver(args.runtime), reps=args.reps), out)
    sidecar(out, {"reps": args.reps})


def cmd_m2(args):
    from runner import bench_model2, write_csv
    suffix = f"_{args.tag}" if args.tag else ""
    out = RESULTS / f"{args.runtime}_m2{suffix}.csv"
    write_csv(bench_model2(get_driver(args.runtime), sessions=args.sessions, execs=args.execs), out)
    sidecar(out, {"sessions": args.sessions, "execs": args.execs})


def cmd_figures(args):
    for script, argv in [
        ("analysis/plot_cdf.py", ["results/docker_m1.csv"]),
        ("analysis/plot_exec_compare.py", []),
        ("analysis/crossover.py", []),
        ("analysis/plot_ladder.py", []),
        ("analysis/plot_cold_compare.py", []),
    ]:
        subprocess.run([sys.executable, script, *argv], check=True)


def cmd_m3(args):
    mech = args.mechanism
    cond = f"_netem{args.netem}" if args.netem else ""
    suffix = f"_{args.tag}" if args.tag else ""
    out = f"/results/docker_m3_{mech}{cond}{suffix}.csv"
    tc = f'tc qdisc add dev eth0 root netem delay {args.netem} && ' if args.netem else ""
    cap = "--cap-add NET_ADMIN " if args.netem else ""
    condition = f"netem{args.netem}" if args.netem else "baseline"                    # NEW
    bench_args = f"--warmup {args.warmup} --iters {args.iters} --condition {condition}"  # NEW
    if mech == "shm":
        ping = (f'docker run --rm --name m3-ping --ipc=shareable --cpuset-cpus=4 {cap}'
                f'-v "$PWD/results:/results" bench-py sh -c "{tc}python -u model3_shm.py '
                f'ping --core 4 --out {out} {bench_args}"')                           # CHANGED
        pong = ('docker run --rm --name m3-pong --ipc=container:m3-ping --cpuset-cpus=6 '
                'bench-py python -u model3_shm.py pong --core 6')
        order = [("terminal 1 (FIRST - creates segment)", ping), ("terminal 2", pong)]
    else:
        pong = ('docker run --rm --name m3-pong --network benchnet --cpuset-cpus=6 '
                'bench-py python -u model3_tcp.py pong --host 0.0.0.0 --core 6')
        ping = (f'docker run --rm --name m3-ping --network benchnet --cpuset-cpus=4 {cap}'
                f'-v "$PWD/results:/results" bench-py sh -c "{tc}python -u model3_tcp.py '
                f'ping --host m3-pong --core 4 --out {out} {bench_args}"')            # CHANGED
        order = [("terminal 1 (FIRST - server listens)", pong), ("terminal 2", ping)]
    print(f"# M3 {mech}{' + netem ' + args.netem if args.netem else ''} -> {out}")
    for label, c in order:
        print(f"\n# {label}:\n{c}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="cpuaas-bench entry point")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("m1", help="Model 1 cold starts")
    s.add_argument("--reps", type=int, default=30)
    s.add_argument("--tag", help="suffix to keep this run alongside existing data")
    s.add_argument("--runtime", choices=RUNTIMES, default="docker")
    s.set_defaults(fn=cmd_m1)

    s = sub.add_parser("m2", help="Docker Model 2 sessions")
    s.add_argument("--sessions", type=int, default=5)
    s.add_argument("--execs", type=int, default=30)
    s.add_argument("--tag", help="suffix to keep this run alongside existing data")
    s.add_argument("--runtime", choices=RUNTIMES, default="docker")
    s.set_defaults(fn=cmd_m2)

    s = sub.add_parser("figures", help="regenerate all figures from CSVs")
    s.set_defaults(fn=cmd_figures)

    s = sub.add_parser("m3", help="print the command pair for an M3 experiment")
    s.add_argument("mechanism", choices=["shm", "tcp"])
    s.add_argument("--netem", help="e.g. 10ms")
    s.add_argument("--tag", help="suffix to keep this run alongside existing data")
    s.add_argument("--warmup", type=int, default=5_000)
    s.add_argument("--iters", type=int, default=50_000)
    s.set_defaults(fn=cmd_m3)

    args = p.parse_args()
    args.fn(args)