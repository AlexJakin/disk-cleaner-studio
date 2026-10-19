"""Streaming WizTree imports and deliberately narrow cleanup suggestions.

All paths in an imported CSV are *observations*, never filesystem authority.
The cleanup executor must check live paths and ownership again before use.
"""
from __future__ import annotations

import codecs
import csv
import hashlib
import json
import ntpath
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


_HEADERS = {
    "path": {"filename", "filepath", "path", "文件名称", "文件名", "路径", "名称"},
    "size": {"size", "大小", "文件大小"},
    "allocated": {"allocated", "allocatedsize", "分配", "已分配", "占用空间"},
    "attributes": {"attributes", "属性"},
    "total_bytes": {"drivecapacity", "totalspace", "capacity", "磁盘容量", "总容量", "总空间"},
    "free_bytes": {"freespace", "可用空间", "剩余空间", "空闲空间"},
    "used_bytes": {"usedspace", "已用空间", "使用空间"},
}
_PROFILE = re.compile(r"^[a-z]:\\users\\[^\\]+\\(.+)$", re.I)
_CACHE_ROOTS = {
    r"appdata\local\pip\cache": ("pip 缓存", "开发缓存", "low"),
    r"appdata\local\uv\cache": ("uv 缓存", "开发缓存", "low"),
    r"appdata\local\npm-cache": ("npm 缓存", "开发缓存", "low"),
    r"appdata\roaming\npm-cache": ("npm 缓存", "开发缓存", "low"),
    r".cache\pip": ("pip 缓存", "开发缓存", "low"),
    r".gradle\caches": ("Gradle 缓存", "开发缓存", "medium"),
    r"appdata\local\temp": ("用户临时文件", "临时文件", "medium"),
    r"appdata\local\crashdumps": ("应用崩溃转储", "崩溃转储", "medium"),
}
_BROWSER = re.compile(
    r"appdata\\local\\(?:google\\chrome|microsoft\\edge)\\user data\\"
    r"(?:default|profile [0-9]+)\\cache$", re.I
)


def _check_cancel(event):
    if event is not None and event.is_set():
        raise InterruptedError("操作已取消")


def _notify(progress, message, count=0):
    if progress is not None:
        progress(message, count)


def _normal_header(value):
    return re.sub(r"[\s_\-()（）]", "", value).casefold().lstrip("\ufeff")


def _number(value, *, allocated=False):
    text = str(value or "").strip().replace(",", "").replace(" ", "")
    if not text:
        return 0
    # WizTree prefixes the allocated size of additional hard links with 0.
    if allocated and len(text) > 1 and text.startswith("0") and text.isdigit():
        return 0
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([KMGTPE]?I?B|BYTES?|字节)?", text, re.I)
    if not match:
        raise ValueError(f"无效大小: {value!r}")
    suffix = (match.group(2) or "").upper()
    power = "KMGTPE".find(suffix[0]) + 1 if suffix and suffix[0] in "KMGTPE" else 0
    result = int(float(match.group(1)) * 1024**power) if "." in match.group(1) else int(match.group(1)) * 1024**power
    if result > 2**63 - 1:
        raise ValueError("大小超出 SQLite 整数范围")
    return result


def _windows_path(value):
    text = value.strip().strip('"').replace("/", "\\")
    drive, tail = ntpath.splitdrive(text)
    if not drive or not tail.startswith("\\"):
        raise ValueError("不是完整 Windows 路径")
    if any(part in {".", ".."} for part in tail.split("\\")):
        raise ValueError("路径含相对目录段")
    return ntpath.normpath(text)


def _key(path):
    return path.casefold()


def _parent(path):
    parent = ntpath.dirname(path)
    return "" if parent == path else parent


def _category(path):
    key = path.casefold()
    parts = key.split("\\")
    if any(p in {"windows", "program files", "program files (x86)", "programdata"} for p in parts[1:2]):
        return "系统与应用"
    profile = _PROFILE.fullmatch(key)
    if profile:
        suffix = profile.group(1)
        cache_suffix = suffix
        while cache_suffix:
            if cache_suffix in _CACHE_ROOTS:
                return _CACHE_ROOTS[cache_suffix][1]
            if _BROWSER.fullmatch(cache_suffix):
                return "浏览器缓存"
            cache_suffix = ntpath.dirname(cache_suffix)
        if suffix.split("\\")[0] in {"documents", "desktop", "downloads", "pictures", "videos", "music", "onedrive", ".ssh", ".gnupg"}:
            return "个人文件"
    return "其他"


