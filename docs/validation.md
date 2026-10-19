# 0.1 本机验证记录

验证日期：2026-10-19（北京时间）。

环境：Windows x64、Python 3.12.7、PySide6 Essentials / Qt 6.8.3、WizTree 4.33。Qt 版本固定为本机已验证的 6.8.3；不随安装隐式升级。

## 已验证内容

- CSV 中英文表头、UTF-8 BOM / UTF-16 / GB18030、容量字段、目录属性、硬链接分配大小标记、缺失中间目录、重复路径和取消回滚。
- WizTree 参数数组调用、真实进程退出、非零退出码、无效输出、超时、取消以及历史文件保留。已使用安装在 `D:\Tools\WizTree` 的程序扫描人工小目录并导入结果。
- 真实 Windows 人工文件的计划、全项备份校验、清理和恢复；包含隐藏文件、单文件、空目录、字面量 `$` 文件名。
- 备份失败阻止删除，源文件变化阻止删除，计划 / manifest 篡改和路径穿越被拒绝，重解析点被拒绝，恢复冲突不覆盖，取消和部分失败统计。
- 控制器实际后台线程与 Qt 信号，示例禁执行，选择与忽略持久化，目录 / 大文件视图切换，无效配置回退，取消后不得开放执行计划。
- 实际 QML 加载、确认前不能执行、恢复确认、忙碌时关窗保护，以及页面截图检查。
- PyInstaller onedir 程序启动与示例加载，运行时无需依赖开发虚拟环境。

## 复验命令

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .test-data\validation
.\.venv\Scripts\python.exe run.py --smoke --demo --data-dir .test-data\smoke
.\build.ps1
```

最终完整测试结果：78 项通过，另有 18 个子测试通过。

## 验证范围

本轮没有运行整盘 C 盘扫描，也没有清理任何真实用户缓存。大规模扫描速度、数百万行 CSV 的资源占用，以及更多应用运行中的缓存行为仍需后续实测。备份只覆盖普通文件内容和目录结构；NTFS 特殊元数据和实时文件系统并发的限制见 README 与 `core/cleanup.py`。
