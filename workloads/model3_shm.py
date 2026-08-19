# bare host processes first, containers second
import argparse
import mmap
import os
import struct
import time
import sys
import json

# =============================================================================
# Model 3 emulation - POSIX shared-memory ping-pong (mechanism: /dev/shm + mmap)
#
# Two cooperating processes share a 4KB segment; ping writes a sequence number
# and busy-spins until pong echoes it. RTT distribution written as CSV.
# START ORDER: ping FIRST (it creates the segment), pong second.
# Output naming: <runtime>_m3_shm[_<condition>].csv
# Rebuild the image after any workload change: make build
#
# 1) Host baseline (no isolation - the control), two terminals from repo root:
#   python3 workloads/model3_shm.py ping --core 4 --out results/host_m3_shm.csv
#   python3 workloads/model3_shm.py pong --core 6
#
# 2) Cross-container (the Model 3 experiment). Donor owns a shareable IPC
#    namespace; peer joins it, so both see the same /dev/shm:
#   docker run --rm --name m3-ping --ipc=shareable --cpuset-cpus=4 -v "$PWD/results:/results" bench-py python -u model3_shm.py ping --core 4 --out /results/docker_m3_shm.csv
#   docker run --rm --name m3-pong --ipc=container:m3-ping --cpuset-cpus=6 bench-py python -u model3_shm.py pong --core 6
#
# 3) Negative control: run (2) with the peer's --ipc flag removed. Expected:
#    FileNotFoundError on /dev/shm/bench_m3 - the isolation boundary exists
#    until deliberately relaxed. Record the traceback.
#
# 4) Netem non-effect (tight-coupling demonstration) - largest delay on the
#    ping side; expected IDENTICAL results to (2), netem shapes network
#    interfaces and the SHM path never touches one:
#   docker run --rm --name m3-ping --ipc=shareable --cpuset-cpus=4 --cap-add NET_ADMIN -v "$PWD/results:/results" bench-py sh -c "tc qdisc add dev eth0 root netem delay 50ms && python -u model3_shm.py ping --core 4 --out /results/docker_m3_shm_netem50ms.csv"
#   docker run --rm --name m3-pong --ipc=container:m3-ping --cpuset-cpus=6 bench-py python -u model3_shm.py pong --core 6
#
# Expected magnitudes: p50 ~0.3us host and container (~500,000x below a Docker
# cold start); ms-scale max outliers = scheduler preemption, keep them in.
# Refuses to overwrite an existing --out file (guard in __main__).
# =============================================================================

SEG = "/dev/shm/bench_m3"
SIZE = 4096
PING_OFF = 0    # ping counter: cache line 0
PONG_OFF = 64   # pong counter: cache line 1 (avoid false sharing)
WARMUP = 5_000  # number of warmup iterations, then measured iterations
ITERS = 50_000

# Open a shared memory segment for ping/pong communication.
def open_seg(create):
    if create:
        with open(SEG, "wb") as f:
            f.write(b"\x00" * SIZE)   # pre-fault pages
    f = open(SEG, "r+b")
    return mmap.mmap(f.fileno(), SIZE)

# Pong process: wait for ping counter to change, then write it back to pong counter.
def pong(m):
    last = 0
    while True:
        # Wait for a ping message
        v = struct.unpack_from("<q", m, PING_OFF)[0]
        if v == -1:
            return
        if v != last:
            last = v
            struct.pack_into("<q", m, PONG_OFF, v)

# Ping process: write to ping counter, wait for pong counter to match, measure RTT.
def ping(m, out):
    # warm-up phase: untimed
    for i in range(1, WARMUP + 1):
        struct.pack_into("<q", m, PING_OFF, i)
        while struct.unpack_from("<q", m, PONG_OFF)[0] != i:
            pass

    # measured phase
    lat = []
    t_batch0 = time.perf_counter_ns()
    # measured iterations: write to ping counter, wait for pong counter to match, record RTT
    for i in range(WARMUP + 1, WARMUP + ITERS + 1):
        t0 = time.perf_counter_ns()
        struct.pack_into("<q", m, PING_OFF, i)
        while struct.unpack_from("<q", m, PONG_OFF)[0] != i:
            pass
        lat.append(time.perf_counter_ns() - t0)
    t_batch1 = time.perf_counter_ns()
    struct.pack_into("<q", m, PING_OFF, -1)
    
    # Write the latencies to a CSV file for later analysis.
    lat.sort()
    n = len(lat)
    # batched mean used as metric for comparison to other models, since it is less sensitive to outliers than the mean of individual RTTs
    print(f"batched mean RTT = {(t_batch1 - t_batch0) / n:.0f} ns")
    print(f"per-op p50={lat[n//2]} ns  p99={lat[int(n*0.99)]} ns  max={lat[-1]} ns")
    with open(out, "w") as f:
        f.write("rtt_ns\n")
        f.writelines(f"{v}\n" for v in lat)
    # add meta data of number of warmups and iterations used for each run
    meta = {
        "warmup": WARMUP, "iters": ITERS,
        "argv": sys.argv,
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(out + ".meta.json", "w") as f:
        json.dump(meta, f, indent=1)
    


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("role", choices=["ping", "pong"])
    p.add_argument("--core", type=int, required=True)
    p.add_argument("--out", default="results/m3_host.csv")
    a = p.parse_args()
    if a.role == "ping" and os.path.exists(a.out):
        sys.exit(f"refusing to overwrite {a.out} - move it or pick a new --out name")
    os.sched_setaffinity(0, {a.core})
    m = open_seg(create=(a.role == "ping"))
    ping(m, a.out) if a.role == "ping" else pong(m)