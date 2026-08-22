import subprocess
import uuid
from pathlib import Path

from .base import RuntimeDriver, Instance

# Built artefacts live where cargo put them; the driver is always run from the repo root
WASM_DIR = Path("workloads_rust/target/wasm32-wasip1/release")


class WasmtimeDriver(RuntimeDriver):
    """
    Process-per-request Wasmtime driver: one `wasmtime run` OS process per provision().
    Matches speaking the same READY/stdin/stdout protocol as the Docker driver as closely as possible.
    
    Chosen over an embedded (in-process) driver for comparability.
    """
    name = "wasmtime"

    def prepare(self, workload: str) -> None:
        """
        AOT-compile the .wasm module to native code (.cwasm) ONCE ahead of time.

        Mirrors DockerDriver.prepare()'s image build: 
        compilation is excluded from the timed cold start by design, 
        so provision() measures sandbox creation, not code generation.
        Same measurement boundary, same justification.
        """
        src = WASM_DIR / f"{workload}.wasm"
        dst = WASM_DIR / f"{workload}.cwasm"
        subprocess.run(["wasmtime", "compile", str(src), "-o", str(dst)],
                       check=True, capture_output=True) # Both true to fail loudly, not in the background

    def provision(self, workload: str) -> Instance:
        # --allow-precompiled: wasmtime refuses .cwasm by default 
        # (off by default as a malicious precompiled file bypasses usual checks); 
            # compilation is build into prepare(), so .cwasm is included
        # No --name needed as instance is not accessed via uuid like with Docker
        proc = subprocess.Popen(
            ["wasmtime", "run", "--allow-precompiled",
             str(WASM_DIR / f"{workload}.cwasm")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )
        
        assert proc.stdin is not None and proc.stdout is not None  # PIPE passed above, added to removes VSCode warning
        # Same blocking-on-READY contract as Docker: a timed provision() spans;
        # process creation + runtime init + module instantiation + workload startup, i.e. the full cold start.
        first = proc.stdout.readline().strip()
        if first != b"READY":
            raise RuntimeError(f"expected READY, got {first!r}")
        return Instance(id="wasm-" + uuid.uuid4().hex[:8], runtime="wasmtime",
                        meta={"proc": proc})

    # This is within the timed reigon, so left as minimal as possible
    def execute(self, instance: Instance, payload: bytes) -> bytes:
        proc = instance.meta["proc"]
        proc.stdin.write(payload + b"\n")           # frame the request: one line = one invocation
        proc.stdin.flush()                          # push it out of the buffer, into the tube NOW
        return proc.stdout.readline().rstrip(b"\n") # block until the one-line response

    def collect(self, instance: Instance) -> dict:
        """
        Peak memory from /proc/<pid>/status VmHWM (peak resident set size).

        Semantics caveat vs Docker: Docker's cgroup
        memory.peak counts the whole container cgroup INCLUDING page cache;
        VmHWM counts one process's peak resident pages. Both are "peak bytes
        of a sandbox", but the accounting boundary differs.
        Must be called while the process is alive -> collect-before-teardown,
        same forced ordering as Docker (whose cgroup dies with the container).
        """
        proc = instance.meta["proc"]
        with open(f"/proc/{proc.pid}/status") as f:
            for line in f:
                if line.startswith("VmHWM:"):
                    return {"memory_peak_bytes": int(line.split()[1]) * 1024}
        raise RuntimeError("VmHWM not found in /proc status")

    def teardown(self, instance: Instance) -> None:
        # Shutdown-by-EOF, the protocol's runtime-agnostic shutdown message
        # (same rationale as Docker: no runtime-specific stop mechanism used).
        proc = instance.meta["proc"]
        proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()   # fallback only, mirrors docker rm -f
            proc.wait()


# Smoke test: python -m drivers.wasmtime_driver
if __name__ == "__main__":
    d = WasmtimeDriver()
    d.prepare("model1")
    inst = d.provision("model1")
    print("provisioned:", inst.id)
    print("execute:", d.execute(inst, b"1000"))   # expected: b'332833500'
    print("collect:", d.collect(inst))
    d.teardown(inst)
    print("teardown complete")
