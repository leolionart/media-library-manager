import unittest
from pathlib import Path

from media_library_manager.models import RootConfig
from media_library_manager.scanner import parse_media_details, scan_roots


class ScannerTests(unittest.TestCase):
    def test_parse_movie_details(self) -> None:
        details = parse_media_details(Path("Dune.Part.Two.2024.2160p.REMUX.mkv"))
        self.assertEqual(details["kind"], "movie")
        self.assertEqual(details["title"], "Dune Part Two")
        self.assertEqual(details["year"], 2024)
        self.assertEqual(details["canonical_name"], "Dune Part Two (2024)")
        self.assertEqual(details["resolution"], 2160)
        self.assertEqual(details["source"], "remux")

    def test_parse_episode_details(self) -> None:
        details = parse_media_details(Path("Severance.S02E03.1080p.WEB-DL.mkv"))
        self.assertEqual(details["kind"], "series")
        self.assertEqual(details["title"], "Severance")
        self.assertEqual(details["season"], 2)
        self.assertEqual(details["episode"], 3)
        self.assertEqual(details["canonical_name"], "Severance - S02E03")

    def test_scan_detects_exact_duplicates(self) -> None:
        with self.subTest("scan duplicate roots"):
            import tempfile

            with tempfile.TemporaryDirectory() as raw_tmp:
                tmp_path = Path(raw_tmp)
                root_a = tmp_path / "DriveA"
                root_b = tmp_path / "DriveB"
                root_a.mkdir()
                root_b.mkdir()

                file_a = root_a / "Dune.Part.Two.2024.2160p.REMUX.mkv"
                file_b = root_b / "Dune Part Two (2024).mkv"
                file_a.write_bytes(b"same-bytes")
                file_b.write_bytes(b"same-bytes")

                report = scan_roots(
                    [
                        RootConfig(path=root_a, label="DriveA", priority=100),
                        RootConfig(path=root_b, label="DriveB", priority=80),
                    ]
                )

                self.assertEqual(len(report.files), 2)
                self.assertEqual(len(report.exact_duplicates), 1)
                self.assertEqual(len(report.media_collisions), 1)
