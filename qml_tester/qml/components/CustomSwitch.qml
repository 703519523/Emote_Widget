import QtQuick 2.15
import QtQuick.Controls 2.15
import ".."

Item {
    id: control
    
    property string label: ""
    property bool checked: false
    
    implicitWidth: parent ? parent.width : 300
    implicitHeight: 40
    
    Row {
        anchors.fill: parent
        spacing: Style.spacingXLarge
        
        // 开关控件 - 直接使用 Switch，不包裹在 Item 中
        Switch {
            id: switchControl
            width: 50
            height: parent.height
            checked: control.checked
            
            onCheckedChanged: control.checked = checked
            
            indicator: Rectangle {
                implicitWidth: 44
                implicitHeight: 24
                anchors.centerIn: parent
                radius: 12
                color: switchControl.checked ? Style.switchTrackOn : Style.switchTrackOff
                
                Behavior on color {
                    ColorAnimation { duration: Style.animationNormal }
                }
                
                Rectangle {
                    x: switchControl.checked ? parent.width - width - 3 : 3
                    anchors.verticalCenter: parent.verticalCenter
                    width: 18
                    height: 18
                    radius: 9
                    color: "#FFFFFF"
                    
                    Behavior on x {
                        NumberAnimation {
                            duration: Style.animationNormal
                            easing.type: Easing.InOutQuad
                        }
                    }
                    
                    // 圆形把手阴影
                    Rectangle {
                        anchors.centerIn: parent
                        width: parent.width + 4
                        height: parent.height + 4
                        radius: width / 2
                        color: Style.shadowColor
                        z: -1
                        opacity: 0.2
                    }
                }
            }
            
            contentItem: Item {}
        }
        
        // 标签
        Text {
            visible: control.label !== ""
            anchors.verticalCenter: parent.verticalCenter
            text: control.label
            font.pixelSize: Style.fontSizeMedium
            color: control.enabled ? Style.textPrimary : Style.textSecondary
            
            Behavior on color {
                ColorAnimation { duration: Style.animationFast }
            }
            
            MouseArea {
                anchors.fill: parent
                anchors.margins: -Style.spacingSmall
                onClicked: {
                    if (control.enabled) {
                        control.checked = !control.checked
                    }
                }
                cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ForbiddenCursor
            }
        }
    }
}