def _cache_rule(path):
    profile = _PROFILE.fullmatch(path.casefold())
    if not profile:
        return None
    suffix = profile.group(1)
    if suffix in _CACHE_ROOTS:
        return _CACHE_ROOTS[suffix]
    if _BROWSER.fullmatch(suffix):
        return ("浏览器磁盘缓存", "浏览器缓存", "low")
    return None


def _detect_encoding(path, cancel_event=None):
    with path.open("rb") as stream:
        head = stream.read(4)
        if head.startswith(codecs.BOM_UTF16_LE) or head.startswith(codecs.BOM_UTF16_BE):
            return "utf-16"
        if head.startswith(codecs.BOM_UTF8):
            return "utf-8-sig"
        if b"\x00" in head:
            return "utf-16-le" if head[1:2] == b"\x00" else "utf-16-be"
        stream.seek(0)
        decoder = codecs.getincrementaldecoder("utf-8")("strict")
        try:
            while block := stream.read(1024 * 1024):
                _check_cancel(cancel_event)
                decoder.decode(block)
            decoder.decode(b"", final=True)
            return "utf-8-sig"
        except UnicodeDecodeError:
            return "gb18030"


class ScanRepository:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "scans.sqlite3"
        self._write_lock = threading.Lock()
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS scans (
                    scan_id TEXT PRIMARY KEY, scanned_at TEXT NOT NULL,
                    root_key TEXT NOT NULL, summary TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS entries (
                    scan_id TEXT NOT NULL, path_key TEXT NOT NULL,
                    path TEXT NOT NULL, parent_key TEXT NOT NULL,
                    name TEXT NOT NULL, size INTEGER NOT NULL,
                    allocated INTEGER NOT NULL, is_dir INTEGER NOT NULL,
                    category TEXT NOT NULL, explicit INTEGER NOT NULL,
                    attributes INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (scan_id, path_key)
                );
                CREATE INDEX IF NOT EXISTS entry_children ON entries(scan_id, parent_key);
                CREATE INDEX IF NOT EXISTS entry_files ON entries(scan_id, is_dir, allocated DESC);
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def import_csv(self, path, cancel_event=None, progress=None) -> dict:
        path = Path(path).resolve()
        _check_cancel(cancel_event)
        encoding = _detect_encoding(path, cancel_event)
        scan_id = uuid.uuid4().hex
        count, invalid, duplicates = 0, 0, 0
        root = None
        capacities = {"total_bytes": 0, "used_bytes": 0, "free_bytes": 0}
        warnings = []
        is_demo = path.name.casefold() == "demo.csv"
        exported_at = None
        _notify(progress, "正在导入 CSV", 0)
        with self._write_lock, self._connect() as db:
            try:
                with path.open("r", encoding=encoding, newline="") as stream:
                    reader = csv.reader(stream)
                    indexes = None
                    for row in reader:
                        _check_cancel(cancel_event)
                        if not row or not any(value.strip() for value in row):
                            continue
                        if indexes is None:
                            normalized = [_normal_header(value) for value in row]
                            mapped = {field: next((i for i, label in enumerate(normalized) if label in aliases), None) for field, aliases in _HEADERS.items()}
                            if mapped["path"] is not None and mapped["size"] is not None:
                                indexes = mapped
                                continue
                            comment = ",".join(row)
                            if "disk-cleaner-demo" in comment.casefold():
                                is_demo = True
                            if "wiztree" in comment.casefold():
                                stamp = re.search(r"\b(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})\b", comment)
                                if stamp:
                                    try:
                                        exported_at = datetime.strptime(stamp.group(1), "%Y/%m/%d %H:%M:%S").astimezone().isoformat(timespec="seconds")
                                    except ValueError:
                                        pass
                            self._comment_capacity(comment, capacities)
                            continue
                        if row[0].lstrip().startswith("#"):
                            self._comment_capacity(",".join(row), capacities)
                            continue
                        get = lambda name: row[indexes[name]].strip() if indexes.get(name) is not None and indexes[name] < len(row) else ""
                        try:
                            for field in capacities:
                                if get(field):
                                    capacities[field] = _number(get(field))
                            source_path = get("path")
                            item_path = _windows_path(source_path)
                            size = _number(get("size"))
                            allocated = _number(get("allocated"), allocated=True) if indexes["allocated"] is not None else size
                            attributes = int(get("attributes") or "0", 0) if get("attributes").lower().startswith("0x") else int(get("attributes") or "0")
                            is_dir = source_path.endswith(("\\", "/")) or bool(attributes & 16)
                        except (ValueError, IndexError):
                            invalid += 1
                            continue
                        if ntpath.dirname(item_path) == item_path:
                            is_dir = True
                        parent = _parent(item_path)
                        old = db.execute("SELECT explicit FROM entries WHERE scan_id=? AND path_key=?", (scan_id, _key(item_path))).fetchone()
                        if old and old[0]:
                            duplicates += 1
                        db.execute("""INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?)
                            ON CONFLICT(scan_id,path_key) DO UPDATE SET
                            size=CASE WHEN entries.explicit THEN MAX(entries.size,excluded.size) ELSE excluded.size END,
                            allocated=CASE WHEN entries.explicit THEN MAX(entries.allocated,excluded.allocated) ELSE excluded.allocated END,
                            is_dir=MAX(entries.is_dir,excluded.is_dir), explicit=1,
                            attributes=(entries.attributes | excluded.attributes), category=excluded.category
                        """, (scan_id, _key(item_path), item_path, _key(parent), ntpath.basename(item_path) or item_path, size, allocated, int(is_dir), _category(item_path), 1, attributes))
                        ancestor = parent
                        while ancestor:
                            next_parent = _parent(ancestor)
                            db.execute("INSERT OR IGNORE INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?)", (scan_id, _key(ancestor), ancestor, _key(next_parent), ntpath.basename(ancestor) or ancestor, 0, 0, 1, _category(ancestor), 0, 0))
                            ancestor = next_parent
                        observed_root = item_path if is_dir else parent
                        if root is None:
                            root = observed_root
                        else:
                            try:
                                root = ntpath.commonpath([root, observed_root])
                            except ValueError as error:
                                raise ValueError("一次导入仅支持同一驱动器的扫描数据") from error
                        count += 1
                        if count % 500 == 0:
                            _notify(progress, "正在导入 CSV", count)
                    if indexes is None:
                        raise ValueError("未找到 WizTree CSV 表头（需要 File Name/文件名称 和 Size/大小）")
                if not count or not root:
                    raise ValueError("CSV 中没有可用的完整 Windows 路径")
                _check_cancel(cancel_event)
                _notify(progress, "正在汇总目录与候选项", count)
                # Explicit directory totals already include descendants. Only synthesize missing totals.
                cursor = db.execute("SELECT path_key FROM entries WHERE scan_id=? AND explicit=0 ORDER BY LENGTH(path_key) DESC", (scan_id,))
                for item in cursor:
                    _check_cancel(cancel_event)
                    totals = db.execute("SELECT COALESCE(SUM(size),0), COALESCE(SUM(allocated),0) FROM entries WHERE scan_id=? AND parent_key=?", (scan_id, item[0])).fetchone()
                    db.execute("UPDATE entries SET size=?,allocated=? WHERE scan_id=? AND path_key=?", (*totals, scan_id, item[0]))
                root_entry = db.execute("SELECT size, allocated FROM entries WHERE scan_id=? AND path_key=?", (scan_id, _key(root))).fetchone()
                if not capacities["used_bytes"]:
                    capacities["used_bytes"] = max(0, capacities["total_bytes"] - capacities["free_bytes"]) if capacities["total_bytes"] else root_entry[1]
                if not capacities["total_bytes"]:
                    capacities["total_bytes"] = capacities["used_bytes"] + capacities["free_bytes"]
                    warnings.append("CSV 未提供完整磁盘容量；容量数值仅反映已导出的数据。")
                if capacities["total_bytes"] and not capacities["free_bytes"]:
                    capacities["free_bytes"] = max(0, capacities["total_bytes"] - capacities["used_bytes"])
                if invalid:
                    warnings.append(f"已跳过 {invalid} 行无效或不完整的数据。")
                if duplicates:
                    warnings.append(f"已合并 {duplicates} 行重复路径；目录与子项不会重复累计。")
                warnings.append("可释放空间使用 Allocated 分配大小估算；实际回收空间以执行结果为准。")
                if is_demo:
                    warnings.append("这是虚拟示例数据，禁止执行清理。")
                candidates = self._candidates(db, scan_id, is_demo, cancel_event, root)
                entry_count = db.execute("SELECT COUNT(*) FROM entries WHERE scan_id=? AND explicit=1", (scan_id,)).fetchone()[0]
                imported_at = datetime.now().astimezone().isoformat(timespec="seconds")
                scanned_at = exported_at or datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
                warnings.append("扫描时间取自 CSV 的 WizTree 导出头；该时间为导出时刻，并非扫描开始时间。" if exported_at else "扫描时间取自 CSV 文件修改时间；复制或编辑文件可能改变该时间，并非原始扫描时间的精确证明。")
                summary = dict(scan_id=scan_id, source=str(path), root=root, scanned_at=scanned_at, imported_at=imported_at, timestamp_source="csv_export_header" if exported_at else "csv_mtime", entry_count=entry_count, **capacities, candidate_bytes=sum(c["allocated"] for c in candidates if c["risk"] != "manual"), candidates=candidates, warnings=warnings, is_demo=is_demo)
                db.execute("INSERT INTO scans VALUES (?,?,?,?)", (scan_id, imported_at, _key(root), json.dumps(summary, ensure_ascii=False)))
                _check_cancel(cancel_event)
            except BaseException:
                db.rollback()
                raise
        _notify(progress, "导入完成", count)
        return summary

    @staticmethod
    def _comment_capacity(comment, capacities):
        for field, labels in {
            "total_bytes": r"DRIVECAPACITY|Total\s*(?:Space|Capacity)|Capacity|总容量|总空间|磁盘容量",
            "used_bytes": r"USEDSPACE|Used\s*Space|已用空间",
            "free_bytes": r"FREESPACE|Free\s*Space|可用空间|剩余空间|空闲空间",
        }.items():
            match = re.search(rf"(?:{labels})\s*[:=,]\s*([0-9]+(?:\.[0-9]+)?\s*(?:[KMGT]i?B|bytes?|字节)?)", comment, re.I)
            if match:
                try:
                    capacities[field] = _number(match.group(1))
                except ValueError:
                    pass

    @staticmethod
    def _candidates(db, scan_id, is_demo, cancel_event, root=""):
        candidates = []
        selected_roots = set()
        rows = db.execute("SELECT * FROM entries WHERE scan_id=? AND is_dir=1 AND allocated>0 ORDER BY LENGTH(path_key), path_key", (scan_id,))
        for row in rows:
            _check_cancel(cancel_event)
            if root and row["path_key"] != _key(root) and not row["path_key"].startswith(_key(root).rstrip("\\") + "\\"):
                continue
            rule = _cache_rule(row["path"])
            manual = row["category"] in {"系统与应用", "个人文件"}
            if not rule and not manual:
                continue
            parent = row["parent_key"]
            if any(parent == root or parent.startswith(root + "\\") for root in selected_roots):
                continue
            name, category, risk = rule if rule else (row["name"], row["category"], "manual")
            selected_roots.add(row["path_key"])
            reparse = bool(row["attributes"] & 1024)
            eligible = bool(rule) and not reparse and not is_demo
            candidates.append(dict(
                id=hashlib.sha256((scan_id + "|" + row["path_key"]).encode()).hexdigest()[:24],
                path=row["path"], name=name, category=category,
                risk="manual" if reparse else risk,
                reason="匹配已知用户缓存的精确目录" if rule else "包含系统、应用或个人数据，仅供分析",
                effect="清理后应用可能重新下载或生成缓存；首次使用可能变慢" if rule else "需要手动确认用途，不提供自动清理",
                prerequisites="先关闭相关应用；执行前复核真实路径、账号归属与备份" if rule else "使用应用自身的管理功能或人工处理",
                size=row["size"], allocated=row["allocated"], is_dir=True, cleanable=eligible,
            ))
        return sorted(candidates, key=lambda item: item["allocated"], reverse=True)

    def list_scans(self) -> list[dict]:
        with self._connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT summary FROM scans ORDER BY scanned_at DESC, rowid DESC")]

    def load_scan(self, scan_id) -> dict:
        with self._connect() as db:
            row = db.execute("SELECT summary FROM scans WHERE scan_id=?", (scan_id,)).fetchone()
            if row is None:
                raise KeyError(f"找不到扫描: {scan_id}")
            return json.loads(row[0])

    @staticmethod
    def _public_entry(row):
        return dict(path=row["path"], name=row["name"], size=row["size"], allocated=row["allocated"], is_dir=bool(row["is_dir"]), category=row["category"])

    def children(self, scan_id, path="", limit=500) -> list[dict]:
        summary = self.load_scan(scan_id)
        directory = _windows_path(path) if path else summary["root"]
        with self._connect() as db:
            return [self._public_entry(row) for row in db.execute("SELECT * FROM entries WHERE scan_id=? AND parent_key=? ORDER BY allocated DESC, is_dir DESC, path_key LIMIT ?", (scan_id, _key(directory), max(0, min(int(limit), 10000))))]

    def top_files(self, scan_id, limit=100) -> list[dict]:
        self.load_scan(scan_id)
        with self._connect() as db:
            return [self._public_entry(row) for row in db.execute("SELECT * FROM entries WHERE scan_id=? AND is_dir=0 ORDER BY size DESC, allocated DESC LIMIT ?", (scan_id, max(0, min(int(limit), 10000))))]

    def compare(self, scan_id) -> list[dict]:
        current = self.load_scan(scan_id)
        with self._connect() as db:
            previous_row = db.execute("SELECT summary FROM scans WHERE root_key=? AND rowid<(SELECT rowid FROM scans WHERE scan_id=?) ORDER BY rowid DESC LIMIT 1", (_key(current["root"]), scan_id)).fetchone()
            if previous_row is None:
                return []
            previous = json.loads(previous_row[0])
            # Union all child keys in SQL so a large directory stays bounded in Python.
            # Compare immediate children, never sum parents and descendants together.
            rows = db.execute("""
                WITH paths AS (
                    SELECT path_key FROM entries WHERE scan_id=? AND parent_key=?
                    UNION SELECT path_key FROM entries WHERE scan_id=? AND parent_key=?
                )
                SELECT COALESCE(new.path,old.path) AS path,
                    COALESCE(new.name,old.name) AS name,
                    COALESCE(old.allocated,0) AS before_bytes,
                    COALESCE(new.allocated,0) AS after_bytes,
                    old.path_key AS old_key, new.path_key AS new_key
                FROM paths
                LEFT JOIN entries old ON old.scan_id=? AND old.path_key=paths.path_key
                LEFT JOIN entries new ON new.scan_id=? AND new.path_key=paths.path_key
                ORDER BY ABS(COALESCE(new.allocated,0)-COALESCE(old.allocated,0)) DESC,
                    COALESCE(new.allocated,old.allocated,0) DESC
                LIMIT 500
            """, (previous["scan_id"], _key(current["root"]), scan_id, _key(current["root"]), previous["scan_id"], scan_id))
            result = []
            for item in rows:
                old_size, new_size = item["before_bytes"], item["after_bytes"]
                result.append(dict(path=item["path"], name=item["name"], before=old_size, after=new_size, previous=old_size, current=new_size, delta=new_size-old_size, before_bytes=old_size, after_bytes=new_size, delta_bytes=new_size-old_size, status="added" if item["old_key"] is None else "removed" if item["new_key"] is None else "changed" if old_size != new_size else "unchanged"))
            return result
