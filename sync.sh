#!/usr/bin/env bash
# Push a code snapshot to the Windows side for backup. Never run benchmarks there!!!
rsync -a --delete --exclude '.venv' --exclude '.git' --exclude 'results/' \
  ~/cpuaas-bench/ "/mnt/c/Users/cpphi/Documents/Westminster/Project/ProjectFiles/cpuaas-bench/"
echo "Synced $(date)"