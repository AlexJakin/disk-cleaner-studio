"""Qt bridge regressions with real queued signals and isolated CSV/SQLite data.

The cleanup service is replaced in every test: no live cache or backup is read,
written, cleaned, restored, or opened by this suite.
"""
import csv
import json
import ntpath
import os
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from disk_cleaner_studio import controller as bridge


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance() or QApplication([])
    yield application


def wait_idle(controller, application, timeout=5):
    deadline = time.monotonic() + timeout
    while controller.busy and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.002)
    application.processEvents()
    assert not controller.busy, "后台任务未在测试期限内完成"


@pytest.fixture
def make_controller(monkeypatch, tmp_path, qapp):
    instances = []
    calls = {"preview": [], "execute": [], "restore": []}

    class FakeCleanupService:
        def __init__(self, backup_root):
            self.backup_root = backup_root

        def list_backups(self):
            return []

        def inspect_target(self, path):
            return {"eligible": True, "reason": "测试路径允许"}

        def create_plan(self, paths, cancel_event=None, progress=None):
            calls["preview"].append(list(paths))
            if progress:
                progress("测试计划已校验", len(paths))
            return {"id": "test-plan", "items": [{"path": path} for path in paths],
                    "estimated_bytes": 200, "warnings": []}

        def execute_plan(self, plan, cancel_event=None, progress=None):
            calls["execute"].append(plan)
            raise AssertionError("测试不应执行任何清理")

        def restore_backup(self, backup_id, cancel_event=None, progress=None):
            calls["restore"].append(backup_id)
            raise AssertionError("测试不应执行任何恢复")

    monkeypatch.setattr(bridge, "CleanupService", FakeCleanupService)
    monkeypatch.setattr(bridge.scanner, "drives", lambda: [])
    monkeypatch.setattr(bridge.scanner, "find_wiztree", lambda configured="": None)

    def create(settings=None, directory=None):
        directory = Path(directory) if directory else tmp_path / f"app-{len(instances)}"
        directory.mkdir(parents=True, exist_ok=True)
        settings_path = directory / "settings.json"
        if settings is not None or not settings_path.exists():
            values = {"backup_root": str(directory / "test-backups")}
            values.update(settings or {})
            settings_path.write_text(json.dumps(values), encoding="utf-8")
        instance = bridge.AppController(directory)
        instances.append(instance)
        return instance

    create.service = FakeCleanupService
    create.calls = calls
    yield create
    for instance in instances:
        instance.shutdown()
        instance._timer.stop()
    qapp.processEvents()
    for instance in instances:
        instance.deleteLater()
    qapp.processEvents()


@pytest.fixture
def synthetic_csv(tmp_path):
    # These are CSV observations only. No directory under this profile is opened.
    root = os.environ.get("USERPROFILE", r"C:\Users\TestUser").rstrip("\\/")
    cache = ntpath.join(root, r"AppData\Local\pip\Cache")
    documents = ntpath.join(root, "Documents")
    path = tmp_path / "controller-fixture.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["File Name", "Size", "Allocated", "Attributes"])
        writer.writerows([
            [root + "\\", 300, 200, 16],
            [cache, 200, 100, 16],
            [ntpath.join(cache, "package.whl"), 200, 100, 32],
            [documents, 100, 100, 16],
            [ntpath.join(documents, "notes.txt"), 100, 100, 32],
        ])
    return {"csv": path, "root": root, "cache": cache, "documents": documents}


def import_fixture(controller, fixture, application):
    controller.import_file(str(fixture["csv"]))
    wait_idle(controller, application)
    assert not controller.error
    assert not controller.summary["is_demo"]
    return next(item for item in controller.candidates if item["cleanable"])


