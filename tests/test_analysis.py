import csv
import threading
from pathlib import Path

import pytest

from disk_cleaner_studio.core.analysis import ScanRepository


def write_csv(path, rows, encoding="utf-8-sig", header=None, comment=""):
    with path.open("w", encoding=encoding, newline="") as stream:
        if comment:
            stream.write(comment + "\n")
        writer = csv.writer(stream)
        writer.writerow(header or ["File Name", "Size", "Allocated", "Attributes", "DRIVECAPACITY", "FREESPACE", "USEDSPACE"])
        writer.writerows(rows)
    return path


@pytest.fixture
def repo(tmp_path):
    return ScanRepository(tmp_path / "data")


def test_no_parent_child_double_count_and_duplicate_rows(repo, tmp_path):
    path = write_csv(tmp_path / "scan.csv", [
        ["D:\\", 1000, 1200, 16, 5000, 3800, 1200],
        [r"D:\Users\Test\AppData\Local\pip\Cache", 600, 700, 16],
        [r"D:\Users\Test\AppData\Local\pip\Cache\large.bin", 600, 700, 32],
        [r"d:\users\test\appdata\local\pip\cache", 600, 700, 16],
    ])
    result = repo.import_csv(path)
    assert result["entry_count"] == 3
    assert (result["total_bytes"], result["used_bytes"], result["free_bytes"]) == (5000, 1200, 3800)
    assert result["candidate_bytes"] == 700
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["is_dir"] is True
    assert repo.children(result["scan_id"])[0]["path"] == r"D:\Users"
    assert repo.top_files(result["scan_id"])[0]["size"] == 600


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16", "gb18030"])
def test_chinese_headers_encodings_and_capacity_comments(repo, tmp_path, encoding):
    path = write_csv(tmp_path / "中文.csv", [
        ["E:\\", 300, 400, 16],
        [r"E:\Users\张三\AppData\Local\Temp", 300, 400, 16],
    ], encoding=encoding, header=["文件名称", "大小", "分配", "属性"], comment="# 总容量: 1000, 已用空间: 400, 可用空间: 600")
    result = repo.import_csv(path)
    assert result["total_bytes"] == 1000
    assert result["used_bytes"] == 400
    assert result["free_bytes"] == 600
    assert result["candidates"][0]["cleanable"] is True


def test_missing_ancestors_are_synthesized_and_allocated_is_distinct(repo, tmp_path):
    result = repo.import_csv(write_csv(tmp_path / "scan.csv", [
        [r"C:\Users\A\AppData\Local\pip\Cache\a.whl", 900, 100, 32],
        [r"C:\Users\A\AppData\Local\pip\Cache\b.whl", 500, 50, 32],
    ]))
    assert result["root"] == r"C:\Users\A\AppData\Local\pip\Cache"
    assert result["candidate_bytes"] == 150
    assert result["candidates"][0]["size"] == 1400
    assert len(repo.children(result["scan_id"])) == 2


def test_only_precise_cache_roots_and_personal_data_are_manual(repo, tmp_path):
    roots = [r"C:\Users\A\Documents\cache", r"C:\Windows\Temp", r"C:\Users\A\AppData\Local\npm-cache2", r"C:\Users\A\AppData\Local\pip\Cache\nested", r"C:\Users\A\AppData\Local\Google\Chrome\User Data\Default\Cache", r"C:\Users\A\AppData\Local\Microsoft\Edge\User Data\Profile 1\Cache"]
    result = repo.import_csv(write_csv(tmp_path / "scan.csv", [[root, 100, 100, 16] for root in roots]))
    eligible = [c for c in result["candidates"] if c["cleanable"]]
    assert {item["path"] for item in eligible} == {r"C:\Users\A\AppData\Local\pip\Cache", roots[-1], roots[-2]}
    assert all(not c["cleanable"] for c in result["candidates"] if "Documents" in c["path"] or "Windows" in c["path"])


def test_reparse_root_not_eligible(repo, tmp_path):
    result = repo.import_csv(write_csv(tmp_path / "scan.csv", [[r"C:\Users\A\AppData\Local\Temp", 100, 100, 16 | 1024]]))
    assert result["candidates"][0]["cleanable"] is False
    assert result["candidates"][0]["risk"] == "manual"


def test_hardlink_allocated_marker_not_reclaimed(repo, tmp_path):
    result = repo.import_csv(write_csv(tmp_path / "scan.csv", [
        [r"C:\Users\A\AppData\Local\Temp\hardlink.bin", 100, "0100", 32],
    ]))
    assert result["candidate_bytes"] == 0
    assert repo.top_files(result["scan_id"])[0]["allocated"] == 0


