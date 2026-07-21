import QtQuick 2.15
import QtQuick.Controls 2.15
import ".."

Rectangle {
    id: root
    color: Style.backgroundColor
    
    ScrollView {
        id: scrollView
        anchors.fill: parent
        anchors.margins: Style.spacingXLarge
        clip: true
        
        Column {
            width: scrollView.width - Style.spacingXLarge * 2
            spacing: Style.spacingXLarge
            
            // ========== 页面标题 ==========
            Text {
                text: "控件展示"
                font.pixelSize: Style.fontSizeHeader
                font.weight: Font.Bold
                color: Style.textPrimary
            }
            
            Text {
                text: "所有 QML 控件演示"
                font.pixelSize: Style.fontSizeMedium
                color: Style.textSecondary
            }
            
            Rectangle {
                width: parent.width
                height: 1
                color: Style.dividerColor
            }
            
            // ========== 按钮组 ==========
            Column {
                width: parent.width
                spacing: Style.spacingMedium
                
                Text {
                    text: "按钮 (Buttons)"
                    font.pixelSize: Style.fontSizeTitle
                    font.weight: Font.Medium
                    color: Style.textPrimary
                }
                
                Rectangle {
                    width: parent.width
                    height: buttonRow.height + Style.spacingLarge * 2
                    radius: Style.radiusLarge
                    color: Style.cardBackground
                    border.width: 1
                    border.color: Style.borderColor
                    
                    Flow {
                        id: buttonRow
                        anchors.centerIn: parent
                        width: parent.width - Style.spacingLarge * 2
                        spacing: Style.spacingLarge
                        
                        CustomButton {
                            text: "主要按钮"
                            isPrimary: true
                            width: 140
                        }
                        
                        CustomButton {
                            text: "次要按钮"
                            isPrimary: false
                            width: 140
                        }
                        
                        CustomButton {
                            text: "禁用按钮"
                            isPrimary: false
                            enabled: false
                            width: 140
                        }
                        
                        CustomButton {
                            text: "大圆角"
                            isPrimary: true
                            radius: Style.radiusXLarge
                            width: 140
                        }
                    }
                }
            }
            
            // ========== 开关组 ==========
            Column {
                width: parent.width
                spacing: Style.spacingMedium
                
                Text {
                    text: "开关 (Switches)"
                    font.pixelSize: Style.fontSizeTitle
                    font.weight: Font.Medium
                    color: Style.textPrimary
                }
                
                Rectangle {
                    width: parent.width
                    height: switchColumn.height + Style.spacingLarge * 2
                    radius: Style.radiusLarge
                    color: Style.cardBackground
                    border.width: 1
                    border.color: Style.borderColor
                    
                    Column {
                        id: switchColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.margins: Style.spacingLarge
                        spacing: Style.spacingMedium
                        
                        CustomSwitch {
                            label: "启用通知"
                            checked: true
                        }
                        
                        CustomSwitch {
                            label: "自动保存"
                            checked: false
                        }
                        
                        CustomSwitch {
                            label: "深色模式"
                            checked: false
                        }
                        
                        CustomSwitch {
                            label: "禁用状态"
                            checked: true
                            enabled: false
                        }
                    }
                }
            }
            
            // ========== 滑块组 ==========
            Column {
                width: parent.width
                spacing: Style.spacingMedium
                
                Text {
                    text: "滑块 (Sliders)"
                    font.pixelSize: Style.fontSizeTitle
                    font.weight: Font.Medium
                    color: Style.textPrimary
                }
                
                Rectangle {
                    width: parent.width
                    height: sliderColumn.height + Style.spacingLarge * 2
                    radius: Style.radiusLarge
                    color: Style.cardBackground
                    border.width: 1
                    border.color: Style.borderColor
                    
                    Column {
                        id: sliderColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.margins: Style.spacingLarge
                        spacing: Style.spacingLarge
                        
                        CustomSlider {
                            width: parent.width * 0.8
                            label: "音量"
                            value: 0.7
                            from: 0
                            to: 1
                        }
                        
                        CustomSlider {
                            width: parent.width * 0.8
                            label: "亮度"
                            value: 0.5
                            from: 0
                            to: 1
                        }
                        
                        CustomSlider {
                            width: parent.width * 0.8
                            label: "速度"
                            value: 1.5
                            from: 0.1
                            to: 3.0
                            decimals: 1
                        }
                    }
                }
            }
            
            // ========== 下拉框组 ==========
            Column {
                width: parent.width
                spacing: Style.spacingMedium
                
                Text {
                    text: "下拉框 (ComboBox)"
                    font.pixelSize: Style.fontSizeTitle
                    font.weight: Font.Medium
                    color: Style.textPrimary
                }
                
                Rectangle {
                    width: parent.width
                    height: comboRow.height + Style.spacingLarge * 2
                    radius: Style.radiusLarge
                    color: Style.cardBackground
                    border.width: 1
                    border.color: Style.borderColor
                    
                    Row {
                        id: comboRow
                        anchors.centerIn: parent
                        spacing: Style.spacingLarge
                        
                        CustomComboBox {
                            width: 200
                            label: "语言"
                            model: ["简体中文", "English", "日本語", "한국어"]
                            currentIndex: 0
                        }
                        
                        CustomComboBox {
                            width: 200
                            label: "主题"
                            model: ["浅色", "深色", "自动"]
                            currentIndex: 0
                        }
                        
                        CustomComboBox {
                            width: 200
                            label: "字体大小"
                            model: ["小", "中", "大", "特大"]
                            currentIndex: 1
                        }
                    }
                }
            }
            
            // ========== 卡片组 ==========
            Column {
                width: parent.width
                spacing: Style.spacingMedium
                
                Text {
                    text: "卡片 (Cards)"
                    font.pixelSize: Style.fontSizeTitle
                    font.weight: Font.Medium
                    color: Style.textPrimary
                }
                
                Row {
                    spacing: Style.spacingLarge
                    
                    // 信息卡片
                    Rectangle {
                        width: 250
                        height: 150
                        radius: Style.radiusLarge
                        color: Style.cardBackground
                        border.width: 1
                        border.color: Style.borderColor
                        
                        Column {
                            anchors.fill: parent
                            anchors.margins: Style.spacingLarge
                            spacing: Style.spacingMedium
                            
                            Text {
                                text: "📊 统计信息"
                                font.pixelSize: Style.fontSizeTitle
                                font.weight: Font.Medium
                                color: Style.textPrimary
                            }
                            
                            Text {
                                text: "总用户数"
                                font.pixelSize: Style.fontSizeSmall
                                color: Style.textSecondary
                            }
                            
                            Text {
                                text: "1,234"
                                font.pixelSize: 32
                                font.weight: Font.Bold
                                color: Style.accentColor
                            }
                        }
                    }
                    
                    // 操作卡片
                    Rectangle {
                        width: 250
                        height: 150
                        radius: Style.radiusLarge
                        color: Style.accentColor
                        
                        Column {
                            anchors.fill: parent
                            anchors.margins: Style.spacingLarge
                            spacing: Style.spacingMedium
                            
                            Text {
                                text: "🚀 快速操作"
                                font.pixelSize: Style.fontSizeTitle
                                font.weight: Font.Medium
                                color: Style.textOnAccent
                            }
                            
                            Text {
                                text: "点击开始新的项目"
                                font.pixelSize: Style.fontSizeMedium
                                color: Style.textOnAccent
                                wrapMode: Text.WordWrap
                                width: parent.width
                            }
                            
                            Item { height: Style.spacingSmall }
                            
                            CustomButton {
                                text: "开始"
                                isPrimary: false
                            }
                        }
                        
                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            
                            onEntered: parent.scale = 1.02
                            onExited: parent.scale = 1.0
                        }
                        
                        Behavior on scale {
                            NumberAnimation { duration: Style.animationNormal; easing.type: Easing.OutQuad }
                        }
                    }
                    
                    // 警告卡片
                    Rectangle {
                        width: 250
                        height: 150
                        radius: Style.radiusLarge
                        color: "#FFF3E0"
                        border.width: 1
                        border.color: "#FFB74D"
                        
                        Column {
                            anchors.fill: parent
                            anchors.margins: Style.spacingLarge
                            spacing: Style.spacingMedium
                            
                            Text {
                                text: "⚠️ 注意"
                                font.pixelSize: Style.fontSizeTitle
                                font.weight: Font.Medium
                                color: "#E65100"
                            }
                            
                            Text {
                                text: "这是一个警告消息示例，用于提醒用户注意重要信息。"
                                font.pixelSize: Style.fontSizeMedium
                                color: "#E65100"
                                wrapMode: Text.WordWrap
                                width: parent.width
                            }
                        }
                    }
                }
            }
            
            // ========== 进度条组 ==========
            Column {
                width: parent.width
                spacing: Style.spacingMedium
                
                Text {
                    text: "进度条 (Progress Bars)"
                    font.pixelSize: Style.fontSizeTitle
                    font.weight: Font.Medium
                    color: Style.textPrimary
                }
                
                Rectangle {
                    width: parent.width
                    height: progressColumn.height + Style.spacingLarge * 2
                    radius: Style.radiusLarge
                    color: Style.cardBackground
                    border.width: 1
                    border.color: Style.borderColor
                    
                    Column {
                        id: progressColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.margins: Style.spacingLarge
                        spacing: Style.spacingLarge
                        
                        // 进度条 1
                        Column {
                            width: parent.width * 0.8
                            spacing: Style.spacingSmall
                            
                            Row {
                                width: parent.width
                                
                                Text {
                                    text: "下载进度"
                                    font.pixelSize: Style.fontSizeMedium
                                    color: Style.textPrimary
                                }
                                
                                Item { width: Style.spacingSmall; height: 1 }
                                
                                Text {
                                    text: "75%"
                                    font.pixelSize: Style.fontSizeSmall
                                    color: Style.textSecondary
                                }
                            }
                            
                            Rectangle {
                                width: parent.width
                                height: 8
                                radius: 4
                                color: Style.sliderTrack
                                
                                Rectangle {
                                    width: parent.width * 0.75
                                    height: parent.height
                                    radius: 4
                                    color: Style.accentColor
                                }
                            }
                        }
                        
                        // 进度条 2
                        Column {
                            width: parent.width * 0.8
                            spacing: Style.spacingSmall
                            
                            Row {
                                width: parent.width
                                
                                Text {
                                    text: "上传进度"
                                    font.pixelSize: Style.fontSizeMedium
                                    color: Style.textPrimary
                                }
                                
                                Item { width: Style.spacingSmall; height: 1 }
                                
                                Text {
                                    text: "45%"
                                    font.pixelSize: Style.fontSizeSmall
                                    color: Style.textSecondary
                                }
                            }
                            
                            Rectangle {
                                width: parent.width
                                height: 8
                                radius: 4
                                color: Style.sliderTrack
                                
                                Rectangle {
                                    width: parent.width * 0.45
                                    height: parent.height
                                    radius: 4
                                    color: "#4CAF50"
                                }
                            }
                        }
                    }
                }
            }
            
            // ========== 标签组 ==========
            Column {
                width: parent.width
                spacing: Style.spacingMedium
                
                Text {
                    text: "标签 (Tags)"
                    font.pixelSize: Style.fontSizeTitle
                    font.weight: Font.Medium
                    color: Style.textPrimary
                }
                
                Rectangle {
                    width: parent.width
                    height: tagRow.height + Style.spacingLarge * 2
                    radius: Style.radiusLarge
                    color: Style.cardBackground
                    border.width: 1
                    border.color: Style.borderColor
                    
                    Row {
                        id: tagRow
                        anchors.centerIn: parent
                        spacing: Style.spacingMedium
                        
                        Rectangle {
                            width: tagText1.width + Style.spacingLarge
                            height: 28
                            radius: Style.radiusSmall
                            color: Style.accentColor
                            
                            Text {
                                id: tagText1
                                anchors.centerIn: parent
                                text: "新功能"
                                font.pixelSize: Style.fontSizeSmall
                                color: Style.textOnAccent
                            }
                        }
                        
                        Rectangle {
                            width: tagText2.width + Style.spacingLarge
                            height: 28
                            radius: Style.radiusSmall
                            color: "#4CAF50"
                            
                            Text {
                                id: tagText2
                                anchors.centerIn: parent
                                text: "推荐"
                                font.pixelSize: Style.fontSizeSmall
                                color: "#FFFFFF"
                            }
                        }
                        
                        Rectangle {
                            width: tagText3.width + Style.spacingLarge
                            height: 28
                            radius: Style.radiusSmall
                            color: "#FF9800"
                            
                            Text {
                                id: tagText3
                                anchors.centerIn: parent
                                text: "热门"
                                font.pixelSize: Style.fontSizeSmall
                                color: "#FFFFFF"
                            }
                        }
                        
                        Rectangle {
                            width: tagText4.width + Style.spacingLarge
                            height: 28
                            radius: Style.radiusSmall
                            color: Style.controlBackground
                            border.width: 1
                            border.color: Style.borderColor
                            
                            Text {
                                id: tagText4
                                anchors.centerIn: parent
                                text: "普通"
                                font.pixelSize: Style.fontSizeSmall
                                color: Style.textPrimary
                            }
                        }
                    }
                }
            }
            
            // 底部间距
            Item { width: 1; height: Style.spacingXLarge }
        }
    }
}
