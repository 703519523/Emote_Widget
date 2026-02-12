import QtQuick 2.15
import QtQuick.Controls 2.15
import ".."

Item {
    id: control
    
    property string label: ""
    property real value: 0.5
    property real from: 0
    property real to: 1
    property real stepSize: 0.01
    property bool showValue: true
    property int decimals: 2
    
    implicitWidth: 200
    implicitHeight: label !== "" ? 52 : 28
    
    // 标签行
    Row {
        id: labelRow
        visible: label !== ""
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: visible ? 20 : 0
        
        Text {
            text: control.label
            font.pixelSize: Style.fontSizeMedium
            color: Style.textPrimary
        }
        
        Item { width: Style.spacingSmall; height: 1 }
        
        Text {
            visible: control.showValue
            text: control.value.toFixed(control.decimals)
            font.pixelSize: Style.fontSizeSmall
            color: Style.textSecondary
        }
    }
    
    // 滑块
    Slider {
        id: slider
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 28
        
        from: control.from
        to: control.to
        stepSize: control.stepSize
        value: control.value
        
        onValueChanged: control.value = value
        
        background: Rectangle {
            x: slider.leftPadding
            y: slider.topPadding + slider.availableHeight / 2 - height / 2
            implicitWidth: 200
            implicitHeight: 4
            width: slider.availableWidth
            height: implicitHeight
            radius: 2
            color: Style.sliderTrack
            
            Rectangle {
                width: slider.visualPosition * parent.width
                height: parent.height
                color: Style.accentColor
                radius: 2
                
                Behavior on width {
                    NumberAnimation { duration: 50 }
                }
            }
        }
        
        handle: Rectangle {
            x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
            y: slider.topPadding + slider.availableHeight / 2 - height / 2
            implicitWidth: 18
            implicitHeight: 18
            radius: 9
            color: slider.pressed ? Style.accentPressed : Style.accentColor
            border.color: Qt.lighter(Style.accentColor, 1.2)
            border.width: 2
            
            scale: slider.pressed ? 1.1 : (slider.hovered ? 1.05 : 1.0)
            
            Behavior on scale {
                NumberAnimation { duration: Style.animationFast; easing.type: Easing.OutQuad }
            }
            
            Behavior on color {
                ColorAnimation { duration: Style.animationFast }
            }
            
            // 阴影效果
            Rectangle {
                anchors.centerIn: parent
                width: parent.width + 6
                height: parent.height + 6
                radius: width / 2
                color: Style.shadowColor
                z: -1
                opacity: slider.pressed ? 0.3 : 0.15
                
                Behavior on opacity {
                    NumberAnimation { duration: Style.animationFast }
                }
            }
        }
    }
}
