
# Docker workings
- Installed native Linux docker in Ubuntu instead of desktop windows version used previously.
- needed cgroup path for memory.peak 
    - discovered via find with a live container, systemd scope pattern confirmed
    Docker memory.peak location:
    find /sys/fs/cgroup -name "memory.peak" -path "*docker*"
    /sys/fs/cgroup/system.slice/docker-a84c991c517b8be6eb2eda6006b471af22aed5b615c4a8ca27466007f41d16b9.scope/memory.peak
- 