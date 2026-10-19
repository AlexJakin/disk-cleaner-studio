import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../lib/Format.js" as Fmt

Item {
    id: page
    signal planRequested()
    property var filtered: {
        var source = backend.candidates, out = [], q = search.text.toLowerCase();
        for(var i=0;i<source.length;i++) {
            var item = source[i];
            if (filter.currentIndex === 3 ? !item.ignored : item.ignored) continue;
            if (filter.currentIndex === 1 && !item.cleanable) continue;
            if (filter.currentIndex === 2 && item.cleanable) continue;
            if (q && (item.name+" "+item.path+" "+item.reason).toLowerCase().indexOf(q)<0) continue;
            out.push(item);
        }
        return out;
    }
    ColumnLayout {
        anchors.fill: parent; spacing: 16
        Panel {
            Layout.fillWidth: true; implicitHeight: 70; color: "#edf5ef"; border.color: "#dae8dc"
            RowLayout {
                anchors.fill: parent; anchors.margins: 18; spacing: 13
                Icon { name: "shield"; width: 26; height: 26; ink: "#739f80" }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 5
                    Text { text: backend.summary.is_demo ? "当前为示例体验，清理和忽略操作已禁用" : "先理解影响，再决定清理"; color: "#436d4a"; font.pixelSize: 13; font.weight: Font.DemiBold }
                    Text { text: "仅开放保守缓存规则；系统目录与其他敏感项目提供建议。执行前会再次核验，并先完成备份。"; color: "#5e7462"; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
                }
                Text { text: "01  选择   →   02  核对   →   03  备份与清理"; color: "#5d7462"; font.pixelSize: 11; visible: page.width > 1000 }
            }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 16
            Panel {
                Layout.fillWidth: true; Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent; spacing: 0
                    RowLayout {
                        Layout.fillWidth: true; Layout.margins: 15; spacing: 10
                        Text { text: "清理建议"; color: "#37513c"; font.pixelSize: 13; font.weight: Font.DemiBold }
                        Text { text: page.filtered.length + " 项"; color: "#617366"; font.pixelSize: 11 }
                        Item { Layout.fillWidth: true }
                        AppComboBox {
                            id: filter; model: ["全部项目", "可执行缓存", "仅建议", "已忽略"]; implicitWidth: 112; implicitHeight: 33
                            font.pixelSize: 11
                            palette.button: "#f7faf6"; palette.buttonText: "#60795e"; palette.highlight: "#e5f1e6"; palette.highlightedText: "#376748"
                        }
                    }
                    AppField { id: search; Layout.fillWidth: true; Layout.leftMargin: 15; Layout.rightMargin: 15; Layout.bottomMargin: 12; placeholderText: "搜索名称、路径或判断依据"; implicitHeight: 34 }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#edf1eb" }
                    ListView {
                        id: candidateList
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        model: page.filtered; boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { }
                        delegate: ItemDelegate {
                            id: row
                            required property var modelData
                            width: candidateList.width; height: 98; hoverEnabled: true
                            background: Rectangle { color: backend.detail.path === row.modelData.path ? "#edf5ee" : row.hovered ? "#f8faf6" : "#ffffff"; Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: "#f0f3ed" } }
                            contentItem: RowLayout {
                                spacing: 10
                                AppCheckBox {
                                    objectName: "candidateCheck_" + row.modelData.id
                                    Layout.leftMargin: 5
                                    checked: !!row.modelData.selected
                                    enabled: !!row.modelData.cleanable && !row.modelData.ignored && !backend.summary.is_demo && !backend.busy
                                    palette.highlight: "#3c8761"
                                    Accessible.name: "选择 " + row.modelData.name
                                    onClicked: backend.toggleCandidate(row.modelData.id)
                                    ToolTip.visible: hovered
                                    ToolTip.text: backend.summary.is_demo ? "示例数据不能执行清理" : !row.modelData.cleanable ? "此项目仅提供建议" : "加入待确认的清理计划"
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 6
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: row.modelData.name; color: "#466341"; font.pixelSize: 12; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
                                        Rectangle {
                                            implicitWidth: tag.implicitWidth+12; implicitHeight: 20; radius: 4; color: row.modelData.risk === "low" ? "#e6f1e6" : "#f5efdf"
                                            Text { id: tag; anchors.centerIn: parent; text: row.modelData.ignored ? "已忽略" : Fmt.risk(row.modelData.risk, row.modelData.cleanable); color: row.modelData.risk === "low" ? "#527b50" : "#8a773f"; font.pixelSize: 10 }
                                        }
                                        Text { text: Fmt.bytes(row.modelData.size); color: "#4e6948"; font.pixelSize: 13; font.family: "Segoe UI"; font.weight: Font.DemiBold; Layout.preferredWidth: 86; horizontalAlignment: Text.AlignRight; Layout.rightMargin: 10 }
                                    }
                                    Text { text: row.modelData.reason || ""; color: "#627463"; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
                                    Text { text: row.modelData.path; color: "#627363"; font.pixelSize: 10; font.family: "Consolas"; Layout.fillWidth: true; elide: Text.ElideMiddle }
                                }
                            }
                            onClicked: backend.selectDetail(modelData.path)
                            ToolTip.visible: hovered; ToolTip.delay: 700; ToolTip.text: modelData.path
                        }
                        Column {
                            visible: candidateList.count === 0; anchors.centerIn: parent; width: Math.max(100, parent.width-40); spacing: 12
                            Icon { name: "spark"; width: 32; height: 32; ink: "#bacdb6"; anchors.horizontalCenter: parent.horizontalCenter }
                            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: backend.summary.root ? "没有符合条件的项目" : "载入扫描结果后查看建议"; color: "#607460"; font.pixelSize: 12 }
                            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: "扫描或导入 CSV 不会自动删除文件"; color: "#627364"; font.pixelSize: 11 }
                        }
                    }
                }
            }
            DetailPane {
                Layout.preferredWidth: page.width > 1030 ? 290 : 252; Layout.fillHeight: true
                itemData: backend.detail; demo: !!backend.summary.is_demo; taskBusy: backend.busy
                onOpenLocation: function(path) { backend.openPath(path); }
                onIgnoreItem: function(id) { backend.ignoreCandidate(id); }
            }
        }
        Panel {
            Layout.fillWidth: true; implicitHeight: 76
            RowLayout {
                anchors.fill: parent; anchors.margins: 17; spacing: 12
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    RowLayout {
                        Text { text: "已选 " + backend.selectedCount + " 项"; color: "#5e755e"; font.pixelSize: 11 }
                        Text { text: Fmt.bytes(backend.selectedBytes); color: "#3e693f"; font.pixelSize: 23; font.family: "Segoe UI"; font.weight: Font.DemiBold }
                    }
                    Text { text: "这是文件大小合计；实际空闲空间变化将在执行后测量。"; color: "#637363"; font.pixelSize: 11 }
                }
                AppButton { objectName: "previewPlanButton"; text: "核对清理计划"; glyph: "chevron"; primary: true; enabled: backend.selectedCount > 0 && !backend.busy && !backend.summary.is_demo; onClicked: page.planRequested() }
            }
        }
    }
}
