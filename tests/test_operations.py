import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_library_manager.operation_storage import OperationStorageRouter
from media_library_manager.operations import apply_plan, delete_file, delete_folder, delete_media_file, move_folder, move_folder_contents


class OperationTests(unittest.TestCase):
    def test_apply_plan_counts_review_actions_as_completed(self) -> None:
        plan = {
            "version": 1,
            "summary": {"move": 0, "delete": 0, "review": 2},
            "actions": [
                {
                    "type": "review",
                    "source": "/tmp/source-a.mkv",
                    "details": {},
                },
                {
                    "type": "review",
                    "source": "/tmp/source-b.mkv",
                    "details": {},
                },
            ],
        }
        events: list[dict[str, object]] = []

        result = apply_plan(plan, execute=False, progress_callback=events.append)

        self.assertEqual(result["summary"]["completed"], 2)
        self.assertEqual(result["summary"]["skipped"], 2)
        self.assertEqual(events[-1]["summary"]["completed"], 2)
        self.assertEqual(events[-1]["summary"]["skipped"], 2)

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

    def test_move_folder_moves_directory_into_destination_parent(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            source_parent = tmp_path / "Downloads"
            destination_parent = tmp_path / "Library"
            source_folder = source_parent / "Movie (2024)"
            source_parent.mkdir()
            destination_parent.mkdir()
            source_folder.mkdir()
            (source_folder / "Movie (2024).mkv").write_bytes(b"movie")

            preview = move_folder(source_folder, destination_parent, execute=False)
            self.assertEqual(preview["status"], "dry-run")
            self.assertTrue(source_folder.exists())

            result = move_folder(source_folder, destination_parent, execute=True)
            self.assertEqual(result["status"], "applied")
            self.assertFalse(source_folder.exists())
            self.assertTrue((destination_parent / "Movie (2024)" / "Movie (2024).mkv").exists())

    def test_move_folder_contents_moves_children_into_existing_folder(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            source = tmp_path / "Downloads" / "Movie (2024)"
            destination = tmp_path / "Library" / "Movie (2024)"
            source.mkdir(parents=True)
            destination.mkdir(parents=True)
            (source / "Movie (2024).mkv").write_bytes(b"movie")
            (source / "Movie (2024).srt").write_text("sub", encoding="utf-8")

            preview = move_folder_contents(source, destination, execute=False)
            self.assertEqual(preview["status"], "dry-run")

            result = move_folder_contents(source, destination, execute=True)
            self.assertEqual(result["status"], "applied")
            self.assertFalse(source.exists())
            self.assertTrue((destination / "Movie (2024).mkv").exists())
            self.assertTrue((destination / "Movie (2024).srt").exists())

    def test_delete_folder_removes_directory_tree(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            target = tmp_path / "DeleteMe" / "Nested"
            target.mkdir(parents=True)
            (target / "file.txt").write_text("x", encoding="utf-8")

            preview = delete_folder(tmp_path / "DeleteMe", execute=False)
            self.assertEqual(preview["status"], "dry-run")

            result = delete_folder(tmp_path / "DeleteMe", execute=True)
            self.assertEqual(result["status"], "applied")
            self.assertFalse((tmp_path / "DeleteMe").exists())

    def test_delete_file_removes_single_file_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            target = tmp_path / "Movie (2024).mkv"
            sidecar = tmp_path / "Movie (2024).srt"
            target.write_bytes(b"movie")
            sidecar.write_text("sub", encoding="utf-8")

            preview = delete_file(target, execute=False)
            self.assertEqual(preview["status"], "dry-run")
            self.assertTrue(target.exists())
            self.assertTrue(sidecar.exists())

            result = delete_file(target, execute=True)
            self.assertEqual(result["status"], "applied")
            self.assertFalse(target.exists())
            self.assertTrue(sidecar.exists())

    def test_delete_media_file_removes_sidecars_and_prunes_empty_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            root = tmp_path / "Library"
            movie_dir = root / "Movie (2024)"
            movie_dir.mkdir(parents=True)
            target = movie_dir / "Movie (2024).mkv"
            sidecar = movie_dir / "Movie (2024).srt"
            target.write_bytes(b"movie")
            sidecar.write_text("sub", encoding="utf-8")

            preview = delete_media_file(target, root_path=root, execute=False)
            self.assertEqual(preview["status"], "dry-run")
            self.assertEqual(len(preview["operations"]), 2)

            result = delete_media_file(target, root_path=root, execute=True, prune_empty_dirs=True)
            self.assertEqual(result["status"], "applied")
            self.assertFalse(target.exists())
            self.assertFalse(sidecar.exists())
            self.assertFalse(movie_dir.exists())

    @patch("media_library_manager.operation_storage.run_smbclient_command")
    def test_move_folder_supports_same_share_smb_rename(self, run_smbclient_mock) -> None:
        def run_side_effect(connection, command: str, *, timeout: int):  # noqa: ARG001
            if command == "ls":
                return {
                    "status": "success",
                    "stdout": "Source|0|2026-04-04|10:00:00|D\nDest|0|2026-04-04|10:00:00|D\n",
                }
            if command == 'cd "Dest";ls':
                return {"status": "success", "stdout": ""}
            if command == 'rename "Source" "Dest/Source"':
                return {"status": "success", "stdout": ""}
            return {"status": "error", "message": f"unexpected command: {command}"}

        run_smbclient_mock.side_effect = run_side_effect
        router = OperationStorageRouter(
            smb_connection_resolver=lambda connection_id: {
                "id": connection_id,
                "label": "NAS",
                "host": "nas.local",
                "username": "leo",
                "password": "secret",
            }
        )

        result = move_folder(
            "smb://nas-1/Media/Source",
            "smb://nas-1/Media/Dest",
            execute=True,
            storage_router=router,
        )
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["destination"], "smb://nas-1/Media/Dest/Source")

    def test_move_folder_rejects_cross_backend_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            source = tmp_path / "Downloads" / "Movie (2024)"
            source.parent.mkdir(parents=True)
            source.mkdir()
            result = move_folder(source, "smb://nas-1/Media/Library", execute=False)
            self.assertEqual(result["status"], "error")
            self.assertIn("SMB operation requires a connection resolver", result["message"])

    @patch("media_library_manager.operation_storage.run_smbclient_command")
    def test_move_folder_rejects_cross_share_smb_move(self, run_smbclient_mock) -> None:
        def run_side_effect(connection, command: str, *, timeout: int):  # noqa: ARG001
            if command == "ls":
                if connection["share_name"] == "Media":
                    return {"status": "success", "stdout": "Source|0|2026-04-04|10:00:00|D\n"}
                return {"status": "success", "stdout": "Library|0|2026-04-04|10:00:00|D\n"}
            if command == 'cd "Library";ls':
                return {"status": "success", "stdout": ""}
            if command == 'cd "Source";ls':
                return {"status": "success", "stdout": ""}
            return {"status": "error", "message": f"unexpected command: {command}"}

        run_smbclient_mock.side_effect = run_side_effect
        router = OperationStorageRouter(
            smb_connection_resolver=lambda connection_id: {
                "id": connection_id,
                "label": "NAS",
                "host": "nas.local",
                "username": "leo",
                "password": "secret",
            }
        )
        result = move_folder(
            "smb://nas-1/Media/Source",
            "smb://nas-1/Library/Library",
            execute=False,
            storage_router=router,
        )
        self.assertEqual(result["status"], "dry-run")
        self.assertIn({"mkdir": "smb://nas-1/Library/Library/Source"}, result["operations"])

    @patch("media_library_manager.operation_storage.run_smbclient_command")
    def test_move_folder_contents_supports_smb_source_to_local_destination(self, run_smbclient_mock) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            destination = tmp_path / "Library" / "Movie (2024)"
            destination.mkdir(parents=True)

            expected_file = (destination / "Movie (2024).mkv").resolve()

            def run_side_effect(connection, command: str, *, timeout: int):  # noqa: ARG001
                if command == "ls":
                    return {"status": "success", "stdout": "Incoming|0|2026-04-04|10:00:00|D\n"}
                if command == 'cd "Incoming";ls':
                    return {"status": "success", "stdout": "Movie (2024).mkv|100|2026-04-04|10:00:00|A\n"}
                if command == f'cd "Incoming";get "Movie (2024).mkv" "{expected_file}"':
                    expected_file.write_bytes(b"movie")
                    return {"status": "success", "stdout": ""}
                if command == 'recurse ON;prompt OFF;deltree "Incoming"':
                    return {"status": "success", "stdout": ""}
                return {"status": "error", "message": f"unexpected command: {command}"}

            run_smbclient_mock.side_effect = run_side_effect
            router = OperationStorageRouter(
                smb_connection_resolver=lambda connection_id: {
                    "id": connection_id,
                    "label": "NAS",
                    "host": "nas.local",
                    "username": "leo",
                    "password": "secret",
                }
            )

            result = move_folder_contents(
                "smb://nas-1/Media/Incoming",
                destination,
                execute=True,
                storage_router=router,
            )

            self.assertEqual(result["status"], "applied")
            self.assertTrue(expected_file.exists())
            self.assertIn({"delete_dir": "smb://nas-1/Media/Incoming"}, result["operations"])

    @patch("media_library_manager.operation_storage.run_smbclient_command")
    def test_move_folder_supports_local_source_to_smb_destination_parent(self, run_smbclient_mock) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            source = tmp_path / "Downloads" / "Movie (2024)"
            source.mkdir(parents=True)
            movie_file = source / "Movie (2024).mkv"
            movie_file.write_bytes(b"movie")

            def run_side_effect(connection, command: str, *, timeout: int):  # noqa: ARG001
                if command == "ls":
                    return {"status": "success", "stdout": "Library|0|2026-04-04|10:00:00|D\n"}
                if command == 'cd "Library";ls':
                    return {"status": "success", "stdout": ""}
                if command == 'cd "Library";mkdir "Movie (2024)"':
                    return {"status": "success", "stdout": ""}
                if command == 'cd "Library";ls':
                    return {"status": "success", "stdout": "Movie (2024)|0|2026-04-04|10:00:00|D\n"}
                if command == f'cd "Library/Movie (2024)";put "{movie_file.resolve()}" "Movie (2024).mkv"':
                    return {"status": "success", "stdout": ""}
                return {"status": "error", "message": f"unexpected command: {command}"}

            run_smbclient_mock.side_effect = run_side_effect
            router = OperationStorageRouter(
                smb_connection_resolver=lambda connection_id: {
                    "id": connection_id,
                    "label": "NAS",
                    "host": "nas.local",
                    "username": "leo",
                    "password": "secret",
                }
            )

            result = move_folder(
                source,
                "smb://nas-1/Media/Library",
                execute=True,
                storage_router=router,
            )

            self.assertEqual(result["status"], "applied")
            self.assertFalse(source.exists())
            self.assertEqual(result["destination"], "smb://nas-1/Media/Library/Movie%20%282024%29")

    @patch("media_library_manager.operation_storage.run_smbclient_command")
    def test_apply_plan_supports_move_action_with_smb_source_uri(self, run_smbclient_mock) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            destination = tmp_path / "Library" / "Movie (2024)" / "Movie (2024).mkv"
            source_root = tmp_path / "PseudoSmbRoot"
            source_root.mkdir()

            def run_side_effect(connection, command: str, *, timeout: int):  # noqa: ARG001
                if command == 'cd "Incoming";ls':
                    return {"status": "success", "stdout": "Movie (2024).mkv|100|2026-04-04|10:00:00|A\n"}
                if command == f'cd "Incoming";get "Movie (2024).mkv" "{destination.resolve()}"':
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(b"movie")
                    return {"status": "success", "stdout": ""}
                if command == 'del "Incoming/Movie (2024).mkv"':
                    return {"status": "success", "stdout": ""}
                return {"status": "error", "message": f"unexpected command: {command}"}

            run_smbclient_mock.side_effect = run_side_effect
            router = OperationStorageRouter(
                smb_connection_resolver=lambda connection_id: {
                    "id": connection_id,
                    "label": "NAS",
                    "host": "nas.local",
                    "username": "leo",
                    "password": "secret",
                }
            )
            plan = {
                "version": 1,
                "summary": {"move": 1, "delete": 0, "review": 0},
                "actions": [
                    {
                        "type": "move",
                        "source": str(source_root / "Movie (2024).mkv"),
                        "source_uri": "smb://nas-1/Media/Incoming/Movie%20%282024%29.mkv",
                        "destination": str(destination),
                        "destination_uri": "",
                        "reason": "canonicalize_best_media",
                        "media_key": "movie:movie:2024",
                        "root_path": str(source_root),
                        "root_storage_uri": "smb://nas-1/Media/Incoming",
                        "keep_path": str(destination),
                        "details": {},
                    }
                ],
            }

            result = apply_plan(plan, execute=True, prune_empty_dirs=True, storage_router=router)

            self.assertEqual(result["summary"]["applied"], 1)
            self.assertTrue(destination.exists())

    @patch("media_library_manager.operation_storage.run_smbclient_command")
    def test_move_folder_supports_local_source_to_smb_destination(self, run_smbclient_mock) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            source = tmp_path / "Downloads" / "Movie (2024)"
            movie_file = source / "Movie (2024).mkv"
            source.mkdir(parents=True)
            movie_file.write_bytes(b"movie")

            def run_side_effect(connection, command: str, *, timeout: int):  # noqa: ARG001
                if command == "ls":
                    return {"status": "success", "stdout": "Library|0|2026-04-04|10:00:00|D\n"}
                if command == 'cd "Library";ls':
                    return {"status": "success", "stdout": ""}
                if command == 'cd "Library";mkdir "Movie (2024)"':
                    return {"status": "success", "stdout": ""}
                if command == 'cd "Library/Movie (2024)";put "{}" "Movie (2024).mkv"'.format(movie_file.resolve()):
                    return {"status": "success", "stdout": ""}
                return {"status": "error", "message": f"unexpected command: {command}"}

            run_smbclient_mock.side_effect = run_side_effect
            router = OperationStorageRouter(
                smb_connection_resolver=lambda connection_id: {
                    "id": connection_id,
                    "label": "NAS",
                    "host": "nas.local",
                    "username": "leo",
                    "password": "secret",
                }
            )

            result = move_folder(source, "smb://nas-1/Media/Library", execute=True, storage_router=router)

            self.assertEqual(result["status"], "applied")
            self.assertFalse(source.exists())
            self.assertEqual(result["destination"], "smb://nas-1/Media/Library/Movie%20%282024%29")

    @patch("media_library_manager.operation_storage.run_smbclient_command")
    def test_apply_plan_supports_cross_backend_file_move(self, run_smbclient_mock) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            source_root = tmp_path / "Downloads"
            source_file = source_root / "Movie (2024).mkv"
            source_root.mkdir()
            source_file.write_bytes(b"movie")

            plan = {
                "version": 1,
                "summary": {"move": 1, "delete": 0, "review": 0},
                "actions": [
                    {
                        "type": "move",
                        "source": str(source_file),
                        "destination": "smb://nas-1/Media/Library/Movie%20%282024%29/Movie%20%282024%29.mkv",
                        "reason": "canonicalize_best_media",
                        "media_key": "movie:movie:2024",
                        "root_path": str(source_root),
                        "keep_path": "smb://nas-1/Media/Library/Movie%20%282024%29/Movie%20%282024%29.mkv",
                        "details": {},
                    }
                ],
            }

            def run_side_effect(connection, command: str, *, timeout: int):  # noqa: ARG001
                if command == "ls":
                    return {"status": "success", "stdout": "Library|0|2026-04-04|10:00:00|D\n"}
                if command == 'cd "Library/Movie (2024)";ls':
                    return {"status": "success", "stdout": ""}
                if command == 'cd "Library";mkdir "Movie (2024)"':
                    return {"status": "success", "stdout": ""}
                if command == 'cd "Library/Movie (2024)";put "{}" "Movie (2024).mkv"'.format(source_file.resolve()):
                    return {"status": "success", "stdout": ""}
                return {"status": "error", "message": f"unexpected command: {command}"}

            run_smbclient_mock.side_effect = run_side_effect
            router = OperationStorageRouter(
                smb_connection_resolver=lambda connection_id: {
                    "id": connection_id,
                    "label": "NAS",
                    "host": "nas.local",
                    "username": "leo",
                    "password": "secret",
                }
            )

            result = apply_plan(plan, execute=True, prune_empty_dirs=True, storage_router=router)

            self.assertEqual(result["summary"]["applied"], 1)
            self.assertFalse(source_file.exists())
