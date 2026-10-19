import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../lib/Format.js" as Fmt

Panel {
    id: panel
    objectName: "detailPane"
    property var itemData: ({})
    property bool demo: false
    property bool taskBusy: false
    signal openLocation(string path)
    signal ignoreItem(string id)
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 18; spacing: 13
        RowLayout {
            Text { text: "项目详情"; color: "#365148"; font.pixelSize: 13; font.weight: Font.DemiBold; Layout.fillWidth: true }
            Icon { name: "info"; width: 16; height: 16; ink: "#91a29a" }
        }
        Item {
            visible: !panel.itemData.path
            Layout.fillWidth: true; Layout.fillHeight: true
            Column {
                anchors.centerIn: parent; width: parent.width; spacing: 15
                Icon { anchors.horizontalCenter: parent.horizontalCenter; name: "folder"; width: 38; height: 38; ink: "#b9ccc3" }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: "选择一个项目"; color: "#5f7468"; font.pixelSize: 13 }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; text: "查看完整路径、空间占用\n和清理建议的判断依据"; color: "#617368"; font.pixelSize: 11; lineHeight: 1.5 }
            }
        }
        ScrollView {
            visible: !!panel.itemData.path
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ColumnLayout {
                width: panel.width - 38; spacing: 13
                Rectangle {
                    visible: !!panel.itemData.id
                    implicitWidth: riskLabel.implicitWidth + 18; implicitHeight: 25; radius: 5
                    color: panel.itemData.risk === "low" ? "#e7f2eb" : "#f5eedf"
                    Text { id: riskLabel; anchors.centerIn: parent; text: Fmt.risk(panel.itemData.risk, panel.itemData.cleanable); color: panel.itemData.risk === "low" ? "#377858" : "#8a703d"; font.pixelSize: 11 }
                }
                Text { Layout.fillWidth: true; text: panel.itemData.name || ""; color: "#29463a"; font.pixelSize: 17; font.weight: Font.DemiBold; wrapMode: Text.Wrap }
                TextArea {
                    Layout.fillWidth: true
                    text: panel.itemData.path || ""
                    readOnly: true; selectByMouse: true; wrapMode: TextEdit.WrapAnywhere
                    padding: 0; font.pixelSize: 11; font.family: "Consolas"; color: "#607368"
                    background: null
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: "#edf1ed" }
                GridLayout {
                    Layout.fillWidth: true; columns: 2; columnSpacing: 14; rowSpacing: 5
                    Text { Layout.fillWidth: true; Layout.preferredWidth: 1; text: "文件大小"; color: "#617367"; font.pixelSize: 11 }
                    Text { Layout.fillWidth: true; Layout.preferredWidth: 1; text: "分配空间"; color: "#617367"; font.pixelSize: 11 }
                    Text { Layout.fillWidth: true; Layout.preferredWidth: 1; text: Fmt.bytes(panel.itemData.size); color: "#375548"; font.pixelSize: 15; font.family: "Segoe UI"; font.weight: Font.DemiBold; elide: Text.ElideRight }
                    Text { Layout.fillWidth: true; Layout.preferredWidth: 1; text: panel.itemData.allocated === undefined ? "—" : Fmt.bytes(panel.itemData.allocated); color: "#375548"; font.pixelSize: 15; font.family: "Segoe UI"; font.weight: Font.DemiBold; elide: Text.ElideRight }
                }
                Repeater {
                    model: [
                        {label:"判断依据", value:panel.itemData.reason || ""},
                        {label:"清理后的影响", value:panel.itemData.effect || ""},
                        {label:"操作前需确认", value:Fmt.list(panel.itemData.prerequisites)}
                    ]
                    delegate: ColumnLayout {
                        required property var modelData
                        visible: modelData.value !== ""
                        Layout.fillWidth: true; spacing: 5
                        Text { text: modelData.label; color: "#617367"; font.pixelSize: 11 }
                        Text { Layout.fillWidth: true; text: modelData.value; color: "#5c7466"; font.pixelSize: 11; wrapMode: Text.Wrap; lineHeight: 1.45 }
                    }
                }
                Text { visible: !panel.itemData.id; Layout.fillWidth: true; text: "空间大小不代表可以删除。请在“清理建议”中查看规则识别的项目。"; color: "#617367"; font.pixelSize: 11; wrapMode: Text.Wrap; lineHeight: 1.45 }
                AppButton { Layout.fillWidth: true; text: "在资源管理器中查看"; glyph: "external"; enabled: !panel.demo && !panel.taskBusy; onClicked: panel.openLocation(panel.itemData.path) }
                AppButton { visible: !!panel.itemData.id && !panel.itemData.ignored; Layout.fillWidth: true; text: "忽略此路径"; subtle: true; enabled: !panel.demo && !panel.taskBusy; hint: "加入忽略列表，可在设置中恢复"; onClicked: panel.ignoreItem(panel.itemData.id) }
            }
        }
    }
}
