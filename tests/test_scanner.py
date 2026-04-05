import unittest
from pathlib import Path

from media_library_manager.models import RootConfig
from media_library_manager.scanner import parse_media_details, scan_roots
from media_library_manager.scanner_storage import ScannedFileEntry, StorageManagerScannerStorage
from media_library_manager.storage import default_storage_manager


class FakeScannerStorageBackend:
    def __init__(self, entries: list[ScannedFileEntry], hashes: dict[str, str]) -> None:
        self.entries = entries
        self.hashes = hashes
        self.hash_calls = 0

    def iter_video_files(self, root: RootConfig, *, allowed_suffixes: set[str]):
        for entry in self.entries:
            if entry.suffix in allowed_suffixes:
                yield entry

    def compute_sha256(self, entry: ScannedFileEntry) -> str:
        self.hash_calls += 1
        return self.hashes[entry.path]


class ProgressAwareFakeScannerStorageBackend(FakeScannerStorageBackend):
    def iter_video_files_with_progress(
        self,
        root: RootConfig,
        *,
        allowed_suffixes: set[str],
        progress_callback=None,
        should_cancel=None,
    ):
        if progress_callback:
            progress_callback({"event": "directory_scanned", "directory_path": str(root.path / "Movies"), "directories_scanned": 1})
        for entry in self.iter_video_files(root, allowed_suffixes=allowed_suffixes):
            yield entry


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

    def test_scan_supports_custom_storage_backend(self) -> None:
        root = RootConfig(path=Path("/virtual/root"), label="SMB", priority=100)
        entries = [
            ScannedFileEntry(
                path="smb://nas/Movies/Dune.Part.Two.2024.2160p.REMUX.mkv",
                relative_path="Dune.Part.Two.2024.2160p.REMUX.mkv",
                size=10,
                stem="Dune.Part.Two.2024.2160p.REMUX",
                suffix=".mkv",
                parent_name="Movies",
            ),
            ScannedFileEntry(
                path="smb://nas/Backup/Dune Part Two (2024).mkv",
                relative_path="Dune Part Two (2024).mkv",
                size=10,
                stem="Dune Part Two (2024)",
                suffix=".mkv",
                parent_name="Backup",
            ),
        ]
        backend = FakeScannerStorageBackend(
            entries=entries,
            hashes={
                "smb://nas/Movies/Dune.Part.Two.2024.2160p.REMUX.mkv": "same-hash",
                "smb://nas/Backup/Dune Part Two (2024).mkv": "same-hash",
            },
        )

        report = scan_roots([root], storage_backend=backend)

        self.assertEqual(len(report.files), 2)
        self.assertEqual(len(report.exact_duplicates), 1)
        self.assertEqual(len(report.media_collisions), 1)
        self.assertEqual(backend.hash_calls, 2)

    def test_scan_supports_storage_manager_backend_for_local_roots(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            root_dir = tmp_path / "Library"
            root_dir.mkdir()
            (root_dir / "Dune.Part.Two.2024.2160p.REMUX.mkv").write_bytes(b"same-bytes")
            (root_dir / "Dune Part Two (2024).mkv").write_bytes(b"same-bytes")

            manager_backend = StorageManagerScannerStorage(default_storage_manager())
            report = scan_roots([RootConfig(path=root_dir, label="Library", priority=100)], storage_backend=manager_backend)

            self.assertEqual(len(report.files), 2)
            self.assertEqual(len(report.exact_duplicates), 1)
            self.assertEqual(len(report.media_collisions), 1)

    def test_scan_roots_can_resume_from_root_checkpoint(self) -> None:
        root_a = RootConfig(path=Path("/library/A"), label="A", priority=100)
        root_b = RootConfig(path=Path("/library/B"), label="B", priority=90)
        entries = [
            ScannedFileEntry(
                path="/library/B/Movie (2024).mkv",
                relative_path="Movie (2024).mkv",
                size=10,
                stem="Movie (2024)",
                suffix=".mkv",
                parent_name="B",
            ),
        ]
        backend = FakeScannerStorageBackend(entries=entries, hashes={entries[0].path: "hash-b"})

        report = scan_roots([root_a, root_b], storage_backend=backend, start_root_index=2)

        self.assertEqual(len(report.files), 1)
        self.assertEqual(report.files[0].root_label, "B")

    def test_scan_detects_same_movie_files_in_same_folder(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            movie_dir = tmp_path / "Library" / "Dune Part Two (2024)"
            movie_dir.mkdir(parents=True)
            (movie_dir / "Dune.Part.Two.2024.2160p.REMUX.mkv").write_bytes(b"movie-a")
            (movie_dir / "Dune.Part.Two.2024.1080p.WEB-DL.mp4").write_bytes(b"movie-b")
            (movie_dir / "Dune.Part.Two.2024.sample.mkv").write_bytes(b"sample")

            report = scan_roots([RootConfig(path=tmp_path / "Library", label="Library", priority=100)])

            self.assertEqual(len(report.folder_media_duplicates), 1)
            group = report.folder_media_duplicates[0]
            self.assertEqual(group["canonical_name"], "Dune Part Two (2024)")
            self.assertEqual(group["folder_path"], str(movie_dir))
            self.assertEqual(len(group["items"]), 2)

    def test_scan_detects_same_folder_movie_duplicate_groups(self) -> None:
        root = RootConfig(path=Path("/library"), label="Library", priority=100)
        entries = [
            ScannedFileEntry(
                path="/library/Dune Part Two (2024)/Dune.Part.Two.2024.2160p.REMUX.mkv",
                relative_path="Dune Part Two (2024)/Dune.Part.Two.2024.2160p.REMUX.mkv",
                size=20,
                stem="Dune.Part.Two.2024.2160p.REMUX",
                suffix=".mkv",
                parent_name="Dune Part Two (2024)",
            ),
            ScannedFileEntry(
                path="/library/Dune Part Two (2024)/Dune Part Two (2024) 1080p WEB-DL.mp4",
                relative_path="Dune Part Two (2024)/Dune Part Two (2024) 1080p WEB-DL.mp4",
                size=10,
                stem="Dune Part Two (2024) 1080p WEB-DL",
                suffix=".mp4",
                parent_name="Dune Part Two (2024)",
            ),
        ]
        backend = FakeScannerStorageBackend(
            entries=entries,
            hashes={
                entries[0].path: "hash-a",
                entries[1].path: "hash-b",
            },
        )

        report = scan_roots([root], storage_backend=backend)

        self.assertEqual(len(report.folder_media_duplicates), 1)
        self.assertEqual(report.folder_media_duplicates[0]["canonical_name"], "Dune Part Two (2024)")
        self.assertEqual(len(report.folder_media_duplicates[0]["items"]), 2)

    def test_scan_ignores_same_folder_movie_samples_for_cleanup_groups(self) -> None:
        root = RootConfig(path=Path("/library"), label="Library", priority=100)
        entries = [
            ScannedFileEntry(
                path="/library/Dune Part Two (2024)/Dune.Part.Two.2024.2160p.REMUX.mkv",
                relative_path="Dune Part Two (2024)/Dune.Part.Two.2024.2160p.REMUX.mkv",
                size=20,
                stem="Dune.Part.Two.2024.2160p.REMUX",
                suffix=".mkv",
                parent_name="Dune Part Two (2024)",
            ),
            ScannedFileEntry(
                path="/library/Dune Part Two (2024)/Dune.Part.Two.2024.sample.mkv",
                relative_path="Dune Part Two (2024)/Dune.Part.Two.2024.sample.mkv",
                size=1,
                stem="Dune.Part.Two.2024.sample",
                suffix=".mkv",
                parent_name="Dune Part Two (2024)",
            ),
        ]
        backend = FakeScannerStorageBackend(
            entries=entries,
            hashes={
                entries[0].path: "hash-a",
                entries[1].path: "hash-b",
            },
        )

        report = scan_roots([root], storage_backend=backend)

        self.assertEqual(report.folder_media_duplicates, [])

    def test_scan_emits_directory_and_file_progress_events(self) -> None:
        root = RootConfig(path=Path("/library"), label="Library", priority=100)
        entry = ScannedFileEntry(
            path="/library/Dune Part Two (2024)/Dune.Part.Two.2024.2160p.REMUX.mkv",
            relative_path="Dune Part Two (2024)/Dune.Part.Two.2024.2160p.REMUX.mkv",
            size=20,
            stem="Dune.Part.Two.2024.2160p.REMUX",
            suffix=".mkv",
            parent_name="Dune Part Two (2024)",
        )
        backend = ProgressAwareFakeScannerStorageBackend(entries=[entry], hashes={entry.path: "hash-a"})
        events: list[dict[str, object]] = []

        report = scan_roots([root], storage_backend=backend, progress_callback=events.append)

        self.assertEqual(len(report.files), 1)
        event_names = [str(event.get("event")) for event in events]
        self.assertIn("root_started", event_names)
        self.assertIn("directory_scanned", event_names)
        self.assertIn("file_indexed", event_names)
        self.assertIn("root_completed", event_names)
        self.assertIn("scan_completed", event_names)
