import tempfile
import unittest
from pathlib import Path

from media_library_manager.models import RootConfig
from media_library_manager.operations import apply_plan
from media_library_manager.scanner import scan_roots


class JobCancellationTests(unittest.TestCase):
    def test_scan_roots_stops_when_cancel_requested(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            root_path = tmp_path / "Downloads"
            movie_dir = root_path / "Movie (2024)"
            movie_dir.mkdir(parents=True)
            (movie_dir / "Movie.2024.mkv").write_bytes(b"x")

            with self.assertRaises(RuntimeError):
                scan_roots(
                    [RootConfig(path=root_path, label="Downloads")],
                    should_cancel=lambda: True,
                )

    def test_apply_plan_returns_cancelled_when_requested(self) -> None:
        plan = {
            "actions": [
                {
                    "type": "review",
                    "source": "/tmp/source",
                }
            ]
        }

        result = apply_plan(plan, should_cancel=lambda: True)

        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["cancelled_at_action"], 1)
