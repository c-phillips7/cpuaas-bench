import csv
import matplotlib.pyplot as plt

SERIES = [
    ("results/docker/docker_m3_shm.csv", "SHM cross-container"),
    ("results/docker/docker_m3_shm_netem50ms.csv", "SHM + netem 50ms (no effect)"),
    ("results/docker/docker_m3_tcp.csv", "TCP container bridge"),
    ("results/docker/docker_m3_tcp_netem1ms.csv", "TCP + netem 1ms"),
    ("results/docker/docker_m3_tcp_netem10ms.csv", "TCP + netem 10ms"),
    ("results/docker/docker_m3_tcp_netem50ms.csv", "TCP + netem 50ms"),
]

for path, label in SERIES:
    with open(path) as f:
        vals = sorted(int(r["rtt_ns"]) / 1000 for r in csv.DictReader(f))  # ns -> µs
    ys = [(i + 1) / len(vals) for i in range(len(vals))]
    plt.step(vals, ys, where="post", label=label)

plt.xscale("log")
plt.xlabel("Round-trip latency (µs, log scale)")
plt.ylabel("Fraction of round trips ≤ x")
plt.title("Model 3 latency ladder: coupling mechanism vs network path (Docker)")
plt.legend(fontsize=8)
plt.grid(True, alpha=0.3, which="both")
plt.savefig("results/figures/docker_m3_ladder.png", dpi=150)
print("wrote results/figures/docker_m3_ladder.png")
