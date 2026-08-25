import sys
import time

import grpc

import heart_pb2
import heart_pb2_grpc


LOCK_MANAGER = "localhost:60100"

# Different delays make the deadlock scenario deterministic.
#
# Node 1:
#   Draft -> wait -> Submission
#
# Node 2:
#   Submission -> wait longer -> Draft
#
# This gives Node 1 enough time to acquire Draft before
# Node 2 asks for Draft.
NODE1_HOLD_TIME = 4
NODE2_HOLD_TIME = 8


# ============================================================
# ACQUIRE LOCK
# ============================================================

def acquire_lock(stub, resource, node_id, timestamp):

    print()
    print(
        f"Node-{node_id}: REQUEST '{resource}' "
        f"(timestamp={timestamp})"
    )

    try:

        response = stub.AcquireLock(
            heart_pb2.LockRequest(
                resource_id=resource,
                holder_id=node_id,
                timestamp=timestamp
            )
        )

    except grpc.RpcError as error:

        print(
            f"Node-{node_id}: ERROR requesting "
            f"'{resource}': {error}"
        )

        return False

    print(
        f"Node-{node_id}: '{resource}' -> "
        f"granted={response.granted} "
        f"({response.message})"
    )

    return response.granted


# ============================================================
# RELEASE LOCK
# ============================================================

def release_lock(stub, resource, node_id):

    print(
        f"Node-{node_id}: RELEASING '{resource}'"
    )

    try:

        response = stub.ReleaseLock(
            heart_pb2.LockRequest(
                resource_id=resource,
                holder_id=node_id,
                timestamp=0
            )
        )

        print(
            f"Node-{node_id}: "
            f"release result = {response.message}"
        )

    except grpc.RpcError as error:

        print(
            f"Node-{node_id}: ERROR releasing "
            f"'{resource}': {error}"
        )


# ============================================================
# WORKER
# ============================================================

