import threading
import time

import grpc

import service_pb2
import service_pb2_grpc


BACKENDS = [
    "localhost:60201",
    "localhost:60202",
    "localhost:60203"
]

NUM_REQUESTS = 9

# Number of currently active requests
active = [0] * len(BACKENDS)

# Protect shared active connection counters
lock = threading.Lock()


def pick_least_connections():

    with lock:

        # Find backend with minimum active connections
        idx = active.index(min(active))

        # Increment BEFORE dispatching
        active[idx] += 1

        print(
            f"[LB] Routing -> {BACKENDS[idx]} "
            f"(active connections now: {active})"
        )

        return idx


def release(idx):

    with lock:

        active[idx] -= 1

        print(
            f"[LB] Released {BACKENDS[idx]} "
            f"(active connections now: {active})"
        )


def handle_request(req_id):

    idx = pick_least_connections()

    address = BACKENDS[idx]

    try:

        with grpc.insecure_channel(address) as channel:

            stub = service_pb2_grpc.WorkerServiceStub(
                channel
            )

            reply = stub.HandleRequest(
                service_pb2.WorkRequest(
                    request_id=req_id
                )
            )

            print(
                f"[LB] Request {req_id} "
                f"-> handled by {reply.handled_by}"
            )

    finally:

        # Always release the connection count
        release(idx)


def main():

    print(
        f"[LB] Load Balancer starting. "
        f"Backends: {BACKENDS}"
    )

    threads = []

    for req_id in range(1, NUM_REQUESTS + 1):

        t = threading.Thread(
            target=handle_request,
            args=(req_id,)
        )

        threads.append(t)

        t.start()

        # Small delay between incoming requests
        time.sleep(0.15)

    for t in threads:

        t.join()

    print("\n[LB] All requests processed.")

    print(
        f"[LB] Final active connection counts "
        f"(should all be 0): {active}"
    )


if __name__ == "__main__":
    main()