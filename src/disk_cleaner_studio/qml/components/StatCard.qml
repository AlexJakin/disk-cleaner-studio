import QtQuick
import QtQuick.Layouts

Panel {
    id: card
    property string label: ""
    property string value: "—"
    property string note: ""
    property string glyph: "disk"
    property bool accent: false
    property real ratio: -1
    implicitHeight: 116
    color: accent ? "#edf6f1" : "#ffffff"
    border.color: accent ? "#d6e9df" : "#e2e9e6"
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 18; spacing: 6
        RowLayout {
            Text { text: card.label; color: "#5f746a"; font.pixelSize: 11; Layout.fillWidth: true }
            Icon { name: card.glyph; width: 17; height: 17; ink: card.accent ? "#4f9076" : "#90a59b" }
        }
        Text { text: card.value; color: card.accent ? "#216e53" : "#253d36"; font.pixelSize: 27; font.weight: Font.DemiBold; font.family: "Segoe UI" }
        RowLayout {
            Text { text: card.note; color: "#617369"; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
            Rectangle {
                visible: card.ratio >= 0
                Layout.preferredWidth: 72; Layout.preferredHeight: 4; radius: 2; color: "#e8eeea"
                Rectangle { width: parent.width * Math.min(1, Math.max(0, card.ratio)); height: 4; radius: 2; color: "#6f9f89" }
            }
        }
    }
}
