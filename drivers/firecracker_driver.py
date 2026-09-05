import json
import subprocess
import uuid
from pathlib import Path

from .base import RuntimeDriver, Instance

FC_DIR = Path("fc").resolve()
    # .resolve() because Firecracker resolves paths iteslf, and the JSON must be absolute
    # Without this, run into NotFoundError
FC_BIN = FC_DIR / "firecracker"
KERNEL = FC_DIR / "vmlinux"
ROOTFS = FC_DIR / "rootfs.ext4"
BOOT_ARGS = ("console=ttyS0 reboot=k panic=1 pci=off "
             "i8042.noaux i8042.nomux i8042.nopnp i8042.dumbkbd "
             "quiet loglevel=0 init=/{binary}")
# Custom boot args to disable uncessary parts and run the workload binary directly
    # console=ttyS0 flag is required to get the guest to print to stdout, which is captured by Firecracker and printed to the host terminal.
    # reboot=k converts the guest reboot into the Firecracker process exiting.
    # panic=1 converts the guest kernel panic into the Firecracker process exiting.
    # pci=off disables PCI, which is not needed for this benchmark and avoids a lot of kernel messages.
    # i8042.* skips probing for harware that does not exist in the VM, which avoids a lot of kernel messages and allows for a faster boot.
    # quiet drops the boot logs to warnings and errors only
    # loglevel=0 drops the boot logs, allows for first byte on the serial console to be READY
    # init=/{binary} runs the workload binary directly, instead of running /sbin/init and then executing the workload binary.
SKIM_LIMIT = 200
    # Set limit so a broekn guest fails loudly instead of silently hanging forever
    

class FirecrackerDriver(RuntimeDriver):
    name = "firecracker"

    # Note: kernel and rootfs building is handled outside of this logic to avoid 
    # needing a password for sudo in the middle of a benchmark run.
        # This differs from the other runtimes, which can build their own binaries within the benchmark run.
    def prepare(self, workload: str) -> None:
        # Only accept rust workloads, not python ones.
        if not workload.endswith("_rs"):
            raise ValueError(f"firecracker guests are native binaries; use {workload}_rs")
        # -3 removes the _rs suffix to get the binary name
        binary = workload[:-3]
        # Check that the required artefacts exist and are up to date.
            # Test added to mirror how something like docker build would guarentee the image.
        for artefact in (FC_BIN, KERNEL, ROOTFS):
            if not artefact.exists():
                raise FileNotFoundError(f"{artefact} missing; run make build-fc-rootfs")
        guest = Path("workloads_rust/target/x86_64-unknown-linux-musl/release") / binary
        if ROOTFS.stat().st_mtime < guest.stat().st_mtime:
            raise RuntimeError("fc/rootfs.ext4 is older than the guest binary; run make build-fc-rootfs")
        
        # Generate a Firecracker config JSON for this workload, which will be used to boot the guest.
        cfg = {
            "boot-source": {
                "kernel_image_path": str(KERNEL),
                "boot_args": BOOT_ARGS.format(binary=binary),
            },
            "drives": [{
                "drive_id": "rootfs",
                "path_on_host": str(ROOTFS),
                "is_root_device": True,
                "is_read_only": True,
            }],
            "machine-config": {"vcpu_count": 1, "mem_size_mib": 128},
        }
        # Write the config to a JSON file named after the workload.
        (FC_DIR / f"{workload}.json").write_text(json.dumps(cfg, indent=1))
        
    def provision(self, workload: str) -> Instance:
        
        # Start Firecracker with the generated config, and wait for it to print READY to stdout.
        proc = subprocess.Popen(
            [str(FC_BIN), "--no-api", "--config-file", str(FC_DIR / f"{workload}.json"),
             "--log-path", "/dev/null"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )
        # added assertion to satisfy type checker, and remove warning
        assert proc.stdin is not None and proc.stdout is not None
        for _ in range(SKIM_LIMIT):
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError("firecracker exited before READY")
            if line.strip() == b"READY":
                break
        else:
            raise RuntimeError(f"READY not seen within {SKIM_LIMIT} lines")
        # Return an Instance object with the Firecracker process and a unique ID
        return Instance(id="fc-" + uuid.uuid4().hex[:8], runtime="firecracker",
                        meta={"proc": proc})

    # Execute a payload in the Firecracker guest by writing to stdin and reading from stdout.
    def execute(self, instance: Instance, payload: bytes) -> bytes:
        proc = instance.meta["proc"]
        proc.stdin.write(payload + b"\n")
        # Flush stdin to ensure the payload is sent to the guest.
        proc.stdin.flush()
        # Read from stdout until we get the payload echoed back, then read the next line which is the actual output.
            # Done to bypass the /r/n echo that prints before the actual output.
        line = proc.stdout.readline().strip()
        if line == payload:
            line = proc.stdout.readline().strip()
        return line
    
    # Collect peak memory usage from Firecracker guest by reading /proc/<pid>/status VmHWM
        # Identical to the Wasmtime driver, but with a different process.
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
    
    # Teardown the Firecracker guest by sending EOF to stdin and waiting for the process to exit.
    def teardown(self, instance: Instance) -> None:
        proc = instance.meta["proc"]
        # Send EOF to the guest by writing Ctrl-D (ASCII 4) to stdin.
        try:
            proc.stdin.write(b"\x04")
            proc.stdin.flush()
            proc.stdin.close()
            proc.wait(timeout=5)
        # If the process does not exit within 5 seconds, kill it and wait for it to exit.
        except (BrokenPipeError, subprocess.TimeoutExpired):
            proc.kill()
            proc.wait()


# Smoke test: python -m drivers.firecracker_driver
if __name__ == "__main__":
    import time
    d = FirecrackerDriver()
    d.prepare("model1_rs")
    inst = d.provision("model1_rs")
    print("provisioned:", inst.id)
    print("execute:", d.execute(inst, b"1000"))   # expected: b'332833500'
    print("collect:", d.collect(inst))
    t0 = time.perf_counter()
    d.teardown(inst)
    print(f"teardown complete in {time.perf_counter() - t0:.2f}s")