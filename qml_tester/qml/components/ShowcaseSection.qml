import QtQuick 2.15
import QtQuick.Layouts 1.15
import ".."

Column {
    id: root
    
    property string title: ""
    default property alias contentData: contentContainer.data
    
    spacing: Style.spacingMedium
    width: parent.width
    
    // 标题
    Text {
        width: parent.width
        text: root.title
        font.pixelSize: Style.fontSizeTitle
        font.weight: Font.Medium
        color: Style.textPrimary
    }
    
    // 内容容器
    Rectangle {
        width: parent.width
        height: contentContainer.implicitHeight + Style.spacingLarge * 2
        radius: Style.radiusLarge
        color: Style.cardBackground
        border.width: 1
        border.color: Style.borderColor
        
        // 细腻阴影
        layer.enabled: true
        layer.effect: Item {
            Rectangle {
                anchors.fill: parent
                anchors.margins: -6
                anchors.topMargin: 2
                radius: Style.radiusLarge + 6
                color: Style.shadowColor
                z: -1
                opacity: 0.06
            }
        }
        
        Column {
            id: contentContainer
            anchors.fill: parent
            anchors.margins: Style.spacingLarge
        }
    }
}
