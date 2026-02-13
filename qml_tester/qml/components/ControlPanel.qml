import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: controlPanel
    color: "#FFFFFF"
    
    // --- 公共属性 ---
    property var motionList: []
    
    // --- 信号定义 ---
    signal loadModelClicked()
    signal playMotionClicked(string motionName)
    signal playVoiceClicked(string voicePath)
    signal stopMotionClicked()
    
    signal scaleChanged(real value)
    signal rotationChanged(real value)
    signal positionChanged(real x, real y)
    
    signal alphaChanged(real value)
    signal grayscaleChanged(real value)
    
    signal physicsChanged(real hair, real parts, real bust)
    signal windChanged(real value)
    
    signal interactionChanged(bool drag, bool zoom, bool gaze)
    signal resetClicked()
    
    // --- 内部逻辑 ---
    function updateInteraction() {
        interactionChanged(dragSwitch.checked, zoomSwitch.checked, gazeSwitch.checked)
    }

    onMotionListChanged: {
        motionCombo.model = motionList
        if (motionList.length > 0) {
            motionCombo.currentIndex = 0
            playMotionButton.enabled = true
        } else {
            playMotionButton.enabled = false
        }
    }
    
    // 状态显示属性别名
    property alias statusText: statusLabel
    property alias loadModelBtn: loadModelButton // 兼容旧代码

    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        
        // 标题栏
        Rectangle {
            Layout.fillWidth: true
            height: 50
            color: "#f5f5f5"
            border.color: "#e0e0e0"
            border.width: 1
            
            Text {
                anchors.centerIn: parent
                text: "EmoteWidget 控制台"
                font.pixelSize: 16
                font.bold: true
                color: "#333"
            }
        }
        
        // 可滚动区域
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AsNeeded
            
            ColumnLayout {
                width: parent.width - 20 // 留出滚动条空间
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 15
                
                // 状态栏
                Rectangle {
                    Layout.fillWidth: true
                    height: 30
                    color: "#eef"
                    radius: 4
                    Text {
                        id: statusLabel
                        anchors.centerIn: parent
                        text: "就绪"
                        color: "#666"
                        font.pixelSize: 12
                    }
                }

                // 1. 基本操作
                GroupBox {
                    title: "基本操作"
                    Layout.fillWidth: true
                    
                    ColumnLayout {
                        anchors.fill: parent
                        Button {
                            id: loadModelButton
                            text: "重新加载模型"
                            Layout.fillWidth: true
                            onClicked: controlPanel.loadModelClicked()
                        }
                        Button {
                            text: "重置所有状态"
                            Layout.fillWidth: true
                            onClicked: {
                                // 重置 UI 控件
                                scaleSlider.value = 1.0
                                rotSlider.value = 0
                                alphaSlider.value = 1.0
                                graySlider.value = 0
                                xSlider.value = 0
                                ySlider.value = 0
                                controlPanel.resetClicked()
                            }
                        }
                    }
                }
                
                // 2. 动画控制
                GroupBox {
                    title: "动画控制"
                    Layout.fillWidth: true
                    
                    ColumnLayout {
                        anchors.fill: parent
                        ComboBox {
                            id: motionCombo
                            Layout.fillWidth: true
                            model: ["(无动作)"]
                        }
                        
                        RowLayout {
                            Button {
                                id: playMotionButton
                                text: "播放"
                                enabled: false
                                Layout.fillWidth: true
                                onClicked: controlPanel.playMotionClicked(motionCombo.currentText)
                            }
                            Button {
                                text: "停止"
                                Layout.fillWidth: true
                                onClicked: controlPanel.stopMotionClicked()
                            }
                        }
                        
                        Button {
                            id: playVoiceButton // 暂时保留
                            text: "播放测试语音"
                            Layout.fillWidth: true
                            onClicked: controlPanel.playVoiceClicked("voice.wav")
                        }
                    }
                }
                
                // 3. 变换 (Transform)
                GroupBox {
                    title: "变换"
                    Layout.fillWidth: true
                    
                    ColumnLayout {
                        anchors.fill: parent
                        
                        Label { text: "缩放: " + scaleSlider.value.toFixed(2) }
                        Slider {
                            id: scaleSlider
                            from: 0.1; to: 3.0; value: 1.0
                            Layout.fillWidth: true
                            onMoved: controlPanel.scaleChanged(value)
                        }
                        
                        Label { text: "旋转: " + rotSlider.value.toFixed(0) + "°" }
                        Slider {
                            id: rotSlider
                            from: -180; to: 180; value: 0
                            Layout.fillWidth: true
                            onMoved: controlPanel.rotationChanged(value)
                        }
                        
                        Label { text: "X 位移: " + xSlider.value.toFixed(0) }
                        Slider {
                            id: xSlider
                            from: -500; to: 500; value: 0
                            Layout.fillWidth: true
                            onMoved: controlPanel.positionChanged(value, ySlider.value)
                        }
                        
                        Label { text: "Y 位移: " + ySlider.value.toFixed(0) }
                        Slider {
                            id: ySlider
                            from: -500; to: 500; value: 0
                            Layout.fillWidth: true
                            onMoved: controlPanel.positionChanged(xSlider.value, value)
                        }
                    }
                }
                
                // 4. 外观 (Appearance)
                GroupBox {
                    title: "外观"
                    Layout.fillWidth: true
                    
                    ColumnLayout {
                        anchors.fill: parent
                        
                        Label { text: "透明度: " + alphaSlider.value.toFixed(2) }
                        Slider {
                            id: alphaSlider
                            from: 0; to: 1.0; value: 1.0
                            Layout.fillWidth: true
                            onMoved: controlPanel.alphaChanged(value)
                        }
                        
                        Label { text: "灰度: " + graySlider.value.toFixed(2) }
                        Slider {
                            id: graySlider
                            from: 0; to: 1.0; value: 0
                            Layout.fillWidth: true
                            onMoved: controlPanel.grayscaleChanged(value)
                        }
                    }
                }
                
                // 5. 物理 (Physics)
                GroupBox {
                    title: "物理"
                    Layout.fillWidth: true
                    
                    ColumnLayout {
                        anchors.fill: parent
                        
                        Label { text: "物理强度 (统一): " + physicsSlider.value.toFixed(2) }
                        Slider {
                            id: physicsSlider
                            from: 0; to: 3.0; value: 1.0
                            Layout.fillWidth: true
                            onMoved: controlPanel.physicsChanged(value, value, value)
                        }
                        
                        Label { text: "风力: " + windSlider.value.toFixed(2) }
                        Slider {
                            id: windSlider
                            from: 0; to: 20.0; value: 0
                            Layout.fillWidth: true
                            onMoved: controlPanel.windChanged(value)
                        }
                    }
                }
                
                // 6. 交互 (Interaction)
                GroupBox {
                    title: "交互开关"
                    Layout.fillWidth: true
                    
                    ColumnLayout {
                        anchors.fill: parent
                        
                        Switch {
                            text: "允许拖拽"
                            checked: false
                            onCheckedChanged: controlPanel.updateInteraction()
                            id: dragSwitch
                        }
                        Switch {
                            text: "允许缩放"
                            checked: false
                            onCheckedChanged: controlPanel.updateInteraction()
                            id: zoomSwitch
                        }
                        Switch {
                            text: "视线跟随"
                            checked: false
                            onCheckedChanged: controlPanel.updateInteraction()
                            id: gazeSwitch
                        }
                    }
                }
                
                // 底部留白
                Item { height: 20 }
            }
        }
    }
}