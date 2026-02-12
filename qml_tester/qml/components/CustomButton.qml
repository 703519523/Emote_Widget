import QtQuick 2.15
import QtQuick.Controls 2.15
import ".."

Button {
    id: control
    
    property bool isPrimary: false
    property int radius: Style.radiusMedium
    
    implicitWidth: Math.max(80, contentItem.implicitWidth + 24)
    implicitHeight: 36
    
    contentItem: Text {
        text: control.text
        font.pixelSize: Style.fontSizeMedium
        font.weight: Font.Medium
        color: control.isPrimary ? Style.textOnAccent : Style.textPrimary
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        
        Behavior on color {
            ColorAnimation { duration: Style.animationFast }
        }
    }
    
    background: Rectangle {
        id: bg
        radius: control.radius
        color: {
            if (control.isPrimary) {
                if (control.pressed) return Style.accentPressed
                if (control.hovered) return Style.accentHover
                return Style.accentColor
            } else {
                if (control.pressed) return Style.buttonSecondaryPressed
                if (control.hovered) return Style.buttonSecondaryHover
                return Style.buttonSecondary
            }
        }
        border.width: control.isPrimary ? 0 : 2
        border.color: control.isPrimary ? "transparent" : Style.buttonBorder
        
        Behavior on color {
            ColorAnimation { duration: Style.animationFast }
        }
        
        // 细腻阴影
        layer.enabled: true
        layer.effect: Item {
            id: shadowEffect
            
            Rectangle {
                anchors.fill: parent
                anchors.margins: -2
                anchors.topMargin: 0
                radius: control.radius + 2
                color: "transparent"
                
                Rectangle {
                    anchors.fill: parent
                    anchors.topMargin: 2
                    radius: parent.radius
                    color: Style.shadowColorLight
                    opacity: control.hovered ? 0.8 : 0.5
                    
                    Behavior on opacity {
                        NumberAnimation { duration: Style.animationFast }
                    }
                }
            }
        }
    }
    
    // 点击缩放动画
    scale: control.pressed ? 0.97 : 1.0
    
    Behavior on scale {
        NumberAnimation {
            duration: Style.animationFast
            easing.type: Easing.OutQuad
        }
    }
}
