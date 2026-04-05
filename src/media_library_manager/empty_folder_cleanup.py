from __future__ import annotations

import re
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any, Callable

from .models import RootConfig
from .rclone_cli import list_entries_recursive
from .scanner import VIDEO_EXTENSIONS, parse_media_details
from .storage import StoragePath, default_storage_manager

STORAGE_URI_SCHEMES = ("local://", "smb://", "rclone://")
DIRECTORY_PROGRESS_INTERVAL = 1
VIDEO_EXTENSION_SUFFIXES = tuple(sorted(VIDEO_EXTENSIONS))
INFERIOR_VIDEO_SET_REASON = "inferior-video-set"
MEDIA_CONTAINER_ALIASES = {
    "movie",
    "movies",
    "film",
    "films",
    "series",
    "tv",
    "tv series",
    "tv-series",
    "shows",
    "show",
}
IGNORED_FOLDER_NAMES = {
    "@eadir",
    ".grab",
    ".stfolder",
    "extrafanart",
    "extrathumbs",
    "metadata",
    "sample",
    "samples",
    "scene",
    "scenes",
    "subs",
    "subtitles",
    "trailer",
    "trailers",
    "trickplay",
}


CleanupProgressCallback = Callable[[dict[str, object]], None]
CleanupCancellationCallback = Callable[[], bool]


def scan_duplicate_empty_folders(
    roots: list[RootConfig],
    *,
    lan_connections: dict[str, Any],
    progress_callback: CleanupProgressCallback | None = None,
    should_cancel: CleanupCancellationCallback | None = None,
    start_root_index: int = 1,
) -> dict[str, Any]:
    manager = default_storage_manager(lan_connections=lan_connections)
    indexed_by_match_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    errors: list[dict[str, Any]] = []
    total_roots = len(roots)
    total_folders_indexed = 0

    normalized_start_index = max(1, int(start_root_index or 1))
    for index, root in enumerate(roots[normalized_start_index - 1 :], start=normalized_start_index):
        if should_cancel and should_cancel():
            raise RuntimeError("job cancelled")

        root_storage = _root_to_storage_path(root)
        if progress_callback:
            progress_callback(
                {
                    "event": "root_started",
                    "index": index,
                    "total_roots": total_roots,
                    "root_label": root.label,
                    "root_path": str(root.path),
                    "total_indexed_files": total_folders_indexed,
                }
            )

        try:
            root_folder_count = _index_root_folders(
                manager=manager,
                root=root,
                root_storage=root_storage,
                indexed_by_match_path=indexed_by_match_path,
                progress_callback=progress_callback,
                root_index=index,
                total_roots=total_roots,
                total_folders_indexed=total_folders_indexed,
                should_cancel=should_cancel,
            )
        except Exception as exc:
            errors.append(
                {
                    "root_label": root.label,
                    "root_path": str(root.path),
                    "root_storage_uri": root.storage_uri or str(root.path),
                    "message": str(exc),
                }
            )
            root_folder_count = 0

        total_folders_indexed += root_folder_count

        if progress_callback:
            progress_callback(
                {
                    "event": "root_completed",
                    "index": index,
                    "total_roots": total_roots,
                    "root_label": root.label,
                    "root_path": str(root.path),
                    "indexed_files": root_folder_count,
                    "total_indexed_files": total_folders_indexed,
                }
            )

    duplicate_groups = []
    for relative_path, candidates in sorted(indexed_by_match_path.items(), key=lambda item: item[0].lower()):
        if len(candidates) < 2:
            continue
        if len({item["root_storage_uri"] for item in candidates}) < 2:
            continue
        duplicate_groups.append((relative_path, candidates))

    groups: list[dict[str, Any]] = []
    for group_index, (relative_path, candidates) in enumerate(duplicate_groups, start=1):
        reviewed_items: list[dict[str, Any]] = []
        deletion_candidates: list[dict[str, Any]] = []
        for item in candidates:
            if should_cancel and should_cancel():
                raise RuntimeError("job cancelled")
            if item.get("has_video") is None or item.get("has_any_file") is None:
                has_video, has_any_file = _folder_has_video(
                    manager=manager,
                    path=item["storage_path"],
                    should_cancel=should_cancel,
                )
                item["has_video"] = has_video
                item["has_any_file"] = has_any_file
            if item.get("has_video") and item.get("inventory") is None:
                item["inventory"] = _build_folder_inventory(
                    manager=manager,
                    path=item["storage_path"],
                    should_cancel=should_cancel,
                )
            reviewed = {
                key: value
                for key, value in item.items()
                if key not in {"match_relative_path", "storage_path", "has_any_file", "inventory"}
            }
            reviewed["has_video"] = bool(item.get("has_video"))
            reviewed["is_deletion_candidate"] = not reviewed["has_video"]
            reviewed["empty_reason"] = None if reviewed["has_video"] else ("empty" if not item.get("has_any_file") else "sidecar-only")
            inventory = item.get("inventory") or {}
            reviewed["video_count"] = int(inventory.get("video_count") or 0)
            reviewed["episode_count"] = int(inventory.get("episode_count") or 0)
            reviewed["unparsed_video_count"] = int(inventory.get("unparsed_video_count") or 0)
            reviewed["episode_keys"] = sorted(inventory.get("episode_keys") or [])
            reviewed_items.append(reviewed)
            if not reviewed["has_video"]:
                deletion_candidates.append(reviewed)

        _mark_inferior_video_set_candidates(reviewed_items, deletion_candidates)

        groups.append(
            {
                "id": f"{_slugify(relative_path)}::{group_index}",
                "folder_name": candidates[0]["folder_name"] if candidates else relative_path,
                "relative_path": relative_path,
                "items": reviewed_items,
                "deletion_candidates": deletion_candidates,
                "deletion_candidate_count": len(deletion_candidates),
                "roots_count": len({item["root_storage_uri"] for item in reviewed_items}),
            }
        )

    if progress_callback:
        progress_callback(
            {
                "event": "scan_completed",
                "total_roots": total_roots,
                "total_indexed_files": total_folders_indexed,
                "exact_duplicate_groups": 0,
                "media_collision_groups": 0,
                "folder_media_duplicate_groups": len(groups),
            }
        )

    return {
        "version": 1,
        "summary": {
            "roots_scanned": total_roots,
            "folders_indexed": total_folders_indexed,
            "duplicate_groups": len(groups),
            "duplicate_folders": sum(len(group["items"]) for group in groups),
            "groups_with_deletion_candidates": sum(1 for group in groups if group["deletion_candidate_count"] > 0),
            "deletion_candidates": sum(group["deletion_candidate_count"] for group in groups),
            "errors": len(errors),
        },
        "groups": groups,
        "errors": errors,
    }


