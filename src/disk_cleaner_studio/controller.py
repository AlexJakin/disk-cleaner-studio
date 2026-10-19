"""Qt bridge. Every slow operation runs outside the GUI thread."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from .core.analysis import ScanRepository
from .core.cleanup import CleanupService
from .core import scanner


def format_bytes(value: float) -> str:
    number = float(value or 0)
    sign = "−" if number < 0 else ""
    number = abs(number)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if number < 1024 or unit == "TiB":
            return f"{sign}{number:.1f} {unit}" if unit != "B" else f"{sign}{number:.0f} B"
        number /= 1024
    return "0 B"


def empty_summary() -> dict:
    return dict(scan_id="", source="", root="", scanned_at="", entry_count=0,
                total_bytes=0, used_bytes=0, free_bytes=0, candidate_bytes=0,
                candidates=[], warnings=[], is_demo=False)


class AppController(QObject):
    changed = Signal()
    _progressed = Signal(str, int)
    _finished = Signal(str, object)
    _failed = Signal(str)

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.repo = ScanRepository(self.data_dir / "scans")
        self._settings_file = self.data_dir / "settings.json"
        self._settings = self._read_settings()
        default_backup = Path("D:/DiskCleanerStudioBackups") if Path("D:/").exists() else self.data_dir / "backups"
        self._backup_root = str(self._settings.get("backup_root") or default_backup)
        self._wiztree_path = str(self._settings.get("wiztree_path") or scanner.find_wiztree() or "")
        self._scan_target = str(self._settings.get("scan_target") or "C:\\")
        try:
            self._scan_timeout = max(30, min(int(self._settings.get("scan_timeout", 1800)), 86400))
        except (TypeError, ValueError, OverflowError):
            self._scan_timeout = 1800
        ignored = self._settings.get("ignored_paths", [])
        self._ignored = [p for p in ignored if isinstance(p, str)] if isinstance(ignored, list) else []
        self._summary = empty_summary()
        self._entries: list[dict] = []
        self._top_files: list[dict] = []
        self._candidates: list[dict] = []
        self._selected: set[str] = set()
        self._detail: dict = {}
        self._current_path = ""
        self._history: list[dict] = []
        self._comparison: list[dict] = []
        self._backups: list[dict] = []
        self._drives = scanner.drives()
        self._busy = False
        self._status = "选择磁盘开始扫描，或导入已有的 WizTree CSV"
        self._error = ""
        self._progress_count = 0
        self._elapsed = "00:00"
        self._started = 0.0
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._plan: dict = {}
        self._pending_plan: dict | None = None
        self._plan_service: CleanupService | None = None
        self._last_result: dict = {}
        self._progressed.connect(self._on_progress)
        self._finished.connect(self._on_finished)
        self._failed.connect(self._on_failed)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._refresh_history()
        self.refreshBackups()

    def _read_settings(self) -> dict:
        if not self._settings_file.exists():
            return {}
        try:
            result = json.loads(self._settings_file.read_text(encoding="utf-8"))
            return result if isinstance(result, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_settings(self):
        values = dict(backup_root=self._backup_root, wiztree_path=self._wiztree_path,
                      scan_target=self._scan_target, scan_timeout=self._scan_timeout,
                      ignored_paths=self._ignored)
        temp = self._settings_file.with_suffix(".tmp")
        temp.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self._settings_file)

    def _invalidate_plan(self):
        self._plan = {}
        self._pending_plan = None
        self._plan_service = None

    def _refresh_history(self):
        self._history = [{**row, "id": row.get("scan_id", "")} for row in self.repo.list_scans()]

    def _update_candidates(self):
        ignored = {os.path.normcase(p.rstrip("\\/")) for p in self._ignored}
        self._candidates = []
        inspector, inspect_error = None, ""
        if not self._summary.get("is_demo", False):
            try:
                inspector = CleanupService(Path(self._backup_root))
            except Exception as exc:
                inspect_error = f"请先修正备份目录设置：{exc}"
        for raw in self._summary.get("candidates", []):
            item = dict(raw)
            key = os.path.normcase(item["path"].rstrip("\\/"))
            item["ignored"] = key in ignored
            item["cleanable"] = bool(item.get("cleanable")) and not self._summary.get("is_demo", False)
            if item["cleanable"]:
                check = inspector.inspect_target(item["path"]) if inspector else {"eligible": False, "reason": inspect_error}
                item["cleanable"] = bool(check["eligible"])
                if not item["cleanable"]:
                    item["reason"] += "；" + check["reason"]
            item["selected"] = item["id"] in self._selected and not item["ignored"]
            self._candidates.append(item)

    def _load_summary(self, summary: dict):
        self._summary = {**empty_summary(), **summary}
        self._selected.clear()
        self._detail = {}
        self._invalidate_plan()
        self._last_result = {}
        self._update_candidates()
        scan_id = self._summary["scan_id"]
        self._current_path = self._summary["root"]
        self._entries = self.repo.children(scan_id, self._current_path)[:500]
        self._top_files = self.repo.top_files(scan_id, 100)
        self._comparison = self.repo.compare(scan_id)
        self._refresh_history()

    def _run(self, action: str, function: Callable):
        if self._busy:
            return
        self._busy, self._error = True, ""
        self._progress_count = 0
        self._started, self._elapsed = time.monotonic(), "00:00"
        self._cancel_event = threading.Event()
        self._timer.start()
        self.changed.emit()

        def run():
            try:
                result = function(self._cancel_event, self._progressed.emit)
                if action == "preview" and self._cancel_event.is_set():
                    raise InterruptedError("计划生成已取消")
            except InterruptedError:
                self._failed.emit("任务已取消。已完成的扫描历史和备份会保留。")
            except Exception as exc:
                self._failed.emit(str(exc) or type(exc).__name__)
            else:
                self._finished.emit(action, result)

        self._worker = threading.Thread(target=run, name=f"studio-{action}", daemon=False)
        self._worker.start()

    @Slot()
    def _tick(self):
        seconds = max(0, int(time.monotonic() - self._started))
        self._elapsed = f"{seconds // 60:02d}:{seconds % 60:02d}"
        self.changed.emit()

    @Slot(str, int)
    def _on_progress(self, message: str, count: int):
        self._status, self._progress_count = message, count
        self.changed.emit()

    @Slot(str)
    def _on_failed(self, message: str):
        self._timer.stop()
        self._busy, self._error = False, message
        self._status = "任务已取消" if "取消" in message else "任务未完成，请查看原因"
        self._invalidate_plan()
        self.refreshBackups()
        self.changed.emit()

    @Slot(str, object)
    def _on_finished(self, action: str, result):
        self._timer.stop()
        self._busy = False
        try:
            if action in ("import", "scan", "demo"):
                self._load_summary(result)
                self._status = "示例已载入 · 模拟数据，仅供体验" if self._summary["is_demo"] else "分析完成 · 可以浏览目录和清理建议"
            elif action == "preview":
                self._pending_plan = result
                self._plan = {**result, "total_bytes": result.get("estimated_bytes", 0), "can_execute": True}
                self._status = "计划已生成，请核对目标、影响与备份位置"
            elif action in ("cleanup", "restore"):
                self._invalidate_plan()
                self._selected.clear()
                self._update_candidates()
                self._last_result = self._normalize_result(result)
                self._status = self._last_result["message"]
                self._error = "；".join(str(e) for e in result.get("errors", []))
                self.refreshBackups()
                self._drives = scanner.drives()
        except Exception as exc:
            self._error = str(exc)
            self._status = "结果读取失败"
        self.changed.emit()

    @staticmethod
    def _normalize_result(result: dict) -> dict:
        items = [{**i, "message": i.get("error", ""), "bytes": i.get("deleted_bytes", i.get("restored_bytes", 0))}
                 for i in result.get("items", [])]
        status = result.get("status", "failed")
        operation = result.get("operation", "cleanup")
        labels = {"complete": "完成", "partial": "部分完成", "failed": "失败", "cancelled": "已取消"}
        title = "恢复" if operation == "restore" else "备份与清理"
        return {**result, "items": items, "success_count": sum(i.get("status") in ("complete", "deleted", "restored", "success") for i in items),
                "failed_count": sum(i.get("status") in ("failed", "partial") for i in items),
                "skipped_count": sum(i.get("status") in ("skipped", "cancelled") for i in items),
                "freed_bytes": result.get("free_space_delta_bytes", 0),
                "message": f"{title}{labels.get(status, status)} · 扫描快照不会自动更新，请重新扫描查看最新占用"}

    summary = Property("QVariantMap", lambda s: s._summary, notify=changed)
    drives = Property("QVariantList", lambda s: s._drives, notify=changed)
    busy = Property(bool, lambda s: s._busy, notify=changed)
    status = Property(str, lambda s: s._status, notify=changed)
    error = Property(str, lambda s: s._error, notify=changed)
    progressCount = Property(int, lambda s: s._progress_count, notify=changed)
    elapsed = Property(str, lambda s: s._elapsed, notify=changed)
    entries = Property("QVariantList", lambda s: s._entries, notify=changed)
    topFiles = Property("QVariantList", lambda s: s._top_files, notify=changed)
    candidates = Property("QVariantList", lambda s: s._candidates, notify=changed)
    selectedBytes = Property("qlonglong", lambda s: sum(c["size"] for c in s._candidates if c["selected"]), notify=changed)
    selectedCount = Property(int, lambda s: sum(c["selected"] for c in s._candidates), notify=changed)
    detail = Property("QVariantMap", lambda s: s._detail, notify=changed)
    currentPath = Property(str, lambda s: s._current_path, notify=changed)
    history = Property("QVariantList", lambda s: s._history, notify=changed)
    comparison = Property("QVariantList", lambda s: s._comparison, notify=changed)
    backups = Property("QVariantList", lambda s: s._backups, notify=changed)
    backupRoot = Property(str, lambda s: s._backup_root, notify=changed)
    wiztreePath = Property(str, lambda s: s._wiztree_path, notify=changed)
    scanTarget = Property(str, lambda s: s._scan_target, notify=changed)
    scanTimeout = Property(int, lambda s: s._scan_timeout, notify=changed)
    plan = Property("QVariantMap", lambda s: s._plan, notify=changed)
    lastResult = Property("QVariantMap", lambda s: s._last_result, notify=changed)
    ignoredPaths = Property("QVariantList", lambda s: s._ignored, notify=changed)

    @Slot(float, result=str)
    def formatBytes(self, value):
        return format_bytes(value)

    @Slot()
    def importCsv(self):
        if self._busy:
            return
        path, _ = QFileDialog.getOpenFileName(None, "导入 WizTree 扫描结果", "", "WizTree CSV (*.csv);;所有文件 (*)")
        if path:
            self.import_file(path)

    def import_file(self, path: str):
        self._invalidate_plan()
        self._status = "正在导入并建立目录索引…"
        self._run("import", lambda cancel, progress: self.repo.import_csv(path, cancel_event=cancel, progress=progress))

    @Slot()
    def loadDemo(self):
        if self._busy:
            return
        base = Path(__file__).resolve().parent
        path = base / "resources" / "demo.csv"
        if not path.exists():
            path = base.parents[1] / "examples" / "demo.csv"
        self._status = "正在载入模拟数据…"
        self._run("demo", lambda cancel, progress: self.repo.import_csv(path, cancel_event=cancel, progress=progress))

    @Slot(str)
    def startScan(self, target: str):
        if self._busy:
            return
        target = target.strip() or self._scan_target
        self.setScanTarget(target)
        self._invalidate_plan()
        exe, timeout = self._wiztree_path, self._scan_timeout
        self._status = "启动 WizTree 扫描…"

        def job(cancel, progress):
            path = scanner.scan(target, self.data_dir / "exports", timeout=timeout,
                                cancel_event=cancel, progress=progress, executable=exe or None)
            return self.repo.import_csv(path, cancel_event=cancel, progress=progress)
        self._run("scan", job)

    @Slot()
    def cancelTask(self):
        if self._busy:
            self._cancel_event.set()
            self._status = "正在取消，等待当前步骤安全结束…"
            self.changed.emit()

    @Slot(str)
    def loadScan(self, scan_id: str):
        if self._busy:
            return
        try:
            self._load_summary(self.repo.load_scan(scan_id))
            self._status = "已打开历史扫描 · 显示扫描时的快照"
        except Exception as exc:
            self._error = str(exc)
        self.changed.emit()

    @Slot(str)
    def navigate(self, path: str):
        if self._busy or not self._summary["scan_id"]:
            return
        try:
            self._entries = self.repo.children(self._summary["scan_id"], path)[:500]
            self._current_path = path or self._summary["root"]
            self._detail = {}
        except Exception as exc:
            self._error = str(exc)
        self.changed.emit()

    @Slot()
    def goUp(self):
        import ntpath
        path = self._current_path
        if path.rstrip("\\/").casefold() == self._summary["root"].rstrip("\\/").casefold():
            return
        parent = ntpath.dirname(path.rstrip("\\/")) if "\\" in path else str(Path(path).parent)
        self.navigate(parent)

    @Slot()
    def showTopFiles(self):
        if not self._busy and self._summary["scan_id"]:
            self._top_files = self.repo.top_files(self._summary["scan_id"], 100)
            self.changed.emit()

    @Slot(str)
    def selectDetail(self, path: str):
        for item in self._candidates + self._entries + self._top_files:
            if item["path"] == path:
                self._detail = dict(item)
                self.changed.emit()
                return

    @Slot(str)
    def toggleCandidate(self, candidate_id: str):
        if self._busy or self._summary["is_demo"]:
            return
        candidate = next((c for c in self._candidates if c["id"] == candidate_id), None)
        if not candidate or candidate["ignored"] or not candidate["cleanable"]:
            return
        if candidate_id in self._selected:
            self._selected.remove(candidate_id)
        else:
            self._selected.add(candidate_id)
        self._invalidate_plan()
        self._update_candidates()
        self.changed.emit()

    @Slot(str)
    def ignoreCandidate(self, candidate_id: str):
        if self._busy:
            return
        candidate = next((c for c in self._candidates if c["id"] == candidate_id), None)
        if candidate:
            if candidate["path"] not in self._ignored:
                self._ignored.append(candidate["path"])
            self._selected.discard(candidate_id)
            self._invalidate_plan()
            self._update_candidates()
            self._save_settings()
            self.changed.emit()

    @Slot(str)
    def unignore(self, path: str):
        if self._busy:
            return
        self._ignored = [p for p in self._ignored if p != path]
        self._update_candidates()
        self._save_settings()
        self.changed.emit()

    @Slot(str)
    def setBackupRoot(self, path: str):
        if self._busy or not path.strip():
            return
        self._backup_root = str(Path(path.strip()).expanduser().absolute())
        self._invalidate_plan()
        self._selected.clear()
        self._update_candidates()
        self._save_settings()
        self.refreshBackups()

    @Slot()
    def chooseBackupRoot(self):
        if self._busy:
            return
        path = QFileDialog.getExistingDirectory(None, "选择固定备份目录", self._backup_root)
        if path:
            self.setBackupRoot(path)

    @Slot(str)
    def setWiztreePath(self, path: str):
        if self._busy:
            return
        self._wiztree_path = path.strip()
        self._save_settings()
        self.changed.emit()

    @Slot()
    def chooseWiztree(self):
        if self._busy:
            return
        path, _ = QFileDialog.getOpenFileName(None, "选择 WizTree64.exe", self._wiztree_path, "WizTree (WizTree*.exe)")
        if path:
            self.setWiztreePath(path)

    @Slot(str)
    def setScanTarget(self, target: str):
        if not self._busy:
            self._scan_target = target.strip()
            self._save_settings()
            self.changed.emit()

    @Slot(int)
    def setScanTimeout(self, timeout: int):
        if not self._busy:
            self._scan_timeout = max(30, min(int(timeout), 86400))
            self._save_settings()
            self.changed.emit()

    @Slot()
    def previewPlan(self):
        if self._busy or self._summary["is_demo"]:
            return
        paths = [c["path"] for c in self._candidates if c["selected"] and c["cleanable"] and not c["ignored"]]
        if not paths:
            self._error = "请先选择可清理的缓存项。"
            self.changed.emit()
            return
        self._invalidate_plan()
        self._plan_service = CleanupService(Path(self._backup_root))
        service = self._plan_service
        self._status = "正在校验目标并生成备份计划…"
        self._run("preview", lambda cancel, progress: service.create_plan(paths, cancel_event=cancel, progress=progress))

    @Slot()
    def executePlan(self):
        if self._busy or self._summary["is_demo"] or not self._pending_plan or not self._plan_service:
            return
        plan, service = self._pending_plan, self._plan_service
        self._status = "正在备份并核验所有目标…"
        self._run("cleanup", lambda cancel, progress: service.execute_plan(plan, cancel_event=cancel, progress=progress))

    @Slot()
    def refreshBackups(self):
        if self._busy:
            return
        try:
            service = CleanupService(Path(self._backup_root))
            self._backups = [{**row, "id": row.get("id", row.get("backup_id", "")),
                              "total_bytes": row.get("total_bytes", row.get("estimated_bytes", 0))}
                             for row in service.list_backups()]
        except Exception as exc:
            self._backups = []
            self._error = f"备份目录无法读取：{exc}"
        self.changed.emit()

    @Slot(str)
    def restoreBackup(self, backup_id: str):
        if self._busy or not any(b["id"] == backup_id for b in self._backups):
            return
        service = CleanupService(Path(self._backup_root))
        self._status = "正在校验备份并恢复…"
        self._run("restore", lambda cancel, progress: service.restore_backup(backup_id, cancel_event=cancel, progress=progress))

    @Slot()
    def clearError(self):
        self._error = ""
        self.changed.emit()

    @Slot(str)
    def openPath(self, path: str):
        known = {i["path"] for i in self._entries + self._top_files + self._candidates}
        known.update((self._backup_root, self._current_path))
        if path not in known or self._summary["is_demo"] and path != self._backup_root:
            return
        target = Path(path)
        if target.is_file():
            target = target.parent
        if target.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def shutdown(self):
        self._cancel_event.set()
        if self._worker and self._worker.is_alive():
            self._worker.join()
