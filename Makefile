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

build-fc-rootfs: build-rust
	@echo "Assembling the Firecracker guest rootfs (32 MiB ext4: two musl binaries + /dev/console)"
	fc/build_rootfs.sh

fc-gate:
	@echo "Booting the Firecracker guest interactively. Ctrl-D to exit."
	fc/firecracker --no-api --config-file fc/gate.json