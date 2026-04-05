import tempfile
import unittest
from pathlib import Path

from media_library_manager.models import LibraryTargets, RootConfig
from media_library_manager.state import StateStore


class StateStoreTests(unittest.TestCase):
    def test_state_store_can_clear_saved_plan(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            store = StateStore(tmp_path / "state" / "app-state.json")
            store.save_plan({"generated_at": "2026-04-04T00:30:00+00:00", "summary": {"move": 1}, "actions": [{"type": "move"}]})

            self.assertIsNotNone(store.load_plan())

            store.clear_plan()

            self.assertIsNone(store.load_plan())
            self.assertIsNone(store.api_payload()["plan"])

    def test_state_store_persists_roots_targets_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            store = StateStore(tmp_path / "state" / "app-state.json")
            store.add_root(RootConfig(path=tmp_path, label="Local", priority=90, kind="movie"))
            store.add_root(
                RootConfig(
                    path=tmp_path / "MountedNAS",
                    label="NAS Movies",
                    priority=70,
                    kind="movie",
                    connection_id="smb-1",
                    connection_label="NAS",
                )
            )
            store.save_targets(LibraryTargets(movie_root=tmp_path / "Movies"))
            store.save_integrations(
                {
                    "radarr": {"enabled": True, "base_url": "http://radarr.local:7878", "api_key": "abc", "root_folder_path": "/movies"},
                    "sonarr": {"enabled": False, "base_url": "", "api_key": "", "root_folder_path": ""},
                    "sync_options": {"sync_after_apply": True, "rescan_after_update": True, "create_root_folder_if_missing": True},
                }
            )
            store.save_lan_connections(
                {
                    "smb": [
                        {
                            "id": "smb-1",
                            "label": "NAS",
                            "host": "nas.local",
                            "share_name": "Media",
                            "username": "leo",
                            "password": "secret",
                        }
                    ]
                }
            )
            store.add_managed_folder(
                {
                    "connection_id": "smb-1",
                    "connection_label": "NAS",
                    "share_name": "Media",
                    "path": "/Movies",
                }
            )
            store.save_report({"generated_at": "2026-04-04T00:00:00+00:00", "summary": {"files": 1}})
            store.save_apply_result({"generated_at": "2026-04-04T01:00:00+00:00", "summary": {"applied": 0}})
            store.save_sync_result({"generated_at": "2026-04-04T01:30:00+00:00", "summary": {"updated": 1}})

            payload = store.api_payload()
            self.assertEqual(payload["roots"][0]["label"], "Local")
            self.assertEqual(payload["roots"][1]["connection_id"], "smb-1")
            self.assertEqual(payload["roots"][1]["connection_label"], "NAS")
            self.assertEqual(payload["targets"]["movie_root"], str(tmp_path / "Movies"))
            self.assertTrue(payload["integrations"]["radarr"]["enabled"])
            self.assertEqual(payload["lan_connections"]["smb"][0]["label"], "NAS")
            self.assertTrue(payload["lan_connections"]["smb"][0]["has_password"])
            self.assertEqual(payload["lan_connections"]["smb"][0]["password"], "")
            self.assertEqual(payload["managed_folders"][0]["path"], "/Movies")
            self.assertEqual(payload["report"]["summary"]["files"], 1)
            self.assertEqual(payload["apply_result"]["summary"]["applied"], 0)
            self.assertEqual(payload["sync_result"]["summary"]["updated"], 1)

    def test_state_store_persists_job_cancel_request(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            store = StateStore(tmp_path / "state" / "app-state.json")
            store.start_job(kind="scan", message="Started library scan.")

            job = store.request_job_cancel()

            self.assertIsNotNone(job)
            assert job is not None
            self.assertTrue(job["cancel_requested"])
            self.assertTrue(store.is_current_job_cancel_requested())
            self.assertIn("Cancellation requested", job["message"])
            self.assertEqual(store.load_current_job()["logs"][-1]["message"], "Cancellation requested by user.")

    def test_state_store_derives_retry_resume_wait_actions_from_job_details(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            store = StateStore(tmp_path / "state" / "app-state.json")
            store.start_job(
                kind="scan",
                message="Started library scan.",
                details={"retryable": True, "resumable": True, "resume_state": {"next_root_index": 2}},
            )

            store.finish_job(
                status="error",
                message="Scan failed.",
                details={"retryable": True, "resumable": True, "resume_state": {"next_root_index": 2}},
            )
            job = store.load_current_job()

            self.assertTrue(job["available_actions"]["retry"])
            self.assertTrue(job["available_actions"]["resume"])
            self.assertTrue(job["available_actions"]["wait"])

    def test_state_store_can_defer_retryable_job(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            store = StateStore(tmp_path / "state" / "app-state.json")
            store.start_job(
                kind="cleanup-scan",
                message="Started duplicate empty-folder cleanup scan.",
                details={
                    "retryable": True,
                    "resumable": True,
                    "resume_state": {"action": "empty-folder-cleanup-scan", "payload": {}, "attempt": 1},
                    "job_control": {
                        "action": "empty-folder-cleanup-scan",
                        "payload": {},
                        "attempt": 1,
                        "can_retry": True,
                        "can_resume": True,
                        "can_wait": True,
                    },
                },
            )
            store.finish_job(
                status="error",
                message="Duplicate empty-folder cleanup scan failed.",
                details={
                    "retryable": True,
                    "resumable": True,
                    "resume_state": {"action": "empty-folder-cleanup-scan", "payload": {}, "attempt": 1},
                    "job_control": {
                        "action": "empty-folder-cleanup-scan",
                        "payload": {},
                        "attempt": 1,
                        "can_retry": True,
                        "can_resume": True,
                        "can_wait": True,
                    },
                },
            )

            job = store.request_job_wait(wait_seconds=90)

            self.assertIsNotNone(job)
            assert job is not None
            self.assertEqual(job["status"], "waiting")
            self.assertTrue(job["available_actions"]["retry"])
            self.assertTrue(job["available_actions"]["resume"])
            self.assertIn("Retry deferred", job["message"])
            self.assertEqual(store.load_current_job()["logs"][-1]["message"], "Retry deferred for 90s.")

    def test_state_store_updates_existing_root_by_original_path(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            store = StateStore(tmp_path / "state" / "app-state.json")
            original_root = tmp_path / "Incoming"
            updated_root = tmp_path / "Processed"
            original_root.mkdir()
            updated_root.mkdir()

            store.add_root(RootConfig(path=original_root, label="Incoming", priority=50, kind="mixed"))
            store.update_root(
                original_root,
                RootConfig(path=updated_root, label="Processed", priority=90, kind="movie"),
            )

            roots = store.list_roots()
            self.assertEqual(len(roots), 1)
            self.assertEqual(roots[0].path, updated_root)
            self.assertEqual(roots[0].label, "Processed")
            self.assertEqual(roots[0].priority, 90)

    def test_state_store_persists_empty_folder_cleanup_report_separately(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            store = StateStore(tmp_path / "state" / "app-state.json")

            store.save_cleanup_report({"generated_at": "2026-04-05T00:00:00+00:00", "summary": {"groups": 1}})
            store.save_empty_folder_cleanup_report(
                {
                    "generated_at": "2026-04-05T00:10:00+00:00",
                    "summary": {"duplicate_groups": 2, "deletion_candidates": 3},
                    "groups": [],
                }
            )

            payload = store.api_payload()
            self.assertEqual(payload["cleanup_report"]["summary"]["groups"], 1)
            self.assertEqual(payload["empty_folder_cleanup_report"]["summary"]["duplicate_groups"], 2)
            self.assertEqual(payload["last_cleanup_at"], "2026-04-05T00:00:00+00:00")
            self.assertEqual(payload["last_empty_folder_cleanup_at"], "2026-04-05T00:10:00+00:00")