def _index_root_folders(
    *,
    manager: Any,
    root: RootConfig,
    root_storage: StoragePath,
    indexed_by_match_path: dict[str, list[dict[str, Any]]],
    progress_callback: CleanupProgressCallback | None = None,
    root_index: int,
    total_roots: int,
    total_folders_indexed: int,
    should_cancel: CleanupCancellationCallback | None = None,
) -> int:
    if root_storage.backend == "rclone":
        return _index_rclone_root_folders(
            root=root,
            root_storage=root_storage,
            indexed_by_match_path=indexed_by_match_path,
            progress_callback=progress_callback,
            root_index=root_index,
            total_roots=total_roots,
            total_folders_indexed=total_folders_indexed,
            should_cancel=should_cancel,
        )

    pending = [root_storage]
    indexed_count = 0
    directories_scanned = 0
    indexed_folders_by_path: dict[str, dict[str, Any]] = {}

    while pending:
        if should_cancel and should_cancel():
            raise RuntimeError("job cancelled")
        current = pending.pop()
        directories_scanned += 1
        if progress_callback and (directories_scanned == 1 or directories_scanned % DIRECTORY_PROGRESS_INTERVAL == 0):
            current_path = current.normalized_path() if current.backend == "local" else current.to_uri()
            progress_callback(
                {
                    "event": "directory_scanned",
                    "index": root_index,
                    "total_roots": total_roots,
                    "root_label": root.label,
                    "root_path": str(root.path),
                    "directory_path": current_path,
                    "directories_scanned": directories_scanned,
                    "root_indexed_files": indexed_count,
                    "total_indexed_files": total_folders_indexed + indexed_count,
                }
            )
        entries = manager.list_dir(current)
        for entry in entries:
            if should_cancel and should_cancel():
                raise RuntimeError("job cancelled")
            if entry.is_dir:
                if _should_ignore_folder(entry.name):
                    continue
                pending.append(entry.path)
                indexed_count += 1
                relative_path = entry.path.relative_to(root_storage)
                folder_record = {
                    "folder_name": entry.name,
                    "relative_path": relative_path,
                    "match_relative_path": _canonicalize_match_relative_path(relative_path),
                    "path": str(root.path / relative_path),
                    "delete_path": entry.path.to_uri() if entry.path.backend != "local" else entry.path.normalized_path(),
                    "storage_uri": entry.path.to_uri(),
                    "root_label": root.label,
                    "root_path": str(root.path),
                    "root_storage_uri": root.storage_uri or str(root.path),
                    "root_kind": root.kind,
                    "storage_path": entry.path,
                    "has_video": False,
                    "has_any_file": False,
                }
                indexed_folders_by_path[relative_path] = folder_record
                indexed_by_match_path[folder_record["match_relative_path"]].append(folder_record)
                continue
            _mark_folder_ancestors(
                indexed_folders_by_path=indexed_folders_by_path,
                current=current,
                root_storage=root_storage,
                field_name="has_any_file",
            )
            if entry.path.suffix().lower() in VIDEO_EXTENSIONS:
                _mark_folder_ancestors(
                    indexed_folders_by_path=indexed_folders_by_path,
                    current=current,
                    root_storage=root_storage,
                    field_name="has_video",
                )

    return indexed_count


