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

    def test_scan_duplicate_empty_folders_detects_nested_duplicate_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            base = Path(raw_tmp)
            root_a = base / "RootA"
            root_b = base / "RootB"
            root_a.mkdir()
            root_b.mkdir()

            drive_movie = root_a / "Movies" / "Edge of Tomorrow (2014)"
            gdrive_movie = root_b / "Movie" / "Edge of Tomorrow (2014)"
            drive_movie.mkdir(parents=True)
            gdrive_movie.mkdir(parents=True)
            (drive_movie / "movie.mkv").write_bytes(b"video")
            (gdrive_movie / "poster.jpg").write_bytes(b"image")

            drive_series = root_a / "Series" / "Dark"
            gdrive_series = root_b / "TV Series" / "Dark"
            drive_series.mkdir(parents=True)
            gdrive_series.mkdir(parents=True)
            (gdrive_series / "show.nfo").write_text("metadata", encoding="utf-8")

            unrelated_same_name = root_a / "Extras" / "Dark"
            unrelated_same_name.mkdir(parents=True)

            report = scan_duplicate_empty_folders(
                [
                    RootConfig(path=root_a, label="Root A", kind="mixed"),
                    RootConfig(path=root_b, label="Root B", kind="mixed"),
                ],
                lan_connections={"smb": []},
            )

            relative_paths = {group["relative_path"] for group in report["groups"]}
            self.assertIn("Edge of Tomorrow (2014)", relative_paths)
            self.assertIn("Dark", relative_paths)
            self.assertNotIn("Extras/Dark", relative_paths)

            movie_group = next(group for group in report["groups"] if group["relative_path"] == "Edge of Tomorrow (2014)")
            self.assertEqual(movie_group["folder_name"], "Edge of Tomorrow (2014)")
            movie_items = {item["root_label"]: item for item in movie_group["items"]}
            self.assertTrue(movie_items["Root A"]["has_video"])
            self.assertTrue(movie_items["Root B"]["is_deletion_candidate"])
            self.assertEqual(movie_items["Root A"]["relative_path"], "Movies/Edge of Tomorrow (2014)")
            self.assertEqual(movie_items["Root B"]["relative_path"], "Movie/Edge of Tomorrow (2014)")

            series_group = next(group for group in report["groups"] if group["relative_path"] == "Dark")
            self.assertEqual(series_group["deletion_candidate_count"], 2)

    def test_scan_duplicate_empty_folders_marks_inferior_series_episode_sets(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            base = Path(raw_tmp)
            root_a = base / "RootA"
            root_b = base / "RootB"
            root_a.mkdir()
            root_b.mkdir()

            weaker_show = root_a / "Series" / "Severance"
            stronger_show = root_b / "TV Series" / "Severance"
            weaker_show.mkdir(parents=True)
            stronger_show.mkdir(parents=True)

            (weaker_show / "Severance.S02E01.mkv").write_bytes(b"video-1")
            (stronger_show / "Severance.S02E01.mkv").write_bytes(b"video-1")
            (stronger_show / "Severance.S02E02.mkv").write_bytes(b"video-2")

            report = scan_duplicate_empty_folders(
                [
                    RootConfig(path=root_a, label="Root A", kind="series"),
                    RootConfig(path=root_b, label="Root B", kind="series"),
                ],
                lan_connections={"smb": []},
            )

            show_group = next(group for group in report["groups"] if group["relative_path"] == "Severance")
            show_items = {item["root_label"]: item for item in show_group["items"]}

            self.assertTrue(show_items["Root A"]["is_deletion_candidate"])
            self.assertEqual(show_items["Root A"]["empty_reason"], "inferior-video-set")
            self.assertEqual(show_items["Root A"]["missing_episode_count"], 1)
            self.assertEqual(show_items["Root A"]["superseded_by_root_label"], "Root B")
            self.assertFalse(show_items["Root B"]["is_deletion_candidate"])
            self.assertEqual(show_items["Root A"]["comparison_mode"], "strict-subset")

    def test_scan_duplicate_empty_folders_prefers_larger_series_copy_when_overlap_is_messy(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            base = Path(raw_tmp)
            root_a = base / "RootA"
            root_b = base / "RootB"
            root_a.mkdir()
            root_b.mkdir()

            weaker_show = root_a / "Series" / "Stranger Things"
            stronger_show = root_b / "TV Series" / "Stranger Things"
            weaker_show.mkdir(parents=True)
            stronger_show.mkdir(parents=True)

            (weaker_show / "Stranger.Things.S05E01.mkv").write_bytes(b"video-1")
            (weaker_show / "Stranger.Things.S05E02.mkv").write_bytes(b"video-2")
            (stronger_show / "Stranger.Things.S05E02.mkv").write_bytes(b"video-2")
            (stronger_show / "Stranger.Things.S05E03.mkv").write_bytes(b"video-3")
            (stronger_show / "Stranger.Things.S05E04.mkv").write_bytes(b"video-4")

            report = scan_duplicate_empty_folders(
                [
                    RootConfig(path=root_a, label="Root A", kind="series"),
                    RootConfig(path=root_b, label="Root B", kind="series"),
                ],
                lan_connections={"smb": []},
            )

            show_group = next(group for group in report["groups"] if group["relative_path"] == "Stranger Things")
            show_items = {item["root_label"]: item for item in show_group["items"]}

            self.assertTrue(show_items["Root A"]["is_deletion_candidate"])
            self.assertEqual(show_items["Root A"]["empty_reason"], "inferior-video-set")
            self.assertEqual(show_items["Root A"]["comparison_mode"], "larger-overlap")
            self.assertEqual(show_items["Root A"]["missing_episode_count"], 2)
            self.assertEqual(show_items["Root A"]["exclusive_episode_count"], 1)
            self.assertFalse(show_items["Root B"]["is_deletion_candidate"])

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

    def test_scan_duplicate_empty_folders_does_not_match_same_leaf_name_in_different_branches(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            base = Path(raw_tmp)
            root_a = base / "RootA"
            root_b = base / "RootB"
            root_a.mkdir()
            root_b.mkdir()

            shared_a = root_a / "Movies" / "Shared Collection"
            shared_b = root_b / "Archives" / "Shared Collection"
            shared_a.mkdir(parents=True)
            shared_b.mkdir(parents=True)

            (shared_a / "movie.mkv").write_bytes(b"video")
            (shared_b / "cover.jpg").write_bytes(b"meta")

            report = scan_duplicate_empty_folders(
                [
                    RootConfig(path=root_a, label="Root A", kind="movie"),
                    RootConfig(path=root_b, label="Root B", kind="movie"),
                ],
                lan_connections={"smb": []},
            )

            relative_paths = {group["relative_path"] for group in report["groups"]}
            self.assertNotIn("Movies/Shared Collection", relative_paths)
            self.assertNotIn("Archives/Shared Collection", relative_paths)

    def test_scan_duplicate_empty_folders_ignores_metadata_noise_folders(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            base = Path(raw_tmp)
            root_a = base / "RootA"
            root_b = base / "RootB"
            root_a.mkdir()
            root_b.mkdir()

            main_a = root_a / "Series" / "Dark"
            main_b = root_b / "TV Series" / "Dark"
            main_a.mkdir(parents=True)
            main_b.mkdir(parents=True)
            (main_a / "Dark.S01E01.mkv").write_bytes(b"video")
            (main_b / "poster.jpg").write_bytes(b"image")

            noise_a = main_a / "Dark.S01E01.trickplay"
            noise_b = main_b / "Dark.S01E01.trickplay"
            noise_a.mkdir()
            noise_b.mkdir()
            (noise_a / "320 - 10x10.jpg").write_bytes(b"tile")
            (noise_b / "320 - 10x10.jpg").write_bytes(b"tile")

            report = scan_duplicate_empty_folders(
                [
                    RootConfig(path=root_a, label="Root A", kind="mixed"),
                    RootConfig(path=root_b, label="Root B", kind="mixed"),
                ],
                lan_connections={"smb": []},
            )

            relative_paths = {group["relative_path"] for group in report["groups"]}
            self.assertIn("Dark", relative_paths)
            self.assertNotIn("Dark/Dark.S01E01.trickplay", relative_paths)

    def test_scan_duplicate_empty_folders_can_resume_from_root_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            base = Path(raw_tmp)
            root_a = base / "RootA"
            root_b = base / "RootB"
            root_a.mkdir()
            root_b.mkdir()

            (root_a / "Movies" / "Dark").mkdir(parents=True)
            (root_b / "Movie" / "Dark").mkdir(parents=True)
            (root_b / "Movie" / "Dark" / "poster.jpg").write_bytes(b"image")

            report = scan_duplicate_empty_folders(
                [
                    RootConfig(path=root_a, label="Root A", kind="mixed"),
                    RootConfig(path=root_b, label="Root B", kind="mixed"),
                ],
                lan_connections={"smb": []},
                start_root_index=2,
            )

            self.assertEqual(report["summary"]["roots_scanned"], 2)
            self.assertEqual(report["summary"]["duplicate_groups"], 0)
