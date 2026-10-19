"""WizTree process integration. Never elevates, deletes history, or cleans files."""
from __future__ import annotations

import csv
import ctypes
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path


def find_wiztree(configured="") -> str | None:
    candidates = [configured, os.environ.get("WIZTREE_PATH", ""), r"D:\Tools\WizTree\WizTree64.exe", r"C:\Program Files\WizTree\WizTree64.exe", r"C:\Program Files (x86)\WizTree\WizTree64.exe"]
    for item in candidates:
        if item and Path(os.path.expandvars(str(item).strip().strip('"'))).is_file():
            return str(Path(os.path.expandvars(str(item).strip().strip('"'))).resolve())
    return shutil.which("WizTree64.exe") or shutil.which("WizTree64")


def _stop_process(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _is_admin():
    try:
        return os.name == "nt" and bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _validate_csv(path):
    from .analysis import _detect_encoding, _HEADERS, _normal_header
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("WizTree 未生成有效 CSV")
    with path.open("r", encoding=_detect_encoding(path), newline="") as stream:
        reader = csv.reader(stream)
        header = None
        for row in reader:
            labels = [_normal_header(value) for value in row]
            path_index = next((i for i, label in enumerate(labels) if label in _HEADERS["path"]), None)
            size_index = next((i for i, label in enumerate(labels) if label in _HEADERS["size"]), None)
            if path_index is not None and size_index is not None:
                header = (path_index, size_index)
                break
        if header is None:
            raise RuntimeError("WizTree CSV 缺少路径和大小表头")
        for row in reader:
            if len(row) > max(header) and row[header[0]].strip() and row[header[1]].strip():
                return
        raise RuntimeError("WizTree CSV 没有扫描条目")


def scan(target, outdir, timeout=1800, cancel_event=None, progress=None, executable=None) -> Path:
    if timeout <= 0:
        raise ValueError("扫描超时必须大于 0")
    if cancel_event is not None and cancel_event.is_set():
        raise InterruptedError("扫描已取消")
    target = str(target).strip()
    if not target or target.startswith("/") or target.startswith("-") or "\x00" in target:
        raise ValueError("请选择有效驱动器或文件夹")
    executable = executable or find_wiztree()
    if not executable:
        raise FileNotFoundError("未找到 WizTree64.exe，请在设置中选择其路径")
    outdir = Path(outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    output = outdir / f"scan_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.csv"
    # Request MFT mode only when this process already has administrator rights.
    # /admin=0 on an ordinary desktop session avoids an automatic UAC elevation.
    command = [str(executable), target, f"/export={output}", f"/admin={int(_is_admin())}", "/exportfolders=1", "/exportfiles=1", "/sortby=2", "/exportdrivecapacity=1", "/exportmaxdepth=0"]
    process = None
    started = time.monotonic()
    try:
        if progress:
            progress(f"正在启动 WizTree：{target}", 0)
        # No PIPE is left unread. A bounded temporary error log is unnecessary for this GUI tool.
        process = subprocess.Popen(command, shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        last_notice = -1
        while process.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("扫描已取消")
            elapsed = time.monotonic() - started
            if elapsed >= timeout:
                raise TimeoutError(f"WizTree 扫描超过 {timeout} 秒")
            if progress and int(elapsed) != last_notice:
                last_notice = int(elapsed)
                progress(f"WizTree 扫描中，已用 {last_notice} 秒", 0)
            time.sleep(0.1)
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("扫描已取消")
        if process.returncode != 0:
            raise RuntimeError(f"WizTree 扫描失败，退出码 {process.returncode}。整盘 MFT 扫描可能需要手动以管理员身份启动本应用。")
        _validate_csv(output)
        if progress:
            progress("WizTree 扫描完成", 0)
        return output
    except BaseException:
        if process is not None:
            _stop_process(process)
        output.unlink(missing_ok=True)
        raise


def drives() -> list[dict]:
    if os.name != "nt":
        usage = shutil.disk_usage(Path.home().anchor or "/")
        return [dict(path="/", label="本地磁盘", total=usage.total, used=usage.used, free=usage.free)]
    kernel = ctypes.windll.kernel32
    mask = kernel.GetLogicalDrives()
    result = []
    for index in range(26):
        if not mask & (1 << index):
            continue
        drive = chr(65 + index) + ":\\"
        # Skip disconnected, optical and removable media to avoid blocking on them.
        if kernel.GetDriveTypeW(ctypes.c_wchar_p(drive)) != 3:
            continue
        try:
            usage = shutil.disk_usage(drive)
        except OSError:
            continue
        label = ctypes.create_unicode_buffer(261)
        kernel.GetVolumeInformationW(ctypes.c_wchar_p(drive), label, len(label), None, None, None, None, 0)
        result.append(dict(path=drive, label=label.value or "本地磁盘", total=usage.total, used=usage.used, free=usage.free))
    return result
