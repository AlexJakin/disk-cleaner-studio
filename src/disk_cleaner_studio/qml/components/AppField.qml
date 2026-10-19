import QtQuick
import QtQuick.Controls

TextField {
    id: field
    implicitHeight: 38
    padding: 11
    font.pixelSize: 12
    color: "#496351"
    placeholderTextColor: "#a1afa3"
    selectByMouse: true
    background: Rectangle { color: field.enabled ? "#fcfdfb" : "#f2f5f1"; radius: 7; border.color: field.activeFocus ? "#7ead91" : "#dfe7df"; border.width: field.activeFocus ? 2 : 1 }
}
