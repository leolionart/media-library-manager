import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_library_manager.models import RootConfig
from media_library_manager.path_repair import delete_provider_item, scan_provider_path_issues, search_library_paths, update_provider_item_path


class PathRepairTests(unittest.TestCase):
    @patch("media_library_manager.path_repair.RadarrClient.list_movies")
    def test_scan_provider_path_issues_suggests_matching_local_root_folder(self, list_movies_mock) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            library_root = tmp_path / "Movies"
            candidate = library_root / "Dune Part Two (2024)"
            candidate.mkdir(parents=True)
            list_movies_mock.return_value = [
                {"id": 11, "title": "Dune Part Two", "year": 2024, "path": "/missing/Dune Part Two (2024)"}
            ]

            result = scan_provider_path_issues(
                {"radarr": {"enabled": True, "base_url": "http://radarr.local", "api_key": "abc"}, "sonarr": {"enabled": False}},
                [RootConfig(path=library_root, label="Movies", kind="movie")],
                {"smb": []},
            )

            self.assertEqual(result["summary"]["issues"], 1)
            self.assertEqual(result["issues"][0]["reason"], "path_not_found")
            self.assertEqual(result["issues"][0]["suggestions"][0]["path"], str(candidate.resolve()))

    @patch("media_library_manager.path_repair.RadarrClient.refresh_movie")
    @patch("media_library_manager.path_repair.RadarrClient.update_movie")
    @patch("media_library_manager.path_repair.RadarrClient.list_movies")
    def test_update_provider_item_path_updates_radarr_item(self, list_movies_mock, update_movie_mock, refresh_movie_mock) -> None:
        list_movies_mock.return_value = [{"id": 11, "title": "Dune Part Two", "year": 2024, "path": "/old/path"}]
        update_movie_mock.side_effect = lambda movie: movie
        refresh_movie_mock.return_value = {"status": "queued"}

        with tempfile.TemporaryDirectory() as raw_tmp:
            new_path = Path(raw_tmp) / "Dune Part Two (2024)"
            new_path.mkdir()

            result = update_provider_item_path(
                {"radarr": {"enabled": True, "base_url": "http://radarr.local", "api_key": "abc"}},
                provider="radarr",
                item_id=11,
                new_path=str(new_path),
            )

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["path"], str(new_path.resolve()))

    def test_search_library_paths_returns_matching_connected_folder(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            library_root = tmp_path / "Movies"
            candidate = library_root / "The Crow (2024)"
            candidate.mkdir(parents=True)

            result = search_library_paths(
                provider="radarr",
                query="The Crow",
                roots=[RootConfig(path=library_root, label="Movies", kind="movie")],
                lan_connections={"smb": []},
            )

            self.assertEqual(result[0]["path"], str(candidate.resolve()))

    @patch("media_library_manager.path_repair.RadarrClient.list_movies")
    def test_scan_provider_path_issues_finds_deeper_nested_match(self, list_movies_mock) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            library_root = tmp_path / "Movies"
            candidate = library_root / "Imported" / "2024" / "The Crow (2024)"
            candidate.mkdir(parents=True)
            list_movies_mock.return_value = [
                {"id": 21, "title": "The Crow", "year": 2024, "path": "/missing/library/The Crow (2024)"}
            ]

            result = scan_provider_path_issues(
                {"radarr": {"enabled": True, "base_url": "http://radarr.local", "api_key": "abc"}, "sonarr": {"enabled": False}},
                [RootConfig(path=library_root, label="Movies", kind="movie")],
                {"smb": []},
            )

            self.assertEqual(result["issues"][0]["suggestions"][0]["path"], str(candidate.resolve()))

    @patch("media_library_manager.path_repair.RadarrClient.delete_movie")
    def test_delete_provider_item_removes_radarr_item_without_deleting_files(self, delete_movie_mock) -> None:
        delete_movie_mock.return_value = {"status": "deleted"}

        result = delete_provider_item(
            {"radarr": {"enabled": True, "base_url": "http://radarr.local", "api_key": "abc"}},
            provider="radarr",
            item_id=11,
        )

        self.assertEqual(result["status"], "success")
        delete_movie_mock.assert_called_once_with(11, delete_files=False, add_import_exclusion=False)
