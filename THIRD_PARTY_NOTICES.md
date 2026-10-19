# Third-party components

Disk Cleaner Studio uses unmodified third-party components. Runtime libraries are kept as separate files in the onedir distribution; they are not statically linked into this application. The application source and build script are included alongside the distribution.

## Qt for Python / PySide6 Essentials / Shiboken6 6.8.3

Copyright The Qt Company Ltd. and other contributors. PySide6 Essentials package metadata declares LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only. Qt modules and their third-party components have their own notices and license conditions.

- Project: https://www.qt.io/qt-for-python
- Licensing information: https://doc.qt.io/qtforpython-6/licenses.html
- Binding source: https://code.qt.io/cgit/pyside/pyside-setup.git/?h=6.8.3
- Qt source archives: https://download.qt.io/archive/qt/6.8/6.8.3/
- Corresponding wheel: https://pypi.org/project/PySide6-Essentials/6.8.3/

GNU license texts are included in `licenses/`. Original package metadata and supplied notices are preserved under `dist/DiskCleanerStudio/licenses/` when building. No modifications have been made to these libraries. Runtime library files may be replaced with compatible builds; the source application may also be run with a compatible independently installed Qt for Python environment. Rebuilding instructions are in README.md and build.ps1.

## Python 3.12 runtime

Python is distributed under the Python Software Foundation License and accompanying notices. See https://docs.python.org/3.12/license.html and https://www.python.org/downloads/release/python-3127/ . The runtime used for this local build is supplied by the user's existing Anaconda installation. The Python LICENSE supplied with that installation is copied to the binary distribution when available.

## PyInstaller

The executable bootloader is created with PyInstaller, which uses the GPL with a bootloader exception. Its provided license and exception are copied into the binary distribution. Source and license: https://github.com/pyinstaller/pyinstaller .

## WizTree

WizTree is a separate application by Antibody Software. It is neither bundled nor modified by this project. Install it separately and follow its license: https://diskanalyzer.com/license .