def _index_rclone_root_folders(
    *,
    root: RootConfig,
    root_storage: StoragePath,
    indexed_by_match_path: dict[str, list[dict[str, Any]]],
    progress_callback: CleanupProgressCallback | None = None,
    root_index: int,
    total_roots: int,
    total_folders_indexed: int,
    should_cancel: CleanupCancellationCallback | None = None,
) -> int:
    indexed_count = 0
    scanned_count = 0
    indexed_folders_by_path: dict[str, dict[str, Any]] = {}

    rows = list_entries_recursive(
        root_storage.rclone_remote,
        root_storage.normalized_path(),
        timeout=900,
        fast_list=True,
    )
    for row in sorted(rows, key=lambda item: str(item.get("Path") or item.get("Name") or "").lower()):
        if should_cancel and should_cancel():
            raise RuntimeError("job cancelled")
        relative_path = str(row.get("Path") or row.get("Name") or "").strip().strip("/")
        if not relative_path:
            continue
        if _path_contains_ignored_folder(relative_path):
            continue
        scanned_count += 1
        if progress_callback and (scanned_count == 1 or scanned_count % 500 == 0):
            progress_callback(
                {
                    "event": "directory_scanned",
                    "index": root_index,
                    "total_roots": total_roots,
                    "root_label": root.label,
                    "root_path": str(root.path),
                    "directory_path": relative_path,
                    "directories_scanned": scanned_count,
                    "root_indexed_files": indexed_count,
                    "total_indexed_files": total_folders_indexed + indexed_count,
                }
            )

        is_dir = bool(row.get("IsDir"))
        if is_dir:
            folder_name = relative_path.rsplit("/", 1)[-1]
            if _should_ignore_folder(folder_name):
                continue
            entry_path = root_storage.join(relative_path)
            indexed_count += 1
            folder_record = {
                "folder_name": folder_name,
                "relative_path": relative_path,
                "match_relative_path": _canonicalize_match_relative_path(relative_path),
                "path": str(root.path / relative_path),
                "delete_path": entry_path.to_uri(),
                "storage_uri": entry_path.to_uri(),
                "root_label": root.label,
                "root_path": str(root.path),
                "root_storage_uri": root.storage_uri or str(root.path),
                "root_kind": root.kind,
                "storage_path": entry_path,
                "has_video": False,
                "has_any_file": False,
            }
            indexed_folders_by_path[relative_path] = folder_record
            indexed_by_match_path[folder_record["match_relative_path"]].append(folder_record)
            continue

        entry_path = root_storage.join(relative_path)
        current_parent = entry_path.parent() or root_storage
        _mark_folder_ancestors(
            indexed_folders_by_path=indexed_folders_by_path,
            current=current_parent,
            root_storage=root_storage,
            field_name="has_any_file",
        )
        if relative_path.lower().endswith(VIDEO_EXTENSION_SUFFIXES):
            _mark_folder_ancestors(
                indexed_folders_by_path=indexed_folders_by_path,
                current=current_parent,
                root_storage=root_storage,
                field_name="has_video",
            )

    return indexed_count


