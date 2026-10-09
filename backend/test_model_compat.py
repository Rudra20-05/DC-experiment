
import json
import shutil
import h5py
import tensorflow as tf
from tensorflow.keras.models import load_model

source = "model.h5"
test_copy = "model_compat_test.h5"

# Keep the original model unchanged
shutil.copy2(source, test_copy)

# Remove unsupported quantization_config entries from the COPY
with h5py.File(test_copy, "r+") as f:
    config = json.loads(f.attrs["model_config"])

    def clean_config(obj):
        if isinstance(obj, dict):
            obj.pop("quantization_config", None)
            for value in obj.values():
                clean_config(value)
        elif isinstance(obj, list):
            for value in obj:
                clean_config(value)

    clean_config(config)

    del f.attrs["model_config"]
    f.attrs["model_config"] = json.dumps(config)

print("TensorFlow version:", tf.__version__)
print("Testing copied model...")

model = load_model(test_copy, compile=False)

print("MODEL LOADED SUCCESSFULLY")
