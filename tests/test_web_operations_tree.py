import unittest
from pathlib import Path
from unittest.mock import patch

from media_library_manager.models import RootConfig
from media_library_manager.storage import StorageEntry, StoragePath
from media_library_manager.web import build_operations_folder_tree


class FakeStorageManager:
    def __init__(self, mapping: dict[str, list[StorageEntry]]):
        self.mapping = mapping

    def list_dir(self, path: StoragePath):
        return self.mapping.get(path.to_uri(), [])


class WebOperationsTreeTests(unittest.TestCase):
    @patch("media_library_manager.web.default_storage_manager")
    def test_build_operations_folder_tree_returns_nested_children(self, default_storage_manager_mock) -> None:
        root = RootConfig(
            path=Path("/smb/smb-1/DATA"),
            label="DATA",
            storage_uri="smb://DATA/?connection_id=smb-1",
            connection_id="smb-1",
            connection_label="NAS",
            share_name="DATA",
        )
        movies = StoragePath.smb(connection_id="smb-1", share_name="DATA", path="/Movies")
        dune = StoragePath.smb(connection_id="smb-1", share_name="DATA", path="/Movies/Dune (2021)")
        series = StoragePath.smb(connection_id="smb-1", share_name="DATA", path="/Series")
        mapping = {
            "smb://DATA/?connection_id=smb-1": [
                StorageEntry(path=movies, name="Movies", entry_type="directory"),
                StorageEntry(path=series, name="Series", entry_type="directory"),
            ],
            "smb://DATA/Movies?connection_id=smb-1": [
                StorageEntry(path=dune, name="Dune (2021)", entry_type="directory"),
            ],
            "smb://DATA/Movies/Dune%20%282021%29?connection_id=smb-1": [],
            "smb://DATA/Series?connection_id=smb-1": [],
        }
        default_storage_manager_mock.return_value = FakeStorageManager(mapping)

        payload = build_operations_folder_tree([root], {"smb": []}, max_depth=3)

        self.assertEqual(payload["summary"]["roots"], 1)
        self.assertEqual(payload["summary"]["nodes"], 3)
        self.assertEqual(len(payload["items"]), 1)
        root_node = payload["items"][0]
        self.assertTrue(root_node["has_children"])
        self.assertEqual(root_node["children"][0]["label"], "Movies")
        self.assertEqual(root_node["children"][0]["children"][0]["label"], "Dune (2021)")
        self.assertEqual(root_node["children"][0]["children"][0]["display_path"], "Movies/Dune (2021)")

    @patch("media_library_manager.web.default_storage_manager")
    def test_build_operations_folder_tree_respects_depth_limit(self, default_storage_manager_mock) -> None:
        root = RootConfig(
            path=Path("/smb/smb-1/DATA"),
            label="DATA",
            storage_uri="smb://DATA/?connection_id=smb-1",
            connection_id="smb-1",
            connection_label="NAS",
            share_name="DATA",
        )
        movies = StoragePath.smb(connection_id="smb-1", share_name="DATA", path="/Movies")
        dune = StoragePath.smb(connection_id="smb-1", share_name="DATA", path="/Movies/Dune (2021)")
        mapping = {
            "smb://DATA/?connection_id=smb-1": [
                StorageEntry(path=movies, name="Movies", entry_type="directory"),
            ],
            "smb://DATA/Movies?connection_id=smb-1": [
                StorageEntry(path=dune, name="Dune (2021)", entry_type="directory"),
            ],
        }
        default_storage_manager_mock.return_value = FakeStorageManager(mapping)

        payload = build_operations_folder_tree([root], {"smb": []}, max_depth=1)

        root_node = payload["items"][0]
        self.assertEqual(len(root_node["children"]), 1)
        self.assertEqual(root_node["children"][0]["label"], "Movies")
        self.assertEqual(root_node["children"][0]["children"], [])
        self.assertFalse(root_node["children"][0]["has_children"])
