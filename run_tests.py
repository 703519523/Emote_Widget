import sys
import os
import json
import logging
import random
from PySide6.QtCore import Qt, Slot, Signal, QTimer, QEvent
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QPushButton, QSlider, QLabel, QComboBox, 
                               QCheckBox, QGroupBox, QLineEdit, QTextEdit, QScrollArea, 
                               QTabWidget, QDoubleSpinBox, QFileDialog, QSpinBox)
from Emote_Widget import EmoteWidget as EmoteWidget

logging.basicConfig(
    level=logging.DEBUG,  # 设置根日志记录器捕获 DEBUG 及以上级别的所有日志
    format='%(asctime)s - %(name)s - [%(levelname)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
 
class CheckableComboBox(QComboBox):
    """ 
    一个支持多选的、带复选框的下拉框控件。
    """ 
    checked_items_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        model = QStandardItemModel(self)
        self.setModel(model)
        self.view().viewport().installEventFilter(self)
        self.model().dataChanged.connect(self._update_text)

        self._changed = False

    def eventFilter(self, widget, event):
        """事件过滤器，用于在点击复选框时保持下拉列表打开。"""
        if event.type() == QEvent.MouseButtonRelease:
            if self.view().isVisible():
                self._changed = True
                return True
        return super().eventFilter(widget, event)

    def hidePopup(self):
        """重写 hidePopup，在下拉列表关闭时发射信号。"""
        if self._changed:
            self.checked_items_changed.emit(self.checked_items())
            self._changed = False
        super().hidePopup()

    def add_item(self, text, checked=False):
        """添加一个条目到下拉列表中。"""
        item = QStandardItem(text)
        item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item.setData(Qt.Unchecked if not checked else Qt.Checked, Qt.CheckStateRole)
        self.model().appendRow(item)
    
    def add_items(self, texts: list):
        """批量添加条目。"""
        for text in texts:
            self.add_item(text)
            
    def set_checked_items(self, items_to_check: list):
        """根据一个列表来设置哪些条目应该被选中。"""
        for i in range(self.model().rowCount()):
            item = self.model().item(i)
            if item.text() in items_to_check:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
        self._update_text()

    def checked_items(self) -> list:
        """返回所有被选中的条目的文本列表。"""
        checked = []
        for i in range(self.model().rowCount()):
            item = self.model().item(i)
            if item.checkState() == Qt.Checked:
                checked.append(item.text())
        return checked

    def _update_text(self):
        """更新 QComboBox 的显示文本，以逗号分隔显示所有选中项。"""
        checked = self.checked_items()
        if checked:
            self.lineEdit().setText(", ".join(checked))
        else:
            self.lineEdit().setText("")


class ParamControlWidget(QWidget):
    """
    用于控制单个模型变量的自定义控件行，具有优化的弹性布局和功能。
    """
    param_data_changed = Signal(str, dict)

    def __init__(self, friendly_name, param_data, all_categories, available_usage_tags: list, parent=None):
        super().__init__(parent)
        self.friendly_name = friendly_name
        self.param_data = param_data.copy()
        self.all_categories = all_categories
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(4, 5, 4, 5)
        main_layout.setSpacing(8)

        self.name_label = QLabel(self.param_data.get('name', 'N/A'))
        self.name_label.setToolTip(f"易记名: {self.friendly_name}\n模型内变量名: {self.param_data.get('name', 'N/A')}")
        
        self.slider = QSlider(Qt.Horizontal)
        
        self.min_spinbox = QDoubleSpinBox()
        self.min_spinbox.setMinimum(-9999); self.min_spinbox.setMaximum(9999)
        self.min_spinbox.setSingleStep(0.1); self.min_spinbox.setFixedWidth(65)

        self.max_spinbox = QDoubleSpinBox()
        self.max_spinbox.setMinimum(-9999); self.max_spinbox.setMaximum(9999)
        self.max_spinbox.setSingleStep(0.1); self.max_spinbox.setFixedWidth(65)
        
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.addItems(sorted(list(self.all_categories)))

        self.usage_combo = CheckableComboBox()
        self.usage_combo.add_items(available_usage_tags)

        self.name_label.setMinimumWidth(120)
        self.slider.setMinimumWidth(150)
        self.category_combo.setMinimumWidth(90)
        self.usage_combo.setMinimumWidth(110)

        main_layout.addWidget(self.name_label, stretch=3)
        main_layout.addWidget(self.slider, stretch=5)
        
        main_layout.addWidget(QLabel("范围:"))
        main_layout.addWidget(self.min_spinbox, stretch=0)
        main_layout.addWidget(self.max_spinbox, stretch=0)
        
        main_layout.addWidget(QLabel("分类:"))
        main_layout.addWidget(self.category_combo, stretch=2)
        
        main_layout.addWidget(QLabel("标签:"))
        main_layout.addWidget(self.usage_combo, stretch=3)

        self.update_ui_from_data()
        
        self.min_spinbox.valueChanged.connect(self._on_data_changed)
        self.max_spinbox.valueChanged.connect(self._on_data_changed)
        self.category_combo.currentTextChanged.connect(self._on_data_changed)
        self.usage_combo.checked_items_changed.connect(self._on_data_changed)

    def update_ui_from_data(self):
        """用 self.param_data 的内容更新 UI 控件。"""
        min_val, max_val = self.param_data.get('range', (-1.0, 1.0))
        self.min_spinbox.blockSignals(True); self.max_spinbox.blockSignals(True)
        self.min_spinbox.setValue(min_val); self.max_spinbox.setValue(max_val)
        self.min_spinbox.blockSignals(False); self.max_spinbox.blockSignals(False)
        self.slider.setRange(0, 1000)
        
        current_value = self.param_data.get('value', (min_val + max_val) / 2)
        slider_pos = 0
        if (max_val - min_val) != 0:
            slider_pos = int(((current_value - min_val) / (max_val - min_val)) * 1000)
        self.slider.setValue(slider_pos)

        self.category_combo.blockSignals(True)
        self.category_combo.setCurrentText(self.param_data.get('category', '未分类'))
        self.category_combo.blockSignals(False)
        
        self.usage_combo.blockSignals(True)
        usages = self.param_data.get('special_usage', [])
        self.usage_combo.set_checked_items(usages)
        self.usage_combo.blockSignals(False)

    def get_value_from_slider(self):
        """将滑块的整数值 (0-1000) 映射到当前的 min/max 范围。"""
        min_val = self.min_spinbox.value()
        max_val = self.max_spinbox.value()
        slider_ratio = self.slider.value() / 1000.0
        return min_val + (max_val - min_val) * slider_ratio

    @Slot()
    def _on_data_changed(self):
        """当任何输入控件改变时，更新 self.param_data 并发射信号。"""
        min_val, max_val = self.min_spinbox.value(), self.max_spinbox.value()
        if min_val > max_val:
            self.min_spinbox.setValue(max_val)
            min_val = max_val
        self.param_data['range'] = (min_val, max_val)
        
        category_text = self.category_combo.currentText()
        if category_text not in self.all_categories:
            self.all_categories.add(category_text)
        self.param_data['category'] = category_text

        self.param_data['special_usage'] = self.usage_combo.checked_items()
        
        self.param_data_changed.emit(self.friendly_name, self.param_data)


class TestMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EmoteWidget SDK - 完整功能测试平台")
        self.resize(1280, 900)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        self.emote_view = EmoteWidget(self)
        main_layout.addWidget(self.emote_view, 2)

        self.available_models = self._scan_for_resources(os.path.join('web_frontend', 'models'), ['.psb'])
        self.available_backgrounds = self._scan_for_resources(os.path.join('web_frontend', 'backgrounds'), ['.png', '.jpg', '.jpeg', '.gif'])
        self.available_dialog_themes = self._scan_for_resources(os.path.join('web_frontend', 'dialogs'), ['.html'])
        self.available_dialog_themes = [os.path.splitext(theme)[0] for theme in self.available_dialog_themes]


        self.tabs = QTabWidget()
        self._create_all_control_tabs()
        main_layout.addWidget(self.tabs, 1)

        self.emote_view.load_finished.connect(self._on_page_load)
        self.emote_view.player_ready.connect(self._on_player_ready)
        self.emote_view.plugins_load_finished.connect(self._populate_plugins_tab)
        self.emote_view.plugins_load_finished.connect(self._on_plugins_loaded)

        self.emote_view.on_character_clicked.connect(self.character_was_clicked)
        self.emote_view.on_character_hovered.connect(self.character_was_hovered)

    @Slot()
    def character_was_clicked(self):
        print("角色被点击了")

    @Slot()
    def character_was_hovered(self):
        print("角色被悬停超过1秒")
        
    def _scan_for_resources(self, relative_dir, extensions):
        """通用资源扫描函数。"""
        resources_dir = os.path.join(os.path.dirname(__file__), relative_dir)
        found_resources = []
        if not os.path.exists(resources_dir):
            print(f"警告: 资源目录 '{resources_dir}' 不存在。")
            return []
        
        for root, _, files in os.walk(resources_dir):
            for file in files:
                if any(file.lower().endswith(ext) for ext in extensions):
                    full_path = os.path.join(root, file)
                    relative_path = os.path.relpath(full_path, resources_dir)
                    found_resources.append(relative_path.replace("\\", "/"))
        
        print(f"在 '{relative_dir}' 中扫描到 {len(found_resources)} 个资源: {found_resources}")
        return found_resources

    def _create_all_control_tabs(self):
        """创建所有标签页并将控件组添加到其中。"""
        creators = {
            "⚙️ 基本": self._create_basic_controls,
            "↔️ 变换": self._create_transform_controls,
            "🎬 动画": self._create_animation_controls,
            "🎨 外观": self._create_appearance_controls,
            "💨 物理": self._create_physics_controls,
            "🔬 绑定": self._create_param_binding_controls,
            "🖱️ 交互": self._create_interaction_controls,
            "💡 高级": self._create_advanced_controls,
            "🧩 插件": self._create_plugins_tab,
        }

        for tab_name, creator_func in creators.items():
            tab_widget = QWidget()
            tab_layout = QVBoxLayout(tab_widget)
            
            group_box = creator_func()
            tab_layout.addWidget(group_box)
            tab_layout.addStretch()

            self.tabs.addTab(tab_widget, tab_name)

    def _create_basic_controls(self):
        group = QGroupBox("1. 基本操作")
        layout = QVBoxLayout(group)
        
        model_layout = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.addItems(self.available_models)
        self.load_model_btn = QPushButton("加载模型")
        self.load_model_btn.clicked.connect(self._load_selected_model)
        model_layout.addWidget(QLabel("模型:"))
        model_layout.addWidget(self.model_combo)
        model_layout.addWidget(self.load_model_btn)
        
        bg_layout = QHBoxLayout()
        self.bg_combo = QComboBox()
        self.bg_combo.addItems(self.available_backgrounds)
        self.apply_bg_btn = QPushButton("应用背景")
        self.apply_bg_btn.clicked.connect(self._apply_selected_background)
        self.clear_bg_btn = QPushButton("清除背景")
        self.clear_bg_btn.clicked.connect(self._clear_background)
        bg_layout.addWidget(QLabel("背景:"))
        bg_layout.addWidget(self.bg_combo)
        bg_layout.addWidget(self.apply_bg_btn)
        bg_layout.addWidget(self.clear_bg_btn)
        
        self.center_btn = QPushButton("自动居中模型")
        self.center_btn.clicked.connect(lambda: self.emote_view.auto_center())
        self.bg_color_btn = QPushButton("切换随机背景颜色")
        self.bg_color_btn.clicked.connect(self._toggle_bg_color)
        
        btn_layout = QHBoxLayout()
        self.hide_btn = QPushButton("隐藏")
        self.hide_btn.clicked.connect(self.emote_view.hide)
        self.show_btn = QPushButton("显示")
        self.show_btn.clicked.connect(self.emote_view.show)
        btn_layout.addWidget(self.hide_btn)
        btn_layout.addWidget(self.show_btn)

        layout.addLayout(model_layout)
        layout.addLayout(bg_layout)
        layout.addWidget(self.center_btn)
        layout.addWidget(self.bg_color_btn)
        layout.addLayout(btn_layout)
        return group

    def _create_transform_controls(self):
        group = QGroupBox("2. 变换 (Transform)")
        layout = QVBoxLayout(group)
        self.scale_slider_layout = self._create_slider("scale", "缩放", 10, 300, 100, self._on_scale_change)
        self.rot_slider_layout = self._create_slider("rotation", "旋转", -180, 180, 0, self.emote_view.set_rotation)
        self.x_slider_layout = self._create_slider("x", "X坐标", -512, 512, 0, self._on_coord_change)
        self.y_slider_layout = self._create_slider("y", "Y坐标", -512, 512, 0, self._on_coord_change)
        layout.addLayout(self.scale_slider_layout)
        layout.addLayout(self.rot_slider_layout)
        layout.addLayout(self.x_slider_layout)
        layout.addLayout(self.y_slider_layout)
        return group

    def _create_animation_controls(self):
        group = QGroupBox("3. 动画")
        layout = QVBoxLayout(group)
        self.speed_slider_layout = self._create_slider("speed", "播放速度", 10, 200, 100, lambda v: self.emote_view.set_speed(v/100.0))
        
        init_anim_layout = QHBoxLayout()
        init_anim_layout.addWidget(QLabel("初始化动画名:"))
        self.init_anim_input = QLineEdit("初期化")
        self.init_anim_input.setToolTip("点击'重置模型状态'时播放的动画名")
        init_anim_layout.addWidget(self.init_anim_input)
        
        self.anim_combo = QComboBox()
        self.anim_combo.currentTextChanged.connect(self.emote_view.play)
        
        button_layout = QHBoxLayout()
        self.stop_btn = QPushButton("停止所有动画")
        self.stop_btn.clicked.connect(self.emote_view.stop_all_timelines)
        self.reset_btn = QPushButton("重置模型状态")
        self.reset_btn.clicked.connect(self._reset_model_and_ui)
        button_layout.addWidget(self.stop_btn)
        button_layout.addWidget(self.reset_btn)

        layout.addLayout(self.speed_slider_layout)
        layout.addLayout(init_anim_layout)
        layout.addWidget(QLabel("主时间轴动画:"))
        layout.addWidget(self.anim_combo)
        layout.addLayout(button_layout)
        return group

    def _create_appearance_controls(self):
        group = QGroupBox("4. 外观与特效")
        layout = QVBoxLayout(group)
        self.alpha_slider_layout = self._create_slider("alpha", "全局透明度", 0, 100, 100, lambda v: self.emote_view.set_global_alpha(v/100.0))
        self.gray_slider_layout = self._create_slider("grayscale", "灰度", 0, 100, 0, lambda v: self.emote_view.set_grayscale(v/100.0))
        
        self.color_btn = QPushButton("切换顶点颜色 (红/绿/蓝/白)")
        self.color_btn.clicked.connect(self._toggle_vertex_color)
        self.vertex_colors = ["#FF3030", "#80FF80", "#8080FF", "#FFFFFF"]
        self.current_color_index = 0
        
        layout.addLayout(self.alpha_slider_layout)
        layout.addLayout(self.gray_slider_layout)
        layout.addWidget(self.color_btn)
        return group

    def _create_physics_controls(self):
        group = QGroupBox("5. 物理与环境")
        layout = QVBoxLayout(group)
        self.hair_slider_layout = self._create_slider("hair", "头发摆动", 0, 300, 100, self._on_physics_change)
        self.parts_slider_layout = self._create_slider("parts", "配件摆动", 0, 300, 100, self._on_physics_change)
        self.bust_slider_layout = self._create_slider("bust", "胸部摆动", 0, 300, 100, self._on_physics_change)
        self.wind_slider_layout = self._create_slider("wind", "风速", 0, 20, 0, lambda v: self.emote_view.set_wind(float(v)))
        layout.addLayout(self.hair_slider_layout)
        layout.addLayout(self.parts_slider_layout)
        layout.addLayout(self.bust_slider_layout)
        layout.addLayout(self.wind_slider_layout)
        return group

    def _create_advanced_controls(self):
        group = QGroupBox("6/7. 高级查询与控制")
        layout = QVBoxLayout(group)
        
        diff_layout = QHBoxLayout()
        self.diff_combo = QComboBox()
        self.play_diff_btn = QPushButton("播放")
        self.play_diff_btn.clicked.connect(self._play_selected_diff)
        self.clear_diff_btn = QPushButton("清除")
        self.clear_diff_btn.clicked.connect(lambda: self.emote_view.set_diff_timeline(1, ""))
        diff_layout.addWidget(self.diff_combo)
        diff_layout.addWidget(self.play_diff_btn)
        diff_layout.addWidget(self.clear_diff_btn)

        self.get_vars_btn = QPushButton("获取所有变量")
        self.get_vars_btn.clicked.connect(lambda: self.emote_view.get_variables(self._on_variables_received))
        
        self.vars_text_edit = QTextEdit()
        self.vars_text_edit.setReadOnly(True)
        self.vars_text_edit.setLineWrapMode(QTextEdit.NoWrap)
        self.vars_text_edit.setPlaceholderText("点击上方按钮以显示模型变量...")
        
        marker_layout = QHBoxLayout()
        self.marker_input = QLineEdit()
        self.marker_input.setPlaceholderText("输入标记点名称...")
        self.get_marker_btn = QPushButton("获取标记点位置")
        self.get_marker_btn.clicked.connect(self._get_marker_pos)
        self.marker_result_label = QLabel("位置: (未查询)")
        marker_layout.addWidget(self.marker_input)
        marker_layout.addWidget(self.get_marker_btn)
        
        layout.addWidget(QLabel("差分动画 (槽位1):"))
        layout.addLayout(diff_layout)
        layout.addWidget(self.get_vars_btn)
        layout.addWidget(self.vars_text_edit)
        layout.addLayout(marker_layout)
        layout.addWidget(self.marker_result_label)

        dialog_group = QGroupBox("对话框测试")
        dialog_layout = QVBoxLayout(dialog_group)

        self.dialog_text_input = QLineEdit("你好！这是一个可换肤的对话框~")
        self.dialog_text_input.setPlaceholderText("在此输入对话框文本...")
        
        theme_layout = QHBoxLayout()
        self.dialog_theme_combo = QComboBox()
        self.dialog_theme_combo.addItems(self.available_dialog_themes)
        theme_layout.addWidget(QLabel("主题:"))
        theme_layout.addWidget(self.dialog_theme_combo)

        duration_layout = QHBoxLayout()
        self.dialog_duration_spinbox = QSpinBox()
        self.dialog_duration_spinbox.setRange(1000, 60000)
        self.dialog_duration_spinbox.setValue(5000)
        self.dialog_duration_spinbox.setSuffix(" ms")
        duration_layout.addWidget(QLabel("显示时长:"))
        duration_layout.addWidget(self.dialog_duration_spinbox)
        
        self.show_dialog_btn = QPushButton("显示对话框")
        self.show_dialog_btn.clicked.connect(self._show_test_dialog)

        dialog_layout.addWidget(self.dialog_text_input)
        dialog_layout.addLayout(theme_layout)
        dialog_layout.addLayout(duration_layout)
        dialog_layout.addWidget(self.show_dialog_btn)
        
        layout.addWidget(dialog_group)
        return group

    def _create_interaction_controls(self):
        """创建“鼠标与音频交互”标签页的UI。"""
        group = QGroupBox("8. 鼠标与音频交互")
        layout = QVBoxLayout(group)
        self.drag_check = QCheckBox("启用拖动")
        self.drag_check.toggled.connect(self.emote_view.enable_drag)
        self.zoom_check = QCheckBox("启用缩放")
        self.zoom_check.toggled.connect(self.emote_view.enable_zoom)
        self.gaze_check = QCheckBox("启用视线跟随")
        self.gaze_check.toggled.connect(self.emote_view.enable_gaze_control)

        lip_sync_group = QGroupBox("口型同步")
        lip_sync_layout = QVBoxLayout(lip_sync_group)

        self.lip_sync_file_btn = QPushButton("选择 .wav 文件并开始")
        self.lip_sync_file_btn.clicked.connect(self._start_file_lip_sync)

        self.stop_lip_sync_btn = QPushButton("停止口型同步")
        self.stop_lip_sync_btn.clicked.connect(self.emote_view.stop_lip_sync)

        self.monitor_check = QCheckBox("在独立窗口中显示监视器")
        self.monitor_check.toggled.connect(
            lambda checked: self.emote_view.show_lip_sync_monitor(checked, as_window=True)
        )

        lip_sync_layout.addWidget(self.lip_sync_file_btn)
        lip_sync_layout.addWidget(self.stop_lip_sync_btn)
        lip_sync_layout.addWidget(self.monitor_check)

        layout.addWidget(self.drag_check)
        layout.addWidget(self.zoom_check)
        layout.addWidget(self.gaze_check)
        layout.addWidget(lip_sync_group)
        return group
    
    def _create_param_binding_controls(self):
        """创建“参数绑定”标签页的UI。"""
        group = QGroupBox("参数绑定与实时调试")
        layout = QVBoxLayout(group)

        btn_layout = QHBoxLayout()
        self.refresh_params_btn = QPushButton("刷新变量列表")
        self.refresh_params_btn.clicked.connect(self._populate_param_binding_panel)
        self.save_map_btn = QPushButton("保存当前绑定到缓存")
        self.save_map_btn.clicked.connect(self.emote_view.save_bindings)
        btn_layout.addWidget(self.refresh_params_btn)
        btn_layout.addWidget(self.save_map_btn)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.params_container = QWidget()
        self.params_layout = QVBoxLayout(self.params_container)
        self.params_layout.setAlignment(Qt.AlignTop)
        scroll_area.setWidget(self.params_container)
        
        layout.addLayout(btn_layout)
        layout.addWidget(scroll_area)
        return group
    
    def _create_plugins_tab(self):
        """创建“插件”标签页的UI。"""
        group = QGroupBox("插件管理与交互")
        main_layout = QVBoxLayout(group)
        
        info_label = QLabel("已加载的插件及其UI将显示在此处。\nUI由插件自身提供。")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #888;")

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        self.plugins_container = QWidget()
        self.plugins_layout = QVBoxLayout(self.plugins_container)
        self.plugins_layout.setAlignment(Qt.AlignTop)
        
        scroll_area.setWidget(self.plugins_container)
        
        main_layout.addWidget(info_label)
        main_layout.addWidget(scroll_area)
        
        return group

    def _create_slider(self, internal_name, display_name, min_val, max_val, init_val, callback):
        layout = QHBoxLayout()
        label = QLabel(f"{display_name}:")
        label.setFixedWidth(60)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(init_val)
        slider.valueChanged.connect(callback)
        layout.addWidget(label)
        layout.addWidget(slider)
        setattr(self, f"{internal_name}_slider_ref", slider)
        return layout

    @Slot()
    def _populate_plugins_tab(self):
        """当插件加载完成后，遍历插件并将其UI添加到插件面板。"""
        while self.plugins_layout.count():
            child = self.plugins_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        all_plugins = self.emote_view.plugins.get_all()
        if not all_plugins:
            self.plugins_layout.addWidget(QLabel("未发现任何插件。"))
            return

        print(f"UI: 发现 {len(all_plugins)} 个插件，正在为其生成UI...")
        for plugin in all_plugins:
            plugin_group = QGroupBox(plugin.get_name())
            plugin_group.setToolTip(plugin.get_description())
            plugin_group_layout = QVBoxLayout(plugin_group)
            
            # 检查插件是否有名为 get_ui_widget 的方法
            if hasattr(plugin, 'get_ui_widget') and callable(plugin.get_ui_widget):
                plugin_ui = plugin.get_ui_widget()
                if isinstance(plugin_ui, QWidget):
                    plugin_group_layout.addWidget(plugin_ui)
                else: # 插件有方法但返回了非QWidget对象
                    plugin_group_layout.addWidget(QLabel("此插件无UI界面。"))
            else: # 插件没有该方法
                plugin_group_layout.addWidget(QLabel("此插件无UI界面。"))
            
            self.plugins_layout.addWidget(plugin_group)

    @Slot()
    def _show_test_dialog(self):
        """从UI读取参数并调用EmoteWidget的show_dialog方法。"""
        text = self.dialog_text_input.text()
        theme = self.dialog_theme_combo.currentText()
        duration = self.dialog_duration_spinbox.value()
        
        if not text:
            print("UI: 对话框文本为空，已取消显示。")
            return
            
        self.emote_view.show_dialog(
            text=text,
            duration_ms=duration,
            theme=theme
        )
    
    @Slot()
    def _on_page_load(self):
        print("主窗口: 页面加载完成，准备加载模型...")
        self.load_model_btn.setEnabled(True)
        #self.emote_view.set_background_color(51, 51, 51, 1.0)
        if self.available_models:
            self.emote_view.load_model(self.available_models[0] )
        else:
            print("错误: 在 'web_frontend/models' 目录中未找到任何 .psb 模型文件。")

    @Slot()
    def _on_plugins_loaded(self):
        """当所有插件都加载完成后，这个槽会被调用。"""
        print("\n主窗口: 收到插件加载完成信号！")
        try:
            self.emote_view.plugins.debug.print_widget_size()
        except AttributeError:
            print("主窗口: 未找到 'debug' 插件。")

    @Slot(list)
    def _on_player_ready(self, timelines):
        """当模型加载并准备就绪后调用。"""
        print(f"主窗口: 模型 '{self.model_combo.currentText()}' 已就绪，收到主 timeline: {timelines}")
        self.anim_combo.blockSignals(True)
        self.anim_combo.clear()
        self.anim_combo.addItems(timelines)
        self.anim_combo.blockSignals(False)
        
        self.emote_view.auto_center()
        self.emote_view.get_diff_timelines(self._on_diff_timelines_received)
        
        self._reset_ui_to_defaults()
        
        self._populate_param_binding_panel()

    def _populate_param_binding_panel(self):
        """请求模型变量并填充参数绑定UI面板。"""
        print("UI: 正在填充参数绑定面板...")
        self.emote_view.get_variables(self._on_variables_for_binding_received)

    @Slot(list)
    def _on_variables_for_binding_received(self, variables_list):
        """
        当从模型异步获取到变量列表后，启动分批UI创建流程。
        """
        while self.params_layout.count():
            child = self.params_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()

        if not variables_list:
            self.params_layout.addWidget(QLabel("未能从模型获取变量列表。"))
            return
        self.variables_to_process = iter(variables_list)
        self.current_map_snapshot = self.emote_view.variable_map.copy()
        self.all_categories_snapshot = set(p.get('category', '未分类') for p in self.current_map_snapshot.values() if isinstance(p, dict))
        self.available_tags_snapshot = self.emote_view.get_available_special_usage_tags()
        self.batch_size = 20
        QTimer.singleShot(0, self._process_widget_creation_batch)

    def _process_widget_creation_batch(self):
        """
        处理并创建一小批 ParamControlWidget 实例，然后预约下一次执行。
        """
        try:
            for _ in range(self.batch_size):
                var_info = next(self.variables_to_process, None)
                if var_info is None:
                    print("UI: 所有参数绑定控件均已创建完成。")
                    return

                model_var_name = var_info.get('label')
                if not model_var_name: continue
                friendly_name, param_data = "unmapped", {"name": model_var_name}
                for f_name, p_data in self.current_map_snapshot.items():
                    if isinstance(p_data, dict) and p_data.get('name') == model_var_name:
                        friendly_name, param_data = f_name, p_data
                        break
                control_widget = ParamControlWidget(friendly_name, param_data, self.all_categories_snapshot, self.available_tags_snapshot)
                control_widget.slider.valueChanged.connect(lambda _, w=control_widget: self.emote_view.set_variable(w.param_data['name'], w.get_value_from_slider()))
                control_widget.param_data_changed.connect(self._on_param_data_in_ui_changed)
                
                self.params_layout.addWidget(control_widget)
            QTimer.singleShot(0, self._process_widget_creation_batch)

        except Exception as e:
            print(f"UI: 创建参数控件时发生错误: {e}")

    @Slot(str, dict)
    def _on_param_data_in_ui_changed(self, friendly_name, new_data):
        """当UI上的参数数据被用户修改时，实时更新 emote_view.variable_map。"""
        self.emote_view.variable_map[friendly_name] = new_data
    
    @Slot()
    def _start_file_lip_sync(self):
        """打开文件对话框并启动基于文件的口型同步。"""
        # 停止任何可能正在运行的同步
        self.emote_view.stop_lip_sync()
        
        filepath, _ = QFileDialog.getOpenFileName(
            self, 
            "选择一个WAV音频文件", 
            "", # 起始目录
            "WAV Files (*.wav)"
        )
        
        if filepath:
            print(f"UI: 请求使用文件 '{filepath}' 开始口型同步...")
            self.emote_view.start_lip_sync_from_file(filepath=filepath)
        
    def _load_selected_model(self):
        model_name = self.model_combo.currentText()
        if model_name:
            self.emote_view.load_model(model_name )

    def _apply_selected_background(self):
        bg_name = self.bg_combo.currentText()
        if bg_name:
            self.emote_view.set_background_image(bg_name)

    def _clear_background(self):
        self.emote_view.set_background_image(None)

    def _on_diff_timelines_received(self, timelines):
        print(f"主窗口: 收到差分 timeline: {timelines}")
        self.diff_combo.clear()
        self.diff_combo.addItems(timelines)

    def _on_variables_received(self, variables):
        print(f"主窗口: 收到 {len(variables)} 个变量")
        pretty_json = json.dumps(variables, indent=2, ensure_ascii=False)
        self.vars_text_edit.setText(pretty_json)

    def _get_marker_pos(self):
        marker_name = self.marker_input.text()
        if marker_name:
            self.emote_view.get_marker_position(marker_name, self._on_marker_pos_received)

    def _on_marker_pos_received(self, pos_data):
        if pos_data:
            text = f"位置: x={pos_data.get('x', 'N/A')}, y={pos_data.get('y', 'N/A')}"
            self.marker_result_label.setText(text)
        else:
            self.marker_result_label.setText("位置: 未找到")

    def _play_selected_diff(self):
        diff_name = self.diff_combo.currentText()
        if diff_name:
            self.emote_view.set_diff_timeline(1, diff_name)

    def _toggle_vertex_color(self):
        color = self.vertex_colors[self.current_color_index]
        self.current_color_index = (self.current_color_index + 1) % len(self.vertex_colors)
        self.emote_view.set_vertex_color(color, duration_ms=200)

    def _toggle_bg_color(self):
        r, g, b = random.randint(30, 80), random.randint(30, 80), random.randint(30, 80)
        self.emote_view.set_background_color(r, g, b, 1.0)
        self.emote_view.set_background_image(None)

    def _on_scale_change(self, value):
        self.emote_view.set_scale(value / 100.0)

    def _on_physics_change(self):
        hair = self.hair_slider_ref.value() / 100.0
        parts = self.parts_slider_ref.value() / 100.0
        bust = self.bust_slider_ref.value() / 100.0
        self.emote_view.set_physics_scale(hair, parts, bust)

    def _on_coord_change(self, _=None):
        x = self.x_slider_ref.value()
        y = self.y_slider_ref.value()
        self.emote_view.set_coord(x, y)

    def _reset_model_and_ui(self):
        if not self.emote_view: return
        init_name = self.init_anim_input.text()
        self.emote_view.config["animation"]["initialization_name"] = init_name
        
        self.emote_view.animation_reset()
        print("UI: 重置所有控制滑块。")
        self._reset_ui_to_defaults()

    def _reset_ui_to_defaults(self):
        sliders = ["scale", "rotation", "x", "y", "speed", "alpha", "grayscale", "hair", "parts", "bust", "wind"]
        defaults = [100, 0, 0, 0, 100, 100, 0, 100, 100, 100, 0]
        for name, value in zip(sliders, defaults):
            slider = getattr(self, f"{name}_slider_ref", None)
            if slider:
                slider.blockSignals(True)
                slider.setValue(value)
                slider.blockSignals(False)

        self.drag_check.setChecked(False)
        self.zoom_check.setChecked(False)
        self.gaze_check.setChecked(False)

        self.vars_text_edit.clear()
        self.marker_result_label.setText("位置: (未查询)")

if __name__ == "__main__":
    app = QApplication(sys.argv)

    chromium_flags = (
        f"--remote-allow-origins=* "
        f"--disable-features=ProcessSharing "
        f"--incognito "
        f"--bwsi "
    )
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = chromium_flags
    os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = "8000"
    window = TestMainWindow()
    window.show()
    sys.exit(app.exec())