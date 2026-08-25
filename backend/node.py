import sys
import time
import threading
from concurrent import futures

import grpc

import heart_pb2
import heart_pb2_grpc


# ============================================================
# CONFIGURATION
# ============================================================

PEERS = {
    1: "localhost:60051",
    2: "localhost:60052",
    3: "localhost:60053"
}

DEFAULT_WORK_SECONDS = 20


# ============================================================
# NODE
# ============================================================

class Node:

    def __init__(self, node_id, work_seconds=DEFAULT_WORK_SECONDS):

        self.node_id = node_id
        self.work_seconds = work_seconds

        # Lamport clock
        self.clock = 0

        # Node state:
        # RELEASED -> WANTED -> HELD -> RELEASED
        self.state = "RELEASED"

        # Timestamp of our current request
        self.request_timestamp = None

        # Number of permissions received
        self.reply_count = 0

        # Deferred requests
        #
        # Format:
        # [
        #     (event, node_id, timestamp)
        # ]
        self.deferred_requests = []

        self.lock = threading.Lock()


    # ========================================================
    # LAMPORT CLOCK
    # ========================================================

    def tick(self):

        with self.lock:
            self.clock += 1
            return self.clock


    def update_clock(self, received_timestamp):

        with self.lock:
            self.clock = max(
                self.clock,
                received_timestamp
            ) + 1

            return self.clock


    # ========================================================
    # START GRPC SERVER
    # ========================================================

    def start_server(self):

        server = grpc.server(
            futures.ThreadPoolExecutor(
                max_workers=20
            )
        )

        heart_pb2_grpc.add_MutexServiceServicer_to_server(
            MutexService(self),
            server
        )

        address = PEERS[self.node_id]

        port = server.add_insecure_port(address)

        if port == 0:

            print(
                f"ERROR: Could not start Node-{self.node_id} "
                f"on {address}"
            )

            return None


        server.start()

        print()
        print("=" * 65)
        print(
            f"Node-{self.node_id} started; "
            f"listening on {address}"
        )
        print("=" * 65)

        print()
        print(
            f"Node-{self.node_id}: Server is ready."
        )

        return server


    # ========================================================
    # CONNECT TO PEER
    # ========================================================

    def send_request(
        self,
        peer_id,
        address,
        timestamp
    ):

        print(
            f"Node-{self.node_id}: "
            f"connecting to Node-{peer_id}..."
        )

        try:

            channel = grpc.insecure_channel(address)

            grpc.channel_ready_future(
                channel
            ).result(timeout=5)

            stub = heart_pb2_grpc.MutexServiceStub(
                channel
            )

            print(
                f"Node-{self.node_id} -> "
                f"Node-{peer_id}: "
                f"REQUEST (timestamp={timestamp})"
            )

            response = stub.RequestAccess(
                heart_pb2.AccessRequest(
                    node_id=self.node_id,
                    timestamp=timestamp
                ),
                timeout=60
            )

            self.update_clock(
                response.timestamp
            )

            print(
                f"Node-{self.node_id}: "
                f"permission from Node-{peer_id}"
            )

            channel.close()

            return True


        except grpc.FutureTimeoutError:

            print(
                f"ERROR: Node-{self.node_id} "
                f"could not connect to Node-{peer_id} "
                f"at {address}"
            )

            return False


        except grpc.RpcError as error:

            print(
                f"ERROR: RPC Node-{self.node_id} -> "
                f"Node-{peer_id} failed: "
                f"{error.code()}"
            )

            return False


    # ========================================================
    # REQUEST CRITICAL SECTION
    # ========================================================

    def request_critical_section(self):

        # ----------------------------------------------------
        # Create our request timestamp
        # ----------------------------------------------------

        timestamp = self.tick()

        with self.lock:

            self.state = "WANTED"

            self.request_timestamp = timestamp

            self.reply_count = 0


        print()
        print("=" * 65)

        print(
            f"Node-{self.node_id} WANTS "
            f"critical section "
            f"(timestamp {timestamp})"
        )

        print("=" * 65)


        # ----------------------------------------------------
        # Send request to all other nodes
        # ----------------------------------------------------

        peer_results = []

        with futures.ThreadPoolExecutor(
            max_workers=2
        ) as executor:

            tasks = []

            for peer_id, address in PEERS.items():

                if peer_id == self.node_id:
                    continue

                task = executor.submit(
                    self.send_request,
                    peer_id,
                    address,
                    timestamp
                )

                tasks.append(task)


            for task in tasks:

                result = task.result()

                peer_results.append(result)


        # ----------------------------------------------------
        # Check whether all permissions were received
        # ----------------------------------------------------

        if not all(peer_results):

            print()
            print(
                f"Node-{self.node_id}: "
                f"Could not get permission from all peers."
            )

            with self.lock:

                self.state = "RELEASED"

                self.request_timestamp = None

            return


        # ----------------------------------------------------
        # ENTER CRITICAL SECTION
        # ----------------------------------------------------

        with self.lock:

            self.state = "HELD"


        print()
        print()
        print("#" * 65)

        print(
            f"Node-{self.node_id}: "
            f"ENTERED critical section"
        )

        print("#" * 65)

        print(
            "Shared Resource:"
        )

        print(
            "Heart Disease Prediction Processing"
        )

        print(
            f"Lamport Clock: {self.clock}"
        )

        print(
            f"Permissions: {self.reply_count}/2"
        )

        print(
            f"Working for {self.work_seconds} seconds..."
        )

        print("#" * 65)


        # ----------------------------------------------------
        # SIMULATE CRITICAL SECTION
        # ----------------------------------------------------

        time.sleep(self.work_seconds)


        # ----------------------------------------------------
        # EXIT CRITICAL SECTION
        # ----------------------------------------------------

        self.release_critical_section()


    # ========================================================
    # RELEASE CRITICAL SECTION
    # ========================================================

    def release_critical_section(self):

        with self.lock:

            self.state = "RELEASED"

            deferred = list(
                self.deferred_requests
            )

            self.deferred_requests.clear()

            self.request_timestamp = None


        print()
        print("#" * 65)

        print(
            f"Node-{self.node_id}: "
            f"EXITED critical section"
        )

        print(
            f"Node-{self.node_id}: "
            f"released {len(deferred)} "
            f"deferred request(s)"
        )

        print("#" * 65)


        # ----------------------------------------------------
        # Release deferred requests
        # ----------------------------------------------------

        for event, requester_id, timestamp in deferred:

            print(
                f"Node-{self.node_id}: "
                f"releasing deferred request "
                f"from Node-{requester_id} "
                f"(timestamp={timestamp})"
            )

            event.set()


