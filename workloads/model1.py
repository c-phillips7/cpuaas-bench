import sys

# flush=True is used to ensure that the output is sent immediately, which is important for inter-process communication.
print("READY", flush=True)

for line in sys.stdin:
    n = int(line.strip()) # n is the workload-size parameter, read from stdin
    result = sum(i * i for i in range(n)) # do some work
    print(result, flush=True)
# No explicit exit needed; the process will exit when stdin is closed.
    