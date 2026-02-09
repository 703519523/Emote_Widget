__version__ = "0.0.2-Refactored"

DEFAULT_CONFIG = {
    "animation": {
        "initialization_name": "初期化",
        "reset_duration_ms": 300,
        "reset_default_color": "#808080FF"
    },
    "lip_sync": {
        "update_fps": 30,
        "mean_decay_time_s": 0.8,
        "peak_decay_time_s": 0.15,
        "activation_ratio": 0.3,
        "mouth_ratio_curve": 0.35,
        "mouth_ratio_oversaturation": 1.1,
        "close_mouth_duration_ms": 200,
        "set_variable_duration_ms": 5,
    },
    "file_streaming": {
        "blocksize_hz": 30,
    }
}