import sys
import ctypes
import os
from ctypes import wintypes
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
from emote_widget import EmoteWidget

# [已弃用] DLL 方法不再需要，现在使用基于 QRegion 的 Python/JS 混合方案
# dll_path = os.path.abspath("./ClickEventHelper.dll")
# try:
#     lib = ctypes.CDLL(dll_path)
#     lib.EnablePixelPerfectClickThrough.argtypes = [wintypes.HWND]
#     print(f"Successfully loaded {dll_path}")
# except OSError as e:
#     print(f"Error: Failed to load {dll_path}: {e}")
#     sys.exit(1)

def main():
    app = QApplication(sys.argv)
    
    # 适配高分屏
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    
    # Chromium 标志设置 (参考 test_qt.py)
    chromium_flags = (
        f"--remote-allow-origins=* "
        f"--disable-features=ProcessSharing "
        f"--incognito "
        f"--bwsi "
    )
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = chromium_flags

    # 创建 EmoteWidget
    print("Creating EmoteWidget...")
    widget = EmoteWidget()
    widget.resize(800, 800)
    
    # 1. 设置窗口透明 (这会去除边框并设置背景透明)
    print("Setting window transparent...")
    widget.controller.set_window_transparent(True, click_through=True)
    
    # 2. 设置窗口置顶
    print("Setting window stay on top...")
    widget.setWindowFlags(widget.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    
    # 3. 监听加载完成信号，加载模型
    def on_load_finished():
        print("WebEngine page loaded. Loading model 'chara.psb'...")
        # 尝试加载 chara.psb
        # 这里假设模型文件位于 web_frontend/models/chara.psb
        widget.controller.load_model("chara.psb")
        
    # 连接信号
    # EmoteWidget 会通过 __getattr__ 转发访问到 controller.load_finished
    # 或者显式使用 widget.controller.load_finished
    widget.controller.load_finished.connect(on_load_finished)
    
    # 4. 监听模型就绪信号
    def on_player_ready(timelines):
        print(f"Model loaded! Available timelines: {timelines}")
        # 居中显示
        widget.controller.auto_center()
        # 播放第一个动作
        if timelines:
            print(f"Playing animation: {timelines[0]}")
            widget.controller.play(timelines[0])
            
    widget.controller.player_ready.connect(on_player_ready)

    # 显示窗口
    widget.show()
    
    # 5. 开启 C++ 点击穿透魔法 (已废弃)
    # 现在 Controller 会自动接收 JS 发来的 Mask 数据并应用 setMask
    print(">>> Test Started: Waiting for mask update from JS...")
    print(">>> Click on the transparent area should pass through to the desktop.")
    print(">>> Click on the character should be intercepted.")

    # 我们可以监听一下 mask 更新信号来确认
    # 注意：这是内部信号，仅供测试
    if hasattr(widget.controller, "_bridge"):
        def on_mask_update(json_str):
            print(f"Mask updated! Rect count: {json_str.count('[') - 1}")
        widget.controller._bridge.render_mask_updated_signal.connect(on_mask_update)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
