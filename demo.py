#!/usr/bin/env python3
# =============================================================================
# demo.py - guided front-end for running the benchmark suite (viva demo aid).
# WRAPPER ONLY: this file knows no benchmark logic. It builds the exact same
# command lines a user would type, SHOWS the command first, then runs it via
# bench.py / workloads/model3_wasm.py. One source of truth; every guard and
# overwrite policy stays in the scripts that own it - this menu just narrates.
# Run from the repo root: python3 demo.py
# =============================================================================
import subprocess
import sys


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


def opt_m1():
    cmd = [sys.executable, "bench.py", "m1"]
    runtime = ask("runtime", "docker", ["docker", "wasmtime"])
    cmd += ["--runtime", runtime]
    if runtime == "docker":
        w = ask("workload", "model1", ["model1", "model1_rs"])
        if w != "model1":
            cmd += ["--workload", w]
    cmd += ["--reps", ask("reps", "30")]
    print("note: an untagged run OVERWRITES the canonical file (regeneration policy)")
    tag = ask("tag to keep it separate (blank = overwrite canonical)", "")
    if tag:
        cmd += ["--tag", tag]
    confirm_and_run(cmd)


def opt_m2():
    cmd = [sys.executable, "bench.py", "m2"]
    runtime = ask("runtime", "docker", ["docker", "wasmtime"])
    cmd += ["--runtime", runtime]
    cmd += ["--sessions", ask("sessions", "5"), "--execs", ask("execs", "30")]
    print("note: an untagged run OVERWRITES the canonical file (regeneration policy)")
    tag = ask("tag to keep it separate (blank = overwrite canonical)", "")
    if tag:
        cmd += ["--tag", tag]
    confirm_and_run(cmd)


def opt_m3_docker():
    # v1 rule: multi-container work is PRINTED, never orchestrated -
    # bench.py m3 emits the two-terminal command pair; this just invokes it
    cmd = [sys.executable, "bench.py", "m3",
           ask("mechanism", "shm", ["shm", "tcp"])]
    netem = ask("netem delay e.g. 10ms (blank = none)", "")
    if netem:
        cmd += ["--netem", netem]
    subprocess.run(cmd)
    print("\n(paste the pair above into two terminals, first-listed first)")


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
    # output guard lives in the script itself; it will refuse an existing file
    confirm_and_run(cmd)


OPTIONS = {
    "1": ("Model 1 cold starts", opt_m1),
    "2": ("Model 2 sessions", opt_m2),
    "3": ("Model 3: docker shm/tcp (prints two-terminal pair)", opt_m3_docker),
    "4": ("Model 3: wasm / python-threads control", opt_m3_wasm),
    "5": ("Regenerate all figures",
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