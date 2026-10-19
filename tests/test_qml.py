"""Exercise the actual QML confirmation gates with a side-effect-free backend.

No real scanner, cleanup service, cache directory, or backup is used. Set
DCS_QML_SCREENSHOT_DIR to retain the minimum-window screenshots for visual QA.
"""
import copy
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, QPointF, Property, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


ROOT = r"C:\Users\Fixture"
CACHE = ROOT + r"\AppData\Local\pip\Cache"


class UiBackend(QObject):
    changed = Signal()
    _types = {
        "summary": "QVariantMap", "drives": "QVariantList", "busy": bool,
        "status": str, "error": str, "progressCount": int, "elapsed": str,
        "entries": "QVariantList", "topFiles": "QVariantList", "candidates": "QVariantList",
        "selectedBytes": "qlonglong", "selectedCount": int, "detail": "QVariantMap",
        "currentPath": str, "history": "QVariantList", "comparison": "QVariantList",
        "backups": "QVariantList", "backupRoot": str, "wiztreePath": str,
        "scanTarget": str, "scanTimeout": int, "plan": "QVariantMap",
        "lastResult": "QVariantMap", "ignoredPaths": "QVariantList",
    }
    for _name, _type in _types.items():
        locals()[_name] = Property(_type, lambda self, key=_name: self.data[key], notify=changed)

    def __init__(self, demo=False):
        super().__init__()
        self.calls = []
        candidate = dict(id="cache", path=CACHE, name="pip 缓存", category="开发缓存",
                         risk="low", reason="匹配精确缓存目录", effect="应用可能重新下载缓存",
                         prerequisites="关闭相关应用，再确认备份位置", size=4096, allocated=4096,
                         is_dir=True, cleanable=not demo, selected=False, ignored=False)
        self.data = dict(summary=dict(root=ROOT, scan_id="fixture", scanned_at="2026-10-18T12:00:00Z",
                                     entry_count=2, total_bytes=20000, used_bytes=10000, free_bytes=10000,
                                     candidate_bytes=4096, is_demo=demo, source="UI fixture", warnings=[]),
                         drives=[], busy=False, status="测试数据已载入", error="", progressCount=0,
                         elapsed="00:00", entries=[candidate], topFiles=[], candidates=[candidate],
                         selectedBytes=0, selectedCount=0, detail={}, currentPath=ROOT, history=[],
                         comparison=[], backups=[dict(id="fixture-backup", created_at="2026-10-18T12:00:00Z",
                                                     status="complete", total_bytes=4096, item_count=1,
                                                     backup_complete=True)],
                         backupRoot=r"D:\FixtureBackups", wiztreePath=r"D:\Tools\WizTree64.exe",
                         scanTarget="C:\\", scanTimeout=1800, plan={}, lastResult={}, ignoredPaths=[])

    @Slot(str)
    def selectDetail(self, path):
        self.data["detail"] = copy.deepcopy(self.data["candidates"][0])
        self.calls.append(("detail", path))
        self.changed.emit()

    @Slot(str)
    def navigate(self, path):
        self.data["currentPath"] = path
        self.calls.append(("navigate", path))
        self.changed.emit()

    @Slot(str)
    def toggleCandidate(self, candidate_id):
        self.calls.append(("toggle", candidate_id))
        candidate = self.data["candidates"][0]
        candidate["selected"] = not candidate["selected"]
        self.data["selectedCount"] = int(candidate["selected"])
        self.data["selectedBytes"] = 4096 if candidate["selected"] else 0
        self.changed.emit()

    @Slot()
    def previewPlan(self):
        self.calls.append(("preview",))
        self.data["busy"] = True
        self.changed.emit()

        def finish():
            self.data["busy"] = False
            self.data["plan"] = dict(items=[dict(path=CACHE, size=4096)], total_bytes=4096,
                                     backup_root=self.data["backupRoot"], can_execute=True,
                                     warnings=["测试计划：没有真实文件操作。"])
            self.changed.emit()
        QTimer.singleShot(20, finish)

    @Slot()
    def executePlan(self):
        self.calls.append(("execute",))
        self.data["lastResult"] = dict(operation="cleanup", status="complete", message="测试清理完成",
                                       freed_bytes=-1024, logical_deleted_bytes=4096, success_count=1,
                                       failed_count=0, skipped_count=0,
                                       items=[dict(path=CACHE, status="complete", message="")])
        self.changed.emit()

    @Slot(str)
    def restoreBackup(self, backup_id):
        self.calls.append(("restore", backup_id))
        self.data["lastResult"] = dict(operation="restore", status="complete", message="测试恢复完成",
                                       restored_bytes=4096, success_count=1, failed_count=0,
                                       items=[dict(path=CACHE, status="complete", message="")])
        self.changed.emit()

    @Slot()
    def refreshBackups(self):
        pass

    @Slot()
    def cancelTask(self):
        self.calls.append(("cancel",))
        self.data["busy"] = False
        self.changed.emit()


@pytest.fixture(scope="session")
def quick_app():
    app = QApplication.instance() or QApplication([])
    font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
        if (font_dir / name).is_file():
            QFontDatabase.addApplicationFont(str(font_dir / name))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    QQuickStyle.setStyle("Basic")
    return app


