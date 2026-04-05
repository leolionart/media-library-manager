from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
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


TRAILING_DIGITS_RE = re.compile(r"^(.*?)(\d+)$")


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
    if mapped is not None:
        root, root_storage_path, relative_segments = mapped
        mapped_storage_path = root_storage_path.join(*relative_segments)
        if manager.exists(mapped_storage_path):
            if not manager.is_dir(mapped_storage_path):
                return None, "path_not_directory"
            return _build_resolved_directory(
                root=root,
                root_storage_path=root_storage_path,
                mapped_storage_path=mapped_storage_path,
            ), "ok"

    return None, "path_not_found"


def provider_path_maps_to_connected_root(*, raw_path: str, roots: list[RootConfig]) -> bool:
    text = str(raw_path or "").strip()
    if not text:
        return False

    local_path = Path(text).expanduser().resolve()
    if local_path.exists():
        return local_path.is_dir()

    provider_segments = _path_segments(text)
    return _find_best_mapped_root(provider_segments=provider_segments, roots=roots) is not None


def _build_resolved_directory(
    *,
    root: RootConfig,
    root_storage_path: StoragePath,
    mapped_storage_path: StoragePath,
) -> ResolvedProviderDirectory:
    mapped_path = _mapped_local_path(root=root, root_storage_path=root_storage_path, mapped_storage_path=mapped_storage_path)
    return ResolvedProviderDirectory(
        path=mapped_path,
        storage_uri=mapped_storage_path.to_uri(),
        connection_id=root.connection_id,
        connection_label=root.connection_label,
        share_name=root.share_name,
    )


def find_provider_path_replacement(
    *,
    raw_path: str,
    roots: list[RootConfig],
    manager: Any,
) -> ResolvedProviderDirectory | None:
    segments = [segment for segment in PurePosixPath(str(raw_path or "")).parts if segment not in {"", "/"}]
    try:
        rclone_index = next(index for index, segment in enumerate(segments) if segment.lower() == "rclone")
    except StopIteration:
        return None
    if rclone_index + 2 >= len(segments):
        return None

    remote_alias = segments[rclone_index + 1]
    relative_segments = segments[rclone_index + 2 :]
    normalized_alias = _normalize_root_hint(remote_alias)

    for root in roots:
        root_storage = _root_to_storage_path(root)
        if root_storage.backend != "rclone":
            continue
        if normalized_alias not in _normalize_root_hint(root.label):
            continue
        candidate_storage = root_storage.join(*relative_segments)
        if not manager.exists(candidate_storage) or not manager.is_dir(candidate_storage):
            continue
        candidate_path = Path(root.path).joinpath(*relative_segments)
        return ResolvedProviderDirectory(
            path=candidate_path,
            storage_uri=candidate_storage.to_uri(),
            connection_id=root.connection_id,
            connection_label=root.connection_label,
            share_name=root.share_name,
        )
    return None


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
        for root_segments in _root_match_candidates(root=root, storage_path=storage_path):
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


def _root_match_candidates(*, root: RootConfig, storage_path: StoragePath) -> list[list[str]]:
    candidates: list[list[str]] = []
    storage_segments = _root_match_segments(storage_path)
    if storage_segments:
        candidates.append(storage_segments)
    if storage_path.backend == "smb":
        share_alias_segments = _smb_share_alias_segments(storage_path)
        if share_alias_segments and share_alias_segments not in candidates:
            candidates.append(share_alias_segments)
    path_segments = _path_segments(str(root.path))
    if path_segments and path_segments not in candidates:
        candidates.append(path_segments)
    return candidates


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
        if all(_segments_equivalent(left, right) for left, right in zip(haystack[index : index + len(needle)], needle)):
            return index
    return -1


def _smb_share_alias_segments(path: StoragePath) -> list[str]:
    share = str(path.share_name or "").strip().strip("/")
    if not share:
        return []
    tail = _path_segments(path.normalized_path())
    alias = _segment_alias(share)
    if alias == share:
        return []
    return [alias, *tail]


def _segments_equivalent(left: str, right: str) -> bool:
    left_normalized = _normalize_segment(left)
    right_normalized = _normalize_segment(right)
    if left_normalized == right_normalized:
        return True
    return _segment_alias(left_normalized) == _segment_alias(right_normalized)


def _normalize_segment(value: str) -> str:
    return str(value or "").strip().strip("/").lower()


def _segment_alias(value: str) -> str:
    normalized = _normalize_segment(value)
    match = TRAILING_DIGITS_RE.match(normalized)
    if not match:
        return normalized
    base = match.group(1).rstrip(" -_")
    return base or normalized
