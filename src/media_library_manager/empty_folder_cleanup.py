from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable

from .models import RootConfig
from .scanner import VIDEO_EXTENSIONS
from .storage import StoragePath, default_storage_manager


CleanupProgressCallback = Callable[[dict[str, object]], None]
CleanupCancellationCallback = Callable[[], bool]


def scan_duplicate_empty_folders(
    roots: list[RootConfig],
    *,
    lan_connections: dict[str, Any],
    progress_callback: CleanupProgressCallback | None = None,
    should_cancel: CleanupCancellationCallback | None = None,
) -> dict[str, Any]:
    manager = default_storage_manager(lan_connections=lan_connections)
    indexed_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    errors: list[dict[str, Any]] = []
    total_roots = len(roots)
    total_folders_indexed = 0

    for index, root in enumerate(roots, start=1):
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

        root_folder_count = 0
        try:
            entries = manager.list_dir(root_storage)
        except Exception as exc:
            errors.append(
                {
                    "root_label": root.label,
                    "root_path": str(root.path),
                    "root_storage_uri": root.storage_uri or str(root.path),
                    "message": str(exc),
                }
            )
            entries = []

        for entry in entries:
            if should_cancel and should_cancel():
                raise RuntimeError("job cancelled")
            if not entry.is_dir:
                continue
            root_folder_count += 1
            total_folders_indexed += 1
            indexed_by_name[entry.name].append(
                {
                    "folder_name": entry.name,
                    "path": str(root.path / entry.name),
                    "delete_path": entry.path.to_uri() if entry.path.backend == "smb" else entry.path.normalized_path(),
                    "storage_uri": entry.path.to_uri(),
                    "root_label": root.label,
                    "root_path": str(root.path),
                    "root_storage_uri": root.storage_uri or str(root.path),
                    "root_kind": root.kind,
                    "storage_path": entry.path,
                }
            )

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
    for folder_name, candidates in sorted(indexed_by_name.items(), key=lambda item: item[0].lower()):
        if len(candidates) < 2:
            continue
        if len({item["root_storage_uri"] for item in candidates}) < 2:
            continue
        duplicate_groups.append((folder_name, candidates))

    groups: list[dict[str, Any]] = []
    for group_index, (folder_name, candidates) in enumerate(duplicate_groups, start=1):
        reviewed_items: list[dict[str, Any]] = []
        deletion_candidates: list[dict[str, Any]] = []
        for item in candidates:
            if should_cancel and should_cancel():
                raise RuntimeError("job cancelled")
            has_video, has_any_file = _folder_has_video(
                manager=manager,
                path=item["storage_path"],
                should_cancel=should_cancel,
            )
            reviewed = {
                key: value
                for key, value in item.items()
                if key != "storage_path"
            }
            reviewed["has_video"] = has_video
            reviewed["is_deletion_candidate"] = not has_video
            reviewed["empty_reason"] = None if has_video else ("empty" if not has_any_file else "sidecar-only")
            reviewed_items.append(reviewed)
            if not has_video:
                deletion_candidates.append(reviewed)

        groups.append(
            {
                "id": f"{_slugify(folder_name)}::{group_index}",
                "folder_name": folder_name,
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


def _folder_has_video(
    *,
    manager: Any,
    path: StoragePath,
    should_cancel: CleanupCancellationCallback | None = None,
) -> tuple[bool, bool]:
    pending = [path]
    has_any_file = False
    while pending:
        if should_cancel and should_cancel():
            raise RuntimeError("job cancelled")
        current = pending.pop()
        try:
            entries = manager.list_dir(current)
        except Exception:
            continue
        for entry in entries:
            if should_cancel and should_cancel():
                raise RuntimeError("job cancelled")
            if entry.is_dir:
                pending.append(entry.path)
                continue
            has_any_file = True
            if entry.path.suffix().lower() in VIDEO_EXTENSIONS:
                return True, True
    return False, has_any_file


def _root_to_storage_path(root: RootConfig) -> StoragePath:
    raw = root.storage_uri or str(root.path)
    if raw.startswith(("local://", "smb://")):
        return StoragePath.from_uri(raw)
    return StoragePath.local(raw)


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return cleaned or "folder"
