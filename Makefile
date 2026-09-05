build:
	docker build -t bench-py .

network:
	docker network create benchnet 2>/dev/null || true

run-model1:
	docker run -i --rm bench-py

run-model2:
	docker run -i --rm bench-py python -u model2.py

clean:
	docker ps -aq --filter "name=bench-" --filter "name=m3-" | xargs -r docker rm -f

build-wasm:
	cargo build --manifest-path workloads_rust/Cargo.toml --release --target wasm32-wasip1

build-rust:
	cargo build --manifest-path workloads_rust/Cargo.toml --release --target x86_64-unknown-linux-musl

# Pinned Firecracker release + CI guest kernel (the exact pair used for all results).
FC_VERSION = v1.16.1
FC_KERNEL_KEY = firecracker-ci/v1.15/x86_64/vmlinux-6.1.155

fc-fetch:
	@echo "Fetching Firecracker $(FC_VERSION) and guest kernel $(notdir $(FC_KERNEL_KEY)) into fc/"
	mkdir -p fc
	curl -sL https://github.com/firecracker-microvm/firecracker/releases/download/$(FC_VERSION)/firecracker-$(FC_VERSION)-x86_64.tgz | tar -xz -C fc
	mv fc/release-$(FC_VERSION)-x86_64/firecracker-$(FC_VERSION)-x86_64 fc/firecracker && rm -rf fc/release-$(FC_VERSION)-x86_64
	curl -sL -o fc/vmlinux https://s3.amazonaws.com/spec.ccfc.min/$(FC_KERNEL_KEY)
	fc/firecracker --version && ls -la fc/vmlinux

build-fc-rootfs: build-rust
	@echo "Assembling the Firecracker guest rootfs (32 MiB ext4: two musl binaries + /dev/console)"
	fc/build_rootfs.sh

fc-gate:
	@echo "Booting the Firecracker guest interactively. Ctrl-D to exit."
	fc/firecracker --no-api --config-file fc/gate.json