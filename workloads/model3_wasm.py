# =============================================================================
# Model 3 emulation - Wasm shared-linear-memory ping-pong (mechanism: wasmtime
# SharedMemory shared by two Instances inside ONE host process = the embedded
# integration model; third sibling of model3_shm.py and model3_tcp.py).
#
# MODES (default = wasm):
#   python3 workloads/model3_wasm.py [wasm] [--chunk N]
#       The experiment: two Wasm guests ping-pong through the SharedMemory.
#       Timing is CHUNKED - one guest call runs --chunk round trips, the host
#       times the call; the ~us-scale Python->Wasm call toll is amortised to
#       ~chunk-fold below signal. Varying --chunk (100/1000/5000) and checking
#       the means agree IS the overhead calibration. Per-op tails are out of
#       reach by design (a per-op host-timed call would put a ~20us instrument
#       on a ~0.2us signal); the output column is named chunk_mean_rtt_ns so
#       the statistic cannot be mistaken for per-op samples.
#   python3 workloads/model3_wasm.py control [--switch-us X]
#       NEGATIVE CONTROL: two PYTHON THREADS run the same protocol through the
#       same SharedMemory - no WebAssembly executes. Predicted: RTT is set by
#       the GIL (p50 ~ 2x switch interval; ~5ms default), tracks --switch-us
#       downward, then flattens at the OS handoff floor (~0.1ms) - still ~3
#       decades above the guest number. Demonstrates the measured coupling is
#       a property of guest execution, not of the buffer.
#
# Requires wasmtime-py -> run under the venv (deliberate exception to the
# stdlib-only measurement rule: that rule keeps scripts runnable inside
# containers; this one never runs in a container - wasmtime-py IS the
# runtime under test). Cores default to 4/6, matching the Docker experiment.
# =============================================================================

import argparse
import ctypes
import json
import os
import statistics
import struct
import sys
import threading
import time
from pathlib import Path

from wasmtime import (Config, Engine, Store, Module, Instance,
                      MemoryType, Limits, SharedMemory, Func)
from wasmtime import _ffi as ffi

# ---------------------------------------------------------------------------
# WORKAROUND. wasmtime-py 47.0.1's
# SharedMemory._as_extern() wraps the pointer one level too deep, so passing
# a SharedMemory as an Instance import fails with "incompatible types,
# LP_LP_wasmtime_sharedmemory instance instead of LP_wasmtime_sharedmemory
# instance". This monkeypatch swaps in a correctly-built extern at runtime.
# (Same defect family: SharedMemory.size() has a stray byref - use data_len() instead.)
# ---------------------------------------------------------------------------
def _as_extern_fixed(self):
    return ffi.wasmtime_extern_t(ffi.WASMTIME_EXTERN_SHAREDMEMORY,
                                 ffi.wasmtime_extern_union(sharedmemory=self.ptr()))
SharedMemory._as_extern = _as_extern_fixed

PING_OFF = 0    # ping countter: cache like 0
PONG_OFF = 64   # pong counter: cache line 1
# amount of spins allowed before aborting
    # unlike with docker, with communicating processes, a built in kill switch needs to be implemented
BUDGET = 2_000_000_000

def make_shared_memory():
    # shared_memory is a SEPARATE switch from wasm_threads
    cfg = Config()
    cfg.wasm_threads = True
    cfg.wasm_bulk_memory = True
    cfg.shared_memory = True
    engine = Engine(cfg)
    shm = SharedMemory(engine, MemoryType(Limits(1, 1), shared=True))
    return engine, shm

# Build a window so python can read and write Wasm memory directly
    # maps the Wasm shared memory into Python's buffer protocol
def host_view(shm, size=128):
    # a memoryview over the wasm memory's bytes, so the host side can use the
    # same struct.pack_into/unpack_from protocol as model3_shm.py
    buf = (ctypes.c_char * size).from_address(
        ctypes.addressof(shm.data_ptr().contents))
        # shm.data_ptr() gives pointer to first byte
        # ctypes.addressof() then gets that pointer's integer address
    return memoryview(buf) # memoryview(buf) makes this python compatible

# ----------------------------------------------------------------------------
# --- control mode: two Python threads, no WebAssembly executes --------------
# ----------------------------------------------------------------------------

def pyctl_pong(mv, n):
    # model3_shm.py pong(), count-bounded instead of sentinel-stopped
    last = 0
    while last < n:
        v = struct.unpack_from("<q", mv, PING_OFF)[0]
        if v != last:
            last = v
            struct.pack_into("<q", mv, PONG_OFF, v)



def pyctl_ping(mv, warmup, iters):
    # model3_shm.py ping(), same per-op timing. Per-op is honest HERE:
    # control RTTs are ms-scale, so the ~100ns clock cost is 4-5 decades below signal
    for i in range(1, warmup + 1):
        struct.pack_into("<q", mv, PING_OFF, i)
        while struct.unpack_from("<q", mv, PONG_OFF)[0] != i:
            pass
    lat = []
    for i in range(warmup + 1, warmup + iters + 1):
        t0 = time.perf_counter_ns()
        struct.pack_into("<q", mv, PING_OFF, i)
        while struct.unpack_from("<q", mv, PONG_OFF)[0] != i:
            pass
        lat.append(time.perf_counter_ns() - t0)
    return lat


