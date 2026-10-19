import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../lib/Format.js" as Fmt

Item {
    id: page
    property var chosenBackup: ({})
    ColumnLayout {
        anchors.fill: parent; spacing: 16
        Panel {
            Layout.fillWidth: true; implicitHeight: 104
            RowLayout {
                anchors.fill: parent; anchors.margins: 20; spacing: 17
                Rectangle { width: 49; height: 49; radius: 13; color: "#eaf3e8"; Icon { anchors.centerIn: parent; name: "backup"; width: 23; height: 23; ink: "#7fa071" } }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 6
                    Text { text: "固定备份位置"; color: "#4a6640"; font.pixelSize: 13; font.weight: Font.DemiBold }
                    Text { text: backend.backupRoot; color: "#62745c"; font.pixelSize: 11; font.family: "Consolas"; Layout.fillWidth: true; elide: Text.ElideMiddle }
                    Text { text: "备份按任务保留，恢复前会验证文件完整性。"; color: "#627460"; font.pixelSize: 11 }
                }
                AppButton { text: "选择目录"; glyph: "folder"; enabled: !backend.busy; onClicked: backend.chooseBackupRoot() }
                AppButton { text: "刷新"; glyph: "refresh"; enabled: !backend.busy; onClicked: backend.refreshBackups() }
            }
        }
        Panel {
            Layout.fillWidth: true; Layout.fillHeight: true
            ColumnLayout {
                anchors.fill: parent; spacing: 0
                RowLayout { Layout.fillWidth: true; Layout.margins: 20; Text { text: "备份记录"; color: "#47643b"; font.pixelSize: 14; font.weight: Font.DemiBold; Layout.fillWidth: true } Text { text: backend.backups.length + " 份"; color: "#61745c"; font.pixelSize: 11 } }
                Rectangle { Layout.fillWidth: true; height: 1; color: "#eaf0e2" }
                ListView {
                    id: backupList; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                    model: backend.backups; boundsBehavior: Flickable.StopAtBounds; ScrollBar.vertical: ScrollBar { }
                    delegate: Item {
                        required property var modelData
                        width: backupList.width; height: 96
                        Rectangle { width: parent.width; height: 1; anchors.bottom: parent.bottom; color: "#f0f3e9" }
                        RowLayout {
                            anchors.fill: parent; anchors.margins: 20; spacing: 20
                            Icon { name: "backup"; width: 22; height: 22; ink: "#a6bc90" }
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 7
                                Text { text: modelData.id; color: "#59774a"; font.pixelSize: 12; font.family: "Consolas"; Layout.fillWidth: true; elide: Text.ElideMiddle }
                                Text { text: Fmt.date(modelData.created_at) + "  ·  " + (modelData.item_count || 0) + " 个项目"; color: "#61745d"; font.pixelSize: 11 }
                            }
                            Text { text: Fmt.status(modelData.status); color: modelData.status === "failed" ? "#b28a59" : "#88a66b"; font.pixelSize: 11 }
                            Text { text: Fmt.bytes(modelData.total_bytes); color: "#5d764f"; font.pixelSize: 13; font.family: "Segoe UI"; Layout.preferredWidth: 105; horizontalAlignment: Text.AlignRight }
                            AppButton { objectName: "restoreButton_" + modelData.id; text: "恢复"; glyph: "history"; enabled: !backend.busy && modelData.backup_complete !== false; hint: modelData.backup_complete === false ? "此备份未完成或未通过校验" : "验证后恢复到原路径"; onClicked: { page.chosenBackup = modelData; restoreDialog.open(); } }
                        }
                    }
                    Column {
                        visible: backupList.count === 0; anchors.centerIn: parent; width: parent.width-70; spacing: 15
                        Icon { anchors.horizontalCenter: parent.horizontalCenter; name: "backup"; width: 44; height: 44; ink: "#bdcfa8" }
                        Text { width: parent.width; text: "这里将保留你的清理备份"; horizontalAlignment: Text.AlignHCenter; color: "#5f7557"; font.pixelSize: 16 }
                        Text { width: parent.width; text: "完成备份与清理后，可在这里查看记录并恢复文件。\n可更换到已有备份所在的目录，再点击刷新。"; horizontalAlignment: Text.AlignHCenter; color: "#61745d"; font.pixelSize: 11; lineHeight: 1.6; wrapMode: Text.Wrap }
                    }
                }
            }
        }
    }
    Dialog {
        id: restoreDialog
        objectName: "restoreDialog"
        parent: Overlay.overlay
        x: (parent.width-width)/2; y: (parent.height-height)/2
        width: Math.min(530, parent.width-60); modal: true; padding: 25
        title: "确认恢复备份"
        background: Panel { radius: 14 }
        contentItem: ColumnLayout {
            spacing: 17
            Text { Layout.fillWidth: true; text: "将验证备份后，把文件恢复到原来的位置。已有文件的冲突会由后端检查，并逐项报告结果。"; color: "#5f7555"; font.pixelSize: 12; wrapMode: Text.Wrap; lineHeight: 1.6 }
            Text { Layout.fillWidth: true; text: page.chosenBackup.id || ""; color: "#597846"; font.pixelSize: 11; font.family: "Consolas"; wrapMode: Text.WrapAnywhere }
            RowLayout { Layout.fillWidth: true; Item { Layout.fillWidth: true } AppButton { objectName: "restoreCancelButton"; text: "取消"; onClicked: restoreDialog.close() } AppButton { objectName: "restoreConfirmButton"; text: "验证并恢复"; primary: true; enabled: !backend.busy; onClicked: { restoreDialog.close(); backend.restoreBackup(page.chosenBackup.id); } } }
        }
    }
}
