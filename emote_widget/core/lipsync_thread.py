# emote_widget/core/lipsync.py
import queue
import numpy as np
from typing import Union
from numpy.typing import NDArray
from PySide6.QtCore import QThread, Signal
from emote_widget.utils.logger import emote_widget_logger as logger

FloatArray = NDArray[np.float32]

class StreamLipSyncThread(QThread):
    """
    使用指数移动平均(EMA)追踪音频能量，实现口型同步计算。
    只负责计算 '开合度 (0.0~1.0)'，不负责具体操作模型。
    """
    mouth_open_ratio_updated = Signal(float)
    debug_data_updated = Signal(dict)

    def __init__(self, audio_queue: queue.Queue[Union[FloatArray, None]], 
                 mean_decay_time: float = 0.8, peak_decay_time: float = 0.15, 
                 update_fps: int = 30, activation_ratio: float = 0.3) -> None:
        super().__init__()
        self.audio_queue = audio_queue
        self.is_running = False
        
        if update_fps <= 0: update_fps = 1
        
        # 计算 EMA 平滑因子
        self.mean_smoothing = np.exp(-1 / (mean_decay_time * update_fps))
        self.peak_smoothing = np.exp(-1 / (peak_decay_time * update_fps))
        
        self.mean_rms = 0.0
        self.peak_rms = 0.0
        self.activation_ratio = activation_ratio

    def run(self) -> None:
        self.is_running = True
        logger.info("LipSyncThread 启动")
        
        while self.is_running:
            try:
                audio_chunk = self.audio_queue.get(timeout=1)
                if audio_chunk is None: break # 停止信号

                if audio_chunk.size == 0: continue
                
                current_rms = float(np.sqrt(np.mean(audio_chunk**2)))
                
                # 更新基线(Mean)和峰值(Peak)
                self.mean_rms = self.mean_rms * self.mean_smoothing + current_rms * (1 - self.mean_smoothing)
                self.peak_rms = max(current_rms, self.peak_rms * self.peak_smoothing)
                
                dynamic_range = self.peak_rms - self.mean_rms
                activation_threshold = self.mean_rms + self.activation_ratio * dynamic_range
                
                mouth_open_ratio = 0.0
                if current_rms > activation_threshold and dynamic_range > 0.001:
                    effective_range = self.peak_rms - activation_threshold
                    mouth_open_ratio = (current_rms - activation_threshold) / (effective_range + 1e-6)
                    mouth_open_ratio = max(0.0, min(mouth_open_ratio, 1.0))
                
                # 发送信号
                self.debug_data_updated.emit({
                    "rms": current_rms, "mean": self.mean_rms,
                    "peak": self.peak_rms, "threshold": activation_threshold
                })
                self.mouth_open_ratio_updated.emit(mouth_open_ratio)

            except queue.Empty:
                # 超时衰减
                self.peak_rms *= self.peak_smoothing
                self.mouth_open_ratio_updated.emit(0.0)
                continue
            except Exception:
                logger.error("LipSync 异常:", exc_info=True)
                
        logger.info("LipSyncThread 停止")

    def stop(self) -> None:
        self.is_running = False
        self.audio_queue.put(None)
        self.wait()