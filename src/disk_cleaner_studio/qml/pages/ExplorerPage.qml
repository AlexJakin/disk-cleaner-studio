import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../lib/Format.js" as Fmt

Item {
    id: page
    property bool hasScan: !!backend.summary.root
    property bool filesMode: false
    signal scanRequested()
    signal suggestionsRequested()
    function resetView() { filesMode = false; }
    ColumnLayout {
        anchors.fill: parent; spacing: 16
        RowLayout {
            Layout.fillWidth: true; spacing: 14
            StatCard { Layout.fillWidth: true; label: "已用空间"; value: page.hasScan && backend.summary.total_bytes > 0 ? Fmt.bytes(backend.summary.used_bytes) : "—"; note: page.hasScan ? backend.summary.total_bytes > 0 ? "总容量 " + Fmt.bytes(backend.summary.total_bytes) : "CSV 未提供磁盘容量" : "扫描后查看磁盘占用"; ratio: backend.summary.total_bytes > 0 ? backend.summary.used_bytes / backend.summary.total_bytes : -1; glyph: "disk" }
            StatCard { Layout.fillWidth: true; label: "剩余空间"; value: page.hasScan && backend.summary.total_bytes > 0 ? Fmt.bytes(backend.summary.free_bytes) : "—"; note: page.hasScan ? backend.summary.total_bytes > 0 ? "扫描时的可用容量" : "CSV 未提供磁盘容量" : "选择磁盘开始探索"; glyph: "backup" }
            StatCard { Layout.fillWidth: true; label: "建议检查的空间"; value: page.hasScan ? Fmt.bytes(backend.summary.candidate_bytes) : "—"; note: "按规则筛选 · 仍需逐项确认"; accent: true; glyph: "spark" }
        }
        Panel {
            visible: !page.hasScan
            Layout.fillWidth: true; Layout.fillHeight: true
            ColumnLayout {
                anchors.centerIn: parent; width: Math.min(parent.width - 70, 550); spacing: 17
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter; width: 70; height: 70; radius: 21; color: "#e8f2ec"
                    Icon { anchors.centerIn: parent; name: "explore"; width: 31; height: 31; ink: "#64a58a" }
                }
                Text { Layout.alignment: Qt.AlignHCenter; text: "给磁盘空间，一张清晰的地图"; color: "#2c4b3e"; font.pixelSize: 24; font.weight: Font.DemiBold }
                Text { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; text: "从占用最多的目录开始，逐层找到空间去向。\n导入已有的 WizTree CSV，或选择磁盘开始扫描。"; color: "#607367"; font.pixelSize: 12; lineHeight: 1.7; wrapMode: Text.Wrap }
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 12; spacing: 10
                    AppButton { text: "开始扫描"; glyph: "scan"; primary: true; enabled: !backend.busy; onClicked: page.scanRequested() }
                    AppButton { text: "导入 CSV"; glyph: "import"; enabled: !backend.busy; onClicked: backend.importCsv() }
                }
                AppButton { Layout.alignment: Qt.AlignHCenter; text: "先用示例体验  →"; subtle: true; enabled: !backend.busy; onClicked: { backend.loadDemo(); page.filesMode = false; } }
                Text { Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 10; text: "文件在本机处理  ·  扫描不会自动清理"; color: "#617367"; font.pixelSize: 11 }
            }
        }
        RowLayout {
            visible: page.hasScan
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 16
            ColumnLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; spacing: 13
                Panel {
                    Layout.fillWidth: true; Layout.preferredHeight: Math.max(225, page.height * 0.39)
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 15; spacing: 10
                        RowLayout {
                            Layout.fillWidth: true
                            Text { text: "空间地图"; color: "#365148"; font.pixelSize: 13; font.weight: Font.DemiBold; Layout.fillWidth: true }
                            Text { text: "按文件大小 · 最多 " + (page.filesMode ? "100" : "500") + " 项 · 双击下钻"; color: "#617367"; font.pixelSize: 11 }
                        }
                        Treemap {
                            Layout.fillWidth: true; Layout.fillHeight: true
                            entries: page.filesMode ? backend.topFiles : backend.entries
                            selectedPath: backend.detail.path || ""
                            onSelected: function(path) { backend.selectDetail(path); }
                            onEntered: function(path) { page.filesMode = false; backend.navigate(path); }
                        }
                    }
                }
                Panel {
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 160
                    ColumnLayout {
                        anchors.fill: parent; spacing: 0
                        RowLayout {
                            Layout.fillWidth: true; Layout.margins: 12; spacing: 8
                            AppButton { text: ""; glyph: "up"; implicitWidth: 30; implicitHeight: 30; subtle: true; hint: "返回上一级"; enabled: !backend.busy && !!backend.currentPath && !page.filesMode; onClicked: backend.goUp() }
                            Text { id: pathLabel; Layout.fillWidth: true; text: page.filesMode ? "最大的100个文件 · 按文件大小排序" : backend.currentPath; color: "#5d7869"; font.family: "Consolas"; font.pixelSize: 11; elide: Text.ElideMiddle; MouseArea { id: pathHover; anchors.fill: parent; hoverEnabled: true } ToolTip.visible: pathHover.containsMouse; ToolTip.text: pathLabel.text }
                            AppButton { text: page.filesMode ? "目录视图" : "大文件排行"; implicitHeight: 30; enabled: !backend.busy; onClicked: { page.filesMode = !page.filesMode; if(page.filesMode) backend.showTopFiles(); } }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: "#ecf0ec" }
                        RowLayout {
                            Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 18; Layout.topMargin: 9; Layout.bottomMargin: 9
                            Text { text: "名称"; color: "#617367"; font.pixelSize: 11; Layout.fillWidth: true }
                            Text { text: "文件大小"; color: "#617367"; font.pixelSize: 11; Layout.preferredWidth: 95; horizontalAlignment: Text.AlignRight }
                            Text { text: "显示项占比"; color: "#617367"; font.pixelSize: 11; Layout.preferredWidth: 72; horizontalAlignment: Text.AlignRight }
                        }
                        ListView {
                            id: entriesList
                            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                            model: page.filesMode ? backend.topFiles : backend.entries
                            ScrollBar.vertical: ScrollBar { }
                            boundsBehavior: Flickable.StopAtBounds
                            delegate: ItemDelegate {
                                id: row
                                required property var modelData
                                width: entriesList.width; height: 44; hoverEnabled: true
                                property real denominator: {
                                    var list = page.filesMode ? backend.topFiles : backend.entries;
                                    var sum=0; for(var i=0;i<list.length;i++) sum+=Number(list[i].size||0);
                                    return sum;
                                }
                                background: Rectangle { color: backend.detail.path === row.modelData.path ? "#eef5f0" : row.hovered ? "#f7faf7" : "transparent" }
                                contentItem: RowLayout {
                                    spacing: 10
                                    Icon { Layout.leftMargin: 8; name: row.modelData.is_dir ? "folder" : "file"; width: 16; height: 16; ink: row.modelData.is_dir ? "#8eac9c" : "#afbaae" }
                                    Text { text: row.modelData.name; color: "#536c5d"; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideMiddle }
                                    Text { text: Fmt.bytes(row.modelData.size); color: "#536c5d"; font.pixelSize: 11; font.family: "Segoe UI"; Layout.preferredWidth: 90; horizontalAlignment: Text.AlignRight }
                                    Rectangle { Layout.preferredWidth: 46; Layout.preferredHeight: 4; Layout.leftMargin: 8; color: "#edf2ed"; radius: 2; Rectangle { width: parent.width * Math.min(1, row.denominator ? row.modelData.size / row.denominator : 0); height: 4; color: "#91b49e"; radius: 2 } }
                                    Icon { name: row.modelData.is_dir ? "chevron" : "file"; width: 12; height: 12; ink: row.modelData.is_dir ? "#9bac9f" : "transparent"; Layout.rightMargin: 7 }
                                }
                                onClicked: backend.selectDetail(modelData.path)
                                onDoubleClicked: { if(modelData.is_dir) { page.filesMode = false; backend.navigate(modelData.path); } }
                                Keys.onRightPressed: { if(modelData.is_dir) { page.filesMode = false; backend.navigate(modelData.path); } }
                                ToolTip.visible: hovered; ToolTip.delay: 650; ToolTip.text: modelData.path
                            }
                            Text { visible: entriesList.count === 0; anchors.centerIn: parent; text: "此处没有记录"; color: "#617367"; font.pixelSize: 12 }
                        }
                    }
                }
            }
            DetailPane {
                Layout.preferredWidth: page.width > 1030 ? 278 : 245; Layout.fillHeight: true
                itemData: backend.detail; demo: !!backend.summary.is_demo; taskBusy: backend.busy
                onOpenLocation: function(path) { backend.openPath(path); }
                onIgnoreItem: function(id) { backend.ignoreCandidate(id); }
            }
        }
        RowLayout {
            visible: page.hasScan
            Layout.fillWidth: true; spacing: 8
            Icon { name: "shield"; width: 14; height: 14; ink: "#9daf9f" }
            Text { text: backend.summary.is_demo ? "示例数据 · 用于体验界面，清理操作已禁用" : "占用大不等于可以删除，先查看清理建议与影响。"; color: "#607366"; font.pixelSize: 11; Layout.fillWidth: true }
            AppButton { text: "查看清理建议  →"; subtle: true; implicitHeight: 28; onClicked: page.suggestionsRequested() }
        }
    }
}
