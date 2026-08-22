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