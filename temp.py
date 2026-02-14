import sys
import os
import ctypes
from ctypes import wintypes
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, Qt, QTimer

# 1. 加载 DLL
dll_path = os.path.abspath("ClickEventHelper.dll")
try:
    lib = ctypes.CDLL(dll_path)
    lib.EnablePixelPerfectClickThrough.argtypes = [wintypes.HWND]
    print("✅ DLL 加载成功")
except Exception as e:
    print(f"❌ DLL 加载失败: {e}")
    sys.exit()

class EmoteWebWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(800, 800)
        
        # 基础透明设置
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建 WebEngineView
        self.view = QWebEngineView()
        self.view.page().setBackgroundColor(Qt.transparent) # 必须：网页背景透明
        layout.addWidget(self.view)

        # 加载一个带透明通道的页面（或者你的看板娘页面）
        # 这里用 data url 模拟一个中间有蓝色方块，四周透明的页面
        html_content = """
        <body style="background:transparent; margin:0; overflow:hidden;">
            <div style="width:200px; height:200px; background:blue; margin:300px auto;">
                我是实体区域
            </div>
        </body>
        """
        self.view.setHtml(html_content)

        # ★ 关键：不能在 __init__ 立即调用，因为窗口句柄和子窗口可能还没准备好
        # 延迟 500ms 执行魔法，或者在 loadFinished 信号中执行
        self.view.loadFinished.connect(self.apply_magic)

    def apply_magic(self):
        # 获取 WebEngineView 的原生句柄
        # 注意：在 QML 中是 findChild 得到的对象，在 Widget 中直接用 winId
        hwnd = wintypes.HWND(int(self.winId()))
        print(f"🔮 正在对窗口 {hex(int(self.winId()))} 施展递归穿透魔法...")
        
        lib.EnablePixelPerfectClickThrough(hwnd)
        print("✨ 魔法已生效：现在只有点中有颜色的像素才有反应！")

if __name__ == "__main__":
    # WebEngine 必须的初始化
    app = QApplication(sys.argv)
    
    win = EmoteWebWindow()
    win.show()
    
    sys.exit(app.exec())