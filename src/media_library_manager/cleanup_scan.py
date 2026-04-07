from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .models import MediaFile, RootConfig
from .provider_path_resolution import map_provider_directory
from .providers.base import ProviderError
from .providers.radarr import RadarrClient
from .providers.sonarr import SonarrClient
from .scanner import build_folder_media_duplicate_groups, inspect_media_file
from .scanner_storage import ScannedFileEntry
from .sync_integrations import build_provider_config


CleanupProgressCallback = Callable[[dict[str, object]], None]
MIN_CLEANUP_FOLDER_INDEX_VERSION = 2


def scan_provider_cleanup(
    integrations: dict[str, Any],
    *,
    providers: list[str] | None = None,
    roots: list[RootConfig] | None = None,
    folder_index_report: dict[str, Any] | None = None,
    progress_callback: CleanupProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
    start_root_index: int = 1,
) -> dict[str, Any]:
    requested = [provider for provider in (providers or ["radarr", "sonarr"]) if provider in {"radarr", "sonarr"}]
    if not requested:
        return _build_cleanup_report(providers=[], provider_items=[], files=[], skipped_items=[], errors=[])
    cache_error = _validate_cleanup_folder_index(folder_index_report)
    if cache_error:
        raise ValueError(cache_error)

    files: list[MediaFile] = []
    provider_items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    active_providers: list[str] = []
    connected_roots = roots or []
    folder_index_lookup = _build_folder_index_lookup(folder_index_report)
    total_files = 0

    for provider in requested:
        config = build_provider_config(integrations.get(provider, {}))
        if not config.enabled:
            skipped_items.append({"provider": provider, "reason": "provider_disabled"})
            continue
        try:
            items = _list_provider_items(provider, config)
            active_providers.append(provider)
        except ProviderError as exc:
            errors.append({"provider": provider, "message": str(exc)})
            continue

        for item in items:
            if should_cancel and should_cancel():
                raise RuntimeError("job cancelled")
            raw_path = str(item.get("path") or "").strip()
            if not raw_path:
                skipped_items.append({"provider": provider, "id": item.get("id"), "title": item.get("title"), "reason": "missing_path"})
                continue
            resolved, status = _resolve_provider_directory_from_cache(raw_path=raw_path, roots=connected_roots)
            if resolved is None:
                skipped_items.append(
                    {"provider": provider, "id": item.get("id"), "title": item.get("title"), "path": raw_path, "reason": status}
                )
                continue
            folder_rows = _lookup_folder_index_rows(folder_index_lookup, resolved=resolved)
            if not folder_rows:
                skipped_items.append(
                    {"provider": provider, "id": item.get("id"), "title": item.get("title"), "path": raw_path, "reason": "folder_index_miss"}
                )
                continue
            provider_items.append(
                {
                    "provider": provider,
                    "id": item.get("id"),
                    "title": item.get("title") or resolved.path.name,
                    "year": item.get("year"),
                    "path": str(resolved.path),
                    "provider_path": raw_path,
                    "storage_uri": resolved.storage_uri,
                }
            )
            root = RootConfig(
                path=resolved.path,
                label=str(item.get("title") or resolved.path.name),
                priority=100,
                kind="movie" if provider == "radarr" else "series",
                connection_id=resolved.connection_id,
                connection_label=resolved.connection_label,
                storage_uri=resolved.storage_uri,
                share_name=resolved.share_name,
            )
            cached_files = _media_files_from_index_rows(folder_rows, root=root)
            files.extend(cached_files)
            total_files += len(cached_files)
            if progress_callback:
                progress_callback(
                    {
                        "event": "root_completed",
                        "index": len(provider_items),
                        "total_roots": len(provider_items),
                        "root_label": root.label,
                        "root_path": str(root.path),
                        "indexed_files": len(cached_files),
                        "total_indexed_files": total_files,
                    }
                )

    if progress_callback:
        progress_callback(
            {
                "event": "provider_roots_loaded",
                "providers": active_providers,
                "roots_scanned": len(provider_items),
                "skipped": len(skipped_items),
                "errors": len(errors),
            }
        )
    if progress_callback:
        progress_callback(
            {
                "event": "scan_completed",
                "total_roots": len(provider_items),
                "total_indexed_files": len(files),
                "exact_duplicate_groups": 0,
                "media_collision_groups": 0,
                "folder_media_duplicate_groups": len(build_folder_media_duplicate_groups(files)),
            }
        )
    return _build_cleanup_report(
        providers=active_providers,
        provider_items=provider_items,
        files=files,
        skipped_items=skipped_items,
        errors=errors,
    )


def _validate_cleanup_folder_index(report: dict[str, Any] | None) -> str | None:
    if not isinstance(report, dict):
        return "Refresh cached folder metadata in Library Finder before running Library Cleanup."
    if int(report.get("version", 0) or 0) < MIN_CLEANUP_FOLDER_INDEX_VERSION:
        return "Cached folder metadata is outdated. Refresh Library Finder to rebuild the folder index."
    items = report.get("items")
    if not isinstance(items, list) or not items:
        return "Cached folder metadata is empty. Refresh Library Finder before running Library Cleanup."
    sample = next((item for item in items if isinstance(item, dict)), None)
    if sample is None or "video_files" not in sample:
        return "Cached folder metadata is missing video file details. Refresh Library Finder before running Library Cleanup."
    return None


