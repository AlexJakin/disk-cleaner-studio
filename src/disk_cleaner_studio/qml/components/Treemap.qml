import QtQuick
import QtQuick.Controls
import "../lib/Treemap.js" as MapLayout
import "../lib/Format.js" as Fmt

Item {
    id: chart
    property var entries: []
    property string selectedPath: ""
    property var tiles: MapLayout.layout(entries, width, height)
    property var swatches: ["#c7e1d7", "#d8e5e9", "#e4e7d8", "#dcdfea", "#d8e9e1", "#eee4d5", "#dfdce7", "#d7e4e0"]
    signal selected(string path)
    signal entered(string path)
    clip: true
    Repeater {
        model: chart.tiles
        delegate: Rectangle {
            id: tile
            required property var modelData
            objectName: "mapTile_" + modelData.data.path
            x: modelData.x + 2.5; y: modelData.y + 2.5
            width: Math.max(0, modelData.w - 5); height: Math.max(0, modelData.h - 5)
            radius: Math.min(7, width/4, height/4)
            color: chart.swatches[modelData.rank % chart.swatches.length]
            border.color: chart.selectedPath === modelData.data.path ? "#347c65" : hit.containsMouse ? "#82a99b" : "transparent"
            border.width: 2
            activeFocusOnTab: true
            Accessible.role: Accessible.Button
            Accessible.name: modelData.data.name + "，" + Fmt.bytes(modelData.data.size)
            Keys.onReturnPressed: chart.selected(modelData.data.path)
            Keys.onSpacePressed: chart.selected(modelData.data.path)
            Keys.onRightPressed: { if (modelData.data.is_dir) chart.entered(modelData.data.path); }
            Rectangle { anchors.fill: parent; color: "transparent"; border.width: tile.activeFocus ? 2 : 0; border.color: "#347c65"; radius: tile.radius }
            Column {
                visible: tile.width > 66 && tile.height > 43
                anchors.fill: parent; anchors.margins: Math.min(15, tile.width / 12); spacing: 6
                Text { width: parent.width; text: tile.modelData.data.name || tile.modelData.data.path; color: "#39554b"; font.pixelSize: tile.width > 160 ? 13 : 11; font.weight: Font.Medium; elide: Text.ElideMiddle }
                Text { visible: tile.height > 66; width: parent.width; text: Fmt.bytes(tile.modelData.data.size); color: "#2c4c40"; font.pixelSize: tile.width > 170 && tile.height > 100 ? 24 : 14; font.family: "Segoe UI"; font.weight: Font.DemiBold; elide: Text.ElideRight }
            }
            MouseArea {
                id: hit; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                onClicked: { tile.forceActiveFocus(); chart.selected(tile.modelData.data.path); }
                onDoubleClicked: { if (tile.modelData.data.is_dir) chart.entered(tile.modelData.data.path); }
            }
            ToolTip.visible: hit.containsMouse
            ToolTip.delay: 550
            ToolTip.text: modelData.data.path + "\n" + Fmt.bytes(modelData.data.size) + (modelData.data.is_dir ? " · 双击进入目录" : "")
        }
    }
    Text { visible: chart.tiles.length === 0; anchors.centerIn: parent; text: "当前目录没有可显示的占用数据"; color: "#607368"; font.pixelSize: 12 }
}
