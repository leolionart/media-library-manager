from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, unquote, urlparse

from .lan_connections import (
    build_cd_command,
    join_share_path,
    normalize_share_path,
    normalize_stored_smb_connection,
    parent_share_path,
    parse_smbclient_entries,
    run_smbclient_command,
)


SmbConnectionResolver = Callable[[str], dict[str, Any] | None]


@dataclass(frozen=True, slots=True)
class StoragePath:
    backend: str
    raw: str
    local_path: Path | None = None
    connection_id: str = ""
    share_name: str = ""
    share_path: str = "/"

    @property
    def name(self) -> str:
        if self.backend == "local":
            if self.local_path is None:
                return ""
            return self.local_path.name
        if self.share_path in {"", "/"}:
            return self.share_name
        return Path(self.share_path).name


class OperationStorageRouter:
    def __init__(self, *, smb_connection_resolver: SmbConnectionResolver | None = None, smb_timeout: int = 20) -> None:
        self.smb_connection_resolver = smb_connection_resolver
        self.smb_timeout = smb_timeout

    def parse_storage_path(self, value: str | Path | StoragePath) -> StoragePath:
        if isinstance(value, StoragePath):
            return value
        if isinstance(value, Path):
            resolved = value.expanduser().resolve()
            return StoragePath(backend="local", raw=str(value), local_path=resolved)

        text = str(value or "").strip()
        if text.startswith("smb://"):
            parsed = urlparse(text)
            connection_id = unquote(parsed.netloc).strip()
            if not connection_id:
                raise ValueError(f"invalid SMB path (missing connection id): {text}")
            parts = [unquote(part) for part in parsed.path.split("/") if part]
            if not parts:
                raise ValueError(f"invalid SMB path (missing share name): {text}")
            share_name = parts[0].strip().strip("/")
            if not share_name:
                raise ValueError(f"invalid SMB path (missing share name): {text}")
            share_path = normalize_share_path("/".join(parts[1:])) or "/"
            return StoragePath(
                backend="smb",
                raw=text,
                connection_id=connection_id,
                share_name=share_name,
                share_path=share_path,
            )

        resolved = Path(text).expanduser().resolve()
        return StoragePath(backend="local", raw=text, local_path=resolved)

    def stringify(self, path: StoragePath) -> str:
        if path.backend == "local":
            return str(path.local_path or "")
        quoted_connection = quote(path.connection_id, safe="")
        quoted_share = quote(path.share_name, safe="")
        suffix = ""
        if path.share_path not in {"", "/"}:
            suffix = "/" + "/".join(quote(part, safe="") for part in path.share_path.strip("/").split("/"))
        return f"smb://{quoted_connection}/{quoted_share}{suffix}"

    def same_backend_namespace(self, left: StoragePath, right: StoragePath) -> bool:
        if left.backend != right.backend:
            return False
        if left.backend == "local":
            return True
        return left.connection_id == right.connection_id and left.share_name == right.share_name

    def is_relative_to(self, candidate: StoragePath, ancestor: StoragePath) -> bool:
        if not self.same_backend_namespace(candidate, ancestor):
            return False
        if candidate.backend == "local":
            assert candidate.local_path is not None and ancestor.local_path is not None
            try:
                candidate.local_path.relative_to(ancestor.local_path)
                return True
            except ValueError:
                return False
        ancestor_path = normalize_share_path(ancestor.share_path) or "/"
        candidate_path = normalize_share_path(candidate.share_path) or "/"
        if ancestor_path == "/":
            return True
        return candidate_path == ancestor_path or candidate_path.startswith(f"{ancestor_path}/")

    def join(self, parent: StoragePath, name: str) -> StoragePath:
        clean_name = str(name or "").strip().strip("/")
        if not clean_name:
            raise ValueError("name is required")
        if parent.backend == "local":
            assert parent.local_path is not None
            return StoragePath(backend="local", raw=str(parent.local_path / clean_name), local_path=(parent.local_path / clean_name))
        return StoragePath(
            backend="smb",
            raw=f"{parent.raw.rstrip('/')}/{clean_name}",
            connection_id=parent.connection_id,
            share_name=parent.share_name,
            share_path=join_share_path(parent.share_path, clean_name),
        )

    def parent(self, path: StoragePath) -> StoragePath | None:
        if path.backend == "local":
            assert path.local_path is not None
            parent = path.local_path.parent
            if parent == path.local_path:
                return None
            return StoragePath(backend="local", raw=str(parent), local_path=parent)
        parent_path = parent_share_path(path.share_path)
        if parent_path is None:
            return None
        return StoragePath(
            backend="smb",
            raw=path.raw,
            connection_id=path.connection_id,
            share_name=path.share_name,
            share_path=parent_path,
        )

    def exists(self, path: StoragePath) -> bool:
        if path.backend == "local":
            assert path.local_path is not None
            return path.local_path.exists()
        return self._smb_entry(path) is not None

    def is_dir(self, path: StoragePath) -> bool:
        if path.backend == "local":
            assert path.local_path is not None
            return path.local_path.is_dir()
        if normalize_share_path(path.share_path) in {"", "/"}:
            return True
        entry = self._smb_entry(path)
        return bool(entry and entry.get("type") == "directory")

    def is_file(self, path: StoragePath) -> bool:
        if path.backend == "local":
            assert path.local_path is not None
            return path.local_path.is_file()
        entry = self._smb_entry(path)
        return bool(entry and entry.get("type") == "file")

    def listdir(self, path: StoragePath) -> list[StoragePath]:
        if path.backend == "local":
            assert path.local_path is not None
            return sorted(
                [StoragePath(backend="local", raw=str(item), local_path=item) for item in path.local_path.iterdir()],
                key=lambda item: item.name.lower(),
            )
        entries = self._smb_list_entries(path)
        return [self.join(path, entry["name"]) for entry in entries]

    def mkdir_parents(self, path: StoragePath) -> None:
        if path.backend == "local":
            assert path.local_path is not None
            path.local_path.mkdir(parents=True, exist_ok=True)
            return
        if path.share_path in {"", "/"}:
            return
        segments = [part for part in path.share_path.strip("/").split("/") if part]
        current = "/"
        for segment in segments:
            next_path = join_share_path(current, segment)
            ref = StoragePath(
                backend="smb",
                raw=path.raw,
                connection_id=path.connection_id,
                share_name=path.share_name,
                share_path=next_path,
            )
            if self.is_dir(ref):
                current = next_path
                continue
            parent = parent_share_path(next_path) or "/"
            command = f'{build_cd_command(parent)}mkdir "{self._escape_command_value(segment)}"'
            self._run_smb_command(path, command)
            current = next_path

    def rename(self, source: StoragePath, destination: StoragePath) -> None:
        if not self.same_backend_namespace(source, destination):
            raise ValueError("cross-backend move is not supported yet")

        if source.backend == "local":
            assert source.local_path is not None and destination.local_path is not None
            source.local_path.rename(destination.local_path)
            return

        if source.share_path in {"", "/"}:
            raise ValueError("cannot rename SMB share root")

        source_rel = source.share_path.strip("/")
        destination_rel = destination.share_path.strip("/")
        command = f'rename "{self._escape_command_value(source_rel)}" "{self._escape_command_value(destination_rel)}"'
        self._run_smb_command(source, command)

    def delete_file(self, path: StoragePath) -> None:
        if path.backend == "local":
            assert path.local_path is not None
            path.local_path.unlink()
            return
        if path.share_path in {"", "/"}:
            raise ValueError("cannot delete SMB share root")
        rel_path = path.share_path.strip("/")
        command = f'del "{self._escape_command_value(rel_path)}"'
        self._run_smb_command(path, command)

    def delete_tree(self, path: StoragePath) -> None:
        if path.backend == "local":
            assert path.local_path is not None
            shutil.rmtree(path.local_path)
            return
        if path.share_path in {"", "/"}:
            raise ValueError("cannot delete SMB share root")
        rel_path = path.share_path.strip("/")
        command = f'recurse ON;prompt OFF;deltree "{self._escape_command_value(rel_path)}"'
        self._run_smb_command(path, command)

    def remove_dir_if_empty(self, path: StoragePath) -> bool:
        if path.backend == "local":
            assert path.local_path is not None
            try:
                path.local_path.rmdir()
                return True
            except OSError:
                return False

        if path.share_path in {"", "/"}:
            return False
        parent = parent_share_path(path.share_path) or "/"
        folder_name = path.name
        command = f'{build_cd_command(parent)}rmdir "{self._escape_command_value(folder_name)}"'
        result = self._try_run_smb_command(path, command)
        return result.get("status") == "success"

    def _smb_entry(self, path: StoragePath) -> dict[str, str] | None:
        if normalize_share_path(path.share_path) in {"", "/"}:
            return {"name": path.share_name, "type": "directory"}
        parent = self.parent(path)
        if parent is None:
            return None
        target_name = path.name
        for entry in self._smb_list_entries(parent):
            if entry.get("name") == target_name:
                return entry
        return None

    def _smb_list_entries(self, path: StoragePath) -> list[dict[str, str]]:
        command = f"{build_cd_command(path.share_path)}ls"
        result = self._run_smb_command(path, command)
        return parse_smbclient_entries(str(result.get("stdout") or ""))

    def _run_smb_command(self, path: StoragePath, command: str) -> dict[str, Any]:
        result = self._try_run_smb_command(path, command)
        if result.get("status") != "success":
            raise ValueError(str(result.get("message") or "SMB command failed"))
        return result

    def _try_run_smb_command(self, path: StoragePath, command: str) -> dict[str, Any]:
        connection = self._resolve_smb_connection(path)
        return run_smbclient_command(connection, command, timeout=self.smb_timeout)

    def _resolve_smb_connection(self, path: StoragePath) -> dict[str, Any]:
        if self.smb_connection_resolver is None:
            raise ValueError("SMB operation requires a connection resolver")
        base = self.smb_connection_resolver(path.connection_id)
        if base is None:
            raise ValueError(f"SMB connection not found: {path.connection_id}")
        normalized = normalize_stored_smb_connection(base)
        normalized["id"] = path.connection_id
        normalized["share_name"] = path.share_name
        if not normalized.get("host"):
            raise ValueError(f"SMB connection host is missing for {path.connection_id}")
        if not normalized.get("username"):
            raise ValueError(f"SMB connection username is missing for {path.connection_id}")
        return normalized

    @staticmethod
    def _escape_command_value(value: str) -> str:
        return str(value).replace('"', '\\"')
