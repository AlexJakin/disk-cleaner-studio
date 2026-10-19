import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool primary: false
    property bool subtle: false
    property string glyph: ""
    property string hint: ""
    implicitHeight: 38
    implicitWidth: Math.max(78, label.implicitWidth + 28 + (glyph ? 22 : 0))
    leftPadding: 14
    rightPadding: 14
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 0.43
    font.family: "Microsoft YaHei UI"
    font.pixelSize: 12
    font.weight: Font.Medium
    contentItem: Item {
        implicitWidth: label.implicitWidth + (control.glyph ? 22 : 0)
        implicitHeight: 20
        Row {
            anchors.centerIn: parent
            spacing: 7
            Icon {
                visible: control.glyph !== ""
                width: 15; height: 15
                anchors.verticalCenter: parent.verticalCenter
                name: control.glyph
                ink: control.primary ? "#ffffff" : "#52676a"
            }
            Text {
                id: label
                text: control.text
                font: control.font
                color: control.primary ? "#ffffff" : "#294448"
            }
        }
    }
    background: Rectangle {
        radius: 7
        color: control.primary ? (control.down ? "#125d57" : control.hovered ? "#208278" : "#18766d")
                               : control.down ? "#e6eeec" : control.hovered ? "#edf3f1" : control.subtle ? "transparent" : "#ffffff"
        border.width: control.activeFocus ? 2 : control.primary || control.subtle ? 0 : 1
        border.color: control.activeFocus ? "#6aafa2" : "#dce5e2"
    }
    ToolTip.visible: hovered && hint !== ""
    ToolTip.delay: 500
    ToolTip.text: hint
}
