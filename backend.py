from flask import Flask, request, jsonify
import joblib
import os
import numpy as np
import pandas as pd
from datetime import datetime
import socket
import signal
import sys
import threading
import time

app = Flask(__name__)

# Global variables to store model and metadata
current_model = None
feature_names = None
last_training_time = None


def load_model():
    global current_model, feature_names, last_training_time
    try:
        model_path = '/shared-volume/model.joblib' 
        if os.path.exists(model_path):
            model_info = joblib.load(model_path)
            current_model = model_info['model']
            feature_names = model_info['feature_names']
            last_training_time = model_info['training_time']
            print(f"Model loaded successfully from {model_path} last trained at {last_training_time}")
        else:
            print("No model file found")
    except Exception as e:
        print(f"Error loading model: {e}")
     

@app.route('/model-info')
def get_model_info():
    if current_model is None:
        return jsonify({"status": "No model loaded"}), 503
    
    return jsonify({
        "status": "active",
        "last_training_time": last_training_time,
        "features": feature_names,
        "model_type": type(current_model).__name__,
        "host": socket.gethostname()
    })


@app.route('/predict', methods=['POST'])
def predict_engagement():
    if current_model is None:
        return jsonify({"error": "No model loaded"}), 503
    
    try:
        # Get user features from request
        user_data = request.get_json()
        
        # Validate all required features are present
        if not all(feature in user_data for feature in feature_names):
            return jsonify({
                "error": "Missing features",
                "required_features": feature_names
            }), 400
        
        # Create feature vector
        features = pd.DataFrame([user_data])[feature_names]
        
        # TODO: implement prediction of engagement_score using the current_model
        engagement_score = float(current_model.predict(features)[0])

        return jsonify({
            "engagement_score": engagement_score,
            "features_used": user_data,
            "model_training_time": last_training_time,
            "host": socket.gethostname()
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400

def _handle_sigusr1(signum, frame):
    host = socket.gethostname()
    print(
        f"preStop signal received (SIGUSR1). Host preparing for shutdown: {host}. "
        f"Last model training time: {last_training_time}",
        flush=True,
    )

def _handle_sigterm(signum, frame):
    try:
        host = socket.gethostname()
        print(f"SIGTERM received. Host being terminated: {host}. Last model training time: {last_training_time}")
    except Exception as err:
        print(f"SIGTERM handler error: {err}")
    finally:
        sys.exit(0)

signal.signal(signal.SIGUSR1, _handle_sigusr1)
signal.signal(signal.SIGTERM, _handle_sigterm)


def _periodic_model_reloader(interval_seconds=30):
    while True:
        try:
            load_model()
        except Exception as e:
            print(f"Error reloading model: {e}")
        time.sleep(interval_seconds)

_reloader_thread = threading.Thread(target=_periodic_model_reloader, args=(30,), daemon=True)
_reloader_thread.start()

if __name__ == '__main__':
    load_model()  # Load model at startup
    app.run(host='0.0.0.0', port=5001)    