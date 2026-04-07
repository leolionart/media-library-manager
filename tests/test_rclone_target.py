import unittest
from media_library_manager.rclone_cli import build_rclone_target


class RcloneTargetTests(unittest.TestCase):
    def test_build_rclone_target_simple(self) -> None:
        self.assertEqual(build_rclone_target("remote", "path/to/file"), "remote:path/to/file")

    def test_build_rclone_target_with_colon_in_path(self) -> None:
        # Path with colon should be prefixed with ./ to avoid being mistaken for a remote
        self.assertEqual(build_rclone_target("remote", "path/with:colon.mkv"), "remote:./path/with:colon.mkv")

    def test_build_rclone_target_remote_only(self) -> None:
        self.assertEqual(build_rclone_target("remote", ""), "remote:")
        self.assertEqual(build_rclone_target("remote", "/"), "remote:")

    def test_build_rclone_target_strip_slashes(self) -> None:
        self.assertEqual(build_rclone_target("remote", "/path/to/file/"), "remote:path/to/file")

    def test_build_rclone_target_invalid_remote(self) -> None:
        with self.assertRaises(ValueError):
            build_rclone_target("", "path")


if __name__ == "__main__":
    unittest.main()
