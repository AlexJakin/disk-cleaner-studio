import QtQuick
import QtQuick.Controls

ComboBox {
    id: control
    implicitHeight: 34
    implicitWidth: 120
    font.pixelSize: 11
    leftPadding: 10
    rightPadding: 27
    background: Rectangle { radius: 6; color: control.down ? "#edf4eb" : "#f9fbf7"; border.color: control.activeFocus ? "#8aaf8d" : "#e3eae0" }
    contentItem: Text { text: control.displayText; font: control.font; color: "#647e5d"; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
    indicator: Icon { x: control.width-width-10; y: (control.height-height)/2; width: 11; height: 11; name: "chevron"; ink: "#7f9875"; rotation: 90 }
}
