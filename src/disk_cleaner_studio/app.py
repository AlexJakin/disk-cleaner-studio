from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from .controller import AppController


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Disk Cleaner Studio · 本地磁盘分析与可恢复缓存清理")
    parser.add_argument("--demo", action="store_true", help="载入模拟数据，不扫描真实磁盘")
    parser.add_argument("--import-csv", metavar="CSV", help="导入 WizTree CSV")
    parser.add_argument("--data-dir", type=Path, help="配置与扫描数据库目录")
    parser.add_argument("--smoke", action="store_true", help="离屏启动验证后自动退出")
    parser.add_argument("--screenshot", type=Path, help="启动后保存界面截图（用于开发验证）")
    parser.add_argument("--page", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--quit-after", type=int, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.smoke:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Disk Cleaner Studio")
    app.setOrganizationName("DiskCleanerStudio")
    app.setApplicationVersion("0.1.0")
    # The Windows offscreen plugin has no native font database. Register real
    # Windows fonts so smoke screenshots also exercise Chinese text layout.
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen" and os.name == "nt":
        font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
            if (font_dir / name).is_file():
                QFontDatabase.addApplicationFont(str(font_dir / name))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "qml" / "assets" / "icon.svg")))
    QQuickStyle.setStyle("Basic")
    data_dir = args.data_dir or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "DiskCleanerStudio"
    backend = AppController(data_dir)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "qml" / "Main.qml")))
    if not engine.rootObjects():
        backend.shutdown()
        return 1
    window = engine.rootObjects()[0]
    if args.demo:
        QTimer.singleShot(0, backend.loadDemo)
    elif args.import_csv:
        QTimer.singleShot(0, lambda: backend.import_file(args.import_csv))
    if args.page:
        QTimer.singleShot(500, lambda: window.setProperty("pageIndex", args.page))
    exit_code = [0]

    def capture():
        if backend.busy:
            QTimer.singleShot(250, capture)
            return
        if args.screenshot:
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            if not window.grabWindow().save(str(args.screenshot)):
                print("Screenshot failed", file=sys.stderr)
                exit_code[0] = 1
        if args.smoke:
            if backend.error:
                print(backend.error, file=sys.stderr)
                exit_code[0] = 1
            print(f"QML OK: {backend.summary.get('entry_count', 0)} entries")
            app.quit()
    if args.screenshot or args.smoke:
        QTimer.singleShot(1500, capture)
    if args.quit_after:
        QTimer.singleShot(args.quit_after, app.quit)
    result = app.exec()
    backend.shutdown()
    return exit_code[0] or result
