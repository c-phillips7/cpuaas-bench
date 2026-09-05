#!/usr/bin/env bash
# fc/build_rootfs.sh - assemble the Firecracker guest root filesystem.
# Contents: the two static musl workload binaries and a /dev/console node. Nothing else.
# The workload runs AS init (init=/model1 in the boot args), so no shell or libc is needed.
set -euo pipefail
cd "$(dirname "$0")/.."
BIN=workloads_rust/target/x86_64-unknown-linux-musl/release
OUT=fc/rootfs.ext4
MNT=$(mktemp -d)
dd if=/dev/zero of="$OUT" bs=1M count=32 status=none
mkfs.ext4 -q -F "$OUT"
sudo mount -o loop "$OUT" "$MNT"
sudo cp "$BIN/model1" "$BIN/model2" "$MNT/"
sudo mkdir -p "$MNT/dev"
sudo mknod -m 600 "$MNT/dev/console" c 5 1
sudo umount "$MNT"
rmdir "$MNT"
ls -la "$OUT"