def test_demo_load_is_asynchronous_and_never_enables_cleanup(make_controller, qapp, monkeypatch):
    controller = make_controller()
    original_import = controller.repo.import_csv
    worker_threads = []
    started = threading.Event()
    released = threading.Event()

    def delayed_import(*args, **kwargs):
        worker_threads.append(threading.get_ident())
        started.set()
        assert released.wait(2)
        return original_import(*args, **kwargs)

    monkeypatch.setattr(controller.repo, "import_csv", delayed_import)
    main_thread = threading.get_ident()
    controller.loadDemo()
    assert controller.busy
    assert started.wait(2)
    assert len(worker_threads) == 1 and worker_threads[0] != main_thread
    released.set()
    wait_idle(controller, qapp)

    assert controller.summary["is_demo"] is True
    assert controller.history and controller.entries and controller.candidates
    assert controller.summary["candidate_bytes"] > 0
    for item in controller.candidates:
        controller.toggleCandidate(item["id"])
    controller.previewPlan()
    controller.executePlan()
    assert controller.selectedCount == 0
    assert controller.plan == {}
    assert all(not item["cleanable"] for item in controller.candidates)
    assert make_controller.calls == {"preview": [], "execute": [], "restore": []}


def test_navigation_and_top_files_preserve_directory_state(make_controller, qapp, synthetic_csv):
    controller = make_controller()
    import_fixture(controller, synthetic_csv, qapp)
    root = controller.currentPath
    root_entries = list(controller.entries)
    controller.goUp()
    assert controller.currentPath == root
    assert controller.entries == root_entries

    controller.navigate(synthetic_csv["cache"])
    assert [item["name"] for item in controller.entries] == ["package.whl"]
    controller.selectDetail(ntpath.join(synthetic_csv["cache"], "package.whl"))
    before = (controller.currentPath, list(controller.entries), dict(controller.detail))
    controller.showTopFiles()
    assert (controller.currentPath, controller.entries, controller.detail) == before
    assert [item["size"] for item in controller.topFiles] == [200, 100]
    controller.goUp()
    assert controller.currentPath == ntpath.dirname(synthetic_csv["cache"])
    assert controller.entries[0]["name"] == "Cache"
    controller.navigate("")
    assert controller.currentPath == root
    assert controller.entries == root_entries


def test_preview_failure_invalidates_an_earlier_executable_plan(make_controller, qapp, synthetic_csv, monkeypatch):
    controller = make_controller()
    candidate = import_fixture(controller, synthetic_csv, qapp)
    controller.toggleCandidate(candidate["id"])
    controller.previewPlan()
    wait_idle(controller, qapp)
    assert controller.plan["can_execute"] is True

    def failed_plan(self, paths, cancel_event=None, progress=None):
        raise ValueError("模拟无法读取缓存，请关闭应用")

    monkeypatch.setattr(make_controller.service, "create_plan", failed_plan)
    controller.previewPlan()
    assert controller.plan == {}
    wait_idle(controller, qapp)
    assert "无法读取缓存" in controller.error
    assert controller.plan == {}
    assert controller._pending_plan is None
    controller.executePlan()
    assert make_controller.calls["execute"] == []


@pytest.mark.parametrize("late_success", [False, True])
def test_cancelled_preview_never_reopens_execution_gate(make_controller, qapp, synthetic_csv, monkeypatch, late_success):
    controller = make_controller()
    candidate = import_fixture(controller, synthetic_csv, qapp)
    controller.toggleCandidate(candidate["id"])
    started = threading.Event()
    released = threading.Event()
    events = []

    def cancellable_plan(self, paths, cancel_event=None, progress=None):
        assert cancel_event is not None
        events.append(cancel_event)
        started.set()
        assert released.wait(2)
        if cancel_event.is_set() and not late_success:
            raise InterruptedError("测试计划已取消")
        return {"id": "late-plan", "estimated_bytes": 200, "items": [], "warnings": []}

    monkeypatch.setattr(make_controller.service, "create_plan", cancellable_plan)
    controller.previewPlan()
    assert started.wait(2)
    controller.cancelTask()
    assert events[0].is_set()
    released.set()
    wait_idle(controller, qapp)
    assert "取消" in controller.error
    assert controller.plan == {}
    assert controller._pending_plan is None
    assert controller._plan_service is None
    controller.executePlan()
    assert make_controller.calls["execute"] == []


