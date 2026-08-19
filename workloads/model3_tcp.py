# This workload measures the round-trip time of a TCP connection between two processes on the same host.
# It is used to measure the overhead of the TCP stack and the kernel's scheduling latency.

# Goal is to rule out common ping pong bug of measuring the Nagle delay timer, not the transport

import argparse
import os
import socket
import time
import sys
import json


# =============================================================================
# Model 3 counterfactual - TCP ping-pong (the network path tight coupling
# escapes). Same protocol and stats as model3_shm.py; 8-byte messages;
# TCP_NODELAY both ends (else Nagle batching measures the wrong thing).
# START ORDER: pong FIRST (server must listen before client connects).
# Output naming: <runtime>_m3_tcp[_netem<delay>].csv
# Rebuild the image after any workload change: make build
#
# 1) Host loopback baseline, two terminals from repo root:
#   python3 workloads/model3_tcp.py pong --core 6
#   python3 workloads/model3_tcp.py ping --core 4 --out results/host_m3_tcp.csv
#
# 2) Container-to-container over a user-defined bridge (Docker DNS resolves the
#    server by name). Once: docker network create benchnet
#   docker run --rm --name m3-pong --network benchnet --cpuset-cpus=6 bench-py python -u model3_tcp.py pong --host 0.0.0.0 --core 6
#   docker run --rm --name m3-ping --network benchnet --cpuset-cpus=4 -v "$PWD/results:/results" bench-py python -u model3_tcp.py ping --host m3-pong --core 4 --out /results/docker_m3_tcp.csv
#
# 3) WAN emulation sweep: ping container applies egress delay to its own eth0
#    (RTT ~= baseline + delay). One run per delay; change BOTH delay and --out:
#   docker run --rm --name m3-ping --network benchnet --cpuset-cpus=4 --cap-add NET_ADMIN -v "$PWD/results:/results" bench-py sh -c "tc qdisc add dev eth0 root netem delay 10ms && python -u model3_tcp.py ping --host m3-pong --core 4 --out /results/docker_m3_tcp_netem10ms.csv"
#    50ms run: cut WARMUP to 200 / ITERS to 2000 first (else ~45min), make
#    build, run, restore constants, make build again; note the reduced n.
#
# Fidelity record (configured -> achieved p50): baseline ~33-46us;
# 1ms -> 1.166ms (reproduced twice, <1% apart); 10ms -> 10.34ms
# (netem overhead ~0.1-0.3ms, document it).
# Expected: ~2 orders of magnitude above the SHM path before any netem delay.
# Refuses to overwrite an existing --out file (guard in __main__).
# =============================================================================
PORT = 5555
WARMUP = 5_000
ITERS = 50_000
MSG = 8  # bytes, matches the SHM counter size


def pong(host):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, PORT))
    srv.listen(1)
    conn, _ = srv.accept()
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1) # Disable Nagle's algorithm for low-latency communication
    while True:
        data = conn.recv(MSG)
        if not data or data == b"\xff" * MSG:
            return
        conn.sendall(data)


def ping(host, out):
    s = socket.create_connection((host, PORT))
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    # Warmup
    for i in range(WARMUP):
        s.sendall(i.to_bytes(MSG, "little"))
        s.recv(MSG)
    lat = []
    t_batch0 = time.perf_counter_ns()
    for i in range(ITERS):
        if i % 10_000 == 0:
            print(f"[{i}/{ITERS}]", file=sys.stderr, flush=True)
        t0 = time.perf_counter_ns()
        s.sendall(i.to_bytes(MSG, "little"))
        s.recv(MSG)
        lat.append(time.perf_counter_ns() - t0)
    t_batch1 = time.perf_counter_ns()
    s.sendall(b"\xff" * MSG)
    lat.sort()
    n = len(lat)
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
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--core", type=int, required=True)
    p.add_argument("--out", default="results/m3_tcp.csv")
    a = p.parse_args()
    # Added check for same file name when trying different delays
    if a.role == "ping" and os.path.exists(a.out):
        sys.exit(f"refusing to overwrite {a.out} - move it or pick a new --out name")
    os.sched_setaffinity(0, {a.core})
    ping(a.host, a.out) if a.role == "ping" else pong(a.host)