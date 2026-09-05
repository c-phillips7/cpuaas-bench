#!/usr/bin/env python3
# =============================================================================
# demo.py - guided front-end for running the benchmark suite (viva demo aid).
# WRAPPER ONLY: this file knows no benchmark logic. It builds the exact same
# command lines a user would type, SHOWS the command first, then runs it via
# bench.py / workloads/model3_wasm.py / make. One source of truth; every guard
# and overwrite policy stays in the scripts that own it - this menu narrates.
# Run from the repo root: python3 demo.py
# =============================================================================
import subprocess
import sys

RUNTIMES = ["docker", "wasmtime", "firecracker"]


def ask(prompt, default=None, choices=None):
    # one prompt helper for everything: shows choices and [default],
    # Enter accepts the default, re-asks until the answer is valid
    c = f" ({'/'.join(choices)})" if choices else ""
    d = f" [{default}]" if default not in (None, "") else ""
    while True:
        raw = input(f"{prompt}{c}{d}: ").strip()
        if not raw and default is not None:
            return default
        if not choices or raw in choices:
            return raw
        print(f"  pick one of: {', '.join(choices)}")


def confirm_and_run(cmd):
    # the demo's core move: show the reproducible command, then run it.
    # if the menu ever fails mid-demo, this printed line is the escape hatch.
    print("\ncommand:\n  " + " ".join(cmd) + "\n")
    if ask("run it?", "y", ["y", "n"]) == "y":
        subprocess.run(cmd)
    else:
        print("skipped.")


def ask_tag(cmd, policy):
    # the overwrite policy differs by tier; say which one applies, then offer --tag
    print(f"note: {policy}")
    tag = ask("tag to keep this run alongside existing data (blank = none)", "")
    return cmd + (["--tag", tag] if tag else [])


REGEN = "an untagged m1/m2 run OVERWRITES the canonical file (regeneration policy)"
GUARD = ("raw M3 runs are GUARDED: an existing output file is refused, never overwritten; "
         "repeat a condition with a tag, or move the old file first")


def pick_workload(runtime, model):
    # docker can run either the python or the rust workload; firecracker guests
    # are native binaries only (the driver refuses anything else); wasmtime's
    # module name is the plain workload name
    if runtime == "docker":
        w = ask("workload", f"model{model}", [f"model{model}", f"model{model}_rs"])
        return [] if w == f"model{model}" else ["--workload", w]
    if runtime == "firecracker":
        print(f"note: firecracker guests are native binaries -> --workload model{model}_rs")
        return ["--workload", f"model{model}_rs"]
    return []


def opt_build():
    # prerequisites, in dependency order; each target is idempotent.
    # build-fc-rootfs needs sudo (loop mount) and fc-fetch needs the network.
    print("targets: build (docker image) build-wasm build-rust fc-fetch build-fc-rootfs network")
    which = ask("which", "all", ["all", "docker", "wasm", "rust", "firecracker", "network"])
    targets = {"all": ["build", "network", "build-wasm", "build-rust", "fc-fetch", "build-fc-rootfs"],
               "docker": ["build", "network"], "wasm": ["build-wasm"], "rust": ["build-rust"],
               "firecracker": ["build-rust", "fc-fetch", "build-fc-rootfs"], "network": ["network"]}[which]
    confirm_and_run(["make", *targets])


def opt_m1():
    cmd = [sys.executable, "bench.py", "m1"]
    runtime = ask("runtime", "docker", RUNTIMES)
    cmd += ["--runtime", runtime] + pick_workload(runtime, 1)
    cmd += ["--reps", ask("reps", "30")]
    confirm_and_run(ask_tag(cmd, REGEN))


def opt_m2():
    cmd = [sys.executable, "bench.py", "m2"]
    runtime = ask("runtime", "docker", RUNTIMES)
    cmd += ["--runtime", runtime] + pick_workload(runtime, 2)
    cmd += ["--sessions", ask("sessions", "5"), "--execs", ask("execs", "30")]
    confirm_and_run(ask_tag(cmd, REGEN))


def opt_m3_docker():
    # v1 rule: multi-container work is PRINTED, never orchestrated -
    # bench.py m3 emits the two-terminal command pair; this just invokes it
    cmd = [sys.executable, "bench.py", "m3",
           ask("mechanism", "shm", ["shm", "tcp"])]
    netem = ask("netem delay e.g. 10ms (blank = none)", "")
    if netem:
        cmd += ["--netem", netem]
    cmd = ask_tag(cmd, GUARD)
    subprocess.run(cmd)
    print("\n(paste the pair above into two terminals, first-listed first;"
          " needs `make build network` once. If ping is refused by the guard,"
          " the waiting pong is stopped with `make clean`)")


def opt_m3_wasm():
    cmd = [sys.executable, "workloads/model3_wasm.py"]
    mode = ask("mode", "wasm", ["wasm", "control"])
    if mode == "control":
        cmd.append("control")
        si = ask("switch-us (blank = untouched interpreter default)", "")
        if si:
            cmd += ["--switch-us", si]
    else:
        chunk = ask("chunk (round trips per guest call)", "1000")
        if chunk != "1000":
            cmd += ["--chunk", chunk]
    confirm_and_run(ask_tag(cmd, GUARD))


def opt_fc_gate():
    # the most watchable thirty seconds: a kernel boots into the workload binary.
    print("a Firecracker microVM boots with the workload as init; type 1000 + Enter"
          " (expect 332833500), then Ctrl-D to exit. Ctrl-C goes to the guest and"
          " does nothing; `pkill firecracker` from another terminal is the escape hatch.")
    confirm_and_run(["make", "fc-gate"])


OPTIONS = {
    "0": ("Build prerequisites (docker image, wasm + musl binaries, firecracker assets)", opt_build),
    "1": ("Model 1 cold starts", opt_m1),
    "2": ("Model 2 sessions", opt_m2),
    "3": ("Model 3: docker shm/tcp (prints two-terminal pair)", opt_m3_docker),
    "4": ("Model 3: wasm / python-threads control", opt_m3_wasm),
    "5": ("Firecracker: boot the guest interactively (make fc-gate)", opt_fc_gate),
    "6": ("Regenerate all figures (results/figures/)",
          lambda: confirm_and_run([sys.executable, "bench.py", "figures"])),
}

if __name__ == "__main__":
    while True:
        print("\n=== cpuaas-bench demo ===")
        for k, (label, _) in OPTIONS.items():
            print(f"{k}) {label}")
        print("q) quit")
        choice = ask("select", None, [*OPTIONS, "q"])
        if choice == "q":
            break
        OPTIONS[choice][1]()
