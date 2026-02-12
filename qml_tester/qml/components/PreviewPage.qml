import QtQuick 2.15
import QtQuick.Controls 2.15
import ".."

Rectangle {
    id: root
    color: Style.backgroundColor
    
    Column {
        anchors.fill: parent
        anchors.margins: Style.spacingXLarge
        spacing: Style.spacingLarge
        
        // 顶部标题区域
        Column {
            width: parent.width
            spacing: Style.spacingTiny
            
            Text {
                text: "EmoteWidget 预览"
                font.pixelSize: Style.fontSizeHeader
                font.weight: Font.Bold
                color: Style.textPrimary
            }
            
            Text {
                text: "实时预览和测试您的 Emote 模型"
                font.pixelSize: Style.fontSizeMedium
                color: Style.textSecondary
            }
        }
        
        // 主预览区域
        Rectangle {
            width: parent.width
            height: parent.height - 80
            radius: Style.radiusLarge
            color: Style.cardBackground
            border.width: 1
            border.color: Style.borderColor
            
            // 阴影效果
            layer.enabled: true
            layer.effect: Item {
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: -8
                    anchors.topMargin: 4
                    radius: Style.radiusLarge + 8
                    color: Style.shadowColor
                    z: -1
                    opacity: 0.08
                }
            }
            
            // EmoteWidget 占位符
            Item {
                anchors.fill: parent
                anchors.margins: Style.spacingXLarge
                
                // 中心占位内容
                Column {
                    anchors.centerIn: parent
                    spacing: Style.spacingLarge
                    
                    // 占位图标
                    Rectangle {
                        width: 120
                        height: 120
                        radius: 60
                        color: Style.accentColor
                        opacity: 0.1
                        anchors.horizontalCenter: parent.horizontalCenter
                        
                        Text {
                            anchors.centerIn: parent
                            text: "🎭"
                            font.pixelSize: 64
                        }
                    }
                    
                    Column {
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: Style.spacingSmall
                        
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "EmoteWidget 预览区域"
                            font.pixelSize: Style.fontSizeTitle
                            font.weight: Font.Medium
                            color: Style.textPrimary
                        }
                        
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "这里将显示您的 Emote 模型"
                            font.pixelSize: Style.fontSizeMedium
                            color: Style.textSecondary
                        }
                    }
                    
                    CustomButton {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "选择模型文件"
                        isPrimary: true
                    }
                }
                
                // 底部信息栏
                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 48
                    radius: Style.radiusMedium
                    color: Style.sidebarBackground
                    
                    Row {
                        anchors.fill: parent
                        anchors.leftMargin: Style.spacingLarge
                        anchors.rightMargin: Style.spacingLarge
                        spacing: Style.spacingXLarge
                        
                        // 状态信息
                        Row {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: Style.spacingSmall
                            
                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 8
                                height: 8
                                radius: 4
                                color: "#4CAF50"
                            }
                            
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: "就绪"
                                font.pixelSize: Style.fontSizeMedium
                                color: Style.textSecondary
                            }
                        }
                        
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 1
                            height: 24
                            color: Style.dividerColor
                        }
                        
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "FPS: 60"
                            font.pixelSize: Style.fontSizeMedium
                            color: Style.textSecondary
                        }
                        
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 1
                            height: 24
                            color: Style.dividerColor
                        }
                        
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "分辨率: 1920x1080"
                            font.pixelSize: Style.fontSizeMedium
                            color: Style.textSecondary
                        }
                    }
                }
            }
        }
    }
}