def _folder_has_video(
    *,
    manager: Any,
    path: StoragePath,
    should_cancel: CleanupCancellationCallback | None = None,
) -> tuple[bool, bool]:
    if path.backend == "rclone":
        rows = list_entries_recursive(
            path.rclone_remote,
            path.normalized_path(),
            timeout=300,
            files_only=True,
            fast_list=True,
        )
        has_any_file = False
        for row in rows:
            if should_cancel and should_cancel():
                raise RuntimeError("job cancelled")
            relative_path = str(row.get("Path") or row.get("Name") or "").strip().strip("/")
            if not relative_path:
                continue
            if _path_contains_ignored_folder(relative_path):
                continue
            has_any_file = True
            if relative_path.lower().endswith(VIDEO_EXTENSION_SUFFIXES):
                return True, True
        return False, has_any_file

    pending = [path]
    has_any_file = False
    while pending:
        if should_cancel and should_cancel():
            raise RuntimeError("job cancelled")
        current = pending.pop()
        entries = manager.list_dir(current)
        for entry in entries:
            if should_cancel and should_cancel():
                raise RuntimeError("job cancelled")
            if entry.is_dir:
                if _should_ignore_folder(entry.name):
                    continue
                pending.append(entry.path)
                continue
            has_any_file = True
            if entry.path.suffix().lower() in VIDEO_EXTENSIONS:
                return True, True
    return False, has_any_file


def _build_folder_inventory(
    *,
    manager: Any,
    path: StoragePath,
    should_cancel: CleanupCancellationCallback | None = None,
) -> dict[str, Any]:
    episode_keys: set[str] = set()
    unmatched_video_files: list[str] = []
    sample_episode_keys: list[str] = []
    video_count = 0

    def record_video(relative_path: str) -> None:
        nonlocal video_count
        if not relative_path.lower().endswith(VIDEO_EXTENSION_SUFFIXES):
            return
        video_count += 1
        parsed = parse_media_details(PurePosixPath(relative_path))
        media_key = str(parsed.get("media_key") or "")
        if str(parsed.get("kind") or "") == "series" and media_key.startswith("episode:"):
            episode_keys.add(media_key)
            if len(sample_episode_keys) < 6 and media_key not in sample_episode_keys:
                sample_episode_keys.append(media_key)
            return
        unmatched_video_files.append(relative_path)

    if path.backend == "rclone":
        rows = list_entries_recursive(
            path.rclone_remote,
            path.normalized_path(),
            timeout=300,
            files_only=True,
            fast_list=True,
        )
        for row in rows:
            if should_cancel and should_cancel():
                raise RuntimeError("job cancelled")
            relative_path = str(row.get("Path") or row.get("Name") or "").strip().strip("/")
            if not relative_path or _path_contains_ignored_folder(relative_path):
                continue
            record_video(relative_path)
    else:
        pending = [path]
        while pending:
            if should_cancel and should_cancel():
                raise RuntimeError("job cancelled")
            current = pending.pop()
            entries = manager.list_dir(current)
            for entry in entries:
                if should_cancel and should_cancel():
                    raise RuntimeError("job cancelled")
                if entry.is_dir:
                    if _should_ignore_folder(entry.name):
                        continue
                    pending.append(entry.path)
                    continue
                relative_path = entry.path.relative_to(path)
                if _path_contains_ignored_folder(relative_path):
                    continue
                record_video(relative_path)

    return {
        "video_count": video_count,
        "episode_count": len(episode_keys),
        "episode_keys": episode_keys,
        "unparsed_video_count": len(unmatched_video_files),
        "unparsed_video_samples": unmatched_video_files[:6],
        "sample_episode_keys": sample_episode_keys,
    }


