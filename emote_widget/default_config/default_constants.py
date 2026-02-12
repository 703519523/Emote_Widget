from typing import TypedDict

__version__ = "0.0.2-Refactored"

class SplashConfig(TypedDict):
    min_splash_duration_ms:int
    

class AnimationConfig(TypedDict):
    initialization_name: str
    reset_duration_ms: int
    reset_default_color: str

class LipSyncConfig(TypedDict):
    update_fps: int
    mean_decay_time_s: float
    peak_decay_time_s: float
    activation_ratio: float
    mouth_ratio_curve: float
    mouth_ratio_oversaturation: float
    close_mouth_duration_ms: int
    set_variable_duration_ms: int

class FileStreamingConfig(TypedDict):
    blocksize_hz: int

class Config(TypedDict):
    splash: SplashConfig
    animation: AnimationConfig
    lip_sync: LipSyncConfig
    file_streaming: FileStreamingConfig

DEFAULT_CONFIG: Config = {
    "splash": {
        "min_splash_duration_ms":1000
    },
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