import unittest
from pathlib import Path

from media_library_manager.models import RootConfig
from media_library_manager.scanner_storage import StorageManagerScannerStorage
from media_library_manager.storage import StoragePath
from media_library_manager.web import build_scan_storage_backend, compute_smb_storage_sha256


class WebScanStorageTests(unittest.TestCase):
    def test_build_scan_storage_backend_returns_none_without_storage_uri(self) -> None:
        roots = [RootConfig(path=Path("/tmp"), label="tmp")]
        backend = build_scan_storage_backend(roots=roots, lan_connections={"smb": []})
        self.assertIsNone(backend)

    def test_build_scan_storage_backend_returns_backend_with_storage_uri(self) -> None:
        roots = [
            RootConfig(
                path=Path("/tmp"),
                label="smb-root",
                storage_uri="smb://DATA/Movies?connection_id=smb-1",
                connection_id="smb-1",
                share_name="DATA",
            )
        ]
        backend = build_scan_storage_backend(roots=roots, lan_connections={"smb": []})
        self.assertIsInstance(backend, StorageManagerScannerStorage)

    def test_build_scan_storage_backend_returns_backend_for_rclone_roots(self) -> None:
        roots = [
            RootConfig(
                path=Path("/rclone/media-remote"),
                label="rclone-root",
                storage_uri="rclone://media-remote/Movies",
            )
        ]
        backend = build_scan_storage_backend(roots=roots, lan_connections={"smb": []})
        self.assertIsInstance(backend, StorageManagerScannerStorage)

    def test_compute_smb_storage_sha256_rejects_non_smb_path(self) -> None:
        with self.assertRaises(ValueError):
            compute_smb_storage_sha256(StoragePath.local("/tmp"), lan_connections={"smb": []})

    def test_compute_smb_storage_sha256_errors_when_connection_missing(self) -> None:
        smb_path = StoragePath.smb(connection_id="smb-missing", share_name="DATA", path="/Movies/Dune.mkv")
        with self.assertRaises(RuntimeError):
            compute_smb_storage_sha256(smb_path, lan_connections={"smb": []})
