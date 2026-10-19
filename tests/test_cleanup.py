"""Destructive operations here are restricted to freshly created synthetic temp data."""

import copy
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

from disk_cleaner_studio.core import cleanup
from disk_cleaner_studio.core.cleanup import CleanupError, CleanupService


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dcs-cleanup-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.backups = self.root / "backups"
        self.service = CleanupService(self.backups, [self.cache])

    def write(self, relative="cache.bin", data=b"synthetic cache"):
        path = self.cache / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def run_cleanup(self, paths=None, **kwargs):
        plan = self.service.create_plan(paths or [str(self.cache)])
        result = self.service.execute_plan(plan, **kwargs)
        self.assertEqual(result["status"], "complete", result)
        return result

    def manifest_path(self, result):
        return self.backups / result["backup_id"] / "manifest.json"

    def load_manifest(self, result):
        return json.loads(self.manifest_path(result).read_text(encoding="utf-8"))

    def save_signed_manifest(self, result, manifest):
        # White-box corruption tests also exercise structural validation AFTER a
        # valid HMAC, as a schema mistake must not become a traversal primitive.
        self.service._write_manifest(self.backups / result["backup_id"], manifest)

    def test_constructor_and_listing_are_read_only(self):
        self.assertFalse(self.backups.exists())
        self.assertEqual(self.service.list_backups(), [])
        self.assertFalse(self.backups.exists())
        self.backups.mkdir()
        fake = self.backups / ("a" * 32)
        fake.mkdir()
        (fake / "manifest.json").write_text('{"signature":"invalid"}', encoding="utf-8")
        self.assertEqual(self.service.list_backups()[0]["status"], "invalid")
        self.assertFalse((self.backups / ".integrity-key").exists())

    def test_inspection_is_read_only_and_does_not_hash(self):
        with patch.object(cleanup, "_snapshot", side_effect=AssertionError("inspection must not hash")):
            self.assertTrue(self.service.inspect_target(self.cache)["eligible"])
            denied = self.service.inspect_target(self.root / "personal")
            self.assertFalse(denied["eligible"])
            self.assertTrue(denied["reason"])
            self.assertFalse(self.service.inspect_target(self.cache / "missing")["eligible"])
        self.assertFalse(self.backups.exists())

    def test_dollar_sign_file_names_are_literal(self):
        path = self.write("$literal.cache", b"literal")
        result = self.run_cleanup([str(path)])
        self.assertEqual(result["logical_deleted_bytes"], len(b"literal"))
        self.assertEqual(self.service.restore_backup(result["backup_id"])["status"], "complete")
        self.assertEqual(path.read_bytes(), b"literal")

    def test_round_trip_hidden_empty_directories_and_contents(self):
        hidden = self.write(".hidden", b"hidden bytes")
        if os.name == "nt":
            import ctypes
            self.assertTrue(ctypes.windll.kernel32.SetFileAttributesW(str(hidden), 2))
        self.write("nested/visible.bin", b"\x00\xff\x01")
        (self.cache / "empty").mkdir()
        result = self.run_cleanup()
        self.assertTrue(self.cache.is_dir())
        self.assertEqual(list(self.cache.iterdir()), [])
        self.assertEqual(result["logical_deleted_bytes"], len(b"hidden bytes") + 3)
        self.assertTrue(result["backup_complete"])
        self.assertIn("free_space_delta_bytes", result)
        self.assertEqual(len(result["source_volumes"]), 1)
        restored = self.service.restore_backup(result["backup_id"])
        self.assertEqual(restored["status"], "complete", restored)
        self.assertEqual(hidden.read_bytes(), b"hidden bytes")
        self.assertEqual((self.cache / "nested/visible.bin").read_bytes(), b"\x00\xff\x01")
        self.assertTrue((self.cache / "empty").is_dir())
        listed = self.service.list_backups()
        self.assertEqual(listed[0]["restore_status"], "complete")
        # Persisted key works across service instances.
        fresh = CleanupService(self.backups, [self.cache])
        self.assertEqual(fresh.list_backups()[0]["backup_id"], result["backup_id"])

    def test_single_file_is_backed_up_removed_and_restored(self):
        path = self.write("one.bin", b"one")
        sibling = self.write("keep.bin", b"keep")
        result = self.run_cleanup([str(path)])
        self.assertFalse(path.exists())
        self.assertEqual(sibling.read_bytes(), b"keep")
        self.assertEqual(self.service.restore_backup(result["backup_id"])["status"], "complete")
        self.assertEqual(path.read_bytes(), b"one")

    def test_parent_child_and_duplicate_targets_are_deduplicated(self):
        file = self.write("nested/cache.bin")
        plan = self.service.create_plan([str(file), str(self.cache), str(file.parent), str(self.cache)])
        self.assertEqual(len(plan["items"]), 1)
        self.assertEqual(plan["items"][0]["path"], str(self.cache))
        self.assertEqual(plan["items"][0]["file_count"], 1)

    def test_outside_root_user_root_drive_root_and_unc_are_rejected(self):
        for value in (str(self.root), str(self.root / "outside"), "\\\\server\\share\\cache"):
            with self.subTest(value=value), self.assertRaises(CleanupError):
                self.service.create_plan([value])
        drive = Path(self.cache.anchor)
        dangerous = CleanupService(self.backups, [drive])
        with self.assertRaises(CleanupError):
            dangerous.create_plan([str(drive)])
        profile = os.environ.get("USERPROFILE") or os.environ.get("HOME")
        if profile:
            dangerous = CleanupService(self.backups, [Path(profile)])
            with self.assertRaises(CleanupError):
                dangerous.create_plan([profile])

    def test_backup_root_cannot_overlap_target(self):
        for backup_root in (self.cache / "backups", self.root):
            service = CleanupService(backup_root, [self.cache])
            with self.assertRaises(CleanupError):
                service.create_plan([str(self.cache)])

    def test_raw_dot_dot_is_rejected(self):
        with self.assertRaises(CleanupError):
            self.service.create_plan([str(self.cache) + os.sep + ".." + os.sep + "cache"])

    def test_changed_plan_is_rejected_before_copy(self):
        self.write()
        plan = self.service.create_plan([str(self.cache)])
        for change in ("path", "size", "backup_root", "fingerprint"):
            altered = copy.deepcopy(plan)
            if change == "backup_root":
                altered[change] = str(self.root / "other")
            elif change == "path":
                altered["items"][0][change] = str(self.root)
            elif change == "size":
                altered["items"][0][change] += 1
            else:
                altered["items"][0][change] = "0" * 64
            with self.subTest(change=change), self.assertRaises(CleanupError):
                self.service.execute_plan(altered)
        self.assertTrue((self.cache / "cache.bin").exists())
        self.assertEqual(self.service.list_backups(), [])

    def test_changed_or_new_source_rejects_stale_plan(self):
        path = self.write(data=b"old")
        plan = self.service.create_plan([str(self.cache)])
        path.write_bytes(b"new")
        result = self.service.execute_plan(plan)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["logical_deleted_bytes"], 0)
        self.assertIsNone(result["backup_id"])
        self.assertEqual(path.read_bytes(), b"new")
        plan = self.service.create_plan([str(self.cache)])
        self.write("new.bin", b"new")
        self.assertEqual(self.service.execute_plan(plan)["status"], "failed")
        self.assertEqual(path.read_bytes(), b"new")

    def test_all_items_backed_up_before_any_deletion(self):
        first = self.write("one/cache", b"first")
        second = self.write("two/cache", b"second")
        plan = self.service.create_plan([str(first.parent), str(second.parent)])
        original_copy = self.service._copy_file
        calls = []

        def fail_second(source, destination, expected, cancel_event=None):
            calls.append(source)
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
            if len(calls) == 2:
                raise OSError("injected disk write failure")
            return original_copy(source, destination, expected, cancel_event)

        with patch.object(self.service, "_copy_file", side_effect=fail_second):
            result = self.service.execute_plan(plan)
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(result["logical_deleted_bytes"], 0)
        self.assertFalse(result["backup_complete"])
        self.assertEqual(first.read_bytes(), b"first")
        self.assertEqual(second.read_bytes(), b"second")
        self.assertEqual(result["items"][0]["backup_status"], "verified")
        self.assertEqual(result["items"][1]["backup_status"], "failed")
        self.assertFalse(self.load_manifest(result)["backup_complete"])
        self.assertEqual(self.service.restore_backup(result["backup_id"])["status"], "failed")

    def test_change_during_backup_closes_global_delete_gate(self):
        first = self.write("one/cache", b"first")
        second = self.write("two/cache", b"second")
        plan = self.service.create_plan([str(first.parent), str(second.parent)])
        modified = False

        def progress(message, count):
            nonlocal modified
            if message.startswith("已校验备份") and not modified:
                first.write_bytes(b"changed while backing up")
                modified = True

        result = self.service.execute_plan(plan, progress=progress)
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(result["logical_deleted_bytes"], 0)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())

    def test_tampered_backup_closes_delete_gate(self):
        path = self.write(data=b"source")
        plan = self.service.create_plan([str(self.cache)])

        def corrupt(message, count):
            if message.startswith("已校验备份"):
                data = list(self.backups.glob("*/data/*/payload/cache.bin"))
                self.assertEqual(len(data), 1)
                data[0].write_bytes(b"broken")

        result = self.service.execute_plan(plan, progress=corrupt)
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(path.read_bytes(), b"source")

    def test_insufficient_space_never_copies_or_deletes(self):
        path = self.write()
        plan = self.service.create_plan([str(self.cache)])
        with patch.object(self.service, "_free", return_value=0):
            result = self.service.execute_plan(plan)
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["backup_id"])
        self.assertTrue(path.exists())

    def test_preview_can_be_cancelled_without_creating_backup_storage(self):
        self.write("a", b"first")
        self.write("b", b"second")
        event = threading.Event()

        def cancel(message, count):
            event.set()

        with self.assertRaises(CleanupError):
            self.service.create_plan([str(self.cache)], cancel_event=event, progress=cancel)
        self.assertFalse(self.backups.exists())
        self.assertTrue((self.cache / "a").exists())

    def test_cancel_before_execution_does_not_create_backup(self):
        path = self.write()
        plan = self.service.create_plan([str(self.cache)])
        event = threading.Event()
        event.set()
        result = self.service.execute_plan(plan, cancel_event=event)
        self.assertEqual(result["status"], "cancelled")
        self.assertIsNone(result["backup_id"])
        self.assertTrue(path.exists())

    def test_cancel_during_backup_never_deletes(self):
        first = self.write("a", b"first")
        second = self.write("b", b"second")
        plan = self.service.create_plan([str(self.cache)])
        event = threading.Event()

        def cancel(message, count):
            if message.startswith("已校验备份"):
                event.set()

        result = self.service.execute_plan(plan, cancel_event=event, progress=cancel)
        self.assertEqual(result["status"], "cancelled", result)
        self.assertFalse(result["backup_complete"])
        self.assertEqual(first.read_bytes(), b"first")
        self.assertEqual(second.read_bytes(), b"second")
        self.assertEqual(result["logical_deleted_bytes"], 0)

    def test_cancel_during_cleanup_retains_verified_backup(self):
        self.write("a", b"first")
        self.write("b", b"second")
        plan = self.service.create_plan([str(self.cache)])
        event = threading.Event()

        def cancel(message, count):
            if message.startswith("已清理"):
                event.set()

        result = self.service.execute_plan(plan, cancel_event=event, progress=cancel)
        self.assertEqual(result["status"], "cancelled", result)
        self.assertTrue(result["backup_complete"])
        self.assertEqual(result["logical_deleted_bytes"], len(b"first"))
        self.assertFalse((self.cache / "a").exists())
        self.assertTrue((self.cache / "b").exists())
        # Remove the synthetic conflicting original before a complete restore.
        (self.cache / "b").unlink()
        self.assertEqual(self.service.restore_backup(result["backup_id"])["status"], "complete")
        self.assertEqual((self.cache / "a").read_bytes(), b"first")
        self.assertEqual((self.cache / "b").read_bytes(), b"second")

    def test_partial_delete_failure_counts_only_successful_unlinks(self):
        self.write("a", b"first")
        second = self.write("b", b"second")
        plan = self.service.create_plan([str(self.cache)])
        original_unlink = Path.unlink

        def fail_one(path, *args, **kwargs):
            if path == second:
                raise PermissionError("injected locked cache")
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", fail_one):
            result = self.service.execute_plan(plan)
        self.assertEqual(result["status"], "partial", result)
        self.assertEqual(result["logical_deleted_bytes"], len(b"first"))
        self.assertEqual(result["items"][0]["files_deleted"], 1)
        self.assertTrue(result["backup_complete"])
        self.assertEqual(second.read_bytes(), b"second")
        self.assertEqual(self.load_manifest(result)["logical_deleted_bytes"], len(b"first"))

    def test_restore_global_conflict_check_never_overwrites(self):
        self.write("a", b"first")
        self.write("b", b"second")
        result = self.run_cleanup()
        existing = self.write("b", b"user-created contents")
        restored = self.service.restore_backup(result["backup_id"])
        self.assertEqual(restored["status"], "failed")
        self.assertFalse((self.cache / "a").exists())
        self.assertEqual(existing.read_bytes(), b"user-created contents")
        self.assertEqual(restored["restored_bytes"], 0)

    def test_restore_rejects_changed_backup_file_before_any_restore(self):
        self.write("a", b"first")
        self.write("b", b"second")
        result = self.run_cleanup()
        manifest = self.load_manifest(result)
        payload = self.backups / result["backup_id"] / manifest["items"][0]["backup_rel"]
        (payload / "b").write_bytes(b"broken backup")
        restored = self.service.restore_backup(result["backup_id"])
        self.assertEqual(restored["status"], "failed")
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_tampered_manifest_is_rejected_and_listed_as_invalid(self):
        self.write()
        result = self.run_cleanup()
        manifest = self.load_manifest(result)
        manifest["items"][0]["path"] = str(self.root / "personal")
        self.manifest_path(result).write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(CleanupError):
            self.service.restore_backup(result["backup_id"])
        self.assertEqual(self.service.list_backups()[0]["status"], "invalid")
        self.assertFalse((self.root / "personal").exists())

    def test_signed_manifest_path_traversal_absolute_and_root_changes_rejected(self):
        self.write()
        result = self.run_cleanup()
        original = self.load_manifest(result)
        for rel in ("../outside", "/absolute", "C:/absolute", "nested/../outside", "a\\outside"):
            altered = copy.deepcopy(original)
            altered["items"][0]["entries"][1]["rel"] = rel
            self.save_signed_manifest(result, altered)
            with self.subTest(rel=rel), self.assertRaises(CleanupError):
                self.service.restore_backup(result["backup_id"])
        altered = copy.deepcopy(original)
        altered["backup_root"] = str(self.root / "other")
        self.save_signed_manifest(result, altered)
        with self.assertRaises(CleanupError):
            self.service.restore_backup(result["backup_id"])
        altered = copy.deepcopy(original)
        altered["items"][0]["backup_rel"] = "../outside"
        self.save_signed_manifest(result, altered)
        with self.assertRaises(CleanupError):
            self.service.restore_backup(result["backup_id"])

    def test_invalid_backup_identifier_rejected(self):
        for identifier in ("..", "../x", str(self.root), "", "a/b", "z" * 32):
            with self.subTest(identifier=identifier), self.assertRaises(CleanupError):
                self.service.restore_backup(identifier)

    def test_restore_can_be_cancelled_and_backup_remains_verified(self):
        self.write("a", b"first")
        self.write("b", b"second")
        result = self.run_cleanup()
        event = threading.Event()

        def cancel(message, count):
            event.set()

        restored = self.service.restore_backup(result["backup_id"], cancel_event=event, progress=cancel)
        self.assertEqual(restored["status"], "cancelled", restored)
        self.assertEqual(restored["restored_bytes"], len(b"first"))
        self.assertEqual((self.cache / "a").read_bytes(), b"first")
        self.assertFalse((self.cache / "b").exists())
        self.assertTrue(self.service.list_backups()[0]["backup_complete"])

    def test_restore_publish_race_does_not_replace_existing_name(self):
        self.write(data=b"original")
        result = self.run_cleanup()
        original_copy = self.service._copy_file

        def race(source, destination, expected, cancel_event=None):
            destination.write_bytes(b"new user file")
            return original_copy(source, destination, expected, cancel_event)

        with patch.object(self.service, "_copy_file", side_effect=race):
            restored = self.service.restore_backup(result["backup_id"])
        self.assertEqual(restored["status"], "failed", restored)
        self.assertEqual((self.cache / "cache.bin").read_bytes(), b"new user file")

    def test_source_volume_observation_is_separate_from_backup_volume(self):
        path = self.write(data=b"logical")
        plan = self.service.create_plan([str(path)])
        calls = {"source": 0, "backup": 0}

        def fake_free(target=None):
            if target is None:
                calls["backup"] += 1
                return 10**9 - calls["backup"] * 100
            calls["source"] += 1
            return 10**9 + calls["source"] * 17

        with patch.object(self.service, "_free", side_effect=fake_free):
            result = self.service.execute_plan(plan)
        self.assertEqual(result["status"], "complete", result)
        self.assertEqual(result["free_space_delta_bytes"], 17)
        self.assertEqual(result["source_volumes"][0]["free_space_delta_bytes"], 17)
        self.assertLess(result["backup_free_space_delta_bytes"], 0)

    def test_default_browser_roots_and_cache_roots_are_narrow(self):
        local = self.root / "Local"
        profile = self.root / "User"
        roaming = self.root / "Roaming"
        for name in ("Default", "Profile 1", "Profile 27", "OtherPersonal"):
            (local / "Google/Chrome/User Data" / name / "Cache").mkdir(parents=True)
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local), "USERPROFILE": str(profile), "APPDATA": str(roaming)}):
            service = CleanupService(self.backups)
            roots = set(service.allowed_roots)
            self.assertIn(local / "Temp", roots)
            self.assertIn(local / "pip/Cache", roots)
            self.assertIn(local / "uv/cache", roots)
            self.assertIn(local / "npm-cache", roots)
            self.assertIn(local / "CrashDumps", roots)
            self.assertIn(profile / ".cache/pip", roots)
            self.assertIn(profile / ".gradle/caches", roots)
            self.assertIn(roaming / "npm-cache", roots)
            self.assertIn(local / "Google/Chrome/User Data/Default/Cache", roots)
            self.assertIn(local / "Google/Chrome/User Data/Profile 1/Cache", roots)
            self.assertNotIn(local / "Google/Chrome/User Data/OtherPersonal/Cache", roots)
            self.assertNotIn(profile / "Documents", roots)

    def test_reparse_flag_detection(self):
        from types import SimpleNamespace
        fake = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        self.assertTrue(cleanup._is_reparse(fake))

    def test_symlink_descendant_and_ancestor_are_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "personal").write_bytes(b"preserve")
        link = self.cache / "link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Windows symlink creation requires Developer Mode or an elevated token")
        with self.assertRaises(CleanupError):
            self.service.create_plan([str(self.cache)])
        service = CleanupService(self.backups, [link])
        with self.assertRaises(CleanupError):
            service.create_plan([str(link / "personal")])
        self.assertEqual((outside / "personal").read_bytes(), b"preserve")

    def test_backup_payload_symlink_rejected(self):
        self.write(data=b"original")
        result = self.run_cleanup()
        manifest = self.load_manifest(result)
        payload = self.backups / result["backup_id"] / manifest["items"][0]["backup_rel"] / "cache.bin"
        outside = self.root / "other"
        outside.write_bytes(b"original")
        payload.unlink()
        try:
            payload.symlink_to(outside)
        except OSError:
            self.skipTest("Windows symlink creation requires Developer Mode or an elevated token")
        restored = self.service.restore_backup(result["backup_id"])
        self.assertEqual(restored["status"], "failed")
        self.assertFalse((self.cache / "cache.bin").exists())
        self.assertEqual(outside.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()
