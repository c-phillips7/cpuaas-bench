import csv
import statistics
import matplotlib.pyplot as plt

def median_col(path, col):
    with open(path) as f:
        return statistics.median(float(r[col]) for r in csv.DictReader(f))

cold = median_col("results/docker_model1.csv", "cold_start_ms")
exec1 = median_col("results/docker_model1.csv", "exec_ms")
warm = median_col("results/docker_model2.csv", "warm_exec_ms")

# Cost of serving N requests:
#   Model 1: N * (cold + exec)   -- every request pays a cold start
#   Model 2: cold + N * warm     -- one cold start, then warm invocations
# Crossover where equal: N = cold / (cold + exec - warm)
n_star = cold / (cold + exec1 - warm)

print(f"medians: cold={cold:.1f}ms  exec_M1={exec1:.3f}ms  warm_M2={warm:.3f}ms")
print(f"crossover N = {n_star:.4f}")

# Plot the cumulative cost of serving N requests for both models, using the median values
N = list(range(0, 11))
plt.plot(N, [n * (cold + exec1) for n in N], marker="o", label="Model 1: N(cold+exec)")
plt.plot(N, [cold + n * warm for n in N], marker="s", label="Model 2: cold + N*warm")
plt.axvline(n_star, ls="--", alpha=0.5)
plt.xlabel("Requests served (N)")
plt.ylabel("Cumulative cost (ms)")
plt.title("Model 1 vs Model 2 cumulative cost (Docker, medians)")
plt.legend()
plt.grid(True, alpha=0.3)
plt.savefig("results/docker_crossover.png", dpi=150)