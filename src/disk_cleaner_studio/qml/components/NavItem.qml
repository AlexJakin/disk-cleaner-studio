import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool current: false
    property string glyph: "explore"
    property string count: ""
    implicitHeight: 44
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    background: Rectangle {
        radius: 8
        color: control.current ? "#e4f1ec" : control.hovered ? "#f1f5f3" : "transparent"
        border.color: control.activeFocus ? "#7bb8a9" : "transparent"
    }
    contentItem: Item {
        Icon { x: 13; anchors.verticalCenter: parent.verticalCenter; name: control.glyph; width: 18; height: 18; ink: control.current ? "#21766b" : "#81938d" }
        Text { x: 43; anchors.verticalCenter: parent.verticalCenter; text: control.text; color: control.current ? "#1c6d63" : "#5a6e68"; font.pixelSize: 13; font.weight: control.current ? Font.DemiBold : Font.Normal; font.family: "Microsoft YaHei UI" }
        Text { anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: control.count; color: "#56756b"; font.pixelSize: 11 }
    }
}
