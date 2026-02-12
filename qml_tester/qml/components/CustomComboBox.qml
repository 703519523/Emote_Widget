import QtQuick 2.15
import QtQuick.Controls 2.15
import ".."

Item {
    id: control
    
    property string label: ""
    property var model: []
    property int currentIndex: 0
    property string currentText: model.length > 0 ? model[currentIndex] : ""
    
    implicitWidth: 200
    implicitHeight: label !== "" ? 52 : 32
    
    // 标签
    Text {
        id: labelText
        visible: control.label !== ""
        anchors.top: parent.top
        anchors.left: parent.left
        text: control.label
        font.pixelSize: Style.fontSizeMedium
        color: Style.textPrimary
        height: visible ? 20 : 0
    }
    
    // 下拉框
    ComboBox {
        id: comboBox
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 32
        
        model: control.model
        currentIndex: control.currentIndex
        
        onCurrentIndexChanged: control.currentIndex = currentIndex
        
        delegate: ItemDelegate {
            width: comboBox.width
            height: 32
            
            contentItem: Text {
                text: modelData
                color: Style.textPrimary
                font.pixelSize: Style.fontSizeMedium
                verticalAlignment: Text.AlignVCenter
                leftPadding: Style.spacingMedium
            }
            
            background: Rectangle {
                color: highlighted ? Style.controlHover : "transparent"
                
                Behavior on color {
                    ColorAnimation { duration: Style.animationFast }
                }
            }
            
            highlighted: comboBox.highlightedIndex === index
        }
        
        indicator: Canvas {
            id: canvas
            x: comboBox.width - width - comboBox.rightPadding
            y: comboBox.topPadding + (comboBox.availableHeight - height) / 2
            width: 10
            height: 6
            contextType: "2d"
            
            Connections {
                target: comboBox
                function onPressedChanged() { canvas.requestPaint() }
            }
            
            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                ctx.moveTo(0, 0)
                ctx.lineTo(width, 0)
                ctx.lineTo(width / 2, height)
                ctx.closePath()
                ctx.fillStyle = Style.textSecondary
                ctx.fill()
            }
        }
        
        contentItem: Text {
            leftPadding: Style.spacingMedium
            rightPadding: comboBox.indicator.width + comboBox.spacing
            text: comboBox.displayText
            font.pixelSize: Style.fontSizeMedium
            color: Style.textPrimary
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        
        background: Rectangle {
            implicitWidth: 120
            implicitHeight: 32
            radius: Style.radiusSmall
            color: comboBox.pressed ? Style.controlPressed : 
                   comboBox.hovered ? Style.controlHover : Style.controlBackground
            border.color: comboBox.pressed ? Style.accentColor : Style.borderColor
            border.width: 1
            
            Behavior on color {
                ColorAnimation { duration: Style.animationFast }
            }
            
            Behavior on border.color {
                ColorAnimation { duration: Style.animationFast }
            }
        }
        
        popup: Popup {
            y: comboBox.height + 4
            width: comboBox.width
            implicitHeight: contentItem.implicitHeight + 8
            padding: 4
            
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: comboBox.popup.visible ? comboBox.delegateModel : null
                currentIndex: comboBox.highlightedIndex
                ScrollIndicator.vertical: ScrollIndicator {}
            }
            
            background: Rectangle {
                radius: Style.radiusSmall
                color: Style.cardBackground
                border.color: Style.borderColor
                border.width: 1
                
                // 阴影效果
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: -4
                    anchors.topMargin: 2
                    radius: Style.radiusSmall + 4
                    color: Style.shadowColor
                    z: -1
                    opacity: 0.15
                }
            }
            
            enter: Transition {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Style.animationFast }
                NumberAnimation { property: "scale"; from: 0.95; to: 1; duration: Style.animationFast }
            }
            
            exit: Transition {
                NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Style.animationFast }
            }
        }
    }
}
