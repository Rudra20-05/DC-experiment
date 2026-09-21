import json
import sys
import grpc
import redis

import heart_pb2
import heart_pb2_grpc


# ============================================================
# CONFIGURATION
# ============================================================

REDIS_HOST = "localhost"
REDIS_PORT = 6379

CACHE_TTL_SECONDS = 10

# Your existing heart-disease gRPC server
BACKEND_SERVICE_ADDR = "localhost:50051"

FRESH_KEY_PREFIX = "heart:fresh:"
STALE_KEY_PREFIX = "heart:stale:"


# ============================================================
# REDIS CONNECTION
# ============================================================

def get_redis():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        socket_connect_timeout=1,
        socket_timeout=1,
        decode_responses=True
    )


# ============================================================
# BACKEND REQUEST
# ============================================================

def fetch_from_backend(features, lamport_time=1):

    with grpc.insecure_channel(BACKEND_SERVICE_ADDR) as channel:

        stub = heart_pb2_grpc.HeartPredictionServiceStub(channel)

        request = heart_pb2.HeartRequest(
            features=features,
            lamport_time=lamport_time
        )

        response = stub.PredictHeartDisease(
            request,
            timeout=3
        )

        return {
            "result": response.result,
            "probability": response.probability,
            "message": response.message,
            "risk_level": response.risk_level,
            "tips": list(response.tips),
            "lamport_time": response.lamport_time
        }


# ============================================================
# CACHE-ASIDE REQUEST
# ============================================================

def get_prediction(features):

    # Create a stable cache key from the input features
    feature_key = ",".join(str(x) for x in features)

    fresh_key = FRESH_KEY_PREFIX + feature_key
    stale_key = STALE_KEY_PREFIX + feature_key

    redis_client = None

    # --------------------------------------------------------
    # STEP 1: Try Redis
    # --------------------------------------------------------

    try:

        redis_client = get_redis()

        cached = redis_client.get(fresh_key)

        if cached:

            print(
                "[Gateway] CACHE HIT - "
                "prediction served from Redis"
            )

            return json.loads(cached), "cache-hit"

        print(
            "[Gateway] CACHE MISS - "
            "requesting prediction from backend"
        )

    except redis.exceptions.RedisError as e:

        print(
            f"[Gateway] REDIS UNAVAILABLE: {e}"
        )

        print(
            "[Gateway] Falling back to backend"
        )

        redis_client = None

    # --------------------------------------------------------
    # STEP 2: Request backend
    # --------------------------------------------------------

    try:

        data = fetch_from_backend(features)

        print(
            "[Gateway] Prediction received from BACKEND"
        )

        # ----------------------------------------------------
        # Store in Redis
        # ----------------------------------------------------

        if redis_client is not None:

            try:

                # Fresh cache with TTL
                redis_client.set(
                    fresh_key,
                    json.dumps(data),
                    ex=CACHE_TTL_SECONDS
                )

                # Permanent stale backup
                redis_client.set(
                    stale_key,
                    json.dumps(data)
                )

                print(
                    "[Gateway] Prediction stored in Redis"
                )

            except redis.exceptions.RedisError as e:

                print(
                    f"[Gateway] Redis write failed: {e}"
                )

        return data, "backend"

    # --------------------------------------------------------
    # STEP 3: Backend unavailable
    # --------------------------------------------------------

    except grpc.RpcError as e:

        print(
            f"[Gateway] BACKEND UNAVAILABLE: {e.code()}"
        )

        # ----------------------------------------------------
        # Try stale cache
        # ----------------------------------------------------

        if redis_client is not None:

            try:

                stale = redis_client.get(stale_key)

                if stale:

                    print(
                        "[Gateway] Serving STALE "
                        "cached prediction"
                    )

                    return (
                        json.loads(stale),
                        "stale-fallback"
                    )

            except redis.exceptions.RedisError:
                pass

        raise RuntimeError(
            "Backend unavailable and no stale "
            "cache is available."
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("=" * 65)
    print("REDIS CACHE GATEWAY - HEART DISEASE PREDICTION")
    print("=" * 65)

    # --------------------------------------------------------
    # Example heart-disease feature vector
    #
    # IMPORTANT:
    # Replace these values with the same feature format
    # expected by your existing heart prediction server.
    # --------------------------------------------------------

    features = [
        63.0,
        1.0,
        3.0,
        145.0,
        233.0,
        1.0,
        0.0,
        150.0,
        0.0,
        2.3,
        0.0,
        0.0,
        1.0
    ]

    print()
    print("Requesting heart-disease prediction...")
    print()

    try:

        data, source = get_prediction(features)

        print()
        print("=" * 65)
        print(f"RESULT SOURCE: {source}")
        print("=" * 65)

        print(f"Prediction Result : {data['result']}")
        print(f"Probability       : {data['probability']}")
        print(f"Risk Level        : {data['risk_level']}")
        print(f"Message           : {data['message']}")
        print(f"Lamport Timestamp : {data['lamport_time']}")

        if data["tips"]:
            print("Tips:")
            for tip in data["tips"]:
                print(f"  - {tip}")

        print("=" * 65)

    except Exception as e:

        print()
        print("=" * 65)
        print("REQUEST FAILED")
        print("=" * 65)
        print(e)
        print("=" * 65)