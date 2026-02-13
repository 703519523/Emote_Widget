import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
// import QtWebEngine // 不再直接需要
// import QtWebChannel // 不再直接需要

import "./components"
import "." as App
// 导入组件目录
import "../../emote_widget/ui/views"

ApplicationWindow {
    id: root
    visible: true
    width: 1280
    height: 720
    title: qsTr("EmoteWidget QML Tester")
    color: Style.backgroundColor
    
    // 当前选中的标签页索引
    property int currentTabIndex: 0
    
    // 监听 EmoteBackend 信号
    Connections {
        target: EmoteBackend
        
        function onPlayerReady(timelines) {
            console.log("QML: 模型就绪，动作数：", timelines.length)
            controlPanel.loadModelBtn.enabled = true
            controlPanel.statusText.text = "模型已加载 (动作数: " + timelines.length + ")"
            controlPanel.motionList = timelines
        }
        
        function onLoadFinished() {
            console.log("QML: 网页加载完成")
        }
        
        function onCharacterClicked() {
            console.log("QML: 角色被点击")
        }
    }
    
    // 主布局
    Row {
        anchors.fill: parent
        spacing: 0
        
        // 左侧控制面板
        ControlPanel {
            id: controlPanel
            width: Style.sidebarWidth
            height: parent.height
            
            // 绑定按钮事件到 EmoteBackend (使用新增的 Slot)
            onLoadModelClicked: EmoteBackend.loadModel("chara.psb")
            onPlayMotionClicked: (name) => EmoteBackend.playMotion(name)
            onPlayVoiceClicked: (path) => EmoteBackend.playVoice(path)
            onStopMotionClicked: EmoteBackend.stopMotion()
            
            onScaleChanged: (val) => EmoteBackend.setScale(val)
            onRotationChanged: (val) => EmoteBackend.setRotation(val)
            onPositionChanged: (x, y) => EmoteBackend.setPosition(x, y)
            
            onAlphaChanged: (val) => EmoteBackend.setAlpha(val)
            onGrayscaleChanged: (val) => EmoteBackend.setGrayscale(val)
            
            onPhysicsChanged: (h, p, b) => EmoteBackend.setPhysics(h, p, b)
            onWindChanged: (val) => EmoteBackend.setWind(val)
            
            onInteractionChanged: (d, z, g) => EmoteBackend.setInteraction(d, z, g)
            onResetClicked: EmoteBackend.reset()
        }
        
        // 右侧主内容区域
        Rectangle {
            width: parent.width - controlPanel.width
            height: parent.height
            color: Style.backgroundColor
            
            Column {
                anchors.fill: parent
                spacing: 0
                
                // 顶部标签页栏
                Rectangle {
                    width: parent.width
                    height: 60
                    color: Style.cardBackground
                    
                    // 底部边框
                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: 1
                        color: Style.dividerColor
                    }
                    
                    Item {
                        anchors.fill: parent
                        anchors.leftMargin: Style.spacingXLarge
                        anchors.rightMargin: Style.spacingXLarge
                        
                        // 左侧标签页按钮
                        Row {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 0
                            
                            TabButton {
                                text: "🎭 模型预览"
                                isActive: root.currentTabIndex === 0
                                onClicked: root.currentTabIndex = 0
                            }
                            
                            TabButton {
                                text: "🎨 控件展示"
                                isActive: root.currentTabIndex === 1
                                onClicked: root.currentTabIndex = 1
                            }
                        }
                    }
                }
                
                // 内容区域
                Item {
                    width: parent.width
                    height: parent.height - 60
                    clip: true
                    
                    // 模型预览页面
                    Rectangle {
                        anchors.fill: parent
                        opacity: root.currentTabIndex === 0 ? 1 : 0
                        visible: opacity > 0
                        color: "#f5f5f5"
                        
                        // 使用封装的 EmoteWidget 组件
                        EmoteWidget {
                            id: emoteView
                            anchors.fill: parent
                            
                            // 注入后端对象
                            backend: EmoteBackend
                            
                            // 可选：设置背景色
                            backgroundColor: "transparent"

                            // 组件加载完成后设置默认模型
                            Component.onCompleted: {
                                backend.modelSource = "chara.psb"
                            }
                        }
                    }
                    
                    // 控件展示页面
                    WidgetShowcase {
                        anchors.fill: parent
                        opacity: root.currentTabIndex === 1 ? 1 : 0
                        visible: opacity > 0
                    }
                }
            }
        }
    }
    
    // 标签页按钮组件
    component TabButton: Rectangle {
        property string text: ""
        property bool isActive: false
        signal clicked()
        
        width: 180
        height: 60
        color: isActive ? Style.backgroundColor : "transparent"
        
        // 底部指示器
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 3
            color: Style.accentColor
            opacity: isActive ? 1 : 0
            
            Behavior on opacity {
                NumberAnimation { duration: Style.animationNormal }
            }
        }
        
        Text {
            anchors.centerIn: parent
            text: parent.text
            font.pixelSize: Style.fontSizeMedium
            font.weight: isActive ? Font.Medium : Font.Normal
            color: isActive ? Style.textPrimary : Style.textSecondary
            
            Behavior on color {
                ColorAnimation { duration: Style.animationNormal }
            }
        }
        
        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            
            onClicked: parent.clicked()
            onEntered: parent.color = isActive ? Style.backgroundColor : Style.controlBackground
            onExited: parent.color = isActive ? Style.backgroundColor : "transparent"
        }
        
        Behavior on color {
            ColorAnimation { duration: Style.animationFast }
        }
    }
}