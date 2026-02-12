"""
EmoteWidget QML 测试器启动脚本
现代化 UI 测试框架
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtCore import QUrl
    from PySide6.QtQuickControls2 import QQuickStyle
except ImportError:
    print("错误: 未找到 PySide6。请安装: pip install PySide6")
    sys.exit(1)


def main():
    """主函数：启动 QML 应用"""
    
    # 设置 QML 样式为 Basic（支持自定义）
    QQuickStyle.setStyle("Basic")
    
    # 创建应用实例
    app = QGuiApplication(sys.argv)
    app.setApplicationName("EmoteWidget Tester")
    app.setOrganizationName("EmoteWidget")
    
    # 创建 QML 引擎
    engine = QQmlApplicationEngine()
    
    # 获取 QML 文件路径
    qml_file = Path(__file__).parent / "qml_tester" / "qml" / "main.qml"
    
    if not qml_file.exists():
        print(f"错误: 找不到 QML 文件: {qml_file}")
        sys.exit(1)
    
    # 添加 QML 导入路径
    qml_dir = Path(__file__).parent / "qml_tester" / "qml"
    engine.addImportPath(str(qml_dir))
    
    # 加载 QML 文件
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    
    # 检查是否成功加载
    if not engine.rootObjects():
        print("错误: 无法加载 QML 文件")
        sys.exit(1)
    
    print("=" * 60)
    print("EmoteWidget QML 测试器已启动")
    print("=" * 60)
    print(f"QML 文件: {qml_file}")
    print(f"导入路径: {qml_dir}")
    print("=" * 60)
    print("\n提示:")
    print("  - 这是一个纯 UI 框架演示")
    print("  - 所有控件都是可交互的")
    print("  - 尚未连接到 Python 后端逻辑")
    print("  - 按 Ctrl+C 或关闭窗口退出")
    print("=" * 60)
    
    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
