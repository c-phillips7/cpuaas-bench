import subprocess
import uuid

from .base import RuntimeDriver, Instance


# NOTE: no text=True included because abstract contract is bytes in/out, not text. The workload is responsible for encoding/decoding text to bytes if needed.
class DockerDriver(RuntimeDriver):
    name = "docker"
    image = "bench-py"
    
    def prepare(self, workload: str) -> None:
        """
        Build the docker image for the workload ONCE ahead of time
        
        Excluded from all timings by design to exclude compilation time from the measured cold start time
        
        Logically, in a FaaS platform, this would be done by the platform operator, not the user, and would not be part of the cold start measurement.
        """
        subprocess.run(["docker", "build", "-t", self.image, "."],
                       check=True, capture_output=True)
        # check=True raises CalledProcessError if the command fails
        # capture_output=True captures stdout and stderr, not included in timings, but useful for debugging if the build fails.

    def provision(self, workload: str) -> Instance:
        # Name is assigned to the container so we can refer to it later for teardown and metrics collection. Using a short unique name avoids collisions with other containers.
        name = "bench-" + uuid.uuid4().hex[:8]  # short unique name for the container
        
        # Run attached with piped stdin/stdout; -i holds stdin open for the request/response protocol, --rm auto-removes on exit
            # f"{workload}.py is the workload script to run inside the container
        proc = subprocess.Popen(
            ["docker", "run", "--rm", "-i", "--name", name, self.image,
            "python", "-u", f"{workload}.py"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )
        # Wait for the workload to signal that it is ready to accept work. The workload prints "READY" to stdout when it is ready.
        # Blocking on READY means a timed provision() spans the full cold start (container + interpreter + workload init), not just container creation.
        first = proc.stdout.readline().strip() # type: ignore
            # Ignore for error since stdout is not None because we passed stdout=subprocess.PIPE
        if first != b"READY":
            raise RuntimeError(f"expected READY, got {first!r}")
        return Instance(id=name, runtime="docker", meta={"proc": proc})
    
    def execute(self, instance: Instance, payload: bytes) -> bytes:
        proc = instance.meta["proc"]
        # Send the payload to the container's stdin and read the result from stdout.
        proc.stdin.write(payload + b"\n")  # add newline to signal end of input
        proc.stdin.flush()  # ensure the data is sent immediately!
        return proc.stdout.readline().rstrip(b"\n") # read the result and strip the newline
    
    def collect(self, instance: Instance) -> dict:
        # Read peak memory usage from the container's cgroup file.
        # Note:This is a Linux-specific implementation. Other drivers may have different ways to collect metrics.
        full_id = subprocess.run(
            ["docker", "inspect", "--format", "{{.Id}}", instance.id],
            check=True, capture_output=True
        ).stdout.decode().strip() # get the full container ID from the short name assigned earlier
        
        # The cgroup file path based on the full container ID.
        # Note: This path may vary based on the Docker version and configuration.
        # Path found using the following command while a container was alive:
        #   find /sys/fs/cgroup -name "memory.peak" -path "*docker*"
        path = f"/sys/fs/cgroup/system.slice/docker-{full_id}.scope/memory.peak" 
        with open(path, "r") as f:
            peak = int(f.read()) # read the peak memory usage in bytes
        return {"memory_peak_bytes": peak}
    
    def teardown(self, instance: Instance) -> None:
        # Stop the container
        proc = instance.meta["proc"]
        proc.stdin.close()  # close stdin to signal the container to exit
        try:
            proc.wait(timeout=5)  # wait for the container to exit gracefully, using build in --rm to remove the container automatically
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", instance.id],
                           capture_output=True)  # force remove the container if it didn't exit in time
            # Note: The above only used as a backup, not main way to kill the process to avoid any built in grace period for shutdown.
            # Also avoids complications with comparison to Wasmtime or other runtimes that may not have a graceful shutdown signal.
            
# Smoke test
if __name__ == "__main__":
    d = DockerDriver()
    d.prepare("model1")
    inst = d.provision("model1")
    print("provisioned:", inst.id)
    print("execute:", d.execute(inst, b"1000")) # Expected output: 332833500
    print("collect:", d.collect(inst))
    d.teardown(inst)
    print("teardown complete")