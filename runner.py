import csv
import time
from pathlib import Path


# Import models
from drivers.docker_driver import DockerDriver


# Number of repetitions for each benchmark
REPS = 30
RESULTS = Path("results")

# Bench Model 1: Ephemeral workload
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

# Bench Model 2: Session-based workload
def bench_model2(driver, sessions=5, execs=30) :
    driver.prepare("model2")
    rows = []
    for s in range(sessions):
        t0 = time.perf_counter_ns()
        inst = driver.provision("model2")
        t1 = time.perf_counter_ns()
        cold_ms = (t1 - t0) / 1e6
        # Warm invocations
        for i in range(execs):
            t2 = time.perf_counter_ns()
            driver.execute(inst, b"1000")
            t3 = time.perf_counter_ns()
            rows.append({
                "session": s,
                "invocation": i,
                "runtime": driver.name,
                "model": 2,
                "cold_start_ms": cold_ms, # Maybe if i == 0 else None 
                "warm_exec_ms": (t3 - t2) / 1e6,
            })
        metrics = driver.collect(inst)
        driver.teardown(inst)
        # Add the memory metrics to the last execs rows for this session
            # memory_peak_bytes is that session's peak over all its invocations
        for r in rows[-execs:]:
            r["memory_peak_bytes"] = metrics["memory_peak_bytes"]
        print(f"session {s}: cold={cold_ms:.1f}ms, {execs} warm execs done")
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
    rows2 = bench_model2(DockerDriver())
    write_csv(rows2, RESULTS / "docker_model2.csv")