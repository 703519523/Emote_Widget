"""
EmoteWidget 口型同步线程模块。

本模块实现了 `StreamLipSyncThread`，负责实时分析音频流的能量（RMS 振幅），
并计算出用于驱动模型嘴部的开合度参数 (Mouth Open Ratio)。

算法原理:
    采用 **指数移动平均 (Exponential Moving Average, EMA)** 算法来动态追踪音频的
    背景噪声 (Mean) 和峰值音量 (Peak)。
    通过动态计算阈值 `Threshold = Mean + (Peak - Mean) * ActivationRatio`，
    实现了对不同音量环境的自适应能力，无需手动校准麦克风增益。
"""

import queue
import numpy as np
from typing import Union, Optional
from numpy.typing import NDArray
from PySide6.QtCore import QThread, Signal
from emote_widget.utils.logger import emote_widget_logger as logger

FloatArray = NDArray[np.float32]

class StreamLipSyncThread(QThread):
    """
    [口型同步线程] 实时音频分析器。
    
    特性:
        - **自适应增益**: 自动适应音量变化，无论是窃窃私语还是大声喊叫，都能正确驱动嘴型。
        - **平滑过渡**: 输出的开合度经过平滑处理，避免嘴部动作过于抖动。
        - **线程安全**: 通过 `queue.Queue` 接收音频数据，通过 Qt 信号输出结果。
    """
    
    # 信号定义
    mouth_open_ratio_updated = Signal(float)
    """计算出的嘴部张开度 (0.0 ~ 1.0)。"""
    
    debug_data_updated = Signal(dict)
    """调试数据 (RMS, Mean, Peak, Threshold)，用于可视化。"""

    def __init__(self, audio_queue: queue.Queue[Union[FloatArray, None]], 
                 mean_decay_time: float = 0.8, peak_decay_time: float = 0.15, 
                 update_fps: int = 30, activation_ratio: float = 0.3) -> None:
        """
        初始化同步线程。

        Args:
            audio_queue (queue.Queue): 音频数据输入队列。放入 None 作为停止信号。
            mean_decay_time (float): 背景噪声均值的衰减时间（秒）。越长对噪声变化反应越慢。
            peak_decay_time (float): 峰值音量的衰减时间（秒）。越短嘴巴闭合越快。
            update_fps (int): 期望的更新帧率。影响 EMA 平滑系数的计算。
            activation_ratio (float): 激活阈值比例。
                                    0.0 = 只要有声音就张嘴; 
                                    1.0 = 只有达到峰值才张嘴。
        """
        super().__init__()
        self.audio_queue = audio_queue
        self.is_running = False
        
        if update_fps <= 0: update_fps = 1
        
        # 计算 EMA 平滑因子 (Alpha, Beta)
        # Formula: decay = exp(-1 / (time * fps))
        self.mean_smoothing = np.exp(-1 / (mean_decay_time * update_fps))
        self.peak_smoothing = np.exp(-1 / (peak_decay_time * update_fps))
        
        self.mean_rms = 0.0 # 当前估算的背景底噪
        self.peak_rms = 0.0 # 当前估算的音量峰值
        self.activation_ratio = activation_ratio

    def run(self) -> None:
        """[Override] 线程主循环。"""
        self.is_running = True
        logger.info("LipSyncThread 启动")
        
        while self.is_running:
            try:
                # 阻塞式获取音频帧，超时 1秒 以便检查 is_running 标志
                audio_chunk: Optional[FloatArray] = self.audio_queue.get(timeout=1)
                
                # 停止信号检测
                if audio_chunk is None: 
                    break 

                if audio_chunk.size == 0: 
                    continue
                
                # 1. 计算均方根振幅 (RMS Amplitude)
                current_rms = float(np.sqrt(np.mean(audio_chunk**2)))
                
                # 2. 更新动态基线 (Mean) 和 动态峰值 (Peak)
                # Mean 用于滤除持续存在的背景噪音
                self.mean_rms = self.mean_rms * self.mean_smoothing + current_rms * (1 - self.mean_smoothing)
                # Peak 用于确定当前说话人的最大音量，仅在音量下降时衰减
                self.peak_rms = max(current_rms, self.peak_rms * self.peak_smoothing)
                
                # 3. 计算动态范围和阈值
                dynamic_range = self.peak_rms - self.mean_rms
                activation_threshold = self.mean_rms + self.activation_ratio * dynamic_range
                
                # 4. 计算归一化开合度
                mouth_open_ratio = 0.0
                # 只有当音量超过阈值且动态范围足够大（避免在静音环境下对底噪过敏）时才计算
                if current_rms > activation_threshold and dynamic_range > 0.001:
                    effective_range = self.peak_rms - activation_threshold
                    # 线性映射到 0~1
                    mouth_open_ratio = (current_rms - activation_threshold) / (effective_range + 1e-6)
                    # 钳位
                    mouth_open_ratio = max(0.0, min(mouth_open_ratio, 1.0))
                
                # 发送结果
                self.debug_data_updated.emit({
                    "rms": current_rms, "mean": self.mean_rms,
                    "peak": self.peak_rms, "threshold": activation_threshold
                })
                self.mouth_open_ratio_updated.emit(mouth_open_ratio)

            except queue.Empty:
                # 队列空闲时（如静音段），让峰值自然衰减，并发送闭嘴信号
                self.peak_rms *= self.peak_smoothing
                self.mouth_open_ratio_updated.emit(0.0)
                continue
            except Exception:
                logger.error("LipSync 异常:", exc_info=True)
                
        logger.info("LipSyncThread 停止")

    def stop(self) -> None:
        """请求停止线程。"""
        self.is_running = False
        # 放入哨兵对象以解除可能的 get() 阻塞
        self.audio_queue.put(None)
        self.wait()
