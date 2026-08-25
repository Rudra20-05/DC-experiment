import sys
import threading
import time
from concurrent import futures

import grpc

import heart_pb2
import heart_pb2_grpc


# ============================================================
# EXPERIMENT 5
# Distributed Deadlock Simulation and Resolution
# ============================================================

DETECT = (
    len(sys.argv) > 1
    and sys.argv[1].lower() == "detect"
)


class LockManager(
    heart_pb2_grpc.LockServiceServicer
):

    def __init__(self):

        self.mutex = threading.Lock()

        # Current owner of each resource
        self.locks = {
            "draft": None,
            "submission": None
        }

        # holder_id -> resource being waited for
        #
        # Example:
        # Node 1 -> submission
        # Node 2 -> draft
        #
        # This creates:
        #
        # Node 1 -> Node 2
        # Node 2 -> Node 1
        #
        # which is a deadlock cycle.
        self.wait_for = {}

        # Condition variables for resources
        self.conditions = {
            "draft": threading.Condition(),
            "submission": threading.Condition()
        }


    # ========================================================
    # WAIT-FOR GRAPH CYCLE DETECTION
    # ========================================================

    def _would_cycle(self, holder, resource):

        """
        Check whether making 'holder' wait for 'resource'
        would create a cycle in the wait-for graph.
        """

        visited = set()

        current_resource = resource

        while True:

            owner = self.locks.get(current_resource)

            # Resource is free
            if owner is None:
                return False

            # Owner is the same requester
            # => cycle detected
            if owner == holder:
                return True

            # Already visited this owner
            if owner in visited:
                return False

            visited.add(owner)

            # Find what this owner is waiting for
            current_resource = self.wait_for.get(owner)

            if current_resource is None:
                return False


    # ========================================================
    # ACQUIRE LOCK
    # ========================================================

    def AcquireLock(
        self,
        request,
        context
    ):

        resource = request.resource_id
        holder = request.holder_id
        timestamp = request.timestamp

        if resource not in self.locks:

            return heart_pb2.LockReply(
                granted=False,
                message="unknown-resource"
            )

        cond = self.conditions[resource]


        with cond:

            with self.mutex:

                owner = self.locks.get(resource)


                # ------------------------------------------------
                # RESOURCE IS FREE
                # ------------------------------------------------

                if owner is None:

                    self.locks[resource] = holder

                    self.wait_for.pop(
                        holder,
                        None
                    )

                    print(
                        f"[LockManager] "
                        f"Node-{holder} ACQUIRED "
                        f"'{resource}'"
                    )

                    return heart_pb2.LockReply(
                        granted=True,
                        message="granted"
                    )


                # ------------------------------------------------
                # RESOURCE ALREADY HELD
                # ------------------------------------------------

                if owner == holder:

                    return heart_pb2.LockReply(
                        granted=True,
                        message="already-held"
                    )


                # ------------------------------------------------
                # DEADLOCK DETECTION
                # ------------------------------------------------

                if DETECT and self._would_cycle(
                    holder,
                    resource
                ):

                    print()
                    print(
                        "=" * 70
                    )

                    print(
                        "[LockManager] DEADLOCK DETECTED!"
                    )

                    print(
                        f"[LockManager] "
                        f"Node-{holder} -> '{resource}' "
                        f"(held by Node-{owner}) "
                        f"would close a cycle."
                    )

                    print(
                        f"[LockManager] "
                        f"ABORTING Node-{holder}"
                    )

                    print(
                        "=" * 70
                    )

                    return heart_pb2.LockReply(
                        granted=False,
                        message="deadlock-abort"
                    )


                # ------------------------------------------------
                # WAIT
                # ------------------------------------------------

                self.wait_for[holder] = resource

                print(
                    f"[LockManager] "
                    f"Node-{holder} WAITING for "
                    f"'{resource}' "
                    f"(held by Node-{owner})"
                )


            # ----------------------------------------------------
            # WAIT UNTIL RESOURCE BECOMES AVAILABLE
            # ----------------------------------------------------

            while True:

                with self.mutex:

                    owner = self.locks.get(resource)

                    if owner is None:

                        self.locks[resource] = holder

                        self.wait_for.pop(
                            holder,
                            None
                        )

                        print(
                            f"[LockManager] "
                            f"Node-{holder} ACQUIRED "
                            f"'{resource}' "
                            f"after waiting"
                        )

                        return heart_pb2.LockReply(
                            granted=True,
                            message="granted-after-wait"
                        )

                cond.wait(
                    timeout=1
                )


    # ========================================================
    # RELEASE LOCK
    # ========================================================

    def ReleaseLock(
        self,
        request,
        context
    ):

        resource = request.resource_id
        holder = request.holder_id

        if resource not in self.locks:

            return heart_pb2.LockReply(
                granted=False,
                message="unknown-resource"
            )

        cond = self.conditions[resource]


        with cond:

            with self.mutex:

                if self.locks.get(resource) == holder:

                    self.locks[resource] = None

                    print(
                        f"[LockManager] "
                        f"Node-{holder} RELEASED "
                        f"'{resource}'"
                    )

                    cond.notify_all()

                    return heart_pb2.LockReply(
                        granted=True,
                        message="released"
                    )

                else:

                    return heart_pb2.LockReply(
                        granted=False,
                        message="not-owner"
                    )


# ============================================================
# START LOCK MANAGER
# ============================================================

def serve():

    server = grpc.server(
        futures.ThreadPoolExecutor(
            max_workers=10
        )
    )

    heart_pb2_grpc.add_LockServiceServicer_to_server(
        LockManager(),
        server
    )

    server.add_insecure_port(
        "localhost:60100"
    )

    server.start()

    print()
    print(
        "=" * 70
    )

    print(
        "LockManager started on localhost:60100"
    )

    print(
        f"Deadlock detection = {DETECT}"
    )

    print(
        "=" * 70
    )

    try:

        while True:

            time.sleep(86400)

    except KeyboardInterrupt:

        print()
        print(
            "LockManager shutting down..."
        )

        server.stop(0)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    serve()