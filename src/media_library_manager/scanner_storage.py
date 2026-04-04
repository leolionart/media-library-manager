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
    def iter_video_files(self, root: RootConfig, *, allowed_suffixes: set[str]) -> Iterable[ScannedFileEntry]:
        root_path = Path(root.path)
        for path in root_path.rglob("*"):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in allowed_suffixes:
                continue
            stat = path.stat()
            yield ScannedFileEntry(
                path=str(path.resolve()),
                relative_path=str(path.relative_to(root_path)),
                size=stat.st_size,
                stem=path.stem,
                suffix=suffix,
                parent_name=path.parent.name,
            )

    def compute_sha256(self, entry: ScannedFileEntry) -> str:
        digest = hashlib.sha256()
        with Path(entry.path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


class StorageManagerScannerStorage:
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
        root_path = self._root_to_storage_path(root)
        pending = [root_path]
        while pending:
            current = pending.pop()
            entries = self.manager.list_dir(current)
            for entry in entries:
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
        if value.startswith(("local://", "smb://")):
            return StoragePath.from_uri(value)
        return StoragePath.local(value)

    def _root_to_storage_path(self, root: RootConfig):
        raw = root.storage_uri or str(root.path)
        if raw.startswith(("local://", "smb://")):
            return StoragePath.from_uri(raw)
        return StoragePath.local(raw)