def _build_folder_index_lookup(report: dict[str, Any] | None) -> dict[str, dict[str, dict[str, Any]]]:
    by_storage_uri: dict[str, dict[str, Any]] = {}
    by_path: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []
    if not isinstance(report, dict):
        return {"by_storage_uri": by_storage_uri, "by_path": by_path, "items": items}
    for item in report.get("items", []):
        if not isinstance(item, dict):
            continue
        items.append(item)
        path = str(item.get("path") or "")
        storage_uri = str(item.get("storage_uri") or "")
        if path:
            by_path[path] = item
        if storage_uri:
            by_storage_uri[storage_uri] = item
    return {"by_storage_uri": by_storage_uri, "by_path": by_path, "items": items}


def _resolve_provider_directory_from_cache(*, raw_path: str, roots: list[RootConfig]) -> tuple[Any | None, str]:
    mapped = map_provider_directory(raw_path=raw_path, roots=roots)
    if mapped is not None:
        return mapped, "ok"
    local_path = Path(str(raw_path or "")).expanduser().resolve()
    if local_path.exists() and not local_path.is_dir():
        return None, "path_not_directory"
    return None, "path_not_found"


def _lookup_folder_index_rows(folder_index_lookup: dict[str, Any], *, resolved: Any) -> list[dict[str, Any]]:
    direct_match: dict[str, Any] | None = None
    storage_uri = str(resolved.storage_uri or "")
    if storage_uri:
        direct_match = folder_index_lookup["by_storage_uri"].get(storage_uri)
    if direct_match is None:
        direct_match = folder_index_lookup["by_path"].get(str(resolved.path))
    if direct_match is None:
        return []

    resolved_path = Path(str(resolved.path))
    matched: list[dict[str, Any]] = []
    for item in folder_index_lookup.get("items", []):
        if not isinstance(item, dict):
            continue
        item_path_text = str(item.get("path") or "").strip()
        if not item_path_text:
            continue
        item_path = Path(item_path_text)
        if item_path == resolved_path or item_path.is_relative_to(resolved_path):
            matched.append(item)
    matched.sort(key=lambda item: (int(item.get("depth") or 0), str(item.get("path") or "").lower()))
    return matched


def rebuild_cleanup_report(existing_report: dict[str, Any], files: list[MediaFile]) -> dict[str, Any]:
    return _build_cleanup_report(
        providers=[str(provider) for provider in existing_report.get("providers", [])],
        provider_items=[item for item in existing_report.get("provider_items", []) if isinstance(item, dict)],
        files=files,
        skipped_items=[item for item in existing_report.get("skipped_items", []) if isinstance(item, dict)],
        errors=[item for item in existing_report.get("errors", []) if isinstance(item, dict)],
    )


def _media_files_from_index_rows(rows: list[dict[str, Any]], *, root: RootConfig) -> list[MediaFile]:
    files: list[MediaFile] = []
    root_path = root.path
    seen: set[str] = set()
    for item in rows:
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
            video_path = Path(path)
            try:
                relative_path = str(video_path.relative_to(root_path))
            except ValueError:
                continue
            entry = ScannedFileEntry(
                path=path,
                relative_path=relative_path,
                size=int(video.get("size") or 0),
                stem=Path(name).stem,
                suffix=Path(name).suffix.lower(),
                parent_name=video_path.parent.name,
            )
            media = inspect_media_file(entry, root)
            media.path = video_path
            media.storage_uri = storage_uri
            files.append(media)
    return files


def _build_cleanup_report(
    *,
    providers: list[str],
    provider_items: list[dict[str, Any]],
    files: list[MediaFile],
    skipped_items: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    groups = _attach_group_metadata(build_folder_media_duplicate_groups(files), provider_items)
    return {
        "version": 1,
        "providers": providers,
        "provider_items": provider_items,
        "summary": {
            "providers": len(providers),
            "roots_scanned": len(provider_items),
            "indexed_files": len(files),
            "folder_media_duplicate_groups": len(groups),
            "groups": len(groups),
            "skipped": len(skipped_items),
            "errors": len(errors),
        },
        "files": [item.to_dict() for item in files],
        "folder_media_duplicates": groups,
        "groups": groups,
        "skipped_items": skipped_items,
        "errors": errors,
    }


def _list_provider_items(provider: str, config: Any) -> list[dict[str, Any]]:
    if provider == "radarr":
        return RadarrClient(config).list_movies()
    if provider == "sonarr":
        return SonarrClient(config).list_series()
    raise ProviderError(f"unsupported provider: {provider}")


def _attach_group_metadata(groups: list[dict[str, Any]], provider_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    item_by_path = {str(item.get("path") or ""): item for item in provider_items}
    attached: list[dict[str, Any]] = []
    for group in groups:
        provider_item = item_by_path.get(str(group.get("root_path") or ""), {})
        attached.append(
            {
                **group,
                "id": f"{group.get('media_key')}::{group.get('folder_path')}",
                "provider": provider_item.get("provider"),
                "provider_item_id": provider_item.get("id"),
                "provider_item_title": provider_item.get("title"),
                "provider_item_year": provider_item.get("year"),
                "provider_item_path": provider_item.get("path"),
            }
        )
    return attached
