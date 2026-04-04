import json
import tempfile
import unittest
from pathlib import Path

from media_library_manager.operations import apply_plan


class OperationTests(unittest.TestCase):
    def test_apply_plan_moves_and_deletes(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            source_root = tmp_path / "DriveA"
            duplicate_root = tmp_path / "DriveB"
            library_root = tmp_path / "Library"
            source_root.mkdir()
            duplicate_root.mkdir()
            library_root.mkdir()

            source = source_root / "Movie.2024.mkv"
            sidecar = source_root / "Movie.2024.srt"
            duplicate = duplicate_root / "Movie copy.mkv"
            source.write_bytes(b"movie-bytes")
            sidecar.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
            duplicate.write_bytes(b"movie-bytes")

            plan = {
                "version": 1,
                "summary": {"move": 1, "delete": 1, "review": 0},
                "actions": [
                    {
                        "type": "move",
                        "source": str(source),
                        "destination": str(library_root / "Movie (2024)" / "Movie (2024).mkv"),
                        "reason": "canonicalize_best_media",
                        "media_key": "movie:movie:2024",
                        "root_path": str(source_root),
                        "keep_path": str(library_root / "Movie (2024)" / "Movie (2024).mkv"),
                        "details": {},
                    },
                    {
                        "type": "delete",
                        "source": str(duplicate),
                        "destination": None,
                        "reason": "exact_duplicate",
                        "media_key": "movie:movie:2024",
                        "root_path": str(duplicate_root),
                        "keep_path": str(library_root / "Movie (2024)" / "Movie (2024).mkv"),
                        "details": {},
                    },
                ],
            }

            dry_run = apply_plan(json.loads(json.dumps(plan)), execute=False)
            self.assertEqual(dry_run["summary"]["dry-run"], 2)

            applied = apply_plan(plan, execute=True, prune_empty_dirs=True)
            self.assertEqual(applied["summary"]["applied"], 2)
            self.assertFalse(source.exists())
            self.assertFalse(duplicate.exists())
            self.assertTrue((library_root / "Movie (2024)" / "Movie (2024).mkv").exists())
            self.assertTrue((library_root / "Movie (2024)" / "Movie (2024).srt").exists())
