from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import parse_qs, quote, unquote, urlparse

from .lan_connections import (
    build_cd_command,
    join_share_path,
    normalize_share_path,
    normalize_stored_smb_connection,
    parent_share_path,
    parse_smbclient_entries,
    run_smbclient_command,
)
from .rclone_cli import RcloneCommandResult, RcloneError, build_rclone_target, run_rclone_command


SmbConnectionResolver = Callable[[str], dict[str, Any] | None]


@dataclass(frozen=True, slots=True)
class StoragePath:
    backend: str
    raw: str
    local_path: Path | None = None
    connection_id: str = ""
    share_name: str = ""
    share_path: str = "/"
    rclone_remote: str = ""
    rclone_path: str = "/"

    @property
    def name(self) -> str:
        if self.backend == "local":
            if self.local_path is None:
                return ""
            return self.local_path.name
        if self.backend == "rclone":
            normalized = OperationStorageRouter._normalize_rclone_path(self.rclone_path)
            if normalized in {"", "/"}:
                return self.rclone_remote
            return PurePosixPath(normalized).name
        if self.share_path in {"", "/"}:
            return self.share_name
        return Path(self.share_path).name


class OperationStorageRouter:
    def __init__(
        self,
        *,
        smb_connection_resolver: SmbConnectionResolver | None = None,
        smb_timeout: int = 20,
        rclone_timeout: int = 60,
    ) -> None:
        self.smb_connection_resolver = smb_connection_resolver
        self.smb_timeout = smb_timeout
        self.rclone_timeout = rclone_timeout
        self._rclone_entry_cache: dict[str, dict[str, Any] | None] = {}

    def parse_storage_path(self, value: str | Path | StoragePath) -> StoragePath:
        if isinstance(value, StoragePath):
            return value
        if isinstance(value, Path):
            resolved = value.expanduser().resolve()
            return StoragePath(backend="local", raw=str(value), local_path=resolved)

        text = str(value or "").strip()
        if text.startswith("rclone://"):
            parsed = urlparse(text)
            remote_name = unquote(parsed.netloc).strip()
            if not remote_name:
                raise ValueError(f"invalid rclone path (missing remote): {text}")
            return StoragePath(
                backend="rclone",
                raw=text,
                rclone_remote=remote_name,
                rclone_path=self._normalize_rclone_path(unquote(parsed.path or "/")),
            )
        if text.startswith("smb://"):
            parsed = urlparse(text)
            query = parse_qs(parsed.query)
            query_connection_id = unquote(query.get("connection_id", [""])[0]).strip()

            if query_connection_id:
                connection_id = query_connection_id
                share_name = unquote(parsed.netloc).strip().strip("/")
                if not share_name:
                    raise ValueError(f"invalid SMB path (missing share name): {text}")
                share_path = normalize_share_path(unquote(parsed.path or "/")) or "/"
            else:
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
        if path.backend == "rclone":
            # Remote names are mostly alphanumeric but can have dashes/underscores
            quoted_remote = quote(path.rclone_remote, safe="-_")
            normalized = self._normalize_rclone_path(path.rclone_path)
            if normalized in {"", "/"}:
                return f"rclone://{quoted_remote}/"
            
            # The path part should be quoted but we must KEEP the forward slashes (/) 
            # and other rclone-friendly characters unquoted.
            # Using quote(path, safe="/ ()!-_.") allows the full path to be reconstructed correctly.
            quoted_path = quote(normalized.lstrip("/"), safe="/ ()!-_.")
            return f"rclone://{quoted_remote}/{quoted_path}"
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
        if left.backend == "rclone":
            return left.rclone_remote == right.rclone_remote
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
        if candidate.backend == "rclone":
            ancestor_path = self._normalize_rclone_path(ancestor.rclone_path)
            candidate_path = self._normalize_rclone_path(candidate.rclone_path)
            if ancestor_path == "/":
                return True
            return candidate_path == ancestor_path or candidate_path.startswith(f"{ancestor_path}/")
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
        if parent.backend == "rclone":
            base = PurePosixPath(self._normalize_rclone_path(parent.rclone_path))
            joined = str(base.joinpath(clean_name))
            if not joined.startswith("/"):
                joined = f"/{joined}"
            return StoragePath(
                backend="rclone",
                raw=f"{parent.raw.rstrip('/')}/{clean_name}",
                rclone_remote=parent.rclone_remote,
                rclone_path=self._normalize_rclone_path(joined),
            )
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
        if path.backend == "rclone":
            current = PurePosixPath(self._normalize_rclone_path(path.rclone_path))
            if str(current) == "/":
                return None
            parent_text = str(current.parent)
            if not parent_text.startswith("/"):
                parent_text = f"/{parent_text}"
            return StoragePath(
                backend="rclone",
                raw=path.raw,
                rclone_remote=path.rclone_remote,
                rclone_path=self._normalize_rclone_path(parent_text),
            )
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
        if path.backend == "rclone":
            return self._rclone_entry(path) is not None
        return self._smb_entry(path) is not None

    def is_dir(self, path: StoragePath) -> bool:
        if path.backend == "local":
            assert path.local_path is not None
            return path.local_path.is_dir()
        if path.backend == "rclone":
            entry = self._rclone_entry(path)
            return bool(entry and bool(entry.get("IsDir")))
        if normalize_share_path(path.share_path) in {"", "/"}:
            return True
        entry = self._smb_entry(path)
        return bool(entry and entry.get("type") == "directory")

    def is_file(self, path: StoragePath) -> bool:
        if path.backend == "local":
            assert path.local_path is not None
            return path.local_path.is_file()
        if path.backend == "rclone":
            entry = self._rclone_entry(path)
            return bool(entry and not bool(entry.get("IsDir")))
        entry = self._smb_entry(path)
        return bool(entry and entry.get("type") == "file")

    def listdir(self, path: StoragePath) -> list[StoragePath]:
        if path.backend == "local":
            assert path.local_path is not None
            return sorted(
                [StoragePath(backend="local", raw=str(item), local_path=item) for item in path.local_path.iterdir()],
                key=lambda item: item.name.lower(),
            )
        if path.backend == "rclone":
            entries = self._rclone_list_entries(path)
            return [self.join(path, entry["Name"]) for entry in entries]
        entries = self._smb_list_entries(path)
        return [self.join(path, entry["name"]) for entry in entries]

    def mkdir_parents(self, path: StoragePath) -> None:
        if path.backend == "local":
            assert path.local_path is not None
            path.local_path.mkdir(parents=True, exist_ok=True)
            return
        if path.backend == "rclone":
            # Use build_rclone_target to ensure we have the correct remote:path format for CLI
            target = build_rclone_target(path.rclone_remote, path.rclone_path)
            result = self._run_rclone_command(["mkdir", target])
            if result.get("status") != "success":
                raise ValueError(str(result.get("message") or "rclone mkdir failed"))
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

    def copy_file(self, source: StoragePath, destination: StoragePath) -> None:
        if source.backend == "local" and destination.backend == "local":
            assert source.local_path is not None and destination.local_path is not None
            destination.local_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source.local_path, destination.local_path)
            return

        if source.backend == "local" and destination.backend == "smb":
            assert source.local_path is not None
            parent = self.parent(destination)
            if parent is None:
                raise ValueError("cannot upload to SMB share root")
            self.mkdir_parents(parent)
            command = (
                f'{build_cd_command(parent.share_path)}'
                f'put "{self._escape_command_value(str(source.local_path))}" "{self._escape_command_value(destination.name)}"'
            )
            self._run_smb_command(destination, command)
            return

        if source.backend == "smb" and destination.backend == "local":
            assert destination.local_path is not None
            destination.local_path.parent.mkdir(parents=True, exist_ok=True)
            self._download_smb_file(source, destination.local_path)
            return

        if source.backend == "smb" and destination.backend == "smb":
            with tempfile.NamedTemporaryFile(prefix="mlm-cross-backend-", delete=False) as handle:
                temp_path = Path(handle.name)
            try:
                self._download_smb_file(source, temp_path)
                self.copy_file(StoragePath(backend="local", raw=str(temp_path), local_path=temp_path), destination)
            finally:
                temp_path.unlink(missing_ok=True)
            return

        raise ValueError("unsupported storage backend copy")

    def rename(self, source: StoragePath, destination: StoragePath) -> None:
        if not self.same_backend_namespace(source, destination):
            raise ValueError("cross-backend move is not supported yet")

        if source.backend == "local":
            assert source.local_path is not None and destination.local_path is not None
            source.local_path.rename(destination.local_path)
            return
        if source.backend == "rclone":
            raise ValueError("rclone rename is not supported by this router yet")

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
        if path.backend == "rclone":
            self._ensure_not_rclone_root(path, "delete")
            target = build_rclone_target(path.rclone_remote, path.rclone_path)
            result = self._run_rclone_command(["deletefile", target])
            if result.get("status") != "success":
                raise ValueError(str(result.get("message") or "rclone deletefile failed"))
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
        if path.backend == "rclone":
            self._ensure_not_rclone_root(path, "delete")
            target = build_rclone_target(path.rclone_remote, path.rclone_path)
            result = self._run_rclone_command(["purge", target])
            if result.get("status") != "success":
                raise ValueError(str(result.get("message") or "rclone purge failed"))
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
        if path.backend == "rclone":
            if self._normalize_rclone_path(path.rclone_path) in {"", "/"}:
                return False
            result = self._try_run_rclone_command(["rmdir", build_rclone_target(path.rclone_remote, path.rclone_path)])
            return result.get("status") == "success"

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

    def _rclone_entry(self, path: StoragePath) -> dict[str, Any] | None:
        cache_key = self.stringify(path)
        if cache_key in self._rclone_entry_cache:
            return self._rclone_entry_cache[cache_key]

        normalized = self._normalize_rclone_path(path.rclone_path)
        if normalized in {"", "/"}:
            entry: dict[str, Any] | None = {"Name": path.rclone_remote, "IsDir": True}
            self._rclone_entry_cache[cache_key] = entry
            return entry

        # Probe the path directly to avoid expensive parent listing or missing entries
        payload = self._run_rclone_command(
            [
                "lsjson",
                build_rclone_target(path.rclone_remote, path.rclone_path),
            ],
            expect_json=True,
        ).get("payload")

        entry = None
        if isinstance(payload, list) and len(payload) > 0:
            entry = payload[0]
        
        self._rclone_entry_cache[cache_key] = entry
        return entry

    def _rclone_list_entries(self, path: StoragePath) -> list[dict[str, Any]]:
        if path.backend != "rclone":
            raise ValueError("rclone path is required")
        payload = self._run_rclone_command(
            [
                "lsjson",
                build_rclone_target(path.rclone_remote, path.rclone_path),
                "--max-depth",
                "1",
            ],
            expect_json=True,
        ).get("payload")
        if payload is None:
            return []
        if not isinstance(payload, list):
            raise ValueError("invalid rclone lsjson response: expected a list")
        entries = [item for item in payload if isinstance(item, dict) and isinstance(item.get("Name"), str)]
        return sorted(entries, key=lambda item: (not bool(item.get("IsDir")), str(item.get("Name")).lower()))

    def _download_smb_file(self, source: StoragePath, destination: Path) -> None:
        if source.share_path in {"", "/"}:
            raise ValueError("cannot download SMB share root")
        parent = self.parent(source)
        if parent is None:
            raise ValueError("cannot download SMB share root")
        command = (
            f'{build_cd_command(parent.share_path)}'
            f'get "{self._escape_command_value(source.name)}" "{self._escape_command_value(str(destination))}"'
        )
        self._run_smb_command(source, command)

    def _run_smb_command(self, path: StoragePath, command: str) -> dict[str, Any]:
        result = self._try_run_smb_command(path, command)
        if result.get("status") != "success":
            raise ValueError(str(result.get("message") or "SMB command failed"))
        return result

    def _try_run_smb_command(self, path: StoragePath, command: str) -> dict[str, Any]:
        connection = self._resolve_smb_connection(path)
        return run_smbclient_command(connection, command, timeout=self.smb_timeout)

    def _run_rclone_command(self, args: list[str], *, expect_json: bool = False) -> dict[str, Any]:
        result = self._try_run_rclone_command(args, expect_json=expect_json)
        if result.get("status") != "success":
            raise ValueError(str(result.get("message") or "rclone command failed"))
        return result

    def _try_run_rclone_command(self, args: list[str], *, expect_json: bool = False) -> dict[str, Any]:
        try:
            payload = run_rclone_command(args, timeout=self.rclone_timeout, expect_json=expect_json)
        except (RcloneError, ValueError) as exc:
            return {"status": "error", "message": str(exc)}
        if isinstance(payload, RcloneCommandResult):
            if payload.status != "success":
                return {"status": "error", "message": payload.message, "payload": payload}
            return {"status": "success", "payload": payload}
        return {
            "status": "success",
            "payload": payload,
        }

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

    @staticmethod
    def _normalize_rclone_path(value: str) -> str:
        text = str(value or "").strip()
        if not text or text == ".":
            return "/"
        return "/" + text.strip("/")

    @classmethod
    def _ensure_not_rclone_root(cls, path: StoragePath, action: str) -> None:
        if cls._normalize_rclone_path(path.rclone_path) in {"", "/"}:
            raise ValueError(f"cannot {action} rclone remote root")
