from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .models import MediaFile, RootConfig
from .rclone_cli import list_entries_recursive
from .scanner import VIDEO_EXTENSIONS, inspect_media_file
from .scanner_storage import ScannedFileEntry
from .storage import StoragePath, default_storage_manager
from .sync_integrations import normalize_title


DEFAULT_FOLDER_INDEX_MAX_DEPTH = 6
FOLDER_INDEX_VERSION = 3
FOLDER_INDEX_CAPABILITIES = [
    "video_files",
    "has_any_file",
    "non_video_file_count",
    "child_folder_count",
    "normalized_name",
]


def build_folder_metadata_index(
    roots: list[RootConfig],
    lan_connections: dict[str, Any],
    *,
    max_depth: int = DEFAULT_FOLDER_INDEX_MAX_DEPTH,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    manager = default_storage_manager(lan_connections=lan_connections)
    bounded_depth = max(1, min(int(max_depth or DEFAULT_FOLDER_INDEX_MAX_DEPTH), 8))
    items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for index, root in enumerate(roots, start=1):
        root_storage_path = root_to_index_storage_path(root)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "root_started",
                    "index": index,
                    "total_roots": len(roots),
                    "root_label": root.label,
                    "root_path": str(root.path),
                }
            )
        try:
            if root_storage_path.backend == "rclone":
                root_items = _index_rclone_root(root, root_storage_path, max_depth=bounded_depth)
            else:
                root_items = _index_storage_root(manager, root, root_storage_path, max_depth=bounded_depth)
            items.extend(root_items)
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "root_completed",
                        "index": index,
                        "total_roots": len(roots),
                        "root_label": root.label,
                        "root_path": str(root.path),
                        "indexed_folders": len(root_items),
                        "total_indexed_folders": len(items),
                    }
                )
        except Exception as exc:
            errors.append({"root_label": root.label, "root_path": str(root.path), "message": str(exc)})
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "root_failed",
                        "index": index,
                        "total_roots": len(roots),
                        "root_label": root.label,
                        "root_path": str(root.path),
                        "message": str(exc),
                        "total_errors": len(errors),
                    }
                )

    if progress_callback is not None:
        progress_callback(
            {
                "event": "scan_completed",
                "total_roots": len(roots),
                "folders": len(items),
                "errors": len(errors),
            }
        )

    return {
        "version": FOLDER_INDEX_VERSION,
        "capabilities": [*FOLDER_INDEX_CAPABILITIES],
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "roots": len(roots),
            "folders": len(items),
            "video_files": sum(int(item.get("video_file_count", 0)) for item in items),
            "non_video_files": sum(int(item.get("non_video_file_count", 0)) for item in items),
            "errors": len(errors),
            "max_depth": bounded_depth,
        },
        "roots": [_root_report_row(root) for root in roots],
        "items": items,
        "errors": errors,
    }


