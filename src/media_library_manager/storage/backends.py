from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..lan_connections import build_cd_command, browse_smb_path, parse_smbclient_entries, resolve_smb_connection, run_smbclient_command
from .paths import StoragePath


class StorageError(RuntimeError):
    pass


class StorageNotFoundError(StorageError):
    pass


@dataclass(slots=True)
class StorageEntry:
    path: StoragePath
    name: str
    entry_type: str
    size: int | None = None
    modified_at: str = ""

    @property
    def is_dir(self) -> bool:
        return self.entry_type == "directory"

    @property
    def is_file(self) -> bool:
        return self.entry_type == "file"


class StorageBackend(Protocol):
    def exists(self, path: StoragePath) -> bool: ...
    def is_dir(self, path: StoragePath) -> bool: ...
    def is_file(self, path: StoragePath) -> bool: ...
    def list_dir(self, path: StoragePath) -> list[StorageEntry]: ...
    def compute_sha256(self, path: StoragePath) -> str: ...


class LocalStorageBackend:
    def exists(self, path: StoragePath) -> bool:
        return Path(path.normalized_path()).exists()

    def is_dir(self, path: StoragePath) -> bool:
        return Path(path.normalized_path()).is_dir()

    def is_file(self, path: StoragePath) -> bool:
        return Path(path.normalized_path()).is_file()

    def list_dir(self, path: StoragePath) -> list[StorageEntry]:
        base = Path(path.normalized_path())
        if not base.exists():
            raise StorageNotFoundError(f"path does not exist: {base}")
        if not base.is_dir():
            raise StorageError(f"path is not a directory: {base}")
        entries: list[StorageEntry] = []
        for child in sorted(base.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            stat = child.stat()
            entries.append(
                StorageEntry(
                    path=StoragePath.local(child),
                    name=child.name,
                    entry_type="directory" if child.is_dir() else "file",
                    size=stat.st_size,
                    modified_at=str(stat.st_mtime),
                )
            )
        return entries

    def compute_sha256(self, path: StoragePath) -> str:
        file_path = Path(path.normalized_path())
        if not file_path.exists():
            raise StorageNotFoundError(f"path does not exist: {file_path}")
        if not file_path.is_file():
            raise StorageError(f"path is not a file: {file_path}")
        return compute_local_sha256(file_path)


class SmbStorageBackend:
    def __init__(self, lan_connections: dict[str, Any]):
        self.lan_connections = lan_connections

    def exists(self, path: StoragePath) -> bool:
        if path.normalized_path() == "/":
            return True
        parent = path.parent()
        if parent is None:
            return True
        return any(entry.name == path.name() for entry in self.list_dir(parent))

    def is_dir(self, path: StoragePath) -> bool:
        if path.normalized_path() == "/":
            return True
        parent = path.parent()
        if parent is None:
            return True
        match = next((entry for entry in self.list_dir(parent) if entry.name == path.name()), None)
        return bool(match and match.is_dir)

    def is_file(self, path: StoragePath) -> bool:
        if path.normalized_path() == "/":
            return False
        parent = path.parent()
        if parent is None:
            return False
        match = next((entry for entry in self.list_dir(parent) if entry.name == path.name()), None)
        return bool(match and match.is_file)

    def list_dir(self, path: StoragePath) -> list[StorageEntry]:
        connection = resolve_smb_connection(self.lan_connections, path.connection_id)
        if connection is None:
            raise StorageNotFoundError(f"connection not found: {path.connection_id}")
        if path.normalized_path() == "/" and not path.share_name:
            result = browse_smb_path(connection, "/", share_name="")
            if result.get("status") != "success":
                raise StorageError(result.get("message", "SMB browse failed"))
            return [
                StorageEntry(
                    path=StoragePath.smb(connection_id=path.connection_id, share_name=entry["share_name"], path="/"),
                    name=entry["name"],
                    entry_type="directory",
                )
                for entry in result.get("entries", [])
            ]

        effective = {**connection, "share_name": path.share_name}
        command = build_smb_list_command(path)
        result = run_smbclient_command(effective, command, timeout=15)
        if result.get("status") != "success":
            raise StorageError(result.get("message", "SMB directory listing failed"))
        entries = parse_smbclient_entries(str(result.get("stdout") or ""))
        return [
            StorageEntry(
                path=path.join(entry["name"]),
                name=entry["name"],
                entry_type=entry["type"],
                size=int(entry["size"]) if str(entry.get("size") or "").isdigit() else None,
                modified_at=str(entry.get("modified_at") or ""),
            )
            for entry in entries
        ]

    def compute_sha256(self, path: StoragePath) -> str:
        normalized = path.normalized_path()
        if normalized in {"", "/"}:
            raise StorageError("path is not a file: SMB share root")

        parent = path.parent()
        if parent is None:
            raise StorageError("path is not a file: SMB share root")

        connection = resolve_smb_connection(self.lan_connections, path.connection_id)
        if connection is None:
            raise StorageNotFoundError(f"connection not found: {path.connection_id}")
        effective = {**connection, "share_name": path.share_name}

        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(prefix="mlm-smb-sha256-", delete=False) as handle:
                temp_file = handle.name
            command = f'{build_cd_command(parent.normalized_path())}get "{escape_smb_command_value(path.name())}" "{escape_smb_command_value(temp_file)}"'
            result = run_smbclient_command(effective, command, timeout=120)
            if result.get("status") != "success":
                raise StorageError(result.get("message", "SMB file download failed"))
            return compute_local_sha256(Path(temp_file))
        finally:
            if temp_file:
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass


def build_smb_list_command(path: StoragePath) -> str:
    normalized = path.normalized_path()
    if normalized in {"", "/"}:
        return "ls"
    return f'cd "{normalized.strip("/")}";ls'


def compute_local_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def escape_smb_command_value(value: str) -> str:
    return str(value).replace('"', '\\"')
