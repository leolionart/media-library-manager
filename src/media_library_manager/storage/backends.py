from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..lan_connections import build_cd_command, browse_smb_path, parse_smbclient_entries, resolve_smb_connection, run_smbclient_command
from .paths import StoragePath
from .rclone_cli import build_rclone_target, is_rclone_not_found_error, run_rclone, run_rclone_json


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


class RcloneStorageBackend:
    def __init__(self, *, timeout: int = 30, hash_timeout: int = 180):
        self.timeout = timeout
        self.hash_timeout = hash_timeout

    def exists(self, path: StoragePath) -> bool:
        if path.normalized_path() == "/":
            return True
        return self._stat(path) is not None

    def is_dir(self, path: StoragePath) -> bool:
        if path.normalized_path() == "/":
            return True
        entry = self._stat(path)
        return bool(entry and bool(entry.get("IsDir")))

    def is_file(self, path: StoragePath) -> bool:
        if path.normalized_path() == "/":
            return False
        entry = self._stat(path)
        return bool(entry and not bool(entry.get("IsDir")))

    def list_dir(self, path: StoragePath) -> list[StorageEntry]:
        target = self._target(path)
        try:
            payload = run_rclone_json(
                ["lsjson", target, "--no-mimetype"],
                timeout=self.timeout,
            )
        except Exception as exc:
            raise self._as_storage_error(exc) from exc

        if payload is None:
            return []
        if not isinstance(payload, list):
            raise StorageError("rclone lsjson returned unexpected payload type")

        rows = sorted(payload, key=lambda row: (not bool(row.get("IsDir")), str(row.get("Name") or "").lower()))
        entries: list[StorageEntry] = []
        for row in rows:
            name = str(row.get("Name") or "").strip()
            if not name or "/" in name:
                continue
            is_dir = bool(row.get("IsDir"))
            size_value = row.get("Size")
            size = int(size_value) if isinstance(size_value, (int, float, str)) and str(size_value).lstrip("-").isdigit() else None
            entries.append(
                StorageEntry(
                    path=path.join(name),
                    name=name,
                    entry_type="directory" if is_dir else "file",
                    size=size,
                    modified_at=str(row.get("ModTime") or ""),
                )
            )
        return entries

    def compute_sha256(self, path: StoragePath) -> str:
        if not self.exists(path):
            raise StorageNotFoundError(f"path does not exist: {path.to_uri()}")
        if not self.is_file(path):
            raise StorageError(f"path is not a file: {path.to_uri()}")

        digest = self._native_sha256(path)
        if digest:
            return digest
        return self._sha256_via_cat(path)

    def _stat(self, path: StoragePath) -> dict[str, Any] | None:
        target = self._target(path)
        try:
            payload = run_rclone_json(
                ["lsjson", target, "--stat", "--no-mimetype"],
                timeout=self.timeout,
            )
        except Exception as exc:
            if is_rclone_not_found_error(exc):
                return None
            raise self._as_storage_error(exc) from exc

        if payload is None:
            return None
        if isinstance(payload, list):
            if not payload:
                return None
            candidate = payload[0]
            if isinstance(candidate, dict):
                return candidate
            raise StorageError("rclone lsjson --stat returned unexpected payload")
        if isinstance(payload, dict):
            return payload
        raise StorageError("rclone lsjson --stat returned unexpected payload")

    def _native_sha256(self, path: StoragePath) -> str | None:
        target = self._target(path)
        try:
            result = run_rclone(
                ["hashsum", "SHA-256", target, "--max-depth", "0", "--files-only"],
                timeout=self.hash_timeout,
            )
        except Exception:
            return None

        for line in result.stdout.splitlines():
            tokens = line.strip().split()
            if not tokens:
                continue
            digest = tokens[0].strip().lower()
            if len(digest) == 64 and all(ch in "0123456789abcdef" for ch in digest):
                return digest
        return None

    def _sha256_via_cat(self, path: StoragePath) -> str:
        target = self._target(path)
        command = ["rclone", "cat", target]
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise StorageError("rclone command not found in PATH") from exc

        assert process.stdout is not None
        assert process.stderr is not None
        digest = hashlib.sha256()
        try:
            for chunk in iter(lambda: process.stdout.read(1024 * 1024), b""):
                digest.update(chunk)
            return_code = process.wait(timeout=self.hash_timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            raise StorageError(f"rclone cat timed out after {self.hash_timeout}s: {target}") from exc
        finally:
            process.stdout.close()

        stderr_text = (process.stderr.read() or b"").decode("utf-8", errors="replace").strip()
        process.stderr.close()
        if return_code != 0:
            message = stderr_text or f"rclone cat failed: {target}"
            raise StorageError(message)
        return digest.hexdigest()

    def _target(self, path: StoragePath) -> str:
        try:
            return build_rclone_target(remote=path.rclone_remote, path=path.normalized_path())
        except Exception as exc:
            raise self._as_storage_error(exc) from exc

    @staticmethod
    def _as_storage_error(exc: Exception) -> StorageError:
        if is_rclone_not_found_error(exc):
            return StorageNotFoundError(str(exc))
        return StorageError(str(exc))
