# EmoteWidget QML 测试器 - 现代化 UI 框架

## 📋 项目简介

这是一个为 EmoteWidget SDK 设计的现代化 QML 测试客户端 UI 框架。采用 Fluent Design 风格，提供清爽、专业的用户界面。

**当前状态**: UI Shell Only（仅 UI 框架，未连接后端逻辑）

## ✨ 特性

### 视觉设计
- 🎨 **浅色主题**: 白色、米白、浅灰配色
- 🔲 **现代化设计**: 扁平化 + 细腻阴影 + 圆角
- ✨ **流畅动画**: 所有交互都有平滑的过渡效果
- 🎯 **响应式布局**: 支持窗口缩放

### UI 组件
- **CustomButton**: 带悬停/点击动画的自定义按钮
- **CustomSlider**: 带标签和数值显示的滑块
- **CustomSwitch**: 现代化开关控件
- **CustomComboBox**: 带动画的下拉选择框
- **SidebarItem**: 侧边栏导航项
- **ControlPanel**: 完整的控制面板

### 功能区域
- **左侧控制面板**: 
  - 基础设置（缩放、透明度、边框、质量）
  - 动画控制（速度、循环、自动播放）
  - 物理效果（重力、风力）
  - 高级选项（调试、日志）
  
- **右侧预览区域**:
  - EmoteWidget 占位符
  - 状态信息栏
  - 操作按钮

## 🚀 快速开始

### 环境要求
```bash
Python 3.8+
PySide6
```

### 安装依赖
```bash
pip install PySide6
```

### 运行测试器
```bash
cd qml_tester
python run_qml.py
```

## 📁 项目结构

```
qml_tester/
├── qml/
│   ├── main.qml              # 主窗口
│   ├── Style.qml             # 全局样式单例
│   ├── qmldir                # QML 模块定义
│   └── components/           # 自定义组件
│       ├── CustomButton.qml
│       ├── CustomSlider.qml
│       ├── CustomSwitch.qml
│       ├── CustomComboBox.qml
│       ├── SidebarItem.qml
│       └── ControlPanel.qml
├── run_qml.py                # Python 启动脚本
└── README.md                 # 本文档
```

## 🎨 设计规范

### 颜色系统
```qml
backgroundColor: "#FAFAFA"      // 主背景
sidebarBackground: "#F5F5F5"   // 侧边栏背景
cardBackground: "#FFFFFF"       // 卡片背景
accentColor: "#0078D4"         // 强调色（蓝色）
textPrimary: "#1A1A1A"         // 主文字
textSecondary: "#666666"       // 次要文字
```

### 圆角规范
- Small: 4px
- Medium: 8px
- Large: 12px
- XLarge: 16px

### 间距规范
- Tiny: 4px
- Small: 8px
- Medium: 12px
- Large: 16px
- XLarge: 24px

### 动画时长
- Fast: 100ms
- Normal: 200ms
- Slow: 300ms

## 🔧 自定义与扩展

### 修改主题颜色
编辑 `qml/Style.qml` 文件中的颜色定义。

### 添加新控件
1. 在 `qml/components/` 目录创建新的 QML 文件
2. 导入 Style 单例: `import ".."`
3. 使用 Style 中定义的颜色和尺寸

### 连接 Python 后端
在 `run_qml.py` 中：
1. 创建 Python 对象
2. 使用 `setContextProperty` 暴露给 QML
3. 在 QML 中通过信号/槽通信

## 📝 待办事项

- [ ] 连接 EmoteWidget Python 后端
- [ ] 实现 WebEngine 加载模型
- [ ] 添加文件选择对话框
- [ ] 实现参数实时调整
- [ ] 添加深色主题支持
- [ ] 性能优化

## 🎯 使用场景

这个 UI 框架适用于：
- EmoteWidget SDK 功能测试
- 参数调试和预览
- 演示和展示
- 作为其他项目的 UI 模板

## 📄 许可证

与 EmoteWidget 项目保持一致。

## 👥 贡献

欢迎提交 Issue 和 Pull Request！

---

**注意**: 当前版本仅包含 UI 框架，不包含任何业务逻辑。所有按钮和控件都是可交互的，但不会触发实际功能。
