import unittest
from unittest.mock import patch

from media_library_manager.rclone_cli import run_rclone_command


class RcloneCliTests(unittest.TestCase):
    @patch("media_library_manager.rclone_cli.subprocess.run")
    def test_run_rclone_command_error_ignores_stdout_blob(self, run_mock) -> None:
        run_mock.return_value.returncode = 1
        run_mock.return_value.stdout = '[{"Path":"Movies","Name":"Movies"}]'
        run_mock.return_value.stderr = ""

        result = run_rclone_command(["lsjson", "remote:"], timeout=5)

        self.assertEqual(result.status, "error")
        self.assertEqual(result.message, "rclone command failed with exit code 1")

