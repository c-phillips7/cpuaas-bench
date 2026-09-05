import csv
import glob
import re
import matplotlib.pyplot as plt

# The who-executes figure: python-threads control RTT vs GIL switch interval,
# with the wasm guests' RTT on the same buffer as the reference line.

# discover all control conditions from the filenames; the 'default' file is
# the untouched interpreter (~5000us switch interval)
data = []
for path in glob.glob("results/host/host_m3_pythreads_*.csv"):
    m = re.search(r"_si(\d+)us", path)
    si = int(m.group(1)) if m else 5000
    with open(path) as f:
        v = sorted(int(r["rtt_ns"]) for r in csv.DictReader(f))
    data.append((si, v))
data.sort()

xs = [si for si, _ in data]
p50s = [v[len(v) // 2] / 1e3 for _, v in data]
p99s = [v[int(len(v) * 0.99)] / 1e3 for _, v in data]

with open("results/wasmtime/wasmtime_m3_shm.csv") as f:
    w = sorted(float(r["chunk_mean_rtt_ns"]) for r in csv.DictReader(f))
wasm_us = w[len(w) // 2] / 1e3

plt.plot(xs, p50s, "o-", label="python threads p50")
plt.plot(xs, p99s, "s--", alpha=0.6, label="python threads p99")
plt.plot(xs, [2 * x for x in xs], ":", alpha=0.6, label="2 x switch interval (predicted)")
plt.axhline(wasm_us, color="tab:green", lw=1.5,
            label=f"wasm guests, same buffer ({wasm_us*1e3:.0f} ns)")
plt.xscale("log"); plt.yscale("log")
plt.xlabel("GIL switch interval (µs, log; 5000 = untouched default)")
plt.ylabel("ping-pong RTT (µs, log)")
plt.title("Same shared memory, different executor")
plt.grid(True, alpha=0.3, which="both")
plt.legend(fontsize=8)
plt.savefig("results/figures/m3_executor_sweep.png", dpi=150)
print("wrote results/figures/m3_executor_sweep.png")
