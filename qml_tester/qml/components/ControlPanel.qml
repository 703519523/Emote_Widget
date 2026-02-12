import QtQuick 2.15
import QtQuick.Controls 2.15
import ".."

Rectangle {
    id: root
    
    property string title: ""
    property int currentTab: 0
    
    color: Style.sidebarBackground
    
    Column {
        anchors.fill: parent
        anchors.margins: Style.spacingLarge
        spacing: Style.spacingLarge
        
        // 标题
        Text {
            text: "控制面板"
            font.pixelSize: Style.fontSizeHeader
            font.weight: Font.Bold
            color: Style.textPrimary
        }
        
        // 分割线
        Rectangle {
            width: parent.width
            height: 1
            color: Style.dividerColor
        }
        
        // 侧边栏导航
        Column {
            width: parent.width
            spacing: Style.spacingTiny
            
            SidebarItem {
                width: parent.width
                text: "基础设置"
                icon: "⚙"
                selected: root.currentTab === 0
                onClicked: root.currentTab = 0
            }
            
            SidebarItem {
                width: parent.width
                text: "动画控制"
                icon: "🎬"
                selected: root.currentTab === 1
                onClicked: root.currentTab = 1
            }
            
            SidebarItem {
                width: parent.width
                text: "物理效果"
                icon: "⚡"
                selected: root.currentTab === 2
                onClicked: root.currentTab = 2
            }
            
            SidebarItem {
                width: parent.width
                text: "高级选项"
                icon: "🔧"
                selected: root.currentTab === 3
                onClicked: root.currentTab = 3
            }
        }
        
        // 分割线
        Rectangle {
            width: parent.width
            height: 1
            color: Style.dividerColor
        }
        
        // 控制区域（根据选中的 Tab 显示不同内容）
        ScrollView {
            width: parent.width
            height: parent.height - y
            clip: true
            
            Column {
                width: parent.width
                spacing: Style.spacingLarge
                
                // 基础设置
                Column {
                    visible: root.currentTab === 0
                    width: parent.width
                    spacing: Style.spacingMedium
                    
                    opacity: visible ? 1 : 0
                    
                    Behavior on opacity {
                        NumberAnimation { duration: Style.animationNormal }
                    }
                    
                    Text {
                        text: "基础设置"
                        font.pixelSize: Style.fontSizeTitle
                        font.weight: Font.Medium
                        color: Style.textPrimary
                    }
                    
                    CustomSlider {
                        width: parent.width
                        label: "缩放比例"
                        value: 1.0
                        from: 0.5
                        to: 2.0
                    }
                    
                    CustomSlider {
                        width: parent.width
                        label: "透明度"
                        value: 1.0
                        from: 0
                        to: 1
                    }
                    
                    CustomSwitch {
                        width: parent.width
                        label: "显示边框"
                        checked: true
                    }
                    
                    CustomComboBox {
                        width: parent.width
                        label: "渲染质量"
                        model: ["低", "中", "高", "超高"]
                        currentIndex: 2
                    }
                }
                
                // 动画控制
                Column {
                    visible: root.currentTab === 1
                    width: parent.width
                    spacing: Style.spacingMedium
                    
                    opacity: visible ? 1 : 0
                    
                    Behavior on opacity {
                        NumberAnimation { duration: Style.animationNormal }
                    }
                    
                    Text {
                        text: "动画控制"
                        font.pixelSize: Style.fontSizeTitle
                        font.weight: Font.Medium
                        color: Style.textPrimary
                    }
                    
                    CustomSlider {
                        width: parent.width
                        label: "动画速度"
                        value: 1.0
                        from: 0.1
                        to: 3.0
                    }
                    
                    CustomSwitch {
                        width: parent.width
                        label: "循环播放"
                        checked: true
                    }
                    
                    CustomSwitch {
                        width: parent.width
                        label: "自动播放"
                        checked: false
                    }
                    
                    CustomComboBox {
                        width: parent.width
                        label: "动画模式"
                        model: ["待机", "说话", "移动", "表情"]
                        currentIndex: 0
                    }
                }
                
                // 物理效果
                Column {
                    visible: root.currentTab === 2
                    width: parent.width
                    spacing: Style.spacingMedium
                    
                    opacity: visible ? 1 : 0
                    
                    Behavior on opacity {
                        NumberAnimation { duration: Style.animationNormal }
                    }
                    
                    Text {
                        text: "物理效果"
                        font.pixelSize: Style.fontSizeTitle
                        font.weight: Font.Medium
                        color: Style.textPrimary
                    }
                    
                    CustomSlider {
                        width: parent.width
                        label: "重力强度"
                        value: 0.5
                        from: 0
                        to: 1
                    }
                    
                    CustomSlider {
                        width: parent.width
                        label: "风力强度"
                        value: 0.3
                        from: 0
                        to: 1
                    }
                    
                    CustomSwitch {
                        width: parent.width
                        label: "启用物理"
                        checked: true
                    }
                }
                
                // 高级选项
                Column {
                    visible: root.currentTab === 3
                    width: parent.width
                    spacing: Style.spacingMedium
                    
                    opacity: visible ? 1 : 0
                    
                    Behavior on opacity {
                        NumberAnimation { duration: Style.animationNormal }
                    }
                    
                    Text {
                        text: "高级选项"
                        font.pixelSize: Style.fontSizeTitle
                        font.weight: Font.Medium
                        color: Style.textPrimary
                    }
                    
                    CustomSwitch {
                        width: parent.width
                        label: "调试模式"
                        checked: false
                    }
                    
                    CustomSwitch {
                        width: parent.width
                        label: "性能监控"
                        checked: false
                    }
                    
                    CustomComboBox {
                        width: parent.width
                        label: "日志级别"
                        model: ["关闭", "错误", "警告", "信息", "调试"]
                        currentIndex: 2
                    }
                    
                    CustomButton {
                        text: "重置所有设置"
                        width: parent.width
                    }
                }
            }
        }
    }
}
