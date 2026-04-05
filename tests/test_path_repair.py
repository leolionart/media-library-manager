import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_library_manager.models import RootConfig
from media_library_manager.path_repair import delete_provider_item, scan_provider_path_issues, search_library_paths, update_provider_item_path


class PathRepairTests(unittest.TestCase):
    @patch("media_library_manager.path_repair.RadarrClient.list_movies")
    def test_scan_provider_path_issues_lists_missing_path_without_suggestions(self, list_movies_mock) -> None:
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
            self.assertEqual(result["issues"][0]["suggestions"], [])

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

    def test_search_library_paths_finds_deeper_nested_match(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            library_root = tmp_path / "Movies"
            candidate = library_root / "Imported" / "2024" / "The Crow (2024)"
            candidate.mkdir(parents=True)

            result = search_library_paths(
                provider="radarr",
                query="The Crow",
                roots=[RootConfig(path=library_root, label="Movies", kind="movie")],
                lan_connections={"smb": []},
            )

            self.assertEqual(result[0]["path"], str(candidate.resolve()))

    def test_search_library_paths_filters_irrelevant_titles(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            library_root = tmp_path / "Movies"
            relevant = library_root / "Edge of Tomorrow (2014)"
            irrelevant = library_root / "Tomorrowland (2015)"
            relevant.mkdir(parents=True)
            irrelevant.mkdir(parents=True)

            result = search_library_paths(
                provider="radarr",
                query="Edge of Tomorrow",
                roots=[RootConfig(path=library_root, label="Movies", kind="movie")],
                lan_connections={"smb": []},
            )

            paths = [item["path"] for item in result]
            self.assertIn(str(relevant.resolve()), paths)
            self.assertNotIn(str(irrelevant.resolve()), paths)

    def test_search_library_paths_prefers_exact_title_over_partial_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            library_root = tmp_path / "Movies"
            exact = library_root / "Mission Impossible Dead Reckoning Part One (2023)"
            partial = library_root / "Mission to Mars (2000)"
            exact.mkdir(parents=True)
            partial.mkdir(parents=True)

            result = search_library_paths(
                provider="radarr",
                query="Mission Impossible Dead Reckoning",
                roots=[RootConfig(path=library_root, label="Movies", kind="movie")],
                lan_connections={"smb": []},
            )

            paths = [item["path"] for item in result]
            self.assertIn(str(exact.resolve()), paths)
            self.assertNotIn(str(partial.resolve()), paths)

    @patch("media_library_manager.path_repair.default_storage_manager")
    @patch("media_library_manager.path_repair.RadarrClient.list_movies")
    def test_scan_provider_path_issues_accepts_path_resolved_through_connected_smb_root(
        self,
        list_movies_mock,
        default_storage_manager_mock,
    ) -> None:
        class FakeStorageManager:
            def exists(self, path) -> bool:
                return path.backend == "smb" and path.share_name == "DATA" and path.normalized_path() == "/rclone/drive/Movies/Edge of Tomorrow (2014)"

            def is_dir(self, path) -> bool:
                return self.exists(path)

        default_storage_manager_mock.return_value = FakeStorageManager()
        list_movies_mock.return_value = [
            {
                "id": 15,
                "title": "Edge of Tomorrow",
                "year": 2014,
                "path": "/volume2/DATA/rclone/drive/Movies/Edge of Tomorrow (2014)",
            }
        ]

        result = scan_provider_path_issues(
            {"radarr": {"enabled": True, "base_url": "http://radarr.local", "api_key": "abc"}, "sonarr": {"enabled": False}},
            [
                RootConfig(
                    path=Path("/smb/conn-1/DATA/rclone/drive/Movies"),
                    label="DATA Movies",
                    kind="movie",
                    connection_id="conn-1",
                    connection_label="Synology.local",
                    storage_uri="smb://DATA/rclone/drive/Movies?connection_id=conn-1",
                    share_name="DATA",
                )
            ],
            {"smb": [{"id": "conn-1"}]},
        )

        self.assertEqual(result["summary"]["issues"], 0)
        self.assertEqual(result["issues"], [])

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

    @patch("media_library_manager.path_repair.RadarrClient.delete_movie")
    def test_delete_provider_item_can_add_import_exclusion(self, delete_movie_mock) -> None:
        delete_movie_mock.return_value = {"status": "deleted"}

        result = delete_provider_item(
            {"radarr": {"enabled": True, "base_url": "http://radarr.local", "api_key": "abc"}},
            provider="radarr",
            item_id=11,
            add_import_exclusion=True,
        )

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["add_import_exclusion"])
        delete_movie_mock.assert_called_once_with(11, delete_files=False, add_import_exclusion=True)
