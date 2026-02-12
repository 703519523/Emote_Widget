import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Dialogs
import "components"

Window {
    id: mainWindow
    visible: true
    width: 1200
    height: 800
    minimumWidth: 900
    minimumHeight: 600
    title: "EmoteWidget 测试器 - 现代化 UI"
    color: Style.backgroundColor
    
    // 当前选中的标签页索引
    property int currentTabIndex: 0
    
    // 已加载的模型文件路径
    property string loadedModelPath: ""
    property string loadedModelName: ""
    
    // 主布局
    Row {
        anchors.fill: parent
        spacing: 0
        
        // 左侧控制面板
        ControlPanel {
            id: controlPanel
            width: Style.sidebarWidth
            height: parent.height
            
            // 添加阴影效果
            layer.enabled: true
            layer.effect: Item {
                Rectangle {
                    anchors.fill: parent
                    anchors.leftMargin: parent.width
                    width: 8
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: Style.shadowColorLight }
                        GradientStop { position: 1.0; color: "transparent" }
                    }
                }
            }
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
                                isActive: mainWindow.currentTabIndex === 0
                                onClicked: mainWindow.currentTabIndex = 0
                            }
                            
                            TabButton {
                                text: "🎨 控件展示"
                                isActive: mainWindow.currentTabIndex === 1
                                onClicked: mainWindow.currentTabIndex = 1
                            }
                        }
                        
                        // 右侧操作按钮
                        Row {
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: Style.spacingMedium
                            
                            // 模型文件名显示
                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: modelNameText.width + Style.spacingLarge
                                height: 36
                                radius: Style.radiusMedium
                                color: Style.accentColor
                                opacity: 0.1
                                visible: mainWindow.loadedModelName !== "" && mainWindow.currentTabIndex === 0
                                
                                Row {
                                    anchors.centerIn: parent
                                    spacing: Style.spacingSmall
                                    
                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "📁"
                                        font.pixelSize: Style.fontSizeMedium
                                    }
                                    
                                    Text {
                                        id: modelNameText
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: mainWindow.loadedModelName
                                        font.pixelSize: Style.fontSizeMedium
                                        color: Style.accentColor
                                        font.weight: Font.Medium
                                    }
                                }
                            }
                            
                            CustomButton {
                                text: mainWindow.loadedModelName === "" ? "📂 加载模型" : "🔄 重新加载"
                                isPrimary: false
                                visible: mainWindow.currentTabIndex === 0
                                
                                onClicked: {
                                    fileDialog.open()
                                }
                            }
                            
                            CustomButton {
                                text: "▶️ 开始测试"
                                isPrimary: true
                                visible: mainWindow.currentTabIndex === 0
                                enabled: mainWindow.loadedModelName !== ""
                                
                                onClicked: {
                                    console.log("开始测试模型:", mainWindow.loadedModelPath)
                                }
                            }
                        }
                    }
                }
                
                // 内容区域 - 使用 StackLayout 实现标签页切换
                Item {
                    width: parent.width
                    height: parent.height - 60
                    clip: true
                    
                    // 模型预览页面
                    PreviewPage {
                        id: previewPage
                        anchors.fill: parent
                        opacity: mainWindow.currentTabIndex === 0 ? 1 : 0
                        visible: opacity > 0
                        
                        // 位置动画
                        transform: Translate {
                            x: mainWindow.currentTabIndex === 0 ? 0 : -50
                            
                            Behavior on x {
                                NumberAnimation {
                                    duration: Style.animationSlow
                                    easing.type: Easing.OutCubic
                                }
                            }
                        }
                        
                        // 透明度动画
                        Behavior on opacity {
                            NumberAnimation {
                                duration: Style.animationSlow
                                easing.type: Easing.OutCubic
                            }
                        }
                    }
                    
                    // 控件展示页面
                    WidgetShowcase {
                        id: showcasePage
                        anchors.fill: parent
                        opacity: mainWindow.currentTabIndex === 1 ? 1 : 0
                        visible: opacity > 0
                        
                        // 位置动画
                        transform: Translate {
                            x: mainWindow.currentTabIndex === 1 ? 0 : 50
                            
                            Behavior on x {
                                NumberAnimation {
                                    duration: Style.animationSlow
                                    easing.type: Easing.OutCubic
                                }
                            }
                        }
                        
                        // 透明度动画
                        Behavior on opacity {
                            NumberAnimation {
                                duration: Style.animationSlow
                                easing.type: Easing.OutCubic
                            }
                        }
                    }
                }
            }
        }
    }
    
    // 文件选择对话框
    FileDialog {
        id: fileDialog
        title: "选择 Emote 模型文件"
        nameFilters: ["Emote 模型文件 (*.psb *.json)", "所有文件 (*)"]
        
        onAccepted: {
            mainWindow.loadedModelPath = fileDialog.selectedFile.toString()
            // 提取文件名
            var path = mainWindow.loadedModelPath
            var fileName = path.substring(path.lastIndexOf('/') + 1)
            if (fileName.indexOf('\\') !== -1) {
                fileName = fileName.substring(fileName.lastIndexOf('\\') + 1)
            }
            mainWindow.loadedModelName = fileName
            
            console.log("已选择模型文件:", mainWindow.loadedModelPath)
            
            // 显示加载成功提示
            loadSuccessAnimation.restart()
        }
        
        onRejected: {
            console.log("取消选择文件")
        }
    }
    
    // 加载成功动画提示
    Rectangle {
        id: loadSuccessToast
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: 80
        width: toastText.width + Style.spacingXLarge * 2
        height: 48
        radius: Style.radiusLarge
        color: "#4CAF50"
        opacity: 0
        z: 1000
        
        Row {
            anchors.centerIn: parent
            spacing: Style.spacingMedium
            
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "✓"
                font.pixelSize: 20
                font.weight: Font.Bold
                color: "#FFFFFF"
            }
            
            Text {
                id: toastText
                anchors.verticalCenter: parent.verticalCenter
                text: "模型加载成功！"
                font.pixelSize: Style.fontSizeMedium
                font.weight: Font.Medium
                color: "#FFFFFF"
            }
        }
        
        SequentialAnimation {
            id: loadSuccessAnimation
            
            NumberAnimation {
                target: loadSuccessToast
                property: "opacity"
                to: 1
                duration: Style.animationNormal
                easing.type: Easing.OutQuad
            }
            
            PauseAnimation {
                duration: 2000
            }
            
            NumberAnimation {
                target: loadSuccessToast
                property: "opacity"
                to: 0
                duration: Style.animationNormal
                easing.type: Easing.InQuad
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
