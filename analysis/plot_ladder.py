import csv
import matplotlib.pyplot as plt

# The master ladder: every Model 3 experiment on one log axis, same ping-pong
# protocol throughout. Each series names its CSV column because the wasm run
# records per-chunk MEANS (chunk_mean_rtt_ns, 50 values) while every other run
# records per-round-trip samples (rtt_ns). Firecracker has no rung: cross-VM
# shared memory is precluded by design and the vsock relay was not built;
# the figure caption says so.
SERIES = [
    # path, label, column
    ("results/host/host_m3_pythreads_default.csv", "Python threads, same buffer (control)", "rtt_ns"),
    ("results/docker/docker_m3_tcp_netem50ms.csv", "TCP + netem 50ms", "rtt_ns"),
    ("results/docker/docker_m3_tcp_netem10ms.csv", "TCP + netem 10ms", "rtt_ns"),
    ("results/docker/docker_m3_tcp_netem1ms.csv", "TCP + netem 1ms", "rtt_ns"),
    ("results/docker/docker_m3_tcp.csv", "TCP container bridge", "rtt_ns"),
    ("results/docker/docker_m3_shm_netem50ms.csv", "SHM cross-container + netem 50ms (no effect)", "rtt_ns"),
    ("results/docker/docker_m3_shm.csv", "SHM cross-container", "rtt_ns"),
    ("results/wasmtime/wasmtime_m3_shm.csv", "Wasm in-process shared memory (chunk means)", "chunk_mean_rtt_ns"),
]

for path, label, col in SERIES:
    with open(path) as f:
        vals = sorted(float(r[col]) / 1000 for r in csv.DictReader(f))  # ns -> µs
    ys = [(i + 1) / len(vals) for i in range(len(vals))]
    plt.step(vals, ys, where="post", label=f"{label} (n={len(vals)})")

plt.xscale("log")
plt.xlabel("Round-trip latency (µs, log scale)")
plt.ylabel("Fraction of round trips ≤ x")
plt.title("Model 3 latency ladder: coupling mechanism vs network path")
plt.grid(True, alpha=0.3, which="both")
plt.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2, fontsize=7, frameon=False)
plt.tight_layout()
plt.savefig("results/figures/docker_m3_ladder.png", dpi=150)
print("wrote results/figures/docker_m3_ladder.png")
