import tempfile
import unittest
from pathlib import Path

from media_library_manager.empty_folder_cleanup import scan_duplicate_empty_folders
from media_library_manager.models import RootConfig


class EmptyFolderCleanupTests(unittest.TestCase):
    def test_scan_duplicate_empty_folders_flags_empty_and_sidecar_only_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            base = Path(raw_tmp)
            root_a = base / "RootA"
            root_b = base / "RootB"
            root_c = base / "RootC"
            root_a.mkdir()
            root_b.mkdir()
            root_c.mkdir()

            # Duplicate group with one side that contains real media.
            edge_a = root_a / "Edge of Tomorrow (2014)" / "Disc1"
            edge_a.mkdir(parents=True)
            (edge_a / "Edge.of.Tomorrow.2014.1080p.mkv").write_bytes(b"video")
            edge_b = root_b / "Edge of Tomorrow (2014)"
            edge_b.mkdir()
            (edge_b / "poster.jpg").write_bytes(b"image")

            # Duplicate group where both sides are deletion candidates.
            good_a = root_a / "Good Boy (2025)"
            good_a.mkdir()
            good_b = root_c / "Good Boy (2025)"
            good_b.mkdir()
            (good_b / "movie.nfo").write_text("metadata", encoding="utf-8")

            # This folder is not duplicated and should not appear in groups.
            unique = root_a / "Unique Folder"
            unique.mkdir()
            (unique / "poster.jpg").write_bytes(b"image")

            report = scan_duplicate_empty_folders(
                [
                    RootConfig(path=root_a, label="Root A", kind="movie"),
                    RootConfig(path=root_b, label="Root B", kind="movie"),
                    RootConfig(path=root_c, label="Root C", kind="movie"),
                ],
                lan_connections={"smb": []},
            )

            summary = report["summary"]
            self.assertEqual(summary["duplicate_groups"], 2)
            self.assertEqual(summary["groups_with_deletion_candidates"], 2)
            self.assertEqual(summary["deletion_candidates"], 3)

            names = {group["folder_name"] for group in report["groups"]}
            self.assertIn("Edge of Tomorrow (2014)", names)
            self.assertIn("Good Boy (2025)", names)
            self.assertNotIn("Unique Folder", names)

            edge_group = next(group for group in report["groups"] if group["folder_name"] == "Edge of Tomorrow (2014)")
            edge_items = {item["root_label"]: item for item in edge_group["items"]}
            self.assertTrue(edge_items["Root A"]["has_video"])
            self.assertFalse(edge_items["Root A"]["is_deletion_candidate"])
            self.assertFalse(edge_items["Root B"]["has_video"])
            self.assertTrue(edge_items["Root B"]["is_deletion_candidate"])
            self.assertEqual(edge_items["Root B"]["empty_reason"], "sidecar-only")

            good_group = next(group for group in report["groups"] if group["folder_name"] == "Good Boy (2025)")
            good_items = {item["root_label"]: item for item in good_group["items"]}
            self.assertEqual(good_items["Root A"]["empty_reason"], "empty")
            self.assertEqual(good_items["Root C"]["empty_reason"], "sidecar-only")

    def test_scan_duplicate_empty_folders_records_root_errors(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            base = Path(raw_tmp)
            root_valid = base / "Valid"
            root_valid.mkdir()
            root_missing = base / "MissingRoot"

            report = scan_duplicate_empty_folders(
                [
                    RootConfig(path=root_valid, label="Valid", kind="movie"),
                    RootConfig(path=root_missing, label="Missing", kind="movie"),
                ],
                lan_connections={"smb": []},
            )

            self.assertEqual(report["summary"]["errors"], 1)
            self.assertEqual(len(report["errors"]), 1)
            self.assertEqual(report["errors"][0]["root_label"], "Missing")