@pytest.fixture
def make_ui(quick_app):
    instances = []

    class Harness:
        def __init__(self, demo):
            self.backend = UiBackend(demo)
            self.engine = QQmlApplicationEngine()
            self.warnings = []
            self.engine.warnings.connect(lambda items: self.warnings.extend(str(i) for i in items))
            self.engine.rootContext().setContextProperty("backend", self.backend)
            qml = Path(__file__).parents[1] / "src/disk_cleaner_studio/qml/Main.qml"
            self.engine.load(QUrl.fromLocalFile(str(qml)))
            assert self.engine.rootObjects()
            self.window = self.engine.rootObjects()[0]
            self.window.resize(1060, 720)
            QTest.qWait(100)

        def find(self, name):
            # Repeater/ListView delegates have visual parents which need not
            # be their QObject owners. Traverse both trees, including popups.
            pending = [self.window, self.window.contentItem()]
            seen = set()
            while pending:
                obj = pending.pop()
                if obj in seen:
                    continue
                seen.add(obj)
                if obj.objectName() == name:
                    return obj
                pending.extend(obj.children())
                if isinstance(obj, QQuickItem):
                    pending.extend(obj.childItems())
            raise AssertionError(name)

        def click(self, name, enabled=True):
            obj = self.find(name)
            assert obj.property("visible")
            assert bool(obj.property("enabled")) is enabled
            point = obj.mapToScene(QPointF(obj.width()/2, obj.height()/2)).toPoint()
            QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point)
            QTest.qWait(100)

        def page(self, index):
            self.window.setProperty("pageIndex", index)
            QTest.qWait(60)

        def capture(self, name):
            folder = os.environ.get("DCS_QML_SCREENSHOT_DIR")
            if folder:
                target = Path(folder)
                target.mkdir(parents=True, exist_ok=True)
                assert self.window.grabWindow().save(str(target / (name + ".png")))

    def create(demo=False):
        instance = Harness(demo)
        instances.append(instance)
        return instance

    yield create
    for instance in instances:
        instance.backend.data["busy"] = False
        instance.window.close()
        instance.engine.deleteLater()
    quick_app.processEvents()


def test_minimum_window_details_and_demo_gate(make_ui):
    ui = make_ui(demo=True)
    assert not ui.backend.calls
    ui.click("mapTile_" + CACHE)
    assert ui.backend.detail["path"] == CACHE
    ui.capture("minimum-explorer-detail")
    ui.page(1)
    ui.click("candidateCheck_cache", enabled=False)
    ui.click("previewPlanButton", enabled=False)
    assert ui.backend.selectedCount == 0
    assert ("preview",) not in ui.backend.calls
    ui.capture("minimum-suggestions-detail")
    ui.page(2)
    ui.capture("minimum-history")
    ui.page(3)
    ui.capture("minimum-backups")
    ui.page(4)
    ui.capture("minimum-settings")
    assert not ui.warnings


def test_plan_requires_explicit_consent_and_reports_negative_delta(make_ui):
    ui = make_ui()
    ui.page(1)
    ui.click("candidateCheck_cache")
    ui.click("previewPlanButton")
    assert ui.find("planDialog").property("visible")
    assert ("execute",) not in ui.backend.calls
    ui.click("executePlanButton", enabled=False)
    assert ("execute",) not in ui.backend.calls
    ui.capture("minimum-plan-confirmation")
    ui.click("planConsent")
    ui.click("executePlanButton")
    assert ui.backend.calls.count(("execute",)) == 1
    assert ui.find("resultDialog").property("visible")
    assert ui.find("resultSpaceStat").property("value") == "−1.00 KiB"
    ui.capture("minimum-cleanup-result")
    ui.backend.data["lastResult"]["freed_bytes"] = None
    ui.backend.changed.emit()
    QTest.qWait(30)
    assert ui.find("resultSpaceStat").property("value") == "—"
    assert not ui.warnings


def test_restore_confirmation_and_busy_window_close(make_ui):
    ui = make_ui()
    ui.page(3)
    ui.click("restoreButton_fixture-backup")
    assert ui.find("restoreDialog").property("visible")
    assert not any(call[0] == "restore" for call in ui.backend.calls)
    ui.capture("minimum-restore-confirmation")
    ui.click("restoreCancelButton")
    assert not any(call[0] == "restore" for call in ui.backend.calls)
    ui.click("restoreButton_fixture-backup")
    ui.click("restoreConfirmButton")
    assert ui.backend.calls.count(("restore", "fixture-backup")) == 1
    assert ui.find("resultSpaceStat").property("label") == "已恢复文件大小"
    assert ui.find("resultSpaceStat").property("value") == "4.00 KiB"
    ui.capture("minimum-restore-result")
    ui.click("resultDoneButton")
    ui.backend.data["busy"] = True
    ui.backend.changed.emit()
    assert ui.window.close() is False
    QTest.qWait(60)
    assert ui.find("closeNotice").property("visible")
    ui.click("closeCancelButton")
    assert ("cancel",) in ui.backend.calls
    assert not ui.warnings
