import time
import threading
import grpc

import replica_pb2
import replica_pb2_grpc


REPLICAS = {
    "A": "localhost:60301",
    "B": "localhost:60302",
    "C": "localhost:60303"
}


def save(replica_name, key, content):

    with grpc.insecure_channel(
        REPLICAS[replica_name]
    ) as channel:

        stub = replica_pb2_grpc.ReplicaServiceStub(
            channel
        )

        ack = stub.SaveValue(
            replica_pb2.ValueUpdate(
                key=key,
                content=content,
                lamport_timestamp=0,
                origin_replica=""
            )
        )

        print(
            f"[CLIENT] Saved on Replica-{replica_name}: "
            f"'{content}'"
        )

        print(
            f"[CLIENT] accepted={ack.accepted}, "
            f"timestamp={ack.lamport_timestamp}"
        )


def read(replica_name, key):

    with grpc.insecure_channel(
        REPLICAS[replica_name]
    ) as channel:

        stub = replica_pb2_grpc.ReplicaServiceStub(
            channel
        )

        state = stub.GetValue(
            replica_pb2.ValueQuery(
                key=key
            )
        )

        return (
            state.content,
            state.lamport_timestamp,
            state.origin_replica
        )


def main():

    key = "heart-disease-workflow"

    print("=" * 70)
    print("EVENTUAL CONSISTENCY DEMONSTRATION")
    print("=" * 70)

    print(
        "\nCreating two concurrent writers "
        "on different replicas...\n"
    )

    writer1 = threading.Thread(
        target=save,
        args=(
            "A",
            key,
            "Heart prediction updated by Writer-1"
        )
    )

    writer2 = threading.Thread(
        target=save,
        args=(
            "C",
            key,
            "Heart prediction updated by Writer-2"
        )
    )

    writer1.start()

    time.sleep(0.05)

    writer2.start()

    writer1.join()
    writer2.join()

    print("\n" + "=" * 70)
    print("STATE IMMEDIATELY AFTER WRITES")
    print("=" * 70)

    for name in REPLICAS:

        try:

            content, timestamp, origin = read(
                name,
                key
            )

            print(
                f"Replica-{name}: "
                f"'{content}' "
                f"(ts={timestamp}, origin={origin})"
            )

        except grpc.RpcError as error:

            print(
                f"Replica-{name}: unavailable "
                f"({error.code()})"
            )

    print("\nWaiting 2 seconds for gossip...\n")

    time.sleep(2)

    print("=" * 70)
    print("STATE AFTER CONVERGENCE")
    print("=" * 70)

    results = {}

    for name in REPLICAS:

        try:

            content, timestamp, origin = read(
                name,
                key
            )

            results[name] = content

            print(
                f"Replica-{name}: "
                f"'{content}' "
                f"(ts={timestamp}, origin={origin})"
            )

        except grpc.RpcError as error:

            print(
                f"Replica-{name}: unavailable "
                f"({error.code()})"
            )

    if len(set(results.values())) == 1:

        final_value = list(
            results.values()
        )[0]

        print("\n" + "=" * 70)
        print("CONVERGED SUCCESSFULLY")
        print("=" * 70)

        print(
            f"All replicas agree on:\n'{final_value}'"
        )

    else:

        print("\nNOT YET CONVERGED")

        print(
            "Replica values:",
            results
        )


if __name__ == "__main__":
    main()