# RuntimeDriver abstract base class
# Goals: provision a sandbox, time it, run the workload, time it, read memory, tear down, repeat

"""
This module defines the CONTRACT between the benchmark loop and the three runtime drivers under test
Docker, Firecracker, Wasmtime
Using standardized contract to ensure measured performance is comparable across runtimes
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

@dataclass
class Instance:
    """
    One live sandbox created by a driver's provision() call
    
    execute() and teardown() need to know which sandbox to address
    """
    id: str
    runtime: str
    # meta holds whatever the driver needs to reach the sandbox later
        # for all three drivers this is the child process handle.
    meta : dict = field(default_factory=dict)

class RuntimeDriver(ABC):
    """
    Abstract base class

    The harness holds the single stopwatch and times the *calls* to these methods
        NOTE: if each driver timed itself there would be three timing implementations with no guarantee they measure the same thing.
    One stopwatch held by the referee keeps the comparison fair
    
    Lifecycle of one measurement:
        prepare() -> provision() -> execute(x1 or xN) -> collect() -> teardown()
        
    prepare (excluded), provision (=cold start), execute (=exec latency), collect (metrics), teardown (cleanup)
    
    Model 1 (ephemeral): provision -> execute -> collect -> teardown, per request
    Model 2 (session): provision -> execute many -> collect -> teardown
    """

    # Concrete driver overrides label for logging and reporting
    name: str = "abstract"

    @abstractmethod
    def prepare(self, workload: str) -> None:
        """
        Build the runtime-specific artefact for a workload ONCE ahead of time
        
        Docker: build the image
        Wasmtime: compile the wasm module
        Firecracker: verify the kernel and root filesystem exist and write the VM config
        
        Excluded from all timings by design to exclude compilation time from the measured cold start time
        """
        
    @abstractmethod
    def provision(self, workload: str) -> Instance:
        """
        Create a new sandbox and BLOCK until the workload signals it is ready.

        The harness times this entire call, so its duration is the cold start latency.
        The blocking requirement is what makes that true: if this returned before the workload could accept work, the measurement would be of sandbox creation only and would underestimate the cold start latency.
        """

    @abstractmethod
    def execute(self, instance: Instance, payload: bytes) -> bytes:
        """
        Run one invocation against a live instance and return its result.

        The harness times this call = execution latency. In Model 2, repeated execute() calls against one instance give the warm-invocation numbers.
        """
    

    @abstractmethod
    def collect(self, instance: Instance) -> dict:
        """
        Read resource metrics for this instance (NOT TIMING METRICS)
        
        Contract: every driver returns the SAME keys, so the harness can write
        uniform CSV rows with no per-runtime special cases. Keys carry their
        units in the name (current contract: memory_peak_bytes) so a
        bytes-vs-MB confusion cannot be typed silently.
        
        Docker: peak memory from the container's cgroup file (memory.peak)
        Wasmtime and Firecracker: VmHWM of the process from /proc (peak resident memory)
        """

    @abstractmethod
    def teardown(self, instance: Instance) -> None:
        """
        Destroy the sandbox and leave NO residue.

        Postcondition: no running container/VM/process remains, and any shared resources are released.
        """

    # Self-test: run `python -m drivers.base` to watch Python enforce the contract.
if __name__ == "__main__":
    try:
        RuntimeDriver()  # type: ignore[abstract]
    except TypeError as e:
        print(f"OK -- abstract class refused instantiation:\n  {e}\n")
 
    class Forgetful(RuntimeDriver):  # implements only 1 of 5 required methods
        def prepare(self, workload: str) -> None: ...
 
    try:
        Forgetful()  # type: ignore[abstract]
    except TypeError as e:
        print(f"OK -- incomplete driver rejected, missing methods listed:\n  {e}")