def _mark_inferior_video_set_candidates(
    reviewed_items: list[dict[str, Any]],
    deletion_candidates: list[dict[str, Any]],
) -> None:
    comparable_items = [
        item
        for item in reviewed_items
        if item.get("has_video")
        and int(item.get("episode_count") or 0) > 0
        and int(item.get("unparsed_video_count") or 0) == 0
        and int(item.get("video_count") or 0) == int(item.get("episode_count") or 0)
    ]
    if len(comparable_items) < 2:
        return

    for item in comparable_items:
        if item.get("is_deletion_candidate"):
            continue
        item_episode_keys = set(item.get("episode_keys") or [])
        if not item_episode_keys:
            continue
        strict_supersets: list[dict[str, Any]] = []
        larger_overlaps: list[dict[str, Any]] = []
        for other in comparable_items:
            if other is item:
                continue
            other_episode_keys = set(other.get("episode_keys") or [])
            if len(other_episode_keys) <= len(item_episode_keys):
                continue
            if item_episode_keys < other_episode_keys:
                strict_supersets.append(other)
                continue
            if item_episode_keys & other_episode_keys:
                larger_overlaps.append(other)
        superior_matches = strict_supersets or larger_overlaps
        if not superior_matches:
            continue
        superior_matches.sort(
            key=lambda other: (
                -(len(set(other.get("episode_keys") or []))),
                str(other.get("root_label") or "").lower(),
                str(other.get("path") or "").lower(),
            )
        )
        best_match = superior_matches[0]
        best_episode_keys = set(best_match.get("episode_keys") or [])
        missing_episode_keys = sorted(best_episode_keys - item_episode_keys)
        exclusive_episode_keys = sorted(item_episode_keys - best_episode_keys)
        item["is_deletion_candidate"] = True
        item["empty_reason"] = INFERIOR_VIDEO_SET_REASON
        item["comparison_mode"] = "strict-subset" if best_match in strict_supersets else "larger-overlap"
        item["superseded_by_root_label"] = best_match.get("root_label")
        item["superseded_by_path"] = best_match.get("path")
        item["missing_episode_count"] = len(missing_episode_keys)
        item["missing_episode_keys"] = missing_episode_keys
        item["exclusive_episode_count"] = len(exclusive_episode_keys)
        item["exclusive_episode_keys"] = exclusive_episode_keys
        deletion_candidates.append(item)


def _root_to_storage_path(root: RootConfig) -> StoragePath:
    raw = root.storage_uri or str(root.path)
    if raw.startswith(STORAGE_URI_SCHEMES):
        return StoragePath.from_uri(raw)
    return StoragePath.local(raw)


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return cleaned or "folder"


def _mark_folder_ancestors(
    *,
    indexed_folders_by_path: dict[str, dict[str, Any]],
    current: StoragePath,
    root_storage: StoragePath,
    field_name: str,
) -> None:
    if current == root_storage:
        return
    relative_path = current.relative_to(root_storage)
    parts = relative_path.split("/")
    for length in range(1, len(parts) + 1):
        candidate = "/".join(parts[:length])
        record = indexed_folders_by_path.get(candidate)
        if record is not None:
            record[field_name] = True


def _canonicalize_match_relative_path(relative_path: str) -> str:
    segments = [segment.strip() for segment in str(relative_path or "").split("/") if segment.strip()]
    if len(segments) >= 2 and _normalize_segment(segments[0]) in MEDIA_CONTAINER_ALIASES:
        segments = segments[1:]
    return "/".join(segments) if segments else str(relative_path or "")


def _should_ignore_folder(name: str) -> bool:
    normalized = _normalize_segment(name)
    if not normalized:
        return True
    if normalized in IGNORED_FOLDER_NAMES:
        return True
    compact = normalized.replace(" ", "")
    if any(token in compact for token in {"trickplay", "@eadir"}):
        return True
    return normalized.startswith(".")


def _path_contains_ignored_folder(relative_path: str) -> bool:
    segments = [segment for segment in str(relative_path or "").split("/") if segment]
    return any(_should_ignore_folder(segment) for segment in segments)


def _normalize_segment(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())
