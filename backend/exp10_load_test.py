
import concurrent.futures
import time
import grpc

import heart_pb2
import heart_pb2_grpc

TARGET_ADDR = "localhost:50051"
NUM_REQUESTS = 20
MAX_WORKERS = 5

FEATURES = [
    52, 1, 0, 125, 212, 0, 1,
    168, 0, 1.0, 2, 2, 3
]


def send_request(request_id):
    start = time.time()

    try:
        with grpc.insecure_channel(TARGET_ADDR) as channel:
            stub = heart_pb2_grpc.HeartPredictionServiceStub(channel)

            response = stub.PredictHeartDisease(
                heart_pb2.HeartRequest(
                    features=FEATURES,
                    lamport_time=request_id
                ),
                timeout=30
            )

        elapsed = time.time() - start

        return (
            request_id,
            True,
            response.message,
            response.lamport_time,
            elapsed,
            ""
        )

    except Exception as exc:
        return (request_id, False, "", 0, time.time() - start, str(exc))


def main():
    print(f"Target: {TARGET_ADDR}")
    print(f"Requests: {NUM_REQUESTS}")
    print(f"Concurrent workers: {MAX_WORKERS}\n")

    start = time.time()

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:
        results = list(executor.map(
            send_request, range(1, NUM_REQUESTS + 1)
        ))

    total_time = time.time() - start
    successful = sum(1 for result in results if result[1])
    failed = NUM_REQUESTS - successful

    for req_id, ok, message, lamport, elapsed, error in results:
        if ok:
            print(
                f"Request {req_id}: SUCCESS | "
                f"{message} | Server Lamport: {lamport} | "
                f"{elapsed:.2f}s"
            )
        else:
            print(f"Request {req_id}: FAILED | {error}")

    print("\n========== LOAD TEST SUMMARY ==========")
    print(f"Total requests : {NUM_REQUESTS}")
    print(f"Successful     : {successful}")
    print(f"Failed         : {failed}")
    print(f"Total time     : {total_time:.2f}s")
    print(
        f"Throughput     : "
        f"{successful / total_time:.2f} successful requests/sec"
        if total_time > 0 else "Throughput     : N/A"
    )


if __name__ == "__main__":
    main()
