from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .models import RootConfig
from .storage import StoragePath


@dataclass(slots=True)
class ResolvedProviderDirectory:
    path: Path
    storage_uri: str
    connection_id: str
    connection_label: str
    share_name: str


def resolve_provider_directory(
    *,
    raw_path: str,
    roots: list[RootConfig],
    manager: Any,
) -> tuple[ResolvedProviderDirectory | None, str]:
    text = str(raw_path or "").strip()
    if not text:
        return None, "missing_path"

    local_path = Path(text).expanduser().resolve()
    if local_path.exists():
        if local_path.is_dir():
            return (
                ResolvedProviderDirectory(
                    path=local_path,
                    storage_uri="",
                    connection_id="",
                    connection_label="",
                    share_name="",
                ),
                "ok",
            )
        return None, "path_not_directory"

    provider_segments = _path_segments(text)
    mapped = _find_best_mapped_root(provider_segments=provider_segments, roots=roots)
    if mapped is None:
        return None, "path_not_found"

    root, root_storage_path, relative_segments = mapped
    mapped_storage_path = root_storage_path.join(*relative_segments)
    if not manager.exists(mapped_storage_path):
        return None, "path_not_found"
    if not manager.is_dir(mapped_storage_path):
        return None, "path_not_directory"

    mapped_path = _mapped_local_path(root=root, root_storage_path=root_storage_path, mapped_storage_path=mapped_storage_path)
    return (
        ResolvedProviderDirectory(
            path=mapped_path,
            storage_uri=mapped_storage_path.to_uri(),
            connection_id=root.connection_id,
            connection_label=root.connection_label,
            share_name=root.share_name,
        ),
        "ok",
    )


def _mapped_local_path(*, root: RootConfig, root_storage_path: StoragePath, mapped_storage_path: StoragePath) -> Path:
    if mapped_storage_path.backend == "local":
        return Path(mapped_storage_path.normalized_path())
    relative = mapped_storage_path.relative_to(root_storage_path)
    parts = [segment for segment in str(relative).split("/") if segment and segment != "."]
    base = Path(root.path)
    if not parts:
        return base
    return base.joinpath(*parts)


def _find_best_mapped_root(
    *,
    provider_segments: list[str],
    roots: list[RootConfig],
) -> tuple[RootConfig, StoragePath, list[str]] | None:
    best_match: tuple[int, RootConfig, StoragePath, list[str]] | None = None
    for root in roots:
        storage_path = _root_to_storage_path(root)
        root_segments = _root_match_segments(storage_path)
        if not root_segments:
            continue
        start_index = _find_subsequence(provider_segments, root_segments)
        if start_index < 0:
            continue
        relative_segments = provider_segments[start_index + len(root_segments) :]
        score = len(root_segments)
        if best_match is None or score > best_match[0]:
            best_match = (score, root, storage_path, relative_segments)
    if best_match is None:
        return None
    _, root, storage_path, relative_segments = best_match
    return root, storage_path, relative_segments


def _root_to_storage_path(root: RootConfig) -> StoragePath:
    raw = root.storage_uri or str(root.path)
    if raw.startswith(("local://", "smb://", "rclone://")):
        return StoragePath.from_uri(raw)
    return StoragePath.local(raw)


def _root_match_segments(path: StoragePath) -> list[str]:
    if path.backend == "smb":
        share = str(path.share_name or "").strip().strip("/")
        tail = _path_segments(path.normalized_path())
        return ([share] if share else []) + tail
    return _path_segments(path.normalized_path())


def _path_segments(value: str) -> list[str]:
    parts = [segment for segment in PurePosixPath(str(value or "")).parts if segment not in {"", "/"}]
    return [segment for segment in parts if segment]


def _find_subsequence(haystack: list[str], needle: list[str]) -> int:
    if not needle or len(needle) > len(haystack):
        return -1
    for index in range(0, len(haystack) - len(needle) + 1):
        if haystack[index : index + len(needle)] == needle:
            return index
    return -1