# -----------------------------------------------------------------
#  --- wasm mode: direct WebAssembly execution in shared memory.
# To measure sandboxed code, the workload itself must be WebAssembly:
#   a Wasm instance can only execute Wasm, and Python cannot become Wasm.
#
# Unlike the Model 1/2 workloads (Rust compiled to .wasm), this guest is
# written directly in WAT - the spec's human-readable text form of
# WebAssembly - because the shared-memory features it needs are pre-standard
# and poorly supported by the Rust toolchain, and 25 readable lines beat an
# opaque binary. 
#
# The following is a hand reimplementation of model3_shm.py's protocol
#       !!! AI was used to generate this translation !!!
# Note: each function below names its Python twin.
# Compiled at Module() construction, untimed - M3 does not time provisioning.
# ----------------------------------------------------------------------------

WAT = r"""
(module
  (import "env" "mem" (memory 1 1 shared))

  ;; model3_shm.py's spin loop: wait until [addr] == want, give up at budget
  (func $spin (param $addr i32) (param $want i64) (param $budget i64) (result i32)
    (local $i i64)
    (loop $l
      (if (i64.eq (i64.atomic.load (local.get $addr)) (local.get $want))
        (then (return (i32.const 1))))
      (local.set $i (i64.add (local.get $i) (i64.const 1)))
      (br_if $l (i64.lt_u (local.get $i) (local.get $budget))))
    (i32.const 0))

  ;; model3_shm.py's ping loop, minus the clock: $count round trips per call
  (func (export "ping_chunk") (param $start i64) (param $count i64) (param $budget i64) (result i32)
    (local $seq i64) (local $end i64)
    (local.set $seq (local.get $start))
    (local.set $end (i64.add (local.get $start) (local.get $count)))
    (loop $l
      (local.set $seq (i64.add (local.get $seq) (i64.const 1)))
      (i64.atomic.store (i32.const 0) (local.get $seq))
      (if (i32.eqz (call $spin (i32.const 64) (local.get $seq) (local.get $budget)))
        (then (return (i32.const 0))))
      (br_if $l (i64.lt_u (local.get $seq) (local.get $end))))
    (i32.const 1))

  ;; model3_shm.py's pong(): echo $n sequence numbers, then return
  (func (export "pong_run") (param $n i64) (param $budget i64) (result i32)
    (local $seq i64)
    (loop $l
      (local.set $seq (i64.add (local.get $seq) (i64.const 1)))
      (if (i32.eqz (call $spin (i32.const 0) (local.get $seq) (local.get $budget)))
        (then (return (i32.const 0))))
      (i64.atomic.store (i32.const 64) (local.get $seq))
      (br_if $l (i64.lt_u (local.get $seq) (local.get $n))))
    (i32.const 1))
)
"""


# ----------------------------------------------------------------------------
# --- shared plumbing --------------------------------------------------------
# ----------------------------------------------------------------------------

def derive_out(args):
    # filenames derive from parameters - the manual-naming error class stays dead
    if args.mode == "control":
        cond = f"si{args.switch_us}us" if args.switch_us is not None else "default"
        return Path("results") / f"host_m3_pythreads_{cond}.csv"
    cond = f"_chunk{args.chunk}" if args.chunk != 1000 else ""
    return Path("results") / f"wasmtime_m3_shm{cond}.csv"


