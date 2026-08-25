from flask import Flask, request, jsonify
from flask_cors import CORS
import numpy as np
import joblib
from tensorflow.keras.models import load_model

app = Flask(__name__)
CORS(app)

# Load once
model = load_model("model.h5")
scaler = joblib.load("scaler.pkl")

@app.route("/")
def home():
    return "API Running"

@app.route("/predict", methods=["POST"])
def predict_api():
    data = request.json["features"]

    data = np.array(data).reshape(1, -1)
    raw_features = data.copy()[0]  # Keep raw values for health tips
    data = scaler.transform(data)

    prob = model.predict(data)[0][0]

    # Sigmoid output = P(no disease).  prob > 0.7 → healthy
    result = 1 if prob > 0.7 else 0

    # Confidence = how sure the model is about its OWN prediction
    #   No disease predicted  → confidence = prob        (e.g. 0.85 → 85%)
    #   Disease predicted     → confidence = 1 - prob    (e.g. 0.02 → 98%)
    if result == 1:
        confidence = round(float(prob) * 100, 2)
    else:
        confidence = round((1 - float(prob)) * 100, 2)

    # Risk level based on the prediction direction
    if result == 1:
        risk_level = "Low"       # Model says no disease
    elif confidence >= 80:
        risk_level = "High"      # Model is very sure about disease
    else:
        risk_level = "Medium"    # Model leans toward disease but isn't highly certain

    # Generate health tips based on input values
    tips = []
    age = raw_features[0]
    bp = raw_features[3]
    chol = raw_features[4]
    fbs = raw_features[5]
    max_hr = raw_features[7]
    exercise_angina = raw_features[8]

    if bp > 130:
        tips.append("Your blood pressure is elevated. Consider reducing salt intake and regular monitoring.")
    if chol > 240:
        tips.append("Cholesterol is high. A diet low in saturated fats and regular exercise can help.")
    elif chol > 200:
        tips.append("Cholesterol is borderline high. Maintain a heart-healthy diet.")
    if fbs == 1:
        tips.append("Fasting blood sugar is elevated. Monitor glucose levels and consult a doctor.")
    if max_hr < 120 and age < 60:
        tips.append("Your max heart rate is below expected for your age. Consider cardio exercises.")
    if exercise_angina == 1:
        tips.append("Exercise-induced chest pain detected. Avoid strenuous activity and consult a cardiologist.")
    if age > 55:
        tips.append("Regular cardiac check-ups are recommended for individuals above 55.")

    # Always add general tips
    if result == 0:
        tips.append("Please consult a cardiologist for a thorough examination.")
        tips.append("Maintain a healthy lifestyle with regular exercise and balanced diet.")
    else:
        tips.append("Great results! Continue maintaining a healthy lifestyle.")
        tips.append("Regular check-ups are still recommended for preventive care.")

    return jsonify({
        "result": result,
        "probability": confidence,
        "message": "No Disease Detected" if result == 1 else "Heart Disease Detected please consult with Doctor",
        "risk_level": risk_level,
        "tips": tips
    })

@app.route("/model-info", methods=["GET"])
def model_info():
    """Return ANN model architecture details"""
    return jsonify({
        "model_type": "Sequential ANN",
        "input_features": 13,
        "layers": [
            {"type": "Dense", "units": 32, "activation": "relu", "regularizer": "L2(0.01)"},
            {"type": "Dropout", "rate": 0.3},
            {"type": "Dense", "units": 16, "activation": "relu", "regularizer": "L2(0.01)"},
            {"type": "Dropout", "rate": 0.2},
            {"type": "Dense", "units": 1, "activation": "sigmoid"}
        ],
        "optimizer": "Adam",
        "loss": "binary_crossentropy",
        "early_stopping_patience": 10,
        "dataset": "Cleveland Heart Disease (1026 samples)"
    })

if __name__ == "__main__":
    app.run(debug=True)