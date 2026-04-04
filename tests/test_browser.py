import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_library_manager.browser import browse_path, parse_mount_line


class BrowserTests(unittest.TestCase):
    def test_parse_mount_line_detects_network_filesystem(self) -> None:
        mount = parse_mount_line("//admin@nas.local/Media on /Volumes/Media (smbfs, nodev, nosuid, mounted by admin)")
        self.assertIsNotNone(mount)
        assert mount is not None
        self.assertTrue(mount.is_network)
        self.assertEqual(str(mount.mount_point), "/Volumes/Media")
        self.assertEqual(mount.filesystem, "smbfs")

    def test_browse_path_lists_directories_first(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp_path = Path(raw_tmp)
            (tmp_path / "Series").mkdir()
            (tmp_path / "movie.mkv").write_bytes(b"video")

            with patch("media_library_manager.browser.list_mounts", return_value=[]):
                payload = browse_path(str(tmp_path))

            self.assertEqual(payload["path"], str(tmp_path.resolve()))
            self.assertEqual(payload["entries"][0]["type"], "directory")
            self.assertEqual(payload["entries"][1]["type"], "file")
