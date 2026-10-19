"""Preserve third-party metadata/notices in the onedir distribution."""
from importlib.metadata import distribution
from pathlib import Path
import shutil
import sys


root = Path(__file__).resolve().parents[1]
destination = root / "dist" / "DiskCleanerStudio" / "licenses"
destination.mkdir(parents=True, exist_ok=True)
shutil.copy2(root / "THIRD_PARTY_NOTICES.md", destination / "THIRD_PARTY_NOTICES.md")
shutil.copytree(root / "licenses", destination / "GNU", dirs_exist_ok=True)
for name in ("PySide6-Essentials", "shiboken6", "pyinstaller"):
    package = distribution(name)
    for item in package.files or []:
        leaf = item.name.casefold()
        if leaf == "metadata" or any(token in leaf for token in ("license", "copying", "notice")):
            source = Path(package.locate_file(item))
            if source.is_file() and ".dist-info" in str(item):
                target = destination / name / Path(item)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
for name in ("LICENSE_PYTHON.txt", "LICENSE.txt", "LICENSE"):
    source = Path(sys.base_prefix) / name
    if source.is_file():
        target = destination / "Python" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
print(f"Third-party notices: {destination}")
