from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Protocol

from .models import RootConfig

try:
    from .storage import StorageManager, StoragePath
except Exception:  # pragma: no cover - graceful fallback if storage package is unavailable
    StorageManager = None  # type: ignore[assignment]
    StoragePath = None  # type: ignore[assignment]


@dataclass(slots=True)
class ScannedFileEntry:
    path: str
    relative_path: str
    size: int
    stem: str
    suffix: str
    parent_name: str


class ScannerStorageBackend(Protocol):
    def iter_video_files(self, root: RootConfig, *, allowed_suffixes: set[str]) -> Iterable[ScannedFileEntry]:
        ...

    def compute_sha256(self, entry: ScannedFileEntry) -> str:
        ...


class LocalPathScannerStorage:
    DIRECTORY_PROGRESS_INTERVAL = 1

    def iter_video_files(self, root: RootConfig, *, allowed_suffixes: set[str]) -> Iterable[ScannedFileEntry]:
        yield from self.iter_video_files_with_progress(root, allowed_suffixes=allowed_suffixes)

    def iter_video_files_with_progress(
        self,
        root: RootConfig,
        *,
        allowed_suffixes: set[str],
        progress_callback: Callable[[dict[str, object]], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> Iterable[ScannedFileEntry]:
        root_path = Path(root.path)
        pending = [root_path]
        directories_scanned = 0

        while pending:
            if should_cancel and should_cancel():
                raise RuntimeError("job cancelled")
            current = pending.pop()
            directories_scanned += 1
            if progress_callback and (directories_scanned == 1 or directories_scanned % self.DIRECTORY_PROGRESS_INTERVAL == 0):
                progress_callback(
                    {
                        "event": "directory_scanned",
                        "directory_path": str(current),
                        "directories_scanned": directories_scanned,
                    }
                )
            try:
                entries = sorted(current.iterdir(), key=lambda entry: entry.name.lower(), reverse=True)
            except (FileNotFoundError, NotADirectoryError, PermissionError):
                continue
            for entry in entries:
                if should_cancel and should_cancel():
                    raise RuntimeError("job cancelled")
                if entry.is_dir():
                    pending.append(entry)
                    continue
                suffix = entry.suffix.lower()
                if suffix not in allowed_suffixes:
                    continue
                stat = entry.stat()
                yield ScannedFileEntry(
                    path=str(entry.resolve()),
                    relative_path=str(entry.relative_to(root_path)),
                    size=stat.st_size,
                    stem=entry.stem,
                    suffix=suffix,
                    parent_name=entry.parent.name,
                )

    def compute_sha256(self, entry: ScannedFileEntry) -> str:
        digest = hashlib.sha256()
        with Path(entry.path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


class StorageManagerScannerStorage:
    DIRECTORY_PROGRESS_INTERVAL = 1

    def __init__(
        self,
        manager: "StorageManager",
        *,
        smb_sha256: Callable[["StoragePath"], str] | None = None,
    ):
        if StorageManager is None or StoragePath is None:
            raise RuntimeError("storage module is not available")
        self.manager = manager
        self.smb_sha256 = smb_sha256

    def iter_video_files(self, root: RootConfig, *, allowed_suffixes: set[str]) -> Iterable[ScannedFileEntry]:
        yield from self.iter_video_files_with_progress(root, allowed_suffixes=allowed_suffixes)

    def iter_video_files_with_progress(
        self,
        root: RootConfig,
        *,
        allowed_suffixes: set[str],
        progress_callback: Callable[[dict[str, object]], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> Iterable[ScannedFileEntry]:
        root_path = self._root_to_storage_path(root)
        pending = [root_path]
        directories_scanned = 0
        while pending:
            if should_cancel and should_cancel():
                raise RuntimeError("job cancelled")
            current = pending.pop()
            directories_scanned += 1
            if progress_callback and (directories_scanned == 1 or directories_scanned % self.DIRECTORY_PROGRESS_INTERVAL == 0):
                progress_callback(
                    {
                        "event": "directory_scanned",
                        "directory_path": current.normalized_path() if current.backend == "local" else current.to_uri(),
                        "directories_scanned": directories_scanned,
                    }
                )
            entries = self.manager.list_dir(current)
            for entry in entries:
                if should_cancel and should_cancel():
                    raise RuntimeError("job cancelled")
                if entry.is_dir:
                    pending.append(entry.path)
                    continue
                suffix = entry.path.suffix().lower()
                if suffix not in allowed_suffixes:
                    continue
                parent = entry.path.parent()
                entry_path = entry.path.normalized_path() if entry.path.backend == "local" else entry.path.to_uri()
                yield ScannedFileEntry(
                    path=entry_path,
                    relative_path=entry.path.relative_to(root_path),
                    size=entry.size or 0,
                    stem=Path(entry.name).stem,
                    suffix=suffix,
                    parent_name=parent.name() if parent else "",
                )

    def compute_sha256(self, entry: ScannedFileEntry) -> str:
        storage_path = self._entry_to_storage_path(entry.path)
        if storage_path.backend == "smb" and self.smb_sha256:
            return self.smb_sha256(storage_path)
        return self.manager.compute_sha256(storage_path)

    def _entry_to_storage_path(self, value: str):
        if value.startswith(("local://", "smb://", "rclone://")):
            return StoragePath.from_uri(value)
        return StoragePath.local(value)

    def _root_to_storage_path(self, root: RootConfig):
        raw = root.storage_uri or str(root.path)
        if raw.startswith(("local://", "smb://", "rclone://")):
            return StoragePath.from_uri(raw)
        return StoragePath.local(raw)
