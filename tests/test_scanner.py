import subprocess
import threading
from pathlib import Path

import pytest

from disk_cleaner_studio.core import scanner


class FakeProcess:
    def __init__(self, code=0, running=False):
        self.returncode = None if running else code
        self.terminated = False
        self.killed = False
    def poll(self):
        return self.returncode
    def terminate(self):
        self.terminated = True
        self.returncode = -15
    def kill(self):
        self.killed = True
        self.returncode = -9
    def wait(self, timeout=None):
        return self.returncode


def fake_launch(monkeypatch, *, code=0, running=False, contents="File Name,Size,Allocated,Attributes\nC:\\test.txt,10,10,32\n", on_launch=None):
    captured = {}
    process = FakeProcess(code, running)
    def launch(command, **kwargs):
        output = Path(next(item[8:] for item in command if item.startswith("/export=")))
        if contents is not None:
            output.write_text(contents, encoding="utf-8-sig")
        captured.update(command=command, kwargs=kwargs, output=output)
        if on_launch:
            on_launch()
        return process
    monkeypatch.setattr(scanner.subprocess, "Popen", launch)
    return process, captured


def test_scan_uses_array_no_elevation_and_preserves_history(monkeypatch, tmp_path):
    monkeypatch.setattr(scanner, "_is_admin", lambda: False)
    old = tmp_path / "old.csv"
    old.write_text("history", encoding="utf-8")
    process, captured = fake_launch(monkeypatch)
    output = scanner.scan(r"C:\Test Folder", tmp_path, executable="WizTree64.exe")
    assert output.is_file()
    assert old.read_text() == "history"
    assert captured["command"][1] == r"C:\Test Folder"
    assert "/admin=0" in captured["command"]
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["stderr"] == subprocess.DEVNULL


def test_existing_admin_rights_enable_mft_without_elevation(monkeypatch, tmp_path):
    monkeypatch.setattr(scanner, "_is_admin", lambda: True)
    process, captured = fake_launch(monkeypatch)
    scanner.scan("C:", tmp_path, executable="fake")
    assert "/admin=1" in captured["command"]


def test_nonzero_exit_removes_incomplete_csv(monkeypatch, tmp_path):
    process, captured = fake_launch(monkeypatch, code=7)
    with pytest.raises(RuntimeError, match="退出码 7"):
        scanner.scan("C:", tmp_path, executable="fake")
    assert not captured["output"].exists()


@pytest.mark.parametrize("contents", [None, "", "garbage\n", "File Name,Size\n"])
def test_missing_empty_or_invalid_csv_rejected(monkeypatch, tmp_path, contents):
    process, captured = fake_launch(monkeypatch, contents=contents)
    with pytest.raises(RuntimeError):
        scanner.scan("C:", tmp_path, executable="fake")
    assert not captured["output"].exists()


def test_cancellation_stops_process_and_removes_csv(monkeypatch, tmp_path):
    event = threading.Event()
    process, captured = fake_launch(monkeypatch, running=True, on_launch=event.set)
    with pytest.raises(InterruptedError):
        scanner.scan("C:", tmp_path, executable="fake", cancel_event=event)
    assert process.terminated
    assert not captured["output"].exists()


def test_timeout_stops_process_and_removes_csv(monkeypatch, tmp_path):
    process, captured = fake_launch(monkeypatch, running=True)
    ticks = iter([0, 10])
    monkeypatch.setattr(scanner.time, "monotonic", lambda: next(ticks))
    with pytest.raises(TimeoutError):
        scanner.scan("C:", tmp_path, timeout=1, executable="fake")
    assert process.terminated
    assert not captured["output"].exists()


def test_does_not_finish_when_csv_exists_but_process_runs(monkeypatch, tmp_path):
    process, captured = fake_launch(monkeypatch, running=True)
    calls = []
    def sleep(_):
        calls.append(True)
        process.returncode = 0
    monkeypatch.setattr(scanner.time, "sleep", sleep)
    output = scanner.scan("C:", tmp_path, executable="fake")
    assert calls and output.exists()


def test_find_wiztree_prefers_configured_then_environment(monkeypatch, tmp_path):
    configured = tmp_path / "configured.exe"
    env = tmp_path / "env.exe"
    configured.touch()
    env.touch()
    monkeypatch.setenv("WIZTREE_PATH", str(env))
    assert scanner.find_wiztree(str(configured)) == str(configured.resolve())
    assert scanner.find_wiztree() == str(env.resolve())


def test_scanner_progress_seconds_are_message_only_not_item_counts(monkeypatch, tmp_path):
    process, captured = fake_launch(monkeypatch, running=True)
    ticks = iter([10, 12])
    monkeypatch.setattr(scanner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(scanner.time, "sleep", lambda _: setattr(process, "returncode", 0))
    notifications = []
    scanner.scan("C:", tmp_path, executable="fake", progress=lambda message, count: notifications.append((message, count)))
    assert any("2 秒" in message for message, _ in notifications)
    assert notifications[-1][0] == "WizTree 扫描完成"
    assert all(count == 0 for _, count in notifications)
