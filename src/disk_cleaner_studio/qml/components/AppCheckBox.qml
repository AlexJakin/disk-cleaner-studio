import QtQuick
import QtQuick.Controls

CheckBox {
    id: control
    implicitWidth: text ? 32 + label.implicitWidth : 28
    implicitHeight: 28
    spacing: 9
    font.pixelSize: 11
    hoverEnabled: true
    indicator: Rectangle {
        x: 4; y: Math.round((control.height-height)/2)
        width: 18; height: 18; radius: 4
        color: control.checked ? "#357e63" : control.enabled ? "#ffffff" : "#f5f7f3"
        border.width: control.activeFocus ? 2 : 1
        border.color: control.checked ? "#357e63" : control.enabled ? "#b6c9bc" : "#d7e0d5"
        Icon { anchors.centerIn: parent; width: 12; height: 12; name: "check"; ink: "#ffffff"; visible: control.checked }
    }
    contentItem: Text {
        id: label
        leftPadding: 31
        verticalAlignment: Text.AlignVCenter
        text: control.text
        font: control.font
        color: control.enabled ? "#617858" : "#859580"
        wrapMode: Text.Wrap
    }
}