@pytest.mark.parametrize("value,expected", [(None, 1800), ("broken", 1800), ({}, 1800), (float("inf"), 1800), (-10, 30), (999999, 86400)])
def test_invalid_settings_timeout_defaults_or_clamps(make_controller, value, expected):
    controller = make_controller({"scan_timeout": value, "ignored_paths": {"invalid": "shape"}, "scan_target": None})
    assert controller.scanTimeout == expected
    assert controller.ignoredPaths == []
    assert controller.scanTarget == "C:\\"
    assert not controller.busy


def test_selection_ignore_and_unignore_persist_without_restoring_selection(make_controller, qapp, synthetic_csv, tmp_path):
    directory = tmp_path / "persistent-app"
    controller = make_controller(directory=directory)
    candidate = import_fixture(controller, synthetic_csv, qapp)
    scan_id = controller.summary["scan_id"]
    controller.toggleCandidate(candidate["id"])
    assert controller.selectedCount == 1
    assert controller.selectedBytes == 200
    controller.previewPlan()
    wait_idle(controller, qapp)
    assert controller.plan["can_execute"] is True
    controller.ignoreCandidate(candidate["id"])
    assert controller.selectedCount == 0
    assert controller.plan == {} and controller._pending_plan is None
    assert next(item for item in controller.candidates if item["id"] == candidate["id"])["ignored"] is True
    controller.toggleCandidate(candidate["id"])
    assert controller.selectedCount == 0

    reopened = make_controller(directory=directory)
    reopened.loadScan(scan_id)
    ignored = next(item for item in reopened.candidates if item["id"] == candidate["id"])
    assert ignored["ignored"] is True
    assert reopened.selectedCount == 0
    assert candidate["path"] in reopened.ignoredPaths

    reopened.unignore(candidate["path"])
    assert not next(item for item in reopened.candidates if item["id"] == candidate["id"])["ignored"]
    reopened.toggleCandidate(candidate["id"])
    assert reopened.selectedCount == 1
    after_unignore = make_controller(directory=directory)
    after_unignore.loadScan(scan_id)
    assert candidate["path"] not in after_unignore.ignoredPaths
    assert not next(item for item in after_unignore.candidates if item["id"] == candidate["id"])["ignored"]
    assert after_unignore.selectedCount == 0


def test_malformed_settings_json_falls_back_instead_of_crashing(make_controller, tmp_path):
    directory = tmp_path / "broken-json"
    directory.mkdir()
    (directory / "settings.json").write_text("{ not valid json", encoding="utf-8")
    controller = make_controller(directory=directory)
    assert controller.scanTimeout == 1800
    assert controller.ignoredPaths == []
    assert controller.summary["scan_id"] == ""


def test_current_path_rejection_disables_csv_candidate(make_controller, qapp, synthetic_csv, monkeypatch):
    def rejected(self, path):
        return {"eligible": False, "reason": "测试：路径不存在或属于其他账号"}

    monkeypatch.setattr(make_controller.service, "inspect_target", rejected)
    controller = make_controller()
    controller.import_file(str(synthetic_csv["csv"]))
    wait_idle(controller, qapp)
    candidate = next(item for item in controller.candidates if item["path"] == synthetic_csv["cache"])
    assert not candidate["cleanable"]
    assert "不存在或属于其他账号" in " ".join(str(value) for value in candidate.values())
    controller.toggleCandidate(candidate["id"])
    assert controller.selectedCount == 0
    controller.previewPlan()
    assert not controller.busy
    assert not controller.plan
    assert make_controller.calls["preview"] == []
