import grpc
from concurrent import futures
import numpy as np
import joblib
from tensorflow.keras.models import load_model

import heart_pb2
import heart_pb2_grpc

from lamport_clock import LamportClock

# Load model once
model = load_model("model.h5")
scaler = joblib.load("scaler.pkl")

# Lamport Clock
clock = LamportClock()


class HeartPredictionService(heart_pb2_grpc.HeartPredictionServiceServicer):

    def PredictHeartDisease(self, request, context):

        # Update Lamport Clock
        clock.update(request.lamport_time)

        print("\n==============================")
        print("Request Received")
        print("Client Lamport Time :", request.lamport_time)
        print("Server Lamport Time :", clock.get_time())
        print("==============================")

        data = np.array(request.features).reshape(1, -1)

        raw_features = data.copy()[0]

        data = scaler.transform(data)

        prob = model.predict(data, verbose=0)[0][0]

        result = 1 if prob > 0.7 else 0

        if result == 1:
            confidence = round(float(prob) * 100, 2)
        else:
            confidence = round((1 - float(prob)) * 100, 2)

        if result == 1:
            risk = "Low"
        elif confidence >= 80:
            risk = "High"
        else:
            risk = "Medium"

        tips = []

        age = raw_features[0]
        bp = raw_features[3]
        chol = raw_features[4]
        fbs = raw_features[5]
        max_hr = raw_features[7]
        exercise_angina = raw_features[8]

        if bp > 130:
            tips.append("Reduce salt intake.")

        if chol > 240:
            tips.append("High cholesterol.")
        elif chol > 200:
            tips.append("Borderline cholesterol.")

        if fbs == 1:
            tips.append("Monitor blood sugar.")

        if max_hr < 120 and age < 60:
            tips.append("Increase cardio exercise.")

        if exercise_angina == 1:
            tips.append("Consult cardiologist.")

        if age > 55:
            tips.append("Regular cardiac checkups.")

        if result == 0:
            tips.append("Please consult a doctor.")
        else:
            tips.append("Maintain healthy lifestyle.")

        # Increment before sending response
        clock.tick()

        return heart_pb2.HeartResponse(
            result=result,
            probability=confidence,
            message="No Disease Detected" if result == 1 else "Heart Disease Detected",
            risk_level=risk,
            tips=tips,
            lamport_time=clock.get_time()
        )


def serve():

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    heart_pb2_grpc.add_HeartPredictionServiceServicer_to_server(
        HeartPredictionService(),
        server
    )

    server.add_insecure_port("[::]:50051")

    server.start()

    print("✅ gRPC Server Running on Port 50051")

    server.wait_for_termination()


if __name__ == "__main__":
    serve()