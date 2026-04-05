import hashlib
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_library_manager.scanner_storage import ScannedFileEntry, StorageManagerScannerStorage
from media_library_manager.storage import LocalStorageBackend, RcloneStorageBackend, SmbStorageBackend, StoragePath
from media_library_manager.storage.backends import StorageError


class FakeStorageManager:
    def __init__(self) -> None:
        self.called_with = None

    def compute_sha256(self, path: StoragePath) -> str:
        self.called_with = path
        return "manager-hash"


class StorageBackendTests(unittest.TestCase):
    def test_storage_path_roundtrips_rclone_uri(self) -> None:
        path = StoragePath.from_uri("rclone://media-remote/Movies/Dune%20%282024%29")
        self.assertEqual(path.backend, "rclone")
        self.assertEqual(path.rclone_remote, "media-remote")
        self.assertEqual(path.normalized_path(), "/Movies/Dune (2024)")
        self.assertEqual(path.to_uri(), "rclone://media-remote/Movies/Dune%20%282024%29")

    def test_local_backend_compute_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            file_path = Path(raw_tmp) / "movie.mkv"
            payload = b"same-bytes"
            file_path.write_bytes(payload)
            backend = LocalStorageBackend()

            digest = backend.compute_sha256(StoragePath.local(file_path))
            self.assertEqual(digest, hashlib.sha256(payload).hexdigest())

    @patch("media_library_manager.storage.backends.resolve_smb_connection")
    @patch("media_library_manager.storage.backends.run_smbclient_command")
    def test_smb_backend_compute_sha256_downloads_temp_file(self, run_mock, resolve_mock) -> None:
        resolve_mock.return_value = {
            "id": "smb-1",
            "host": "nas.local",
            "username": "leo",
            "password": "secret",
            "share_name": "Media",
        }
        payload = b"movie-bytes"
        downloaded_targets: list[Path] = []

        def side_effect(connection, command: str, *, timeout: int):  # noqa: ARG001
            match = re.search(r'get ".*?" "(.*?)"$', command)
            self.assertIsNotNone(match)
            target = Path(match.group(1))
            downloaded_targets.append(target)
            target.write_bytes(payload)
            return {"status": "success", "stdout": ""}

        run_mock.side_effect = side_effect
        backend = SmbStorageBackend({"smb": []})
        storage_path = StoragePath.smb(connection_id="smb-1", share_name="Media", path="/Movies/file.mkv")

        digest = backend.compute_sha256(storage_path)
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
        self.assertEqual(len(downloaded_targets), 1)
        self.assertFalse(downloaded_targets[0].exists())

    def test_smb_backend_compute_sha256_rejects_share_root(self) -> None:
        backend = SmbStorageBackend({"smb": []})
        path = StoragePath.smb(connection_id="smb-1", share_name="Media", path="/")
        with self.assertRaises(StorageError):
            backend.compute_sha256(path)

    @patch("media_library_manager.storage.backends.run_rclone_json")
    def test_rclone_backend_lists_entries_from_lsjson(self, run_rclone_json_mock) -> None:
        run_rclone_json_mock.return_value = [
            {"Name": "Movies", "IsDir": True, "Size": 0, "ModTime": "2026-04-05T12:00:00Z"},
            {"Name": "readme.txt", "IsDir": False, "Size": 12, "ModTime": "2026-04-05T12:01:00Z"},
        ]
        backend = RcloneStorageBackend()

        entries = backend.list_dir(StoragePath.rclone(remote="media-remote", path="/"))

        self.assertEqual([entry.name for entry in entries], ["Movies", "readme.txt"])
        self.assertTrue(entries[0].is_dir)
        self.assertEqual(entries[0].path.to_uri(), "rclone://media-remote/Movies")
        self.assertTrue(entries[1].is_file)
        self.assertEqual(entries[1].size, 12)

    def test_scanner_storage_uses_manager_compute_sha256_for_smb_by_default(self) -> None:
        manager = FakeStorageManager()
        storage = StorageManagerScannerStorage(manager)
        entry = ScannedFileEntry(
            path="smb://Media/Movies/file.mkv?connection_id=smb-1",
            relative_path="Movies/file.mkv",
            size=12,
            stem="file",
            suffix=".mkv",
            parent_name="Movies",
        )

        digest = storage.compute_sha256(entry)
        self.assertEqual(digest, "manager-hash")
        self.assertIsNotNone(manager.called_with)
        assert manager.called_with is not None
        self.assertEqual(manager.called_with.backend, "smb")
        self.assertEqual(manager.called_with.connection_id, "smb-1")
