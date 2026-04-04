from __future__ import annotations

from typing import Any

from .backends import LocalStorageBackend, SmbStorageBackend, StorageBackend
from .paths import StoragePath


class StorageManager:
    def __init__(self, lan_connections: dict[str, Any] | None = None):
        self.local = LocalStorageBackend()
        self.smb = SmbStorageBackend(lan_connections or {"smb": []})

    def backend_for(self, path: StoragePath) -> StorageBackend:
        if path.backend == "local":
            return self.local
        if path.backend == "smb":
            return self.smb
        raise ValueError(f"unsupported storage backend: {path.backend}")

    def exists(self, path: StoragePath) -> bool:
        return self.backend_for(path).exists(path)

    def is_dir(self, path: StoragePath) -> bool:
        return self.backend_for(path).is_dir(path)

    def is_file(self, path: StoragePath) -> bool:
        return self.backend_for(path).is_file(path)

    def list_dir(self, path: StoragePath):
        return self.backend_for(path).list_dir(path)

    def compute_sha256(self, path: StoragePath) -> str:
        return self.backend_for(path).compute_sha256(path)


def default_storage_manager(*, lan_connections: dict[str, Any] | None = None) -> StorageManager:
    return StorageManager(lan_connections=lan_connections)
