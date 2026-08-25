import grpc

import heart_pb2
import heart_pb2_grpc

from lamport_clock import LamportClock

clock = LamportClock()

channel = grpc.insecure_channel("localhost:50051")

stub = heart_pb2_grpc.HeartPredictionServiceStub(channel)

features = [
    52,
    1,
    0,
    125,
    212,
    0,
    1,
    168,
    0,
    1.0,
    2,
    2,
    3
]

clock.tick()

print("Client Lamport Time :", clock.get_time())

response = stub.PredictHeartDisease(
    heart_pb2.HeartRequest(
        features=features,
        lamport_time=clock.get_time()
    )
)

clock.update(response.lamport_time)

print("\nPrediction :", response.message)
print("Confidence :", response.probability)
print("Risk Level :", response.risk_level)

print("\nHealth Tips:")

for tip in response.tips:
    print("-", tip)

print("\nUpdated Client Lamport Clock :", clock.get_time())