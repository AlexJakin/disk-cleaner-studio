"""Conservative, local cache backup / cleanup / restore using the standard library.

API notes
---------
Only explicitly allowed cache paths can be emptied; directory targets themselves
are retained. ``allowed_roots`` is a test/developer injection point, never a UI
option. Plans and manifests are HMAC authenticated to catch accidental changes;
this is not a security boundary against a user/process that can edit the key.
Every ordinary file (including hidden files) is copied and SHA-256 checked before
any source is removed. Restoration refuses to replace existing files.

Windows ACLs, alternate data streams, EFS, hard-link relationships, compression,
sparse allocation and all filesystem metadata are NOT backed up. This engine
backs up ordinary file contents and directory names, with best-effort timestamps.
Path/reparse checks and repeated snapshots reduce races, but cannot make a live
filesystem transactional. Close applications using a cache before cleaning it.
Free-space changes include other processes and are reported separately from
logical file bytes deleted. Same-volume backups may yield no net free space.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import threading
from datetime import datetime, timezone
from typing import Callable, Any
import uuid


_SCHEMA = 1
_CHUNK = 1024 * 1024
_MANIFEST_LIMIT = 256 * 1024 * 1024
_ID = re.compile(r"^[0-9a-f]{32}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
Progress = Callable[[str, int], None] | None


class CleanupError(ValueError):
    """An invalid or unsafe request; no cleanup is started for such a request."""


class _Cancelled(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _identity(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _inside(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((_identity(path), _identity(root))) == _identity(root)
    except ValueError:
        return False


def _is_reparse(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE)


def _safe_parts(parts: tuple[str, ...] | list[str]) -> None:
    for part in parts:
        if (part in (".", "..") or part.endswith((".", " ")) or ":" in part
                or "\\" in part or "\x00" in part or _RESERVED.match(part)):
            raise CleanupError(f"不安全的路径片段：{part!r}")


def _absolute(value: str | Path) -> Path:
    try:
        raw = os.fspath(value)
    except TypeError as exc:
        raise CleanupError("路径必须是字符串或 Path") from exc
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise CleanupError("路径必须为非空字符串")
    if raw.startswith(("\\\\", "//")):
        raise CleanupError("不支持 UNC 或设备路径")
    # Inspect raw components before pathlib normalizes dot components away.
    raw_parts = raw.replace("\\", "/").split("/")
    if any(part in (".", "..") for part in raw_parts):
        raise CleanupError("路径不能包含 . 或 ..")
    path = Path(raw)
    if not path.is_absolute():
        raise CleanupError("必须使用绝对路径")
    _safe_parts(path.parts[1:])
    return Path(os.path.abspath(path))


def _check_ancestors(path: Path) -> None:
    """Use lstat, never resolve(), so junctions cannot disappear during validation."""
    chain = list(reversed((path, *path.parents)))
    for index, component in enumerate(chain):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise CleanupError(f"无法检查路径 {component}：{exc}") from exc
        if _is_reparse(info):
            raise CleanupError(f"拒绝符号链接或重解析点：{component}")
        if index < len(chain) - 1 and not stat.S_ISDIR(info.st_mode):
            raise CleanupError(f"路径祖先不是目录：{component}")


def _relative(value: Any, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise CleanupError("备份相对路径无效")
    if value == "" and allow_empty:
        return value
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or "\\" in value or ":" in value
            or value != path.as_posix() or any(p in ("", ".", "..") for p in value.split("/"))):
        raise CleanupError("备份相对路径含有绝对路径或路径穿越")
    _safe_parts(path.parts)
    return value


def _cancelled(event: Any) -> bool:
    return bool(event is not None and event.is_set())


def _check_cancel(event: Any) -> None:
    if _cancelled(event):
        raise _Cancelled("操作已取消")


def _notify(progress: Progress, message: str, count: int) -> None:
    if progress:
        try:
            progress(message, count)
        except Exception:
            # A UI notification must not bypass the backup gate.
            pass


def _stat_token(info: os.stat_result) -> tuple[int, ...]:
    # Python 3.12+ on Windows can report different ctime semantics/precision for
    # path-based stat and fstat. Birth time is the consistent identity component.
    changed = getattr(info, "st_birthtime_ns", info.st_ctime_ns) if os.name == "nt" else info.st_ctime_ns
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            changed, info.st_mode)


def _hash_file(path: Path, cancel_event: Any = None) -> tuple[str, os.stat_result]:
    _check_cancel(cancel_event)
    _check_ancestors(path)
    before = path.lstat()
    if _is_reparse(before) or not stat.S_ISREG(before.st_mode):
        raise CleanupError(f"拒绝非常规文件：{path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if _stat_token(before) != _stat_token(opened):
            raise CleanupError(f"读取期间源文件发生变化：{path}")
        digest = hashlib.sha256()
        while chunk := stream.read(_CHUNK):
            _check_cancel(cancel_event)
            digest.update(chunk)
        after_open = os.fstat(stream.fileno())
    _check_ancestors(path)
    after = path.lstat()
    if _stat_token(before) != _stat_token(after_open) or _stat_token(before) != _stat_token(after):
        raise CleanupError(f"读取期间源文件发生变化：{path}")
    return digest.hexdigest(), after


def _snapshot(path: Path, cancel_event: Any = None, progress: Progress = None,
              progress_counter: list[int] | None = None) -> dict:
    """An inventory includes empty directories and content hashes of every file."""
    _check_ancestors(path)
    entries: list[dict] = []
    counter = progress_counter if progress_counter is not None else [0]

    def visit(current: Path, rel: str) -> None:
        _check_cancel(cancel_event)
        info = current.lstat()
        if _is_reparse(info):
            raise CleanupError(f"目标含有符号链接或重解析点：{current}")
        base = {"rel": rel, "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns,
                "mode": info.st_mode, "ino": info.st_ino, "dev": info.st_dev}
        if stat.S_ISDIR(info.st_mode):
            base.update(kind="directory", size=0)
            entries.append(base)
            # scandir does not exclude hidden/system files.
            with os.scandir(current) as iterator:
                children = sorted(iterator, key=lambda item: item.name.casefold())
            for child in children:
                _safe_parts([child.name])
                child_rel = child.name if not rel else f"{rel}/{child.name}"
                visit(current / child.name, child_rel)
            after = current.lstat()
            if _stat_token(info) != _stat_token(after):
                raise CleanupError(f"扫描期间目录发生变化：{current}")
        elif stat.S_ISREG(info.st_mode):
            digest, checked = _hash_file(current, cancel_event)
            if _stat_token(info) != _stat_token(checked):
                raise CleanupError(f"扫描期间文件发生变化：{current}")
            base.update(kind="file", size=info.st_size, sha256=digest)
            entries.append(base)
            counter[0] += 1
            _notify(progress, f"已校验源文件：{current.name}", counter[0])
        else:
            raise CleanupError(f"目标含有不支持的文件类型：{current}")

    visit(path, "")
    entries.sort(key=lambda entry: entry["rel"])
    return {"kind": entries[0]["kind"], "entries": entries,
            "size": sum(e["size"] for e in entries if e["kind"] == "file"),
            "file_count": sum(e["kind"] == "file" for e in entries),
            "fingerprint": hashlib.sha256(_canonical(entries)).hexdigest()}


def _content_inventory(snapshot: dict) -> list[dict]:
    return [{key: entry[key] for key in ("rel", "kind", "size", "sha256") if key in entry}
            for entry in snapshot["entries"]]


class CleanupService:
    """A per-process serial service. Invalid/tampered input raises CleanupError.

    Runtime copy/delete failures return status ``failed``/``partial`` and per-item
    errors. Cancellation returns ``cancelled``; completed deletions remain counted
    and their verified backup remains available. ``progress(message, count)`` uses
    a monotonically increasing ordinary-file count within each phase.
    """

    def __init__(self, backup_root: Path, allowed_roots: list[Path] | None = None):
        self.backup_root = _absolute(backup_root)
        if self.backup_root == Path(self.backup_root.anchor):
            raise CleanupError("备份目录不能是盘符根目录")
        _check_ancestors(self.backup_root)
        roots = allowed_roots if allowed_roots is not None else self._default_roots()
        self.allowed_roots = tuple(_absolute(root) for root in roots)
        self._key: bytes | None = None
        self._lock = threading.Lock()

    @staticmethod
    def _default_roots() -> list[Path]:
        roots: list[Path] = []
        local = os.environ.get("LOCALAPPDATA")
        profile = os.environ.get("USERPROFILE")
        if local:
            base = _absolute(local)
            roots.extend(base / part for part in ("Temp", "pip/Cache", "uv/cache", "npm-cache", "CrashDumps"))
            for browser in ("Google/Chrome/User Data", "Microsoft/Edge/User Data"):
                profiles = base / browser
                try:
                    _check_ancestors(profiles)
                    if profiles.is_dir():
                        with os.scandir(profiles) as iterator:
                            for entry in iterator:
                                if (re.fullmatch(r"Default|Profile [0-9]+", entry.name)
                                        and entry.is_dir(follow_symlinks=False)
                                        and not _is_reparse(entry.stat(follow_symlinks=False))):
                                    roots.append(profiles / entry.name / "Cache")
                except (OSError, CleanupError):
                    pass
        if profile:
            base = _absolute(profile)
            roots.extend((base / ".cache/pip", base / ".gradle/caches"))
        roaming = os.environ.get("APPDATA")
        if roaming:
            roots.append(_absolute(roaming) / "npm-cache")
        return roots

    def _target(self, value: str | Path, *, must_exist: bool = True) -> Path:
        path = _absolute(value)
        if path == Path(path.anchor):
            raise CleanupError("禁止清理盘符根目录")
        for variable in ("USERPROFILE", "HOME"):
            raw = os.environ.get(variable)
            if raw and _identity(path) == _identity(_absolute(raw)):
                raise CleanupError("禁止清理用户根目录")
        for raw in (os.environ.get("WINDIR"), os.environ.get("SYSTEMROOT")):
            if raw and _inside(path, _absolute(raw)):
                raise CleanupError("禁止清理 Windows 系统目录")
        if not any(_inside(path, root) for root in self.allowed_roots):
            raise CleanupError(f"路径不在允许的缓存目录内：{path}")
        if _inside(self.backup_root, path) or _inside(path, self.backup_root):
            raise CleanupError("清理目标与备份目录不能互相包含")
        _check_ancestors(path)
        if must_exist:
            try:
                info = path.lstat()
            except FileNotFoundError as exc:
                raise CleanupError(f"目标已不存在：{path}") from exc
            if not stat.S_ISREG(info.st_mode) and not stat.S_ISDIR(info.st_mode):
                raise CleanupError("目标必须是普通文件或目录")
        return path

    def inspect_target(self, path: str | Path) -> dict:
        """Read-only eligibility hint; preview/execution still validate the tree.

        This deliberately performs no hashing or recursive inspection, so it is
        suitable for disabling ineligible scan-result rows in the interface.
        """
        try:
            self._target(path, must_exist=True)
            return {"eligible": True, "reason": "允许的当前用户缓存路径；预览和执行时将复核全部内容。"}
        except Exception as exc:
            return {"eligible": False, "reason": str(exc)}

    def _storage(self, *, create: bool = True) -> bytes:
        _check_ancestors(self.backup_root)
        if create:
            self.backup_root.mkdir(parents=True, exist_ok=True)
        _check_ancestors(self.backup_root)
        if not self.backup_root.is_dir():
            raise CleanupError("备份路径不是目录")
        key_path = self.backup_root / ".integrity-key"
        _check_ancestors(key_path)
        if self._key is None:
            if not create:
                try:
                    info = key_path.lstat()
                except FileNotFoundError as exc:
                    raise CleanupError("备份完整性密钥不存在") from exc
                if not stat.S_ISREG(info.st_mode) or info.st_size != 32:
                    raise CleanupError("备份完整性密钥无效")
                self._key = key_path.read_bytes()
                return self._key
            try:
                fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                info = key_path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_size != 32:
                    raise CleanupError("备份完整性密钥无效")
                self._key = key_path.read_bytes()
            else:
                self._key = os.urandom(32)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(self._key)
                    stream.flush()
                    os.fsync(stream.fileno())
        if len(self._key) != 32:
            raise CleanupError("备份完整性密钥无效")
        return self._key

    def _sign(self, value: dict) -> dict:
        payload = {key: val for key, val in value.items() if key != "signature"}
        result = dict(payload)
        result["signature"] = hmac.new(self._storage(), _canonical(payload), hashlib.sha256).hexdigest()
        return result

    def _authenticated(self, value: dict) -> dict:
        if not isinstance(value, dict) or not isinstance(value.get("signature"), str):
            raise CleanupError("计划或备份清单缺少完整性签名")
        try:
            # Detach nested data so a caller cannot change a live plan after validation.
            detached = json.loads(_canonical(value))
            payload = {key: val for key, val in detached.items() if key != "signature"}
            expected = hmac.new(self._storage(create=False), _canonical(payload), hashlib.sha256).hexdigest()
        except (TypeError, ValueError) as exc:
            raise CleanupError("计划或备份清单格式无效") from exc
        if not hmac.compare_digest(expected, detached["signature"]):
            raise CleanupError("计划或备份清单已被修改，拒绝执行")
        return payload

    def _free(self, path: Path | None = None) -> int:
        candidate = path or self.backup_root
        while not candidate.exists() and candidate != candidate.parent:
            candidate = candidate.parent
        _check_ancestors(candidate)
        return shutil.disk_usage(candidate).free

    @staticmethod
    def _volume(path: Path) -> int:
        candidate = path
        while not candidate.exists() and candidate != candidate.parent:
            candidate = candidate.parent
        return candidate.stat().st_dev

    def create_plan(self, paths: list[str], cancel_event: Any = None, progress: Progress = None) -> dict:
        if not isinstance(paths, list) or not paths:
            raise CleanupError("请选择至少一个允许的缓存目标")
        if len(paths) > 1000:
            raise CleanupError("单个计划最多包含 1000 个目标")
        candidates = sorted({self._target(path) for path in paths}, key=lambda p: (len(p.parts), _identity(p)))
        selected: list[Path] = []
        for path in candidates:
            if not any(_inside(path, parent) for parent in selected):
                selected.append(path)
        items: list[dict] = []
        counter = [0]
        for path in selected:
            try:
                _check_cancel(cancel_event)
                snap = _snapshot(path, cancel_event, progress, counter)
            except _Cancelled as exc:
                raise CleanupError("预览已取消") from exc
            except OSError as exc:
                raise CleanupError(f"无法完整读取目标 {path}：{exc}") from exc
            items.append({"path": str(path), "name": path.name, **{
                key: snap[key] for key in ("kind", "size", "file_count", "fingerprint")}})
        estimated = sum(item["size"] for item in items)
        same_volume = any(self._volume(Path(item["path"])) == self._volume(self.backup_root) for item in items)
        warnings = ["只备份普通文件内容和目录名称；不保留 Windows ACL、备用数据流等所有元数据。请先关闭使用这些缓存的应用。"]
        if same_volume:
            warnings.append("备份与至少一个清理目标在同一磁盘：备份会占用空间，清理后可能没有净释放空间。")
        plan = {"schema_version": _SCHEMA, "id": uuid.uuid4().hex, "created_at": _now(),
                "backup_root": str(self.backup_root), "items": items, "estimated_bytes": estimated,
                "required_backup_bytes": estimated + max(_CHUNK, estimated // 100),
                "available_bytes": self._free(), "same_volume": same_volume, "warnings": warnings}
        return self._sign(plan)

    def _validate_plan(self, plan: dict) -> dict:
        payload = self._authenticated(plan)
        if (payload.get("schema_version") != _SCHEMA or not _ID.fullmatch(str(payload.get("id", "")))
                or payload.get("backup_root") != str(self.backup_root)):
            raise CleanupError("计划版本、标识或备份目录无效")
        items = payload.get("items")
        if not isinstance(items, list) or not items or len(items) > 1000:
            raise CleanupError("计划目标列表无效")
        paths: list[Path] = []
        total = 0
        for item in items:
            if not isinstance(item, dict):
                raise CleanupError("计划目标格式无效")
            path = self._target(item.get("path", ""))
            if str(path) != item["path"] or item.get("name") != path.name:
                raise CleanupError("计划目标路径无效")
            if any(_inside(path, previous) or _inside(previous, path) for previous in paths):
                raise CleanupError("计划包含重复或互相包含的目标")
            paths.append(path)
            if (item.get("kind") not in ("file", "directory") or type(item.get("size")) is not int
                    or item["size"] < 0 or type(item.get("file_count")) is not int
                    or item["file_count"] < 0 or not _HASH.fullmatch(str(item.get("fingerprint", "")))):
                raise CleanupError("计划目标统计无效")
            total += item["size"]
        if payload.get("estimated_bytes") != total or payload.get("required_backup_bytes") != total + max(_CHUNK, total // 100):
            raise CleanupError("计划大小统计无效")
        return payload

    @staticmethod
    def _matches(item: dict, snapshot: dict) -> None:
        if any(item[key] != snapshot[key] for key in ("kind", "size", "file_count", "fingerprint")):
            raise CleanupError(f"源内容或元数据已变化，请重新生成预览：{item['path']}")

    def _write_manifest(self, folder: Path, manifest: dict) -> None:
        _check_ancestors(folder)
        signed = self._sign(manifest)
        encoded = _canonical(signed)
        if len(encoded) > _MANIFEST_LIMIT:
            raise CleanupError("备份清单过大，拒绝执行；请按较小缓存目录分批处理")
        target = folder / "manifest.json"
        _check_ancestors(target)
        temporary = folder / f".manifest-{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            _check_ancestors(folder)
            _check_ancestors(target)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _entry_path(root: Path, entry: dict) -> Path:
        rel = _relative(entry["rel"], allow_empty=True)
        return root.joinpath(*PurePosixPath(rel).parts) if rel else root

    def _copy_file(self, source: Path, destination: Path, expected: dict, cancel_event: Any = None) -> None:
        _check_cancel(cancel_event)
        _check_ancestors(source)
        _check_ancestors(destination)
        digest, info = _hash_file(source, cancel_event)
        if info.st_size != expected["size"] or digest != expected["sha256"]:
            raise CleanupError(f"复制前文件内容已变化：{source}")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        if destination.exists():
            raise CleanupError(f"目标已存在，拒绝覆盖：{destination}")
        temporary = destination.parent / f".dcs-{uuid.uuid4().hex}.tmp"
        owned: tuple[int, int] | None = None
        try:
            fd = os.open(source, flags)
            with os.fdopen(fd, "rb") as incoming:
                before = os.fstat(incoming.fileno())
                if _stat_token(before) != _stat_token(info):
                    raise CleanupError(f"复制前源文件已变化：{source}")
                _check_ancestors(temporary)
                with temporary.open("xb") as outgoing:
                    created = os.fstat(outgoing.fileno())
                    owned = (created.st_dev, created.st_ino)
                    while chunk := incoming.read(_CHUNK):
                        _check_cancel(cancel_event)
                        outgoing.write(chunk)
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                after = os.fstat(incoming.fileno())
            _check_ancestors(source)
            if _stat_token(before) != _stat_token(after) or _stat_token(before) != _stat_token(source.lstat()):
                raise CleanupError(f"复制期间源文件已变化：{source}")
            actual, copied = _hash_file(temporary, cancel_event)
            if copied.st_size != expected["size"] or actual != expected["sha256"]:
                raise CleanupError(f"备份文件校验失败：{destination}")
            try:
                os.utime(temporary, ns=(info.st_atime_ns, info.st_mtime_ns), follow_symlinks=False)
            except (OSError, NotImplementedError):
                pass
            _check_cancel(cancel_event)
            _check_ancestors(destination)
            _check_ancestors(temporary)
            if os.name == "nt":
                # Windows rename refuses an existing destination (unlike POSIX rename).
                os.rename(temporary, destination)
            else:
                # link() atomically publishes without replacing an existing name.
                os.link(temporary, destination, follow_symlinks=False)
                temporary.unlink()
        finally:
            if owned is not None:
                try:
                    _check_ancestors(temporary)
                    leftover = temporary.lstat()
                    if (leftover.st_dev, leftover.st_ino) == owned and stat.S_ISREG(leftover.st_mode):
                        temporary.unlink()
                except FileNotFoundError:
                    pass

    def _copy_tree(self, source: Path, destination: Path, snapshot: dict,
                   cancel_event: Any, progress: Progress, counter: list[int]) -> None:
        directories = [e for e in snapshot["entries"] if e["kind"] == "directory"]
        for entry in sorted(directories, key=lambda e: len(PurePosixPath(e["rel"]).parts)):
            _check_cancel(cancel_event)
            target = self._entry_path(destination, entry)
            _check_ancestors(target)
            target.mkdir()
            _check_ancestors(target)
        for entry in snapshot["entries"]:
            if entry["kind"] == "file":
                self._copy_file(self._entry_path(source, entry), self._entry_path(destination, entry), entry, cancel_event)
                counter[0] += 1
                _notify(progress, f"已校验备份：{self._entry_path(source, entry).name}", counter[0])
        actual = _snapshot(destination, cancel_event)
        if _content_inventory(actual) != _content_inventory(snapshot):
            raise CleanupError(f"备份完整性校验失败：{source}")

    def _delete_item(self, path: Path, snapshot: dict, result: dict,
                     cancel_event: Any, progress: Progress, counter: list[int]) -> None:
        for entry in snapshot["entries"]:
            if entry["kind"] != "file":
                continue
            _check_cancel(cancel_event)
            current = self._entry_path(path, entry)
            self._target(current)
            digest, info = _hash_file(current, cancel_event)
            if (digest != entry["sha256"] or info.st_size != entry["size"]
                    or info.st_mtime_ns != entry["mtime_ns"] or info.st_ino != entry["ino"]):
                raise CleanupError(f"删除前源文件已变化：{current}")
            _check_cancel(cancel_event)
            _check_ancestors(current)
            if _stat_token(info) != _stat_token(current.lstat()):
                raise CleanupError(f"删除前源文件已变化：{current}")
            current.unlink()
            result["deleted_bytes"] += entry["size"]
            result["files_deleted"] += 1
            counter[0] += 1
            _notify(progress, f"已清理：{current.name}", counter[0])
        directories = [e for e in snapshot["entries"] if e["kind"] == "directory" and e["rel"]]
        for entry in sorted(directories, key=lambda e: len(PurePosixPath(e["rel"]).parts), reverse=True):
            _check_cancel(cancel_event)
            current = self._entry_path(path, entry)
            self._target(current)
            if not stat.S_ISDIR(current.lstat().st_mode):
                raise CleanupError(f"目录类型已变化：{current}")
            current.rmdir()  # Refuses unexpected new files instead of recursive deletion.
        if snapshot["kind"] == "directory":
            self._target(path)
            with os.scandir(path) as iterator:
                if next(iterator, None) is not None:
                    raise CleanupError(f"清理期间出现新文件，已保留：{path}")

    def execute_plan(self, plan: dict, cancel_event: Any = None, progress: Progress = None) -> dict:
        if not self._lock.acquire(blocking=False):
            raise CleanupError("另一个备份、清理或恢复操作正在运行")
        try:
            return self._execute(plan, cancel_event, progress)
        finally:
            self._lock.release()

    def _execute(self, plan: dict, cancel_event: Any, progress: Progress) -> dict:
        payload = self._validate_plan(plan)
        source_volumes: list[dict] = []
        seen_volumes: set[int] = set()
        for item in payload["items"]:
            path = Path(item["path"])
            volume = self._volume(path)
            if volume not in seen_volumes:
                seen_volumes.add(volume)
                source_volumes.append({"volume": str(volume), "path": str(path),
                                       "free_before_bytes": self._free(path),
                                       "free_after_bytes": None, "free_space_delta_bytes": None})
        result = {"operation": "cleanup", "backup_id": None, "backup_path": None, "status": "failed",
                  "items": [{"path": item["path"], "status": "pending", "backup_status": "pending",
                             "deleted_bytes": 0, "files_deleted": 0, "error": None} for item in payload["items"]],
                  "logical_deleted_bytes": 0,
                  "free_before_bytes": sum(v["free_before_bytes"] for v in source_volumes), "free_after_bytes": None,
                  "free_space_delta_bytes": None, "source_volumes": source_volumes,
                  "backup_free_before_bytes": self._free(), "backup_free_after_bytes": None,
                  "backup_free_space_delta_bytes": None, "backup_complete": False, "errors": []}
        manifest: dict | None = None
        folder: Path | None = None
        current_index: int | None = None
        phase = "validation"
        try:
            _check_cancel(cancel_event)
            snapshots: list[dict] = []
            for item in payload["items"]:
                _check_cancel(cancel_event)
                self._target(item["path"])
                snap = _snapshot(Path(item["path"]), cancel_event)
                self._matches(item, snap)
                snapshots.append(snap)
            if self._free() < payload["required_backup_bytes"]:
                raise CleanupError("备份磁盘可用空间不足；尚未删除任何源文件")
            backup_id = uuid.uuid4().hex
            folder = self.backup_root / backup_id
            _check_ancestors(folder)
            folder.mkdir()
            (folder / "data").mkdir()
            result.update(backup_id=backup_id, backup_path=str(folder))
            manifest = {"schema_version": _SCHEMA, "backup_id": backup_id, "created_at": _now(),
                        "backup_root": str(self.backup_root), "plan_id": payload["id"], "status": "backing_up",
                        "backup_complete": False, "estimated_bytes": payload["estimated_bytes"],
                        "restore_status": None, "items": []}
            for index, (item, snap) in enumerate(zip(payload["items"], snapshots)):
                manifest["items"].append({**item, "entries": snap["entries"],
                                          "backup_rel": f"data/{index:04d}/payload", "backup_status": "pending",
                                          "status": "pending", "deleted_bytes": 0, "files_deleted": 0, "error": None})
            self._write_manifest(folder, manifest)
            phase = "backup"
            counter = [0]
            for index, (item, snap) in enumerate(zip(payload["items"], snapshots)):
                current_index = index
                _check_cancel(cancel_event)
                self._target(item["path"])
                self._matches(item, _snapshot(Path(item["path"]), cancel_event))
                relative = manifest["items"][index]["backup_rel"]
                destination = folder.joinpath(*PurePosixPath(relative).parts)
                _check_ancestors(destination.parent)
                destination.parent.mkdir()
                manifest["items"][index]["backup_status"] = "copying"
                self._write_manifest(folder, manifest)
                self._copy_tree(Path(item["path"]), destination, snap, cancel_event, progress, counter)
                result["items"][index]["backup_status"] = "verified"
                manifest["items"][index]["backup_status"] = "verified"
                self._write_manifest(folder, manifest)
            # Global gate: every approved source is checked after ALL copies succeed.
            phase = "source_recheck"
            for index, item in enumerate(manifest["items"]):
                current_index = index
                backup_source = folder.joinpath(*PurePosixPath(item["backup_rel"]).parts)
                if _content_inventory(_snapshot(backup_source, cancel_event)) != _content_inventory({"entries": item["entries"]}):
                    raise CleanupError(f"全部备份复核时内容校验失败：{item['path']}")
            for index, item in enumerate(payload["items"]):
                current_index = index
                _check_cancel(cancel_event)
                self._target(item["path"])
                self._matches(item, _snapshot(Path(item["path"]), cancel_event))
            manifest["backup_complete"] = result["backup_complete"] = True
            manifest["status"] = "backed_up"
            self._write_manifest(folder, manifest)
            phase = "cleanup"
            counter = [0]
            for index, (item, snap) in enumerate(zip(payload["items"], snapshots)):
                current_index = index
                _check_cancel(cancel_event)
                self._target(item["path"])
                self._matches(item, _snapshot(Path(item["path"]), cancel_event))
                result["items"][index]["status"] = "cleaning"
                self._delete_item(Path(item["path"]), snap, result["items"][index], cancel_event, progress, counter)
                result["items"][index]["status"] = "complete"
                manifest["items"][index].update(result["items"][index])
                self._write_manifest(folder, manifest)
            result["status"] = "complete"
        except _Cancelled as exc:
            result["status"] = "cancelled"
            result["errors"].append(str(exc))
            if current_index is not None:
                affected = result["items"][current_index]
                if affected["status"] != "complete":
                    affected["status"] = "cancelled"
                    affected["error"] = str(exc)
                    if phase == "backup" and affected["backup_status"] != "verified":
                        affected["backup_status"] = "cancelled"
        except Exception as exc:
            result["errors"].append(f"{phase}：{exc}")
            result["status"] = "partial" if any(i["files_deleted"] for i in result["items"]) else "failed"
            if current_index is not None:
                affected = result["items"][current_index]
                if affected["status"] != "complete":
                    affected["status"] = "partial" if affected["files_deleted"] else "failed"
                    affected["error"] = str(exc)
                    if phase == "backup":
                        affected["backup_status"] = "failed"
        finally:
            for item in result["items"]:
                if item["status"] == "pending":
                    item["status"] = "skipped"
            result["logical_deleted_bytes"] = sum(i["deleted_bytes"] for i in result["items"])
            try:
                for volume in source_volumes:
                    volume["free_after_bytes"] = self._free(Path(volume["path"]))
                    volume["free_space_delta_bytes"] = volume["free_after_bytes"] - volume["free_before_bytes"]
                result["free_after_bytes"] = sum(v["free_after_bytes"] for v in source_volumes)
                result["free_space_delta_bytes"] = result["free_after_bytes"] - result["free_before_bytes"]
                result["backup_free_after_bytes"] = self._free()
                result["backup_free_space_delta_bytes"] = result["backup_free_after_bytes"] - result["backup_free_before_bytes"]
            except (OSError, CleanupError) as exc:
                result["errors"].append(f"读取可用空间失败：{exc}")
            if manifest is not None and folder is not None:
                manifest["status"] = result["status"]
                manifest["completed_at"] = _now()
                manifest["logical_deleted_bytes"] = result["logical_deleted_bytes"]
                manifest["errors"] = result["errors"]
                for saved, current in zip(manifest["items"], result["items"]):
                    saved.update(current)
                try:
                    self._write_manifest(folder, manifest)
                except Exception as exc:
                    result["errors"].append(f"写入最终备份状态失败：{exc}")
                    if result["status"] == "complete":
                        result["status"] = "partial"
        return result

    def _read_manifest(self, backup_id: str) -> tuple[Path, dict]:
        if not isinstance(backup_id, str) or not _ID.fullmatch(backup_id):
            raise CleanupError("备份标识无效")
        folder = self.backup_root / backup_id
        target = folder / "manifest.json"
        _check_ancestors(target)
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MANIFEST_LIMIT:
            raise CleanupError("备份清单文件无效或过大")
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CleanupError(f"无法读取备份清单：{exc}") from exc
        manifest = self._authenticated(raw)
        if (manifest.get("schema_version") != _SCHEMA or manifest.get("backup_id") != backup_id
                or manifest.get("backup_root") != str(self.backup_root)):
            raise CleanupError("备份清单的版本、标识或原始备份根目录无效")
        items = manifest.get("items")
        if not isinstance(items, list) or not items or len(items) > 1000:
            raise CleanupError("备份目标列表无效")
        originals: list[Path] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise CleanupError("备份目标格式无效")
            original = self._target(item.get("path", ""), must_exist=False)
            if str(original) != item.get("path") or item.get("name") != original.name:
                raise CleanupError("备份原始路径无效")
            if any(_inside(original, prev) or _inside(prev, original) for prev in originals):
                raise CleanupError("备份原始目标重复或互相包含")
            originals.append(original)
            if item.get("backup_rel") != f"data/{index:04d}/payload":
                raise CleanupError("备份存储路径无效")
            _relative(item["backup_rel"])
            entries = item.get("entries")
            if not isinstance(entries, list) or not entries:
                raise CleanupError("备份文件清单为空")
            seen: set[str] = set()
            known_dirs: set[str] = set()
            total = count = 0
            for entry in entries:
                if not isinstance(entry, dict):
                    raise CleanupError("备份文件条目无效")
                rel = _relative(entry.get("rel"), allow_empty=True)
                identity = os.path.normcase(rel)
                if identity in seen:
                    raise CleanupError("备份文件条目重复")
                seen.add(identity)
                if entry.get("kind") not in ("file", "directory") or type(entry.get("size")) is not int or entry["size"] < 0:
                    raise CleanupError("备份文件类型或大小无效")
                if entry["kind"] == "directory":
                    if entry["size"] != 0:
                        raise CleanupError("备份目录大小无效")
                    known_dirs.add(rel)
                else:
                    if not _HASH.fullmatch(str(entry.get("sha256", ""))):
                        raise CleanupError("备份文件校验值无效")
                    total += entry["size"]
                    count += 1
            if entries[0].get("rel") != "" or entries[0].get("kind") != item.get("kind"):
                raise CleanupError("备份根条目无效")
            for entry in entries:
                if entry["rel"]:
                    parent = PurePosixPath(entry["rel"]).parent.as_posix()
                    if ("" if parent == "." else parent) not in known_dirs:
                        raise CleanupError("备份清单缺少父目录")
            if (item.get("kind") == "file" and len(entries) != 1) or item.get("size") != total or item.get("file_count") != count:
                raise CleanupError("备份大小或数量无效")
            if hashlib.sha256(_canonical(entries)).hexdigest() != item.get("fingerprint"):
                raise CleanupError("备份源快照指纹无效")
        if sum(item["size"] for item in items) != manifest.get("estimated_bytes"):
            raise CleanupError("备份总大小无效")
        return folder, manifest

    def list_backups(self) -> list[dict]:
        if not self.backup_root.exists():
            return []
        _check_ancestors(self.backup_root)
        result: list[dict] = []
        for folder in self.backup_root.iterdir():
            if not _ID.fullmatch(folder.name):
                continue
            try:
                _, manifest = self._read_manifest(folder.name)
                result.append({"backup_id": folder.name, "id": folder.name,
                               "created_at": manifest["created_at"], "status": manifest["status"],
                               "backup_complete": manifest.get("backup_complete", False),
                               "estimated_bytes": manifest["estimated_bytes"], "item_count": len(manifest["items"]),
                               "backup_path": str(folder), "restore_status": manifest.get("restore_status"),
                               "logical_deleted_bytes": manifest.get("logical_deleted_bytes", 0)})
            except (OSError, CleanupError, KeyError, TypeError) as exc:
                result.append({"backup_id": folder.name, "id": folder.name, "created_at": "",
                               "status": "invalid", "backup_complete": False, "estimated_bytes": 0,
                               "item_count": 0, "backup_path": str(folder), "restore_status": None, "error": str(exc)})
        return sorted(result, key=lambda item: item["created_at"], reverse=True)

    def _restore_preflight(self, folder: Path, manifest: dict, cancel_event: Any) -> None:
        if not manifest.get("backup_complete") or any(i.get("backup_status") != "verified" for i in manifest["items"]):
            raise CleanupError("备份未全部通过校验，不能作为完整恢复源")
        for item in manifest["items"]:
            _check_cancel(cancel_event)
            source = folder.joinpath(*PurePosixPath(item["backup_rel"]).parts)
            expected = {"entries": item["entries"]}
            if _content_inventory(_snapshot(source, cancel_event)) != _content_inventory(expected):
                raise CleanupError(f"备份内容校验失败：{item['name']}")
            original = self._target(item["path"], must_exist=False)
            for entry in item["entries"]:
                destination = self._entry_path(original, entry)
                self._target(destination, must_exist=False)
                try:
                    info = destination.lstat()
                except FileNotFoundError:
                    continue
                if entry["kind"] == "file" or not stat.S_ISDIR(info.st_mode):
                    raise CleanupError(f"恢复冲突：目标已存在，拒绝覆盖：{destination}")

    def restore_backup(self, backup_id: str, cancel_event: Any = None, progress: Progress = None) -> dict:
        if not self._lock.acquire(blocking=False):
            raise CleanupError("另一个备份、清理或恢复操作正在运行")
        try:
            return self._restore(backup_id, cancel_event, progress)
        finally:
            self._lock.release()

    def _restore(self, backup_id: str, cancel_event: Any, progress: Progress) -> dict:
        folder, manifest = self._read_manifest(backup_id)
        result = {"operation": "restore", "backup_id": backup_id, "status": "failed", "restored_bytes": 0,
                  "items": [{"path": i["path"], "status": "pending", "restored_bytes": 0,
                             "files_restored": 0, "error": None} for i in manifest["items"]], "errors": []}
        current_index: int | None = None
        try:
            _check_cancel(cancel_event)
            self._restore_preflight(folder, manifest, cancel_event)
            # Group source bytes by destination filesystem; each needs its own capacity.
            volumes: dict[int, tuple[Path, int]] = {}
            for item in manifest["items"]:
                original = Path(item["path"])
                volume = self._volume(original)
                previous = volumes.get(volume, (original, 0))
                volumes[volume] = (original, previous[1] + item["size"])
            for original, size in volumes.values():
                if self._free(original) < size + max(_CHUNK, size // 100):
                    raise CleanupError("恢复目标磁盘可用空间不足")
            counter = 0
            for index, item in enumerate(manifest["items"]):
                current_index = index
                _check_cancel(cancel_event)
                original = self._target(item["path"], must_exist=False)
                source = folder.joinpath(*PurePosixPath(item["backup_rel"]).parts)
                directories = [e for e in item["entries"] if e["kind"] == "directory"]
                for entry in sorted(directories, key=lambda e: len(PurePosixPath(e["rel"]).parts)):
                    _check_cancel(cancel_event)
                    destination = self._entry_path(original, entry)
                    self._target(destination, must_exist=False)
                    # Only original target ancestors may be missing for a single-file restore.
                    destination.mkdir(parents=False, exist_ok=True)
                    self._target(destination)
                for entry in item["entries"]:
                    if entry["kind"] != "file":
                        continue
                    _check_cancel(cancel_event)
                    destination = self._entry_path(original, entry)
                    self._target(destination, must_exist=False)
                    existed = destination.exists()
                    try:
                        self._copy_file(self._entry_path(source, entry), destination, entry, cancel_event)
                    except Exception:
                        # Exclusive creation means we own a new incomplete file only if
                        # it was absent before and was not concurrently substituted.
                        # Leave it for inspection rather than risking deletion of user data.
                        if not existed and destination.exists():
                            result["items"][index]["incomplete_path"] = str(destination)
                        raise
                    result["items"][index]["restored_bytes"] += entry["size"]
                    result["items"][index]["files_restored"] += 1
                    counter += 1
                    _notify(progress, f"已恢复：{destination.name}", counter)
                result["items"][index]["status"] = "complete"
            result["status"] = "complete"
        except _Cancelled as exc:
            result["status"] = "cancelled"
            result["errors"].append(str(exc))
            if current_index is not None and result["items"][current_index]["status"] != "complete":
                result["items"][current_index].update(status="cancelled", error=str(exc))
        except Exception as exc:
            result["status"] = "partial" if any(i["files_restored"] for i in result["items"]) else "failed"
            result["errors"].append(str(exc))
            if current_index is not None:
                affected = result["items"][current_index]
                if affected["status"] != "complete":
                    affected.update(status="partial" if affected["files_restored"] else "failed", error=str(exc))
        finally:
            for item in result["items"]:
                if item["status"] == "pending":
                    item["status"] = "skipped"
            result["restored_bytes"] = sum(i["restored_bytes"] for i in result["items"])
            manifest["restore_status"] = result["status"]
            manifest["last_restore_at"] = _now()
            manifest["last_restore_result"] = result
            try:
                self._write_manifest(folder, manifest)
            except Exception as exc:
                result["errors"].append(f"保存恢复状态失败：{exc}")
                if result["status"] == "complete":
                    result["status"] = "partial"
        return result
