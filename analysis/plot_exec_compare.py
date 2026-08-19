import csv
import matplotlib.pyplot as plt

# Read the CSV file and plot the CDF of cold start latencies
def cdf(path, col):
    with open(path) as f:
        vals = sorted(float(r[col]) for r in csv.DictReader(f))
    return vals, [(i + 1) / len(vals) for i in range(len(vals))]


# Plotting logic
x1, y1 = cdf("results/docker_model1.csv", "exec_ms")
x2, y2 = cdf("results/docker_model2.csv", "warm_exec_ms")
plt.step(x1, y1, where="post", label="Model 1 exec (always first invocation)")
plt.step(x2, y2, where="post", label="Model 2 warm exec")
plt.xlabel("Execution latency (ms)")
plt.ylabel("Fraction of runs ≤ x")
plt.title("Execution latency: first-invocation vs warm (Docker)")
plt.legend()
plt.grid(True, alpha=0.3)
plt.savefig("results/docker_exec_compare.png", dpi=150)