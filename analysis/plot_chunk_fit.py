import argparse
import csv
import glob
import json
import re
import matplotlib.pyplot as plt

# FFI-toll calibration: chunk mean = true_rtt + toll/chunk, linear in 1/chunk.
# Only ingests runs whose SIDECAR records the requested --iters, so points on
# one fit always carry equal statistical weight (same total round trips).
p = argparse.ArgumentParser()
p.add_argument("--iters", type=int, default=50_000,
               help="only include runs whose sidecar iters matches (default 50000)")
args = p.parse_args()

points = []   # (chunk_size, mean_of_chunk_means_ns)
for path in glob.glob("results/wasmtime_m3_shm*.csv"):
    try:
        with open(f"{path}.meta.json") as f:
            meta = json.load(f)
    except FileNotFoundError:
        print(f"skipping {path}: no sidecar (cannot verify iters)")
        continue
    if meta.get("iters") != args.iters:
        continue
    m = re.search(r"_chunk(\d+)", path)
    chunk = int(m.group(1)) if m else 1000
    with open(path) as f:
        v = [float(r["chunk_mean_rtt_ns"]) for r in csv.DictReader(f)]
    points.append((chunk, sum(v) / len(v)))
points.sort()

if len(points) < 2:
    raise SystemExit(f"need >=2 matching runs for a fit, found {len(points)} "
                     f"with iters={args.iters}")

inv = [1 / c for c, _ in points]
ys = [y for _, y in points]
n = len(points)
mx, my = sum(inv) / n, sum(ys) / n
slope = sum((x - mx) * (y - my) for x, y in zip(inv, ys)) / sum((x - mx) ** 2 for x in inv)
intercept = my - slope * mx

plt.plot(inv, ys, "o", label="measured chunk means")
plt.plot([0] + inv, [intercept + slope * x for x in [0] + inv], "-", alpha=0.7,
         label=f"fit: RTT = {intercept:.0f} ns + {slope/1e3:.1f} µs / chunk")
plt.xlabel("1 / chunk size")
plt.ylabel("mean RTT per chunk (ns)")
plt.title(f"FFI toll calibration ({args.iters:,} round trips per point)")
plt.grid(True, alpha=0.3)
plt.legend(fontsize=9)
suffix = "" if args.iters == 50_000 else f"_iters{args.iters}"
plt.savefig(f"results/m3_chunk_fit{suffix}.png", dpi=150)
print(f"wrote results/m3_chunk_fit{suffix}.png  "
      f"(true RTT ~{intercept:.0f} ns, toll ~{slope/1e3:.1f} us/call, n={n} points)")