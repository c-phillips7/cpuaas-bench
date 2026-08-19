import csv
import time
from pathlib import Path


# Import models
from drivers.docker_driver import DockerDriver


# Number of repetitions for each benchmark
REPS = 30
RESULTS = Path("results")


def bench_model1(driver, reps=REPS):
    # Prepare the driver for the workload, not timed, done once per driver/workload
    driver.prepare("model1")
    rows = []
    for i in range(reps):
        t0 = time.perf_counter_ns()
        inst = driver.provision("model1")
        t1 = time.perf_counter_ns()
        result = driver.execute(inst, b"1000")
        t2 = time.perf_counter_ns()
        metrics = driver.collect(inst)
        driver.teardown(inst)
        # Record the results for this repetition with detials
        rows.append({
            "rep": i,
            "runtime": driver.name,
            "model": 1,
            "cold_start_ms": (t1 - t0) / 1e6,
            "exec_ms": (t2 - t1) / 1e6,
            "memory_peak_bytes": metrics["memory_peak_bytes"],
        })
        print(f"rep {i:2d}  cold={rows[-1]['cold_start_ms']:8.1f}ms  exec={rows[-1]['exec_ms']:6.2f}ms")
    return rows

# Write results to a CSV file
def write_csv(rows, path):
    RESULTS.mkdir(exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

# Main execution
if __name__ == "__main__":
    rows = bench_model1(DockerDriver())
    write_csv(rows, RESULTS / "docker_model1.csv")