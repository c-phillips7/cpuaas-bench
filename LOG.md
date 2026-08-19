
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