#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWebEngineQuick import QtWebEngineQuick
from PySide6.QtQuickControls2 import QQuickStyle

from emote_widget import EmoteWidgetQml

def main():
    # 1. 初始化应用和 WebEngine
    app = QGuiApplication(sys.argv)
    QtWebEngineQuick.initialize()
    QQuickStyle.setStyle("Basic")  # 设置基础样式
    
    # 2. 创建 QML 引擎
    engine = QQmlApplicationEngine()
    
    # 3. 创建并设置 EmoteWidgetQml 实例
    # 注入插件路径（如果有的话）
    backend = EmoteWidgetQml()
    
    # 注册项目根目录资源
    import os
    cwd = os.getcwd()
    backend.controller.add_resource_path('models', os.path.join(cwd, 'models'))
    backend.controller.add_resource_path('models', os.path.join(cwd, 'modellist'))
    backend.controller.add_resource_path('backgrounds', os.path.join(cwd, 'backgrounds'))
    
    engine.rootContext().setContextProperty("EmoteBackend", backend)
    
    # 4. 设置 QML 导入路径
    qml_dir = project_root / "qml_tester" / "qml"
    engine.addImportPath(str(qml_dir))
    
    # 5. 加载 QML 文件
    qml_file = qml_dir / "main.qml"
    url = QUrl.fromLocalFile(str(qml_file))
    engine.load(url)    
    
    # 6. 检查 QML 是否成功加载
    if not engine.rootObjects():
        print(f"错误: 无法加载 QML 文件: {qml_file}")
        print(f"QML 导入路径: {qml_dir}")
        sys.exit(-1)
    
    # 7. 设置清理回调
    app.aboutToQuit.connect(backend.cleanup)
    
    # 8. 启动应用
    print("=" * 60)
    print("EmoteWidget QML 测试器已启动")
    print("=" * 60)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()