import sys

# flush=True is used to ensure that the output is sent immediately, which is important for inter-process communication.
print("READY", flush=True)


# variable initialized outside of logic, as Model 2 requires the workload to maintain state across invocations.
total = 0
for line in sys.stdin:
    n = int(line.strip())
    total += sum(i * i for i in range(n))
    print(total, flush=True)