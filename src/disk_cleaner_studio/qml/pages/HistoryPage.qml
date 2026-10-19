import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../lib/Format.js" as Fmt

Item {
    id: page
    signal scanLoaded()
    RowLayout {
        anchors.fill: parent; spacing: 16
        Panel {
            Layout.preferredWidth: Math.min(420, page.width * 0.46); Layout.fillHeight: true
            ColumnLayout {
                anchors.fill: parent; spacing: 0
                RowLayout { Layout.fillWidth: true; Layout.margins: 20; Text { text: "扫描记录"; color: "#3c5844"; font.pixelSize: 14; font.weight: Font.DemiBold; Layout.fillWidth: true } Text { text: backend.history.length + " 份"; color: "#617363"; font.pixelSize: 11 } }
                Rectangle { Layout.fillWidth: true; height: 1; color: "#edf1e9" }
                ListView {
                    id: historyList; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                    model: backend.history; boundsBehavior: Flickable.StopAtBounds; ScrollBar.vertical: ScrollBar { }
                    delegate: ItemDelegate {
                        id: row; required property var modelData
                        width: historyList.width; height: 124; hoverEnabled: true; enabled: !backend.busy
                        background: Rectangle { color: row.hovered ? "#f4f8ee" : "transparent"; Rectangle { width: parent.width; height: 1; anchors.bottom: parent.bottom; color: "#eef2e8" } }
                        contentItem: ColumnLayout {
                            spacing: 8
                            RowLayout { Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; Icon { name: "disk"; width: 16; height: 16 } Text { text: row.modelData.root || "扫描结果"; font.pixelSize: 13; color: "#526d48"; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideMiddle } Text { text: row.modelData.is_demo ? "示例" : "本地"; color: "#60745c"; font.pixelSize: 11 } }
                            Text { Layout.leftMargin: 12; text: Fmt.date(row.modelData.scanned_at); color: "#62745d"; font.pixelSize: 11 }
                            Text { Layout.leftMargin: 12; Layout.rightMargin: 12; Layout.fillWidth: true; text: Number(row.modelData.entry_count || 0).toLocaleString() + " 条记录  ·  建议检查 " + Fmt.bytes(row.modelData.candidate_bytes); color: "#62745e"; font.pixelSize: 11; elide: Text.ElideRight }
                        }
                        onClicked: { backend.loadScan(modelData.id); page.scanLoaded(); }
                        ToolTip.visible: hovered; ToolTip.text: "载入这份扫描结果"
                    }
                    Text { visible: historyList.count === 0; anchors.centerIn: parent; text: "还没有扫描记录"; color: "#617460"; font.pixelSize: 12 }
                }
            }
        }
        Panel {
            Layout.fillWidth: true; Layout.fillHeight: true
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 20; spacing: 12
                Text { text: "空间变化"; color: "#405c42"; font.pixelSize: 15; font.weight: Font.DemiBold }
                Text { Layout.fillWidth: true; text: "当前扫描与同一位置的上一份记录比较，按变化大小列出。"; wrapMode: Text.Wrap; color: "#627460"; font.pixelSize: 11; lineHeight: 1.5 }
                Rectangle { Layout.fillWidth: true; height: 1; color: "#ebf0e5"; Layout.topMargin: 3 }
                RowLayout { Layout.fillWidth: true; Text { text: "路径 / 当前分配空间"; color: "#627360"; font.pixelSize: 11; Layout.fillWidth: true } Text { text: "分配空间变化"; color: "#627360"; font.pixelSize: 11 } }
                ListView {
                    id: comparisonList; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                    model: backend.comparison; boundsBehavior: Flickable.StopAtBounds; ScrollBar.vertical: ScrollBar { }
                    delegate: Item {
                        required property var modelData
                        width: comparisonList.width; height: 63
                        RowLayout {
                            anchors.fill: parent; spacing: 10
                            ColumnLayout { Layout.fillWidth: true; spacing: 6; Text { text: modelData.path; color: "#5d7653"; font.pixelSize: 11; font.family: "Consolas"; Layout.fillWidth: true; elide: Text.ElideMiddle } Text { text: Fmt.bytes(modelData.previous) + "  →  " + Fmt.bytes(modelData.current); color: "#62745e"; font.pixelSize: 11 } }
                            Text { text: (modelData.delta > 0 ? "+" : "") + Fmt.bytes(modelData.delta); color: modelData.delta > 0 ? "#b18b4b" : "#6c9a63"; font.pixelSize: 12; font.family: "Segoe UI"; Layout.rightMargin: 6 }
                        }
                        MouseArea { id: comparisonHover; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                        ToolTip.visible: comparisonHover.containsMouse; ToolTip.text: modelData.path
                    }
                    Column { visible: comparisonList.count === 0; anchors.centerIn: parent; width: parent.width; spacing: 13; Icon { name: "history"; width: 35; height: 35; ink: "#bfceb0"; anchors.horizontalCenter: parent.horizontalCenter } Text { width: parent.width; text: "有可比较的两次扫描后，\n在这里查看目录空间的增减。"; horizontalAlignment: Text.AlignHCenter; color: "#617461"; font.pixelSize: 12; lineHeight: 1.6 } }
                }
            }
        }
    }
}