def run_worker(
    node_id,
    role,
    first_resource,
    second_resource
):

    print()
    print("=" * 70)

    print(
        f"Node-{node_id} started"
    )

    print(
        f"Role: {role}"
    )

    print(
        f"Lock order: "
        f"{first_resource} -> {second_resource}"
    )

    print("=" * 70)


    # --------------------------------------------------------
    # Connect to Lock Manager
    # --------------------------------------------------------

    try:

        channel = grpc.insecure_channel(
            LOCK_MANAGER
        )

        grpc.channel_ready_future(
            channel
        ).result(timeout=5)

        stub = heart_pb2_grpc.LockServiceStub(
            channel
        )

    except grpc.FutureTimeoutError:

        print()
        print(
            "ERROR: Lock Manager is not running."
        )

        print(
            "Start it using:"
        )

        print(
            "python lock_manager.py"
        )

        return

    except grpc.RpcError as error:

        print(
            f"ERROR connecting to Lock Manager: {error}"
        )

        return


    # --------------------------------------------------------
    # Timestamp
    # --------------------------------------------------------

    timestamp = node_id

    held_resources = []


    # ========================================================
    # STEP 1: ACQUIRE FIRST RESOURCE
    # ========================================================

    first_granted = acquire_lock(
        stub,
        first_resource,
        node_id,
        timestamp
    )

    if not first_granted:

        print(
            f"Node-{node_id}: "
            f"Could not acquire '{first_resource}'."
        )

        channel.close()

        return


    # IMPORTANT:
    # Actually record the first lock.
    held_resources.append(
        first_resource
    )


    # ========================================================
    # STEP 2: HOLD FIRST RESOURCE
    # ========================================================

    if node_id == 1:

        hold_time = NODE1_HOLD_TIME

    else:

        hold_time = NODE2_HOLD_TIME


    print()
    print(
        f"Node-{node_id}: "
        f"Holding '{first_resource}' "
        f"for {hold_time} seconds..."
    )


    if node_id == 1:

        print(
            "Node-1: "
            "This gives Node-2 time to acquire "
            "'submission'."
        )

    else:

        print(
            "Node-2: "
            "Waiting longer before requesting "
            "'draft'."
        )


    time.sleep(
        hold_time
    )


    # ========================================================
    # STEP 3: ACQUIRE SECOND RESOURCE
    # ========================================================

    second_granted = acquire_lock(
        stub,
        second_resource,
        node_id,
        timestamp
    )


    # ========================================================
    # SECOND RESOURCE GRANTED
    # ========================================================

    if second_granted:

        # IMPORTANT:
        # Record the SECOND lock too.
        #
        # This fixes the bug from the previous version.
        held_resources.append(
            second_resource
        )

        print()
        print(
            f"Node-{node_id}: "
            f"ACQUIRED BOTH RESOURCES"
        )

        print(
            f"  1. {first_resource}"
        )

        print(
            f"  2. {second_resource}"
        )

        print()
        print(
            "#" * 70
        )

        print(
            f"Node-{node_id}: "
            f"ENTERED CRITICAL SECTION"
        )

        print(
            "Processing shared resource..."
        )

        print(
            "#" * 70
        )

        time.sleep(2)


    # ========================================================
    # SECOND RESOURCE DENIED
    # ========================================================

    else:

        print()
        print(
            "=" * 70
        )

        print(
            f"Node-{node_id}: "
            f"SECOND RESOURCE NOT GRANTED"
        )

        print(
            f"Node-{node_id}: "
            f"Releasing held resources..."
        )

        print(
            "=" * 70
        )


        # ----------------------------------------------------
        # Release every resource currently held
        # ----------------------------------------------------

        for resource in reversed(
            held_resources
        ):

            release_lock(
                stub,
                resource,
                node_id
            )


        held_resources.clear()


        # ----------------------------------------------------
        # Retry after deadlock resolution
        # ----------------------------------------------------

        print()

        print(
            f"Node-{node_id}: "
            f"Waiting before retry..."
        )

        time.sleep(1)


        print()
        print(
            "=" * 70
        )

        print(
            f"Node-{node_id}: "
            f"RETRYING"
        )

        print("=" * 70)


        # ----------------------------------------------------
        # Retry second resource first
        # ----------------------------------------------------

        retry_second = acquire_lock(
            stub,
            second_resource,
            node_id,
            timestamp + 1
        )


        if retry_second:

            held_resources.append(
                second_resource
            )


            # ------------------------------------------------
            # Retry first resource
            # ------------------------------------------------

            retry_first = acquire_lock(
                stub,
                first_resource,
                node_id,
                timestamp + 2
            )


            if retry_first:

                held_resources.append(
                    first_resource
                )

                print()
                print(
                    f"Node-{node_id}: "
                    f"Successfully acquired both "
                    f"resources after retry."
                )

                print(
                    "#" * 70
                )

                print(
                    f"Node-{node_id}: "
                    f"ENTERED CRITICAL SECTION"
                )

                print(
                    "Processing shared resource..."
                )

                print(
                    "#" * 70
                )

                time.sleep(2)

            else:

                print(
                    f"Node-{node_id}: "
                    f"Could not acquire "
                    f"'{first_resource}' on retry."
                )


    # ========================================================
    # RELEASE ALL RESOURCES
    # ========================================================

    print()

    for resource in reversed(
        held_resources
    ):

        release_lock(
            stub,
            resource,
            node_id
        )


    held_resources.clear()


    # ========================================================
    # FINISHED
    # ========================================================

    print()
    print(
        "=" * 70
    )

    print(
        f"Node-{node_id}: DONE"
    )

    print("=" * 70)


    channel.close()


# ============================================================
# MAIN
# ============================================================

def main():

    if len(sys.argv) != 3:

        print()
        print(
            "Usage:"
        )

        print(
            "python worker.py 1 autosave"
        )

        print(
            "python worker.py 2 submission"
        )

        return


    node_id = int(
        sys.argv[1]
    )

    role = sys.argv[2].lower()


    # ========================================================
    # NODE 1
    # AutoSave
    #
    # Draft -> Submission
    # ========================================================

    if node_id == 1 and role == "autosave":

        run_worker(
            node_id=1,
            role="AutoSave",
            first_resource="draft",
            second_resource="submission"
        )


    # ========================================================
    # NODE 2
    # Final Submission
    #
    # Submission -> Draft
    # ========================================================

    elif node_id == 2 and role == "submission":

        run_worker(
            node_id=2,
            role="Final Submission",
            first_resource="submission",
            second_resource="draft"
        )


    else:

        print()
        print(
            "Invalid command."
        )

        print()
        print(
            "Use:"
        )

        print(
            "python worker.py 1 autosave"
        )

        print(
            "python worker.py 2 submission"
        )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()