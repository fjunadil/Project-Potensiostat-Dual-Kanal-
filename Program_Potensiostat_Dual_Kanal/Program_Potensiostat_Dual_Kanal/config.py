from pathlib import Path


RODEOSTAT_PORT = "/dev/ttyACM0"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"

MUX_PINS = {
    "s0": 5,
}

MUX_CHANNELS = (1, 2)
MUX_ADDRESS_BY_CHANNEL = {
    1: 0,
    2: 1,
}

DEFAULT_CV_PARAMETERS = {
    "currentRange": "1000 uA",
    "sampleRate": 50,
    "quietTime": 0,
    "quietValue": -0.5,
    "startValue": -0.5,
    "vertex1Value": 0.5,
    "vertex2Value": -0.5,
    "stepValue": 0.01,
    "scanRate": 0.02,
    "numCycles": 1,
}

METHOD_DEFINITIONS = {
    "cv": {
        "label": "CV - Cyclic Voltammetry",
        "title": "Cyclic Voltammetry",
        "test_name": "cyclic",
        "prefix": "cv",
        "parameters": DEFAULT_CV_PARAMETERS,
    },
}

METHOD_LABELS = {key: definition["label"] for key, definition in METHOD_DEFINITIONS.items()}
DEFAULT_METHOD_PARAMETERS = {key: definition["parameters"] for key, definition in METHOD_DEFINITIONS.items()}

DEFAULT_STABILIZATION_SECONDS = 3.0
