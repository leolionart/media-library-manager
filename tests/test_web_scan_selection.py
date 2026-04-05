import unittest
from pathlib import Path

from media_library_manager.models import RootConfig
from media_library_manager.web import (
    build_selected_scan_roots,
    normalize_root_payload,
    root_requires_local_directory,
)


class WebScanSelectionTests(unittest.TestCase):
    def test_build_selected_scan_roots_maps_local_selected_root(self) -> None:
        library_root = RootConfig(path=Path("/library"), label="Library", priority=90, kind="movie")

        selected = build_selected_scan_roots(
            [
                {
                    "label": "Library",
                    "path": "/library",
                    "root_path": "/library",
                    "storage_uri": "/library",
                    "root_storage_uri": "/library",
                }
            ],
            roots=[library_root],
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].path, Path("/library"))
        self.assertEqual(selected[0].storage_uri, "")
        self.assertEqual(selected[0].priority, 90)

    def test_build_selected_scan_roots_maps_local_selected_folders(self) -> None:
        library_root = RootConfig(path=Path("/library"), label="Library", priority=90, kind="movie")

        selected = build_selected_scan_roots(
            [
                {
                    "label": "Dune (2024)",
                    "path": "/library/Dune (2024)",
                    "root_path": "/library",
                    "storage_uri": "local:///library/Dune%20%282024%29",
                    "root_storage_uri": "",
                }
            ],
            roots=[library_root],
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].path, Path("/library/Dune (2024)"))
        self.assertEqual(selected[0].storage_uri, "local:///library/Dune%20%282024%29")
        self.assertEqual(selected[0].priority, 90)

    def test_build_selected_scan_roots_maps_smb_selected_folders(self) -> None:
        library_root = RootConfig(
            path=Path("/smb/smb-1/DATA"),
            label="DATA",
            priority=80,
            kind="mixed",
            storage_uri="smb://DATA/?connection_id=smb-1",
            connection_id="smb-1",
            connection_label="NAS",
            share_name="DATA",
        )

        selected = build_selected_scan_roots(
            [
                {
                    "label": "Movies",
                    "path": "smb://DATA/Movies?connection_id=smb-1",
                    "root_path": "/smb/smb-1/DATA",
                    "storage_uri": "smb://DATA/Movies?connection_id=smb-1",
                    "root_storage_uri": "smb://DATA/?connection_id=smb-1",
                }
            ],
            roots=[library_root],
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].path, Path("/smb/smb-1/DATA/Movies"))
        self.assertEqual(selected[0].storage_uri, "smb://DATA/Movies?connection_id=smb-1")
        self.assertEqual(selected[0].connection_id, "smb-1")

    def test_build_selected_scan_roots_maps_smb_selected_root(self) -> None:
        library_root = RootConfig(
            path=Path("/smb/smb-1/DATA"),
            label="DATA",
            priority=80,
            kind="mixed",
            storage_uri="smb://DATA/?connection_id=smb-1",
            connection_id="smb-1",
            connection_label="NAS",
            share_name="DATA",
        )

        selected = build_selected_scan_roots(
            [
                {
                    "label": "DATA",
                    "path": "/smb/smb-1/DATA",
                    "root_path": "/smb/smb-1/DATA",
                    "storage_uri": "smb://DATA/?connection_id=smb-1",
                    "root_storage_uri": "smb://DATA/?connection_id=smb-1",
                }
            ],
            roots=[library_root],
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].path, Path("/smb/smb-1/DATA"))
        self.assertEqual(selected[0].storage_uri, "smb://DATA/?connection_id=smb-1")
        self.assertEqual(selected[0].connection_id, "smb-1")

    def test_build_selected_scan_roots_maps_rclone_selected_folder(self) -> None:
        library_root = RootConfig(
            path=Path("/rclone/media-remote"),
            label="media-remote",
            priority=70,
            kind="mixed",
            storage_uri="rclone://media-remote/",
        )

        selected = build_selected_scan_roots(
            [
                {
                    "label": "Movies",
                    "path": "rclone://media-remote/Movies",
                    "root_path": "/rclone/media-remote",
                    "storage_uri": "rclone://media-remote/Movies",
                    "root_storage_uri": "rclone://media-remote/",
                }
            ],
            roots=[library_root],
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].path, Path("/rclone/media-remote/Movies"))
        self.assertEqual(selected[0].storage_uri, "rclone://media-remote/Movies")

    def test_normalize_root_payload_accepts_rclone_storage_uri(self) -> None:
        payload = {
            "storage_uri": "rclone://media-remote/Movies",
            "label": "Movies",
            "kind": "movie",
        }
        root = normalize_root_payload(payload)

        self.assertEqual(root.storage_uri, payload["storage_uri"])
        self.assertEqual(root.label, "Movies")
        self.assertEqual(root.kind, "movie")
        self.assertEqual(root.path, Path("/rclone/media-remote/Movies"))
        self.assertFalse(root_requires_local_directory(root))

    def test_normalize_root_payload_accepts_rclone_storage_uri(self) -> None:
        payload = {
            "storage_uri": "rclone://media-remote/Movies",
            "label": "Movies",
            "kind": "movie",
        }
        root = normalize_root_payload(payload)

        self.assertEqual(root.storage_uri, payload["storage_uri"])
        self.assertEqual(root.label, "Movies")
        self.assertEqual(root.kind, "movie")
        self.assertEqual(root.path, Path("/rclone/media-remote/Movies"))
        self.assertFalse(root_requires_local_directory(root))
