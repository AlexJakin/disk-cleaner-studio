import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "pages"
import "lib/Format.js" as Fmt

ApplicationWindow {
    id: app
    objectName: "studioWindow"
    width: 1320; height: 860
    minimumWidth: 1060; minimumHeight: 720
    visible: true
    title: "Disk Cleaner Studio · 空间探索"
    color: "#f5f7f3"
    font.family: "Microsoft YaHei UI"
    font.pixelSize: 12
    palette.highlight: "#277d68"
    palette.highlightedText: "#ffffff"
    palette.window: "#f5f7f3"
    palette.text: "#3f5a46"
    property int pageIndex: 0
    property bool waitingForPlan: false
    property string lastResultSignature: ""
    property string lastScanId: ""
    property var pageTitles: ["空间探索", "清理建议", "扫描历史", "备份与恢复", "设置"]
    property var pageSubtitles: ["从空间地图出发，找到每一份占用的去向。", "了解判断依据与清理影响，然后逐项选择。", "保留每次扫描，查看空间如何变化。", "查看清理备份，将文件恢复到原来的位置。", "管理扫描工具、备份位置与忽略项。"]
    function navigatePage(index) { pageIndex = Math.max(0, Math.min(4, index)); }
    function openScanDialog() { scanPath.text = backend.scanTarget; scanDialog.open(); }
    function requestPlan() { waitingForPlan = true; backend.previewPlan(); }
    onClosing: function(close) { if (backend.busy) { close.accepted = false; closeNotice.open(); } }
    Connections {
        target: backend
        function onChanged() {
            if (waitingForPlan && !backend.busy) {
                waitingForPlan = false;
                if (backend.plan.can_execute && backend.plan.items && backend.plan.items.length) planDialog.open();
            }
            var scanId = backend.summary.scan_id || "";
            if (scanId !== lastScanId) { lastScanId = scanId; explorer.resetView(); }
            var signature = JSON.stringify(backend.lastResult);
            if (signature !== lastResultSignature && !backend.busy) {
                lastResultSignature = signature;
                if (backend.lastResult.status) resultDialog.open();
            }
        }
    }
    Shortcut { sequence: "Ctrl+O"; enabled: !backend.busy; onActivated: backend.importCsv() }
    Shortcut { sequence: "Ctrl+1"; onActivated: app.navigatePage(0) }
    Shortcut { sequence: "Ctrl+2"; onActivated: app.navigatePage(1) }
    Shortcut { sequence: "Alt+Up"; enabled: app.pageIndex === 0 && !backend.busy; onActivated: backend.goUp() }
    RowLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            Layout.preferredWidth: 211; Layout.fillHeight: true; color: "#ffffff"
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: "#e7ece3" }
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 16; spacing: 6
                RowLayout {
                    Layout.topMargin: 13; Layout.bottomMargin: 30; Layout.leftMargin: 8; spacing: 10
                    Rectangle {
                        width: 35; height: 35; radius: 10; color: "#216d55"
                        Icon { anchors.centerIn: parent; name: "explore"; width: 18; height: 18; ink: "#e4f4df" }
                    }
                    ColumnLayout { spacing: 2; Text { text: "Disk Cleaner"; color: "#2b4935"; font.pixelSize: 16; font.family: "Segoe UI"; font.weight: Font.DemiBold } Text { text: "STUDIO"; color: "#5f755e"; font.pixelSize: 8; font.letterSpacing: 3.5; font.family: "Segoe UI" } }
                }
                Text { Layout.leftMargin: 13; Layout.bottomMargin: 6; text: "工作空间"; color: "#627463"; font.pixelSize: 11 }
                NavItem { Layout.fillWidth: true; text: "空间探索"; glyph: "explore"; current: app.pageIndex === 0; onClicked: app.navigatePage(0) }
                NavItem { Layout.fillWidth: true; text: "清理建议"; glyph: "spark"; current: app.pageIndex === 1; count: backend.candidates.length ? String(backend.candidates.length) : ""; onClicked: app.navigatePage(1) }
                NavItem { Layout.fillWidth: true; text: "扫描历史"; glyph: "history"; current: app.pageIndex === 2; onClicked: app.navigatePage(2) }
                NavItem { Layout.fillWidth: true; text: "备份与恢复"; glyph: "backup"; current: app.pageIndex === 3; onClicked: { app.navigatePage(3); backend.refreshBackups(); } }
                Rectangle { Layout.fillWidth: true; Layout.margins: 12; Layout.topMargin: 20; Layout.bottomMargin: 11; height: 1; color: "#edf1e8" }
                Text { Layout.leftMargin: 13; Layout.bottomMargin: 9; text: "本机磁盘"; color: "#627463"; font.pixelSize: 11 }
                ListView {
                    id: driveList
                    Layout.fillWidth: true; Layout.preferredHeight: Math.min(backend.drives.length * 62, 186)
                    clip: true; boundsBehavior: Flickable.StopAtBounds
                    model: backend.drives
                    delegate: ItemDelegate {
                        id: driveItem
                        required property var modelData
                        width: driveList.width; height: 62; hoverEnabled: true; enabled: !backend.busy
                        background: Rectangle { color: driveItem.hovered ? "#f5f8f0" : "transparent"; radius: 7 }
                        contentItem: ColumnLayout {
                            spacing: 7
                            RowLayout {
                                Layout.leftMargin: 8; Layout.rightMargin: 8; Layout.fillWidth: true; spacing: 7
                                Icon { name: "disk"; width: 15; height: 15; ink: "#a0b48c" }
                                Text { text: driveItem.modelData.path; color: "#5f7556"; font.pixelSize: 11; Layout.fillWidth: true }
                                Text { text: Fmt.bytes(driveItem.modelData.free) + " 可用"; color: "#627361"; font.pixelSize: 10 }
                            }
                            Rectangle { Layout.fillWidth: true; Layout.leftMargin: 9; Layout.rightMargin: 9; height: 3; color: "#edf2e5"; radius: 2; Rectangle { width: parent.width * Math.max(0, Math.min(1, driveItem.modelData.total ? driveItem.modelData.used / driveItem.modelData.total : 0)); height: 3; radius: 2; color: "#a4bc91" } }
                        }
                        onClicked: { scanPath.text = modelData.path; scanDialog.open(); }
                        ToolTip.visible: hovered; ToolTip.delay: 500; ToolTip.text: (modelData.label || modelData.path) + " · 选择扫描位置"
                    }
                }
                Item { Layout.fillHeight: true }
                NavItem { Layout.fillWidth: true; text: "设置"; glyph: "settings"; current: app.pageIndex === 4; onClicked: app.navigatePage(4) }
                Rectangle {
                    Layout.fillWidth: true; Layout.topMargin: 12; implicitHeight: 67; radius: 9; color: "#f5f8f0"
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 12; spacing: 9
                        Icon { name: "shield"; width: 19; height: 19; ink: "#97af82" }
                        ColumnLayout { spacing: 5; Text { text: "本地处理"; color: "#5e7655"; font.pixelSize: 11 } Text { text: "文件与数据保留在本机"; color: "#627460"; font.pixelSize: 10 } }
                    }
                }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
            RowLayout {
                Layout.fillWidth: true; Layout.leftMargin: 29; Layout.rightMargin: 29; Layout.topMargin: 27; Layout.bottomMargin: 22; spacing: 12
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 7
                    RowLayout {
                        Text { text: app.pageTitles[app.pageIndex]; color: "#2f4a39"; font.pixelSize: 26; font.weight: Font.DemiBold }
                        Rectangle { visible: !!backend.summary.is_demo; Layout.leftMargin: 5; implicitWidth: 61; implicitHeight: 22; radius: 5; color: "#e8f0df"; Text { anchors.centerIn: parent; text: "示例数据"; color: "#5e7653"; font.pixelSize: 10 } }
                    }
                    Text { text: app.pageSubtitles[app.pageIndex]; color: "#617461"; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
                }
                AppButton { text: "导入 CSV"; glyph: "import"; enabled: !backend.busy; onClicked: { app.navigatePage(0); backend.importCsv(); } hint: "导入已有扫描 · Ctrl+O" }
                AppButton { text: "开始扫描"; glyph: "scan"; primary: true; enabled: !backend.busy; onClicked: app.openScanDialog() }
            }
            Rectangle {
                visible: backend.error !== ""
                Layout.fillWidth: true; Layout.leftMargin: 29; Layout.rightMargin: 29; Layout.bottomMargin: 13
                implicitHeight: errorText.implicitHeight + 24; radius: 8; color: "#faf0e4"; border.color: "#f0dec7"
                RowLayout {
                    anchors.fill: parent; anchors.margins: 12; spacing: 9
                    Icon { name: "info"; width: 17; height: 17; ink: "#b78c5f" }
                    Text { id: errorText; Layout.fillWidth: true; text: backend.error; color: "#7b6d51"; font.pixelSize: 11; wrapMode: Text.Wrap; maximumLineCount: 4; elide: Text.ElideRight }
                    AppButton { text: ""; glyph: "close"; implicitWidth: 26; implicitHeight: 26; subtle: true; hint: "关闭提示"; onClicked: backend.clearError() }
                }
            }
            StackLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.leftMargin: 29; Layout.rightMargin: 29; Layout.bottomMargin: 20
                currentIndex: app.pageIndex
                ExplorerPage { id: explorer; onScanRequested: app.openScanDialog(); onSuggestionsRequested: app.navigatePage(1) }
                SuggestionsPage { onPlanRequested: app.requestPlan() }
                HistoryPage { onScanLoaded: { explorer.resetView(); app.navigatePage(0); } }
                BackupsPage { }
                SettingsPage { }
            }
            Rectangle {
                Layout.fillWidth: true; implicitHeight: backend.busy ? 61 : 38; color: "#ffffff"
                Rectangle { width: parent.width; height: 1; color: "#e6ede0" }
                ColumnLayout {
                    anchors.fill: parent; anchors.leftMargin: 28; anchors.rightMargin: 28; anchors.topMargin: 7; anchors.bottomMargin: 6; spacing: 4
                    RowLayout {
                        Layout.fillWidth: true; spacing: 8
                        Rectangle { width: 5; height: 5; radius: 3; color: backend.busy ? "#6ea35d" : backend.error ? "#c29d69" : "#a4bd90" }
                        Text { text: backend.status; color: "#61745b"; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
                        Text { visible: backend.busy; text: (backend.progressCount > 0 ? backend.progressCount + " 项 · " : "") + backend.elapsed; color: "#61745b"; font.pixelSize: 11; font.family: "Consolas" }
                        AppButton { visible: backend.busy; text: "取消任务"; implicitHeight: 26; implicitWidth: 78; subtle: true; onClicked: backend.cancelTask() }
                        AppButton { visible: !backend.busy && !!backend.lastResult.status; text: "查看结果"; implicitHeight: 25; subtle: true; onClicked: resultDialog.open() }
                        AppButton { visible: !backend.busy && (backend.summary.warnings || []).length > 0; text: "扫描说明 " + (backend.summary.warnings || []).length; glyph: "info"; implicitHeight: 25; subtle: true; onClicked: scanNotes.open() }
                        Text { visible: !backend.busy && !!backend.summary.root; text: "快照 " + Fmt.date(backend.summary.scanned_at); color: "#627461"; font.pixelSize: 10 }
                    }
                    ProgressBar { visible: backend.busy; Layout.fillWidth: true; implicitHeight: 3; indeterminate: true; palette.highlight: "#88ad72"; palette.dark: "#eaf0e1" }
                }
            }
        }
    }
    Dialog {
        id: scanDialog; objectName: "scanDialog"; parent: Overlay.overlay
        x: (parent.width-width)/2; y: (parent.height-height)/2; width: 560; modal: true; padding: 25
        title: "选择扫描位置"
        background: Panel { radius: 14 }
        contentItem: ColumnLayout {
            spacing: 17
            Text { text: "磁盘或目录路径"; color: "#61745b"; font.pixelSize: 11 }
            AppField { id: scanPath; Layout.fillWidth: true; text: backend.scanTarget; placeholderText: "例如 C:\\ 或 D:\\Projects"; onAccepted: { if(text.trim() && !backend.busy) { scanDialog.close(); app.navigatePage(0); backend.startScan(text); } } }
            Flow {
                Layout.fillWidth: true; spacing: 8
                Repeater { model: backend.drives; delegate: AppButton { required property var modelData; text: modelData.path; implicitWidth: 67; onClicked: scanPath.text = modelData.path } }
            }
            Text { Layout.fillWidth: true; text: "WizTree 将扫描并导出目录索引。此步骤只读取磁盘，不会清理文件。全盘扫描可能需要 Windows 管理员授权。"; color: "#62745f"; font.pixelSize: 11; wrapMode: Text.Wrap; lineHeight: 1.6 }
            Text { visible: !backend.wiztreePath; Layout.fillWidth: true; text: "尚未配置 WizTree。请到设置中选择 WizTree64.exe。"; color: "#75704f"; font.pixelSize: 11; wrapMode: Text.Wrap }
            RowLayout { Layout.fillWidth: true; Item { Layout.fillWidth: true } AppButton { text: "取消"; onClicked: scanDialog.close() } AppButton { text: "开始扫描"; primary: true; glyph: "scan"; enabled: !!scanPath.text.trim() && !!backend.wiztreePath && !backend.busy; onClicked: { scanDialog.close(); app.navigatePage(0); backend.startScan(scanPath.text); } } }
        }
    }
    Dialog {
        id: planDialog; objectName: "planDialog"; parent: Overlay.overlay
        x: (parent.width-width)/2; y: (parent.height-height)/2; width: 740; height: Math.min(640, app.height-80); modal: true; padding: 24
        closePolicy: Popup.CloseOnEscape
        title: "核对清理计划"
        onOpened: planConsent.checked = false
        background: Panel { radius: 14 }
        contentItem: ColumnLayout {
            spacing: 14
            Text { Layout.fillWidth: true; text: "下列路径来自你选择的项目。执行前将再次核验路径与状态，完成全部备份及校验后才开始清理。"; color: "#607559"; font.pixelSize: 12; wrapMode: Text.Wrap; lineHeight: 1.55 }
            Rectangle {
                Layout.fillWidth: true; implicitHeight: 65; radius: 8; color: "#f2f6ea"
                RowLayout { anchors.fill: parent; anchors.margins: 14; Text { text: "共 " + ((backend.plan.items || []).length) + " 项"; color: "#5f7554"; font.pixelSize: 12; Layout.fillWidth: true } Text { text: Fmt.bytes(backend.plan.total_bytes); color: "#577841"; font.pixelSize: 25; font.family: "Segoe UI"; font.weight: Font.DemiBold } }
            }
            ListView {
                id: planList; Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 110; clip: true
                model: backend.plan.items || []; boundsBehavior: Flickable.StopAtBounds; ScrollBar.vertical: ScrollBar { }
                delegate: Item {
                    required property var modelData
                    width: planList.width; height: Math.max(58, planPath.implicitHeight+22)
                    RowLayout { anchors.fill: parent; anchors.margins: 9; spacing: 15; Icon { name: "folder"; width: 17; height: 17; ink: "#a8be8b" } Text { id: planPath; text: modelData.path || ""; Layout.fillWidth: true; color: "#607558"; font.pixelSize: 11; font.family: "Consolas"; wrapMode: Text.WrapAnywhere } Text { text: Fmt.bytes(modelData.size !== undefined ? modelData.size : modelData.total_bytes); color: "#5b774c"; font.pixelSize: 12; font.family: "Segoe UI" } }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#eaf0e0" }
            RowLayout { Layout.fillWidth: true; Icon { name: "backup"; width: 19; height: 19; ink: "#94ad75" } Text { text: "备份位置"; color: "#607559"; font.pixelSize: 11 } Text { text: backend.plan.backup_root || backend.backupRoot; Layout.fillWidth: true; color: "#5e764e"; font.pixelSize: 11; font.family: "Consolas"; wrapMode: Text.WrapAnywhere } }
            Text { visible: !!Fmt.list(backend.plan.warnings); text: Fmt.list(backend.plan.warnings); Layout.fillWidth: true; color: "#737052"; font.pixelSize: 11; wrapMode: Text.Wrap }
            AppCheckBox { id: planConsent; objectName: "planConsent"; Layout.fillWidth: true; text: "我已核对以上路径与备份位置，确认执行备份和清理"; enabled: !backend.busy }
            RowLayout { Layout.fillWidth: true; Item { Layout.fillWidth: true } AppButton { text: "返回修改"; onClicked: planDialog.close() } AppButton { objectName: "executePlanButton"; text: "确认备份并清理"; primary: true; glyph: "shield"; enabled: planConsent.checked && !!backend.plan.can_execute && !backend.busy && !backend.summary.is_demo; onClicked: { planDialog.close(); backend.executePlan(); } } }
        }
    }
    Dialog {
        id: resultDialog; objectName: "resultDialog"; parent: Overlay.overlay
        x: (parent.width-width)/2; y: (parent.height-height)/2; width: 720; height: Math.min(580, app.height-100); modal: true; padding: 24
        title: "操作结果"
        background: Panel { radius: 14 }
        contentItem: ColumnLayout {
            spacing: 16
            Text { Layout.fillWidth: true; text: backend.lastResult.message || ""; color: "#5f7650"; font.pixelSize: 12; wrapMode: Text.Wrap; lineHeight: 1.5 }
            RowLayout {
                Layout.fillWidth: true; spacing: 12
                StatCard {
                    objectName: "resultSpaceStat"
                    Layout.fillWidth: true; implicitHeight: 105
                    label: backend.lastResult.operation === "restore" ? "已恢复文件大小" : "源磁盘空闲变化"
                    value: backend.lastResult.operation === "restore" ? Fmt.bytes(backend.lastResult.restored_bytes)
                         : backend.lastResult.freed_bytes === null || backend.lastResult.freed_bytes === undefined ? "—"
                         : (backend.lastResult.freed_bytes > 0 ? "+" : "") + Fmt.bytes(backend.lastResult.freed_bytes)
                    note: backend.lastResult.operation === "restore" ? "按已恢复文件统计" : "执行前后测量，可能为负数"
                    glyph: "disk"; accent: true
                }
                StatCard { Layout.fillWidth: true; implicitHeight: 105; label: backend.lastResult.operation === "restore" ? "成功 / 失败" : "逻辑删除量"; value: backend.lastResult.operation === "restore" ? (backend.lastResult.success_count || 0) + " / " + (backend.lastResult.failed_count || 0) : Fmt.bytes(backend.lastResult.logical_deleted_bytes); note: "以逐项结果为准"; glyph: "file" }
            }
            Text { text: "成功 " + (backend.lastResult.success_count || 0) + "   ·   失败 " + (backend.lastResult.failed_count || 0) + "   ·   跳过 " + (backend.lastResult.skipped_count || 0); color: "#617557"; font.pixelSize: 11 }
            ListView {
                id: resultList; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; model: backend.lastResult.items || []
                boundsBehavior: Flickable.StopAtBounds; ScrollBar.vertical: ScrollBar { }
                delegate: Item {
                    required property var modelData
                    width: resultList.width; height: Math.max(62, resultPath.implicitHeight + resultMessage.implicitHeight + 22)
                    RowLayout { anchors.fill: parent; anchors.margins: 7; spacing: 15; ColumnLayout { Layout.fillWidth: true; spacing: 5; Text { id: resultPath; text: modelData.path || modelData.original_path || ""; color: "#5f7555"; font.pixelSize: 11; font.family: "Consolas"; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere } Text { id: resultMessage; text: modelData.message || ""; visible: text !== ""; color: "#707155"; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap } } Text { text: Fmt.status(modelData.status); color: modelData.status === "failed" ? "#b49159" : "#86a55e"; font.pixelSize: 11 } }
                }
            }
            RowLayout { Layout.fillWidth: true; AppButton { text: "查看备份"; glyph: "backup"; onClicked: { resultDialog.close(); app.navigatePage(3); backend.refreshBackups(); } } Item { Layout.fillWidth: true } AppButton { objectName: "resultDoneButton"; text: "完成"; primary: true; onClicked: resultDialog.close() } }
        }
    }
    Dialog {
        id: scanNotes; parent: Overlay.overlay
        x: (parent.width-width)/2; y: (parent.height-height)/2; width: 570; modal: true; padding: 24
        title: "当前扫描说明"
        background: Panel { radius: 14 }
        contentItem: ColumnLayout {
            spacing: 17
            Text { Layout.fillWidth: true; text: Fmt.list(backend.summary.warnings); wrapMode: Text.Wrap; font.pixelSize: 12; color: "#617559"; lineHeight: 1.6 }
            Text { Layout.fillWidth: true; text: "数据来源：" + (backend.summary.source || "—"); wrapMode: Text.WrapAnywhere; font.pixelSize: 11; color: "#637460" }
            AppButton { Layout.alignment: Qt.AlignRight; text: "知道了"; primary: true; onClicked: scanNotes.close() }
        }
    }
    Dialog {
        id: closeNotice; objectName: "closeNotice"; parent: Overlay.overlay
        x: (parent.width-width)/2; y: (parent.height-height)/2; width: 470; modal: true; padding: 24
        title: "请等待当前任务结束"
        background: Panel { radius: 14 }
        contentItem: ColumnLayout {
            spacing: 18
            Text { Layout.fillWidth: true; text: "任务仍在运行。可先取消任务，待当前步骤安全结束后再关闭窗口。"; wrapMode: Text.Wrap; font.pixelSize: 12; color: "#617559"; lineHeight: 1.6 }
            RowLayout { Layout.fillWidth: true; Item { Layout.fillWidth: true } AppButton { text: "继续等待"; onClicked: closeNotice.close() } AppButton { objectName: "closeCancelButton"; text: "取消任务"; primary: true; onClicked: { backend.cancelTask(); closeNotice.close(); } } }
        }
    }
}