def write_output(out, colname, values, extra):
    with open(out, "w") as f:
        f.write(colname + "\n")
        f.writelines(f"{v}\n" for v in values)
    meta = {"argv": sys.argv,
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    meta.update(extra)
    with open(f"{out}.meta.json", "w") as f:
        json.dump(meta, f, indent=1)
     
# ----------------------------------------------------------------------------
# --- runners ----------------------------------------------------------------
# ----------------------------------------------------------------------------

def run_control(args, out):
    # the unmodified version IS the default: switch interval untouched unless asked
    if args.switch_us is not None:
        sys.setswitchinterval(args.switch_us / 1e6) # converts default s input to µs

    # build Wasm shared memory
        # engine is kept to stop potential garbage collection
    engine, shm = make_shared_memory()
    mv = host_view(shm)
    n_total = args.warmup + args.iters

    # set up thread for pong
    def pong_role():
        # set core for pong
        os.sched_setaffinity(0, {args.core_pong})   # pid 0 = THIS thread on Linux
        pyctl_pong(mv, n_total)

    t = threading.Thread(target=pong_role, daemon=True)
        # daemon=True: pong cannot outlive ping - if ping dies early, Python exits
        # and takes the spinning thread with it (no orphaned spinner)
    t.start()
    
    # set core for ping
    os.sched_setaffinity(0, {args.core_ping})
    # collect latencies data
    lat = pyctl_ping(mv, args.warmup, args.iters)
    # Wait for pong to finish its n_total echoes and exit
        # timeout to ensure if pong gets stuck, ping still reports
    t.join(timeout=10)

    lat.sort()
    n = len(lat)
    label = f"si={args.switch_us}us" if args.switch_us is not None else "default si"
    # Convert figures then calculate the median, the max, and the p99
    print(f"pythreads control ({label}): p50={lat[n//2]/1e6:.3f} ms  "
          f"p99={lat[int(n*0.99)]/1e6:.3f} ms  max={lat[-1]/1e6:.3f} ms")
    write_output(out, "rtt_ns", lat,
                 {"mode": "control", "switch_us": args.switch_us,
                  "warmup": args.warmup, "iters": args.iters,
                  "cores": [args.core_ping, args.core_pong]})


def run_wasm(args, out):
    # Setup instances and shared memory for the run
    engine, shm = make_shared_memory()
    module = Module(engine, WAT)
    s_ping, s_pong = Store(engine), Store(engine)
    ping_x = Instance(s_ping, module, [shm]).exports(s_ping)
    pong_x = Instance(s_pong, module, [shm]).exports(s_pong)
    
    
    # Assert values to remove Pylance warnings of "Object of type "Global" is not callable"
    ping_chunk = ping_x["ping_chunk"]
    pong_run = pong_x["pong_run"]
    assert isinstance(ping_chunk, Func) and isinstance(pong_run, Func)

    # Splitting and recombining to ensure only full chunks used
        # ie, for 50,000 requests at --chunk 7,000;
        # would become 7 chunks of 7,000, or 49,000 actual iters
    nchunks = args.iters // args.chunk
    iters = nchunks * args.chunk          # trim to a whole number of chunks
    n_total = args.warmup + iters
    result = {}

    def pong_role():
        # set core for pong
        os.sched_setaffinity(0, {args.core_pong})
        result["pong"] = pong_run(s_pong, n_total, BUDGET)
    
    t = threading.Thread(target=pong_role, daemon=True)
        # daemon=True: pong cannot outlive ping - if ping dies early, Python exits
        # and takes the spinning thread with it (no orphaned spinner)
    t.start()
    time.sleep(0.05)                      # let pong enter its guest call
    
    # set core for ping
    os.sched_setaffinity(0, {args.core_ping})

    # seq is how many round trips have been consumed so far
    seq = 0
    # untimed warmup runs
        # Note, BUDGET has to be passed every call as guest has no memory of config betwem calls
    if ping_chunk(s_ping, seq, args.warmup, BUDGET) != 1:
        sys.exit("warmup failed: spin budget exhausted (is pong running?)")
    seq += args.warmup

    # calculate the mean time for the chunk of requests
    means = []
    for _ in range(nchunks):
        t0 = time.perf_counter_ns()
        if ping_chunk(s_ping, seq, args.chunk, BUDGET) != 1:
            sys.exit(f"chunk at seq={seq} failed: spin budget exhausted")
        means.append((time.perf_counter_ns() - t0) / args.chunk)
        seq += args.chunk
    t.join(timeout=30)

    ms = sorted(means)
    print(f"wasm guests: {nchunks} chunks x {args.chunk} RTTs | "
          f"mean {statistics.mean(ms):.0f} ns  p50 {ms[len(ms)//2]:.0f} ns  "
          f"max {ms[-1]:.0f} ns | pong ok={result.get('pong')}")
    write_output(out, "chunk_mean_rtt_ns", [f"{m:.1f}" for m in ms],
                 {"mode": "wasm", "chunk": args.chunk, "nchunks": nchunks,
                  "warmup": args.warmup, "iters": iters,
                  "cores": [args.core_ping, args.core_pong]})

# Main method
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", nargs="?", choices=["wasm", "control"], default="wasm",
                   help="default: the wasm experiment")
    p.add_argument("--switch-us", type=int,
                   help="control only: sys.setswitchinterval in microseconds; absent = untouched")
    p.add_argument("--chunk", type=int, default=1000,
                   help="wasm only: round trips per guest call")
    p.add_argument("--warmup", type=int)   # per-mode defaults filled below
    p.add_argument("--iters", type=int)
    p.add_argument("--core-ping", type=int, default=4)
    p.add_argument("--core-pong", type=int, default=6)
    a = p.parse_args()

    if a.mode == "control":
        if a.chunk != 1000:
            p.error("--chunk is a wasm-mode option")
        a.warmup = 20 if a.warmup is None else a.warmup
        a.iters = 200 if a.iters is None else a.iters      # ~10ms RTTs: ~2-4s total
    else:
        if a.switch_us is not None:
            p.error("--switch-us is a control-mode option")
        a.warmup = 5_000 if a.warmup is None else a.warmup
        a.iters = 50_000 if a.iters is None else a.iters

    out = derive_out(a)
    if out.exists():
        sys.exit(f"refusing to overwrite {out} - move it or pick a new name")

    run_control(a, out) if a.mode == "control" else run_wasm(a, out)