import tempfile
import unittest
from pathlib import Path

from media_library_manager.models import LibraryTargets, RootConfig
from media_library_manager.planner import plan_actions
from media_library_manager.scanner import scan_roots


class PlannerTests(unittest.TestCase):
    def test_plan_moves_keeper_and_deletes_exact_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            source_root = tmp_path / "Source"
            backup_root = tmp_path / "Backup"
            movies_root = tmp_path / "Library" / "Movies"
            source_root.mkdir(parents=True)
            backup_root.mkdir(parents=True)
            movies_root.mkdir(parents=True)

            keeper = source_root / "Dune.Part.Two.2024.2160p.REMUX.mkv"
            duplicate = backup_root / "Dune Part Two (2024).mkv"
            keeper.write_bytes(b"same-bytes")
            duplicate.write_bytes(b"same-bytes")

            report = scan_roots(
                [
                    RootConfig(path=source_root, label="Source", priority=100),
                    RootConfig(path=backup_root, label="Backup", priority=50),
                ]
            )
            plan = plan_actions(report, LibraryTargets(movie_root=movies_root))

            self.assertEqual(plan["summary"]["move"], 1)
            self.assertEqual(plan["summary"]["delete"], 1)
            actions = {action["type"]: action for action in plan["actions"]}
            self.assertTrue(actions["move"]["destination"].endswith("Dune Part Two (2024)/Dune Part Two (2024).mkv"))
