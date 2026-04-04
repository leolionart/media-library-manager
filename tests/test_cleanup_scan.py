import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_library_manager.cleanup_scan import rebuild_cleanup_report, scan_provider_cleanup
from media_library_manager.planner import media_from_dict


class CleanupScanTests(unittest.TestCase):
    @patch("media_library_manager.cleanup_scan.RadarrClient.list_movies")
    def test_scan_provider_cleanup_reads_radarr_library_paths(self, list_movies_mock) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            movie_dir = Path(raw_tmp) / "Dune Part Two (2024)"
            movie_dir.mkdir()
            (movie_dir / "Dune.Part.Two.2024.2160p.REMUX.mkv").write_bytes(b"a")
            (movie_dir / "Dune Part Two (2024) 1080p WEB-DL.mp4").write_bytes(b"b")
            list_movies_mock.return_value = [{"id": 101, "title": "Dune Part Two", "year": 2024, "path": str(movie_dir)}]

            report = scan_provider_cleanup(
                {
                    "radarr": {"enabled": True, "base_url": "https://radarr.local", "api_key": "secret"},
                    "sonarr": {"enabled": False, "base_url": "", "api_key": ""},
                },
                providers=["radarr"],
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
            season_dir = series_dir / "Season 02"
            season_dir.mkdir(parents=True)
            (season_dir / "Severance.S02E03.1080p.WEB-DL.mkv").write_bytes(b"a")
            (season_dir / "Severance.S02E03.2160p.WEB-DL.mkv").write_bytes(b"b")
            list_series_mock.return_value = [{"id": 202, "title": "Severance", "year": 2022, "path": str(series_dir)}]

            report = scan_provider_cleanup(
                {
                    "radarr": {"enabled": False, "base_url": "", "api_key": ""},
                    "sonarr": {"enabled": True, "base_url": "https://sonarr.local", "api_key": "secret"},
                },
                providers=["sonarr"],
            )

            self.assertEqual(report["summary"]["roots_scanned"], 1)
            self.assertEqual(report["summary"]["folder_media_duplicate_groups"], 1)
            self.assertEqual(report["folder_media_duplicates"][0]["provider"], "sonarr")
            self.assertEqual(report["folder_media_duplicates"][0]["provider_item_title"], "Severance")

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
