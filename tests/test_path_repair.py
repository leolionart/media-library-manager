import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_library_manager.models import RootConfig
from media_library_manager.path_repair import delete_provider_item, scan_provider_path_issues, search_library_paths, update_provider_item_path
from media_library_manager.provider_path_resolution import provider_path_maps_to_connected_root, resolve_provider_directory


class PathRepairTests(unittest.TestCase):
    @patch("media_library_manager.path_repair.RadarrClient.list_movies")
    def test_scan_provider_path_issues_lists_missing_path_without_suggestions(self, list_movies_mock) -> None:
        list_movies_mock.return_value = [
            {
                "id": 11,
                "title": "Dune Part Two",
                "year": 2024,
                "path": "/missing/Dune Part Two (2024)",
                "hasFile": False,
                "isAvailable": True,
            }
        ]

        result = scan_provider_path_issues(
            {"radarr": {"enabled": True, "base_url": "http://radarr.local", "api_key": "abc"}, "sonarr": {"enabled": False}},
            [RootConfig(path=Path("/volume2/DATA/rclone/gdrive/Movies"), label="Movies", kind="movie", storage_uri="rclone://aitran/Movies")],
            {"smb": []},
        )

        self.assertEqual(result["summary"]["issues"], 1)
        self.assertEqual(result["issues"][0]["reason"], "item_missing")

    @patch("media_library_manager.path_repair.RadarrClient.refresh_movie")
    @patch("media_library_manager.path_repair.RadarrClient.update_movie")
    @patch("media_library_manager.path_repair.RadarrClient.get_movie")
    def test_update_provider_item_path_updates_radarr_item(self, get_movie_mock, update_movie_mock, refresh_movie_mock) -> None:
        get_movie_mock.return_value = {"id": 11, "title": "Dune Part Two", "year": 2024, "path": "/old/path"}
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

    @patch("media_library_manager.path_repair.default_storage_manager")
    def test_search_library_paths_uses_cached_folder_index_before_live_scan(self, default_storage_manager_mock) -> None:
        result = search_library_paths(
            provider="sonarr",
            query="BEEF",
            roots=[RootConfig(path=Path("/library/series"), label="Series", kind="series")],
            lan_connections={"smb": []},
            folder_index_report={
                "items": [
                    {
                        "label": "BEEF",
                        "normalized_name": "beef",
                        "path": "/library/series/BEEF",
                        "storage_uri": "local:///library/series/BEEF",
                        "root_label": "Series",
                        "root_path": "/library/series",
                        "root_storage_uri": "/library/series",
                        "kind": "series",
                        "depth": 1,
                    }
                ]
            },
        )

        self.assertEqual(result[0]["path"], "/library/series/BEEF")
        default_storage_manager_mock.assert_not_called()

    @patch("media_library_manager.path_repair.list_entries_recursive")
    @patch("media_library_manager.path_repair.default_storage_manager")
    def test_search_library_paths_uses_root_mount_path_for_rclone_results(self, default_storage_manager_mock, list_entries_recursive_mock) -> None:
        class FakeStorageManager:
            def list_dir(self, path):
                raise AssertionError("normal root traversal should not be used for rclone-focused search")

        default_storage_manager_mock.return_value = FakeStorageManager()
        list_entries_recursive_mock.return_value = [
            {"Path": "Movies/Borderlands (2024)", "Name": "Borderlands (2024)", "IsDir": True},
        ]
        result = search_library_paths(
            provider="radarr",
            query="Borderlands",
            roots=[RootConfig(path=Path("/volume2/DATA/rclone/gdrive"), label="DATA gdrive", kind="movie", storage_uri="rclone://aitran/")],
            lan_connections={"smb": []},
        )

        self.assertEqual(result[0]["path"], "/volume2/DATA/rclone/gdrive/Movies/Borderlands (2024)")

    @patch("media_library_manager.path_repair.default_storage_manager")
    def test_search_library_paths_prioritizes_provider_specific_root_before_mixed_roots(self, default_storage_manager_mock) -> None:
        from media_library_manager.storage.backends import StorageEntry

        class FakeStorageManager:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            def list_dir(self, path):
                self.calls.append((path.backend, path.normalized_path()))
                if path.backend == "local" and path.normalized_path() == "/library/series":
                    return [StorageEntry(path=path.join("BEEF"), name="BEEF", entry_type="directory")]
                return []

        manager = FakeStorageManager()
        default_storage_manager_mock.return_value = manager

        result = search_library_paths(
            provider="sonarr",
            query="BEEF",
            roots=[
                RootConfig(path=Path("/library/mixed"), label="Mixed", kind="mixed"),
                RootConfig(path=Path("/library/series"), label="Series", kind="series"),
            ],
            lan_connections={"smb": []},
        )

        self.assertEqual(result[0]["path"], "/library/series/BEEF")
        self.assertEqual(manager.calls[0][1], "/library/series")
        self.assertNotIn(("local", "/library/mixed"), manager.calls)

    @patch("media_library_manager.path_repair.list_entries_recursive")
    @patch("media_library_manager.path_repair.default_storage_manager")
    def test_search_library_paths_still_checks_series_root_when_rclone_root_exists(
        self,
        default_storage_manager_mock,
        list_entries_recursive_mock,
    ) -> None:
        from media_library_manager.storage.backends import StorageEntry

        class FakeStorageManager:
            def list_dir(self, path):
                if path.backend == "local" and path.normalized_path() == "/library/series":
                    return [StorageEntry(path=path.join("BEEF"), name="BEEF", entry_type="directory")]
                return []

        default_storage_manager_mock.return_value = FakeStorageManager()
        list_entries_recursive_mock.return_value = [
            {"Path": "TV Series/BEEF", "Name": "BEEF", "IsDir": True},
        ]

        result = search_library_paths(
            provider="sonarr",
            query="BEEF",
            roots=[
                RootConfig(path=Path("/library/series"), label="Series", kind="series"),
                RootConfig(path=Path("/volume2/DATA/rclone/gdrive"), label="DATA gdrive", kind="mixed", storage_uri="rclone://aitran/"),
            ],
            lan_connections={"smb": []},
        )

        self.assertEqual(result[0]["path"], "/library/series/BEEF")
        list_entries_recursive_mock.assert_not_called()

    @patch("media_library_manager.path_repair.list_entries_recursive")
    @patch("media_library_manager.path_repair.default_storage_manager")
    def test_search_library_paths_penalizes_episode_and_trickplay_folders_against_series_root(
        self,
        default_storage_manager_mock,
        list_entries_recursive_mock,
    ) -> None:
        class FakeStorageManager:
            def list_dir(self, path):
                raise AssertionError("normal root traversal should not be used for rclone-focused search")

        default_storage_manager_mock.return_value = FakeStorageManager()
        list_entries_recursive_mock.return_value = [
            {"Path": "TV Series/The Bear/Season 2/The Bear - S02E01 - Beef WEBDL-1080p.trickplay", "Name": "The Bear - S02E01 - Beef WEBDL-1080p.trickplay", "IsDir": True},
            {"Path": "TV Series/BEEF", "Name": "BEEF", "IsDir": True},
        ]

        result = search_library_paths(
            provider="sonarr",
            query="BEEF",
            roots=[RootConfig(path=Path("/volume2/DATA/rclone/gdrive"), label="DATA gdrive", kind="mixed", storage_uri="rclone://aitran/")],
            lan_connections={"smb": []},
        )

        self.assertEqual(result[0]["path"], "/volume2/DATA/rclone/gdrive/TV Series/BEEF")

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

    def test_provider_path_maps_to_connected_root_accepts_usbshare_alias(self) -> None:
        roots = [
            RootConfig(
                path=Path("/smb/smb-1/usbshare1"),
                label="usbshare1",
                kind="mixed",
                storage_uri="smb://usbshare1/?connection_id=smb-1",
                connection_id="smb-1",
                share_name="usbshare1",
            )
        ]

        self.assertTrue(
            provider_path_maps_to_connected_root(
                raw_path="/volumeUSB1/usbshare/Series/BEEF",
                roots=roots,
            )
        )

    def test_provider_path_maps_to_connected_root_accepts_rclone_root_label_alias(self) -> None:
        roots = [
            RootConfig(
                path=Path("/rclone/aitran"),
                label="DATA gdrive",
                kind="mixed",
                storage_uri="rclone://aitran/",
            ),
            RootConfig(
                path=Path("/rclone/naai"),
                label="DATA drive",
                kind="mixed",
                storage_uri="rclone://naai/",
            ),
        ]

        self.assertTrue(
            provider_path_maps_to_connected_root(
                raw_path="/volume2/DATA/rclone/gdrive/TV Series/Sweet Tooth",
                roots=roots,
            )
        )
        self.assertTrue(
            provider_path_maps_to_connected_root(
                raw_path="/volume2/DATA/rclone/drive/Series/Gen V",
                roots=roots,
            )
        )

    def test_provider_path_maps_to_connected_root_prefers_specific_drive_alias_over_generic_rclone_hint(self) -> None:
        roots = [
            RootConfig(
                path=Path("/rclone/aitran"),
                label="DATA gdrive",
                kind="mixed",
                storage_uri="rclone://aitran/",
            ),
            RootConfig(
                path=Path("/rclone/naai"),
                label="DATA drive",
                kind="mixed",
                storage_uri="rclone://naai/",
            ),
        ]

        self.assertTrue(
            provider_path_maps_to_connected_root(
                raw_path="/volume2/DATA/rclone/drive/Series/ONE PIECE (2023)",
                roots=roots,
            )
        )

    def test_resolve_provider_directory_maps_usbshare_alias_to_connected_root(self) -> None:
        class FakeStorageManager:
            def exists(self, path) -> bool:
                return path.backend == "smb" and path.share_name == "usbshare1" and path.normalized_path() == "/Series/BEEF"

            def is_dir(self, path) -> bool:
                return self.exists(path)

        roots = [
            RootConfig(
                path=Path("/smb/smb-1/usbshare1"),
                label="usbshare1",
                kind="mixed",
                storage_uri="smb://usbshare1/?connection_id=smb-1",
                connection_id="smb-1",
                share_name="usbshare1",
            )
        ]

        resolved, status = resolve_provider_directory(
            raw_path="/volumeUSB1/usbshare/Series/BEEF",
            roots=roots,
            manager=FakeStorageManager(),
        )

        self.assertEqual(status, "ok")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.storage_uri, "smb://usbshare1/Series/BEEF?connection_id=smb-1")

    @patch("media_library_manager.path_repair.RadarrClient.list_movies")
    def test_scan_provider_path_issues_accepts_path_resolved_through_connected_smb_root(
        self,
        list_movies_mock,
    ) -> None:
        list_movies_mock.return_value = [
            {
                "id": 15,
                "title": "Edge of Tomorrow",
                "year": 2014,
                "path": "/volume2/DATA/rclone/drive/Movies/Edge of Tomorrow (2014)",
                "hasFile": True,
                "isAvailable": True,
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

    @patch("media_library_manager.path_repair.RadarrClient.list_movies")
    def test_scan_provider_path_issues_accepts_path_resolved_through_connected_rclone_mount_alias(
        self,
        list_movies_mock,
    ) -> None:
        list_movies_mock.return_value = [
            {
                "id": 3,
                "title": "Borderlands",
                "year": 2024,
                "path": "/volume2/DATA/rclone/gdrive/Movies/Borderlands (2024)",
                "hasFile": True,
                "isAvailable": True,
            }
        ]

        result = scan_provider_path_issues(
            {"radarr": {"enabled": True, "base_url": "http://radarr.local", "api_key": "abc"}, "sonarr": {"enabled": False}},
            [
                RootConfig(
                    path=Path("/volume2/DATA/rclone/gdrive"),
                    label="DATA gdrive",
                    kind="mixed",
                    storage_uri="rclone://aitran/",
                )
            ],
            {"smb": []},
        )

        self.assertEqual(result["summary"]["issues"], 0)
        self.assertEqual(result["issues"], [])

    @patch("media_library_manager.path_repair.RadarrClient.list_movies")
    def test_scan_provider_path_issues_treats_provider_path_as_valid_when_it_maps_to_connected_root(
        self,
        list_movies_mock,
    ) -> None:
        list_movies_mock.return_value = [
            {
                "id": 3,
                "title": "Borderlands",
                "year": 2024,
                "path": "/volume2/DATA/rclone/gdrive/Movies/Borderlands (2024)",
                "hasFile": True,
                "isAvailable": True,
            }
        ]

        result = scan_provider_path_issues(
            {"radarr": {"enabled": True, "base_url": "http://radarr.local", "api_key": "abc"}, "sonarr": {"enabled": False}},
            [
                RootConfig(
                    path=Path("/volume2/DATA/rclone/gdrive"),
                    label="DATA gdrive",
                    kind="mixed",
                    storage_uri="rclone://aitran/",
                )
            ],
            {"smb": []},
        )

        self.assertEqual(result["summary"]["issues"], 0)
        self.assertEqual(result["issues"], [])

    @patch("media_library_manager.path_repair.RadarrClient.list_movies")
    def test_scan_provider_path_issues_keeps_unmapped_provider_path_as_issue(self, list_movies_mock) -> None:
        list_movies_mock.return_value = [
            {
                "id": 18,
                "title": "The Witcher",
                "year": 2019,
                "path": "/volumeUSB1/usbshare/Series/The Witcher",
                "hasFile": False,
                "isAvailable": True,
            }
        ]

        result = scan_provider_path_issues(
            {"radarr": {"enabled": True, "base_url": "http://radarr.local", "api_key": "abc"}, "sonarr": {"enabled": False}},
            [
                RootConfig(
                    path=Path("/volume2/DATA/rclone/gdrive"),
                    label="DATA gdrive",
                    kind="mixed",
                    storage_uri="rclone://aitran/",
                )
            ],
            {"smb": []},
        )

        self.assertEqual(result["summary"]["issues"], 1)
        self.assertEqual(result["issues"][0]["reason"], "item_missing")

    @patch("media_library_manager.path_repair.RadarrClient.list_movies")
    def test_scan_provider_path_issues_flags_path_when_it_does_not_map_to_any_connected_root(self, list_movies_mock) -> None:
        list_movies_mock.return_value = [
            {
                "id": 77,
                "title": "Unknown Root",
                "year": 2024,
                "path": "/other/system/Movies/Unknown Root (2024)",
                "hasFile": False,
                "isAvailable": True,
            }
        ]

        result = scan_provider_path_issues(
            {"radarr": {"enabled": True, "base_url": "http://radarr.local", "api_key": "abc"}, "sonarr": {"enabled": False}},
            [RootConfig(path=Path("/volume2/DATA/rclone/gdrive"), label="DATA gdrive", kind="mixed", storage_uri="rclone://aitran/")],
            {"smb": []},
        )

        self.assertEqual(result["summary"]["issues"], 1)
        self.assertEqual(result["issues"][0]["reason"], "item_missing")

    @patch("media_library_manager.path_repair.RadarrClient.list_movies")
    def test_scan_provider_path_issues_skips_unreleased_radarr_movies_even_when_path_is_missing(self, list_movies_mock) -> None:
        list_movies_mock.return_value = [
            {
                "id": 12,
                "title": "Future Movie",
                "year": 2026,
                "path": "/missing/Future Movie (2026)",
                "hasFile": False,
                "isAvailable": False,
            }
        ]

        result = scan_provider_path_issues(
            {"radarr": {"enabled": True, "base_url": "http://radarr.local", "api_key": "abc"}, "sonarr": {"enabled": False}},
            [RootConfig(path=Path("/volume2/DATA/rclone/gdrive/Movies"), label="Movies", kind="movie", storage_uri="rclone://aitran/Movies")],
            {"smb": []},
        )

        self.assertEqual(result["summary"]["issues"], 0)
        self.assertEqual(result["issues"], [])

    @patch("media_library_manager.path_repair.RadarrClient.list_movies")
    def test_scan_provider_path_issues_skips_radarr_movies_that_are_not_missing_in_provider(self, list_movies_mock) -> None:
        list_movies_mock.return_value = [
            {
                "id": 13,
                "title": "Existing Movie",
                "year": 2024,
                "path": "/missing/Existing Movie (2024)",
                "hasFile": True,
                "isAvailable": True,
            }
        ]

        result = scan_provider_path_issues(
            {"radarr": {"enabled": True, "base_url": "http://radarr.local", "api_key": "abc"}, "sonarr": {"enabled": False}},
            [RootConfig(path=Path("/volume2/DATA/rclone/gdrive/Movies"), label="Movies", kind="movie", storage_uri="rclone://aitran/Movies")],
            {"smb": []},
        )

        self.assertEqual(result["summary"]["issues"], 0)
        self.assertEqual(result["issues"], [])

    @patch("media_library_manager.path_repair.SonarrClient.list_series")
    def test_scan_provider_path_issues_keeps_sonarr_series_when_provider_reports_it_missing(self, list_series_mock) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            series_root = Path(raw_tmp) / "TV Series"
            series_path = series_root / "Parasyte - The Grey"
            series_path.mkdir(parents=True)
            list_series_mock.return_value = [
                {
                    "id": 8,
                    "title": "Parasyte: The Grey",
                    "year": 2024,
                    "path": str(series_path),
                    "statistics": {
                        "episodeCount": 6,
                        "episodeFileCount": 0,
                    },
                }
            ]

            result = scan_provider_path_issues(
                {"radarr": {"enabled": False}, "sonarr": {"enabled": True, "base_url": "http://sonarr.local", "api_key": "abc"}},
                [RootConfig(path=series_root, label="TV Series", kind="series")],
                {"smb": []},
            )

            self.assertEqual(result["summary"]["issues"], 1)
            self.assertEqual(result["issues"][0]["reason"], "item_missing")

    @patch("media_library_manager.path_repair.SonarrClient.list_series")
    def test_scan_provider_path_issues_keeps_sonarr_series_when_path_is_missing(self, list_series_mock) -> None:
        list_series_mock.return_value = [
            {
                "id": 8,
                "title": "Parasyte: The Grey",
                "year": 2024,
                "path": "/volume2/DATA/rclone/gdrive/TV Series/Parasyte - The Grey",
                "statistics": {
                    "episodeCount": 6,
                    "episodeFileCount": 0,
                },
            }
        ]

        result = scan_provider_path_issues(
            {"radarr": {"enabled": False}, "sonarr": {"enabled": True, "base_url": "http://sonarr.local", "api_key": "abc"}},
            [RootConfig(path=Path("/volume5/TV Series"), label="TV Series", kind="series")],
            {"smb": []},
        )

        self.assertEqual(result["summary"]["issues"], 1)
        self.assertEqual(result["issues"][0]["reason"], "item_missing")

    @patch("media_library_manager.path_repair.SonarrClient.list_series")
    def test_scan_provider_path_issues_keeps_sonarr_series_when_rclone_alias_maps_to_connected_root(
        self,
        list_series_mock,
    ) -> None:
        list_series_mock.return_value = [
            {
                "id": 4,
                "title": "Sweet Tooth",
                "year": 2021,
                "path": "/volume2/DATA/rclone/gdrive/TV Series/Sweet Tooth",
                "statistics": {
                    "episodeCount": 24,
                    "episodeFileCount": 0,
                },
            }
        ]

        result = scan_provider_path_issues(
            {"radarr": {"enabled": False}, "sonarr": {"enabled": True, "base_url": "http://sonarr.local", "api_key": "abc"}},
            [RootConfig(path=Path("/volume2/DATA/rclone/gdrive"), label="DATA gdrive", kind="mixed", storage_uri="rclone://aitran/")],
            {"smb": []},
        )

        self.assertEqual(result["summary"]["issues"], 1)
        self.assertEqual(result["issues"][0]["reason"], "item_missing")

    @patch("media_library_manager.path_repair.SonarrClient.list_series")
    def test_scan_provider_path_issues_skips_sonarr_series_when_provider_has_episode_files(self, list_series_mock) -> None:
        list_series_mock.return_value = [
            {
                "id": 441,
                "title": "ONE PIECE (2023)",
                "year": 2023,
                "path": "/volume2/DATA/rclone/drive/Series/ONE PIECE (2023)",
                "statistics": {
                    "episodeCount": 16,
                    "episodeFileCount": 16,
                },
            }
        ]

        result = scan_provider_path_issues(
            {"radarr": {"enabled": False}, "sonarr": {"enabled": True, "base_url": "http://sonarr.local", "api_key": "abc"}},
            [RootConfig(path=Path("/rclone/naai"), label="DATA drive", kind="mixed", storage_uri="rclone://naai/")],
            {"smb": []},
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
