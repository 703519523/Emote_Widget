import QtQuick 2.15
import QtQuick.Controls 2.15
import ".."

Item {
    id: control
    
    property string text: ""
    property string icon: ""
    property bool selected: false
    
    signal clicked()
    
    implicitWidth: 240
    implicitHeight: 40
    
    Rectangle {
        id: background
        anchors.fill: parent
        anchors.leftMargin: Style.spacingSmall
        anchors.rightMargin: Style.spacingSmall
        radius: Style.radiusMedium
        color: {
            if (control.selected) return Style.accentColor
            if (mouseArea.containsMouse) return Style.controlHover
            return "transparent"
        }
        
        Behavior on color {
            ColorAnimation { duration: Style.animationNormal }
        }
        
        Row {
            anchors.fill: parent
            anchors.leftMargin: Style.spacingMedium
            anchors.rightMargin: Style.spacingMedium
            spacing: Style.spacingMedium
            
            // 图标（使用文字代替）
            Text {
                visible: control.icon !== ""
                anchors.verticalCenter: parent.verticalCenter
                text: control.icon
                font.pixelSize: Style.fontSizeLarge
                font.bold: true
                color: control.selected ? Style.textOnAccent : Style.textPrimary
                
                Behavior on color {
                    ColorAnimation { duration: Style.animationNormal }
                }
            }
            
            // 文字
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: control.text
                font.pixelSize: Style.fontSizeMedium
                font.weight: control.selected ? Font.Medium : Font.Normal
                color: control.selected ? Style.textOnAccent : Style.textPrimary
                
                Behavior on color {
                    ColorAnimation { duration: Style.animationNormal }
                }
            }
        }
        
        // 选中指示器
        Rectangle {
            visible: control.selected
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: 3
            height: parent.height * 0.6
            radius: 1.5
            color: Style.textOnAccent
        }
    }
    
    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        
        onClicked: control.clicked()
    }
    
    // 点击缩放效果
    scale: mouseArea.pressed ? 0.98 : 1.0
    
    Behavior on scale {
        NumberAnimation {
            duration: Style.animationFast
            easing.type: Easing.OutQuad
        }
    }
}
