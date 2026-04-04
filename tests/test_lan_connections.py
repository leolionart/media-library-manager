import unittest
from unittest.mock import patch

from media_library_manager.lan_connections import (
    browse_smb_path,
    create_smb_directory,
    delete_smb_directory,
    redact_lan_connections,
    resolve_smb_connection_for_test,
    test_smb_connection,
    upsert_smb_connection,
)


class CompletedProcess:
    def __init__(self, *, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class LanConnectionTests(unittest.TestCase):
    def test_upsert_connection_preserves_existing_password_when_omitted(self) -> None:
        connections = {
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
        updated_connections, saved = upsert_smb_connection(
            connections,
            {"id": "smb-1", "label": "NAS Updated", "host": "nas.local", "share_name": "Media", "username": "leo"},
        )
        self.assertEqual(saved["password"], "secret")
        self.assertEqual(updated_connections["smb"][0]["label"], "NAS Updated")

    def test_redact_connections_hides_password(self) -> None:
        payload = redact_lan_connections(
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
        self.assertEqual(payload["smb"][0]["password"], "")
        self.assertTrue(payload["smb"][0]["has_password"])

    def test_resolve_connection_for_test_uses_stored_password(self) -> None:
        resolved = resolve_smb_connection_for_test(
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
            },
            {"id": "smb-1"},
        )
        self.assertEqual(resolved["password"], "secret")

    @patch("media_library_manager.lan_connections.subprocess.run")
    def test_test_smb_connection_lists_shares(self, run_mock) -> None:
        run_mock.return_value = CompletedProcess(
            returncode=0,
            stdout="Disk|Media|Main media share\nDisk|Movies|Movie library\n",
        )
        result = test_smb_connection(
            {
                "host": "nas.local",
                "username": "leo",
                "password": "secret",
            }
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["shares"][0]["name"], "Media")

    @patch("media_library_manager.lan_connections.subprocess.run", side_effect=FileNotFoundError)
    def test_test_smb_connection_handles_missing_smbclient(self, _run_mock) -> None:
        result = test_smb_connection(
            {
                "host": "nas.local",
                "username": "leo",
                "password": "secret",
            }
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("smbclient", result["message"])

    @patch("media_library_manager.lan_connections.subprocess.run")
    def test_browse_smb_path_lists_directories(self, run_mock) -> None:
        run_mock.return_value = CompletedProcess(
            returncode=0,
            stdout="Movies|0|2026-04-04|10:00:00|D\nREADME.txt|12|2026-04-04|10:00:00|A\n",
        )
        result = browse_smb_path(
            {
                "id": "smb-1",
                "label": "NAS",
                "host": "nas.local",
                "share_name": "Media",
                "base_path": "/library",
                "username": "leo",
                "password": "secret",
            }
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["entries"][0]["path"], "/library/Movies")

    @patch("media_library_manager.lan_connections.subprocess.run")
    def test_create_and_delete_smb_directory_use_smbclient(self, run_mock) -> None:
        run_mock.return_value = CompletedProcess(returncode=0, stdout="")
        connection = {
            "id": "smb-1",
            "label": "NAS",
            "host": "nas.local",
            "share_name": "Media",
            "username": "leo",
            "password": "secret",
        }

        created = create_smb_directory(connection, "/library", "Movies")
        deleted = delete_smb_directory(connection, "/library/Movies")

        self.assertEqual(created["status"], "success")
        self.assertEqual(created["path"], "/library/Movies")
        self.assertEqual(deleted["status"], "success")
        self.assertEqual(deleted["parent"], "/library")