def filter_index_candidates_for_provider(
    *,
    provider: str,
    roots: list[RootConfig],
    report: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(report, dict):
        return []
    items = report.get("items")
    if not isinstance(items, list) or not items:
        return []
    allowed_root_keys = {_root_storage_identity(root) for root in iter_provider_roots(provider, roots)}
    if not allowed_root_keys:
        return []
    return [
        item
        for item in items
        if isinstance(item, dict) and str(item.get("root_storage_uri") or "") in allowed_root_keys
    ]


def iter_provider_roots(provider: str, roots: list[RootConfig]) -> list[RootConfig]:
    matched: list[RootConfig] = []
    for root in roots:
        if provider == "radarr" and root.kind not in {"movie", "mixed"}:
            continue
        if provider == "sonarr" and root.kind not in {"series", "mixed"}:
            continue
        matched.append(root)
    primary_kind = "movie" if provider == "radarr" else "series"
    return sorted(
        matched,
        key=lambda root: (0 if root.kind == primary_kind else 1, str(root.label or "").lower(), str(root.path)),
    )


def validate_folder_index_report(
    report: dict[str, Any] | None,
    *,
    required_capabilities: list[str] | None = None,
    minimum_version: int = 2,
) -> str | None:
    if not isinstance(report, dict):
        return "Refresh cached folder metadata in Library Finder before running this scan."
    if int(report.get("version", 0) or 0) < int(minimum_version):
        return "Cached folder metadata is outdated. Refresh Library Finder to rebuild the folder index."
    items = report.get("items")
    if not isinstance(items, list) or not items:
        return "Cached folder metadata is empty. Refresh Library Finder before running this scan."
    capabilities = {str(item).strip() for item in report.get("capabilities", []) if str(item).strip()}
    missing = [name for name in (required_capabilities or []) if name not in capabilities]
    if missing:
        return f"Cached folder metadata is missing capabilities: {', '.join(missing)}. Refresh Library Finder to rebuild the folder index."
    return None


def build_folder_index_lookup(report: dict[str, Any] | None) -> dict[str, Any]:
    by_storage_uri: dict[str, dict[str, Any]] = {}
    by_path: dict[str, dict[str, Any]] = {}
    by_root_storage_uri: dict[str, list[dict[str, Any]]] = defaultdict(list)
    items: list[dict[str, Any]] = []
    if not isinstance(report, dict):
        return {
            "by_storage_uri": by_storage_uri,
            "by_path": by_path,
            "by_root_storage_uri": by_root_storage_uri,
            "items": items,
        }
    for item in report.get("items", []):
        if not isinstance(item, dict):
            continue
        items.append(item)
        path = str(item.get("path") or "")
        storage_uri = str(item.get("storage_uri") or "")
        root_storage_uri = str(item.get("root_storage_uri") or "")
        if path:
            by_path[path] = item
        if storage_uri:
            by_storage_uri[storage_uri] = item
        if root_storage_uri:
            by_root_storage_uri[root_storage_uri].append(item)
    return {
        "by_storage_uri": by_storage_uri,
        "by_path": by_path,
        "by_root_storage_uri": by_root_storage_uri,
        "items": items,
    }


def folder_index_rows_for_roots(*, roots: list[RootConfig], report: dict[str, Any] | None) -> list[dict[str, Any]]:
    lookup = build_folder_index_lookup(report)
    allowed_root_keys = {_root_storage_identity(root) for root in roots}
    if not allowed_root_keys:
        return []
    rows: list[dict[str, Any]] = []
    for key in sorted(allowed_root_keys):
        rows.extend(lookup["by_root_storage_uri"].get(key, []))
    rows.sort(key=lambda item: (str(item.get("path") or "").lower(), int(item.get("depth") or 0)))
    return rows


def media_files_from_index_rows(rows: list[dict[str, Any]], *, roots: list[RootConfig]) -> list[MediaFile]:
    roots_by_storage = {_root_storage_identity(root): root for root in roots}
    roots_by_path = {str(root.path): root for root in roots}
    fallback_roots_by_path: dict[str, RootConfig] = {}
    files: list[MediaFile] = []
    seen: set[str] = set()

    for item in rows:
        if not isinstance(item, dict):
            continue
        root = _root_for_index_item(
            item=item,
            roots_by_storage=roots_by_storage,
            roots_by_path=roots_by_path,
            fallback_roots_by_path=fallback_roots_by_path,
        )
        if root is None:
            continue
        for video in item.get("video_files", []):
            if not isinstance(video, dict):
                continue
            path = str(video.get("path") or "").strip()
            storage_uri = str(video.get("storage_uri") or "").strip()
            name = str(video.get("name") or Path(path).name or "").strip()
            if not path or not name:
                continue
            dedupe_key = storage_uri or path
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            entry = ScannedFileEntry(
                path=path,
                relative_path=str(video.get("relative_path") or "").strip() or _relative_to_root(path, root),
                size=int(video.get("size") or 0),
                stem=Path(name).stem,
                suffix=Path(name).suffix.lower(),
                parent_name=Path(path).parent.name,
            )
            if not entry.relative_path:
                continue
            media = inspect_media_file(entry, root)
            media.path = Path(path)
            media.storage_uri = storage_uri
            files.append(media)
    return files


def root_to_index_storage_path(root: RootConfig) -> StoragePath:
    raw = root.storage_uri or str(root.path)
    if raw.startswith(("local://", "smb://", "rclone://")):
        return StoragePath.from_uri(raw)
    return StoragePath.local(raw)


def _index_rclone_root(root: RootConfig, root_storage_path: StoragePath, *, max_depth: int) -> list[dict[str, Any]]:
    rows = list_entries_recursive(
        root_storage_path.rclone_remote,
        root_storage_path.normalized_path(),
        fast_list=True,
    )
    items_by_uri: dict[str, dict[str, Any]] = {}
    for row in rows:
        raw_relative_path = str(row.get("Path") or row.get("Name") or "").strip().strip("/")
        if not raw_relative_path:
            continue
        relative_parts = [segment for segment in raw_relative_path.split("/") if segment and segment != "."]
        if not relative_parts:
            continue
        is_dir = bool(row.get("IsDir", False))
        if is_dir:
            if len(relative_parts) > max_depth:
                continue
            entry_path = root_storage_path.join(*relative_parts)
            items_by_uri.setdefault(
                entry_path.to_uri(),
                _folder_index_item(
                    root=root,
                    root_storage_path=root_storage_path,
                    entry_path=entry_path,
                    depth=len(relative_parts),
                ),
            )
            parent_parts = relative_parts[:-1]
            if parent_parts:
                parent_path = root_storage_path.join(*parent_parts)
                parent_item = items_by_uri.setdefault(
                    parent_path.to_uri(),
                    _folder_index_item(
                        root=root,
                        root_storage_path=root_storage_path,
                        entry_path=parent_path,
                        depth=len(parent_parts),
                    ),
                )
                parent_item["child_folder_count"] = int(parent_item.get("child_folder_count") or 0) + 1
            continue
        if len(relative_parts) < 2:
            continue
        parent_parts = relative_parts[:-1]
        if len(parent_parts) > max_depth:
            continue
        parent_path = root_storage_path.join(*parent_parts)
        parent_uri = parent_path.to_uri()
        item = items_by_uri.setdefault(
            parent_uri,
            _folder_index_item(
                root=root,
                root_storage_path=root_storage_path,
                entry_path=parent_path,
                depth=len(parent_parts),
            ),
        )
        _mark_has_any_file_ancestors(
            items_by_uri=items_by_uri,
            root=root,
            root_storage_path=root_storage_path,
            folder_parts=parent_parts,
        )
        file_row = _video_file_index_item(
            root=root,
            root_storage_path=root_storage_path,
            entry_path=root_storage_path.join(*relative_parts),
            size=_coerce_size(row.get("Size")),
        )
        if file_row is None:
            item["non_video_file_count"] = int(item.get("non_video_file_count") or 0) + 1
            continue
        item["video_files"] = _dedupe_video_file_rows([*item["video_files"], file_row])
        item["video_file_count"] = len(item["video_files"])
    items = list(items_by_uri.values())
    items.sort(key=lambda item: (str(item.get("path") or "").lower(), str(item.get("label") or "").lower()))
    return items


def _index_storage_root(manager: Any, root: RootConfig, root_storage_path: StoragePath, *, max_depth: int) -> list[dict[str, Any]]:
    items_by_uri: dict[str, dict[str, Any]] = {}
    pending: list[tuple[StoragePath, int]] = [(root_storage_path, 0)]
    while pending:
        current_path, depth = pending.pop()
        entries = manager.list_dir(current_path)
        current_depth = depth
        if current_depth > 0:
            current_uri = current_path.to_uri()
            current_item = items_by_uri.setdefault(
                current_uri,
                _folder_index_item(
                    root=root,
                    root_storage_path=root_storage_path,
                    entry_path=current_path,
                    depth=current_depth,
                ),
            )
            video_rows: list[dict[str, Any]] = []
            non_video_count = 0
            has_any_file = False
            child_folder_count = 0
            for entry in entries:
                if entry.is_dir:
                    child_folder_count += 1
                    continue
                has_any_file = True
                file_row = _video_file_index_item(
                    root=root,
                    root_storage_path=root_storage_path,
                    entry_path=entry.path,
                    size=entry.size,
                )
                if file_row is None:
                    non_video_count += 1
                    continue
                video_rows.append(file_row)
            current_item["video_files"] = _dedupe_video_file_rows(video_rows)
            current_item["video_file_count"] = len(current_item["video_files"])
            current_item["non_video_file_count"] = non_video_count
            current_item["has_any_file"] = bool(has_any_file)
            current_item["child_folder_count"] = child_folder_count
            if has_any_file:
                current_parts = [segment for segment in current_path.relative_to(root_storage_path).split("/") if segment]
                _mark_has_any_file_ancestors(
                    items_by_uri=items_by_uri,
                    root=root,
                    root_storage_path=root_storage_path,
                    folder_parts=current_parts,
                )
        if depth >= max_depth:
            continue
        for entry in entries:
            if not entry.is_dir:
                continue
            next_depth = depth + 1
            items_by_uri.setdefault(
                entry.path.to_uri(),
                _folder_index_item(
                    root=root,
                    root_storage_path=root_storage_path,
                    entry_path=entry.path,
                    depth=next_depth,
                ),
            )
            pending.append((entry.path, next_depth))
    items = list(items_by_uri.values())
    items.sort(key=lambda item: (str(item.get("path") or "").lower(), str(item.get("label") or "").lower()))
    return items


def _folder_index_item(*, root: RootConfig, root_storage_path: StoragePath, entry_path: StoragePath, depth: int) -> dict[str, Any]:
    return {
        "label": entry_path.name(),
        "normalized_name": normalize_title(entry_path.name()),
        "path": storage_entry_display_path(root=root, root_storage_path=root_storage_path, entry_path=entry_path),
        "storage_uri": entry_path.to_uri(),
        "root_label": root.label,
        "root_path": str(root.path),
        "root_storage_uri": _root_storage_identity(root),
        "kind": root.kind,
        "depth": depth,
        "video_file_count": 0,
        "non_video_file_count": 0,
        "has_any_file": False,
        "child_folder_count": 0,
        "video_files": [],
    }


def _video_file_index_item(
    *,
    root: RootConfig,
    root_storage_path: StoragePath,
    entry_path: StoragePath,
    size: int | None,
) -> dict[str, Any] | None:
    suffix = entry_path.suffix().lower()
    if suffix not in VIDEO_EXTENSIONS:
        return None
    path_text = storage_entry_display_path(root=root, root_storage_path=root_storage_path, entry_path=entry_path)
    return {
        "name": entry_path.name(),
        "path": path_text,
        "storage_uri": entry_path.to_uri() if entry_path.backend != "local" else "",
        "relative_path": entry_path.relative_to(root_storage_path),
        "size": int(size or 0),
    }


def _coerce_size(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    return int(text) if text.isdigit() else 0


def _dedupe_video_file_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("storage_uri") or row.get("path") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _root_for_index_item(
    *,
    item: dict[str, Any],
    roots_by_storage: dict[str, RootConfig],
    roots_by_path: dict[str, RootConfig],
    fallback_roots_by_path: dict[str, RootConfig],
) -> RootConfig | None:
    root_storage_uri = str(item.get("root_storage_uri") or "").strip()
    if root_storage_uri and root_storage_uri in roots_by_storage:
        return roots_by_storage[root_storage_uri]

    root_path_text = str(item.get("root_path") or "").strip()
    if root_path_text and root_path_text in roots_by_path:
        return roots_by_path[root_path_text]

    if root_path_text:
        fallback = fallback_roots_by_path.get(root_path_text)
        if fallback is not None:
            return fallback
        fallback = RootConfig(
            path=Path(root_path_text),
            label=str(item.get("root_label") or Path(root_path_text).name),
            priority=50,
            kind=str(item.get("kind") or "mixed"),
            storage_uri=root_storage_uri,
            connection_id=str(item.get("connection_id") or ""),
            connection_label=str(item.get("connection_label") or ""),
            share_name=str(item.get("share_name") or ""),
        )
        fallback_roots_by_path[root_path_text] = fallback
        return fallback

    return None


def _relative_to_root(path: str, root: RootConfig) -> str:
    try:
        return str(Path(path).relative_to(root.path))
    except ValueError:
        return ""


def _mark_has_any_file_ancestors(
    *,
    items_by_uri: dict[str, dict[str, Any]],
    root: RootConfig,
    root_storage_path: StoragePath,
    folder_parts: list[str],
) -> None:
    for length in range(1, len(folder_parts) + 1):
        ancestor_parts = folder_parts[:length]
        ancestor_path = root_storage_path.join(*ancestor_parts)
        ancestor_item = items_by_uri.setdefault(
            ancestor_path.to_uri(),
            _folder_index_item(
                root=root,
                root_storage_path=root_storage_path,
                entry_path=ancestor_path,
                depth=len(ancestor_parts),
            ),
        )
        ancestor_item["has_any_file"] = True


def storage_entry_display_path(*, root: RootConfig, root_storage_path: StoragePath, entry_path: StoragePath) -> str:
    if entry_path.backend == "local":
        return entry_path.normalized_path()
    relative = entry_path.relative_to(root_storage_path)
    parts = [segment for segment in str(relative).split("/") if segment and segment != "."]
    if not parts:
        return str(root.path)
    return str(Path(root.path).joinpath(*parts))


def _root_storage_identity(root: RootConfig) -> str:
    return str(root.storage_uri or root.path)


def _root_report_row(root: RootConfig) -> dict[str, Any]:
    return {
        "label": root.label,
        "path": str(root.path),
        "storage_uri": _root_storage_identity(root),
        "kind": root.kind,
        "connection_id": root.connection_id,
        "connection_label": root.connection_label,
        "share_name": root.share_name,
    }
