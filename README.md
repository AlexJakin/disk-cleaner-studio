# Disk Cleaner Studio

> **项目来源说明**：本项目借鉴了 [iziqing/-disk-cleaner](https://github.com/iziqing/-disk-cleaner) 的设计思路与磁盘扫描、分析、备份清理流程，并在此基础上开发了可视化桌面界面。感谢原项目作者的分享。

面向 Windows 的本地磁盘分析与可恢复缓存清理工具，采用 Python + PySide6 / QML。所有扫描、规则分析、备份和历史记录都在本机完成。

## 快速开始

双击项目根目录的 **Start.cmd**。存在已打包版本时直接启动，无需安装 Python。可执行文件位于 `dist/DiskCleanerStudio/DiskCleanerStudio.exe`，移动时需保留整个 `DiskCleanerStudio` 文件夹。

首次进入可以选择“载入示例”体验界面，或导入 WizTree CSV。示例是模拟数据，不能执行清理。程序不会启动后自动扫描或删除文件。

源码运行需要 Windows 10/11 x64、Python 3.11–3.13（本次使用 Python 3.12）和项目依赖：

```powershell
.\setup.ps1
.\.venv\Scripts\python.exe run.py
```

指定 Python 路径：

```powershell
.\setup.ps1 -Python 'D:\prenstation\anaconda3\python.exe' -Dev
.\.venv\Scripts\python.exe run.py --demo
```

## 使用流程

1. **扫描或导入**：在顶部选择磁盘，也可在设置中填写具体目录。点击扫描调用本机 WizTree；导入 CSV 不需要管理员权限。
2. **空间探索**：容量概览、面积图和目录列表联动；双击目录进入下一级，支持返回上级和查看前 100 个大文件。同级目录最多展示前 500 项，避免大量对象阻塞界面。
3. **清理建议**：查看路径、命中原因、风险、影响与前置条件。候选项默认不勾选，可以加入持久化忽略名单。
4. **预览备份计划**：仅接受当前用户明确支持的缓存路径。预览后，程序执行时仍会再次检查路径、文件清单与内容。
5. **备份与清理**：先复制所有目标并逐文件 SHA-256 校验，全部成功后才开始清理。保留缓存根目录，逐项报告状态。备份失败会阻止删除。
6. **恢复与复查**：在备份页恢复；遇到同名文件会拒绝覆盖并报告冲突。清理后重新扫描查看最新占用，历史快照不会被自动改写。

## WizTree 配置

WizTree 单独安装，不随本项目分发。程序会查找 `WIZTREE_PATH`、常见安装目录，以及本机已安装的 `D:\Tools\WizTree\WizTree64.exe`，也可在设置中手动选择。

NTFS 整盘快速扫描通常需要管理员权限。程序不会自动弹出提权：可自行以管理员身份启动应用，或在管理员身份运行的 WizTree 中导出 CSV，再导入本应用。小目录通常可在普通权限下扫描。

官方资料：[WizTree 下载](https://diskanalyzer.com/download)、[CSV 导出与命令行](https://diskanalyzer.com/guide)。WizTree 免费许可适用于个人使用，商业使用请查看其许可。

## 数据与空间口径

- 配置与 SQLite 索引默认位于 `%LOCALAPPDATA%\DiskCleanerStudio`。可使用 `--data-dir PATH` 指定独立目录。
- 备份位置首次确定后固定保存到设置中。存在 D 盘时默认建议 `D:\DiskCleanerStudioBackups`，否则位于应用数据目录的 `backups` 下。
- CSV 中 `Size` 是逻辑大小，`Allocated` 是已分配空间；界面区分两者，不把建议大小承诺为真实释放量。
- 执行结果分别记录逻辑删除字节和源磁盘空闲变化；备份磁盘变化单独保存。后台进程也会改变磁盘空间，因此空闲变化是观测值，不能精确归因于本次操作。同盘备份可能导致净空闲空间减少。
- 历史记录时间优先采用 WizTree CSV 首行的导出时间，缺失时使用 CSV 文件修改时间，并另存导入时间。不会自动删除旧 CSV 或备份。CSV 可能含个人路径，分享前请检查。

## 当前范围

这是可运行的 0.1 版本。清理范围保守限定为当前用户的特定缓存；Windows 系统组件、其他用户、个人文档和应用安装目录只提供分析，不开放自动删除。不会根据 AI 输出直接执行任意路径。

执行前应关闭相关应用。第一版拒绝重解析点，备份以普通文件内容和目录结构为主，不承诺完整保留 NTFS ACL、备用数据流、EFS、硬链接关系等文件系统元数据。需要这些特性的目录请使用专门的备份工具。备份不会自动过期删除；同名文件恢复冲突需先人工处理，不会自动覆盖。

## 开发与验证

```powershell
.\setup.ps1 -Dev
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe run.py --smoke --demo --data-dir .test-data
.\build.ps1
```

`--smoke` 使用 Qt 离屏后端验证实际 QML 加载并退出。`--screenshot PATH` 可保存界面截图。打包使用 PyInstaller onedir；Qt 依赖无需额外安装。Qt 使用 Essentials 包，避免引入无关的 WebEngine。

目录结构及扩展约定见 [docs/architecture.md](docs/architecture.md)。本项目独立开发，没有修改或复制执行旧项目的清理脚本。

## 依赖许可

PySide6 / Qt 的使用与分发需遵循其 LGPLv3 / GPLv3 或商业许可；本项目打包保留动态 Qt 库及其许可资料，不将 WizTree 一起分发。依赖声明及源码链接见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。发布前应阅读 [Qt for Python 许可说明](https://doc.qt.io/qtforpython-6/licenses.html)。
