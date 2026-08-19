import csv
import sys
import matplotlib.pyplot as plt


# Read the CSV file and plot the CDF of cold start latencies
path = sys.argv[1]
with open(path) as f:
    vals = sorted(float(r["cold_start_ms"]) for r in csv.DictReader(f))
n = len(vals)
ys = [(i + 1) / n for i in range(n)]
plt.step(vals, ys, where="post")
plt.xlabel("Cold start latency (ms)")
plt.ylabel("Fraction of runs ≤ x")
plt.title(f"Docker Model 1 cold starts (n={n})")
plt.grid(True, alpha=0.3)
plt.savefig(path.replace(".csv", "_cdf.png"), dpi=150)