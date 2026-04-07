import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_library_manager.folder_index import build_folder_metadata_index
from media_library_manager.models import RootConfig


class FolderIndexTests(unittest.TestCase):
    def test_build_folder_metadata_index_captures_direct_video_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            root_path = Path(raw_tmp) / "Movies"
            movie_dir = root_path / "Dune Part Two (2024)"
            movie_dir.mkdir(parents=True)
            (movie_dir / "Dune.Part.Two.2024.2160p.REMUX.mkv").write_bytes(b"a")
            (movie_dir / "poster.jpg").write_bytes(b"x")
            root_path = root_path.resolve()
            movie_dir = movie_dir.resolve()

            report = build_folder_metadata_index(
                [RootConfig(path=root_path, label="Movies", kind="movie")],
                {"smb": []},
                max_depth=3,
            )

            self.assertEqual(report["version"], 2)
            self.assertEqual(report["summary"]["folders"], 1)
            self.assertEqual(report["summary"]["video_files"], 1)
            self.assertEqual(report["items"][0]["path"], str(movie_dir))
            self.assertEqual(report["items"][0]["video_file_count"], 1)
            self.assertEqual(report["items"][0]["video_files"][0]["name"], "Dune.Part.Two.2024.2160p.REMUX.mkv")

    def test_build_folder_metadata_index_keeps_video_metadata_at_max_depth(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            root_path = Path(raw_tmp) / "Series"
            season_dir = root_path / "Severance" / "Season 02"
            season_dir.mkdir(parents=True)
            (season_dir / "Severance.S02E03.2160p.WEB-DL.mkv").write_bytes(b"a")
            root_path = root_path.resolve()
            season_dir = season_dir.resolve()

            report = build_folder_metadata_index(
                [RootConfig(path=root_path, label="Series", kind="series")],
                {"smb": []},
                max_depth=2,
            )

            season_item = next(item for item in report["items"] if item["path"] == str(season_dir))
            self.assertEqual(season_item["depth"], 2)
            self.assertEqual(season_item["video_file_count"], 1)
            self.assertEqual(season_item["video_files"][0]["name"], "Severance.S02E03.2160p.WEB-DL.mkv")

    @patch("media_library_manager.folder_index.list_entries_recursive")
    def test_build_folder_metadata_index_dedupes_duplicate_rclone_video_rows(self, list_entries_recursive_mock) -> None:
        list_entries_recursive_mock.return_value = [
            {"Path": "TV Series/The Continental (2023)", "Name": "The Continental (2023)", "IsDir": True},
            {"Path": "TV Series/The Continental (2023)/Season 1", "Name": "Season 1", "IsDir": True},
            {
                "Path": "TV Series/The Continental (2023)/Season 1/The Continental (2023) - S01E03 - Night 3 - Theater of Pain WEBDL-1080p.mkv",
                "Name": "The Continental (2023) - S01E03 - Night 3 - Theater of Pain WEBDL-1080p.mkv",
                "IsDir": False,
                "Size": 100,
            },
            {
                "Path": "TV Series/The Continental (2023)/Season 1/The Continental (2023) - S01E03 - Night 3 - Theater of Pain WEBDL-1080p.mkv",
                "Name": "The Continental (2023) - S01E03 - Night 3 - Theater of Pain WEBDL-1080p.mkv",
                "IsDir": False,
                "Size": 100,
            },
        ]

        report = build_folder_metadata_index(
            [RootConfig(path=Path("/rclone/aitran"), label="DATA gdrive", kind="mixed", storage_uri="rclone://aitran/")],
            {"smb": []},
            max_depth=4,
        )

        season_item = next(item for item in report["items"] if item["path"] == "/rclone/aitran/TV Series/The Continental (2023)/Season 1")
        self.assertEqual(season_item["video_file_count"], 1)
        self.assertEqual(len(season_item["video_files"]), 1)
