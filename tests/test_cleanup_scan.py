import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_library_manager.cleanup_scan import rebuild_cleanup_report, scan_provider_cleanup
from media_library_manager.models import RootConfig
from media_library_manager.planner import media_from_dict


class CleanupScanTests(unittest.TestCase):
    def _folder_index_report(self, *items: dict[str, object]) -> dict[str, object]:
        return {
            "version": 2,
            "generated_at": "2026-04-07T00:00:00+00:00",
            "summary": {"roots": 1, "folders": len(items), "video_files": sum(int(item.get("video_file_count", 0)) for item in items), "errors": 0, "max_depth": 6},
            "roots": [],
            "items": list(items),
            "errors": [],
        }

    def _folder_index_item(self, *, path: str, root_path: str, label: str, kind: str = "movie", storage_uri: str = "", root_storage_uri: str = "", video_files: list[dict[str, object]] | None = None) -> dict[str, object]:
        return {
            "label": label,
            "normalized_name": label.lower(),
            "path": path,
            "storage_uri": storage_uri,
            "root_label": label,
            "root_path": root_path,
            "root_storage_uri": root_storage_uri,
            "kind": kind,
            "depth": 1,
            "video_file_count": len(video_files or []),
            "video_files": video_files or [],
        }

    def _video_file(self, *, path: str, relative_path: str, size: int, storage_uri: str = "") -> dict[str, object]:
        return {
            "name": Path(path).name,
            "path": path,
            "storage_uri": storage_uri,
            "relative_path": relative_path,
            "size": size,
        }

    @patch("media_library_manager.cleanup_scan.RadarrClient.list_movies")
    def test_scan_provider_cleanup_reads_radarr_library_paths(self, list_movies_mock) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            movie_dir = Path(raw_tmp) / "Dune Part Two (2024)"
            movie_dir.mkdir()
            movie_dir = movie_dir.resolve()
            list_movies_mock.return_value = [{"id": 101, "title": "Dune Part Two", "year": 2024, "path": str(movie_dir)}]

            report = scan_provider_cleanup(
                {
                    "radarr": {"enabled": True, "base_url": "https://radarr.local", "api_key": "secret"},
                    "sonarr": {"enabled": False, "base_url": "", "api_key": ""},
                },
                providers=["radarr"],
                folder_index_report=self._folder_index_report(
                    self._folder_index_item(
                        path=str(movie_dir),
                        root_path=str(movie_dir.parent),
                        label="Dune Part Two (2024)",
                        video_files=[
                            self._video_file(
                                path=str(movie_dir / "Dune.Part.Two.2024.2160p.REMUX.mkv"),
                                relative_path="Dune.Part.Two.2024.2160p.REMUX.mkv",
                                size=1,
                            ),
                            self._video_file(
                                path=str(movie_dir / "Dune Part Two (2024) 1080p WEB-DL.mp4"),
                                relative_path="Dune Part Two (2024) 1080p WEB-DL.mp4",
                                size=1,
                            ),
                        ],
                    )
                ),
            )

            self.assertEqual(report["summary"]["roots_scanned"], 1)
            self.assertEqual(report["summary"]["folder_media_duplicate_groups"], 1)
            self.assertEqual(len(report["folder_media_duplicates"]), 1)
            self.assertEqual(report["folder_media_duplicates"][0]["provider"], "radarr")
            self.assertEqual(report["folder_media_duplicates"][0]["provider_item_id"], 101)
            self.assertEqual(len(report["files"]), 2)

    @patch("media_library_manager.cleanup_scan.SonarrClient.list_series")
    def test_scan_provider_cleanup_reads_sonarr_library_paths(self, list_series_mock) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            series_dir = Path(raw_tmp) / "Severance"
            (series_dir / "Season 02").mkdir(parents=True)
            series_dir = series_dir.resolve()
            list_series_mock.return_value = [{"id": 202, "title": "Severance", "year": 2022, "path": str(series_dir)}]

            report = scan_provider_cleanup(
                {
                    "radarr": {"enabled": False, "base_url": "", "api_key": ""},
                    "sonarr": {"enabled": True, "base_url": "https://sonarr.local", "api_key": "secret"},
                },
                providers=["sonarr"],
                folder_index_report=self._folder_index_report(
                    self._folder_index_item(
                        path=str(series_dir),
                        root_path=str(series_dir.parent),
                        label="Severance",
                        kind="series",
                        video_files=[],
                    ),
                    self._folder_index_item(
                        path=str(series_dir / "Season 02"),
                        root_path=str(series_dir.parent),
                        label="Season 02",
                        kind="series",
                        video_files=[
                            self._video_file(
                                path=str(series_dir / "Season 02" / "Severance.S02E03.1080p.WEB-DL.mkv"),
                                relative_path="Season 02/Severance.S02E03.1080p.WEB-DL.mkv",
                                size=1,
                            ),
                            self._video_file(
                                path=str(series_dir / "Season 02" / "Severance.S02E03.2160p.WEB-DL.mkv"),
                                relative_path="Season 02/Severance.S02E03.2160p.WEB-DL.mkv",
                                size=1,
                            ),
                        ],
                    ),
                ),
            )

            self.assertEqual(report["summary"]["roots_scanned"], 1)
            self.assertEqual(report["summary"]["folder_media_duplicate_groups"], 1)
            self.assertEqual(report["folder_media_duplicates"][0]["provider"], "sonarr")
            self.assertEqual(report["folder_media_duplicates"][0]["provider_item_title"], "Severance")

    @patch("media_library_manager.cleanup_scan.RadarrClient.list_movies")
    def test_scan_provider_cleanup_resolves_provider_path_through_connected_smb_root(
        self,
        list_movies_mock,
    ) -> None:
        list_movies_mock.return_value = [
            {
                "id": 15,
                "title": "Edge of Tomorrow",
                "year": 2014,
                "path": "/volume2/DATA/rclone/drive/Movies/Edge of Tomorrow (2014)",
            }
        ]

        report = scan_provider_cleanup(
            {
                "radarr": {"enabled": True, "base_url": "https://radarr.local", "api_key": "secret"},
                "sonarr": {"enabled": False, "base_url": "", "api_key": ""},
            },
            providers=["radarr"],
            roots=[
                RootConfig(
                    path=Path("/smb/conn-1/DATA/rclone/drive/Movies"),
                    label="DATA Movies",
                    priority=90,
                    kind="movie",
                    connection_id="conn-1",
                    connection_label="Synology.local",
                    storage_uri="smb://DATA/rclone/drive/Movies?connection_id=conn-1",
                    share_name="DATA",
                )
            ],
            folder_index_report=self._folder_index_report(
                self._folder_index_item(
                    path="/smb/conn-1/DATA/rclone/drive/Movies/Edge of Tomorrow (2014)",
                    root_path="/smb/conn-1/DATA/rclone/drive/Movies",
                    label="Edge of Tomorrow (2014)",
                    storage_uri="smb://DATA/rclone/drive/Movies/Edge%20of%20Tomorrow%20%282014%29?connection_id=conn-1",
                    root_storage_uri="smb://DATA/rclone/drive/Movies?connection_id=conn-1",
                    video_files=[
                        self._video_file(
                            path="/smb/conn-1/DATA/rclone/drive/Movies/Edge of Tomorrow (2014)/Edge.of.Tomorrow.2014.1080p.mkv",
                            relative_path="Edge.of.Tomorrow.2014.1080p.mkv",
                            size=10,
                            storage_uri="smb://DATA/rclone/drive/Movies/Edge%20of%20Tomorrow%20%282014%29/Edge.of.Tomorrow.2014.1080p.mkv?connection_id=conn-1",
                        )
                    ],
                )
            ),
        )

        self.assertEqual(report["summary"]["roots_scanned"], 1)
        self.assertEqual(report["summary"]["indexed_files"], 1)
        self.assertEqual(report["summary"]["skipped"], 0)
        self.assertEqual(report["provider_items"][0]["provider_path"], "/volume2/DATA/rclone/drive/Movies/Edge of Tomorrow (2014)")

    @patch("media_library_manager.cleanup_scan.RadarrClient.list_movies")
    def test_scan_provider_cleanup_uses_cached_rclone_folder_index_without_live_probe(
        self,
        list_movies_mock,
    ) -> None:
        list_movies_mock.return_value = [
            {
                "id": 18,
                "title": "Borderlands",
                "year": 2024,
                "path": "/volume2/rclone/aitran/Movies/Borderlands (2024)",
            }
        ]

        report = scan_provider_cleanup(
            {
                "radarr": {"enabled": True, "base_url": "https://radarr.local", "api_key": "secret"},
                "sonarr": {"enabled": False, "base_url": "", "api_key": ""},
            },
            providers=["radarr"],
            roots=[
                RootConfig(
                    path=Path("/rclone/aitran/Movies"),
                    label="aitran Movies",
                    priority=90,
                    kind="movie",
                    connection_id="",
                    connection_label="",
                    storage_uri="rclone://aitran/Movies",
                    share_name="",
                )
            ],
            folder_index_report=self._folder_index_report(
                self._folder_index_item(
                    path="/rclone/aitran/Movies/Borderlands (2024)",
                    root_path="/rclone/aitran/Movies",
                    label="Borderlands (2024)",
                    storage_uri="rclone://aitran/Movies/Borderlands%20%282024%29",
                    root_storage_uri="rclone://aitran/Movies",
                    video_files=[
                        self._video_file(
                            path="/rclone/aitran/Movies/Borderlands (2024)/Borderlands.2024.2160p.mkv",
                            relative_path="Borderlands.2024.2160p.mkv",
                            size=10,
                            storage_uri="rclone://aitran/Movies/Borderlands%20%282024%29/Borderlands.2024.2160p.mkv",
                        ),
                        self._video_file(
                            path="/rclone/aitran/Movies/Borderlands (2024)/Borderlands.2024.1080p.mkv",
                            relative_path="Borderlands.2024.1080p.mkv",
                            size=8,
                            storage_uri="rclone://aitran/Movies/Borderlands%20%282024%29/Borderlands.2024.1080p.mkv",
                        ),
                    ],
                )
            ),
        )

        self.assertEqual(report["summary"]["roots_scanned"], 1)
        self.assertEqual(report["summary"]["indexed_files"], 2)
        self.assertEqual(report["summary"]["folder_media_duplicate_groups"], 1)
        self.assertEqual(report["summary"]["skipped"], 0)

    @patch("media_library_manager.cleanup_scan.RadarrClient.list_movies")
    def test_scan_provider_cleanup_dedupes_duplicate_cached_video_rows(self, list_movies_mock) -> None:
        list_movies_mock.return_value = [
            {
                "id": 18,
                "title": "Borderlands",
                "year": 2024,
                "path": "/volume2/rclone/aitran/Movies/Borderlands (2024)",
            }
        ]

        duplicate_video = self._video_file(
            path="/rclone/aitran/Movies/Borderlands (2024)/Borderlands.2024.2160p.mkv",
            relative_path="Borderlands.2024.2160p.mkv",
            size=10,
            storage_uri="rclone://aitran/Movies/Borderlands%20%282024%29/Borderlands.2024.2160p.mkv",
        )

        report = scan_provider_cleanup(
            {
                "radarr": {"enabled": True, "base_url": "https://radarr.local", "api_key": "secret"},
                "sonarr": {"enabled": False, "base_url": "", "api_key": ""},
            },
            providers=["radarr"],
            roots=[
                RootConfig(
                    path=Path("/rclone/aitran/Movies"),
                    label="aitran Movies",
                    priority=90,
                    kind="movie",
                    connection_id="",
                    connection_label="",
                    storage_uri="rclone://aitran/Movies",
                    share_name="",
                )
            ],
            folder_index_report=self._folder_index_report(
                self._folder_index_item(
                    path="/rclone/aitran/Movies/Borderlands (2024)",
                    root_path="/rclone/aitran/Movies",
                    label="Borderlands (2024)",
                    storage_uri="rclone://aitran/Movies/Borderlands%20%282024%29",
                    root_storage_uri="rclone://aitran/Movies",
                    video_files=[duplicate_video, duplicate_video],
                )
            ),
        )

        self.assertEqual(report["summary"]["indexed_files"], 1)
        self.assertEqual(report["summary"]["folder_media_duplicate_groups"], 0)

    @patch("media_library_manager.cleanup_scan.RadarrClient.list_movies")
    def test_scan_provider_cleanup_requires_enriched_folder_index(self, list_movies_mock) -> None:
        list_movies_mock.return_value = [{"id": 101, "title": "Dune Part Two", "year": 2024, "path": "/library/Dune Part Two (2024)"}]

        with self.assertRaisesRegex(ValueError, "Refresh|outdated"):
            scan_provider_cleanup(
                {
                    "radarr": {"enabled": True, "base_url": "https://radarr.local", "api_key": "secret"},
                    "sonarr": {"enabled": False, "base_url": "", "api_key": ""},
                },
                providers=["radarr"],
                folder_index_report={"version": 1, "items": []},
            )

    def test_rebuild_cleanup_report_recomputes_groups_after_delete(self) -> None:
        existing = {
            "providers": ["radarr"],
            "provider_items": [{"provider": "radarr", "id": 101, "title": "Dune Part Two", "year": 2024, "path": "/library/Dune Part Two (2024)"}],
            "skipped_items": [],
            "errors": [],
        }
        files = [
            media_from_dict(
                {
                    "path": "/library/Dune Part Two (2024)/Dune.Part.Two.2024.2160p.REMUX.mkv",
                    "root_path": "/library/Dune Part Two (2024)",
                    "root_label": "Dune Part Two",
                    "root_priority": 100,
                    "kind": "movie",
                    "media_key": "movie:dune-part-two:2024",
                    "canonical_name": "Dune Part Two (2024)",
                    "title": "Dune Part Two",
                    "year": 2024,
                    "season": None,
                    "episode": None,
                    "size": 20,
                    "relative_path": "Dune.Part.Two.2024.2160p.REMUX.mkv",
                    "resolution": 2160,
                    "source": "remux",
                    "codec": "x265",
                    "dynamic_range": None,
                    "quality_rank": 120,
                    "sha256": None,
                    "storage_uri": "",
                    "root_storage_uri": "",
                }
            )
        ]

        rebuilt = rebuild_cleanup_report(existing, files)

        self.assertEqual(rebuilt["summary"]["folder_media_duplicate_groups"], 0)
        self.assertEqual(rebuilt["folder_media_duplicates"], [])
