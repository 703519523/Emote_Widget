import os
import threading
import queue
from emote_widget.utils.logger import audio_logger as logger

# 尝试导入音频库，做成软依赖
try:
    import soundfile as sf
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False


def stream_audio_file(filepath: str, audio_queue: queue.Queue, stop_event: threading.Event, blocksize_hz: int = 30):
    """
    在一个新的守护线程中读取音频文件并推送到队列。
    """
    if not AUDIO_AVAILABLE:
        logger.error("缺少 soundfile 或 sounddevice 库，无法播放音频。")
        return

    def thread_target():
        logger.info(f"文件流: 开始读取 '{os.path.basename(filepath)}'...")
        try:
            with sf.SoundFile(filepath, 'r') as audio_file:
                samplerate = audio_file.samplerate
                channels = audio_file.channels
                blocksize = int(samplerate / blocksize_hz)
                
                # 创建输出流进行播放
                with sd.OutputStream(samplerate=samplerate, channels=channels) as stream:
                    while not stop_event.is_set():
                        # 读取一块
                        audio_chunk = audio_file.read(blocksize, dtype='float32')
                        if len(audio_chunk) == 0:
                            break 
                        
                        # 播放
                        stream.write(audio_chunk)
                        
                        # 转单声道并放入分析队列
                        if channels > 1:
                            mono_chunk = audio_chunk.mean(axis=1)
                        else:
                            mono_chunk = audio_chunk
                        
                        audio_queue.put(mono_chunk)
        except Exception as e:
            logger.error(f"文件流播放出错: {e}", exc_info=True)
        finally:
            audio_queue.put(None)
            logger.info("文件流结束。")

    t = threading.Thread(target=thread_target, daemon=True)
    t.start()