import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ScrollView {
    id: page
    clip: true
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    ColumnLayout {
        width: page.availableWidth; spacing: 16
        Panel {
            Layout.fillWidth: true; implicitHeight: scanSettings.implicitHeight + 40
            ColumnLayout {
                id: scanSettings; anchors.fill: parent; anchors.margins: 20; spacing: 14
                Text { text: "扫描设置"; color: "#45623d"; font.pixelSize: 15; font.weight: Font.DemiBold }
                Text { text: "WizTree 可执行文件"; color: "#60745a"; font.pixelSize: 11 }
                RowLayout {
                    Layout.fillWidth: true
                    AppField { Layout.fillWidth: true; text: backend.wiztreePath; placeholderText: "选择 WizTree64.exe"; enabled: !backend.busy; onEditingFinished: backend.setWiztreePath(text) }
                    AppButton { text: "浏览…"; glyph: "folder"; enabled: !backend.busy; onClicked: backend.chooseWiztree() }
                }
                RowLayout {
                    Layout.fillWidth: true; spacing: 20
                    ColumnLayout { Layout.fillWidth: true; spacing: 8; Text { text: "默认扫描位置"; color: "#60745a"; font.pixelSize: 11 } AppField { Layout.fillWidth: true; text: backend.scanTarget; placeholderText: "例如 C:\\ 或某个目录"; enabled: !backend.busy; onEditingFinished: backend.setScanTarget(text) } }
                    ColumnLayout { spacing: 8; Text { text: "扫描超时（秒）"; color: "#60745a"; font.pixelSize: 11 } SpinBox { from: 30; to: 86400; stepSize: 60; value: backend.scanTimeout; editable: true; implicitHeight: 38; implicitWidth: 160; enabled: !backend.busy; onValueModified: backend.setScanTimeout(value) } }
                }
                Text { Layout.fillWidth: true; text: "整盘快速扫描通常需要管理员权限；请自行以管理员身份启动，或导入 WizTree 导出的 CSV。默认不会在启动时扫描。"; color: "#61735e"; font.pixelSize: 11; wrapMode: Text.Wrap }
            }
        }
        Panel {
            Layout.fillWidth: true; implicitHeight: backupSettings.implicitHeight + 40
            ColumnLayout {
                id: backupSettings; anchors.fill: parent; anchors.margins: 20; spacing: 12
                Text { text: "备份与执行"; color: "#45623d"; font.pixelSize: 15; font.weight: Font.DemiBold }
                Text { text: "备份存放目录"; color: "#60745a"; font.pixelSize: 11 }
                RowLayout { Layout.fillWidth: true; AppField { Layout.fillWidth: true; text: backend.backupRoot; enabled: !backend.busy; onEditingFinished: backend.setBackupRoot(text) } AppButton { text: "浏览…"; glyph: "folder"; enabled: !backend.busy; onClicked: backend.chooseBackupRoot() } }
                Text { Layout.fillWidth: true; text: "建议使用其他磁盘。备份也会占用空间；若备份与清理目标位于同一磁盘，空闲空间可能不会增加。"; color: "#62745e"; font.pixelSize: 11; wrapMode: Text.Wrap; lineHeight: 1.5 }
                Rectangle {
                    Layout.fillWidth: true; implicitHeight: safetyLabel.implicitHeight+24; radius: 7; color: "#f3f7ed"
                    Text { id: safetyLabel; anchors.fill: parent; anchors.margins: 12; text: "当前仅支持保守缓存规则的清理。系统更新、系统目录及高风险数据仅给出建议。执行前校验路径，先完成备份与完整性检查，再开始删除。"; color: "#607557"; font.pixelSize: 11; wrapMode: Text.Wrap; lineHeight: 1.5 }
                }
            }
        }
        Panel {
            Layout.fillWidth: true; implicitHeight: ignoreSettings.implicitHeight + 40
            ColumnLayout {
                id: ignoreSettings; anchors.fill: parent; anchors.margins: 20; spacing: 12
                RowLayout { Layout.fillWidth: true; Text { text: "忽略的路径"; color: "#45623d"; font.pixelSize: 15; font.weight: Font.DemiBold; Layout.fillWidth: true } Text { text: backend.ignoredPaths.length + " 项"; color: "#60745a"; font.pixelSize: 11 } }
                Text { visible: backend.ignoredPaths.length === 0; text: "暂无忽略项。在建议详情中选择“忽略此路径”后，会显示在这里。"; color: "#62745e"; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
                Repeater {
                    model: backend.ignoredPaths
                    delegate: RowLayout {
                        required property string modelData
                        Layout.fillWidth: true
                        Text { text: modelData; color: "#617558"; font.pixelSize: 11; font.family: "Consolas"; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere }
                        AppButton { text: "恢复显示"; subtle: true; enabled: !backend.busy; onClicked: backend.unignore(modelData) }
                    }
                }
            }
        }
        Text { Layout.fillWidth: true; Layout.topMargin: 4; Layout.bottomMargin: 12; text: "Disk Cleaner Studio  ·  本地桌面应用\n设置会自动保存在本机。扫描记录与操作结果均保留在本地。"; color: "#617461"; font.pixelSize: 11; lineHeight: 1.6 }
    }
}
