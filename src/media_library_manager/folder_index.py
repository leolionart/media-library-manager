from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .models import RootConfig
from .rclone_cli import list_entries_recursive
from .storage import StoragePath, default_storage_manager
from .sync_integrations import normalize_title


DEFAULT_FOLDER_INDEX_MAX_DEPTH = 6


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
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "roots": len(roots),
            "folders": len(items),
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


def root_to_index_storage_path(root: RootConfig) -> StoragePath:
    raw = root.storage_uri or str(root.path)
    if raw.startswith(("local://", "smb://", "rclone://")):
        return StoragePath.from_uri(raw)
    return StoragePath.local(raw)


def _index_rclone_root(root: RootConfig, root_storage_path: StoragePath, *, max_depth: int) -> list[dict[str, Any]]:
    rows = list_entries_recursive(
        root_storage_path.rclone_remote,
        root_storage_path.normalized_path(),
        dirs_only=True,
        fast_list=True,
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        if not bool(row.get("IsDir", True)):
            continue
        raw_relative_path = str(row.get("Path") or row.get("Name") or "").strip().strip("/")
        if not raw_relative_path:
            continue
        relative_parts = [segment for segment in raw_relative_path.split("/") if segment and segment != "."]
        if not relative_parts or len(relative_parts) > max_depth:
            continue
        entry_path = root_storage_path.join(*relative_parts)
        items.append(_folder_index_item(root=root, root_storage_path=root_storage_path, entry_path=entry_path, depth=len(relative_parts)))
    items.sort(key=lambda item: (str(item.get("path") or "").lower(), str(item.get("label") or "").lower()))
    return items


def _index_storage_root(manager: Any, root: RootConfig, root_storage_path: StoragePath, *, max_depth: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    pending: list[tuple[StoragePath, int]] = [(root_storage_path, 0)]
    while pending:
        current_path, depth = pending.pop()
        if depth >= max_depth:
            continue
        for entry in manager.list_dir(current_path):
            if not entry.is_dir:
                continue
            next_depth = depth + 1
            items.append(_folder_index_item(root=root, root_storage_path=root_storage_path, entry_path=entry.path, depth=next_depth))
            pending.append((entry.path, next_depth))
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
    }


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