def test_demo_cannot_be_cleaned_and_totals_match(repo):
    demo = Path(__file__).resolve().parents[1] / "examples" / "demo.csv"
    result = repo.import_csv(demo)
    assert result["is_demo"] is True
    assert result["total_bytes"] == result["used_bytes"] + result["free_bytes"]
    assert sum(row["allocated"] for row in repo.children(result["scan_id"])) == result["used_bytes"]
    assert result["candidates"]
    assert result["candidate_bytes"] == 5000000000
    assert all(not item["cleanable"] for item in result["candidates"])


def test_cancel_during_streaming_rolls_back_and_existing_scan_survives(repo, tmp_path):
    first = repo.import_csv(write_csv(tmp_path / "first.csv", [[r"C:\small.txt", 1, 1, 32]]))
    event = threading.Event()
    path = write_csv(tmp_path / "many.csv", [[fr"C:\data\file{index}.dat", 1, 1, 32] for index in range(1500)])
    def progress(message, count):
        if count >= 500:
            event.set()
    with pytest.raises(InterruptedError):
        repo.import_csv(path, cancel_event=event, progress=progress)
    assert [item["scan_id"] for item in repo.list_scans()] == [first["scan_id"]]
    with repo._connect() as db:
        assert db.execute("SELECT COUNT(DISTINCT scan_id) FROM entries").fetchone()[0] == 1


def test_comparison_uses_previous_scan_of_same_root(repo, tmp_path):
    old = repo.import_csv(write_csv(tmp_path / "old.csv", [["C:\\", 100, 100, 16], [r"C:\a.bin", 100, 100, 32]]))
    repo.import_csv(write_csv(tmp_path / "other.csv", [["D:\\", 999, 999, 16]]))
    new = repo.import_csv(write_csv(tmp_path / "new.csv", [["C:\\", 150, 150, 16], [r"C:\a.bin", 120, 120, 32], [r"C:\b.bin", 30, 30, 32]]))
    assert repo.compare(old["scan_id"]) == []
    changes = {item["name"]: item for item in repo.compare(new["scan_id"])}
    assert changes["a.bin"]["delta"] == 20
    assert changes["a.bin"]["current"] == 120
    assert changes["a.bin"]["previous"] == 100
    assert changes["b.bin"]["status"] == "added"


def test_invalid_csv_rolls_back_and_rejects_relative_paths(repo, tmp_path):
    path = write_csv(tmp_path / "invalid.csv", [[r"..\Temp", 100, 100, 16]])
    with pytest.raises(ValueError):
        repo.import_csv(path)
    assert repo.list_scans() == []


def test_children_and_comparison_are_bounded_at_sql_query(repo, tmp_path):
    path = write_csv(tmp_path / "many.csv", [["C:\\", 1500, 1500, 16]] + [[fr"C:\file{i}.bin", i, i, 32] for i in range(1500)])
    first = repo.import_csv(path)
    second = repo.import_csv(path)
    children = repo.children(second["scan_id"])
    assert len(children) == 500
    assert children[0]["allocated"] == 1499
    assert len(repo.children(second["scan_id"], limit=10)) == 10
    assert len(repo.compare(second["scan_id"])) == 500


def test_import_time_is_separate_from_csv_modification_time(repo, tmp_path):
    import os
    path = write_csv(tmp_path / "old.csv", [[r"C:\small.txt", 1, 1, 32]])
    os.utime(path, (1577836800, 1577836800))
    result = repo.import_csv(path)
    assert result["scanned_at"].startswith("2020-01-01")
    assert result["imported_at"] != result["scanned_at"]
    assert result["timestamp_source"] == "csv_mtime"


def test_candidate_does_not_extend_above_imported_scope(repo, tmp_path):
    result = repo.import_csv(write_csv(tmp_path / "nested.csv", [[r"C:\Users\A\AppData\Local\pip\Cache\nested\file.bin", 100, 100, 32]]))
    assert result["root"].endswith(r"Cache\nested")
    assert result["candidates"] == []


def test_wiztree_export_timestamp_preferred_and_resident_allocated_preserved(repo, tmp_path):
    path = write_csv(tmp_path / "export.csv", [["C:\\small\\", 41, 0, 0], [r"C:\small\note.txt", 41, 0, 32]], comment="生成者 WizTree 4.33 2026/10/18 22:35:51 (您可通过选项更改此信息)")
    result = repo.import_csv(path)
    assert result["timestamp_source"] == "csv_export_header"
    assert result["scanned_at"].startswith("2026-10-18T22:35:51")
    assert repo.top_files(result["scan_id"])[0]["allocated"] == 0


def test_top_files_orders_by_logical_size_not_allocated(repo, tmp_path):
    result = repo.import_csv(write_csv(tmp_path / "sizes.csv", [[r"C:\sparse.bin", 1000, 100, 32], [r"C:\normal.bin", 500, 500, 32]]))
    rows = repo.top_files(result["scan_id"])
    assert rows[0]["name"] == "sparse.bin"
    assert rows[0]["size"] == 1000
    assert rows[0]["allocated"] == 100
