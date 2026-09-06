Non textnsive List of workings, just notes made along the way outside of git commits

# Docker workings
- Installed native Linux docker in Ubuntu instead of desktop windows version used previously.
- needed cgroup path for memory.peak 
    - discovered via find with a live container, systemd scope pattern confirmed
    Docker memory.peak location:
    find /sys/fs/cgroup -name "memory.peak" -path "*docker*"
    /sys/fs/cgroup/system.slice/docker-a84c991c517b8be6eb2eda6006b471af22aed5b615c4a8ca27466007f41d16b9.scope/memory.peak
- runner.py + first cold-start CDF: median runs ~200ms, first rep the slowest, likely due to page-cache
    - Noticed Rep-0 memory is different: 14 MB vs ~5.5 MB for others. Again points to cgroup pages cache for the first itteration
- Crossover analysis comparing model 1 to model 2 in docker. Difference is ~195ms/request regret vs ~5.5 MB residency
-  Warm executions lower and tighter than Model 1 executions
    - M1 always pays first invocation costs.
- Redid naming scheme to be (runtime_model_mechanism_condition)
- Noticed issue of overiding files when trying different netem latencys. Fixed overwriting issue with guard built into scripts and options to add names in the commands.
- Meta json sidecar added to be clear how many warm ups and invocations were used for the data (I had forgotten what I did for some of the past runs).
- Netem fidelity set up and tested. Appears to be working as intended
- Noticed issue with docker buildx plugin proken, and legacy builder fallback was being used. Resolved after reinstall and daemon cycle.
- Analysis scipts had issue accessing venv, made measurement stdlib only
- Created unified bench.py script to act as an entry point, where the kind of runtime, model, and other args can be passed to give an easier reproducable test suite (Not automated yet, still requires manual copying of commands into two seperate terminals for model 3)
    - Similarly changed WARMUP, ITERS and condition to CLI arguments, no need to rebuld docker when trying different values.
- Found bug where sentinel race at 50 ms netem, the shutdown packet died when the container was killed. The pong hung, so fixed with sleep of 0.5s at the end before killing process.
- Ran full reporducibility run with the new bench.py, all looks good.

# Wasamtime workings
- Due to how wasm is built is seems rust is significantly more optimized for the workload. There is a python option, but that just baloons the size of each image, offsetting the main benefit of wasam's very fast cold start compared to docker
    - Potentially could implement a rust workload (or some equivalent) to the docker implementation.
- built rust based workloads based on boilerplate cargo wasm library
- Translated as closely as I could the docker driver logic to wasmtime, noting differences.
    - Smoke test passes as expected
- updated bench.py to allow for different drivers to be passed as an argument and run the relevant code, maintining the central entry point
- built python equivalent of docker logic for wasm, but it was extremely slow (~10ms)
    - found there is a built in delay via sys.setswitchinterval, which can be set to a lower value, which when lowered to the limit was still too slow (~0.17ms)
- All the python logic seems to cause issues when being translated to WebAssembly, meaning all measuements there have been for just python interperitation and translation, not the desired measurement.
- Implemented WAT (Plain english WebAssembly) to pre translate the model3_shm protocals.
    - This allows wasm to actually work in its native WebAssembly
- In testing wasm with WAT, found another issue with Foreign Function Interface (FFI) between parts of my python instructions and the true RTT for wasm 
    - Here the issue comes from Python→native Wasmtime via ctypes
    - Used a system of batching runs and taking the average to measure this toll, and try and get the real RTT

# Back to Docker
- To compare the cold startup and other analysis in models 1 and 2, to account for the introduced rust workload, a Docker equivalent is added.
- Implemented a pipeline to generate the binaries for docker to use, and added them to the build.
- Added _rs to the naming convention, and added logic to check for _rs as a siffix to log the workload as rust based.
- Re ran model 1 and 2 for docker (python workload), and new rust workloads to give clean comparison
    - slight differences, but on the scale of docker vs Wasm, barely noticible

# Firecracker workings
- Install: Firecracker v1.16.1 release binary. The getting-started kernel script returned an empty key because the v1.16 CI bucket had no kernels yet; a 385 KB XML listing got saved as vmlinux. Spotted by size (a kernel is ~40 MB). Listed the v1.15 bucket by hand, took vmlinux-6.1.155 plus its .config, recorded the pairing.
- Rootfs: 32 MiB ext4, loop-mounted, only model1, model2 (the musl static-pie binaries, file string) and a /dev/console node. No shell, no libc. Kernel config confirmed DEVTMPFS_MOUNT=y, so the node is belt-and-braces.
- Workload runs as init (init=/model1) so the guest starts nothing but the workload, same fairness argument as the _rs Docker control. No networking at all; the serial console is the protocol channel.
- First verbose boot: Run /model1 as init process at 0.806 s, READY, 1000 → 332833500. Ctrl-D produced Attempted to kill init! exitcode=0x0, Rebooting in 1 seconds, Firecracker exited. So EOF-shutdown works over serial.
Half-second gap in the boot log between clk: Disabling unused clocks and AT Raw Set 2 keyboard: the kernel probing a PS/2 keyboard that does not exist. Added i8042.noaux i8042.nomux i8042.nopnp i8042.dumbkbd (Firecracker's own integration-test flags): init at 0.294 s.
- Added quiet boot (quiet loglevel=0): READY is the first byte the guest writes; even the panic trace is silent because the kernel only raises the console level on panic when it was non-zero.
- Driver made, same five methods as wasmtime. prepare() verifies artefacts and writes fc/<workload>.json rather than building (the rootfs build needs sudo; lives in the Makefile). Added a staleness check: refuses a rootfs older than the guest binary. base.py docstring amended to match.
- bench.py integration: three lines (RUNTIMES, get_driver, usage note); plot_cold_compare one line; runner zero. No leftover VMMs after 35 boots (pgrep firecracker empty).
- Result I did not expect: Firecracker boots a whole kernel faster than Docker starts a container (119 vs 192 ms). Order is Wasm < FC < Docker, memory the other way round (5.5 / 16.5 / 47.6 MB). Plan had predicted 150 to 300 ms.

# Clean up, refactors and demo
- results/ had 65 files flat. Moved to results/<runtime>/ (docker 10, wasmtime 9, firecracker 2, host 8 results + sidecars) and results/figures/. Folder = filename's first token.
- bench.py figures only ran 5 of the 7 figure scripts (executor sweep and chunk fit were missing). Fixed; "all figures regenerate" is now true. __pycache__ was tracked; untracked and ignored.
- Ladder figure: added the Wasm rung and the Python-threads control (8 series, per-series column). Control lands on top of the 10 ms netem rung; SHM+netem is drawn exactly over SHM.
- Demo audit found wasm M3 had no --tag, so its overwrite guard had no escape; added. fc-fetch Makefile target pinned to the exact versions. Demo gained build and interactive-boot options.
- Demo ran int a bug: after the interactive Firecracker boot, Python's input() returned EOF forever (menu spammed). Shell was fine afterwards (stty -a normal), so it was Python's stdin, not the terminal. Fix: reopen sys.stdin from /dev/tty after the boot; exit cleanly on EOF/Ctrl-C.
- README written (AI-drafted, edited by me); wasmtime CLI 47.0.3 confirmed installed via the official installer (~/.wasmtime/bin).