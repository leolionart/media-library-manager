import unittest
from pathlib import Path

from media_library_manager.models import RootConfig
from media_library_manager.web import build_selected_scan_roots


class WebScanSelectionTests(unittest.TestCase):
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