# ============================================================
# GRPC SERVICE
# ============================================================

class MutexService(
    heart_pb2_grpc.MutexServiceServicer
):

    def __init__(self, node):

        self.node = node


    # ========================================================
    # REQUEST ACCESS
    # ========================================================

    def RequestAccess(
        self,
        request,
        context
    ):

        node = self.node

        requester_id = request.node_id
        requester_timestamp = request.timestamp


        # ----------------------------------------------------
        # Update Lamport clock
        # ----------------------------------------------------

        node.update_clock(
            requester_timestamp
        )


        print()
        print(
            f"Node-{node.node_id}: "
            f"received request from "
            f"Node-{requester_id} "
            f"(timestamp {requester_timestamp})"
        )


        # ----------------------------------------------------
        # Determine priority
        #
        # Compare:
        #
        #     (Lamport timestamp, Node ID)
        #
        # Smaller pair has priority.
        # ----------------------------------------------------

        with node.lock:

            our_request = None

            if node.state == "WANTED":

                our_request = (
                    node.request_timestamp,
                    node.node_id
                )

            elif node.state == "HELD":

                our_request = (
                    node.request_timestamp
                    if node.request_timestamp is not None
                    else float("inf"),
                    node.node_id
                )


            incoming_request = (
                requester_timestamp,
                requester_id
            )


            # ------------------------------------------------
            # Decide whether to defer
            # ------------------------------------------------

            should_defer = False


            if node.state == "HELD":

                should_defer = True


            elif (
                node.state == "WANTED"
                and our_request is not None
                and our_request < incoming_request
            ):

                should_defer = True


        # ====================================================
        # DEFER REQUEST
        # ====================================================

        if should_defer:

            print(
                f"Node-{node.node_id}: "
                f"DEFERS Node-{requester_id}"
            )


            # Create an Event.
            #
            # The RPC will WAIT here.
            #
            # It will only continue when this node exits
            # its critical section and calls event.set().
            #

            event = threading.Event()


            with node.lock:

                node.deferred_requests.append(
                    (
                        event,
                        requester_id,
                        requester_timestamp
                    )
                )


            print(
                f"Node-{node.node_id}: "
                f"Node-{requester_id}'s permission "
                f"is waiting..."
            )


            # ------------------------------------------------
            # WAIT UNTIL CRITICAL SECTION IS RELEASED
            # ------------------------------------------------

            event.wait()


            # ------------------------------------------------
            # Deferred request is now released
            # ------------------------------------------------

            reply_timestamp = node.tick()


            print(
                f"Node-{node.node_id}: "
                f"GRANTS deferred request to "
                f"Node-{requester_id}"
            )


            return heart_pb2.AccessReply(
                node_id=node.node_id,
                timestamp=reply_timestamp
            )


        # ====================================================
        # IMMEDIATE GRANT
        # ====================================================

        reply_timestamp = node.tick()


        print(
            f"Node-{node.node_id}: "
            f"GRANTS Node-{requester_id}"
        )


        return heart_pb2.AccessReply(
            node_id=node.node_id,
            timestamp=reply_timestamp
        )


# ============================================================
# MAIN
# ============================================================

def main():

    if len(sys.argv) < 3:

        print()
        print(
            "Usage:"
        )

        print(
            "  python node.py 1 server"
        )

        print(
            "  python node.py 2 server"
        )

        print(
            "  python node.py 3 server"
        )

        print()

        print(
            "Request mode:"
        )

        print(
            "  python node.py 1 request"
        )

        print(
            "  python node.py 2 request"
        )

        print(
            "  python node.py 3 request"
        )

        return


    node_id = int(sys.argv[1])

    mode = sys.argv[2].lower()


    # --------------------------------------------------------
    # Validate node
    # --------------------------------------------------------

    if node_id not in PEERS:

        print(
            "ERROR: Node ID must be 1, 2, or 3."
        )

        return


    node = Node(
        node_id=node_id,
        work_seconds=DEFAULT_WORK_SECONDS
    )


    # ========================================================
    # SERVER MODE
    # ========================================================

    if mode == "server":

        server = node.start_server()

        if server is None:

            return


        try:

            while True:

                time.sleep(1)


        except KeyboardInterrupt:

            print()
            print(
                f"Node-{node_id}: "
                f"stopping server..."
            )

            server.stop(0)


    # ========================================================
    # REQUEST MODE
    # ========================================================

    elif mode == "request":

        print()
        print(
            f"Node-{node_id}: "
            f"Starting request immediately..."
        )

        node.request_critical_section()


    # ========================================================
    # INVALID MODE
    # ========================================================

    else:

        print(
            "ERROR: Invalid mode."
        )

        print(
            "Use 'server' or 'request'."
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()