import csv
import sys
import matplotlib.pyplot as plt

# Overlay the Model 1 cold-start CDFs of every CSV given on the command line
    # default se to two cannonical runtime files
paths = sys.argv[1:] or ["results/docker_m1.csv", "results/wasmtime_m1.csv",
                         "results/docker_m1_model1_rs.csv"]

for path in paths:
    with open(path) as f:
        rows = list(csv.DictReader(f))
    vals = sorted(float(r["cold_start_ms"]) for r in rows)
    runtime = rows[0]["runtime"]
    workload = rows[0].get("workload", "model1")
    n = len(vals)
    ys = [(i + 1) / n for i in range(n)]
    p50 = vals[n // 2]
    plt.step(vals, ys, where="post",
        label=f"{runtime}/{workload} (n={n}, p50={p50:.1f} ms)")
    
plt.xscale("log")
plt.xlabel("Cold start latency (ms, log scale)")
plt.ylabel("Fraction of runs ≤ x")
plt.title("Model 1 cold starts by runtime")
plt.grid(True, alpha=0.3, which="both")
plt.legend()
plt.savefig("results/m1_cold_compare.png", dpi=150)
print("wrote results/m1_cold_compare.png")